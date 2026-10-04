"""bootleg factory: Slack in, PRs out.

    python app.py
"""

import os
import sys

from dotenv import load_dotenv

REQUIRED = ("SLACK_BOT_TOKEN", "SLACK_APP_TOKEN", "SLACK_CHANNEL_ID")


def main():
    load_dotenv()
    missing = [k for k in REQUIRED if not os.environ.get(k)]
    if missing:
        sys.exit(f"Missing {', '.join(missing)}. Copy .env.example to .env and fill it in.")

    import db, factory, slackbot, web

    db.connect()
    port = web.start(int(os.environ.get("PORT", 7777)) or None)
    print(f"[web]     http://localhost:{port}")

    notify, serve = slackbot.build()
    factory.start(notify)
    print("[factory] pipeline running")
    print(f"[slack]   listening on channel {os.environ['SLACK_CHANNEL_ID']}")
    serve()  # blocks


if __name__ == "__main__":
    main()
