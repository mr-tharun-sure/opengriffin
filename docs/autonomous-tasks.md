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
| `evening-review` | 21:00 daily | End-of-day recap: what got done, what's still open, proposed top 3 for tomorrow. |
| `daily-standup` | 09:00 weekdays | Sends your standup prompt; when you reply, the agent saves priorities to memory and updates the kanban board. |
| `weekly-report` | Sunday 18:00 | Week-in-review from the journal + usage stats, with a `griffin card` reminder. |
| `hn-mentions` | hourly poll | Watches Hacker News (Algolia API) for keyword mentions — your project, brand, competitors — deduplicated across checks. |
| `rss-digest` | every 30 min | New items across your RSS/Atom feeds, deduplicated by guid in the trigger state store. Quiet checks never invoke the model. |
| `file-dropbox` | every 2 min | Watch `~/.opengriffin/dropbox`; new files are read and processed by type — summarize documents, transcribe audio, extract action items to kanban. |

### Parameters

Every preset accepts `deliver_to` (default `home`) and its own knobs:

- `morning-digest`: `cron`, `topics` (comma-separated news subjects)
- `github-watcher`: `cron`, `repos` (comma-separated `owner/repo`)
- `web-monitor`: `url`, `interval_sec`, `condition` (optional LLM yes/no gate)
- `inbox-triage`: `cron` (requires email tools/MCP configured; stays SILENT otherwise)
- `evening-review`, `daily-standup`, `weekly-report`: `cron`
- `hn-mentions`: `keywords` (comma-separated search terms), `interval_sec`
- `rss-digest`: `feeds` (comma-separated feed URLs), `interval_sec`
- `file-dropbox`: `dir`, `pattern` (glob), `interval_sec`

From Python:

```python
from opengriffin import task_presets
task_presets.enable("github-watcher", {"repos": "you/yourrepo", "cron": "*/20 * * * *"})
```

## One-shot reminders

"remind me Friday at 5pm to submit the report" → the agent calls the
`remind_me` tool, which creates a `once` trigger that fires at that time
and then disables itself. `mode=agent` reminders run a full agent prompt
at fire time instead of sending fixed text ("remind me Friday to follow
up on whatever issues are still open").

## Trigger sources

Beyond the original `cron` / `webhook` / `poll`, triggers now support:

- `once` — fire at an ISO datetime, then self-disable (used by `remind_me`)
- `rss` — fetch comma-separated feeds, dedup items by guid in the state
  store, and only invoke the agent when something is genuinely new
- `file` — watch a directory glob; fires with the list of new/changed files

## The trigger state store

`~/.opengriffin/trigger_state.json` is durable per-trigger scratch space,
readable/writable by the agent via `trigger_state_get` /
`trigger_state_set`. The `rss` and `file` sources maintain their dedup
state there automatically; watcher prompts (GitHub, HN) use it to
remember what they already reported, so dedup survives bot restarts and
the daily session reset.

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
