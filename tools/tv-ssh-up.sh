#!/bin/sh
# Bring up key-only root SSH after a TV reboot.
# TV=<tv ip> LOCAL=<this machine ip> KEY=~/.ssh/id_ed25519 MANIFEST=org.local.mvpdwebapp
set -e
: "${TV:?set TV to the TV IP}"
: "${LOCAL:?set LOCAL to this machine IP}"
KEY=${KEY:-$HOME/.ssh/id_ed25519}
MANIFEST=${MANIFEST:-org.local.mvpdwebapp}
cd "$(dirname "$0")/.."
python3 exploit.py --tv "$TV" --local-ip "$LOCAL" --manifest-app-id "$MANIFEST" \
    --payload payloads/ssh.sh --ssh-pubkey "$KEY.pub"
ssh -i "$KEY" "root@$TV" 'id; uptime'
