#!/bin/bash
cp /tmp/hardcap.sh /usr/local/bin/hardcap.sh
chmod +x /usr/local/bin/hardcap.sh
cp /tmp/hardcap_deadline /etc/hardcap_deadline
printf '%s\n' '*/5 * * * * root /usr/local/bin/hardcap.sh' > /etc/cron.d/hardcap
chmod 644 /etc/cron.d/hardcap
echo "INSTALLED $(hostname) deadline=$(cat /etc/hardcap_deadline)"
