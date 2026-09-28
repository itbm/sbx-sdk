#!/usr/bin/env python3
"""A tiny stand-in for the sbx daemon, served over a Unix socket.

Used by the SDK smoke tests to check each wrapper's socket transport end to
end. It implements only the few endpoints the smoke tests call.

Usage: fake_sbxd.py SOCKET_PATH [--token TOKEN]

When --token is given, every endpoint except /daemon/health and /daemon/info
requires `Authorization: Bearer TOKEN`, as the real daemon's spec describes.
"""

import argparse
import json
import os
import re
import socketserver
import sys
from http.server import BaseHTTPRequestHandler

SANDBOXES = [
    {
        "id": "abc123",
        "name": "claude-demo",
        "agent": "claude",
        "status": "running",
        "workspaces": [{"path": "/home/user/demo", "read_only": False}],
    }
]

PUBLIC_PATHS = {"/daemon/health", "/daemon/info"}
EXEC_PATH = re.compile(r"^/sandbox/([^/]+)/exec$")


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    token = None
    socket_path = ""

    def log_message(self, format, *args):  # noqa: A002 - matches the base class
        # The base implementation reads client_address[0], which is empty for
        # Unix sockets.
        sys.stderr.write("fake_sbxd: " + (format % args) + "\n")

    def _send(self, status, body=b"", content_type="application/json"):
        self.send_response(status)
        if body:
            self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _json(self, status, value):
        self._send(status, json.dumps(value).encode())

    def _authorised(self):
        if self.token is None or self.path.split("?")[0] in PUBLIC_PATHS:
            return True
        if self.headers.get("Authorization") == f"Bearer {self.token}":
            return True
        self._json(401, {"message": "unauthorized"})
        return False

    def _read_body(self):
        length = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(length) if length else b""

    def do_GET(self):
        if not self._authorised():
            return
        path = self.path.split("?")[0]
        if path == "/daemon/health":
            self._json(200, {
                "api_version": "0.16.0",
                "release": False,
                "revision": "fake",
                "status": "healthy",
                "version": "v0.34.0",
            })
        elif path == "/daemon/info":
            self._json(200, {"api_socket": self.socket_path, "docker_socket": ""})
        elif path == "/sandbox":
            self._json(200, SANDBOXES)
        else:
            self._json(404, {"message": "not found"})

    def do_POST(self):
        if not self._authorised():
            return
        body = self._read_body()
        match = EXEC_PATH.match(self.path.split("?")[0])
        if match:
            if match.group(1) not in {s["name"] for s in SANDBOXES}:
                self._json(404, {"message": "sandbox not found"})
                return
            cmd = json.loads(body or b"{}").get("cmd", [])
            self._send(200, (" ".join(cmd) + "\n").encode(), "text/plain")
        else:
            self._json(404, {"message": "not found"})


class Server(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("socket_path")
    parser.add_argument("--token")
    args = parser.parse_args()

    if os.path.exists(args.socket_path):
        os.unlink(args.socket_path)
    Handler.token = args.token
    Handler.socket_path = args.socket_path
    with Server(args.socket_path, Handler) as server:
        print("ready", flush=True)
        try:
            server.serve_forever()
        finally:
            os.unlink(args.socket_path)


if __name__ == "__main__":
    main()
