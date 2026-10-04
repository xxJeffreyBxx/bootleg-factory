# bootleg factory

A weekend agent runner. Slack message in, PR out.

    Slack message -> queued -> imp_running -> qa_running -> pr_open
                                   |              |
                                   +--> failed <--+

- **IMP**: `claude -p` in a fresh `git worktree`, writes code. The factory commits it.
- **QA**: a second, adversarial `claude -p` that reads the diff and emits `VERDICT: pass|fail`.
- **PR**: on pass, push the branch and `gh pr create`.
- **UI**: http://localhost:7777

## Run

    python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
    cp .env.example .env   # fill in your Slack tokens
    .venv/bin/python app.py
