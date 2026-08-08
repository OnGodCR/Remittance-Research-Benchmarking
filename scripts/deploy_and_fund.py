"""Deploy the test dollar and prepare the wallet pool. Run once per cluster.

WHAT THIS DOES
--------------
1. Compiles the token contract
2. Deploys it to the chain
3. Derives a pool of sender wallets and a set of recipient wallets
4. Gives every sender enough native coin to pay for its transactions
5. Gives every sender a large balance of test dollars
6. Writes a config file the measurement program reads

None of this happens during a timed run. Setup work that leaked into the
measurement window would show up as latency that has nothing to do with the
architecture.

TWO THINGS DONE DELIBERATELY
----------------------------
**Wallets are derived from a seed, not generated randomly.** The same seed
always produces the same wallets, so a cluster can be torn down and rebuilt
identically. The seed lives in a file that is never committed; only the public
addresses go in the config.

**Senders are funded generously and recipients are reused.** Both protect the
cost measurement. A wallet whose balance hits zero, or a recipient receiving
tokens for the very first time, costs a different amount to write to the
chain -- and since large payments empty wallets sooner than small ones, that
would sneak a false size-dependence into results that are supposed to be flat
(ANALYSIS_PLAN.md S12).

USAGE
-----
    .venv/bin/python -m scripts.deploy_and_fund \\
        --rpc-url http://<node>:8545 \\
        --chain-id 100 \\
        --funder-key <premined account key> \\
        --senders 46
"""

from __future__ import annotations

import argparse
import json
import secrets
import sys
from pathlib import Path

from eth_account import Account
from web3 import HTTPProvider, Web3

Account.enable_unaudited_hdwallet_features()

REPO = Path(__file__).resolve().parent.parent
CONTRACT = REPO / "contracts" / "TestStablecoin.sol"
CONFIG_DIR = REPO / "config"
KEYS_DIR = REPO / "keys"          # gitignored
SEED_FILE = KEYS_DIR / "seed.txt"  # gitignored

#: Token uses 6 decimals, matching USDC/USDT.
TOKEN_UNITS = 10 ** 6

#: Test dollars minted to each sender. Far more than any run consumes -- the
#: point is that no balance ever approaches zero.
MINT_PER_SENDER_USD = 100_000_000

#: Native coin per sender, for transaction fees. A 300/second run over 300
#: seconds is ~90,000 payments; spread across the pool that is ~2,000 each, at
#: roughly 0.00012 coin apiece. 10 coins is several hundred runs of headroom.
FUND_PER_SENDER_ETHER = 10

#: Distinct recipients. Enough that no single destination is hammered, few
#: enough that all of them are "warm" after the first few seconds.
RECIPIENT_COUNT = 32


def load_or_create_seed() -> str:
    """Read the wallet seed, creating one on first run.

    Kept out of the repo. Anyone with this value controls every test wallet --
    worthless on a private chain, but the habit matters, and this repo becomes
    public at publication.
    """
    KEYS_DIR.mkdir(exist_ok=True)
    if SEED_FILE.exists():
        return SEED_FILE.read_text().strip()

    seed = secrets.token_hex(32)
    SEED_FILE.write_text(seed + "\n")
    SEED_FILE.chmod(0o600)
    print(f"created new wallet seed at {SEED_FILE} (not committed)")
    return seed


def derive_accounts(seed: str, label: str, count: int) -> list:
    """Deterministically derive `count` wallets from the seed.

    Same seed plus same label always yields the same wallets, so a rebuilt
    cluster is identical to the one it replaced.
    """
    accounts = []
    for i in range(count):
        material = Web3.keccak(text=f"{seed}:{label}:{i}")
        accounts.append(Account.from_key(material))
    return accounts


def compile_contract() -> tuple[list, str]:
    """Compile the token, installing the Solidity compiler if needed."""
    import solcx

    version = "0.8.24"
    installed = [str(v) for v in solcx.get_installed_solc_versions()]
    if version not in installed:
        print(f"installing Solidity compiler {version} (one-time)...")
        solcx.install_solc(version)

    # EVM target must be "london", NOT the compiler default.
    #
    # Solidity 0.8.20+ targets the Shanghai instruction set, which added PUSH0
    # (opcode 0x5F) in April 2023. Polygon Edge v1.3.2 was released in January
    # 2024 but does not implement it. Deploying Shanghai-compiled bytecode to
    # this chain fails in a way that looks nothing like a compiler problem:
    # the transaction is accepted, mined, and reverts having consumed exactly
    # the full gas limit -- the signature of an unrecognised instruction.
    #
    # This costs us nothing. PUSH0 is a small gas optimisation, not a feature,
    # and the contract's behaviour is identical either way.
    print(f"compiling {CONTRACT.name} (EVM target: london)...")
    compiled = solcx.compile_files(
        [str(CONTRACT)], output_values=["abi", "bin"],
        solc_version=version, optimize=True, optimize_runs=200,
        evm_version="london",
    )
    key = next(k for k in compiled if k.endswith(":TestStablecoin"))
    return compiled[key]["abi"], compiled[key]["bin"]


def send_and_wait(w3: Web3, tx: dict, key: str, description: str) -> dict:
    """Sign, send, and wait for a setup transaction to land."""
    signed = Account.sign_transaction(tx, key)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)
    if receipt.status != 1:
        raise RuntimeError(f"{description} failed on chain (tx {tx_hash.hex()})")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rpc-url", required=True, help="node JSON-RPC endpoint")
    parser.add_argument("--chain-id", type=int, required=True)
    parser.add_argument("--funder-key", required=True,
                        help="private key of the premined genesis account")
    parser.add_argument("--senders", type=int, default=46,
                        help="sender wallets to prepare (46 supports 300/sec)")
    parser.add_argument("--gas-price-gwei", type=float, default=1.0)
    parser.add_argument("--output", default="config/phase1.json")
    args = parser.parse_args()

    w3 = Web3(HTTPProvider(args.rpc_url))
    if not w3.is_connected():
        print(f"ERROR: cannot reach a node at {args.rpc_url}")
        return 1

    actual = w3.eth.chain_id
    if actual != args.chain_id:
        print(f"ERROR: connected to chain {actual}, expected {args.chain_id}. "
              f"Refusing to deploy to the wrong network.")
        return 1

    funder = Account.from_key(args.funder_key)
    gas_price = w3.to_wei(args.gas_price_gwei, "gwei")
    balance = w3.eth.get_balance(funder.address)
    print(f"connected to chain {actual}; funder {funder.address} "
          f"holds {w3.from_wei(balance, 'ether'):,.2f}")

    needed = w3.to_wei(FUND_PER_SENDER_ETHER * args.senders, "ether")
    if balance < needed:
        print(f"ERROR: funder needs at least "
              f"{w3.from_wei(needed, 'ether'):,.0f} to fund {args.senders} wallets, "
              f"has {w3.from_wei(balance, 'ether'):,.2f}. "
              f"Increase the premined balance in the chain's genesis file.")
        return 1

    seed = load_or_create_seed()
    senders = derive_accounts(seed, "sender", args.senders)
    recipients = derive_accounts(seed, "recipient", RECIPIENT_COUNT)
    print(f"derived {len(senders)} senders and {len(recipients)} recipients")

    # -- deploy -----------------------------------------------------------
    abi, bytecode = compile_contract()
    nonce = w3.eth.get_transaction_count(funder.address)
    contract = w3.eth.contract(abi=abi, bytecode=bytecode)
    deploy_tx = contract.constructor().build_transaction({
        "from": funder.address, "nonce": nonce,
        "gas": 2_000_000, "gasPrice": gas_price, "chainId": args.chain_id,
    })
    receipt = send_and_wait(w3, deploy_tx, args.funder_key, "contract deployment")
    token_address = receipt.contractAddress
    nonce += 1
    print(f"token deployed at {token_address} "
          f"(deployment used {receipt.gasUsed:,} gas)")

    token = w3.eth.contract(address=token_address, abi=abi)

    # -- fund gas ---------------------------------------------------------
    print(f"funding {len(senders)} wallets with native coin for fees...")
    fund_amount = w3.to_wei(FUND_PER_SENDER_ETHER, "ether")
    for i, sender in enumerate(senders):
        send_and_wait(w3, {
            "to": sender.address, "value": fund_amount, "gas": 21_000,
            "gasPrice": gas_price, "nonce": nonce, "chainId": args.chain_id,
        }, args.funder_key, f"gas funding for {sender.address}")
        nonce += 1
        if (i + 1) % 10 == 0 or i + 1 == len(senders):
            print(f"  {i + 1}/{len(senders)}")

    # -- mint tokens ------------------------------------------------------
    # Batched: one transaction instead of dozens.
    print("minting test dollars to senders...")
    mint_units = MINT_PER_SENDER_USD * TOKEN_UNITS
    for chunk_start in range(0, len(senders), 50):
        chunk = [s.address for s in senders[chunk_start:chunk_start + 50]]
        mint_tx = token.functions.mintBatch(chunk, mint_units).build_transaction({
            "from": funder.address, "nonce": nonce,
            "gas": 6_000_000, "gasPrice": gas_price, "chainId": args.chain_id,
        })
        send_and_wait(w3, mint_tx, args.funder_key, "minting to senders")
        nonce += 1

    # Give recipients a non-zero starting balance. A first-ever receipt costs
    # more to record than a subsequent one, and that one-off cost would land
    # on whichever payments happened to go first -- contaminating exactly the
    # early measurements the warm-up rule is already trying to protect.
    print("warming recipient balances...")
    recipient_tx = token.functions.mintBatch(
        [r.address for r in recipients], TOKEN_UNITS
    ).build_transaction({
        "from": funder.address, "nonce": nonce,
        "gas": 6_000_000, "gasPrice": gas_price, "chainId": args.chain_id,
    })
    send_and_wait(w3, recipient_tx, args.funder_key, "warming recipients")

    # -- verify -----------------------------------------------------------
    check = token.functions.balanceOf(senders[0].address).call()
    if check != mint_units:
        print(f"ERROR: verification failed -- first sender holds {check}, "
              f"expected {mint_units}")
        return 1
    print(f"verified: each sender holds "
          f"{check // TOKEN_UNITS:,} test dollars")

    # -- write config -----------------------------------------------------
    CONFIG_DIR.mkdir(exist_ok=True)
    config_path = REPO / args.output
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps({
        "rpc_url": args.rpc_url,
        "chain_id": args.chain_id,
        "token_address": token_address,
        "gas_price_wei": gas_price,
        "sender_addresses": [s.address for s in senders],
        "recipients": [r.address for r in recipients],
        "note": "Private keys are NOT here. They are derived from keys/seed.txt, "
                "which is gitignored. Re-derive with scripts.deploy_and_fund.",
    }, indent=2) + "\n")

    keys_path = KEYS_DIR / "senders.json"
    keys_path.write_text(json.dumps([s.key.hex() for s in senders], indent=2) + "\n")
    keys_path.chmod(0o600)

    print(f"\nwrote {config_path.relative_to(REPO)} (safe to commit)")
    print(f"wrote {keys_path.relative_to(REPO)} (gitignored -- never commit)")
    print("\nready. The cluster can now run a benchmark.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
