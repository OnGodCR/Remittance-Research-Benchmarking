#!/usr/bin/env bash

# A PROCESS CHECK THAT FINDS ITSELF
#
# `pgrep -f foo` and `pkill -f foo` search whole command lines, so the shell
# running the check has "foo" in its own -- the check matches itself. It
# reports RUNNING when nothing is, and `pkill` kills its own wrapper. This
# cost hours on 22 Aug 2026 and, in one case, killed a sweep on its first
# instruction. The brackets fix it: the regex [f]oo still matches the text
# "foo" in a real process, but this line's own text reads "[f]oo", which the
# regex does not match. Repo convention -- see RESUME_HERE.md S5 trap 8.
# ---------------------------------------------------------------------------
# ONE ENDPOINT VS FOUR — the proper, repeated measurement
#
# WHY THIS EXISTS
#
# On 19 Aug 2026 a single pair of runs showed that Polygon's measured ceiling
# was largely one node's ability to answer questions about payments, not the
# sidechain's ability to settle them. Sending settlement checks to four nodes
# instead of one took 274.9 payments/sec (invalid, the sender fell 228ms
# behind) to 290.5/sec (clean) -- on HALF the validator hardware the published
# 270.5/sec used.
#
# That was one run per condition. Enough to show the published framing is
# wrong; nowhere near enough to replace the numbers. This is the repeated
# version, so the correction can carry a confidence interval instead of an
# anecdote.
#
# WHAT IS MEASURED, AND WHY THE TWO BLOCKS DIFFER
#
#   200 and 300/sec, BOTH arms, 5 repeats.
#     300 is where the published number lives, so it is the direct comparison.
#     200 is a control: both arms should agree there, because the published
#     data shows 200/sec passes cleanly with zero failures and no strain. If
#     the arms DISAGREE at 200, something other than the endpoint count is
#     different between them and the whole comparison is suspect. A control
#     that can fail is the only kind worth running.
#
#   400, 500 and 600/sec, FOUR-ENDPOINT ARM ONLY, 5 repeats.
#     This measures the collapse shape, which is the claim actually withdrawn
#     from the paper ("Polygon degrades gracefully"). Running the
#     single-endpoint arm up here would waste an hour producing runs that
#     auto-invalidate for sender saturation -- we already know it cannot drive
#     these loads through one node.
#
# 35 runs, about 3.2 hours, roughly $5.
#
# NO VALIDATOR RESTARTS.
#
# Unlike the waiting-room experiment, the thing being varied is a flag on the
# sending program, not a setting on the nodes. So nothing restarts, nothing
# needs a settle period, and no run can be disturbed by a node coming back up
# mid-measurement. That removes the single largest source of noise from the
# earlier attempt.
#
# ARM ORDER ALTERNATES, for the same reason it did before: whichever arm runs
# second in a repeat meets a chain with more accumulated work behind it, and
# that showed up earlier as a ~17/sec penalty. Alternating cancels it.
#
# USAGE
#   nohup caffeinate -i ./scripts/run_endpoint_ab.sh > run.log 2>&1 &
#   ./scripts/run_endpoint_ab.sh --dry-run
#   ./scripts/run_endpoint_ab.sh --from-repeat 2
#
# Do NOT add setsid -- macOS has no setsid and the run dies instantly.
# ---------------------------------------------------------------------------
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ZONE=us-east4-c
PROJECT=remittances-benchmarking
GEN=bench-p2-generator

AMOUNT=200
WINDOW=300
WORKERS=8
DRY_RUN=0
FROM_REPEAT=0

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run)     DRY_RUN=1; shift ;;
    --from-repeat) FROM_REPEAT="$2"; shift 2 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

log()  { printf '\033[0;36m==>\033[0m %s\n' "$*"; }
die()  { printf '\033[0;31merror:\033[0m %s\n' "$*" >&2; exit 1; }
note() { printf '    %s\n' "$*"; }

cd "$REPO/terraform/phase2" || die "no terraform directory"
ENDPOINTS=$(tofu output -json validator_private_ips 2>/dev/null \
  | python3 -c "import sys,json;print(','.join(f'http://{i}:8545' for i in json.load(sys.stdin)))")
[ -n "$ENDPOINTS" ] || die "could not read the validator endpoints from terraform"
cd "$REPO"

# Each arm leads in 2 or 3 of the 5 repeats, as evenly as an odd count allows.
FIRST=("one" "four" "one" "four" "one")

if [ "$DRY_RUN" = "1" ]; then
  log "Plan (nothing will be run)"
  echo "  endpoints: $ENDPOINTS"
  for r in 0 1 2 3 4; do
    if [ "${FIRST[$r]}" = "one" ]; then a="one four"; else a="four one"; fi
    echo "  repeat $r: 200/sec [$a], 300/sec [$a], then 400/500/600 four-endpoint only"
  done
  echo
  echo "  35 runs total, about 3.2 hours."
  exit 0
fi

# ---------------------------------------------------------------------------
# WAIT FOR THE CHAIN'S QUEUE TO DRAIN BEFORE THE NEXT MEASURED RUN.
#
# WHY THIS HAD TO BE ADDED (19 Aug 2026, after it corrupted a run)
#
# A 300-second run at 600/sec offers 180,000 payments to a chain that can
# settle about 100/sec. It ends with a queue of well over a hundred thousand
# transactions still waiting. The next run then starts on a chain that is
# still chewing through the previous one.
#
# That is exactly what happened. Repeat 1's first run -- a 200/sec control
# that had been perfectly clean in repeat 0 (199.1/sec, zero failures) --
# came back at 171.0/sec with 9,452 timeouts, with 8,200 payments in flight
# where a few hundred would be normal. Nothing was wrong with the endpoints or
# the chain: it was still draining repeat 0's 600/sec run.
#
# Without this wait the experiment would have blamed the endpoint count for a
# queue left behind by the previous load step -- and because the arms
# alternate, whichever arm happened to follow a 600/sec run would look worse.
#
# The threshold is a level, not zero: background traffic runs continuously by
# design and keeps a few hundred transactions pending at all times. Zero would
# never arrive.
#
# NOTE FOR THE WRITE-UP: the published sweep ran its loads low-to-high with no
# drain between them, so its high-load runs inherited whatever the previous
# step left behind. That is consistent with the 562ms absolute scheduling lag
# measured in the published 300/sec runs against 63.8ms at 200/sec.
# ---------------------------------------------------------------------------
drain_wait() {
  local threshold=1000 waited=0 cap=900 pending
  local node
  node=$(cd "$REPO/terraform/phase2" && tofu output -json validator_private_ips 2>/dev/null \
         | python3 -c "import sys,json;print(json.load(sys.stdin)[0])")
  while [ "$waited" -lt "$cap" ]; do
    pending=$(gcloud compute ssh "$GEN" --zone "$ZONE" --project "$PROJECT" --no-tunnel-through-iap \
      --command "curl -s -m 10 -X POST -H 'Content-Type: application/json' \
        --data '{\"jsonrpc\":\"2.0\",\"method\":\"txpool_status\",\"params\":[],\"id\":1}' \
        http://${node}:8545 | python3 -c 'import sys,json;d=json.load(sys.stdin)[\"result\"];print(int(d[\"pending\"])+int(d[\"queued\"]))'" \
      < /dev/null -- -o StrictHostKeyChecking=no -o LogLevel=ERROR -o ConnectTimeout=30 2>/dev/null | tail -1)
    case "$pending" in (''|*[!0-9]*) pending=0 ;; esac
    if [ "$pending" -le "$threshold" ]; then
      [ "$waited" -gt 0 ] && note "queue drained to $pending after ${waited}s"
      return 0
    fi
    sleep 20; waited=$((waited + 20))
  done
  note "WARNING: queue still at $pending after ${cap}s -- continuing anyway, flag this run"
}

one_run() {  # arm(one|four), tps, repeat
  local arm="$1" tps="$2" r="$3" flag=""
  [ "$arm" = "four" ] && flag="--rpc-urls '$ENDPOINTS'"
  drain_wait
  log "repeat $r / $arm endpoint(s) / $tps per second"
  gcloud compute ssh "$GEN" --zone "$ZONE" --project "$PROJECT" --no-tunnel-through-iap \
    --command "cd /opt/benchmark && ./.venv/bin/python -m harness.cli run \
      --config config/phase1.json --tps $tps --window $WINDOW --amount $AMOUNT \
      --workers $WORKERS --repeat $r --phase phase-6-endpoints-$arm --arm baseline \
      $flag 2>&1 | grep -E 'achieved|lag growth' | tail -2" \
    < /dev/null -- -o StrictHostKeyChecking=no -o LogLevel=ERROR -o ConnectTimeout=60 2>&1 \
    | grep -v "^Warning:" | tail -2
}

# A LEFTOVER RUN FROM AN ABORTED ATTEMPT WILL DESTROY THIS ONE.
#
# Killing the orchestrator on the Mac does NOT stop the run already executing
# on the generator -- the ssh session dies, the remote python does not. Start a
# fresh run while that one is still going and both use the same 46 wallets, so
# their transaction counters collide. Observed 19 Aug 2026: a control run came
# back 0.0 payments/sec with all 23,959 failing on "nonce too low", "already
# known" and "replacement tx underpriced". Nothing was wrong with the chain or
# the harness; two senders were fighting over the same wallets.
log "Clearing any leftover run on the generator"
gcloud compute ssh "$GEN" --zone "$ZONE" --project "$PROJECT" --no-tunnel-through-iap \
  --command "pkill -f '[p]python -m harness.cli run' 2>/dev/null; sleep 2; \
    pgrep -f '[p]python -m harness.cli run' >/dev/null && echo '  WARNING: a run is still active' \
      || echo '  clear'" \
  < /dev/null -- -o StrictHostKeyChecking=no -o LogLevel=ERROR -o ConnectTimeout=60 2>&1 | tail -1

log "Starting background traffic for the whole experiment"
gcloud compute ssh "$GEN" --zone "$ZONE" --project "$PROJECT" --no-tunnel-through-iap \
  --command "cd /opt/benchmark && setsid nohup ./.venv/bin/python -m harness.noise \
      --config config/phase1.json --duration 13000 --keys keys/noise_senders.json \
      > /tmp/noise.log 2>&1 < /dev/null & \
    sleep 8 && (pgrep -f '[h]harness.noise' >/dev/null && echo 'background traffic RUNNING' \
      || echo 'BACKGROUND TRAFFIC FAILED')" \
  < /dev/null -- -o StrictHostKeyChecking=no -o LogLevel=ERROR -o ConnectTimeout=60 2>&1 | tail -2

for r in 0 1 2 3 4; do
  [ "$r" -lt "$FROM_REPEAT" ] && { note "repeat $r already done, skipping"; continue; }
  if [ "${FIRST[$r]}" = "one" ]; then arms="one four"; else arms="four one"; fi
  for tps in 200 300; do
    for arm in $arms; do one_run "$arm" "$tps" "$r"; done
  done
  # Collapse shape: four-endpoint only. One endpoint cannot drive these loads,
  # so running it would only manufacture invalid runs.
  for tps in 400 500 600; do one_run four "$tps" "$r"; done
done

log "All 35 runs finished."
note "Check FIRST how many auto-invalidated for sender lag, then compare"
note "phase-6-endpoints-one against phase-6-endpoints-four at 200 and 300."
note "The 200/sec rows are the control: if the arms disagree there, something"
note "other than endpoint count differs and the comparison is not safe."
