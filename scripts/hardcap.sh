#!/bin/bash
# Absolute lifetime cap. The deadline is an epoch timestamp in
# /etc/hardcap_deadline, so this SURVIVES REBOOTS -- unlike the previous `at`
# job, which vanished when the generator rebooted on 11 Aug 2026 and left the
# whole cluster with no shutdown protection of any kind.
D=$(cat /etc/hardcap_deadline 2>/dev/null || echo 0)
[ "$(date +%s)" -ge "$D" ] && /sbin/shutdown -h now "hard lifetime cap reached"
