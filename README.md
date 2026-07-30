# Zenbox

A 3D zen-garden web view of your unread Slack messages, where each unread
message is a potted plant that wilts with age.

Zenbox turns the anxiety of a cluttered Slack into something calm you actually
want to look at. Instead of a wall of red unread badges, it gives you a single
web page — the **Unread Garden** — that renders your unread Slack messages from
the last three days as a 3D zen garden: raked sand with a scattering of potted
plants, one plant per unread message.

## What it is

Fresh messages are healthy and green; as a message goes unanswered it wilts —
yellowing after a few hours, drooping and brown after a day — so a single glance
tells you both how much is waiting and how stale it has become. Hover a plant to
read the channel, sender, and message text; click it to open that exact message
in Slack and act on it. The page refreshes itself about once a minute, and when
you have no unreads in the window it simply says **"Your garden is at peace."**

It is a single-user, **read-only** ambient view — it never posts, marks things
read, or changes anything in your Slack. It only reflects what is already there.

## How it works

`system/apps/slack_zen_garden` is the whole application — a self-contained Flask
service with no database.

- `src/slack_zen_garden/runner.py` — a small Flask app with three routes: `/`
  serves the front-end, `/api/plants` returns the live unread data as JSON, and
  `/health` is a liveness probe. It reaches Slack exclusively by shelling out to
  `latchkey curl` (the `slack()` helper), calling `client.counts`,
  `conversations.history`, `conversations.info`, `users.info`, and `auth.test`.
  It filters to messages newer than your last-read marker within a 72-hour
  window, resolves Slack markup to readable text, buckets each message by age,
  and builds a Slack permalink for each one.
- `src/slack_zen_garden/assets/index.html` — a single self-contained page that
  loads three.js, renders the plants as a 3D garden, polls `api/plants` every
  ~60 seconds, and wires up hover tooltips and click-to-open-in-Slack.

It runs as a workspace service (the `[program:slack-zen-garden]` block in
`system/supervisord.conf`), serving at `/service/slack-zen-garden/` through the
workspace proxy on port `8083` (overridable via `SLACK_ZEN_GARDEN_PORT`). All
Slack access flows through `latchkey curl`, so there are **no API keys or token
files in the repo**.

## Adapting this

This repository is a [Minds](https://imbue.com) **inspiration** — a bootable
snapshot you can create a new mind from, not just read. Once adopted, an agent
follows [`inspiration-zenbox.md`](inspiration-zenbox.md) to present and adapt it.

- **Connect your Slack.** Zenbox needs read access to your unread messages — the
  adopting agent requests the `slack-read-all` permission during setup, which
  covers every Slack method it calls. Nothing is stored; credentials are injected
  at call time by latchkey.
- **Tune the window, buckets, and caps.** The 72-hour window, the green/yellow/
  brown age thresholds, and the plant caps (60 total, 15 per conversation) are
  module constants in `runner.py` — adjust them to how busy your Slack is.
- **Thread replies are not shown** — only top-level channel, DM, and group-DM
  messages. Extend `fetch_unread()` to walk `conversations.replies` if you live
  in threads.
- **Single-user, no auth**, and the port (`8083`) is set in `runner.py` and the
  supervisord wiring — add authentication and change the port if you expose it
  beyond a private workspace.
