"""Temporary capability-authenticated document server INSIDE the isolated browser.

Never exposed to the host, control network, or URL-submission API. Only Lighthouse
for an already authenticated renderer document may bypass its proxy for loopback.
"""

import secrets
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


@contextmanager
def private_document(html):
    if html is None:
        yield None
        return
    path = "/" + secrets.token_urlsafe(32)
    body = html.encode()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # Never log the capability.

        def do_GET(self):
            if not secrets.compare_digest(self.path, path):
                self.send_error(403)
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Robots-Tag", "noindex,nofollow")
            self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; img-src data:; base-uri 'none'; form-action 'none'")
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}{path}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
