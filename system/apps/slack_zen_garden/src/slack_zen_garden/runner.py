"""3D zen garden view of unread Slack messages as aging potted plants.

`/api/plants` fetches the user's live unread messages (channels, DMs, and group DMs)
from the last 72 hours via the Slack web API (through the latchkey credential
gateway) and maps each to a plant bucketed by age. The frontend renders them as a
zen garden. Slack markup in message text is resolved to readable text; a permalink
to open each message in Slack is preserved as the link back to the source record.

Note: unread *thread replies* are not included yet -- only top-level channel/DM/group
messages (and thread parents / broadcasts that appear in conversation history).
"""

import html
import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any

from flask import Flask
from flask import Response
from werkzeug.serving import run_simple

app = Flask("slack_zen_garden", static_folder=None)

ASSETS = Path(__file__).parent / "assets"

WINDOW_HOURS = 72
WINDOW_SECONDS = WINDOW_HOURS * 3600
# Slack's conversations.history is unreliable when passed an `oldest` cursor -- it
# intermittently returns an empty set for the same call. So we fetch a fixed page of
# recent messages and filter to the unread window client-side, which is stable.
HISTORY_PAGE = 100
MAX_PER_CONVERSATION = 15  # cap plants contributed by any one conversation
MAX_PLANTS = 60  # cap total plants so the 3D scene stays legible
# System message subtypes that are not real messages a person would want as a plant.
SKIP_SUBTYPES = frozenset(
    {"channel_join", "channel_leave", "group_join", "group_leave", "channel_archive", "channel_unarchive"}
)

# Long-lived caches (the service is a long-running process; these persist across requests).
_user_names: dict[str, str] = {}
_channel_names: dict[str, str] = {}
_team_url: str | None = None

_MENTION = re.compile(r"<@(U[A-Z0-9]+)>")
_LINK = re.compile(r"<(https?://[^|>]+)(?:\|([^>]+))?>")
_CHANNEL_REF = re.compile(r"<#C[A-Z0-9]+\|([^>]+)>")
_SPECIAL = re.compile(r"<!(channel|here|everyone)>")
_SUBTEAM = re.compile(r"<!subteam\^[A-Z0-9]+(?:\|([^>]+))?>")


class SlackError(Exception):
    """A Slack API call failed (transport error or an `ok: false` response)."""


def slack(method: str, params: dict[str, str] | None = None) -> dict[str, Any]:
    url = f"https://slack.com/api/{method}"
    if params:
        query = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{url}?{query}"
    proc = subprocess.run(
        ["latchkey", "curl", "-s", "-X", "POST", url],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise SlackError(f"latchkey curl failed for {method}: {proc.stderr.strip() or proc.returncode}")
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise SlackError(f"non-JSON response for {method}: {proc.stdout[:200]!r}") from exc
    if not data.get("ok"):
        raise SlackError(f"Slack API error for {method}: {data.get('error', 'unknown')}")
    return data


def team_url() -> str:
    global _team_url
    if _team_url is None:
        info = slack("auth.test")
        url = info["url"]
        _team_url = url if url.endswith("/") else url + "/"
    return _team_url


def resolve_user(uid: str) -> str:
    if not uid:
        return "Unknown"
    if uid not in _user_names:
        try:
            info = slack("users.info", {"user": uid})
        except SlackError:
            return uid
        prof = (info.get("user") or {}).get("profile") or {}
        _user_names[uid] = (
            prof.get("display_name") or prof.get("real_name") or (info.get("user") or {}).get("name") or uid
        )
    return _user_names[uid]


def resolve_channel(cid: str, kind: str) -> str:
    if cid not in _channel_names:
        try:
            info = slack("conversations.info", {"channel": cid})
        except SlackError:
            return cid
        ch = info.get("channel") or {}
        if kind == "im":
            _channel_names[cid] = "DM: " + resolve_user(ch.get("user", ""))
        elif ch.get("name"):
            _channel_names[cid] = "#" + ch["name"]
        else:
            _channel_names[cid] = ch.get("name_normalized") or ("Group DM" if kind == "mpim" else cid)
    return _channel_names[cid]


def clean_text(text: str) -> str:
    """Resolve Slack markup into readable text: @mentions, links, channel refs, specials."""
    text = _MENTION.sub(lambda m: "@" + resolve_user(m.group(1)), text)
    text = _CHANNEL_REF.sub(lambda m: "#" + m.group(1), text)
    text = _SPECIAL.sub(lambda m: "@" + m.group(1), text)
    text = _SUBTEAM.sub(lambda m: m.group(1) or "@group", text)
    text = _LINK.sub(lambda m: m.group(2) or m.group(1), text)
    return html.unescape(text).strip()


def bucket_for(age_seconds: float) -> str:
    if age_seconds > 24 * 3600:
        return "dying"
    if age_seconds > 3 * 3600:
        return "yellowing"
    return "green"


def permalink_for(channel_id: str, ts: str) -> str:
    return f"{team_url()}archives/{channel_id}/p{ts.replace('.', '')}"


def _unread_conversations(counts: dict[str, Any]) -> list[dict[str, Any]]:
    convos: list[dict[str, Any]] = []
    for kind, key in (("channel", "channels"), ("im", "ims"), ("mpim", "mpims")):
        for c in counts.get(key, []):
            if c.get("has_unreads") and c.get("last_read"):
                convos.append({"id": c["id"], "kind": kind, "last_read": c["last_read"]})
    return convos


def fetch_unread() -> dict[str, Any]:
    now = time.time()
    window_start = now - WINDOW_SECONDS
    counts = slack("client.counts", {"thread_counts_by_channel": "true"})
    convos = _unread_conversations(counts)

    plants: list[dict[str, Any]] = []
    truncated = False
    for convo in convos:
        last_read = float(convo["last_read"])
        try:
            hist = slack("conversations.history", {"channel": convo["id"], "limit": str(HISTORY_PAGE)})
        except SlackError:
            continue
        # Messages come newest-first; keep those unread (newer than last_read) and within the window.
        chan_name = None
        contributed = 0
        for m in hist.get("messages", []):
            if m.get("type") != "message" or not m.get("text"):
                continue
            if m.get("subtype") in SKIP_SUBTYPES:
                continue
            ts = float(m["ts"])
            if ts <= last_read or ts < window_start:
                continue
            if chan_name is None:
                chan_name = resolve_channel(convo["id"], convo["kind"])
            age_s = now - ts
            sender = resolve_user(m.get("user", "")) if m.get("user") else (m.get("username") or "Bot")
            plants.append(
                {
                    "id": m["ts"],
                    "channel": chan_name,
                    "sender": sender,
                    "text": clean_text(m["text"]),
                    "age_hours": round(age_s / 3600, 1),
                    "bucket": bucket_for(age_s),
                    "permalink": permalink_for(convo["id"], m["ts"]),
                }
            )
            contributed += 1
            if len(plants) >= MAX_PLANTS:
                truncated = True
                break
            if contributed >= MAX_PER_CONVERSATION:
                break
        if truncated:
            break

    plants.sort(key=lambda p: p["id"], reverse=True)
    return {
        "generated_at": now,
        "window_hours": WINDOW_HOURS,
        "unread_count": len(plants),
        "truncated": truncated,
        "is_sample": False,
        "plants": plants,
    }


@app.route("/")
def index() -> Response:
    return Response((ASSETS / "index.html").read_text(), mimetype="text/html")


@app.route("/api/plants")
def plants() -> Response:
    try:
        data = fetch_unread()
    except SlackError as exc:
        return Response(json.dumps({"error": str(exc)}), status=502, mimetype="application/json")
    return Response(json.dumps(data), mimetype="application/json")


@app.route("/health")
def health() -> Response:
    return Response('{"status": "ok"}', mimetype="application/json")


PORT = int(os.environ.get("SLACK_ZEN_GARDEN_PORT", "8083"))


def main() -> None:
    run_simple("127.0.0.1", PORT, app, threaded=True, use_reloader=False, use_debugger=False)


if __name__ == "__main__":
    main()
