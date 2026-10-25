#!/usr/bin/env bash
# List the ACTUAL sweep and noise processes with full command lines.
#
# `pgrep -fc <pattern>` run through `gcloud ssh --command` counts the SSH
# command itself, because that command string contains the pattern. That is
# PHASE4_HANDOFF.md (in git history) bug 4, and it produced a false "3 duplicates" reading. From a
# script file the pattern exists only inside the file.
echo "--- processes matching the sweep script ---"
ps -eo pid,etimes,args --no-headers | grep -F 'run_near_sweep_inner.sh' | grep -v grep \
  | awk '{printf "  pid %-7s up %5ss  %s\n", $1, $2, substr($0, index($0,$3))}'
echo "--- processes matching the noise generator ---"
ps -eo pid,etimes,args --no-headers | grep -F 'harness.noise_near' | grep -v grep \
  | awk '{printf "  pid %-7s up %5ss  %s\n", $1, $2, substr($0, index($0,$3))}'
echo "--- measured-run processes (children of the sweep) ---"
ps -eo pid,etimes,args --no-headers | grep -F 'harness.cli' | grep -v grep \
  | awk '{printf "  pid %-7s up %5ss\n", $1, $2}'
echo "--- pid files ---"
echo "  sweep.pid=$(cat /opt/benchmark/data/working/sweep.pid 2>/dev/null)  noise.pid=$(cat /opt/benchmark/data/working/noise.pid 2>/dev/null)"
