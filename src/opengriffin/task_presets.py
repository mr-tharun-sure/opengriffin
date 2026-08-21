"""Autonomous task presets — one-call setup for common "bot works while
you don't" workflows, built on the Ambient Trigger Mesh (triggers.py).

Each preset is a parameterized template that compiles to an ordinary
trigger in triggers.json, so everything the mesh supports (enable/disable,
trigger_list, trigger_remove) works on presets too. The action prompts use
the SILENT contract from triggers.py: watchers reply the bare token
SILENT when there is nothing worth delivering, so quiet periods send no
messages.

Enable from Telegram by just asking the bot ("enable the morning digest
at 7:30") — the agent calls task_preset_enable — or from Python:

    from opengriffin import task_presets
    task_presets.enable("morning-digest", {"cron": "30 7 * * *"})

Restart the bot (or wait for the next boot) to register new schedules.
"""

from __future__ import annotations

import json
from typing import Annotated

from claude_agent_sdk import create_sdk_mcp_server, tool

from . import triggers as triggers_module

_SILENT_RULE = (
    "\n\nIf there is nothing new or noteworthy to report, reply with exactly "
    "SILENT (no other text) and nothing will be delivered."
)


def _morning_digest(p: dict) -> dict:
    topics = p.get("topics", "").strip()
    news = (
        f"3. Headlines: search the web for notable news on: {topics}. One line each, with links.\n"
        if topics
        else ""
    )
    return {
        "source": {"kind": "cron", "expr": p.get("cron", "0 7 * * *")},
        "predicate": "",
        "action": {
            "kind": "agent",
            "prompt": (
                "Compose my morning digest as a single compact Telegram message "
                "(under 3500 chars, plain text, use short bullet lines):\n"
                "1. Yesterday: read the tail of my journal "
                "(~/.opengriffin/memories/JOURNAL.md) and summarize what happened "
                "and what the nightly loops learned.\n"
                "2. Today: list my open kanban tasks (kanban tools), most "
                "important first.\n" + news + "Start with a one-line greeting. Always deliver this "
                "digest — never reply SILENT."
            ),
            "deliver_to": p.get("deliver_to", "home"),
        },
    }


def _github_watcher(p: dict) -> dict:
    repos = p.get("repos", "").strip()
    return {
        "source": {"kind": "cron", "expr": p.get("cron", "*/30 * * * *")},
        "predicate": "",
        "action": {
            "kind": "agent",
            "prompt": (
                f"Check these GitHub repos for activity since the last check "
                f"(~30 min ago): {repos or '(none configured — reply SILENT)'}.\n"
                "Use the GitHub API (https://api.github.com/repos/<owner>/<repo>/"
                "issues?since=..., /pulls, /actions/runs) or any GitHub tools you "
                "have. Report ONLY new items: opened issues/PRs, review comments, "
                "failed CI runs, merged PRs. One bullet per item with a link. "
                "Track what you already reported with trigger_state_get/"
                "trigger_state_set (trigger_id='preset-github-watcher', store "
                "reported item URLs) so you never repeat an item." + _SILENT_RULE
            ),
            "deliver_to": p.get("deliver_to", "home"),
        },
    }


def _web_monitor(p: dict) -> dict:
    url = p.get("url", "").strip()
    condition = p.get("condition", "").strip()
    return {
        "source": {
            "kind": "poll",
            "url": url,
            "interval_sec": int(p.get("interval_sec", 1800)),
        },
        # Optional LLM gate evaluated against the fetched payload, e.g.
        # "Is the price below $500?" — empty means always run the action.
        "predicate": condition,
        "action": {
            "kind": "agent",
            "prompt": (
                f"You are watching {url or '(no url configured — reply SILENT)'}. "
                "The fetched payload is attached. Compare it to the fingerprint "
                "stored via trigger_state_get (trigger_id='preset-web-monitor'), "
                "then store an updated short fingerprint with trigger_state_set. "
                "If something meaningful changed "
                "— content, price, availability, a new mention — describe the "
                "change in 2-4 lines with the link." + _SILENT_RULE
            ),
            "deliver_to": p.get("deliver_to", "home"),
        },
    }


def _inbox_triage(p: dict) -> dict:
    return {
        "source": {"kind": "cron", "expr": p.get("cron", "0 8,17 * * *")},
        "predicate": "",
        "action": {
            "kind": "agent",
            "prompt": (
                "Inbox triage sweep. Using whatever email tools/MCP servers are "
                "available to you, review unread mail since the last sweep:\n"
                "1. Group by urgency: needs-reply-today / can-wait / FYI-only.\n"
                "2. For each needs-reply item, include sender, one-line gist, and "
                "a suggested reply drafted in MY voice (see "
                "~/.opengriffin/memories/VOICE.md if present) — but do NOT send "
                "anything without my approval.\n"
                "3. Ignore newsletters and automated notifications unless one "
                "looks important.\n"
                "If no email tools are available, or there is no unread mail, "
                "reply SILENT." + _SILENT_RULE
            ),
            "deliver_to": p.get("deliver_to", "home"),
        },
    }


def _evening_review(p: dict) -> dict:
    return {
        "source": {"kind": "cron", "expr": p.get("cron", "0 21 * * *")},
        "predicate": "",
        "action": {
            "kind": "agent",
            "prompt": (
                "Compose my evening review as one compact Telegram message:\n"
                "1. Done today: infer from today's journal entries and any kanban "
                "tasks that moved to done.\n"
                "2. Still open: kanban tasks in progress or blocked, one line each.\n"
                "3. Tomorrow: propose the top 3 things to tackle, based on what's "
                "open and anything I said today about priorities.\n"
                "Keep it under 2500 chars. Always deliver — never reply SILENT."
            ),
            "deliver_to": p.get("deliver_to", "home"),
        },
    }


def _daily_standup(p: dict) -> dict:
    return {
        "source": {"kind": "cron", "expr": p.get("cron", "0 9 * * 1-5")},
        "predicate": "",
        "action": {
            "kind": "agent",
            "prompt": (
                "Send me my standup prompt. In one short message: remind me what "
                "I said I'd do (yesterday's journal + open kanban tasks, max 4 "
                "bullets), then ask me: what are your top priorities today, and "
                "is anything blocking you? My reply arrives as a normal chat "
                "message — when it does, save the priorities with the memory "
                "tools and update the kanban board accordingly. "
                "Always deliver — never reply SILENT."
            ),
            "deliver_to": p.get("deliver_to", "home"),
        },
    }


def _weekly_report(p: dict) -> dict:
    return {
        "source": {"kind": "cron", "expr": p.get("cron", "0 18 * * 0")},
        "predicate": "",
        "action": {
            "kind": "agent",
            "prompt": (
                "Compose my week-in-review. Read the last 7 days of my journal "
                "(~/.opengriffin/memories/JOURNAL.md) and usage stats, then write "
                "a single message: the week's wins, what the nightly loops "
                "learned about me, tasks completed vs carried over, and one "
                "suggestion for next week. End by reminding me I can run "
                "`griffin card` to turn this week's best journal entry into a "
                "shareable card. Always deliver — never reply SILENT."
            ),
            "deliver_to": p.get("deliver_to", "home"),
        },
    }


def _hn_mentions(p: dict) -> dict:
    from urllib.parse import quote

    keywords = p.get("keywords", "").strip()
    url = (
        "https://hn.algolia.com/api/v1/search_by_date?query="
        + quote(keywords)
        + "&tags=(story,comment)&hitsPerPage=20"
        if keywords
        else ""
    )
    return {
        "source": {
            "kind": "poll",
            "url": url,
            "interval_sec": int(p.get("interval_sec", 3600)),
        },
        "predicate": "",
        "action": {
            "kind": "agent",
            "prompt": (
                f"You are watching Hacker News for mentions of: "
                f"{keywords or '(no keywords configured — reply SILENT)'}. "
                "The attached payload is the latest Algolia search results. "
                "Report only hits you have NOT reported before (track reported "
                "objectIDs via trigger_state_get/trigger_state_set with "
                "trigger_id='preset-hn-mentions'): title/comment gist, points, "
                "and the news.ycombinator.com/item?id=<objectID> link. Skip "
                "false-positive matches that aren't really about the subject." + _SILENT_RULE
            ),
            "deliver_to": p.get("deliver_to", "home"),
        },
    }


def _rss_digest(p: dict) -> dict:
    feeds = p.get("feeds", "").strip()
    return {
        # The rss source fetches every feed, dedups items by guid in the
        # trigger state store, and only invokes the agent when something is
        # genuinely new — quiet checks cost zero tokens.
        "source": {
            "kind": "rss",
            "feeds": feeds,
            "interval_sec": int(p.get("interval_sec", 1800)),
        },
        "predicate": "",
        "action": {
            "kind": "agent",
            "prompt": (
                "New items appeared in my RSS feeds (attached as new_items). "
                "Summarize them as a compact digest: one bullet per item — "
                "title, one-line gist if you can infer it, link. Group by feed "
                "if there is more than one. Skip nothing; the source already "
                "filtered to unseen items only."
            ),
            "deliver_to": p.get("deliver_to", "home"),
        },
    }


def _file_dropbox(p: dict) -> dict:
    directory = p.get("dir", "~/.opengriffin/dropbox")
    return {
        # The file source polls the directory and only invokes the agent when
        # files were added or changed since the last check.
        "source": {
            "kind": "file",
            "dir": directory,
            "pattern": p.get("pattern", "*"),
            "interval_sec": int(p.get("interval_sec", 120)),
        },
        "predicate": "",
        "action": {
            "kind": "agent",
            "prompt": (
                f"New files landed in my dropbox folder ({directory}); paths are "
                "attached as new_files. For each: read it and act by type — "
                "summarize documents/PDFs, transcribe audio (voice tools), "
                "describe images, extract action items from meeting notes and "
                "add them to the kanban board. Reply with one section per file. "
                "Never delete or move the files."
            ),
            "deliver_to": p.get("deliver_to", "home"),
        },
    }


# name -> (description, default params, builder). Params not listed here are
# still passed through to the builder, so presets can grow options without
# schema churn.
PRESETS: dict = {
    "morning-digest": {
        "description": "Daily briefing: yesterday's journal, today's kanban, optional news topics.",
        "params": {"cron": "0 7 * * *", "topics": "", "deliver_to": "home"},
        "build": _morning_digest,
    },
    "github-watcher": {
        "description": "Watch GitHub repos for new issues/PRs/CI failures; quiet when nothing happened.",
        "params": {"cron": "*/30 * * * *", "repos": "", "deliver_to": "home"},
        "build": _github_watcher,
    },
    "web-monitor": {
        "description": "Poll a URL and report only meaningful changes (optional yes/no condition gate).",
        "params": {"url": "", "interval_sec": 1800, "condition": "", "deliver_to": "home"},
        "build": _web_monitor,
    },
    "inbox-triage": {
        "description": "Periodic email sweep with urgency grouping and reply drafts in your voice.",
        "params": {"cron": "0 8,17 * * *", "deliver_to": "home"},
        "build": _inbox_triage,
    },
    "evening-review": {
        "description": "End-of-day recap: what got done, what's open, proposed top 3 for tomorrow.",
        "params": {"cron": "0 21 * * *", "deliver_to": "home"},
        "build": _evening_review,
    },
    "daily-standup": {
        "description": "Weekday-morning standup prompt; your reply updates memory and the kanban board.",
        "params": {"cron": "0 9 * * 1-5", "deliver_to": "home"},
        "build": _daily_standup,
    },
    "weekly-report": {
        "description": "Sunday week-in-review from the journal, with a griffin card reminder.",
        "params": {"cron": "0 18 * * 0", "deliver_to": "home"},
        "build": _weekly_report,
    },
    "hn-mentions": {
        "description": "Watch Hacker News for keyword mentions (your project, brand, competitors).",
        "params": {"keywords": "", "interval_sec": 3600, "deliver_to": "home"},
        "build": _hn_mentions,
    },
    "rss-digest": {
        "description": "Digest of new items across RSS/Atom feeds; guid-deduplicated, zero cost when quiet.",
        "params": {"feeds": "", "interval_sec": 1800, "deliver_to": "home"},
        "build": _rss_digest,
    },
    "file-dropbox": {
        "description": "Watch a folder; new files get read and processed by type (summarize/transcribe/extract tasks).",
        "params": {
            "dir": "~/.opengriffin/dropbox",
            "pattern": "*",
            "interval_sec": 120,
            "deliver_to": "home",
        },
        "build": _file_dropbox,
    },
}


def build(name: str, params: dict | None = None) -> dict:
    """Compile a preset into a trigger dict (without persisting it)."""
    spec = PRESETS.get(name)
    if spec is None:
        raise KeyError(f"unknown preset: {name} (have: {', '.join(sorted(PRESETS))})")
    merged = {**spec["params"], **(params or {})}
    trigger = spec["build"](merged)
    trigger["id"] = merged.get("id") or f"preset-{name}"
    trigger["enabled"] = True
    trigger["preset"] = name
    return trigger


def enable(name: str, params: dict | None = None) -> dict:
    """Compile a preset and persist it into triggers.json (upsert by id)."""
    trigger = build(name, params)
    data = triggers_module._load()
    data["triggers"] = [t for t in data.get("triggers", []) if t.get("id") != trigger["id"]]
    data["triggers"].append(trigger)
    triggers_module._save(data)
    return trigger


# ----------------------------- agent-callable MCP tools -----------------------------


@tool(
    "task_preset_list",
    "List available autonomous task presets (morning digest, GitHub watcher, web monitor, inbox triage) with their parameters, plus which are currently enabled.",
    {},
)
async def _list(args: dict) -> dict:
    enabled_ids = {t.get("id") for t in triggers_module._load().get("triggers", [])}
    lines = []
    for name, spec in PRESETS.items():
        mark = "✓ enabled" if f"preset-{name}" in enabled_ids else "  off"
        lines.append(f"[{mark}] {name} — {spec['description']}")
        lines.append(f"         params: {json.dumps(spec['params'])}")
    lines.append("")
    lines.append("Enable with task_preset_enable; disable with trigger_remove(id='preset-<name>').")
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


@tool(
    "task_preset_enable",
    "Enable an autonomous task preset. The user describes what they want ('morning digest at 7:30 with AI news', 'watch my opengriffin repo') and the agent maps it to a preset name + params. Takes effect on next bot restart.",
    {
        "name": Annotated[
            str, "Preset name: morning-digest | github-watcher | web-monitor | inbox-triage"
        ],
        "params_json": Annotated[
            str | None,
            'JSON overrides for the preset\'s params, e.g. {"cron": "30 7 * * *", "topics": "AI agents, Claude"} or {"repos": "owner/repo1, owner/repo2"}',
        ],
    },
)
async def _enable(args: dict) -> dict:
    try:
        params = json.loads(args.get("params_json") or "{}")
    except Exception as e:
        return {
            "content": [{"type": "text", "text": f"params_json invalid JSON: {e}"}],
            "is_error": True,
        }
    try:
        trigger = enable(args["name"], params)
    except KeyError as e:
        return {"content": [{"type": "text", "text": str(e)}], "is_error": True}
    return {
        "content": [
            {
                "type": "text",
                "text": (
                    f"enabled {trigger['id']}\n{json.dumps(trigger, indent=2)[:1500]}\n\n"
                    "Restart the bot to register the schedule."
                ),
            }
        ]
    }


PRESETS_SERVER = create_sdk_mcp_server(
    name="task_presets",
    version="1.0.0",
    tools=[_list, _enable],
)
