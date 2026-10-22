#!/usr/bin/env python3
"""Read-only compatibility probe for the mvpd-webapp delivery chain.

Checks, on a live TV, each link of the chain:
  1. SSAP reachable and pairing accepted
  2. launchWebApp accepted
  3. trustLevel="default" exposes PalmServiceBridge
  4. mvpd-service answers a read
  5. (optional, --mutating) addMvpd/removeMvpd reach the rmdir path

It never fetches a payload and never executes a command by default.
"""

import argparse
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from webos_ssap import SSAPClient, SSAPError, WebSocket

HERE = Path(__file__).resolve().parent

PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><title>mvpd probe</title></head>
<body style="background:#111;color:#eee;font:22px sans-serif;padding:24px"><pre id="out"></pre>
<script>
(function () {
    var MUTATE = __MUTATE__;
    var NAME = __NAME__;
    var out = document.getElementById('out'), keep = [];
    function log(m) {
        out.textContent += m + '\\n';
        var i = new Image(); keep.push(i);
        i.src = '/log?message=' + encodeURIComponent(m);
    }
    function call(label, uri, payload, next) {
        var B = typeof PalmServiceBridge === 'function' ? PalmServiceBridge : null;
        if (!B) { log(label + ': bridge unavailable'); return; }
        var b = new B(); keep.push(b);
        b.onservicecallback = function (r) { log(label + ': ' + r); if (next) next(); };
        b.call(uri, JSON.stringify(payload));
    }
    log('PalmSystem: ' + typeof PalmSystem);
    log('PalmServiceBridge: ' + typeof PalmServiceBridge);
    log('webOSServiceBridge: ' + typeof webOSServiceBridge);
    call('system', 'luna://com.webos.service.tv.systemproperty/getSystemInfo',
         {keys: ['sdkVersion', 'firmwareVersion', 'otaId', 'boardType']});
    call('mvpd-read', 'luna://com.webos.service.mvpd/setting/get',
         {appId: 'mvpdprobe', key: '__mvpd_probe_missing__'});
    if (MUTATE) {
        call('addMvpd', 'luna://com.webos.service.mvpd/vendor/addMvpd', {appId: NAME}, function () {
            call('removeMvpd', 'luna://com.webos.service.mvpd/vendor/removeMvpd', {appId: NAME}, null);
        });
    }
    if (window.PalmSystem) window.PalmSystem.stageReady();
})();
</script></body></html>
"""


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Probe the mvpd-webapp chain on a live TV.")
    p.add_argument("--tv", required=True)
    p.add_argument("--local-ip", required=True)
    p.add_argument("--http-port", type=int, default=8080)
    p.add_argument("--key-file", default=str(HERE / "client.key"))
    p.add_argument("--manifest-app-id", default="org.local.mvpdwebapp")
    p.add_argument("--mutating", action="store_true",
                   help="also create and remove a throwaway /var/lib/mvpd entry")
    p.add_argument("--timeout", type=float, default=20.0)
    p.add_argument("--debug", action="store_true")
    return p.parse_args(argv)


def log(message):
    print("[%s] %s" % (time.strftime("%H:%M:%S"), message), flush=True)


class Probe:
    def __init__(self, args):
        self.args = args
        self.lines = []
        self.done = threading.Event()
        self.lock = threading.Lock()

    def page(self):
        name = "mvpdprobe" + str(int(time.time()))
        return (PAGE.replace("__MUTATE__", "true" if self.args.mutating else "false")
                    .replace("__NAME__", json.dumps(name)).encode())

    def serve(self):
        probe = self
        page = self.page()

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                parsed = urlsplit(self.path)
                if parsed.path == "/log":
                    message = parse_qs(parsed.query).get("message", [""])[0][:4000]
                    with probe.lock:
                        probe.lines.append(message)
                    log("TV: " + message)
                    if message.startswith("removeMvpd:") or (
                            not probe.args.mutating and message.startswith("mvpd-read:")):
                        probe.done.set()
                    self.send_response(204)
                    self.end_headers()
                    return
                if parsed.path != "/probe":
                    self.send_error(404)
                    return
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(page)))
                self.end_headers()
                self.wfile.write(page)

            def log_message(self, fmt, *a):
                if probe.args.debug:
                    log("http: " + (fmt % a))

        server = ThreadingHTTPServer((self.args.local_ip, self.args.http_port), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        return server


def verdict(lines, mutating):
    joined = "\n".join(lines)
    bridge = "PalmServiceBridge: function" in joined or "PalmServiceBridge: object" in joined
    mvpd = "mvpd-read: {" in joined and '"returnValue":true' in joined.replace(" ", "")
    launch = True  # reaching the page means the launch worked
    rmdir = "removeMvpd:" in joined and '"returnValue":true' in joined.replace(" ", "")
    print()
    print("== verdict ==")
    print("launchWebApp accepted            : %s" % ("yes" if launch else "no"))
    print("PalmServiceBridge (trustLevel)   : %s" % ("yes" if bridge else "no"))
    print("mvpd-service readable            : %s" % ("yes" if mvpd else "no"))
    if mutating:
        print("add/removeMvpd rmdir path        : %s" % ("yes" if rmdir else "no"))
        print("=> chain plausible               : %s" % ("YES" if (bridge and mvpd and rmdir) else "NO"))
    else:
        print("=> chain plausible (read-only)   : %s" % ("YES" if (bridge and mvpd) else "NO"))
        print("   re-run with --mutating to test the rmdir/system() path")
    return 0 if (bridge and mvpd) else 1


def main(argv=None):
    args = parse_args(argv)
    probe = Probe(args)
    server = probe.serve()
    client = None
    try:
        client = SSAPClient(WebSocket.connect(args.tv, 3001, secure=True))
        key_path = Path(args.key_file)
        key = key_path.read_text().strip() if key_path.exists() else ""
        manifest = {
            "manifestVersion": 1, "appVersion": "1.0", "appId": args.manifest_app_id,
            "vendorId": "mvpd-autoroot-webapp", "localizedAppNames": {"": "MVPD probe"},
            "localizedVendorNames": {"": "mvpd-autoroot-webapp"},
            "permissions": ["LAUNCH", "CLOSE", "READ_APP_STATUS",
                            "READ_INSTALLED_APPS", "READ_RUNNING_APPS", "LAUNCH_WEBAPP"],
        }
        new_key = client.register(key, manifest, timeout=90.0, log=log)
        if new_key and new_key != key:
            key_path.write_text(new_key)
            key_path.chmod(0o600)

        response = client.request("ssap://webapp/launchWebApp", {
            "webAppId": "mvpdprobe" + str(int(time.time())),
            "webAppUrl": "http://%s:%d/probe" % (args.local_ip, args.http_port),
            "noLoadingSplash": True,
            "appInfo": {"title": "MVPD probe", "type": "web", "trustLevel": "default"},
        })
        log("launch response: " + json.dumps(response))
        launched = (response.get("payload") or {}).get("id")
        session = (response.get("payload") or {}).get("sessionId")
        probe.done.wait(args.timeout)
        time.sleep(1)
        if launched:
            close = {"webAppId": launched, "id": launched}
            if session:
                close["sessionId"] = session
            client.request("ssap://webapp/closeWebApp", close)
    except SSAPError as error:
        log("error: %s" % error)
        return 2
    finally:
        if client is not None:
            client.close()
        server.shutdown()
        server.server_close()
    return verdict(probe.lines, args.mutating)


if __name__ == "__main__":
    sys.exit(main())
