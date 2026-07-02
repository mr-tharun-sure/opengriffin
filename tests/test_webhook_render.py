"""Tests for the webhook template renderer and skill-name validation."""

import pytest

from opengriffin.skill_hub import _validate_name
from opengriffin.webhooks import _render

CTX = {
    "headers": {"X-GitHub-Event": "push"},
    "body": {"repository": {"full_name": "acme/widgets"}, "commits": [{"id": "abc123"}]},
    "query": {"token": "t"},
}


def test_render_bracket_lookup():
    assert _render("GitHub: {{ headers['X-GitHub-Event'] }}", CTX) == "GitHub: push"


def test_render_dot_lookup():
    assert _render("{{ body.repository.full_name }}", CTX) == "acme/widgets"


def test_render_mixed_and_list_index():
    assert _render("{{ body['commits'][0]['id'] }}", CTX) == "abc123"


def test_render_missing_key():
    assert _render("{{ body.nope }}", CTX) == "<missing:body.nope>"


def test_render_rejects_code_expressions():
    # Anything that isn't a plain lookup path must not be evaluated.
    for expr in (
        "__import__('os').system('id')",
        "().__class__.__mro__",
        "headers['a'] + headers['b']",
        "body.__class__",
    ):
        out = _render("{{ " + expr + " }}", CTX)
        assert out.startswith("<missing:"), expr


def test_validate_name_accepts_normal_names():
    assert _validate_name("my-skill") == "my-skill"
    assert _validate_name(" trimmed ") == "trimmed"


def test_validate_name_rejects_traversal():
    for bad in ("../../etc", "..", "a/b", "a\\b", "", ".hidden", "."):
        with pytest.raises(ValueError):
            _validate_name(bad)
