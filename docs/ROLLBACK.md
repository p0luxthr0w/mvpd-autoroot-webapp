# Rollback

Everything below is optional and reversible. None of it modifies the firmware.

## Payloads

`id.sh` and `ssh.sh` leave no persistent change beyond what they create:

```sh
rm -rf /home/root/.ssh
# stop the SSH daemon; it is not started automatically at boot
for p in /proc/[0-9]*; do
  tr '\0' ' ' < "$p/cmdline" 2>/dev/null | grep -q dropbear && kill "${p#/proc/}"
done
```

The appId used for the trigger is removed by `removeMvpd` itself
(`rm -rf /var/lib/mvpd/<appId>`). Leftovers from interrupted runs:

```sh
rm -rf /var/lib/mvpd/*
```

## Persistent root and Homebrew Channel (`payloads/autoroot.sh`)

```sh
luna-send -n 1 -f luna://com.webos.appInstallService/remove '{"id":"org.webosbrew.hbchannel"}'
rm -rf /var/luna/preferences/devmode_enabled
# then reboot
```

Do not create `/media/cryptofs/apps/usr/palm/services/com.palmdts.devmode.service/start-devmode.sh`
unless it carries a valid LG signature: on boot, `devmode.conf` removes `devmode_enabled` and
`/media/developer` when verification fails.

## Update blocking (if applied)

The block is a bind mount of `/etc/hosts` plus
`/var/luna/preferences/webosbrew_block_updates`. A reboot clears the mount; remove the preference
file to stop Homebrew Channel's startup script from re-applying it:

```sh
rm -f /var/luna/preferences/webosbrew_block_updates
```

## Settings changed for debloating

```sh
luna-send -n 1 -f luna://com.webos.settingsservice/setSystemSettings \
  '{"category":"option","settings":{"livePlus":"on"}}'
luna-send -n 1 -f luna://com.webos.settingsservice/setSystemSettings \
  '{"category":"general","settings":{"adCookie":"on"}}'
luna-send -n 1 -f luna://com.webos.service.dmost/enableChannelPlus '{}'
```

Services stopped with `kill` restart on demand or after a reboot.
