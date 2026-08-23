#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Realism technique #2 for the NEAR cluster: injected latency, jitter and loss.
#
# WHY A SEPARATE SCRIPT FROM inject_impairment.sh
#
# That one hardcodes `bench-p1`/`bench-p2` node names and reads addresses from
# `terraform/$PHASE` outputs. Phase 4's nodes are `near-validator-N` with two
# validators per region rather than one. Rather than thread a third naming
# scheme through a script that already carries two, this states the phase-4
# topology explicitly. The IMPAIRMENT VALUES ARE IDENTICAL, which is the point:
# both architectures must pay the same network penalty or the comparison
# measures our test setup instead of the two designs.
#
# WHY IT IS NEEDED AT ALL
#
# Phase 4 already spans four continents, so consensus pays genuine distance --
# but across Google's private backbone: dedicated fibre, near-zero loss, stable
# timing. Real validators sit behind ordinary ISPs. Consensus protocols tolerate
# latency well (everyone waits longer) and tolerate LOSS badly, because a
# dropped vote is indistinguishable from a silent validator until a timeout
# fires. 250ms with no loss behaves very differently from 250ms with 0.4% loss,
# and only the second resembles production.
#
# WITHOUT THIS, NEAR WOULD BE MEASURED ON A CLEAN NETWORK AND POLYGON ON A DIRTY
# ONE. Verified 12 Aug 2026: `tc qdisc show` on the NEAR validators reported no
# netem at all, while every Polygon run recorded impairment in its config. NEAR
# would have won the comparison partly on network conditions.
#
# THE ONE THING THAT MUST NOT BE GOT WRONG
#
# Impair the system under test, never the instrument measuring it. Phase 2's
# first attempt attached netem to the interface root, which delayed everything
# leaving the machine including replies to the load generator: scheduling lag
# went from 10ms to 553ms at 100/sec and 48 SECONDS at 300/sec, and both runs
# auto-invalidated. The chain was fine; we were degrading our own stopwatch.
#
# So: a `prio` qdisc with three bands, netem on band 3, and filters that steer
# ONLY packets addressed to other validators into it. Generator traffic and RPC
# replies take an unimpaired band.
#
# USAGE
#   ./scripts/inject_impairment_near.sh            # apply
#   ./scripts/inject_impairment_near.sh --show     # inspect
#   ./scripts/inject_impairment_near.sh --clear    # remove
# ---------------------------------------------------------------------------
set -uo pipefail

# Read from tfvars like deploy_near.sh, not hardcoded: this said
# "remittances-benchmarking" while the cluster moved to the project that
# actually holds the processor allowance, and would have silently impaired
# nothing -- leaving the runs comparing an unimpaired NEAR against an
# impaired Polygon. Run from the repository root.
PROJECT="$(grep -E '^project_id' terraform/phase4/terraform.tfvars | cut -d'"' -f2)"
ACTION="apply"
case "${1:-}" in
  --clear) ACTION="clear" ;;
  --show)  ACTION="show" ;;
  "")      ACTION="apply" ;;
  *) echo "usage: $0 [--show|--clear]" >&2; exit 2 ;;
esac

# Phase 4 topology, stated explicitly. Index = validator number.
NAMES=(near-validator-0 near-validator-1 near-validator-2 near-validator-3
       near-validator-4 near-validator-5 near-validator-6 near-validator-7)
ZONES=(us-east4-c us-east4-c asia-south1-a asia-south1-a
       asia-southeast1-a asia-southeast1-a europe-west2-b europe-west2-b)
# The addresses are DERIVED, not hardcoded. The 21 Aug rebuild assigned new
# internal addresses to seven of the eight machines, and the hardcoded list
# from the 11 Aug cluster matched only validator-0 -- so seven-eighths of the
# delay and packet-loss rules pointed at addresses nobody holds, while the
# script printed APPLIED for every machine. Found by the 23 Aug ops audit,
# verified against the infrastructure state. The 21 Aug fix to this same
# script corrected the project name and missed the addresses; this closes the
# whole class by reading the state instead of copying from it.
IPS=($(cd "$(dirname "${BASH_SOURCE[0]}")/../terraform/phase4" && \
  tofu output -json validators | python3 -c "
import sys, json
print(' '.join(v['private_ip'] for v in json.load(sys.stdin)))"))
if [ "${#IPS[@]}" -ne "${#NAMES[@]}" ]; then
  echo "error: expected ${#NAMES[@]} validator addresses from the infrastructure state, got ${#IPS[@]}" >&2
  exit 1
fi

# IDENTICAL to phase 2's profile (METHODOLOGY_LOG.md §4 technique #2), applied
# per REGION, so each corridor pays what it paid for Polygon. Two validators per
# region here against Polygon's one, so each value is used twice.
#
# Sources, pulled 8 Aug 2026 and unchanged:
#   - ITU-T Y.1541: international paths target <=0.1% loss for real-time
#     classes; general internet paths commonly exceed it.
#   - Ofcom UK and FCC US broadband measurement programmes: typical fixed-line
#     loss 0.1-0.5%, jitter 2-10ms domestically, higher on long-haul routes.
#   - Long-haul intercontinental public-internet routes typically add 20-60ms
#     over the equivalent private-backbone path.
#
# Only the DIFFERENCE between backbone and public internet is added; adding the
# full figure on top of existing latency would double-count. Values are
# deliberately conservative -- overstating impairment misleads exactly as much
# as understating it.
DELAY_MS=(20 20 45 45 40 40 25 25)
JITTER_MS=(4 4 12 12 10 10 6 6)
LOSS_PCT=("0.1" "0.1" "0.4" "0.4" "0.3" "0.3" "0.15" "0.15")
CORRIDOR=("US (Virginia)" "US (Virginia)" "India (Mumbai)" "India (Mumbai)"
          "SE Asia (Singapore)" "SE Asia (Singapore)" "UK (London)" "UK (London)")

# A JUDGEMENT CALL, STATED RATHER THAN BURIED: a validator's profile is applied
# to ALL of its peer traffic, including the peer sharing its region. The value
# models the quality of THAT VALIDATOR'S OWN connection to the public internet,
# which it pays regardless of where the packet is going. The alternative --
# exempting same-region pairs -- would give the four co-located pairs a private
# low-latency link that no comparable pair had on Polygon, where every validator
# was alone in its region. Exempting them would hand NEAR an advantage that is
# an artifact of the quota that forced 2-per-region.
COUNT=${#NAMES[@]}
log() { printf '\033[0;36m==>\033[0m %s\n' "$*"; }

# Written out per host rather than looped through gcloud where it matters:
# a `for` loop wrapping `gcloud compute ssh` silently fails to take effect on
# the remote host (PHASE4_HANDOFF.md §2.2). This loop only BUILDS commands; each
# ssh call is made individually below and its end state verified on the host.
run_on() {  # index, command
  gcloud compute ssh "${NAMES[$1]}" --zone "${ZONES[$1]}" --project "$PROJECT" \
    --command "$2" < /dev/null 2>&1 | grep -v "^Warning:"
}

case "$ACTION" in

apply)
  log "Applying impairment to $COUNT NEAR validators (consensus traffic only)"
  for ((i = 0; i < COUNT; i++)); do
    d=${DELAY_MS[$i]}; j=${JITTER_MS[$i]}; l=${LOSS_PCT[$i]}
    cmd="sudo tc qdisc del dev ens4 root 2>/dev/null; \
         sudo tc qdisc add dev ens4 root handle 1: prio bands 3 && \
         sudo tc qdisc add dev ens4 parent 1:3 handle 30: netem \
           delay ${d}ms ${j}ms distribution normal loss ${l}%"
    for ((k = 0; k < COUNT; k++)); do
      [ "$k" -eq "$i" ] && continue
      cmd="$cmd && sudo tc filter add dev ens4 protocol ip parent 1:0 prio 1 \
           u32 match ip dst ${IPS[$k]}/32 flowid 1:3"
    done
    # Verify the FILTERS, not just the delay rule: the delay rule existing says
    # nothing about whether any live machine's traffic is matched by it. Each
    # machine must carry one filter per peer -- seven.
    cmd="$cmd; echo APPLIED \$(tc qdisc show dev ens4 | grep -c netem) FILTERS \$(sudo tc filter show dev ens4 parent 1:0 | grep -c 'match ')"
    out=$(run_on "$i" "$cmd" | tail -1)
    printf '  %-18s %-22s +%sms ±%sms, %s%% loss  -> %s\n' \
      "${NAMES[$i]}" "${CORRIDOR[$i]}" "$d" "$j" "$l" "$out"
    case "$out" in
      *"FILTERS $((COUNT - 1))") : ;;
      *) echo "error: ${NAMES[$i]} does not carry $((COUNT - 1)) peer filters -- impairment is NOT correctly applied" >&2
         exit 1 ;;
    esac
  done
  echo
  log "Impairment active. Record these values with the results -- they are an"
  echo "    independent variable, not an implementation detail."
  ;;

clear)
  log "Removing impairment from $COUNT NEAR validators"
  for ((i = 0; i < COUNT; i++)); do
    out=$(run_on "$i" "sudo tc qdisc del dev ens4 root 2>/dev/null; echo CLEARED \$(tc qdisc show dev ens4 | grep -c netem)" | tail -1)
    printf '  %-18s %s\n' "${NAMES[$i]}" "$out"
  done
  ;;

show)
  log "Current impairment"
  for ((i = 0; i < COUNT; i++)); do
    out=$(run_on "$i" "tc qdisc show dev ens4 | grep netem || echo 'none'" | tail -1)
    printf '  %-18s %s\n' "${NAMES[$i]}" "$out"
  done
  ;;
esac
