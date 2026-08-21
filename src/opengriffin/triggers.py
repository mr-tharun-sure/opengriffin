"""Ambient Trigger Mesh — composable signal → predicate → action DAG.

Triggers fire from any of:
  - cron expression (uses APScheduler, same as cron jobs)
  - webhook event arriving at /hooks/<route>
  - poll: any HTTP endpoint at an interval

A trigger has a chain:
  source -> predicate (LLM yes/no) -> action (skill, prompt, send_message)

When the predicate returns yes, the action runs. Visual editing later;
JSON config now.

Schema (triggers.json):
{
  "triggers": [
    {
      "id": "stripe-revenue-alert",
      "enabled": true,
      "source": {"kind": "webhook", "route": "stripe"},
      "predicate": "Did weekly revenue drop more than 10% week-over-week?",
      "action": {
        "kind": "agent",
        "prompt": "Investigate yesterday's Stripe data and draft a 3-paragraph postmortem.",
        "deliver_to": "home"
      }
    }
  ]
}
"""

from __future__ import annotations

import datetime as dt
import json
import logging
from typing import Annotated

from claude_agent_sdk import create_sdk_mcp_server, tool

from .paths import TRIGGER_STATE as STATE_FILE
from .paths import TRIGGERS as TRIGGERS_FILE

log = logging.getLogger("opengriffin.triggers")

# An agent action can reply with exactly this token to deliver nothing —
# the contract that lets periodic watchers stay quiet when nothing changed.
SILENT_TOKEN = "SILENT"


def _load() -> dict:
    if not TRIGGERS_FILE.is_file():
        return {"triggers": []}
    try:
        return json.loads(TRIGGERS_FILE.read_text())
    except Exception:
        return {"triggers": []}


def _save(data: dict) -> None:
    TRIGGERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    TRIGGERS_FILE.write_text(json.dumps(data, indent=2) + "\n")


# ----------------------------- per-trigger state -----------------------------
#
# Durable key/value scratch space keyed by trigger id — what a watcher uses to
# remember which items it already reported (RSS guids, HN objectIDs, file
# mtimes) so dedup survives restarts and doesn't depend on session memory.


def state_get(trigger_id: str) -> dict:
    if not STATE_FILE.is_file():
        return {}
    try:
        return json.loads(STATE_FILE.read_text()).get(trigger_id, {})
    except Exception:
        return {}


def state_set(trigger_id: str, state: dict) -> None:
    data = {}
    if STATE_FILE.is_file():
        try:
            data = json.loads(STATE_FILE.read_text())
        except Exception:
            data = {}
    data[trigger_id] = state
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(data, indent=2) + "\n")


# ----------------------------- evaluation -----------------------------


async def evaluate(trigger: dict, event_payload: dict | None = None) -> str | None:
    """Evaluate a trigger against an inbound event. Returns the agent's response,
    or None if the predicate did not fire.

    Predicate is evaluated by Claude with a strict yes/no contract.
    """
    from . import bot as bot_module  # noqa

    predicate = trigger.get("predicate", "").strip()
    if not predicate:
        # No predicate → fire unconditionally
        decision = "yes"
    else:
        # Ask Claude. Tight prompt.
        ctx = json.dumps(event_payload or {}, indent=2)[:2000]
        ask = (
            f"You are evaluating a trigger condition. Reply with EXACTLY 'yes' "
            f"or 'no', followed by a one-sentence reason. No other text.\n\n"
            f"Condition: {predicate}\n\n"
            f"Event payload:\n{ctx}\n"
        )
        try:
            reply = await bot_module.ask_claude_with_progress(0, ask, None, status_msg_id=None)
        except Exception as e:
            log.warning("predicate eval failed: %s", e)
            return None
        decision = (reply or "no").strip().lower()[:3]

    if not decision.startswith("yes"):
        return None

    # Execute the action
    from .botctx import CTX

    action = trigger.get("action") or {}
    kind = action.get("kind", "agent")
    if kind == "agent":
        prompt = action.get("prompt", "")
        if event_payload:
            prompt += "\n\nEvent payload:\n" + json.dumps(event_payload, indent=2)[:2000]
        try:
            result = await bot_module.ask_claude_with_progress(0, prompt, None, status_msg_id=None)
        except Exception as e:
            log.exception("trigger action failed")
            return f"action failed: {e}"
        # Deliver the result — without this, cron/poll agent triggers run
        # but their output never reaches the user.
        if result and result.strip().rstrip(".").upper() != SILENT_TOKEN:
            chat = action.get("deliver_to") or "home"
            if chat == "home":
                chat = CTX.home_chat_id
            if CTX.bot and chat:
                try:
                    await CTX.bot.send_message(chat_id=chat, text=result[:4000])
                except Exception:
                    log.exception("trigger %s delivery failed", trigger.get("id"))
        return result
    elif kind == "send":
        # Just send a message via the configured bot
        chat = action.get("deliver_to") or CTX.home_chat_id
        if chat == "home":
            chat = CTX.home_chat_id
        text = action.get("text", "trigger fired")
        if CTX.bot and chat:
            await CTX.bot.send_message(chat_id=chat, text=text)
        return "sent"
    else:
        log.warning("unknown action kind: %s", kind)
    return None


# ----------------------------- registration -----------------------------


def install_into_scheduler(scheduler) -> int:
    """For every trigger with source.kind == 'cron' or 'poll', register a job."""
    n = 0
    for t in _load().get("triggers", []):
        if not t.get("enabled", True):
            continue
        src = t.get("source") or {}
        if src.get("kind") == "cron":
            from apscheduler.triggers.cron import CronTrigger

            scheduler.add_job(
                _run_trigger,
                trigger=CronTrigger.from_crontab(src["expr"]),
                args=[t],
                id=f"trigger:{t['id']}",
                name=f"trigger:{t['id']}",
                replace_existing=True,
            )
            n += 1
        elif src.get("kind") == "poll":
            from apscheduler.triggers.interval import IntervalTrigger

            scheduler.add_job(
                _run_poll_trigger,
                trigger=IntervalTrigger(seconds=int(src.get("interval_sec", 300))),
                args=[t],
                id=f"trigger:{t['id']}",
                name=f"trigger:{t['id']}",
                replace_existing=True,
            )
            n += 1
        elif src.get("kind") == "rss":
            from apscheduler.triggers.interval import IntervalTrigger

            scheduler.add_job(
                _run_rss_trigger,
                trigger=IntervalTrigger(seconds=int(src.get("interval_sec", 1800))),
                args=[t],
                id=f"trigger:{t['id']}",
                name=f"trigger:{t['id']}",
                replace_existing=True,
            )
            n += 1
        elif src.get("kind") == "file":
            from apscheduler.triggers.interval import IntervalTrigger

            scheduler.add_job(
                _run_file_trigger,
                trigger=IntervalTrigger(seconds=int(src.get("interval_sec", 120))),
                args=[t],
                id=f"trigger:{t['id']}",
                name=f"trigger:{t['id']}",
                replace_existing=True,
            )
            n += 1
        elif src.get("kind") == "once":
            from apscheduler.triggers.date import DateTrigger

            when = dt.datetime.fromisoformat(src["at"])
            if when <= dt.datetime.now(when.tzinfo):
                continue  # already in the past; leave for cleanup
            scheduler.add_job(
                _run_once_trigger,
                trigger=DateTrigger(run_date=when),
                args=[t],
                id=f"trigger:{t['id']}",
                name=f"trigger:{t['id']}",
                replace_existing=True,
            )
            n += 1
    return n


async def _run_trigger(trigger: dict) -> None:
    log.info("Trigger %s firing (cron)", trigger.get("id"))
    await evaluate(
        trigger, event_payload={"fired_at": dt.datetime.now().isoformat(), "kind": "cron"}
    )


async def _run_poll_trigger(trigger: dict) -> None:
    """For poll triggers: fetch the URL, pass payload to predicate."""
    import aiohttp

    src = trigger.get("source") or {}
    url = src.get("url")
    if not url:
        return
    try:
        async with aiohttp.ClientSession() as sess, sess.get(url, timeout=15) as resp:
            payload = await resp.text()
            try:
                payload_obj = json.loads(payload)
            except Exception:
                payload_obj = {"text": payload[:2000]}
    except Exception as e:
        log.warning("poll fetch failed: %s", e)
        return
    await evaluate(trigger, event_payload={"kind": "poll", "url": url, "data": payload_obj})


def parse_feed(xml_text: str) -> list[dict]:
    """Minimal RSS 2.0 / Atom parser — enough for digests, no new dependency.

    Returns [{id, title, link, published}] with id falling back through
    guid → link → title.
    """
    import xml.etree.ElementTree as ET

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    items = []

    def _text(el, *names):
        for name in names:
            found = el.find(name)
            if found is not None and (found.text or "").strip():
                return found.text.strip()
        return ""

    # RSS 2.0: <rss><channel><item>
    for item in root.iter("item"):
        entry = {
            "title": _text(item, "title"),
            "link": _text(item, "link"),
            "published": _text(item, "pubDate"),
        }
        entry["id"] = _text(item, "guid") or entry["link"] or entry["title"]
        if entry["id"]:
            items.append(entry)
    # Atom: <feed><entry> (namespaced)
    ns = "{http://www.w3.org/2005/Atom}"
    for entry_el in root.iter(f"{ns}entry"):
        link_el = entry_el.find(f"{ns}link")
        entry = {
            "title": _text(entry_el, f"{ns}title"),
            "link": (link_el.get("href") if link_el is not None else "") or "",
            "published": _text(entry_el, f"{ns}published", f"{ns}updated"),
        }
        entry["id"] = _text(entry_el, f"{ns}id") or entry["link"] or entry["title"]
        if entry["id"]:
            items.append(entry)
    return items


async def _run_rss_trigger(trigger: dict) -> None:
    """Fetch every configured feed, diff against seen ids, and only invoke the
    agent when there are genuinely new items — zero LLM cost on quiet checks."""
    import aiohttp

    src = trigger.get("source") or {}
    feeds = [u.strip() for u in (src.get("feeds") or "").split(",") if u.strip()]
    if not feeds:
        return
    tid = trigger["id"]
    state = state_get(tid)
    seen: list[str] = list(state.get("seen_ids", []))
    new_items = []
    async with aiohttp.ClientSession() as sess:
        for url in feeds:
            try:
                async with sess.get(url, timeout=20) as resp:
                    text = await resp.text()
            except Exception as e:
                log.warning("rss fetch failed for %s: %s", url, e)
                continue
            for item in parse_feed(text):
                if item["id"] not in seen:
                    item["feed"] = url
                    new_items.append(item)
                    seen.append(item["id"])
    first_run = "seen_ids" not in state
    state["seen_ids"] = seen[-500:]  # bounded
    state_set(tid, state)
    if first_run:
        # Baseline pass: don't dump the entire feed history on the user.
        log.info("rss trigger %s baselined %d items", tid, len(new_items))
        return
    if new_items:
        await evaluate(trigger, event_payload={"kind": "rss", "new_items": new_items[:30]})


async def _run_file_trigger(trigger: dict) -> None:
    """Watch a directory for new/changed files and hand them to the agent."""
    from pathlib import Path

    src = trigger.get("source") or {}
    directory = Path(src.get("dir", "")).expanduser()
    if not directory.is_dir():
        return
    pattern = src.get("pattern", "*")
    tid = trigger["id"]
    state = state_get(tid)
    known: dict = state.get("files", {})
    current: dict = {}
    new_files = []
    for f in sorted(directory.glob(pattern)):
        if not f.is_file() or f.name.startswith("."):
            continue
        stamp = f"{int(f.stat().st_mtime)}:{f.stat().st_size}"
        current[str(f)] = stamp
        if known.get(str(f)) != stamp:
            new_files.append(str(f))
    first_run = "files" not in state
    state["files"] = current
    state_set(tid, state)
    if first_run or not new_files:
        return
    await evaluate(trigger, event_payload={"kind": "file", "new_files": new_files[:20]})


async def _run_once_trigger(trigger: dict) -> None:
    """Fire a one-shot trigger, then disable it so it never re-registers."""
    log.info("Trigger %s firing (once)", trigger.get("id"))
    try:
        await evaluate(
            trigger, event_payload={"fired_at": dt.datetime.now().isoformat(), "kind": "once"}
        )
    finally:
        data = _load()
        for t in data.get("triggers", []):
            if t.get("id") == trigger.get("id"):
                t["enabled"] = False
                t["fired_at"] = dt.datetime.now().isoformat(timespec="seconds")
        _save(data)


async def webhook_dispatch(route: str, payload: dict) -> list[str]:
    """Called by the webhook handler when an event arrives. Fires all
    triggers whose source.kind == 'webhook' and source.route matches.
    """
    fired = []
    for t in _load().get("triggers", []):
        if not t.get("enabled", True):
            continue
        src = t.get("source") or {}
        if src.get("kind") == "webhook" and src.get("route") == route:
            result = await evaluate(t, event_payload=payload)
            if result:
                fired.append(t["id"])
    return fired


# ----------------------------- agent-callable MCP tools -----------------------------


@tool(
    "trigger_create",
    "Create an ambient trigger that fires from cron, webhook, or poll. The agent uses this when the user describes a 'when X happens, do Y' workflow. Source kinds: cron (with expr), webhook (with route), poll (with url + interval_sec).",
    {
        "id": Annotated[str, "Unique trigger id (kebab-case)"],
        "source_kind": Annotated[str, "cron | webhook | poll"],
        "source_config": Annotated[
            str,
            "JSON config for the source. cron: {expr: '0 9 * * *'}. webhook: {route: 'stripe'}. poll: {url: '...', interval_sec: 300}",
        ],
        "predicate": Annotated[
            str | None, "Optional yes/no question evaluated by Claude before action fires"
        ],
        "action_kind": Annotated[str, "agent | send"],
        "action_prompt": Annotated[str | None, "Prompt text for action_kind=agent"],
        "deliver_to": Annotated[str | None, "Chat id to deliver result; 'home' for default"],
    },
)
async def _create(args: dict) -> dict:
    try:
        source_cfg = json.loads(args.get("source_config") or "{}")
    except Exception as e:
        return {
            "content": [{"type": "text", "text": f"source_config invalid JSON: {e}"}],
            "is_error": True,
        }
    trigger = {
        "id": args["id"],
        "enabled": True,
        "source": {"kind": args["source_kind"], **source_cfg},
        "predicate": args.get("predicate", ""),
        "action": {
            "kind": args["action_kind"],
            "prompt": args.get("action_prompt", ""),
            "deliver_to": args.get("deliver_to", "home"),
        },
    }
    data = _load()
    data["triggers"] = [t for t in data["triggers"] if t["id"] != args["id"]]
    data["triggers"].append(trigger)
    _save(data)
    return {
        "content": [
            {"type": "text", "text": f"created trigger {args['id']} (restart bot to register)"}
        ]
    }


@tool(
    "trigger_list",
    "List all configured ambient triggers.",
    {},
)
async def _list(args: dict) -> dict:
    items = _load().get("triggers", [])
    if not items:
        return {"content": [{"type": "text", "text": "(no triggers)"}]}
    lines = []
    for t in items:
        src = t.get("source", {})
        on_off = "✓" if t.get("enabled", True) else "✗"
        lines.append(
            f"{on_off} {t['id']} — {src.get('kind')}({src.get('expr') or src.get('route') or src.get('url')})"
        )
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


@tool(
    "trigger_remove",
    "Delete an ambient trigger by id.",
    {"id": Annotated[str, "Trigger id"]},
)
async def _remove(args: dict) -> dict:
    data = _load()
    before = len(data["triggers"])
    data["triggers"] = [t for t in data["triggers"] if t["id"] != args["id"]]
    if before == len(data["triggers"]):
        return {
            "content": [{"type": "text", "text": f"no such trigger: {args['id']}"}],
            "is_error": True,
        }
    _save(data)
    return {"content": [{"type": "text", "text": f"removed {args['id']}"}]}


@tool(
    "remind_me",
    "Set a one-shot reminder. Use when the user says 'remind me <when> to <thing>'. The reminder fires once at the given time and then disables itself. mode='send' delivers the text verbatim; mode='agent' runs the text as an agent prompt at fire time (for reminders that need fresh context, e.g. 'remind me Friday to follow up on whatever issues are still open').",
    {
        "when_iso": Annotated[
            str, "Fire time as ISO datetime in the server's local time, e.g. 2026-08-22T17:00:00"
        ],
        "text": Annotated[str, "Reminder text (mode=send) or agent prompt (mode=agent)"],
        "mode": Annotated[str | None, "send (default) | agent"],
        "deliver_to": Annotated[str | None, "Chat id; 'home' default"],
    },
)
async def _remind(args: dict) -> dict:
    try:
        when = dt.datetime.fromisoformat(args["when_iso"])
    except ValueError as e:
        return {"content": [{"type": "text", "text": f"bad when_iso: {e}"}], "is_error": True}
    if when <= dt.datetime.now(when.tzinfo):
        return {"content": [{"type": "text", "text": "when_iso is in the past"}], "is_error": True}
    mode = (args.get("mode") or "send").strip()
    tid = "remind-" + when.strftime("%Y%m%d-%H%M%S")
    action: dict = {"deliver_to": args.get("deliver_to") or "home"}
    if mode == "agent":
        action.update({"kind": "agent", "prompt": args["text"]})
    else:
        action.update({"kind": "send", "text": f"⏰ Reminder: {args['text']}"})
    trigger = {
        "id": tid,
        "enabled": True,
        "source": {"kind": "once", "at": when.isoformat()},
        "predicate": "",
        "action": action,
    }
    data = _load()
    data["triggers"] = [t for t in data.get("triggers", []) if t.get("id") != tid]
    data["triggers"].append(trigger)
    _save(data)
    return {
        "content": [
            {
                "type": "text",
                "text": f"reminder {tid} set for {when.isoformat()} (registers on next bot restart if the scheduler is not running)",
            }
        ]
    }


@tool(
    "trigger_state_get",
    "Read the durable per-trigger state store (survives restarts). Watcher prompts use this to recall which items were already reported.",
    {"trigger_id": Annotated[str, "Trigger id, e.g. preset-github-watcher"]},
)
async def _state_get(args: dict) -> dict:
    return {
        "content": [{"type": "text", "text": json.dumps(state_get(args["trigger_id"]), indent=2)}]
    }


@tool(
    "trigger_state_set",
    "Write the durable per-trigger state store. Pass the FULL state object as JSON — it replaces what was stored.",
    {
        "trigger_id": Annotated[str, "Trigger id"],
        "state_json": Annotated[str, "JSON object to store"],
    },
)
async def _state_set(args: dict) -> dict:
    try:
        state = json.loads(args["state_json"])
        assert isinstance(state, dict)
    except Exception as e:
        return {
            "content": [{"type": "text", "text": f"state_json must be a JSON object: {e}"}],
            "is_error": True,
        }
    state_set(args["trigger_id"], state)
    return {"content": [{"type": "text", "text": f"state saved for {args['trigger_id']}"}]}


TRIGGERS_SERVER = create_sdk_mcp_server(
    name="triggers",
    version="1.0.0",
    tools=[_create, _list, _remove, _remind, _state_get, _state_set],
)
