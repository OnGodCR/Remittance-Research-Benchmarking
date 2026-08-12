#!/usr/bin/env python3
"""Keep phase 4 collecting data without a human in the loop.

Runs on the generator from cron every 5 minutes. Each invocation makes one
decision and exits; there is no long-lived process to die quietly.

WHAT IT DOES, AND WHY EACH PART EXISTS
--------------------------------------
1. GATES THE SWEEP ON A WHOLE VALIDATOR SET.
   The harness aborts a run whose health check fails, so a sweep started
   against 7 validators would churn through all 140 configurations failing
   instantly, filling the database with abandoned rows. Worse, it would look
   like progress. The sweep is only started when the liveness watch has
   reported a full set with >=2 validators per shard for several consecutive
   samples.

2. RE-ADMITS EXPELLED VALIDATORS AUTOMATICALLY.
   This is the failure that cost phase 4 a day. A reclaimed spot instance
   misses the blocks it was scheduled to produce, its epoch score falls under
   the 90% kickout threshold, and the protocol expels it. It does NOT rejoin on
   its own -- it must submit a fresh stake proposal, which takes effect two
   epochs (about four hours) later. Nobody noticed node0 had been expelled
   until it was checked by hand, and shard 3 sat on a single validator in the
   meantime. Here, any validator that is neither in the current set nor already
   proposing is re-staked immediately, so the four-hour clock starts at once
   rather than whenever someone looks.

3. RESTARTS A DEAD SWEEP.
   Tracked by PID file, never by `pgrep -f` -- that matched the checking
   command's own arguments and reported healthy progress for processes that did
   not exist (PHASE4_HANDOFF.md bug 4).

4. WRITES A STATUS FILE.
   `supervisor_status.json`, the single place to read what is happening. The
   database is the source of truth for progress: a run counts only when it has
   `ended_wall IS NOT NULL AND invalidated = 0`.

WHAT IT DELIBERATELY DOES NOT DO
--------------------------------
It cannot shut the cluster down. The generator has no service account attached,
so it cannot call the Compute API at all. Cluster shutdown is done from the
operator side, with a per-machine deadline file as the backstop if that never
happens.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sqlite3
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

BASE = Path("/opt/benchmark")
WORKING = BASE / "data" / "working"
DB = WORKING / "runs.sqlite"
LIVENESS = WORKING / "validator_liveness.jsonl"
STATUS = WORKING / "supervisor_status.json"
PIDFILE = WORKING / "sweep.pid"
NOISE_PIDFILE = WORKING / "noise.pid"
NOISE_KEYS = BASE / "keys" / "near_noise_senders.json"
LOG = Path("/var/log/near-supervisor.log")
VALIDATOR_KEYS = BASE / "keys" / "near_validator_keys.json"

RPC = "http://10.40.0.10:3030"

#: 4 amounts x 7 load steps x 5 repeats.
MATRIX_TOTAL = 140
#: Consecutive healthy liveness samples required before starting the sweep.
#: At a 10s interval this is one minute of proven health -- long enough that a
#: single transient RPC blip does not start a sweep, short enough not to waste
#: the window after an epoch boundary restores the set.
HEALTHY_SAMPLES_REQUIRED = 6
#: A liveness sample older than this means the watcher is not running, and
#: health is unknown rather than good.
LIVENESS_MAX_AGE = 60.0


def log(msg: str) -> None:
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} {msg}"
    print(line, flush=True)
    try:
        with LOG.open("a") as fh:
            fh.write(line + "\n")
    except OSError:
        pass


def rpc(method: str, params, timeout: float = 10.0):
    req = urllib.request.Request(
        RPC,
        data=json.dumps({"jsonrpc": "2.0", "id": 1,
                         "method": method, "params": params}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = json.load(resp)
    if body.get("error"):
        raise RuntimeError(str(body["error"])[:200])
    return body["result"]


# -- liveness -----------------------------------------------------------------

#: Bytes of tail to read when looking for recent samples. Generous on purpose.
#:
#: This was originally sized as `200 * (n + 5)` -- an estimate of the line
#: length. Adding per-validator production counters to each sample pushed a
#: line past 450 bytes, so the seek covered only FIVE samples where six are
#: required to declare the chain healthy. The supervisor would then have
#: reported "only 5 liveness samples available" forever and never started the
#: sweep, no matter how healthy the chain became.
#:
#: A fixed generous window has no such failure mode: 256 KB is roughly 500
#: samples, about 85 minutes at a 10s interval, and reading it costs nothing
#: next to the five-minute cron period. Do not replace this with an estimate of
#: the line length again -- the record format is expected to grow.
_TAIL_BYTES = 256 * 1024


def recent_liveness(n: int) -> list[dict]:
    """Last n samples, newest last.

    Reads a fixed tail rather than the whole file: over a 13-hour sweep this log
    is ~4,700 lines and growing.
    """
    if not LIVENESS.exists():
        return []
    with LIVENESS.open("rb") as fh:
        size = os.path.getsize(LIVENESS)
        fh.seek(-min(_TAIL_BYTES, size), os.SEEK_END)
        lines = fh.read().decode("utf-8", "replace").splitlines()
    out = []
    # The first line may be truncated by the seek; json.loads rejects it and it
    # is skipped, which is why the slice takes more lines than needed.
    for line in lines[-(n + 2):]:
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out[-n:]


def chain_is_healthy() -> tuple[bool, str]:
    samples = recent_liveness(HEALTHY_SAMPLES_REQUIRED)
    if len(samples) < HEALTHY_SAMPLES_REQUIRED:
        return False, f"only {len(samples)} liveness samples available"
    age = time.time() - samples[-1]["t"]
    if age > LIVENESS_MAX_AGE:
        return False, f"liveness watch is stale ({age:.0f}s old); is it running?"
    bad = [s for s in samples if not s.get("ok")]
    if bad:
        last = samples[-1]
        return False, (f"{len(bad)}/{len(samples)} recent samples degraded; "
                       f"validators={last.get('validators')} "
                       f"shards={last.get('shards')}")
    return True, "validator set whole for the last minute"


# -- validator re-admission ---------------------------------------------------

#: The protocol expels a validator whose epoch score falls below this.
#: Read from the chain when available; this is the fallback.
KICKOUT_THRESHOLD_PCT = 90.0


def restake_missing() -> list[str]:
    """Re-stake any validator that is absent, or that is certain to be expelled.

    Returns the accounts a proposal was submitted for. Silent no-op when the
    key file is absent, so the supervisor still works without it.

    WHY "CERTAIN TO BE EXPELLED" IS INCLUDED, NOT JUST "ABSENT"
    Expulsion is decided at the end of the epoch in which a validator
    underperformed, but only takes effect two epochs later, and the validator
    stays in the set in the meantime. Waiting until it disappears therefore
    wastes two full epochs -- four hours -- before the four-hour re-admission
    clock even starts. node1 was reclaimed at 00:04 on 12 Aug, recovered to
    100% block production within minutes, and was still doomed on a 63% epoch
    score it could not arithmetically recover. Proposing while it is still
    nominally a member is what gets it back at the earliest possible epoch.

    A proposal for a validator already at the right stake is a no-op on chain,
    so acting early costs nothing if the prediction turns out wrong.
    """
    if not VALIDATOR_KEYS.exists():
        return []
    try:
        keys = json.loads(VALIDATOR_KEYS.read_text())
        vals = rpc("validators", [None])
    except Exception as exc:                       # noqa: BLE001
        log(f"restake: cannot read state ({type(exc).__name__}: {exc})")
        return []

    proposing = {p["account_id"] for p in vals.get("current_proposals", [])}
    queued = {v["account_id"] for v in vals.get("next_validators", [])}

    # Score logging only. The decision below is NOT based on this arithmetic --
    # see why immediately after.
    for v in vals["current_validators"]:
        bp = 100.0 * v["num_produced_blocks"] / max(1, v["num_expected_blocks"])
        cp = 100.0 * v["num_produced_chunks"] / max(1, v["num_expected_chunks"])
        if bp < KICKOUT_THRESHOLD_PCT or cp < KICKOUT_THRESHOLD_PCT:
            log(f"restake: {v['account_id']} scoring {bp:.1f}% blocks / "
                f"{cp:.1f}% chunks -- below the {KICKOUT_THRESHOLD_PCT:g}% "
                f"kickout threshold, will be expelled")

    # THE RULE: propose for anyone who is not in the set for the NEXT epoch and
    # is not already proposing.
    #
    # `next_validators` is the protocol's own decision about who will be
    # validating next, so this needs no guesswork about kickout arithmetic or
    # epoch offsets. It also covers a case that "is it absent now?" misses
    # entirely: a validator whose expulsion has been DECIDED but not yet
    # APPLIED is still listed as current, so waiting for it to disappear
    # forfeits a whole epoch. node1 was in exactly that state -- nominally a
    # member, already condemned on a 63% score.
    #
    # A proposal for a validator that is in fact fine is a no-op on chain: it
    # re-declares the same stake. The rule is therefore safe to apply eagerly,
    # and eagerly is the point -- every epoch of delay is two more hours.
    missing = [k for k in keys
               if k["account_id"] not in queued
               and k["account_id"] not in proposing]
    if not missing:
        return []

    # Match the stake of whoever is currently in the set, so every validator
    # carries equal weight and is selected to produce blocks equally often.
    stake = vals["current_validators"][0]["stake"] if vals["current_validators"] else None
    if stake is None:
        log("restake: no current validators to copy a stake from; skipping")
        return []

    done = []
    for k in missing:
        try:
            _submit_stake(k["account_id"], k["public_key"], k["secret_key"], stake)
            log(f"restake: submitted proposal for {k['account_id']} at stake {stake}")
            done.append(k["account_id"])
        except Exception as exc:                   # noqa: BLE001
            log(f"restake: FAILED for {k['account_id']}: {type(exc).__name__}: {exc}")
    return done


def _submit_stake(account_id: str, public_key: str, secret_key: str,
                  stake: str) -> None:
    """Submit one StakeAction.

    py-near's `Account.stake` cannot be used: it calls
    `create_staking_action(public_key, amount)` while that builder's signature
    is `(amount, pk)`, so it tries to base58-decode the stake amount as a key
    and dies on "Invalid character '0'". The action is built directly here with
    the arguments the right way round.
    """
    import asyncio

    async def go() -> None:
        from py_near.account import Account
        from py_near import transactions as tx
        acct = Account(account_id, secret_key, rpc_addr=RPC)
        await acct.startup()
        await acct.sign_and_submit_tx(
            account_id, [tx.create_staking_action(int(stake), public_key)])

    asyncio.run(go())


# -- sweep process ------------------------------------------------------------

def sweep_pid() -> int | None:
    """The sweep's PID if it is genuinely alive, else None.

    PID file rather than a process-name search. `pgrep -f "harness.cli run"`
    matches the arguments of the command doing the checking, so it reported
    RUNNING for processes that did not exist and healthy progress was reported
    to Angad on that basis.
    """
    if not PIDFILE.exists():
        return None
    try:
        pid = int(PIDFILE.read_text().strip())
    except (ValueError, OSError):
        return None
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, PermissionError):
        return None
    return pid


def noise_pid() -> int | None:
    """PID of the background-traffic generator if it is alive, else None."""
    if not NOISE_PIDFILE.exists():
        return None
    try:
        pid = int(NOISE_PIDFILE.read_text().strip())
    except (ValueError, OSError):
        return None
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, PermissionError):
        return None
    return pid


def start_noise() -> int | None:
    """Start competing background traffic (realism technique #3).

    WHY THE SWEEP MUST NOT RUN WITHOUT THIS
    Every one of Polygon's 140 runs carried ~88 transactions/sec of competing
    load, and the Polygon sweep script refuses to start without it: "the sweep
    would run against an idle chain, which is not the full realism stack." NEAR
    measured on an empty chain against Polygon measured on a busy one would win
    the comparison partly on how quiet its blocks were, which is not a fact
    about sharding.

    Duration is set well past the length of the sweep; the supervisor restarts
    it if it exits early.
    """
    if not NOISE_KEYS.exists():
        log(f"noise: {NOISE_KEYS} missing -- cannot start background traffic")
        return None
    logfile = BASE / "noise.log"
    proc = subprocess.Popen(
        [str(BASE / ".venv" / "bin" / "python"), "-u", "-m", "harness.noise_near",
         "--config", str(BASE / "config" / "phase4.json"),
         "--keys", str(NOISE_KEYS),
         "--duration", "86400"],
        cwd=str(BASE),
        stdout=logfile.open("a"), stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL, start_new_session=True,
    )
    NOISE_PIDFILE.write_text(str(proc.pid))
    return proc.pid


def stop_noise() -> None:
    pid = noise_pid()
    if pid is None:
        return
    try:
        os.killpg(os.getpgid(pid), signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        pass
    NOISE_PIDFILE.unlink(missing_ok=True)


def start_sweep(phase: str) -> int:
    """Launch the resumable sweep detached, and record its PID.

    setsid so it survives this cron invocation exiting, and `python -u` inside
    the sweep script for the same reason its logs previously read as empty:
    Python buffers stdout when it is not a terminal.
    """
    logfile = BASE / "sweep.log"
    proc = subprocess.Popen(
        ["setsid", "bash", str(BASE / "scripts" / "run_near_sweep_inner.sh"), phase],
        cwd=str(BASE),
        stdout=logfile.open("a"),
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
    )
    PIDFILE.write_text(str(proc.pid))
    return proc.pid


def stop_sweep() -> None:
    pid = sweep_pid()
    if pid is None:
        return
    try:
        os.killpg(os.getpgid(pid), signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        pass
    PIDFILE.unlink(missing_ok=True)


# -- progress -----------------------------------------------------------------

def progress(phase: str) -> dict:
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try:
        done = conn.execute(
            "SELECT COUNT(*) FROM runs WHERE phase=? AND architecture='near' "
            "AND ended_wall IS NOT NULL AND invalidated=0", (phase,)).fetchone()[0]
        invalid = conn.execute(
            "SELECT COUNT(*) FROM runs WHERE phase=? AND architecture='near' "
            "AND invalidated=1", (phase,)).fetchone()[0]
        started = conn.execute(
            "SELECT COUNT(*) FROM runs WHERE phase=? AND architecture='near'",
            (phase,)).fetchone()[0]
        last = conn.execute(
            "SELECT tx_size_usd, target_tps, repeat_index, t0_wall, ended_wall "
            "FROM runs WHERE phase=? AND architecture='near' "
            "ORDER BY t0_wall DESC LIMIT 1", (phase,)).fetchone()
    finally:
        conn.close()
    return {
        "complete": done,
        "total": MATRIX_TOTAL,
        "invalidated": invalid,
        "started": started,
        "last_run": (
            {"amount": last[0], "tps": last[1], "repeat": last[2],
             "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(last[3])),
             "finished": last[4] is not None}
            if last else None),
    }


# -- main ---------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--phase", default="phase-4-full-stack")
    ap.add_argument("--no-start", action="store_true",
                    help="observe and re-stake, but never launch the sweep")
    args = ap.parse_args()

    WORKING.mkdir(parents=True, exist_ok=True)
    prog = progress(args.phase)
    healthy, why = chain_is_healthy()
    pid = sweep_pid()

    restaked = restake_missing()

    npid = noise_pid()

    if prog["complete"] >= MATRIX_TOTAL:
        state, action = "complete", "matrix finished; sweep stopped"
        if pid:
            stop_sweep()
        if npid:
            stop_noise()
            npid = None
    elif not healthy:
        # Stop rather than let it churn: each aborted run still creates a row,
        # and 140 instant failures would look like a sweep that ran.
        state, action = "waiting_for_validators", why
        if pid:
            stop_sweep()
            action = f"{why}; stopped the sweep to avoid churning failed runs"
        # Noise is stopped too: it is only meaningful alongside measurement, and
        # leaving it running would burn the noise accounts' balances for nothing.
        if npid:
            stop_noise()
            npid = None
    elif pid:
        if npid is None:
            npid = start_noise()
            state, action = "running", (
                f"sweep alive (pid {pid}); background traffic had stopped and "
                f"was restarted (pid {npid})")
            log("noise: RESTARTED mid-sweep -- runs overlapping the gap saw "
                "less competing load than intended")
        else:
            state, action = "running", f"sweep alive (pid {pid}), noise (pid {npid})"
    elif args.no_start:
        state, action = "ready", "chain healthy; --no-start set, not launching"
    else:
        # Noise first, then the sweep: a run that begins before background
        # traffic is flowing is measured on a quieter chain than the rest.
        npid = start_noise()
        if npid is None:
            state, action = "blocked", (
                "chain healthy but background traffic could not start; NOT "
                "measuring, because an idle chain is not the full realism stack "
                "and the result would not be comparable with Polygon")
            log(f"[{state}] {action}")
        else:
            pid = start_sweep(args.phase)
            state, action = "running", (
                f"chain healthy; started background traffic (pid {npid}) "
                f"then sweep (pid {pid})")

    status = {
        "checked_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "state": state,
        "action": action,
        "phase": args.phase,
        "progress": prog,
        "chain_healthy": healthy,
        "chain_detail": why,
        "sweep_pid": pid,
        "noise_pid": npid,
        "restaked_this_check": restaked,
    }
    STATUS.write_text(json.dumps(status, indent=2))
    log(f"[{state}] {action} | {prog['complete']}/{MATRIX_TOTAL} complete"
        + (f" | restaked {restaked}" if restaked else ""))
    print(json.dumps(status, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
