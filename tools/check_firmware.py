#!/usr/bin/env python3
"""Offline check of an extracted LG firmware tree for the mvpd-webapp chain.

Usage: check_firmware.py /path/to/extracted/root

The tree must contain usr/sbin/mvpd-service and the webapp service files, e.g.
the output of epk2extract or a mounted rootfs. It does not replace a live test.
"""

import json
import sys
from pathlib import Path

CHECKS = []


def report(name, ok, detail=""):
    CHECKS.append((name, ok, detail))
    print("%-42s %s%s" % (name, "OK" if ok else "MISSING", ("  " + detail) if detail else ""))


def main(argv):
    if len(argv) != 2:
        sys.exit(__doc__)
    root = Path(argv[1])

    binary = root / "usr/sbin/mvpd-service"
    report("mvpd-service binary", binary.is_file())
    if binary.is_file():
        data = binary.read_bytes()
        report("  system() rmdir format", b"rm -rf %s" in data)
        report("  /var/lib/mvpd path", b"/var/lib/mvpd" in data)
        report("  addMvpd/removeMvpd symbols",
               b"interface_mvpd_vendor_addMvpd" in data and b"interface_mvpd_vendor_removeMvpd" in data)

    interface = (root / "usr/palm/services/com.webos.service.secondscreen.gateway"
                      / "interfaces/webapp.interface")
    report("webapp.interface", interface.is_file())
    if interface.is_file():
        report("  launchWebApp declared", "launchWebApp" in interface.read_text(errors="replace"))

    adapter = (root / "usr/palm/services/com.webos.service.apiadapter/adapters/webapp/index.js")
    report("apiadapter webapp handler", adapter.is_file())

    permissions = root / "usr/share/luna-service2/api-permissions.d/compat.api.json"
    report("compat.api.json", permissions.is_file())
    if permissions.is_file():
        try:
            groups = json.loads(permissions.read_text(errors="replace"))
        except json.JSONDecodeError:
            groups = {}
        public = set(groups.get("public") or [])
        report("  vendor methods are public",
               "com.webos.service.mvpd/vendor/addMvpd" in public
               and "com.webos.service.mvpd/vendor/removeMvpd" in public)

    ok = all(flag for _, flag, _ in CHECKS)
    print()
    print("all static markers present" if ok else "at least one marker is missing")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
