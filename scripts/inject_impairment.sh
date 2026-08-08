#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Realism technique #2: injected latency, jitter and packet loss.
#
# WHY THIS IS NEEDED ON TOP OF REAL GEOGRAPHY
#
# Phase 2 step 1 already put validators on four continents, so consensus pays
# genuine intercontinental distance. But it pays that distance across GOOGLE'S
# PRIVATE BACKBONE -- dedicated fibre, near-zero loss, stable timing. Real
# validators are not all on one company's network. They sit behind consumer
# and commercial ISPs, where packets are lost and delay varies minute to
# minute.
#
# That difference matters more than it sounds. Consensus protocols tolerate
# latency well -- everyone simply waits longer. They tolerate LOSS badly,
# because a dropped vote is indistinguishable from a silent validator until a
# timeout expires. A network with 250ms delay and no loss behaves very
# differently from one with 250ms delay and 0.5% loss, and only the second
# resembles the real world.
#
# WHERE THE NUMBERS COME FROM
#
# Values are set per-corridor from published measurements rather than
# invented. Sources are recorded beside each value so the paper can cite them
# and a reviewer can check them. We add only the DIFFERENCE between what the
# cloud backbone already provides and what the public internet delivers --
# adding the full figure on top of existing latency would double-count.
#
# USAGE
#   ./scripts/inject_impairment.sh --phase phase2            # apply
#   ./scripts/inject_impairment.sh --phase phase2 --clear    # remove
#   ./scripts/inject_impairment.sh --phase phase2 --show     # inspect
#
# Applies to the interface as a whole, so it affects consensus traffic between
# validators. The generator's own path is left untouched deliberately: the
# measurement instrument should not be impaired, only the system under test.
# ---------------------------------------------------------------------------
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PHASE="phase2"
ACTION="apply"

while [ $# -gt 0 ]; do
  case "$1" in
    --phase) PHASE="$2"; shift 2 ;;
    --clear) ACTION="clear"; shift ;;
    --show)  ACTION="show"; shift ;;
    *) echo "unknown argument: $1" >&2; exit 1 ;;
  esac
done

TF_DIR="$REPO/terraform/$PHASE"
NODE_PREFIX="bench-p2"
[ "$PHASE" = "phase1" ] && NODE_PREFIX="bench-p1"

log() { printf '\033[0;36m==>\033[0m %s\n' "$*"; }
die() { printf '\033[0;31merror:\033[0m %s\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# Impairment profile, per validator index.
#
# Delay is ADDITIONAL one-way delay on top of the cloud backbone. Jitter is
# the variation around it. Loss is the percentage of packets dropped.
#
# Sources (pulled 8 Aug 2026, to be cited in the Methodology):
#   - ITU-T Y.1541 network performance classes: international paths target
#     <=0.1% loss for real-time classes; general internet paths commonly
#     exceed this.
#   - Published broadband measurement programmes (Ofcom UK, FCC US) report
#     typical fixed-line loss of 0.1-0.5% and jitter of 2-10ms domestically,
#     rising on long-haul international routes.
#   - Long-haul intercontinental routes over the public internet typically add
#     20-60ms over the equivalent private-backbone path, chiefly from less
#     direct routing and additional hops.
#
# Values are deliberately CONSERVATIVE. Overstating impairment would make the
# results pessimistic in a way that is just as misleading as understating it.
# ---------------------------------------------------------------------------
declare -a DELAY_MS=(20 45 40 25)
declare -a JITTER_MS=(4 12 10 6)
declare -a LOSS_PCT=("0.1" "0.4" "0.3" "0.15")
declare -a CORRIDOR=("US (Virginia)" "India (Mumbai)" "SE Asia (Singapore)" "UK (London)")

cd "$TF_DIR"
[ -f terraform.tfstate ] || die "No cluster found. Run 'tofu apply' in $TF_DIR first."

PROJECT=$(grep -oE '"project": *"[^"]+"' terraform.tfstate | head -1 | cut -d'"' -f4)
[ -n "$PROJECT" ] || PROJECT=$(gcloud config get-value project 2>/dev/null)

ZONES=()
while IFS= read -r z; do [ -n "$z" ] && ZONES+=("$z"); done \
  < <(tofu output -json validator_zones 2>/dev/null | jq -r '.[]' 2>/dev/null || true)
if [ ${#ZONES[@]} -eq 0 ]; then
  single=$(tofu output -raw zone)
  n=$(tofu output -json validator_private_ips | jq 'length')
  for ((i = 0; i < n; i++)); do ZONES+=("$single"); done
fi
COUNT=${#ZONES[@]}

ssh_node() {
  gcloud compute ssh "${NODE_PREFIX}-validator-$1" --zone "${ZONES[$1]}" \
    --project "$PROJECT" --no-tunnel-through-iap \
    --command "$2" -- -o StrictHostKeyChecking=no -o LogLevel=ERROR 2>/dev/null
}

case "$ACTION" in

  apply)
    log "Applying network impairment to $COUNT validators"
    echo "  (additional delay on top of real cloud-backbone latency)"
    echo
    for ((i = 0; i < COUNT; i++)); do
      d=${DELAY_MS[$i]}; j=${JITTER_MS[$i]}; l=${LOSS_PCT[$i]}
      # `netem` is the kernel's own network emulator. Applied to the primary
      # interface so it affects all consensus traffic leaving this validator.
      # `distribution normal` makes jitter behave like real networks rather
      # than a uniform random spread.
      ssh_node "$i" "sudo tc qdisc del dev ens4 root 2>/dev/null; \
        sudo tc qdisc add dev ens4 root netem \
          delay ${d}ms ${j}ms distribution normal loss ${l}%" \
        || die "Could not apply impairment to validator-$i."
      printf '  validator-%d  %-22s +%sms ±%sms, %s%% loss\n' \
        "$i" "${CORRIDOR[$i]}" "$d" "$j" "$l"
    done
    echo
    log "Impairment active. Record these values with the results -- they are"
    echo "    an independent variable, not an implementation detail."
    ;;

  clear)
    log "Removing impairment from $COUNT validators"
    for ((i = 0; i < COUNT; i++)); do
      ssh_node "$i" "sudo tc qdisc del dev ens4 root 2>/dev/null || true"
      printf '  validator-%d cleared\n' "$i"
    done
    log "Network restored to baseline."
    ;;

  show)
    log "Current impairment on each validator"
    for ((i = 0; i < COUNT; i++)); do
      out=$(ssh_node "$i" "tc qdisc show dev ens4 | head -2")
      printf '  validator-%d  %s\n' "$i" "$(echo "$out" | tr '\n' ' ')"
    done
    ;;
esac
