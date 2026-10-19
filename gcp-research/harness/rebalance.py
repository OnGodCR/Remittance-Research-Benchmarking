"""Recycle channel liquidity by paying in the opposite direction.

WHY THIS EXISTS
---------------
A Lightning channel holds a fixed amount of value, split between its two ends.
Paying across it moves the split. Sustained one-directional flow -- which is
exactly what a remittance corridor is -- pushes every channel to one side and
then nothing more can pass. The verification run made this concrete: 28
payments succeeded in the first 15 seconds, then 280 failed, and LND's own
reason codes said INSUFFICIENT_BALANCE.

That is not a fault in our deployment. Real routing nodes rebalance
continuously, and the fees they charge are what pay for it. A test network
without rebalancing is not a realistic Lightning network -- it is a Lightning
network that has been switched off partway through.

TWO MODES, FOR TWO DIFFERENT JOBS
---------------------------------
`reset` runs between measured runs on the well-capitalised arm. Each run drains
liquidity in one direction; this puts it back, so run N+1 starts from the same
state as run N. Without it, later runs in the sweep would be measuring a
progressively emptier network and the repeats would not be repeats.

`continuous` runs *during* the liquidity arm, where capacities are held at real
1ML values. There, a channel carries roughly three $200 payments before it is
spent, so steady state only exists if liquidity is being recycled the whole
time. This is the Lightning analogue of the background traffic used on Polygon
(realism technique #3): traffic the measured workload has to share the network
with.

WHAT IT MEASURES, NOT JUST WHAT IT FIXES
----------------------------------------
The reverse volume needed to sustain a given forward rate IS the capital
recycling cost -- the thing that makes Lightning's true cost per remittance
higher than its routing fee suggests. `--report` prints it.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import ssl
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import aiohttp  # noqa: E402

SATS_PER_BTC = 100_000_000


class Rebalancer:
    def __init__(self, config: dict) -> None:
        # Deliberately reversed: the measured workload pays sender -> recipient,
        # so recycling pays recipient -> sender.
        self._payers = config["recipients"]
        self._payees = config["senders"]
        self._rate = config["btc_usd_rate"]
        self._session: aiohttp.ClientSession | None = None
        self.sent = 0
        self.ok = 0
        self.done = 0        # attempts that have actually RESOLVED
        self.moved_sat = 0

    async def __aenter__(self):
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE       # private regtest, self-signed
        self._session = aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(limit=128, ssl=ctx),
            timeout=aiohttp.ClientTimeout(total=90),
        )
        return self

    async def __aexit__(self, *exc):
        if self._session:
            await self._session.close()

    @staticmethod
    def _hdr(ep):
        return {"Grpc-Metadata-macaroon": ep["macaroon"]}

    async def _inbound(self, ep) -> int:
        """How much this node can still RECEIVE: the balance on the far side."""
        try:
            async with self._session.get(f"{ep['url']}/v1/channels", headers=self._hdr(ep)) as r:
                d = await r.json()
                return sum(int(c.get("remote_balance", 0)) for c in d.get("channels", []))
        except Exception:
            return 0

    async def _outbound(self, ep) -> int:
        try:
            async with self._session.get(f"{ep['url']}/v1/channels", headers=self._hdr(ep)) as r:
                d = await r.json()
                return sum(int(c.get("local_balance", 0)) for c in d.get("channels", []))
        except Exception:
            return 0

    async def _pay(self, payer, payee, sats: int) -> bool:
        """One reverse payment. Failures are expected and not worth logging:
        a rebalance that cannot find a route simply means that direction is
        already full, which is the condition we are trying to reach."""
        try:
            async with self._session.post(
                f"{payee['url']}/v1/invoices", headers=self._hdr(payee),
                json={"value": str(sats), "expiry": "600"},
            ) as r:
                if r.status != 200:
                    return False
                inv = await r.json()

            body = {"payment_request": inv["payment_request"], "timeout_seconds": 30,
                    "fee_limit_msat": str(sats * 50), "no_inflight_updates": True}
            async with self._session.post(
                f"{payer['url']}/v2/router/send", headers=self._hdr(payer), json=body,
            ) as r:
                async for raw in r.content:
                    line = raw.strip()
                    if not line:
                        continue
                    upd = json.loads(line).get("result", {})
                    if upd.get("status") == "SUCCEEDED":
                        self.moved_sat += sats
                        return True
                    if upd.get("status") == "FAILED":
                        return False
        except Exception:
            return False
        return False

    async def reset_mission_control(self) -> int:
        """Clear every node's memory of recent routing failures.

        LND's mission control records which channels recently failed and
        penalises them in later pathfinding. That state is per-node, persists
        across runs, and decays slowly -- so run N+1 begins already biased by
        whatever failed in run N. It showed up as a failure rate climbing
        monotonically across repeats of an identical configuration (14%, 14%,
        23%, 28%, 28%) while liquidity stayed plentiful and every channel
        stayed active, and while static pathfinding still found routes to all
        seven recipients.

        Resetting between runs is the routing counterpart of resetting
        liquidity: the pre-registered protocol treats the five repeats as
        independent samples, and they are only independent if each starts from
        the same state. Recorded in METHODOLOGY_LOG.md.
        """
        done = 0
        for ep in self._payers + self._payees:
            try:
                async with self._session.post(f"{ep['url']}/v2/router/mc/reset",
                                              headers=self._hdr(ep), json={}) as r:
                    if r.status == 200:
                        done += 1
            except Exception:
                pass
        return done

    async def run(self, mode: str, amount_usd: float, duration: float,
                  target_tps: float) -> dict:
        sats = int(round(amount_usd / self._rate * SATS_PER_BTC))
        started = time.monotonic()
        i = 0
        inflight: set[asyncio.Task] = set()

        # Recipients are drained WORST-FIRST, not round robin.
        #
        # Round robin treats every recipient as equally in need, but they are
        # not: the thin ones fill up first. Measured directly, leaf-11 and
        # leaf-13 -- the two smallest -- had 0.03 and 0.01 BTC of inbound left
        # while the others held 17-27 BTC, so 2 of 7 payments failed no matter
        # how much total liquidity the network had. That is 28.6%, and it was
        # the failure rate exactly.
        #
        # Refreshed periodically rather than once, because the ordering shifts
        # as the gap proceeds.
        order: list = []
        last_ranked = 0.0

        while time.monotonic() - started < duration:
            now = time.monotonic()
            if not order or now - last_ranked > 20:
                inb = await asyncio.gather(*(self._inbound(e) for e in self._payers))
                order = [e for _, e in sorted(zip(inb, range(len(self._payers))),
                                              key=lambda z: z[0])]
                order = [self._payers[idx] for _, idx in
                         sorted(zip(inb, range(len(self._payers))), key=lambda z: z[0])]
                last_ranked = now

            payer = order[i % len(order)]
            payee = self._payees[i % len(self._payees)]
            i += 1

            async def one(p=payer, q=payee):
                self.sent += 1
                result = await self._pay(p, q, sats)
                self.done += 1
                if result:
                    self.ok += 1

            t = asyncio.create_task(one())
            inflight.add(t)
            t.add_done_callback(inflight.discard)

            if target_tps > 0:
                await asyncio.sleep(1.0 / target_tps)

            # Stop early only once enough attempts have RESOLVED and none
            # succeeded -- that means the direction is full and there is
            # nothing left to recycle.
            #
            # The first version compared `sent` against `ok`. Payments are
            # fired asynchronously, so `ok` is still zero while the first
            # batch is in flight: the check tripped after about a second,
            # every single time. The rebalancer moved 0.006 BTC per gap
            # instead of restoring the run's drain, sender liquidity fell from
            # 38.6 to 25.3 BTC over a dozen runs, and the failure rate climbed
            # to 71% -- which looked like Lightning degrading when it was our
            # recycling never running.
            if mode == "reset" and self.done >= 150 and self.ok == 0:
                break

        if inflight:
            await asyncio.gather(*inflight, return_exceptions=True)

        elapsed = time.monotonic() - started
        return {
            "mode": mode, "sent": self.sent, "succeeded": self.ok,
            "moved_btc": round(self.moved_sat / SATS_PER_BTC, 4),
            "elapsed_s": round(elapsed, 1),
            "achieved_tps": round(self.ok / elapsed, 2) if elapsed else 0.0,
        }


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default="config/phase3.json")
    ap.add_argument("--mode", choices=["reset", "continuous"], default="reset")
    ap.add_argument("--amount", type=float, default=200.0)
    ap.add_argument("--duration", type=float, default=120.0)
    ap.add_argument("--tps", type=float, default=20.0)
    ap.add_argument("--report", action="store_true",
                    help="print the recycling volume needed -- this is the capital cost evidence")
    args = ap.parse_args()

    config = json.loads(Path(args.config).read_text())
    async with Rebalancer(config) as rb:
        before = sum(await asyncio.gather(*(rb._outbound(e) for e in config["senders"])))
        result = await rb.run(args.mode, args.amount, args.duration, args.tps)
        # Mission control is deliberately NOT reset between runs.
        #
        # It was tried, on the theory that carrying learned routing state made
        # run N+1 depend on run N. Measured, it was far worse: failure at
        # $10/10-per-sec went from 3-17% to 71%. LND's mission control is not
        # contamination, it is how a node learns which channels actually work,
        # and a node that has forgotten routes blindly the way a freshly
        # started one does.
        #
        # Real senders accumulate this state too, so keeping it is also the
        # more realistic choice. The mild upward drift across repeats that
        # prompted the experiment is reported as a limitation instead.
        after = sum(await asyncio.gather(*(rb._outbound(e) for e in config["senders"])))

    result["sender_outbound_before_btc"] = round(before / SATS_PER_BTC, 4)
    result["sender_outbound_after_btc"] = round(after / SATS_PER_BTC, 4)
    result["restored_btc"] = round((after - before) / SATS_PER_BTC, 4)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
