# NEAR — what "settled" means, and why it matters

**Written:** 11 August 2026
**Use this when:** writing the Methodology section, and any time NEAR's latency is compared with Polygon's.

---

## 1. The definition

**A NEAR transaction counts as settled when its outcome reaches `FINAL`.**

Not `EXECUTED_OPTIMISTIC`. This is required by `claude.md` §7 and it is not a formality.

---

## 2. What the alternative would have done

NEAR exposes several finality levels. The two that matter here:

| Level | Meaning |
|---|---|
| `EXECUTED_OPTIMISTIC` | The receiving shard has executed the transaction. The result is **not yet final network-wide** and can still change. |
| `FINAL` | The result is final across the whole network. |

`EXECUTED_OPTIMISTIC` returns **sooner** — sometimes much sooner, because it does not wait for the cross-shard result to be folded into a final block.

Accepting it would have:

- **understated NEAR's settlement latency**, by an amount that grows with cross-shard traffic
- **flattered NEAR against Polygon**, whose IBFT finality is genuine at one block with no probabilistic reorg window to wait out
- broken the comparison the entire study exists to make, because the two architectures would have been measured against different standards of "done"

A remittance is not settled when one shard thinks it happened. It is settled when the network agrees.

---

## 3. How it is enforced in code

`py-near`'s `get_tx` uses the legacy positional RPC form:

```python
await self.json_rpc("tx", [tx_hash, tx_recipient_id])
```

That form **cannot request a finality level** — it returns whatever the node's default is. So the adapter does not use it. It calls the RPC directly with an explicit `wait_until`:

```python
result = await provider.json_rpc("tx", {
    "tx_hash": tx_ref,
    "sender_account_id": signer,
    "wait_until": "FINAL",
})
```

See `harness/adapters/near.py::await_confirmation`.

**This is worth a sentence in the paper.** It is exactly the kind of detail that silently produces a wrong number: the library's convenience method would have worked, returned plausible data, and quietly measured the wrong thing.

---

## 4. Comparison across the three architectures

Each architecture has its own honest definition of settled, and the Methodology should state all three together:

| Architecture | Settled when | Why this one |
|---|---|---|
| **Polygon** | Included in a committed block, **N = 1** | IBFT gives deterministic instant finality. There is no reorg window, so waiting extra blocks would add delay that does not exist and mask a genuine Polygon advantage. |
| **Lightning** | Preimage returned to the sender | The payment is irreversibly complete at that moment. |
| **NEAR** | Outcome at **`FINAL`** | Optimistic execution is shard-local and not yet network-final. |

These are different mechanisms, not different levels of strictness. Each is the point at which that architecture's payment is genuinely irreversible — which is what makes them comparable.

---

## 5. The timeout

**60 seconds**, uniform across all three architectures (`claude.md` §7). Roughly 10× the expected p99, and past that a remittance has functionally failed regardless of what the network eventually decides.

A NEAR transaction that has not reached `FINAL` within 60s is recorded as `status = timeout`, not `failed` — the same distinction used on Polygon, where it separates *accepted-then-lost* payments from *rejected at submission*. That distinction turned out to matter enormously on Polygon: under clean conditions it never lost an accepted payment, and under node failure it did.
