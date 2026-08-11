"""Command line for running benchmarks.

Phase 1 (validate the pipeline works, at a deliberately slow rate):

    .venv/bin/python -m harness.cli run \\
        --config config/phase1.json --tps 5 --window 300 --amount 200

Check the harness's own ceiling before trusting any high-rate result:

    .venv/bin/python -m harness.cli capacity

A full sweep for one architecture:

    .venv/bin/python -m harness.cli sweep --config config/phase1.json --phase phase-2
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from .adapters.lightning import LightningAdapter
from .adapters.null import NullAdapter

# PolygonAdapter is imported lazily, inside the functions that use it.
#
# It pulls in web3 and eth_account, which the Lightning generator has no reason
# to install -- and a missing Polygon dependency must never stop a Lightning
# run. Importing it at module scope meant every `harness run` on the Lightning
# cluster died before reaching the adapter it actually needed.
#
# This changes nothing about measurement: the import moves, the code does not.
from .core.arrival import seed_for
from .core.parallel import run_parallel_benchmark
from .core.runner import run_benchmark
from .core.storage import RunConfig, Store

REPO = Path(__file__).resolve().parent.parent
DEFAULT_DB = REPO / "data" / "working" / "runs.sqlite"

#: The pre-registered load ramp (ANALYSIS_PLAN.md S2).
LOAD_STEPS = [10, 25, 50, 100, 150, 200, 300]

#: The pre-registered amounts. $200 is the World Bank benchmark and leads
#: every comparison.
AMOUNTS = [10.0, 50.0, 200.0, 500.0]

#: Pre-registered repeat count (realism technique #8).
REPEATS = 5

#: Fixed window per run (claude.md S6).
WINDOW = 300.0

#: One base seed for the whole project makes every arrival pattern
#: reproducible while keeping repeats independent of each other.
BASE_SEED = 20260807

#: The realism techniques active during phase-2-full-stack, recorded with
#: every run so the conditions are evidence rather than an inference from a
#: phase name. Values match METHODOLOGY_LOG.md S4 exactly.
FULL_STACK_REALISM = {
    "multi_region": {
        "enabled": True,
        "regions": ["us-east4", "asia-south1", "asia-southeast1", "europe-west2"],
        "validators": 4,
    },
    "injected_impairment": {
        "enabled": True,
        "scope": "validator-to-validator only; measurement path unimpaired",
        "per_validator": [
            {"region": "us-east4", "delay_ms": 20, "jitter_ms": 4, "loss_pct": 0.10},
            {"region": "asia-south1", "delay_ms": 45, "jitter_ms": 12, "loss_pct": 0.40},
            {"region": "asia-southeast1", "delay_ms": 40, "jitter_ms": 10, "loss_pct": 0.30},
            {"region": "europe-west2", "delay_ms": 25, "jitter_ms": 6, "loss_pct": 0.15},
        ],
    },
    "background_traffic": {
        "enabled": True,
        "base_tps": 60, "peak_tps": 115, "mean_tps": 88,
        "tx_type": "native transfer, 21000 gas",
        "calibrated_to": "Polygon mainnet ~87 tx/sec (7.5M/day)",
    },
    "hardware_matched": {
        "enabled": True,
        "machine_type": "n2-standard-8",
        "vcpu": 8, "ram_gb": 32,
        "note": "CPU/RAM matched to published Polygon validator specs; "
                "storage deliberately not matched",
    },
    "adversarial_nodes": {"enabled": False, "note": "separate arm"},
    "repeats": REPEATS,
}


def load_polygon_adapter(config_path: Path):
    from .adapters.polygon import PolygonAdapter

    config = json.loads(config_path.read_text())
    keys_path = REPO / "keys" / "senders.json"
    if not keys_path.exists():
        raise SystemExit(
            f"missing {keys_path}. Run scripts/deploy_and_fund.py first -- "
            f"it derives the wallets and writes their keys."
        )
    keys = json.loads(keys_path.read_text())
    if len(keys) != len(config["sender_addresses"]):
        raise SystemExit(
            f"config lists {len(config['sender_addresses'])} senders but "
            f"{len(keys)} keys are present. Re-run deploy_and_fund.py."
        )
    return PolygonAdapter(
        rpc_url=config["rpc_url"],
        token_address=config["token_address"],
        sender_keys=keys,
        recipients=config["recipients"],
        chain_id=config["chain_id"],
        gas_price_wei=config.get("gas_price_wei", 1_000_000_000),
    )


def load_lightning_adapter(config_path: Path) -> LightningAdapter:
    """Build the LND adapter from the config lightning_bootstrap.py wrote.

    That script only writes the config after verifying every planned channel is
    active, so a config existing here means the topology is complete. Failing
    loudly on a missing file is better than running against a half-funded
    network, which would still produce numbers -- biased against Lightning, and
    for a reason that is ours rather than the architecture's.
    """
    config = json.loads(config_path.read_text())
    for key in ("senders", "recipients", "btc_usd_rate"):
        if key not in config:
            raise SystemExit(
                f"{config_path} has no '{key}'. Run scripts/lightning_bootstrap.py "
                f"first -- it funds the topology and writes this file."
            )
    return LightningAdapter(
        sender_endpoints=config["senders"],
        recipient_endpoints=config["recipients"],
        btc_usd_rate=config["btc_usd_rate"],
    )


def load_near_adapter(config_path: Path):
    """Build the NEAR adapter from the config the deploy script writes.

    Imported lazily for the same reason PolygonAdapter is: py-near is a NEAR
    dependency and a Lightning or Polygon generator has no reason to install
    it. A missing dependency for one architecture must never stop a run of
    another.
    """
    from .adapters.near import NearAdapter

    config = json.loads(config_path.read_text())
    for key in ("rpc_url", "token_contract", "recipients"):
        if key not in config:
            raise SystemExit(
                f"{config_path} has no '{key}'. Run the NEAR deploy script "
                f"first -- it creates the accounts, deploys the NEP-141 token "
                f"and writes this file."
            )
    keys_path = REPO / "keys" / "near_senders.json"
    if not keys_path.exists():
        raise SystemExit(f"missing {keys_path}. Run the NEAR deploy script first.")
    return NearAdapter(
        rpc_url=config["rpc_url"],
        token_contract=config["token_contract"],
        sender_keys=json.loads(keys_path.read_text()),
        recipients=config["recipients"],
    )


def _architecture_of(config_path: Path) -> str:
    """Pick the adapter from the config, not from a flag.

    A flag could disagree with the config and mislabel a run's architecture in
    the database -- the kind of quiet error that only surfaces in phase 6, when
    the cross-architecture comparison is being written.
    """
    try:
        return json.loads(config_path.read_text()).get("architecture", "polygon")
    except Exception:
        return "polygon"


def _adapter_spec(config_path: Path) -> dict:
    """Everything a worker process needs to build its own adapter.

    Passed as plain data because worker processes are spawned fresh -- an
    adapter object holds network connections that cannot cross a process
    boundary.
    """
    config = json.loads(config_path.read_text())
    keys_path = REPO / "keys" / "senders.json"
    if not keys_path.exists():
        raise SystemExit(f"missing {keys_path}. Run scripts/deploy_and_fund.py first.")
    return {
        "rpc_url": config["rpc_url"],
        "token_address": config["token_address"],
        "sender_keys": json.loads(keys_path.read_text()),
        "recipients": config["recipients"],
        "chain_id": config["chain_id"],
        "gas_price_wei": config.get("gas_price_wei", 1_000_000_000),
    }


async def cmd_run(args: argparse.Namespace) -> int:
    arch = _architecture_of(Path(args.config))
    if arch == "lightning":
        return await _run_lightning(args)
    if arch == "near":
        return await _run_near(args)

    if args.workers > 1:
        spec = _adapter_spec(Path(args.config))
        store = Store(args.db)
        cfg = RunConfig(
            architecture="polygon", adapter="polygon-edge",
            tx_size_usd=args.amount, target_tps=args.tps,
            window_seconds=args.window, repeat_index=args.repeat,
            arrival_seed=seed_for(BASE_SEED, args.tps, args.amount, args.repeat),
            phase=args.phase, arm=args.arm,
        )
        summary = await run_parallel_benchmark(cfg, store, spec, workers=args.workers)
        store.close()
        return 0 if not summary["generator_saturated"] else 2

    from .adapters.polygon import PolygonAdapter

    adapter = load_polygon_adapter(Path(args.config))

    needed = PolygonAdapter.required_pool_size(args.tps)
    have = len(adapter._sender_keys)
    if have < needed:
        print(f"WARNING: {args.tps:g}/sec wants ~{needed} sender wallets, only "
              f"{have} available. Sends will queue behind each other and the "
              f"result will measure our own client, not the chain. "
              f"Re-run deploy_and_fund.py with --senders {needed}.")

    store = Store(args.db)
    cfg = RunConfig(
        architecture="polygon", adapter=adapter.name,
        tx_size_usd=args.amount, target_tps=args.tps,
        window_seconds=args.window, repeat_index=args.repeat,
        arrival_seed=seed_for(BASE_SEED, args.tps, args.amount, args.repeat),
        phase=args.phase, arm=args.arm,
    )
    summary = await run_benchmark(adapter, cfg, store)
    store.close()
    return 0 if not summary["generator_saturated"] else 2


async def _run_lightning(args: argparse.Namespace) -> int:
    """One Lightning run.

    Single-process by design, unlike Polygon's multi-worker path. Polygon
    needed workers because signing and nonce management were CPU-bound in our
    client; a Lightning send is one HTTP call and the work happens on the LND
    nodes. Adding workers here would add complexity and a second place for the
    generator to become the bottleneck, with nothing gained. If the harness
    ever does saturate, `capacity` will show it -- the same check that caught
    Polygon's phantom knee.
    """
    adapter = load_lightning_adapter(Path(args.config))
    store = Store(args.db)
    cfg = RunConfig(
        architecture="lightning", adapter=adapter.name,
        tx_size_usd=args.amount, target_tps=args.tps,
        window_seconds=args.window, repeat_index=args.repeat,
        arrival_seed=seed_for(BASE_SEED, args.tps, args.amount, args.repeat),
        phase=args.phase, arm=args.arm,
        # The adapter mints its invoice pool during setup and needs to know how
        # many payments are coming and at what amount. Passed through the
        # existing `extra` channel rather than by changing the shared runner:
        # Polygon's 155 measured runs used the core as it stands, and altering
        # it now would mean the two architectures were measured by different
        # versions of the one instrument the whole design depends on.
        extra={
            "scheduled_count": int(args.tps * args.window * 1.2),  # Poisson headroom
            "tx_size_usd": args.amount,
        },
    )
    summary = await run_benchmark(adapter, cfg, store)
    store.close()
    return 0 if not summary["generator_saturated"] else 2


async def _run_near(args: argparse.Namespace) -> int:
    """One NEAR run.

    Single-process, like Lightning and unlike Polygon's multi-worker path.
    Polygon needed workers because signing and nonce management were CPU-bound
    in our client; a NEAR submission is one RPC call and the work happens on
    the validators. If the harness ever does saturate, `capacity` shows it.
    """
    from .adapters.near import NearAdapter

    adapter = load_near_adapter(Path(args.config))

    needed = NearAdapter.required_pool_size(args.tps)
    have = len(adapter._sender_keys)
    if have < needed:
        print(f"WARNING: {args.tps:g}/sec wants ~{needed} sender accounts, only "
              f"{have} available. NEAR orders transactions per access key by "
              f"nonce, so sends will queue behind each other and the result "
              f"will measure our own client rather than the chain.")

    store = Store(args.db)
    cfg = RunConfig(
        architecture="near", adapter=adapter.name,
        tx_size_usd=args.amount, target_tps=args.tps,
        window_seconds=args.window, repeat_index=args.repeat,
        arrival_seed=seed_for(BASE_SEED, args.tps, args.amount, args.repeat),
        phase=args.phase, arm=args.arm,
    )
    summary = await run_benchmark(adapter, cfg, store)
    store.close()
    return 0 if not summary["generator_saturated"] else 2


async def cmd_capacity(args: argparse.Namespace) -> int:
    """Find the harness's own ceiling, before it can be mistaken for a finding.

    Runs the full ramp against a backend that does nothing but wait. Any limit
    that shows up here is ours. Every real result must sit comfortably below
    the point where this starts falling behind (ANALYSIS_PLAN.md S7).
    """
    store = Store(args.db)
    print("Measuring the harness's own maximum rate.\n"
          "Anything below is OUR ceiling, not a blockchain's.\n")

    ceiling = None
    for tps in LOAD_STEPS:
        cfg = RunConfig(
            architecture="null", adapter="null", tx_size_usd=200.0,
            target_tps=float(tps), window_seconds=args.window,
            arrival_seed=seed_for(BASE_SEED, tps, 200.0, 0),
            phase="capacity-check",
        )
        summary = await run_benchmark(
            NullAdapter(settle_delay_seconds=args.settle_delay), cfg, store,
            verbose=False,
        )
        lag = summary["lag"]
        state = "SATURATED" if lag.saturated else "ok"
        print(f"  {tps:>3}/sec -> achieved {summary['achieved_tps']:6.1f} | "
              f"p95 lag {lag.p95_lag*1000:7.1f}ms | {state}")
        if lag.saturated and ceiling is None:
            ceiling = tps

    print()
    if ceiling is None:
        print(f"Harness kept up through {LOAD_STEPS[-1]}/sec. All planned load "
              f"levels are safe to measure.")
    else:
        print(f"Harness began falling behind at {ceiling}/sec. Results at or "
              f"above that rate would measure our tooling, not the chain.\n"
              f"Fix by running multiple worker processes before collecting data.")
    store.close()
    return 0


async def cmd_sweep(args: argparse.Namespace) -> int:
    """The full pre-registered matrix for one architecture.

    4 amounts x 7 load levels x 5 repeats = 140 runs, ~11.7 hours at a
    300-second window. Intended to run unattended; the cluster's idle-shutdown
    timer is the safety net if it dies partway.
    """
    store = Store(args.db)

    # Which configurations already have a completed run for this phase.
    #
    # A 12-hour sweep is long enough that something will interrupt it -- a
    # preempted machine, a crash, a stopped session. Without this, resuming
    # means either repeating 97 runs of finished work or hand-picking what to
    # re-run, and hand-picking is how configurations get silently skipped.
    already: set = set()
    if args.resume:
        rows = store.conn.execute(
            "SELECT tx_size_usd, target_tps, repeat_index FROM runs "
            "WHERE phase = ? AND invalidated = 0", (args.phase,)
        ).fetchall()
        already = {(round(r[0], 2), round(r[1], 2), r[2]) for r in rows}
        print(f"resuming: {len(already)} configurations already complete")

    todo = [(a, t, r) for a in AMOUNTS for t in LOAD_STEPS for r in range(REPEATS)
            if (round(a, 2), round(float(t), 2), r) not in already]
    total = len(todo)
    done = failed = 0

    print(f"Sweep: {total} runs to go, ~{total * WINDOW / 3600:.1f} hours of "
          f"measurement.\n")

    for amount, tps, repeat in todo:
        done += 1
        cfg = RunConfig(
            architecture="polygon", adapter="polygon-edge",
            tx_size_usd=amount, target_tps=float(tps),
            window_seconds=WINDOW, repeat_index=repeat,
            arrival_seed=seed_for(BASE_SEED, tps, amount, repeat),
            phase=args.phase, arm=args.arm,
            realism=FULL_STACK_REALISM if "full-stack" in (args.phase or "") else {},
        )
        print(f"[{done}/{total}] ${amount:g} @ {tps}/sec, repeat {repeat}")
        try:
            if args.workers > 1:
                summary = await run_parallel_benchmark(
                    cfg, store, _adapter_spec(Path(args.config)),
                    workers=args.workers, verbose=False)
            else:
                summary = await run_benchmark(
                    load_polygon_adapter(Path(args.config)), cfg, store,
                    verbose=False)
            print(f"    achieved {summary['achieved_tps']:.1f}/sec | "
                  f"ok {summary['confirmed']} fail {summary['failed']}")
            if summary["generator_saturated"]:
                print("    ^ flagged invalid: harness saturated")
        except Exception as exc:
            failed += 1
            print(f"    RUN FAILED: {type(exc).__name__}: {exc}")
            if failed > 5:
                print("\nAborting: too many failures. Fix the cluster "
                      "before burning more time.")
                store.close()
                return 1

    print(f"\nSweep complete. {done - failed}/{total} runs recorded.")
    store.close()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="harness", description=__doc__)
    parser.add_argument("--db", default=str(DEFAULT_DB),
                        help="working database (archives go to data/ as Parquet)")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="a single test run")
    p_run.add_argument("--config", required=True)
    p_run.add_argument("--tps", type=float, required=True)
    p_run.add_argument("--amount", type=float, default=200.0)
    p_run.add_argument("--window", type=float, default=WINDOW)
    p_run.add_argument("--repeat", type=int, default=0)
    p_run.add_argument("--phase", default="phase-1")
    p_run.add_argument("--arm", default="baseline", choices=["baseline", "adversarial"])
    p_run.add_argument("--workers", type=int, default=1,
                       help="processes to split the load across. Python uses one "
                            "processor core, which capped the harness at ~150/sec "
                            "in the Phase 2 pilot. Use 4+ above 100/sec.")
    p_run.set_defaults(func=cmd_run)

    p_cap = sub.add_parser("capacity", help="measure the harness's own ceiling")
    p_cap.add_argument("--window", type=float, default=60.0)
    p_cap.add_argument("--settle-delay", type=float, default=2.0,
                       help="simulated settlement delay, set near a real "
                            "chain's finality so confirmation-tracking load "
                            "is realistic")
    p_cap.set_defaults(func=cmd_capacity)

    p_sweep = sub.add_parser("sweep", help="the full pre-registered matrix")
    p_sweep.add_argument("--config", required=True)
    p_sweep.add_argument("--phase", required=True)
    p_sweep.add_argument("--arm", default="baseline", choices=["baseline", "adversarial"])
    p_sweep.add_argument("--resume", action="store_true",
                         help="skip configurations that already have a valid "
                              "completed run in this phase. Essential for a "
                              "12-hour sweep -- something will interrupt it.")
    p_sweep.add_argument("--workers", type=int, default=8,
                         help="processes to split load across. Defaults to 8: a "
                              "single process caps out near 150/sec, and the sweep "
                              "goes to 300.")
    p_sweep.set_defaults(func=cmd_sweep)

    args = parser.parse_args()
    return asyncio.run(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
