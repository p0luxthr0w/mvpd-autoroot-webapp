# Compatibility: which firmware / webOS versions does this chain work on?

A single firmware version string is not enough. The chain has **five independent links**, and each
one can fail on its own. Test them separately.

| # | Link | Version-dependent? | How to check |
| :--- | :--- | :--- | :--- |
| 1 | SSAP TLS 3001 reachable, pairing accepted | low (2.x–6.x) | connect + register |
| 2 | `ssap://webapp/launchWebApp` accepts the launch | low (secondscreen gateway) | launch; the page loads |
| 3 | `trustLevel: "default"` exposes `PalmServiceBridge` | **unknown, likely varies** | probe: `typeof PalmServiceBridge` |
| 4 | `mvpd-service` present, `vendor/*` callable publicly | **high** | probe: `setting/get`, then `addMvpd` |
| 5 | `removeMvpd` reaches `system("rm -rf %s")` | tied to link 4 | probe `--mutating`: `removeMvpd` returns true |

## Known data points

| Version / model | Links 1–3 | Links 4–5 | Source |
| :--- | :--- | :--- | :--- |
| webOS 1 – 3.4.2 | not tested here | present | upstream `mvpd-autoroot` README |
| `05.70.55`, `3.4.3-570913`, W16K, OLED55B6V | **verified** | **verified** | this repository |
| `05.70.55`, W16K, 55UH770V-TA | not tested | reported working | `mvpd-autoroot` issue #4 |
| webOS 3.5 and newer | unknown | **absent** | upstream README ("service is not present in 3.5 and newer") |
| webOS 4.x – 6.x | unknown | absent (other exploits apply) | community |

Two conclusions:

- **The 3.4.2/3.4.3 boundary is not a hard cutoff.** The service still exists and is exploitable on
  `05.70.55` (release `3.4.3-570913`, SDK `3.4.0`). The README's "1 through 3.4.2" is a
  conservative claim, not the real limit.
- **Link 3 is the real unknown.** Even on firmware where `mvpd-service` is gone, the question
  "does a requester-chosen `trustLevel` grant the native bridge?" remains worth testing: it is
  independent of MVPD.

## Test a live TV

Read-only (no write, no command execution):

```sh
python3 probe.py --tv <TV_IP> --local-ip <MAC_IP>
```

Interpretation:

- `PalmServiceBridge: yes` + `mvpd-service readable: yes` → the delivery works on this firmware.
- `PalmServiceBridge: no` → link 3 fails; `launchWebApp` exists but the `appInfo` trick does not.
- `PalmServiceBridge: yes` + `mvpd-service readable: no` → delivery works, root does not (no MVPD).

Then the state-changing variant, which creates and removes one throwaway directory under
`/var/lib/mvpd/`:

```sh
python3 probe.py --tv <TV_IP> --local-ip <MAC_IP> --mutating
```

`add/removeMvpd rmdir path: yes` means `removeMvpd` built its `rm -rf` command and `system()`
returned 0. It does not prove command output; use `exploit.py --payload payloads/id.sh` for that.

## Test a firmware offline

1. Download the official EPK for the target model from LG support.
2. Extract it with [epk2extract](https://github.com/openlgtv/epk2extract) (the decryption key
   depends on the chip family).
3. Run the static checker:

```sh
python3 tools/check_firmware.py /path/to/extracted/root
```

It looks for:

- `usr/sbin/mvpd-service` and the strings `rm -rf %s`, `/var/lib/mvpd`, and both
  `interface_mvpd_vendor_*` symbols;
- `webapp.interface` declaring `launchWebApp`;
- the apiadapter `webapp` handler;
- `vendor/addMvpd` and `vendor/removeMvpd` in the **public** permission group of
  `compat.api.json`.

Caveats:

- Static markers do not prove runtime behaviour: permissions, jail, and the `appInfo` handling
  still need a live test.
- A full rootfs extraction can fail on case-insensitive filesystems (macOS name collisions).
  Missing files may be an extraction artifact, not a firmware fact.
- Some partitions are separate (`otncabi`, `tvservice`); the service may live outside the rootfs
  image you extracted.

## Which version string counts?

`getSystemInfo` returns several different values, and they do not move together:

- `sdkVersion`: `3.4.0`
- release: `3.4.3-570913` (shown in TV settings)
- `firmwareVersion`: `05.70.55`
- `otaId`: `HE_DTV_W16K_AFADABAA`
- `boardType`: `K2L_DVB_EU`

Compare devices by **model + OTA id + firmware**, not by SDK alone. A device can report SDK 3.4.0
while running a 3.4.3 release.

## Community sources

- [CanI.RootMy.TV](https://cani.rootmy.tv/) — per-model/firmware root status.
- [mvpd-autoroot](https://github.com/throwaway96/mvpd-autoroot) — README and issues, including
  #4 (`05.70.55`, W16K).
- [webosbrew](https://www.webosbrew.org/) — Homebrew Channel and firmware notes.

## Filling the matrix

When you test a device, record:

```
model:
firmwareVersion / release / otaId / boardType:
links 1-2 (launch): yes/no
link 3 (bridge with trustLevel=default): yes/no
link 4 (mvpd read / add+remove): yes/no
link 5 (rmdir path, exploit id payload): yes/no
notes:
```

Open an issue or a PR with the row so the matrix grows.
