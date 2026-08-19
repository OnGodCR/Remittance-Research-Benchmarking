#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# FIND THE ACTUAL KNEE, BETWEEN 300 AND 400
#
# WHY
#
# With settlement checks spread across four nodes, this cluster handles 300
# payments/sec with ZERO failures and collapses to 241/sec when offered 400.
# So the knee -- the point where it stops keeping up -- is somewhere in
# between, and every published statement about "the knee" put it at 300.
#
# 300 was simply the top of the pre-registered ramp. It was never measured as
# a knee; it was the last step before the ramp ran out. Locating the real one
# turns "higher than we said" into a number.
#
# WHY FOUR ENDPOINTS ONLY
#
# The single-endpoint arm cannot be measured up here -- at 300/sec it already
# falls half a second behind its own schedule and auto-invalidates. Running it
# would manufacture invalid runs and teach us nothing we do not already know.
#
# 4 loads x 5 repeats = 20 runs, about 1.9 hours, roughly $3.
#
# USAGE
#   nohup caffeinate -i ./scripts/run_knee_ramp.sh > knee.log 2>&1 &
#   ./scripts/run_knee_ramp.sh --dry-run
#   ./scripts/run_knee_ramp.sh --from-repeat 2
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
[ -n "$ENDPOINTS" ] || die "could not read validator endpoints"
cd "$REPO"

# Load order rotates per repeat so a slow-building effect cannot line up with
# load -- the same reason the earlier experiments rotated theirs.
ORDERS=("320 340 360 380" "380 320 340 360" "360 380 320 340" "340 360 380 320" "320 380 340 360")

if [ "$DRY_RUN" = "1" ]; then
  log "Plan (nothing will be run)"
  for r in 0 1 2 3 4; do echo "  repeat $r: ${ORDERS[$r]}"; done
  echo; echo "  20 runs, four endpoints, about 1.9 hours."
  exit 0
fi

log "Clearing any leftover run on the generator"
gcloud compute ssh "$GEN" --zone "$ZONE" --project "$PROJECT" --no-tunnel-through-iap \
  --command "pkill -f 'python -m harness.cli run' 2>/dev/null; sleep 2; echo cleared" \
  < /dev/null -- -o StrictHostKeyChecking=no -o LogLevel=ERROR -o ConnectTimeout=60 2>&1 | tail -1

log "Starting background traffic"
gcloud compute ssh "$GEN" --zone "$ZONE" --project "$PROJECT" --no-tunnel-through-iap \
  --command "pgrep -f harness.noise >/dev/null && echo 'background traffic already running' || \
    (cd /opt/benchmark && setsid nohup ./.venv/bin/python -m harness.noise \
      --config config/phase1.json --duration 8000 --keys keys/noise_senders.json \
      > /tmp/noise.log 2>&1 < /dev/null & sleep 8; \
     pgrep -f harness.noise >/dev/null && echo 'background traffic RUNNING' || echo 'NOISE FAILED')" \
  < /dev/null -- -o StrictHostKeyChecking=no -o LogLevel=ERROR -o ConnectTimeout=60 2>&1 | tail -1

for r in 0 1 2 3 4; do
  [ "$r" -lt "$FROM_REPEAT" ] && { note "repeat $r already done, skipping"; continue; }
  for tps in ${ORDERS[$r]}; do
    log "repeat $r / four endpoints / $tps per second"
    gcloud compute ssh "$GEN" --zone "$ZONE" --project "$PROJECT" --no-tunnel-through-iap \
      --command "cd /opt/benchmark && ./.venv/bin/python -m harness.cli run \
        --config config/phase1.json --tps $tps --window $WINDOW --amount $AMOUNT \
        --workers $WORKERS --repeat $r --phase phase-6-knee --arm baseline \
        --rpc-urls '$ENDPOINTS' 2>&1 | grep -E 'achieved|lag growth' | tail -2" \
      < /dev/null -- -o StrictHostKeyChecking=no -o LogLevel=ERROR -o ConnectTimeout=60 2>&1 \
      | grep -v "^Warning:" | tail -2
  done
done

log "All 20 knee runs finished."
note "The knee is the highest load where achieved still tracks offered and"
note "failures stay near zero. Compare against 300 (clean) and 400 (40% lost)."
