"""Explicit integration-only server, fixed fixture names; no filesystem traversal."""
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

NAMES = {"clean": "clean", "overflow": "overflow", "broken-contact": "broken_contact",
         "missing-labels": "missing_labels", "conflicting-facts": "conflicting_facts",
         "prompt-injection": "prompt_injection"}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        slug = self.path.split("?", 1)[0].strip("/")
        if slug == "timeout":
            time.sleep(25)  # Actual navigation timeout, not a simulated capture result.
            self.send_error(504)
            return
        if slug not in NAMES:
            self.send_error(404)
            return
        body = (Path("evals/fixtures") / (NAMES[slug] + ".html")).read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8082), Handler).serve_forever()
