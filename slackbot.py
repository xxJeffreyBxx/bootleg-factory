"""Task ingestion. One new message in the watched channel becomes one task.

We poll `conversations.history` rather than using Socket Mode: polling needs
only the bot token, and a 3-second loop is plenty for a weekend factory.
Re-ingestion is harmless anyway — slack_ts is unique in the tasks table.
"""

import os
import time
import traceback

from slack_sdk import WebClient

import db

POLL = 3.0  # seconds between history checks


def is_task(message):
    """A task is a human's own top-level message. Everything else is noise:
    bot chatter, edits and joins, and replies inside a task's own thread."""
    if message.get("bot_id") or message.get("subtype") or not message.get("user"):
        return False
    if message.get("thread_ts") and message["thread_ts"] != message["ts"]:
        return False
    return bool((message.get("text") or "").strip())


def build():
    """Return (notify, serve). `notify` posts into a task's thread; `serve`
    blocks, polling the channel for new tasks."""
    client = WebClient(token=os.environ["SLACK_BOT_TOKEN"])
    channel = os.environ["SLACK_CHANNEL_ID"]
    who = client.auth_test()  # fail loudly now rather than mid-poll
    print(f"[slack]   authed as {who['user']} in {who['team']}")

    def notify(task, text):
        if not task["slack_channel"]:
            return  # made in the web UI; there's no thread to reply in
        try:
            client.chat_postMessage(
                channel=task["slack_channel"], thread_ts=task["slack_thread"],
                text=f"Task `{task['id']}`: {text}",
            )
        except Exception as e:
            print(f"[slack] could not reply to task {task['id']}: {e}")

    def ingest(since):
        """One pass over anything newer than `since`. Returns the new high mark."""
        resp = client.conversations_history(
            channel=channel, oldest=str(since), limit=50)
        for m in reversed(resp["messages"]):  # oldest first, so ids follow time
            since = max(since, float(m["ts"]))
            if not is_task(m):
                continue
            task_id = db.add_task(m["text"].strip(), m["user"], channel,
                                  m["ts"], m["ts"])
            if task_id is None:
                continue  # already a task; we've seen this message before
            print(f"[slack]   queued task {task_id}: {m['text'][:60]}")
            client.chat_postMessage(
                channel=channel, thread_ts=m["ts"],
                text=f"Got it. Task `{task_id}` queued. I'll reply here when it lands.",
            )
        return since

    def serve():
        since = time.time()  # ignore history from before we started
        while True:
            try:
                since = ingest(since)
            except Exception:
                traceback.print_exc()
            time.sleep(POLL)

    return notify, serve
