"""Worktrees, claude -p subprocesses, and PR creation.

Every agent invocation runs in its own `git worktree`, never in the main
checkout. Neither agent is allowed to run git: the factory does the one commit
and the one push itself, so there is no path to a destructive git operation.
"""

import os
import re
import subprocess
import textwrap

import prompts

REPO = os.path.dirname(os.path.abspath(__file__))
WORKTREES = os.path.join(REPO, "worktrees")
# Logs live outside the worktree so they never end up in a task's diff.
LOGS = os.path.join(REPO, "logs")
BASE_BRANCH = "main"

# IMP may read, write and run code to check its work, but git is denied outright.
IMP_TOOLS = ["Read", "Write", "Edit", "Glob", "Grep", "Bash(python3 *)", "Bash(pytest *)"]
# QA only looks. --restricted additionally strips the tools that execute code.
QA_TOOLS = ["Read", "Glob", "Grep"]

QA_BANNER = "=== QA starting (adversarial review) ==="

VERDICT_RE = re.compile(r"^VERDICT:\s*(pass|fail)\s*$", re.MULTILINE | re.IGNORECASE)


def git(*args, cwd=REPO):
    """Run git and return stdout. Raises on failure so we fail loudly."""
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True,
        capture_output=True, text=True,
    ).stdout


def log_path(task_id):
    return os.path.join(LOGS, f"task-{task_id}.log")


def note(task_id, text):
    """Append a factory-side line to the task's log. The agents' stdout and
    stderr land in this same file, so the log reads as one story."""
    path = log_path(task_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a") as f:
        f.write(text if text.endswith("\n") else text + "\n")


def read_log(task_id, tail=20000):
    try:
        with open(log_path(task_id)) as f:
            return f.read()[-tail:]
    except OSError:
        return ""


def make_worktree(task_id):
    """Create a fresh worktree + branch for this task. Returns (path, branch)."""
    branch = f"bootleg/task-{task_id}"
    path = os.path.join(WORKTREES, f"task-{task_id}")
    os.makedirs(WORKTREES, exist_ok=True)
    git("worktree", "add", "-b", branch, path, BASE_BRANCH)
    return path, branch


def spawn(task_id, worktree, prompt, tools, restricted=False):
    """Start a claude -p subprocess. stdout and stderr both stream to the task
    log, so nothing an agent says is swallowed."""
    path = log_path(task_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    out = open(path, "a", buffering=1)
    cmd = ["claude", "-p", prompt, "--permission-mode", "acceptEdits",
           "--allowedTools", *tools]
    if restricted:
        cmd.append("--restricted")
    return subprocess.Popen(
        cmd, cwd=worktree, stdout=out, stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL, text=True,
    )


def start_imp(task):
    worktree, branch = make_worktree(task["id"])
    note(task["id"], f"=== IMP starting in {worktree} on {branch} ===")
    prompt = prompts.IMP_PROMPT.format(task_text=task["text"])
    return worktree, branch, spawn(task["id"], worktree, prompt, IMP_TOOLS)


def commit_work(task):
    """Commit whatever IMP wrote. Returns True if there was anything to commit."""
    wt = task["worktree_path"]
    git("add", "-A", cwd=wt)
    if not git("diff", "--cached", "--stat", cwd=wt).strip():
        return False
    subject = textwrap.shorten(task["text"], 68, placeholder="...")
    git("commit", "-m", f"{subject}\n\nBuilt by bootleg-factory task {task['id']}.", cwd=wt)
    return True


def diff_of(task, limit=60000):
    """The diff IMP produced, relative to where the worktree branched from."""
    wt = task["worktree_path"]
    return git("diff", f"{BASE_BRANCH}...HEAD", cwd=wt)[:limit]


def start_qa(task):
    note(task["id"], QA_BANNER)
    prompt = prompts.QA_PROMPT.format(task_text=task["text"], diff=diff_of(task))
    return spawn(task["id"], task["worktree_path"], prompt, QA_TOOLS, restricted=True)


def parse_verdict(log_text):
    """Return 'pass', 'fail', or None. Only a literal VERDICT: line counts."""
    found = VERDICT_RE.findall(log_text)
    return found[-1].lower() if found else None


def qa_findings(log_text, limit=1500):
    """The QA output, minus the verdict line, for the PR body and Slack reply."""
    body = VERDICT_RE.sub("", log_text).strip()
    body = body.split(QA_BANNER)[-1].strip()
    return body[-limit:]


def open_pr(task, findings):
    """Push the task branch and open a PR. Returns the PR URL."""
    git("push", "-u", "origin", task["branch"])
    title = textwrap.shorten(task["text"], 68, placeholder="...")
    body = (
        f"Built by bootleg-factory task {task['id']}.\n\n"
        f"**Task**\n\n> {task['text']}\n\n"
        f"**Adversarial QA review** (verdict: pass)\n\n```\n{findings}\n```\n"
    )
    return subprocess.run(
        ["gh", "pr", "create", "--base", BASE_BRANCH, "--head", task["branch"],
         "--title", title, "--body", body],
        cwd=REPO, check=True, capture_output=True, text=True,
    ).stdout.strip().splitlines()[-1]


def open_prs():
    """Open PRs needing review, for the UI panel."""
    out = subprocess.run(
        ["gh", "pr", "list", "--state", "open", "--json",
         "number,title,url,headRefName"],
        cwd=REPO, capture_output=True, text=True,
    )
    return out.stdout if out.returncode == 0 else "[]"
