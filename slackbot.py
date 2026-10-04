"""Task ingestion. One message in the watched channel becomes one task."""

import os

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

import db

CHANNEL = os.environ.get("SLACK_CHANNEL_ID")


def build():
    """Return (notify, serve). `notify` posts into a task's thread; `serve`
    blocks running the Socket Mode client."""
    app = App(token=os.environ["SLACK_BOT_TOKEN"])

    @app.event("message")
    def on_message(event, logger):
        if event.get("channel") != CHANNEL:
            return
        # Ignore our own replies, edits/deletions, and anything inside a thread:
        # a thread is the conversation about a task, not a new task.
        if event.get("bot_id") or event.get("subtype"):
            return
        if event.get("thread_ts") and event["thread_ts"] != event["ts"]:
            return
        text = (event.get("text") or "").strip()
        if not text:
            return
        ts = event["ts"]
        task_id = db.add_task(text, event.get("user"), event["channel"], ts, ts)
        if task_id is None:
            return  # Slack redelivered an event we already have a task for.
        logger.info("queued task %s: %s", task_id, text[:60])
        app.client.chat_postMessage(
            channel=event["channel"], thread_ts=ts,
            text=f"Got it. Task `{task_id}` queued. I'll reply here when it lands.",
        )

    def notify(task, text):
        try:
            app.client.chat_postMessage(
                channel=task["slack_channel"], thread_ts=task["slack_thread"],
                text=f"Task `{task['id']}`: {text}",
            )
        except Exception as e:
            print(f"[slack] could not reply to task {task['id']}: {e}")

    def serve():
        SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"]).start()

    return notify, serve
