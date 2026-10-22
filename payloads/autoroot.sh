#!/bin/sh
# Run the upstream mvpd-autoroot (AGPL, throwaway96) as root:
# persistent devmode flag, Homebrew Channel install, service elevation.
set -e
cd /tmp
BASE=https://raw.githubusercontent.com/throwaway96/mvpd-autoroot/main
IPK=https://github.com/webosbrew/webos-homebrew-channel/releases/download/v0.7.3/org.webosbrew.hbchannel_0.7.3_all.ipk
curl -sSL -o autoroot.sh "$BASE/autoroot.sh"
curl -sSL -o hbchannel.ipk "$IPK"
sh autoroot.sh -d
