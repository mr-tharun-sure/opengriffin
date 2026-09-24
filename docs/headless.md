# Running headless (24/7 bot)

OpenGriffin is meant to run unattended — on a Mac mini in a closet, a home
server, a VPS. Three things make that reliable: durable Claude auth, a
process supervisor, and knowing the one-instance rule. `opengriffin doctor`
checks the first; this page covers all three.

## Claude auth that doesn't expire monthly

The interactive `claude` → `/login` flow stores a refresh token meant for
laptops: it expires after roughly **28 days** and is invalidated when the
same account signs in elsewhere. On a 24/7 bot that shows up as a monthly
outage — every reply failing with `401` / "Failed to authenticate" until
someone re-runs `/login` on the server.

Use a **long-lived setup token** instead (still billed to your Claude
subscription):

```bash
claude setup-token     # one-time browser sign-in; prints sk-ant-oat01-…
```

The token is shown **once** — copy it into your env file:

```bash
# ~/.opengriffin/.env
CLAUDE_CODE_OAUTH_TOKEN=sk-ant-oat01-...
```

Then restart the bot. It now authenticates independently of
`~/.claude/.credentials.json`: logins on other devices can't break it, and
the token lasts about a year. Have the bot remind you to renew it:
*"remind me in 11 months to re-run claude setup-token"*.

Alternatives and rules:

- `ANTHROPIC_API_KEY` also never expires (pay-per-token instead of your
  subscription).
- Set **exactly one** of `CLAUDE_CODE_OAUTH_TOKEN` / `ANTHROPIC_API_KEY`.
  A stale key silently outranks a working login — the cause of many
  mystery 401s.
- `opengriffin doctor` reports which auth source is in effect and warns
  if you're running a daemon on laptop-grade `/login` credentials.

## Run under a supervisor

The installer renders ready-to-use service files into your install dir
(see the tail of `install.sh` output for the exact commands):

- **Linux** — `opengriffin.service`, installed as a systemd *user*
  service (`systemctl --user enable --now opengriffin`, plus
  `loginctl enable-linger $USER`). Restart:
  `systemctl --user restart opengriffin`.
- **macOS** — `opengriffin.plist`, installed as a per-user LaunchAgent.
  Restart: `launchctl kickstart -k gui/$(id -u)/com.opengriffin.agent`.
  Logs: `tail -f <install dir>/opengriffin.log`.

Both run the bot **as your user** — deliberately. A root/system service
has a different `$HOME`, can't see your Claude credentials, and fails
auth. Both also restart the bot on crashes and at boot, which your
scheduled [autonomous tasks](autonomous-tasks.md) depend on.

## One instance only

Telegram allows one `getUpdates` poller per bot token. Two running
instances (say, a forgotten LaunchAgent plus a terminal session) fight
over it and you'll see:

```
telegram.error.Conflict: terminated by other getUpdates request
```

Find the duplicate with `pgrep -af opengriffin` and
`launchctl list | grep griffin` (or `systemctl --user status opengriffin`),
and remove all but one.

## Quick triage table

| Symptom | Cause | Fix |
|---|---|---|
| `401 … OAuth` on every reply | `/login` token expired | switch to `claude setup-token` (above) |
| `telegram.error.InvalidToken` | bot token revoked/typo'd, or the bot read a different `.env` | verify with `curl …/getMe`; keep one `.env` at `~/.opengriffin/.env` |
| `telegram.error.Conflict` | two bot instances | kill the duplicate |
| bot exits at startup, "refusing to start an open bot" | `TELEGRAM_ALLOWED_USERS` unset | add your numeric id (from @userinfobot) |
| silence, log shows `Unauthorized message from …` | your id not in the allowlist | `/whoami` to the bot, fix the id |

Run `opengriffin doctor` first — it now checks the env file location,
both Telegram settings, and Claude auth durability in one shot.
