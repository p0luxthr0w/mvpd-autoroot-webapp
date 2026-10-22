#!/bin/sh
# Key-only root SSH using the dropbear bundled with Homebrew Channel.
mkdir -p /home/root/.ssh
chmod 700 /home/root/.ssh
add_key() {
  grep -qF "$1" /home/root/.ssh/authorized_keys 2>/dev/null || echo "$1" >> /home/root/.ssh/authorized_keys
}
{{SSH_KEYS}}
chmod 600 /home/root/.ssh/authorized_keys
mkdir -p /var/lib/webosbrew/sshd
chmod 700 /var/lib/webosbrew/sshd
DROPBEAR=/media/developer/apps/usr/palm/services/org.webosbrew.hbchannel.service/bin/dropbear
if [ ! -x "$DROPBEAR" ]; then
  echo "dropbear not found: install Homebrew Channel first"
  exit 1
fi
if ! netstat -ltn 2>/dev/null | grep -qE '[:.]22[[:space:]]'; then
  "$DROPBEAR" -R -p 22 -s
fi
sleep 1
netstat -ltn 2>/dev/null | grep -qE '[:.]22[[:space:]]' && echo sshd-up || echo sshd-down
