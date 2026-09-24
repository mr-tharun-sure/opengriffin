"""OpenGriffin command-line entrypoint."""

from __future__ import annotations

import os

import typer
from rich import print as rprint
from rich.table import Table

app = typer.Typer(
    name="opengriffin",
    help="Self-evolving personal agent. Telegram-first, multi-provider, OSS.",
    add_completion=False,
)

# Subcommand: migrate from-hermes / from-openclaw
try:
    from . import migrate as _migrate_module

    app.add_typer(
        _migrate_module.app, name="migrate", help="Import state from a prior agent runtime"
    )
except Exception:
    pass


@app.command()
def run() -> None:
    """Start the Telegram bot (foreground; ctrl-c to quit)."""
    from . import bot

    bot.main()


@app.command()
def doctor() -> None:
    """Diagnose the install — env file, tokens, Claude auth durability, provider."""
    from pathlib import Path

    from dotenv import load_dotenv

    from . import paths as paths_module
    from . import providers as _p  # noqa

    # Load .env exactly the way bot.py does, so doctor reports what the bot
    # will actually see rather than whatever happens to be in the shell.
    env_file = None
    for candidate in (
        paths_module.ENV_FILE,
        Path.cwd() / ".env",
        Path.home() / ".config" / "opengriffin" / ".env",
    ):
        if candidate.is_file():
            load_dotenv(candidate)
            env_file = candidate
            break

    table = Table(title="OpenGriffin doctor")
    table.add_column("Check")
    table.add_column("Status")
    table.add_column("Detail")

    table.add_row(
        "Env file",
        "✅" if env_file else "⚠️",
        str(env_file) if env_file else "none found — copy .env.example to ~/.opengriffin/.env",
    )

    prov = os.environ.get("OPENGRIFFIN_PROVIDER", "claude")
    table.add_row("Provider", "✅", prov)

    tok = os.environ.get("TELEGRAM_BOT_TOKEN")
    table.add_row("TELEGRAM_BOT_TOKEN", "✅" if tok else "❌", "set" if tok else "missing")

    allowed = os.environ.get("TELEGRAM_ALLOWED_USERS", "").strip()
    table.add_row(
        "TELEGRAM_ALLOWED_USERS",
        "✅" if allowed else "❌",
        "set"
        if allowed
        else "missing — the bot refuses to start open (get your id from @userinfobot)",
    )

    # Claude auth durability. Interactive /login refresh tokens expire after
    # ~28 days and are invalidated by logins elsewhere — fine on a laptop,
    # a monthly outage on a 24/7 bot. See docs/headless.md.
    oat = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    login_creds = Path.home() / ".claude" / ".credentials.json"
    if oat and api_key:
        table.add_row(
            "Claude auth",
            "⚠️",
            "both CLAUDE_CODE_OAUTH_TOKEN and ANTHROPIC_API_KEY set — remove one so it's unambiguous which is used",
        )
    elif oat:
        table.add_row("Claude auth", "✅", "long-lived setup-token (headless-safe, ~1 year)")
    elif api_key:
        table.add_row("Claude auth", "✅", "ANTHROPIC_API_KEY (never expires; pay-per-token)")
    elif login_creds.is_file():
        table.add_row(
            "Claude auth",
            "⚠️",
            "interactive `claude /login` credentials — these expire ~monthly and break when you "
            "log in elsewhere. For a 24/7 bot run `claude setup-token` and put "
            "CLAUDE_CODE_OAUTH_TOKEN in your .env (see docs/headless.md)",
        )
    else:
        table.add_row(
            "Claude auth",
            "❌",
            "no credentials found — run `claude setup-token` (Max subscription) or set ANTHROPIC_API_KEY",
        )

    try:
        from .providers import get_provider

        p = get_provider()
        table.add_row(
            "Provider load",
            "✅",
            f"{p.name} (tools={p.supports_tools}, skills={p.supports_skills})",
        )
    except Exception as e:
        table.add_row("Provider load", "❌", str(e))

    rprint(table)


@app.command()
def journal(n: int = 5) -> None:
    """Show the last `n` daily journal entries."""
    from . import self_improve

    rprint(self_improve.read_recent_journal(n))


@app.command()
def usage() -> None:
    """Show 24h/7d/30d cost + token totals."""
    from . import usage as u

    rprint(u.summary())


@app.command()
def insights() -> None:
    """Deeper usage breakdown — daily totals, top jobs, top topics."""
    from . import usage as u

    rprint(u.insights())


@app.command()
def memory(target: str = typer.Argument("both", help="memory | user | both")) -> None:
    """Show persistent memory (MEMORY.md and/or USER.md)."""
    from . import memory as m

    if target in ("memory", "both"):
        rprint("[bold]MEMORY.md[/bold]")
        for e in m.list_entries("memory"):
            rprint(f"• {e}")
    if target in ("user", "both"):
        rprint("\n[bold]USER.md[/bold]")
        for e in m.list_entries("user"):
            rprint(f"• {e}")


@app.command()
def improve() -> None:
    """Run a self-improvement turn now (normally cron-triggered at 4:30am)."""
    import asyncio

    from . import self_improve

    rprint("Running self-improvement turn…")
    asyncio.run(self_improve.run_daily(bot=None, deliver_to=None))
    rprint("[green]done — see /journal[/green]")


@app.command()
def card(
    date: str = typer.Option(None, "--date", "-d", help="Entry date YYYY-MM-DD (default: latest)"),
    output: str = typer.Option(None, "--output", "-o", help="Output path (default: memories dir)"),
    png: bool = typer.Option(False, "--png", help="Also rasterise to PNG (sips/rsvg/cairosvg)"),
) -> None:
    """Render a nightly journal entry into a shareable card (SVG, optionally PNG)."""
    from . import journal_card

    try:
        res = journal_card.make_card(date=date, output=output, png=png)
    except ValueError as e:
        rprint(f"[red]{e}[/red]")
        raise typer.Exit(1) from e
    rprint(f"[green]card written[/green] for {res['date']}")
    rprint(f"  SVG: {res['svg']}")
    if res["png"]:
        rprint(f"  PNG: {res['png']}")
    elif png:
        rprint("  [yellow]PNG skipped — no rasteriser found (install librsvg/cairosvg).[/yellow]")
    rprint("\nOpen it, screenshot it, post it. [dim]This is your launch artifact.[/dim]")


def main():
    app()


if __name__ == "__main__":
    main()
