"""Tests for the goals store module."""

from __future__ import annotations

from src.goals import store as goals_store


def test_load_all_missing_file_returns_empty(tmp_path):
    """Test that loading from a missing file returns an empty dict."""
    goals_path = tmp_path / "goals.json"
    assert goals_store.load_all(goals_path) == {}


def test_save_get_roundtrip(tmp_path):
    """Test that saving and retrieving a goal works."""
    goals_path = tmp_path / "goals.json"
    goals_store.save("a", "do x", goals_path)
    assert goals_store.get("a", goals_path) == "do x"


def test_get_unknown_returns_none(tmp_path):
    """Test that getting an unknown goal returns None."""
    goals_path = tmp_path / "goals.json"
    assert goals_store.get("unknown", goals_path) is None


def test_save_preserves_existing(tmp_path):
    """Test that saving a new goal preserves existing ones."""
    goals_path = tmp_path / "goals.json"
    goals_store.save("a", "do x", goals_path)
    goals_store.save("b", "do y", goals_path)
    all_goals = goals_store.load_all(goals_path)
    assert all_goals == {"a": "do x", "b": "do y"}


def test_delete(tmp_path):
    """Test deleting a goal."""
    goals_path = tmp_path / "goals.json"
    goals_store.save("a", "do x", goals_path)
    assert goals_store.delete("a", goals_path) is True
    assert goals_store.get("a", goals_path) is None
    # Deleting again should return False
    assert goals_store.delete("a", goals_path) is False


def test_list_names_sorted(tmp_path):
    """Test that list_names returns sorted goal names."""
    goals_path = tmp_path / "goals.json"
    goals_store.save("b", "do y", goals_path)
    goals_store.save("a", "do x", goals_path)
    assert goals_store.list_names(goals_path) == ["a", "b"]
