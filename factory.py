"""The pipeline loop: dispatch work, watch subprocesses, advance state.

One thread, one `while True`. All state lives in SQLite; the only thing held in
memory is the handle on each live subprocess.
"""

import subprocess
import threading
import time
import traceback

import db
import runner

TICK = 2.0  # seconds between polls


class Factory:
    def __init__(self, notify):
        # notify(task_row, text) posts back to the task's Slack thread.
        self.notify = notify
        self.running = {}  # task_id -> ("imp" | "qa", Popen)

    # ---- lifecycle -------------------------------------------------------

    def reap_orphans(self):
        """A restart leaves in-flight rows with no subprocess behind them. Fail
        them loudly rather than re-running work we can't account for."""
        for status in ("imp_running", "qa_running"):
            for task in db.tasks_with_status(status):
                runner.note(task["id"], f"=== orphaned by factory restart in {status} ===")
                self.fail(task, f"Orphaned by a factory restart while in {status}.")

    def run_forever(self):
        self.reap_orphans()
        while True:
            try:
                self.tick()
            except Exception:
                traceback.print_exc()
            time.sleep(TICK)

    def tick(self):
        self.dispatch_queued()
        self.check_running()
        self.check_merged()

    # ---- stages ----------------------------------------------------------

    def dispatch_queued(self):
        for task in db.tasks_with_status("queued"):
            # claim() is atomic, so this row can only be picked up once.
            if not db.claim(task["id"], "queued", "imp_running"):
                continue
            try:
                worktree, branch, proc = runner.start_imp(task)
                db.set_fields(task["id"], worktree_path=worktree, branch=branch)
                self.running[task["id"]] = ("imp", proc)
            except Exception as e:
                runner.note(task["id"], f"=== failed to start IMP ===\n{traceback.format_exc()}")
                self.fail(db.get_task(task["id"]), f"Could not start IMP: {e}")

    def check_running(self):
        for task_id, (stage, proc) in list(self.running.items()):
            # Mirror the log file into the DB so the UI sees progress live.
            db.set_fields(task_id, last_log=runner.read_log(task_id))
            code = proc.poll()
            if code is None:
                continue
            del self.running[task_id]
            task = db.get_task(task_id)
            runner.note(task_id, f"=== {stage.upper()} exited with code {code} ===")
            try:
                if stage == "imp":
                    self.imp_finished(task, code)
                else:
                    self.qa_finished(task, code)
            except Exception as e:
                runner.note(task_id, traceback.format_exc())
                self.fail(db.get_task(task_id), f"{stage.upper()} handling blew up: {e}")
            db.set_fields(task_id, last_log=runner.read_log(task_id))

    def imp_finished(self, task, code):
        if code != 0:
            return self.fail(task, f"IMP exited {code}. See the task log.")
        if not runner.commit_work(task):
            return self.fail(task, "IMP exited cleanly but committed no changes.")
        runner.note(task["id"], "=== committed IMP's diff ===")
        if db.claim(task["id"], "imp_running", "qa_running"):
            self.running[task["id"]] = ("qa", runner.start_qa(db.get_task(task["id"])))

    def qa_finished(self, task, code):
        log = runner.read_log(task["id"])
        verdict = runner.parse_verdict(log)
        findings = runner.qa_findings(log)
        if verdict is None:
            return self.fail(task, f"QA produced no parseable VERDICT line (exit {code}).")
        if verdict == "fail":
            return self.fail(task, f"QA failed:\n{findings}")
        url = runner.open_pr(task, findings)
        db.set_fields(task["id"], pr_url=url)
        db.claim(task["id"], "qa_running", "pr_open")
        runner.note(task["id"], f"=== QA passed, PR opened: {url} ===")
        self.notify(task, f"QA passed. PR opened: {url}")

    def check_merged(self):
        """Close the loop: a merged PR means the task is done."""
        for task in db.tasks_with_status("pr_open"):
            if not task["pr_url"]:
                continue
            out = subprocess.run(
                ["gh", "pr", "view", task["pr_url"], "--json", "state"],
                cwd=runner.REPO, capture_output=True, text=True,
            )
            if out.returncode == 0 and '"MERGED"' in out.stdout:
                db.claim(task["id"], "pr_open", "done")

    # ---- failure ---------------------------------------------------------

    def fail(self, task, reason):
        db.set_fields(task["id"], status="failed", last_log=runner.read_log(task["id"]))
        runner.note(task["id"], f"=== FAILED: {reason} ===")
        self.notify(task, f"Task failed. {reason}")


def start(notify):
    """Run the pipeline in a background thread. Returns the Factory."""
    f = Factory(notify)
    threading.Thread(target=f.run_forever, daemon=True, name="factory").start()
    return f
