#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Operator-side control for the phase 4 cluster. Run from a machine with gcloud
# credentials -- the generator has NO service account attached and cannot call
# the Compute API at all, so cluster-wide actions must originate here.
#
#   status   what every machine is doing, plus chain health and sweep progress
#   renew    push the dead-man's-switch deadline forward by 6 hours
#   stop     halt every machine (disks and chain state survive; resumable)
#
# WHY `renew` EXISTS
# Each machine halts itself at an absolute deadline in /etc/hardcap_deadline.
# The window is deliberately short. If the operator side stops renewing --
# session ends, laptop closes, anything -- the cluster halts within six hours
# instead of billing for days. Renewal is the proof that someone is still
# watching; its absence is the signal to shut down.
#
# WHY EVERY CALL IS WRITTEN OUT INDIVIDUALLY
# A `for` loop wrapping `gcloud compute ssh` or `scp` silently fails to take
# effect on the remote host, and multi-file scp delivers only a subset. Both
# report success. Several nodes reported "FAILED" when the install had not run
# and others reported nothing when it had (PHASE4_HANDOFF.md S2.2). The end
# state is verified on each host rather than inferred from an exit code.
# ---------------------------------------------------------------------------
set -uo pipefail

P="project-c4c87dcb-da41-4caf-922"
ACTION="${1:-status}"

Z_GEN=us-east4-c
Z0=us-east4-c;        Z1=us-east4-c
Z2=asia-south1-a;     Z3=asia-south1-a
Z4=asia-southeast1-a; Z5=asia-southeast1-a
Z6=europe-west2-b;    Z7=europe-west2-b

case "$ACTION" in

renew)
  NEW=$(( $(date +%s) + 6*3600 ))
  echo "new deadline: $NEW ($(python3 -c "import time;print(time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime($NEW)))"))"
  C="echo $NEW | sudo tee /etc/hardcap_deadline >/dev/null && sudo shutdown -c 2>/dev/null; echo \"\$(hostname) -> \$(cat /etc/hardcap_deadline)\""
  gcloud compute ssh near-generator   --zone $Z_GEN --project $P --command "$C" 2>&1 | grep -- '->'
  gcloud compute ssh near-validator-0 --zone $Z0    --project $P --command "$C" 2>&1 | grep -- '->'
  gcloud compute ssh near-validator-1 --zone $Z1    --project $P --command "$C" 2>&1 | grep -- '->'
  gcloud compute ssh near-validator-2 --zone $Z2    --project $P --command "$C" 2>&1 | grep -- '->'
  gcloud compute ssh near-validator-3 --zone $Z3    --project $P --command "$C" 2>&1 | grep -- '->'
  gcloud compute ssh near-validator-4 --zone $Z4    --project $P --command "$C" 2>&1 | grep -- '->'
  gcloud compute ssh near-validator-5 --zone $Z5    --project $P --command "$C" 2>&1 | grep -- '->'
  gcloud compute ssh near-validator-6 --zone $Z6    --project $P --command "$C" 2>&1 | grep -- '->'
  gcloud compute ssh near-validator-7 --zone $Z7    --project $P --command "$C" 2>&1 | grep -- '->'
  ;;

stop)
  # Halt, not delete. Disks, chain state and the database all survive, and the
  # sweep resumes from where it stopped. Deleting would throw away 900 funded
  # accounts and the whole chain history for the sake of a few dollars of disk.
  echo "halting all nine machines (disks and chain state survive)"
  gcloud compute instances stop near-generator   --zone $Z_GEN --project $P -q
  gcloud compute instances stop near-validator-0 --zone $Z0    --project $P -q
  gcloud compute instances stop near-validator-1 --zone $Z1    --project $P -q
  gcloud compute instances stop near-validator-2 --zone $Z2    --project $P -q
  gcloud compute instances stop near-validator-3 --zone $Z3    --project $P -q
  gcloud compute instances stop near-validator-4 --zone $Z4    --project $P -q
  gcloud compute instances stop near-validator-5 --zone $Z5    --project $P -q
  gcloud compute instances stop near-validator-6 --zone $Z6    --project $P -q
  gcloud compute instances stop near-validator-7 --zone $Z7    --project $P -q
  gcloud compute instances list --project $P \
    --format="table(name,zone,status,scheduling.provisioningModel)"
  ;;

status)
  echo "=== instances ==="
  gcloud compute instances list --project $P \
    --format="table(name,zone,status,scheduling.provisioningModel)"
  echo
  echo "=== supervisor status (source of truth for progress) ==="
  gcloud compute ssh near-generator --zone $Z_GEN --project $P \
    --command 'cat /opt/benchmark/data/working/supervisor_status.json' 2>&1 \
    | grep -v '^Warning:'
  echo
  echo "=== deadline on this machine ==="
  gcloud compute ssh near-generator --zone $Z_GEN --project $P \
    --command 'echo "generator deadline $(date -u -d @$(cat /etc/hardcap_deadline))"' 2>&1 \
    | grep deadline
  ;;

*)
  echo "usage: $0 {status|renew|stop}" >&2
  exit 2
  ;;
esac
