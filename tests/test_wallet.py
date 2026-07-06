"""Tests for wallet spending caps and spend recording."""

import pytest

from opengriffin import wallet


@pytest.fixture(autouse=True)
def _isolated_wallet(tmp_path, monkeypatch):
    monkeypatch.setattr(wallet, "WALLET_FILE", tmp_path / "wallet.json")
    monkeypatch.setenv("WALLET_DAILY_USD_CAP", "10")


def test_daily_cap_enforced():
    ok, _ = wallet.can_spend(9.99)
    assert ok
    wallet.record_spend(8, "vendor", "item")
    ok, msg = wallet.can_spend(3)
    assert not ok
    assert "daily cap" in msg


def test_skill_cap_tracks_skill_spend_not_global():
    wallet._save({"caps": {"weather": 5}, "spend": {}})
    # Global spend of $4 must not count against the weather skill's $5 cap.
    wallet.record_spend(4, "vendor", "item")
    ok, _ = wallet.can_spend(2, skill="weather")
    assert ok
    # But the skill's own spend must.
    wallet.record_spend(4, "vendor", "item", skill="weather")
    ok, msg = wallet.can_spend(2, skill="weather")
    assert not ok
    assert "weather" in msg


def test_record_spend_accumulates_and_keeps_history():
    wallet.record_spend(1.5, "acme", "widget", skill="shopping")
    wallet.record_spend(2.5, "acme", "gadget", skill="shopping")
    assert wallet.daily_spent_usd() == pytest.approx(4.0)
    assert wallet.skill_spent_usd("shopping") == pytest.approx(4.0)
    history = wallet._load()["history"]
    assert history[-1]["skill"] == "shopping"
    assert history[-1]["vendor"] == "acme"
