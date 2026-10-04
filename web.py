"""The status UI. Stdlib http.server; five routes, no framework."""

import json
import os
import socket
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import db
import runner

HERE = os.path.dirname(os.path.abspath(__file__))

# Columns worth showing; last_log is big, so the UI fetches it separately.
TASK_FIELDS = ("id", "text", "status", "slack_user", "created_at", "updated_at",
               "worktree_path", "branch", "pr_url")

MAX_BODY = 64 * 1024  # a task is a sentence or a paragraph, not a file


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

    def do_POST(self):
        if self.path != "/api/tasks":
            return self.send(404, "text/plain", b"not found")
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return self.error(400, "bad Content-Length")
        if length < 0:  # rfile.read(-1) would block until the client hangs up
            return self.error(400, "bad Content-Length")
        if length > MAX_BODY:
            return self.error(413, "body too large")
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            return self.error(400, "body must be JSON")
        text = body.get("text") if isinstance(body, dict) else None
        if not isinstance(text, str) or not text.strip():
            return self.error(400, "text is required")
        # No Slack message behind this task: a synthetic, unique slack_ts keeps
        # the UNIQUE index happy, and the empty channel tells notify to stay quiet.
        task_id = db.add_task(text.strip(), "", "", f"ui-{uuid.uuid4().hex}", "")
        self.send(200, "application/json", json.dumps({"id": task_id}).encode())

    def error(self, code, message):
        self.send(code, "application/json", json.dumps({"error": message}).encode())

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


def start(preferred=7777):
    """Serve the UI in a background thread. Returns the port actually used."""
    port = free_port(preferred)
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True, name="web").start()
    return port
