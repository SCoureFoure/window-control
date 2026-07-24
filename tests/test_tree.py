"""Tests for src/scripts/tree.py — project-tree resolution (pure functions).

All trees are built under tmp_path with plain mkdir/write_text; nothing
touches the real ~/.window-control config.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.scripts import tree


def make_project(root: Path) -> Path:
    p = root / "uma"
    (p / "daily-races").mkdir(parents=True)
    (p / "scripts").mkdir()
    (p / "project.yaml").write_text("lens: uma\n", encoding="utf-8")
    return p


def test_locate_happy(tmp_path: Path):
    p = make_project(tmp_path)
    (p / "daily-races" / "daily-legend-races.yaml").write_text("steps: []\n", encoding="utf-8")

    path = tree.locate("uma/daily-races/daily-legend-races", projects_dir=tmp_path)
    assert path == p / "daily-races" / "daily-legend-races.yaml"


def test_locate_missing_raises(tmp_path: Path):
    make_project(tmp_path)
    with pytest.raises(FileNotFoundError):
        tree.locate("uma/daily-races/does-not-exist", projects_dir=tmp_path)


def test_locate_one_segment_raises(tmp_path: Path):
    with pytest.raises(ValueError):
        tree.locate("just-a-name", projects_dir=tmp_path)


def test_locate_dotdot_raises(tmp_path: Path):
    with pytest.raises(ValueError):
        tree.locate("uma/../x", projects_dir=tmp_path)


def test_search_bare_finds_all_sorted(tmp_path: Path):
    p1 = make_project(tmp_path)
    (p1 / "daily-races" / "shared.yaml").write_text("steps: []\n", encoding="utf-8")

    p2 = tmp_path / "other"
    (p2 / "sub").mkdir(parents=True)
    (p2 / "project.yaml").write_text("lens: other\n", encoding="utf-8")
    (p2 / "sub" / "shared.yaml").write_text("steps: []\n", encoding="utf-8")

    hits = tree.search_bare("shared", projects_dir=tmp_path)
    assert hits == sorted(hits)
    assert len(hits) == 2


def test_search_bare_missing_dir_empty(tmp_path: Path):
    assert tree.search_bare("shared", projects_dir=tmp_path / "nope") == []


def test_ancestor_chain_order(tmp_path: Path):
    root = tmp_path / "root"
    folder = root / "a" / "b"
    folder.mkdir(parents=True)

    assert tree.ancestor_chain(folder, root) == [root / "a" / "b", root / "a", root]


def test_ancestor_chain_outside_raises(tmp_path: Path):
    root = tmp_path / "root"
    other = tmp_path / "other"
    root.mkdir()
    other.mkdir()

    with pytest.raises(ValueError):
        tree.ancestor_chain(other, root)


def test_resolve_button_nearest_wins(tmp_path: Path):
    p = make_project(tmp_path)
    (p / "buttons.json").write_text(
        '{"back": {"point": [1, 1]}, "go": {"point": [2, 2]}}', encoding="utf-8"
    )
    (p / "daily-races" / "buttons.json").write_text(
        '{"go": {"point": [9, 9]}}', encoding="utf-8"
    )

    child = p / "daily-races"
    assert tree.resolve_button("go", child, p) == (9, 9)
    assert tree.resolve_button("back", child, p) == (1, 1)


def test_resolve_button_rect_center_via_store(tmp_path: Path):
    p = make_project(tmp_path)
    (p / "buttons.json").write_text('{"box": {"rect": [0, 0, 80, 80]}}', encoding="utf-8")

    assert tree.resolve_button("box", p, p) == (40, 40)


def test_resolve_button_unknown_lists_checked(tmp_path: Path):
    p = make_project(tmp_path)
    (p / "buttons.json").write_text('{"back": {"point": [1, 1]}}', encoding="utf-8")
    (p / "daily-races" / "buttons.json").write_text('{"go": {"point": [9, 9]}}', encoding="utf-8")

    child = p / "daily-races"
    with pytest.raises(KeyError) as excinfo:
        tree.resolve_button("nope", child, p)

    # KeyError's str() reprs the whole message, and Path.__repr__ renders
    # paths as posix-style (forward-slash) strings — compare against repr(),
    # not str(), or Windows backslash paths never match.
    message = str(excinfo.value)
    assert repr(child / "buttons.json") in message
    assert repr(p / "buttons.json") in message


def test_resolve_run_target_nearest_scripts_dir(tmp_path: Path):
    p = make_project(tmp_path)
    (p / "scripts" / "x.yaml").write_text("steps: []\n", encoding="utf-8")
    (p / "daily-races" / "scripts").mkdir()
    (p / "daily-races" / "scripts" / "x.yaml").write_text("steps: []\n", encoding="utf-8")

    child = p / "daily-races"
    result = tree.resolve_run_target("x", child, p)
    assert result == p / "daily-races" / "scripts" / "x.yaml"


def test_resolve_run_target_ignores_loose_files(tmp_path: Path):
    p = make_project(tmp_path)
    (p / "daily-races" / "x.yaml").write_text("steps: []\n", encoding="utf-8")
    (p / "scripts" / "x.yaml").write_text("steps: []\n", encoding="utf-8")

    child = p / "daily-races"
    result = tree.resolve_run_target("x", child, p)
    assert result == p / "scripts" / "x.yaml"


def test_resolve_run_target_missing_raises(tmp_path: Path):
    p = make_project(tmp_path)
    child = p / "daily-races"
    with pytest.raises(FileNotFoundError):
        tree.resolve_run_target("nope", child, p)


def test_load_project_config_merge_and_override(tmp_path: Path):
    p = make_project(tmp_path)
    (p / "project.yaml").write_text("lens: uma\nmax-steps-per-goal: 20\n", encoding="utf-8")
    (p / "daily-races" / "project.yaml").write_text("max-steps-per-goal: 5\n", encoding="utf-8")

    child = p / "daily-races"
    cfg = tree.load_project_config(child, p)
    assert cfg == {"lens": "uma", "max-steps-per-goal": 5}


def test_load_project_config_missing_root_lens_raises(tmp_path: Path):
    p = tmp_path / "uma"
    (p / "daily-races").mkdir(parents=True)
    (p / "project.yaml").write_text("max-steps-per-goal: 20\n", encoding="utf-8")

    child = p / "daily-races"
    with pytest.raises(ValueError):
        tree.load_project_config(child, p)


def test_load_project_config_child_lens_raises(tmp_path: Path):
    p = make_project(tmp_path)
    (p / "daily-races" / "project.yaml").write_text("lens: other\n", encoding="utf-8")

    child = p / "daily-races"
    with pytest.raises(ValueError):
        tree.load_project_config(child, p)
