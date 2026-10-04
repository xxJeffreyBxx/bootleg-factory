# bootleg factory

A weekend agent runner. Slack message in, PR out.

    Slack message -> queued -> imp_running -> qa_running -> pr_open
                                   |              |
                                   +--> failed <--+

- **IMP**: `claude -p` in a fresh `git worktree`, writes code. The factory commits it.
- **QA**: a second, adversarial `claude -p` that reads the diff and emits `VERDICT: pass|fail`.
- **PR**: on pass, push the branch and `gh pr create`.
- **UI**: http://localhost:7777

## Prerequisites

- **`claude`** on your PATH and logged in. Both agents are `claude -p` subprocesses.
- **`gh`** installed and authenticated (`gh auth status`). Used to open and list PRs.
- **This directory must be a git repo with an `origin` remote.** Tasks branch off
  `main` here and their PRs open against this repo. To point the factory at a
  different repo, change `REPO` and `BASE_BRANCH` in `runner.py`.
- Python 3.9+ should do; developed and tested on 3.14.

## Run

    python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
    cp .env.example .env   # fill in SLACK_BOT_TOKEN and SLACK_CHANNEL_ID
    .venv/bin/python app.py

Then open http://localhost:7777 and post a message in your task channel.
`PORT` defaults to 7777 and steps up if that port is taken.

## Where things land

| path | what | committed? |
|---|---|---|
| `tasks.db` | all task state; `sqlite3 tasks.db "select id, status, pr_url from tasks"` | no, gitignored |
| `logs/task-<id>.log` | full IMP + QA output for a task, stdout and stderr | no, gitignored |
| `worktrees/task-<id>/` | the scratch worktree that task ran in, kept after the run | no, gitignored |
| `.env` | your Slack token | no, gitignored |

Worktrees are deliberately left in place so you can inspect what an agent did.
Clean up a finished one with `git worktree remove worktrees/task-<id>`.

## Slack app setup (one time)

Ingestion polls `conversations.history`, so you only need a bot token.

1. api.slack.com/apps -> your app -> **OAuth & Permissions** -> bot scopes
   `channels:history` and `chat:write`. Install to workspace.
2. Copy the bot token (`xoxb-...`) into `SLACK_BOT_TOKEN`.
3. Create a dedicated channel, `/invite` the bot, and put that channel's ID in
   `SLACK_CHANNEL_ID`. Use a channel of its own: every new top-level human
   message in it becomes a task.

## Layout

| file | job |
|---|---|
| `app.py` | entrypoint: checks env, starts web + pipeline + Slack |
| `slackbot.py` | ingestion: polls the channel, one message becomes one task |
| `db.py` | SQLite state, atomic status claims |
| `factory.py` | the poll loop that advances tasks through the pipeline |
| `runner.py` | worktrees, `claude -p` subprocesses, verdict parsing, `gh pr create` |
| `prompts.py` | the IMP and adversarial QA prompts |
| `web.py` + `static/index.html` | the status UI |
