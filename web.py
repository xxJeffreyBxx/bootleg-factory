"""The status UI. Stdlib http.server; four routes, no framework."""

import json
import os
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import db
import runner

HERE = os.path.dirname(os.path.abspath(__file__))

# Columns worth showing; last_log is big, so the UI fetches it separately.
TASK_FIELDS = ("id", "text", "status", "slack_user", "created_at", "updated_at",
               "worktree_path", "branch", "pr_url")


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/", "/index.html"):
            with open(os.path.join(HERE, "static", "index.html"), "rb") as f:
                self.send(200, "text/html; charset=utf-8", f.read())
        elif self.path == "/api/tasks":
            rows = [{k: t[k] for k in TASK_FIELDS} for t in db.all_tasks()]
            self.send(200, "application/json", json.dumps(rows).encode())
        elif self.path == "/api/prs":
            self.send(200, "application/json", runner.open_prs().encode())
        elif self.path.startswith("/log/"):
            task = db.get_task(self.path.rsplit("/", 1)[-1])
            body = (task["last_log"] or "(no output yet)") if task else "no such task"
            self.send(200, "text/plain; charset=utf-8", body.encode())
        else:
            self.send(404, "text/plain", b"not found")

    def send(self, code, ctype, body):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass  # the UI polls every 5s; don't drown the console


def free_port(start=7777, tries=20):
    """Default to 7777, step up if something already holds it."""
    for port in range(start, start + tries):
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    raise RuntimeError(f"no free port in {start}..{start + tries}")


def start(port=None):
    """Serve the UI in a background thread. Returns the port in use."""
    port = port or free_port()
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True, name="web").start()
    return port
