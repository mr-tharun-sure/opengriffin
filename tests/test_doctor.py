"""Tests for `opengriffin doctor` — env loading and Claude-auth durability checks."""

import pytest
from typer.testing import CliRunner

from opengriffin import cli

runner = CliRunner()


@pytest.fixture(autouse=True)
def _clean_env(tmp_path, monkeypatch):
    """Isolate HOME and strip auth/telegram vars so each test states its own world."""
    monkeypatch.setenv("HOME", str(tmp_path))
    for var in (
        "CLAUDE_CODE_OAUTH_TOKEN",
        "ANTHROPIC_API_KEY",
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_ALLOWED_USERS",
        "OPENGRIFFIN_PROVIDER",
    ):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.chdir(tmp_path)  # no stray ./.env pickup


def _doctor_output() -> str:
    result = runner.invoke(cli.app, ["doctor"])
    assert result.exit_code == 0, result.output
    return result.output


def test_doctor_flags_missing_credentials():
    out = _doctor_output()
    assert "no credentials found" in out
    assert "TELEGRAM_ALLOWED_USERS" in out


def test_doctor_prefers_setup_token(monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "sk-ant-oat01-test")
    out = _doctor_output()
    assert "long-lived setup-token" in out


def test_doctor_warns_on_login_credentials(tmp_path, monkeypatch):
    creds = tmp_path / ".claude"
    creds.mkdir()
    (creds / ".credentials.json").write_text("{}")
    out = _doctor_output()
    assert "setup-token" in out  # steers toward the durable option
    assert "expire" in out


def test_doctor_warns_when_both_auth_sources_set(monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "sk-ant-oat01-test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-api03-test")
    out = _doctor_output()
    assert "remove one" in out


def test_doctor_reads_env_file(tmp_path, monkeypatch):
    from opengriffin import paths

    env = tmp_path / "og-home" / ".env"
    env.parent.mkdir()
    env.write_text("TELEGRAM_BOT_TOKEN=123:abc\nTELEGRAM_ALLOWED_USERS=42\n")
    monkeypatch.setattr(paths, "ENV_FILE", env)
    out = _doctor_output()
    # The env file was found (rich may truncate the path, so assert the effect):
    assert "none found" not in out
    # ...and its values are reflected in the checks.
    assert "missing" not in out
