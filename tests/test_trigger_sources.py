"""Tests for the rss/file/once trigger sources and the state store."""

import asyncio
import datetime as dt

import pytest

from opengriffin import triggers

RSS_XML = """<?xml version="1.0"?>
<rss version="2.0"><channel><title>Feed</title>
<item><guid>g1</guid><title>First post</title><link>https://ex.com/1</link><pubDate>Mon, 17 Aug 2026 10:00:00 GMT</pubDate></item>
<item><guid>g2</guid><title>Second post</title><link>https://ex.com/2</link></item>
</channel></rss>"""

ATOM_XML = """<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom"><title>AFeed</title>
<entry><id>a1</id><title>Atom entry</title><link href="https://ex.com/a1"/><updated>2026-08-17T10:00:00Z</updated></entry>
</feed>"""


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(triggers, "TRIGGERS_FILE", tmp_path / "triggers.json")
    monkeypatch.setattr(triggers, "STATE_FILE", tmp_path / "trigger_state.json")


def test_parse_feed_rss_and_atom():
    items = triggers.parse_feed(RSS_XML)
    assert [i["id"] for i in items] == ["g1", "g2"]
    assert items[0]["link"] == "https://ex.com/1"
    items = triggers.parse_feed(ATOM_XML)
    assert items == [
        {
            "title": "Atom entry",
            "link": "https://ex.com/a1",
            "published": "2026-08-17T10:00:00Z",
            "id": "a1",
        }
    ]
    assert triggers.parse_feed("not xml at all") == []


def test_state_store_roundtrip():
    assert triggers.state_get("t1") == {}
    triggers.state_set("t1", {"seen": ["a"]})
    triggers.state_set("t2", {"n": 1})
    assert triggers.state_get("t1") == {"seen": ["a"]}
    assert triggers.state_get("t2") == {"n": 1}


class _FakeResp:
    def __init__(self, text):
        self._text = text

    async def text(self):
        return self._text

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


class _FakeSession:
    """Stands in for aiohttp.ClientSession; serves a mutable XML payload."""

    payload = RSS_XML

    def __init__(self, *args, **kwargs):
        pass

    def get(self, url, timeout=None):
        return _FakeResp(type(self).payload)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


@pytest.fixture
def rss_world(monkeypatch):
    import aiohttp

    _FakeSession.payload = RSS_XML
    monkeypatch.setattr(aiohttp, "ClientSession", _FakeSession)
    calls = []

    async def fake_evaluate(trigger, event_payload=None):
        calls.append(event_payload)
        return "delivered"

    monkeypatch.setattr(triggers, "evaluate", fake_evaluate)
    trigger = {
        "id": "rss1",
        "enabled": True,
        "source": {"kind": "rss", "feeds": "https://ex.com/feed.xml", "interval_sec": 60},
        "action": {"kind": "agent", "prompt": "digest", "deliver_to": "home"},
    }
    return trigger, calls


def test_rss_trigger_baselines_then_reports_only_new(rss_world):
    trigger, calls = rss_world
    # First run establishes the baseline without invoking the agent.
    asyncio.run(triggers._run_rss_trigger(trigger))
    assert calls == []
    # Same feed again: nothing new, agent not invoked.
    asyncio.run(triggers._run_rss_trigger(trigger))
    assert calls == []
    # A new item appears: agent gets exactly that item.
    _FakeSession.payload = RSS_XML.replace(
        "</channel>",
        "<item><guid>g3</guid><title>Third</title><link>https://ex.com/3</link></item></channel>",
    )
    asyncio.run(triggers._run_rss_trigger(trigger))
    assert len(calls) == 1
    assert [i["id"] for i in calls[0]["new_items"]] == ["g3"]


def test_file_trigger_reports_new_files(tmp_path, monkeypatch):
    calls = []

    async def fake_evaluate(trigger, event_payload=None):
        calls.append(event_payload)
        return "delivered"

    monkeypatch.setattr(triggers, "evaluate", fake_evaluate)
    watch_dir = tmp_path / "dropbox"
    watch_dir.mkdir()
    (watch_dir / "existing.txt").write_text("old")
    trigger = {
        "id": "f1",
        "enabled": True,
        "source": {"kind": "file", "dir": str(watch_dir), "pattern": "*", "interval_sec": 60},
        "action": {"kind": "agent", "prompt": "process", "deliver_to": "home"},
    }
    # Baseline run: existing files are recorded, not reported.
    asyncio.run(triggers._run_file_trigger(trigger))
    assert calls == []
    # No changes: quiet.
    asyncio.run(triggers._run_file_trigger(trigger))
    assert calls == []
    # New file: reported.
    (watch_dir / "notes.pdf").write_text("new")
    asyncio.run(triggers._run_file_trigger(trigger))
    assert len(calls) == 1
    assert calls[0]["new_files"] == [str(watch_dir / "notes.pdf")]


def test_once_trigger_fires_and_self_disables(monkeypatch):
    fired = []

    async def fake_evaluate(trigger, event_payload=None):
        fired.append(trigger["id"])
        return "ok"

    monkeypatch.setattr(triggers, "evaluate", fake_evaluate)
    trigger = {
        "id": "remind-1",
        "enabled": True,
        "source": {"kind": "once", "at": "2030-01-01T09:00:00"},
        "action": {"kind": "send", "text": "hi", "deliver_to": "home"},
    }
    triggers._save({"triggers": [trigger]})
    asyncio.run(triggers._run_once_trigger(trigger))
    assert fired == ["remind-1"]
    stored = triggers._load()["triggers"][0]
    assert stored["enabled"] is False
    assert stored["fired_at"]


class _FakeScheduler:
    def __init__(self):
        self.jobs = []

    def add_job(self, func, trigger=None, args=None, **kwargs):
        self.jobs.append((func.__name__, kwargs.get("id")))


def test_install_registers_all_source_kinds():
    future = (dt.datetime.now() + dt.timedelta(days=1)).isoformat()
    triggers._save(
        {
            "triggers": [
                {"id": "c", "source": {"kind": "cron", "expr": "0 7 * * *"}},
                {"id": "p", "source": {"kind": "poll", "url": "https://x", "interval_sec": 60}},
                {"id": "r", "source": {"kind": "rss", "feeds": "https://x", "interval_sec": 60}},
                {"id": "f", "source": {"kind": "file", "dir": "/tmp", "interval_sec": 60}},
                {"id": "o", "source": {"kind": "once", "at": future}},
                {"id": "past", "source": {"kind": "once", "at": "2020-01-01T00:00:00"}},
                {"id": "off", "enabled": False, "source": {"kind": "cron", "expr": "0 7 * * *"}},
            ]
        }
    )
    sched = _FakeScheduler()
    n = triggers.install_into_scheduler(sched)
    assert n == 5  # past-dated 'once' and disabled triggers are skipped
    names = {job_id for _, job_id in sched.jobs}
    assert names == {"trigger:c", "trigger:p", "trigger:r", "trigger:f", "trigger:o"}
