"""Trusted test server, never reachable through the production public URL policy."""

import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/timeout"):
            time.sleep(45)
        if self.path.startswith("/unavailable.png"):
            self.send_error(503, "Intentional unavailable fixture asset")
            return
        super().do_GET()


if __name__ == "__main__":
    ThreadingHTTPServer(
        ("127.0.0.1", 8091), partial(Handler, directory=str(Path(__file__).parent / "fixtures"))
    ).serve_forever()
