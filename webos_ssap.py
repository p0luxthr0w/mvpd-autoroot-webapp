"""Minimal SSAP client for LG webOS TVs (standard library only).

Implements just what this project needs: a TLS WebSocket on port 3001, the
register/pairing handshake, and request/response calls.
"""

import base64
import json
import os
import socket
import ssl
import struct
import time

WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
DEFAULT_TIMEOUT = 10.0


class SSAPError(Exception):
    pass


class WebSocket:
    """Very small RFC 6455 client: text frames, ping/pong, close."""

    def __init__(self, sock):
        self._sock = sock
        self.closed = False

    @classmethod
    def connect(cls, host, port=3001, secure=True, timeout=DEFAULT_TIMEOUT):
        raw = socket.create_connection((host, port), timeout)
        if secure:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            raw = context.wrap_socket(raw, server_hostname=host)
        key = base64.b64encode(os.urandom(16)).decode()
        request = (
            "GET / HTTP/1.1\r\n"
            "Host: %s:%d\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            "Sec-WebSocket-Key: %s\r\n"
            "Sec-WebSocket-Version: 13\r\n"
            "\r\n" % (host, port, key)
        )
        raw.sendall(request.encode())
        response = b""
        while b"\r\n\r\n" not in response:
            chunk = raw.recv(4096)
            if not chunk:
                raise SSAPError("connection closed during WebSocket handshake")
            response += chunk
        status = response.split(b"\r\n", 1)[0]
        if b" 101 " not in status:
            raise SSAPError("WebSocket handshake failed: %s" % status.decode(errors="replace"))
        return cls(raw)

    # -- framing ---------------------------------------------------------

    def _send_frame(self, opcode, payload):
        header = bytes([0x80 | opcode])
        length = len(payload)
        if length < 126:
            header += bytes([0x80 | length])
        elif length < 65536:
            header += bytes([0x80 | 126]) + struct.pack("!H", length)
        else:
            header += bytes([0x80 | 127]) + struct.pack("!Q", length)
        mask = os.urandom(4)
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        self._sock.sendall(header + mask + masked)

    def _recv_exact(self, count):
        data = b""
        while len(data) < count:
            chunk = self._sock.recv(count - len(data))
            if not chunk:
                raise SSAPError("connection closed")
            data += chunk
        return data

    def _recv_frame(self):
        first, second = self._recv_exact(2)
        fin = first & 0x80
        opcode = first & 0x0F
        masked = second & 0x80
        length = second & 0x7F
        if length == 126:
            length = struct.unpack("!H", self._recv_exact(2))[0]
        elif length == 127:
            length = struct.unpack("!Q", self._recv_exact(8))[0]
        mask = self._recv_exact(4) if masked else None
        payload = self._recv_exact(length) if length else b""
        if mask:
            payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        return bool(fin), opcode, payload

    def send_text(self, text):
        self._send_frame(0x1, text.encode())

    def recv_text(self, timeout=DEFAULT_TIMEOUT):
        """Return the next text message, or None if the peer closed."""
        self._sock.settimeout(timeout)
        buffer = b""
        while True:
            try:
                fin, opcode, payload = self._recv_frame()
            except socket.timeout:
                raise
            if opcode == 0x8:
                self.closed = True
                return None
            if opcode == 0x9:  # ping
                self._send_frame(0xA, payload)
                continue
            if opcode == 0xA:  # pong
                continue
            if opcode in (0x1, 0x2, 0x0):
                buffer += payload
                if fin:
                    return buffer.decode(errors="replace")

    def close(self):
        if not self.closed:
            try:
                self._send_frame(0x8, b"")
            except OSError:
                pass
            self.closed = True
        try:
            self._sock.close()
        except OSError:
            pass


class SSAPClient:
    def __init__(self, ws):
        self._ws = ws
        self._counter = 0

    def _next_id(self, prefix):
        self._counter += 1
        return "%s_%d" % (prefix, self._counter)

    def register(self, client_key="", manifest=None, timeout=60.0, log=print):
        """Register/pair. Blocks until the user accepts the prompt on the TV."""
        payload = {
            "forcePairing": False,
            "pairingType": "PROMPT",
            "manifest": manifest or {},
        }
        if client_key:
            payload["client-key"] = client_key
        message_id = self._next_id("register")
        self._ws.send_text(json.dumps({"id": message_id, "type": "register", "payload": payload}))
        prompted = False
        deadline = time.time() + timeout
        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                raise SSAPError("timed out waiting for registration")
            try:
                raw = self._ws.recv_text(timeout=remaining)
            except socket.timeout:
                raise SSAPError("timed out waiting for registration")
            if raw is None:
                raise SSAPError("connection closed during registration")
            message = json.loads(raw)
            kind = message.get("type")
            if kind == "registered":
                return (message.get("payload") or {}).get("client-key", client_key)
            if kind == "response" and (message.get("payload") or {}).get("pairingType"):
                if not prompted:
                    prompted = True
                    log("Accept the pairing prompt on the TV.")
                continue
            if kind == "error":
                raise SSAPError(message.get("error") or "registration rejected")

    def request(self, uri, payload=None, timeout=15.0):
        message_id = self._next_id("req")
        self._ws.send_text(json.dumps({
            "id": message_id,
            "type": "request",
            "uri": uri,
            "payload": payload or {},
        }))
        deadline = time.time() + timeout
        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                raise SSAPError("timed out waiting for %s" % uri)
            try:
                raw = self._ws.recv_text(timeout=remaining)
            except socket.timeout:
                raise SSAPError("timed out waiting for %s" % uri)
            if raw is None:
                raise SSAPError("connection closed while awaiting %s" % uri)
            message = json.loads(raw)
            if message.get("id") == message_id:
                return message

    def close(self):
        self._ws.close()
