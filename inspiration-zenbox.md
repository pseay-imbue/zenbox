---
title: Zenbox
description: A 3D zen-garden web view of your unread Slack messages, where each unread message is a potted plant that wilts with age.
thumbnail: inspiration-zenbox.svg
version: v1
format: v1
---

# Zenbox

This file is the manifest for the **Zenbox** inspiration (slug:
`zenbox`). It is the one document a future agent reads to understand,
present, and adapt this inspiration. If you are an agent in a mind that was
created from this inspiration, this file is your script: read all of it, then
follow "How to adapt it" below.

## What it is

A 3D zen-garden web view of your unread Slack messages, where each unread message is a potted plant that wilts with age.

Zenbox turns the anxiety of a cluttered Slack into something calm you actually
want to look at. Instead of a wall of red unread badges, it gives you a single
web page ("Unread Garden") that renders your unread Slack messages from the last
three days as a 3D zen garden: raked sand with a scattering of potted plants, one
plant per unread message. Fresh messages are healthy and green; as a message goes
unanswered it wilts -- yellowing after a few hours, drooping and brown after a day
-- so a glance tells you both how much is waiting and how stale it is. Hovering a
plant reveals the channel, sender, and message text; clicking opens that exact
message in Slack. The page refreshes about once a minute, and with no unreads in
the window it says "Your garden is at peace." It is a single-user, read-only
ambient view -- it never posts, marks things read, or changes anything in Slack;
it only reflects what is already there.

## How it works

The snapshot includes these paths (each is a repo-root-relative path copied
from the original mind onto a clean default-workspace-template base):

- `system/apps/slack_zen_garden`
- `system/supervisord.conf`
- `pyproject.toml`
- `uv.lock`

`system/apps/slack_zen_garden` is the whole app, a self-contained Python library.
Its `runner.py` is a small Flask service with three routes: `/` serves the
front-end, `/api/plants` returns the live unread data as JSON, and `/health` is a
liveness probe. `runner.py` reaches Slack exclusively by shelling out to `latchkey
curl` (the `slack()` helper), calling Slack web API methods `client.counts`,
`conversations.history`, `conversations.info`, `users.info`, and `auth.test`. It
finds conversations with unread messages, pulls recent history, filters to messages
newer than your last-read marker within a 72-hour window, resolves Slack markup to
readable text, buckets each message by age, builds a Slack permalink, and caps the
result (at most 15 plants per conversation, 60 total). The front-end
`system/apps/slack_zen_garden/src/slack_zen_garden/assets/index.html` is a single
self-contained page that loads three.js, renders the plants as a 3D garden, polls
`api/plants` every ~60s, and wires up hover tooltips and click-to-open-in-Slack.

At runtime it runs as the `[program:slack-zen-garden]` supervisord program in
`system/supervisord.conf`, which runs `python3 system/scripts/forward_port.py
--url http://localhost:8083 --name slack-zen-garden` (registering the
`slack-zen-garden` workspace tab) and then `uv run slack-zen-garden`. The app
serves at `/` (Flask via werkzeug `run_simple`) and the system_interface reverse
proxy handles the `/service/slack-zen-garden/` prefixing -- no `ROOT_PATH` is used
(unlike some apps). The listen port is 8083, overridable via the
`SLACK_ZEN_GARDEN_PORT` env var (the hardcoded default in `runner.py`'s `main()`).
`pyproject.toml` registers `slack-zen-garden` as a workspace dependency and source,
and `uv.lock` locks the resolution.

## Recipe

This inspiration is version `v1` (front-matter `version:`).
It is not a fork of the workspace it came from -- it is DERIVED from it by the
recipe below: include these paths, leave these out, apply these
published-version rules. An update re-runs the recipe against the current
workspace and publishes the result as the next version, so anything excluded
here stays excluded even though it still exists in the source workspace. This
block is the durable home of that recipe -- a later update reads it back from
here.

```yaml
version: v1
include:
  - system/apps/slack_zen_garden
  - system/supervisord.conf
  - pyproject.toml
  - uv.lock
data_include: []
exclude:
  []
modification_rules:
  []
```

## Prerequisites

Activation requirements: what the adopting agent must SET UP -- and must
INITIATE ITSELF during setup, before asking how to adapt -- for this
inspiration to run against the new user's own accounts/data. One line per
requirement, in this machine-readable form (greppable by `requires_`):

- requires_permission: slack-api / slack-read-all (user-approved; the adopting
  agent initiates this via a latchkey permission request during setup). This
  single read scope covers every Slack web API method the app calls --
  client.counts, conversations.history, conversations.info, users.info, and
  auth.test. Credentials are injected by latchkey at call time; nothing is
  stored in the repo.

There are no `requires_secret` lines: the app holds no API keys or token files
-- all Slack access flows through `latchkey curl`, which supplies the user's
session credentials at call time. There is no `requires_llm` line either: the
app calls no LLM.

## How to adapt it

Instructions for the NEXT agent -- the one adapting this inspiration into a
new mind. This is the `use-inspiration` skill's template path; in short:

1. Read this entire file first, especially "Prerequisites" and "Holes"
   below -- Prerequisites are your SETUP agenda, Holes are your ADAPTATION
   agenda.
2. Present the inspiration to the user in plain, non-technical language: what
   it is, what it does, and what it needs from them (name the Prerequisites).
3. Ask whether they want to use the same connectors (e.g. their own Slack).
   If YES: ACTIVATE FIRST -- initiate every `requires_permission` line NOW
   via a latchkey permission request (see the `latchkey` skill; the request
   opens the approval/login flow in the minds app), wire up any
   `requires_secret` values, start the services, and get the app showing
   THE USER'S OWN DATA. Done for a data-backed app means the user can open it
   and see their own data -- NOT that a service starts or an endpoint returns
   200. Then tell them it is live and to take a look.
4. Only AFTER that (or immediately, if they chose different connectors -- the
   swap is then the first adaptation) ask: "How do you want to adapt it?"
5. Work through each hole interactively, one at a time. Translate each into
   plain language, ask for a decision only when you genuinely need one, and
   resolve the obvious ones yourself.
6. When done, append a dated entry to "Adaptation history" below (never
   rewrite earlier entries) and commit.

## Holes

- Thread replies are not shown. The garden only includes top-level channel, DM,
  and group-DM messages (plus thread parents/broadcasts in history). Unread
  replies buried in threads are invisible; an adopter who lives in threads would
  extend `fetch_unread()` in `runner.py` to walk `conversations.replies`.
- The time window, age buckets, and caps are hardcoded module constants in
  `runner.py` (72h `WINDOW_HOURS`; green <3h, yellowing 3-24h, drooping/brown
  >24h in `bucket_for()`; `MAX_PLANTS = 60`, `MAX_PER_CONVERSATION = 15`). Tune
  them to how busy the new user's Slack is.
- Single-user only -- renders whichever Slack account latchkey is authenticated
  as; no account picker or multi-user support.
- The port defaults to 8083 (overridable via `SLACK_ZEN_GARDEN_PORT`, and set in
  the `[program:slack-zen-garden]` block / forward_port call); change it if it
  collides with another service.

## Publication history

This inspiration's changelog: what each published version changed. The PUBLISHER
appends one entry per version (newest last); earlier entries are never rewritten.
This is distinct from "Adaptation history" below, which is the ADOPTERS' log.

### v1 (2026-07-30) -- Republished Zenbox migrated onto the current workspace template (system/apps layout, port 8083, proxy-prefixed serving).

## Adaptation history

Each mind that adapts this inspiration appends one dated entry below. Earlier
entries are never rewritten.
