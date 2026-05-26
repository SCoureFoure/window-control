"""Tests for src/safety.py — action allowlist."""

from __future__ import annotations

import importlib

import pytest

import src.safety as safety


def _reset():
    """Reload the module to restore ALLOWED_ACTIONS to its default."""
    importlib.reload(safety)


def test_all_actions_allowed_by_default():
    _reset()
    assert safety.is_allowed("left_click")
    assert safety.is_allowed("type")
    assert safety.is_allowed("screenshot")


def test_restrict_limits_allowed_set():
    _reset()
    safety.restrict({"left_click", "screenshot"})
    assert safety.is_allowed("left_click")
    assert safety.is_allowed("screenshot")
    assert not safety.is_allowed("type")
    assert not safety.is_allowed("key")
    _reset()


def test_is_allowed_unknown_action_false():
    _reset()
    assert not safety.is_allowed("fly_to_moon")


def test_parse_allow_flag_valid():
    result = safety.parse_allow_flag("left_click,type,screenshot")
    assert result == {"left_click", "type", "screenshot"}


def test_parse_allow_flag_strips_whitespace():
    result = safety.parse_allow_flag("left_click, type , screenshot")
    assert "left_click" in result
    assert "type" in result


def test_parse_allow_flag_unknown_raises():
    with pytest.raises(ValueError, match="Unknown action"):
        safety.parse_allow_flag("left_click,teleport")


def test_typing_actions_constant():
    assert "type" in safety.TYPING_ACTIONS
    assert "key" in safety.TYPING_ACTIONS


def test_no_typing_shortcut_removes_type_and_key():
    _reset()
    safety.restrict(safety.ALLOWED_ACTIONS - safety.TYPING_ACTIONS)
    assert not safety.is_allowed("type")
    assert not safety.is_allowed("key")
    assert safety.is_allowed("left_click")
    _reset()


def test_all_actions_subset_of_handlers():
    from src.zones.action import _HANDLERS
    assert safety.ALL_ACTIONS == frozenset(_HANDLERS.keys())
