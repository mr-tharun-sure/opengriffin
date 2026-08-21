# Autonomous task presets

Presets are one-call setups for common "the bot works while you don't"
workflows. Each compiles to an ordinary [Ambient Trigger Mesh](cron.md)
trigger in `~/.opengriffin/triggers.json`, so `trigger_list` /
`trigger_remove` and manual JSON editing all apply.

The easiest way to enable one is to just ask the bot in Telegram:

> enable the morning digest at 7:30 with news about AI agents
>
> watch ManasaEdavalli-TharunSure/opengriffin for new issues and CI failures

The agent maps your request to `task_preset_enable` with the right
parameters. Restart the bot to register new schedules.

## The presets

| Preset | Default schedule | What it does |
|---|---|---|
| `morning-digest` | 07:00 daily | One Telegram message: yesterday's journal highlights, today's kanban tasks, optional news topics. |
| `github-watcher` | every 30 min | New issues, PRs, review comments, and CI failures across your repos — remembers what it already told you. |
| `web-monitor` | every 30 min | Polls a URL; reports only when something meaningful changed, with an optional yes/no condition gate ("Is the price under $500?"). |
| `inbox-triage` | 08:00 + 17:00 | Sweeps unread mail via your configured email tools, groups by urgency, drafts replies in your voice — never sends without approval. |

### Parameters

Every preset accepts `deliver_to` (default `home`) and its own knobs:

- `morning-digest`: `cron`, `topics` (comma-separated news subjects)
- `github-watcher`: `cron`, `repos` (comma-separated `owner/repo`)
- `web-monitor`: `url`, `interval_sec`, `condition` (optional LLM yes/no gate)
- `inbox-triage`: `cron` (requires email tools/MCP configured; stays SILENT otherwise)

From Python:

```python
from opengriffin import task_presets
task_presets.enable("github-watcher", {"repos": "you/yourrepo", "cron": "*/20 * * * *"})
```

## The SILENT contract

Watcher prompts instruct the agent to reply with the bare token `SILENT`
when there is nothing worth telling you. `triggers.evaluate` drops those
replies instead of delivering them — quiet periods send no messages.
Write your own trigger prompts with the same rule to get the same
behavior.

## Disabling

Ask the bot ("turn off the github watcher"), or directly:
`trigger_remove(id="preset-github-watcher")`, or set `"enabled": false`
in `triggers.json`.
