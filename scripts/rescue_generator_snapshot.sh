#!/usr/bin/env bash
# Copy the validator health log (and the generator's other small logs) out of
# the 13 Aug snapshot, so the nine NEAR snapshots can be deleted.
#
# WHY THIS EXISTS
# The snapshots cost ~$24/month and the $300 credit expires 6 Nov 2026. The
# only thing on them that exists nowhere else is the generator's working
# directory, above all data/working/validator_liveness.jsonl: the record that
# every published NEAR run had its full validator set (ANALYSIS_PLAN.md
# amendment on validator liveness). Everything else -- results, the original
# token contract -- is already in this repository.
#
# WHAT IT DOES, AND WHAT IT COSTS
# Builds a temporary disk from snap-near-generator, starts a small machine,
# attaches the disk and mounts it READ-ONLY, copies the text logs and a manifest of every
# file to data/near_supplementary/rescued_generator_13aug/, then deletes the
# machine and the disk. About 15 minutes; well under $0.10.
#
# Three guards, because a forgotten machine is this project's classic leak:
#   1. a trap deletes the machine and disk on ANY exit, including Ctrl-C;
#   2. Google itself deletes the machine after 60 minutes (--max-run-duration),
#      even if this laptop dies mid-run;
#   3. the disk is set to auto-delete with the machine.
#
# The disk is ATTACHED read-write but MOUNTED read-only. Google refuses
# auto-delete on a disk attached read-only (found on the first real run,
# 19 Oct), and guard 3 matters more: without it, a laptop dying mid-run
# leaves a 100 GB disk billing after the machine deletes itself. Nothing is
# written either way -- the mount is ro,noload -- and the disk is a throwaway
# copy; the snapshot cannot be changed from here.
#
# WHY A DEBIAN MACHINE, AND WHY THE DISK IS ATTACHED AFTER BOOT
# The snapshot is an Ubuntu boot disk. On 24 Aug, attaching a boot-disk clone
# to an Ubuntu machine gave two disks the same filesystem label and threw the
# next boot into emergency mode (README.md cloud trap 15). A Debian rescue
# machine has different labels, and attaching only once it is running means
# the clone never takes part in a boot at all.
#
# The snapshot itself is never modified: Google builds the disk from it.
#
# USAGE
#   ./scripts/rescue_generator_snapshot.sh            # do it
#   ./scripts/rescue_generator_snapshot.sh --dry-run  # print the plan, touch nothing

set -euo pipefail

PROJECT="project-c4c87dcb-da41-4caf-922"
ZONE="us-east4-c"                 # where near-generator lived; a snapshot can restore anywhere, this is just consistent
SNAPSHOT="snap-near-generator"
VM="near-rescue-vm"
DISK="near-rescue-disk"
REMOTE_ROOT="/opt/benchmark"      # the harness's home on the generator
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="$REPO/data/near_supplementary/rescued_generator_13aug"

DRY=0
[[ "${1:-}" == "--dry-run" ]] && DRY=1

run() {
  echo "+ $*"
  if (( DRY == 0 )); then "$@"; fi
}

cleanup() {
  # Runs on every exit. Deleting something already gone is not an error here.
  echo
  echo "== cleaning up (machine and temporary disk)"
  if (( DRY == 1 )); then
    echo "+ gcloud compute instances delete $VM --project $PROJECT --zone $ZONE --quiet"
    echo "+ gcloud compute disks delete $DISK --project $PROJECT --zone $ZONE --quiet"
    return
  fi
  gcloud compute instances delete "$VM" --project "$PROJECT" --zone "$ZONE" --quiet 2>/dev/null || true
  gcloud compute disks delete "$DISK" --project "$PROJECT" --zone "$ZONE" --quiet 2>/dev/null || true
  left=$(gcloud compute instances list --project "$PROJECT" --format="value(name)" 2>/dev/null; \
         gcloud compute disks list --project "$PROJECT" --format="value(name)" 2>/dev/null)
  if [[ -n "$left" ]]; then
    echo "!! STILL PRESENT IN THE PROJECT -- delete these in the console, they bill:"
    echo "$left"
  else
    echo "   nothing left running or stored except the snapshots."
  fi
}
trap cleanup EXIT

echo "== 0. preflight"
if (( DRY == 0 )); then
  gcloud compute snapshots describe "$SNAPSHOT" --project "$PROJECT" --format="value(status)" | grep -qx READY \
    || { echo "snapshot $SNAPSHOT not found or not READY in $PROJECT"; exit 1; }
  if gcloud compute instances describe "$VM" --project "$PROJECT" --zone "$ZONE" >/dev/null 2>&1 \
     || gcloud compute disks describe "$DISK" --project "$PROJECT" --zone "$ZONE" >/dev/null 2>&1; then
    echo "$VM or $DISK already exists -- a previous run did not clean up."
    echo "Delete them first:"
    echo "  gcloud compute instances delete $VM --project $PROJECT --zone $ZONE"
    echo "  gcloud compute disks delete $DISK --project $PROJECT --zone $ZONE"
    trap - EXIT; exit 1
  fi
  mkdir -p "$DEST"
fi

echo "== 1. temporary disk from the snapshot"
run gcloud compute disks create "$DISK" --project "$PROJECT" --zone "$ZONE" \
  --source-snapshot "$SNAPSHOT" --type pd-standard

echo "== 2. small Debian machine that deletes itself after 60 minutes"
run gcloud compute instances create "$VM" --project "$PROJECT" --zone "$ZONE" \
  --machine-type e2-small --image-family debian-12 --image-project debian-cloud \
  --boot-disk-size 10GB --max-run-duration 60m --instance-termination-action DELETE

echo "== 3. attach the snapshot copy after boot (mounted read-only in step 4)"
run gcloud compute instances attach-disk "$VM" --project "$PROJECT" --zone "$ZONE" \
  --disk "$DISK" --device-name "$DISK"
run gcloud compute instances set-disk-auto-delete "$VM" --project "$PROJECT" --zone "$ZONE" \
  --disk "$DISK" --auto-delete

# Everything below runs ON the rescue machine. The root filesystem is the
# largest ext4 partition on the attached disk; `noload` stops ext4 from
# replaying its journal, which would be a write.
read -r -d '' REMOTE <<EOF || true
set -euo pipefail
DEV=\$(lsblk -lnpo NAME,FSTYPE,SIZE -b /dev/disk/by-id/google-$DISK | awk '\$2=="ext4"{print \$3, \$1}' | sort -n | tail -1 | cut -d' ' -f2)
echo "root partition: \$DEV"
sudo mkdir -p /mnt/rescue
sudo mount -o ro,noload "\$DEV" /mnt/rescue
W=/mnt/rescue$REMOTE_ROOT
test -d "\$W" || { echo "no $REMOTE_ROOT on this disk"; exit 1; }
echo "--- size of $REMOTE_ROOT/data/working"
sudo du -sh "\$W/data/working" || true
# Manifest of EVERYTHING under the harness directory, kept even for files not
# copied, so the repository records what existed before the snapshot is gone.
sudo find "\$W" -xdev -type f -printf '%s\t%TY-%Tm-%Td %TH:%TM\t%P\n' | sort -k3 > /tmp/manifest.tsv
# The text logs: health log, node events, run logs. Not the SQLite databases
# (their contents are already in data/raw) and not the chain itself. Run as
# root throughout: /opt/benchmark is root-owned, so even cd into it fails as
# the login user.
sudo sh -c 'cd "\$1" && find . -xdev -type f \( -name "*.jsonl" -o -name "*.log" -o -name "*.csv" -o -name "*.txt" \) -size -500M -print0 | tar --null -czf /tmp/rescued_logs.tar.gz --files-from=-' _ "\$W"
sudo sha256sum "\$W/data/working/validator_liveness.jsonl" > /tmp/validator_liveness.sha256 || echo "WARNING: validator_liveness.jsonl not found"
ls -la /tmp/rescued_logs.tar.gz /tmp/manifest.tsv
EOF

echo "== 4. mount and package the logs on the rescue machine"
if (( DRY == 1 )); then
  echo "+ gcloud compute ssh $VM -- <mount read-only, list, tar the logs>"
  echo "$REMOTE" | sed 's/^/    | /'
else
  # The first ssh can race the machine finishing boot; retry briefly.
  for i in 1 2 3 4 5 6; do
    gcloud compute ssh "$VM" --project "$PROJECT" --zone "$ZONE" --quiet --command "true" 2>/dev/null && break
    echo "   waiting for ssh ($i/6)"; sleep 15
  done
  gcloud compute ssh "$VM" --project "$PROJECT" --zone "$ZONE" --quiet --command "$REMOTE"
fi

echo "== 5. copy back to $DEST"
for f in rescued_logs.tar.gz manifest.tsv validator_liveness.sha256; do
  run gcloud compute scp --project "$PROJECT" --zone "$ZONE" --quiet "$VM:/tmp/$f" "$DEST/$f" || true
done

if (( DRY == 0 )); then
  echo "== 6. verify locally"
  test -s "$DEST/rescued_logs.tar.gz" || { echo "!! no logs came back -- do NOT delete the snapshots"; exit 1; }
  tar -tzf "$DEST/rescued_logs.tar.gz" | grep -q 'validator_liveness.jsonl' \
    && echo "   validator_liveness.jsonl is in the archive" \
    || { echo "!! validator_liveness.jsonl is NOT in the archive -- do NOT delete the snapshots"; exit 1; }
  ls -la "$DEST"
  echo
  echo "Done. Next: commit $DEST, then follow docs/snapshot_retirement.md."
fi
