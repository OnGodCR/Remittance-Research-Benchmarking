// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title TestStablecoin
 * @notice A minimal dollar-pegged token used as the remittance payload.
 *
 * WHY THIS EXISTS
 * ---------------
 * Real remittances on Polygon move stablecoins (USDC/USDT), not the network's
 * native coin. That distinction is not cosmetic: a token transfer costs roughly
 * three times the computational work of a native transfer, because it has to
 * read and write balances held inside a contract rather than just move the
 * chain's built-in currency. Benchmarking native transfers would understate the
 * real cost of a real remittance by about 3x.
 *
 * It also makes the amounts trivial and exact. One token equals one dollar, so
 * the $10 / $50 / $200 / $500 test amounts need no exchange rate and introduce
 * no rounding. Only Lightning needs a real currency conversion.
 *
 * DELIBERATELY MINIMAL
 * --------------------
 * This is the ERC-20 behaviour that production stablecoins share, and nothing
 * else. No pausing, blacklisting, upgrade proxy, or fee-on-transfer logic.
 * Every one of those would add computational work that varies between real
 * issuers, which would make our measured cost a property of whichever issuer we
 * chose to imitate rather than of the architecture.
 *
 * `decimals` is 6, matching USDC and USDT rather than the 18 that most tokens
 * use. Keeping the same precision as the real thing keeps the arithmetic
 * identical.
 *
 * IMPORTANT FOR MEASUREMENT
 * -------------------------
 * The amount transferred does not change the work performed. `_balances[x] -= v`
 * costs the same whether v is 10 or 500 -- both are numbers in identically sized
 * slots. This is why the $10/$50/$200/$500 cost curves are predicted to be flat
 * on this architecture (ANALYSIS_PLAN.md S12).
 *
 * The one way amount could leak in: writing a balance slot costs more when it
 * changes from zero, and less when it returns to zero. A large payment is more
 * likely to empty a sender than a small one. We avoid this by funding senders
 * generously and reusing recipients, so no balance ever touches zero mid-run --
 * but note the reason is our test setup, not a property of the EVM.
 */
contract TestStablecoin {
    string public constant name = "Remittance Test Dollar";
    string public constant symbol = "RTD";
    uint8 public constant decimals = 6;

    uint256 public totalSupply;
    address public immutable minter;

    mapping(address => uint256) private _balances;
    mapping(address => mapping(address => uint256)) private _allowances;

    event Transfer(address indexed from, address indexed to, uint256 value);
    event Approval(address indexed owner, address indexed spender, uint256 value);

    error InsufficientBalance(address from, uint256 have, uint256 need);
    error InsufficientAllowance(address owner, address spender, uint256 have, uint256 need);
    error NotMinter();
    error ZeroAddress();

    constructor() {
        minter = msg.sender;
    }

    function balanceOf(address account) external view returns (uint256) {
        return _balances[account];
    }

    function allowance(address owner, address spender) external view returns (uint256) {
        return _allowances[owner][spender];
    }

    /**
     * @notice Fund the sender account pool before a run.
     * @dev Restricted to the deployer. Not part of the measured path -- funding
     *      happens during setup, never during a timed window.
     */
    function mint(address to, uint256 value) external {
        if (msg.sender != minter) revert NotMinter();
        if (to == address(0)) revert ZeroAddress();
        totalSupply += value;
        unchecked {
            // Cannot overflow: totalSupply above would have reverted first.
            _balances[to] += value;
        }
        emit Transfer(address(0), to, value);
    }

    /// @dev Convenience for funding the whole sender pool in one transaction.
    function mintBatch(address[] calldata recipients, uint256 value) external {
        if (msg.sender != minter) revert NotMinter();
        uint256 len = recipients.length;
        for (uint256 i = 0; i < len; ++i) {
            address to = recipients[i];
            if (to == address(0)) revert ZeroAddress();
            totalSupply += value;
            unchecked {
                _balances[to] += value;
            }
            emit Transfer(address(0), to, value);
        }
    }

    /// @notice The measured operation. This is what a "remittance" is in this study.
    function transfer(address to, uint256 value) external returns (bool) {
        _transfer(msg.sender, to, value);
        return true;
    }

    function approve(address spender, uint256 value) external returns (bool) {
        _allowances[msg.sender][spender] = value;
        emit Approval(msg.sender, spender, value);
        return true;
    }

    function transferFrom(address from, address to, uint256 value) external returns (bool) {
        uint256 allowed = _allowances[from][msg.sender];
        if (allowed != type(uint256).max) {
            if (allowed < value) revert InsufficientAllowance(from, msg.sender, allowed, value);
            unchecked {
                _allowances[from][msg.sender] = allowed - value;
            }
        }
        _transfer(from, to, value);
        return true;
    }

    function _transfer(address from, address to, uint256 value) private {
        if (to == address(0)) revert ZeroAddress();
        uint256 fromBalance = _balances[from];
        if (fromBalance < value) revert InsufficientBalance(from, fromBalance, value);
        unchecked {
            _balances[from] = fromBalance - value;
            // Cannot overflow: the sum of all balances equals totalSupply.
            _balances[to] += value;
        }
        emit Transfer(from, to, value);
    }
}
