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

## Slack app setup (one time)

At api.slack.com/apps -> Create New App -> From scratch:

1. **Socket Mode** -> enable. Generate an app-level token with
   `connections:write`. That is your `SLACK_APP_TOKEN` (`xapp-1-...`).
2. **OAuth & Permissions** -> bot token scopes: `channels:history`, `chat:write`.
3. **Event Subscriptions** -> enable, subscribe to bot event `message.channels`.
4. **Install to Workspace** -> copy the bot token (`xoxb-...`) into
   `SLACK_BOT_TOKEN`.
5. Invite the bot to your channel (`/invite @yourbot`) and put that channel's
   ID in `SLACK_CHANNEL_ID`.

## Layout

| file | job |
|---|---|
| `app.py` | entrypoint: checks env, starts web + pipeline + Slack |
| `slackbot.py` | ingestion: one channel message becomes one task |
| `db.py` | SQLite state, atomic status claims |
| `factory.py` | the poll loop that advances tasks through the pipeline |
| `runner.py` | worktrees, `claude -p` subprocesses, verdict parsing, `gh pr create` |
| `prompts.py` | the IMP and adversarial QA prompts |
| `web.py` + `static/index.html` | the status UI |
