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
                "Remember what you have already reported (memory tools) so you "
                "never repeat an item." + _SILENT_RULE
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
                "The fetched payload is attached. Compare it to what you remember "
                "from previous checks (memory tools; store a short fingerprint of "
                "the current state for next time). If something meaningful changed "
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
