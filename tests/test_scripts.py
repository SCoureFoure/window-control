"""Tests for src/scripts/runner.py — YAML script loading and execution.

External boundaries mocked:
- orchestrator.run (patched on the runner's `orchestrator` module reference)
- DesktopBackend (patched to return a FakeBackend that records calls)

All scripts_dir / maps_dir / lenses_path arguments use tmp_path — nothing
touches the real ~/.window-control config.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from src.actionmap.store import ActionMap
from src.actionmap import store as actionmap_store
from src.lens.model import Lens
from src.lens import store as lens_store
from src.scripts import runner


class FakeBackend:
    """Records every call it receives instead of touching real input."""

    def __init__(self):
        self.calls = []

    def click(self, x, y, button="left"):
        self.calls.append(("click", x, y, button))

    def swipe(self, x1, y1, x2, y2, duration=0.3):
        self.calls.append(("swipe", x1, y1, x2, y2, duration))

    def type_text(self, text):
        self.calls.append(("type_text", text))

    def wait(self, seconds):
        self.calls.append(("wait", seconds))

    def key(self, keys):
        self.calls.append(("key", keys))

    def scroll(self, x, y, direction, amount):
        self.calls.append(("scroll", x, y, direction, amount))


def _write_script(scripts_dir: Path, name: str, text: str) -> None:
    scripts_dir.mkdir(parents=True, exist_ok=True)
    (scripts_dir / f"{name}.yaml").write_text(textwrap.dedent(text), encoding="utf-8")


FULL_SCRIPT = """\
    name: uma-daily
    lens: uma
    steps:
      - goal: "click the Options icon"
      - tap: settings
      - type: "hello"
      - wait: 1.0
      - swipe: {from: back, to: home, duration: 0.3}
"""


# ---------------------------------------------------------------------------
# load_script
# ---------------------------------------------------------------------------

def test_load_script_roundtrip(tmp_path):
    _write_script(tmp_path, "uma-daily", FULL_SCRIPT)
    script = runner.load_script("uma-daily", scripts_dir=tmp_path)
    assert script.name == "uma-daily"
    assert script.lens == "uma"
    assert len(script.steps) == 5
    assert script.steps[0] == {"goal": "click the Options icon"}
    assert script.steps[1] == {"tap": "settings"}
    assert script.steps[2] == {"type": "hello"}
    assert script.steps[3] == {"wait": 1.0}
    assert script.steps[4] == {"swipe": {"from": "back", "to": "home", "duration": 0.3}}


def test_load_script_name_defaults_to_stem(tmp_path):
    _write_script(tmp_path, "nameless", """\
        lens: uma
        steps:
          - tap: settings
    """)
    script = runner.load_script("nameless", scripts_dir=tmp_path)
    assert script.name == "nameless"


def test_load_script_missing_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        runner.load_script("nope", scripts_dir=tmp_path)


def test_load_script_bad_step_key_raises(tmp_path):
    _write_script(tmp_path, "bad-key", """\
        lens: uma
        steps:
          - tap: a
          - zap: x
    """)
    with pytest.raises(ValueError) as excinfo:
        runner.load_script("bad-key", scripts_dir=tmp_path)
    assert "2" in str(excinfo.value)


def test_load_script_multi_key_step_raises(tmp_path):
    _write_script(tmp_path, "multi-key", """\
        lens: uma
        steps:
          - tap: a
            wait: 1
    """)
    with pytest.raises(ValueError):
        runner.load_script("multi-key", scripts_dir=tmp_path)


# ---------------------------------------------------------------------------
# step_to_action
# ---------------------------------------------------------------------------

def test_step_to_action_tap():
    amap = ActionMap(lens="uma", buttons={"settings": {"point": [5, 6]}})
    action = runner.step_to_action({"tap": "settings"}, amap)
    assert action.tool_use_id == "script"
    assert action.action == "left_click"
    assert action.coordinate == (5, 6)


def test_step_to_action_type():
    action = runner.step_to_action({"type": "hello"}, None)
    assert action.tool_use_id == "script"
    assert action.action == "type"
    assert action.text == "hello"


def test_step_to_action_wait():
    action = runner.step_to_action({"wait": 1.0}, None)
    assert action.tool_use_id == "script"
    assert action.action == "wait"
    assert action.duration == 1.0


def test_step_to_action_swipe_default_duration():
    amap = ActionMap(lens="uma", buttons={
        "back": {"point": [1, 2]},
        "home": {"point": [3, 4]},
    })
    action = runner.step_to_action({"swipe": {"from": "back", "to": "home"}}, amap)
    assert action.tool_use_id == "script"
    assert action.action == "left_click_drag"
    assert action.start_coordinate == (1, 2)
    assert action.coordinate == (3, 4)
    assert action.duration == 0.3


def test_step_to_action_goal_returns_none():
    assert runner.step_to_action({"goal": "do something"}, None) is None


# ---------------------------------------------------------------------------
# run_script
# ---------------------------------------------------------------------------

def _save_lens(lenses_path: Path, name: str = "L") -> Lens:
    lens = Lens(name=name, x=100, y=200, w=300, h=400)
    lens_store.save(lens, path=lenses_path)
    return lens


def test_run_script_goal_steps_call_orchestrator(tmp_path, monkeypatch):
    scripts_dir = tmp_path / "scripts"
    lenses_path = tmp_path / "lenses.json"
    maps_dir = tmp_path / "maps"
    _save_lens(lenses_path)
    _write_script(scripts_dir, "two-goals", """\
        lens: L
        steps:
          - goal: "first goal"
          - goal: "second goal"
    """)

    recorded = []

    def fake_run(goal, lens, max_steps, show_grid, show_border):
        recorded.append(goal)
        return "done"

    monkeypatch.setattr(runner.orchestrator, "run", fake_run)
    monkeypatch.setattr(runner, "DesktopBackend", lambda: FakeBackend())

    outcome = runner.run_script(
        "two-goals",
        show_border=False,
        scripts_dir=scripts_dir,
        maps_dir=maps_dir,
        lenses_path=lenses_path,
    )

    assert outcome == "done"
    assert recorded == ["first goal", "second goal"]


def test_run_script_aborts_on_non_done_goal(tmp_path, monkeypatch):
    scripts_dir = tmp_path / "scripts"
    lenses_path = tmp_path / "lenses.json"
    maps_dir = tmp_path / "maps"
    _save_lens(lenses_path)
    _write_script(scripts_dir, "two-goals", """\
        lens: L
        steps:
          - goal: "first goal"
          - goal: "second goal"
    """)

    recorded = []

    def fake_run(goal, lens, max_steps, show_grid, show_border):
        recorded.append(goal)
        return "impossible"

    monkeypatch.setattr(runner.orchestrator, "run", fake_run)
    monkeypatch.setattr(runner, "DesktopBackend", lambda: FakeBackend())

    outcome = runner.run_script(
        "two-goals",
        show_border=False,
        scripts_dir=scripts_dir,
        maps_dir=maps_dir,
        lenses_path=lenses_path,
    )

    assert outcome == "impossible"
    assert recorded == ["first goal"]


def test_run_script_deterministic_dispatch(tmp_path, monkeypatch):
    scripts_dir = tmp_path / "scripts"
    lenses_path = tmp_path / "lenses.json"
    maps_dir = tmp_path / "maps"
    lens = _save_lens(lenses_path)
    actionmap_store.save(
        ActionMap(lens="L", buttons={"settings": {"point": [5, 6]}}),
        maps_dir=maps_dir,
    )
    _write_script(scripts_dir, "det", """\
        lens: L
        steps:
          - tap: settings
          - type: "hello"
          - wait: 1.0
    """)

    fake_backend = FakeBackend()
    monkeypatch.setattr(runner, "DesktopBackend", lambda: fake_backend)

    outcome = runner.run_script(
        "det",
        show_border=False,
        scripts_dir=scripts_dir,
        maps_dir=maps_dir,
        lenses_path=lenses_path,
    )

    assert outcome == "done"
    assert fake_backend.calls == [
        ("click", lens.x + 5, lens.y + 6, "left"),
        ("type_text", "hello"),
        ("wait", 1.0),
    ]


def test_run_script_no_map_needed_for_goal_type_wait(tmp_path, monkeypatch):
    scripts_dir = tmp_path / "scripts"
    lenses_path = tmp_path / "lenses.json"
    maps_dir = tmp_path / "maps"  # never created — no map file exists
    _save_lens(lenses_path)
    _write_script(scripts_dir, "no-map", """\
        lens: L
        steps:
          - goal: "do a thing"
          - type: "hello"
          - wait: 1.0
    """)

    monkeypatch.setattr(runner.orchestrator, "run", lambda *a, **k: "done")
    monkeypatch.setattr(runner, "DesktopBackend", lambda: FakeBackend())

    outcome = runner.run_script(
        "no-map",
        show_border=False,
        scripts_dir=scripts_dir,
        maps_dir=maps_dir,
        lenses_path=lenses_path,
    )

    assert outcome == "done"


def test_run_script_missing_map_aborts(tmp_path, monkeypatch):
    scripts_dir = tmp_path / "scripts"
    lenses_path = tmp_path / "lenses.json"
    maps_dir = tmp_path / "maps"  # never created
    _save_lens(lenses_path)
    _write_script(scripts_dir, "needs-map", """\
        lens: L
        steps:
          - tap: settings
    """)

    monkeypatch.setattr(runner, "DesktopBackend", lambda: FakeBackend())

    outcome = runner.run_script(
        "needs-map",
        show_border=False,
        scripts_dir=scripts_dir,
        maps_dir=maps_dir,
        lenses_path=lenses_path,
    )

    assert outcome == "error"


def test_run_script_oob_tap_aborts(tmp_path, monkeypatch):
    scripts_dir = tmp_path / "scripts"
    lenses_path = tmp_path / "lenses.json"
    maps_dir = tmp_path / "maps"
    _save_lens(lenses_path)  # lens is 300x400
    actionmap_store.save(
        ActionMap(lens="L", buttons={"far": {"point": [9999, 9999]}}),
        maps_dir=maps_dir,
    )
    _write_script(scripts_dir, "oob", """\
        lens: L
        steps:
          - tap: far
    """)

    fake_backend = FakeBackend()
    monkeypatch.setattr(runner, "DesktopBackend", lambda: fake_backend)

    outcome = runner.run_script(
        "oob",
        show_border=False,
        scripts_dir=scripts_dir,
        maps_dir=maps_dir,
        lenses_path=lenses_path,
    )

    assert outcome == "error"
    assert fake_backend.calls == []


# ---------------------------------------------------------------------------
# New step types: key and scroll
# ---------------------------------------------------------------------------


def test_step_to_action_key():
    action = runner.step_to_action({"key": ["ctrl", "l"]}, None)
    assert action.tool_use_id == "script"
    assert action.action == "key"
    assert action.keys == ["ctrl", "l"]


def test_step_to_action_scroll_named_button():
    amap = ActionMap(lens="uma", buttons={"results": {"point": [50, 60]}})
    action = runner.step_to_action(
        {"scroll": {"at": "results", "direction": "up", "amount": 5}}, amap
    )
    assert action.tool_use_id == "script"
    assert action.action == "scroll"
    assert action.coordinate == (50, 60)
    assert action.scroll_direction == "up"
    assert action.scroll_distance == 5


def test_step_to_action_scroll_literal_coord_defaults():
    action = runner.step_to_action({"scroll": {"at": [10, 20]}}, None)
    assert action.tool_use_id == "script"
    assert action.action == "scroll"
    assert action.coordinate == (10, 20)
    assert action.scroll_direction == "down"
    assert action.scroll_distance == 3


def test_load_script_bad_key_value_raises(tmp_path):
    _write_script(tmp_path, "bad-key", """\
        lens: uma
        steps:
          - key: "ctrl"
    """)
    with pytest.raises(ValueError) as excinfo:
        runner.load_script("bad-key", scripts_dir=tmp_path)
    assert "1" in str(excinfo.value)


def test_load_script_bad_scroll_direction_raises(tmp_path):
    _write_script(tmp_path, "bad-scroll", """\
        lens: uma
        steps:
          - scroll: {at: [1, 2], direction: sideways}
    """)
    with pytest.raises(ValueError) as excinfo:
        runner.load_script("bad-scroll", scripts_dir=tmp_path)
    assert "1" in str(excinfo.value)


def test_run_script_key_and_scroll_dispatch(tmp_path, monkeypatch):
    scripts_dir = tmp_path / "scripts"
    lenses_path = tmp_path / "lenses.json"
    maps_dir = tmp_path / "maps"
    lens = _save_lens(lenses_path)
    _write_script(scripts_dir, "key-scroll", """\
        lens: L
        steps:
          - key: [enter]
          - scroll: {at: [10, 20], direction: down}
    """)

    fake_backend = FakeBackend()
    monkeypatch.setattr(runner, "DesktopBackend", lambda: fake_backend)

    outcome = runner.run_script(
        "key-scroll",
        show_border=False,
        scripts_dir=scripts_dir,
        maps_dir=maps_dir,
        lenses_path=lenses_path,
    )

    assert outcome == "done"
    assert fake_backend.calls == [
        ("key", ["enter"]),
        ("scroll", lens.x + 10, lens.y + 20, "down", 3),
    ]


def test_run_script_scroll_named_needs_map(tmp_path, monkeypatch):
    scripts_dir = tmp_path / "scripts"
    lenses_path = tmp_path / "lenses.json"
    maps_dir = tmp_path / "maps"  # never created
    _save_lens(lenses_path)
    _write_script(scripts_dir, "scroll-named", """\
        lens: L
        steps:
          - scroll: {at: results}
    """)

    monkeypatch.setattr(runner, "DesktopBackend", lambda: FakeBackend())

    outcome = runner.run_script(
        "scroll-named",
        show_border=False,
        scripts_dir=scripts_dir,
        maps_dir=maps_dir,
        lenses_path=lenses_path,
    )

    assert outcome == "error"


# ---------------------------------------------------------------------------
# run: step, tree integration
# ---------------------------------------------------------------------------


def _make_project_root(root: Path, name: str, lens: str) -> Path:
    """Mirror of make_project() in tests/test_tree.py — a bare project root."""
    p = root / name
    p.mkdir(parents=True)
    (p / "project.yaml").write_text(f"lens: {lens}\n", encoding="utf-8")
    return p


def test_run_step_flat_expansion(tmp_path, monkeypatch):
    scripts_dir = tmp_path / "scripts"
    lenses_path = tmp_path / "lenses.json"
    _save_lens(lenses_path)
    _write_script(scripts_dir, "A", """\
        lens: L
        steps:
          - type: "a"
          - run: B
          - type: "c"
    """)
    _write_script(scripts_dir, "B", """\
        lens: L
        steps:
          - type: "b"
    """)

    fake_backend = FakeBackend()
    monkeypatch.setattr(runner, "DesktopBackend", lambda: fake_backend)

    outcome = runner.run_script(
        "A",
        show_border=False,
        scripts_dir=scripts_dir,
        lenses_path=lenses_path,
        projects_dir=tmp_path / "projects",
    )

    assert outcome == "done"
    assert fake_backend.calls == [
        ("type_text", "a"),
        ("type_text", "b"),
        ("type_text", "c"),
    ]


def test_run_cycle_returns_error(tmp_path, monkeypatch):
    scripts_dir = tmp_path / "scripts"
    lenses_path = tmp_path / "lenses.json"
    _save_lens(lenses_path)
    _write_script(scripts_dir, "A", """\
        lens: L
        steps:
          - run: A
    """)

    monkeypatch.setattr(runner, "DesktopBackend", lambda: FakeBackend())

    outcome = runner.run_script(
        "A",
        show_border=False,
        scripts_dir=scripts_dir,
        lenses_path=lenses_path,
        projects_dir=tmp_path / "projects",
    )

    assert outcome == "error"


def test_run_depth_cap_returns_error(tmp_path, monkeypatch):
    scripts_dir = tmp_path / "scripts"
    lenses_path = tmp_path / "lenses.json"
    _save_lens(lenses_path)
    for i in range(1, 10):
        _write_script(scripts_dir, f"s{i}", f"""\
            lens: L
            steps:
              - run: s{i + 1}
        """)
    _write_script(scripts_dir, "s10", """\
        lens: L
        steps:
          - type: "x"
    """)

    monkeypatch.setattr(runner, "DesktopBackend", lambda: FakeBackend())

    outcome = runner.run_script(
        "s1",
        show_border=False,
        scripts_dir=scripts_dir,
        lenses_path=lenses_path,
        projects_dir=tmp_path / "projects",
    )

    assert outcome == "error"


def test_tree_script_uses_project_lens_and_override(tmp_path, monkeypatch):
    projects_dir = tmp_path / "projects"
    p = _make_project_root(projects_dir, "uma", "uma")
    (p / "buttons.json").write_text('{"go": {"point": [2, 2]}}', encoding="utf-8")
    daily = p / "daily"
    daily.mkdir()
    (daily / "buttons.json").write_text('{"go": {"point": [9, 9]}}', encoding="utf-8")
    (daily / "task.yaml").write_text("steps:\n  - tap: go\n", encoding="utf-8")

    lenses_path = tmp_path / "lenses.json"
    lens_store.save(Lens(name="uma", x=100, y=200, w=50, h=50), path=lenses_path)

    fake_backend = FakeBackend()
    monkeypatch.setattr(runner, "DesktopBackend", lambda: fake_backend)

    outcome = runner.run_script(
        "uma/daily/task",
        show_border=False,
        scripts_dir=tmp_path / "scripts",
        lenses_path=lenses_path,
        projects_dir=projects_dir,
    )

    assert outcome == "done"
    assert fake_backend.calls == [("click", 109, 209, "left")]


def test_tree_shared_script_lexical_buttons(tmp_path, monkeypatch):
    projects_dir = tmp_path / "projects"
    p = _make_project_root(projects_dir, "uma", "uma")
    (p / "buttons.json").write_text('{"back": {"point": [1, 1]}}', encoding="utf-8")
    (p / "scripts").mkdir()
    (p / "scripts" / "home.yaml").write_text("steps:\n  - tap: back\n", encoding="utf-8")

    child = p / "daily"
    child.mkdir()
    (child / "buttons.json").write_text('{"back": {"point": [9, 9]}}', encoding="utf-8")
    (child / "task.yaml").write_text("steps:\n  - run: home\n", encoding="utf-8")

    lenses_path = tmp_path / "lenses.json"
    lens_store.save(Lens(name="uma", x=100, y=200, w=50, h=50), path=lenses_path)

    fake_backend = FakeBackend()
    monkeypatch.setattr(runner, "DesktopBackend", lambda: fake_backend)

    outcome = runner.run_script(
        "uma/daily/task",
        show_border=False,
        scripts_dir=tmp_path / "scripts",
        lenses_path=lenses_path,
        projects_dir=projects_dir,
    )

    assert outcome == "done"
    assert fake_backend.calls == [("click", 101, 201, "left")]


def test_tree_script_with_lens_key_errors(tmp_path, monkeypatch):
    projects_dir = tmp_path / "projects"
    p = _make_project_root(projects_dir, "uma", "uma")
    (p / "task.yaml").write_text("lens: x\nsteps: []\n", encoding="utf-8")

    lenses_path = tmp_path / "lenses.json"
    lens_store.save(Lens(name="uma", x=0, y=0, w=10, h=10), path=lenses_path)

    monkeypatch.setattr(runner, "DesktopBackend", lambda: FakeBackend())

    outcome = runner.run_script(
        "uma/task",
        show_border=False,
        scripts_dir=tmp_path / "scripts",
        lenses_path=lenses_path,
        projects_dir=projects_dir,
    )

    assert outcome == "error"


def test_bare_name_ambiguous_errors(tmp_path, monkeypatch):
    projects_dir = tmp_path / "projects"
    p = _make_project_root(projects_dir, "uma", "uma")
    (p / "dup.yaml").write_text("steps: []\n", encoding="utf-8")

    scripts_dir = tmp_path / "scripts"
    _write_script(scripts_dir, "dup", """\
        lens: L
        steps: []
    """)

    lenses_path = tmp_path / "lenses.json"
    _save_lens(lenses_path)

    monkeypatch.setattr(runner, "DesktopBackend", lambda: FakeBackend())

    outcome = runner.run_script(
        "dup",
        show_border=False,
        scripts_dir=scripts_dir,
        lenses_path=lenses_path,
        projects_dir=projects_dir,
    )

    assert outcome == "error"


def test_max_steps_precedence(tmp_path, monkeypatch):
    projects_dir = tmp_path / "projects"
    p = _make_project_root(projects_dir, "uma", "uma")
    (p / "project.yaml").write_text("lens: uma\nmax-steps-per-goal: 5\n", encoding="utf-8")
    (p / "task.yaml").write_text('steps:\n  - goal: "g"\n', encoding="utf-8")

    lenses_path = tmp_path / "lenses.json"
    lens_store.save(Lens(name="uma", x=0, y=0, w=10, h=10), path=lenses_path)

    recorded = []

    def fake_run(goal, lens, max_steps, show_grid, show_border):
        recorded.append(max_steps)
        return "done"

    monkeypatch.setattr(runner.orchestrator, "run", fake_run)
    monkeypatch.setattr(runner, "DesktopBackend", lambda: FakeBackend())

    outcome = runner.run_script(
        "uma/task",
        max_steps_per_goal=None,
        show_border=False,
        scripts_dir=tmp_path / "scripts",
        lenses_path=lenses_path,
        projects_dir=projects_dir,
    )
    assert outcome == "done"
    assert recorded == [5]

    outcome = runner.run_script(
        "uma/task",
        max_steps_per_goal=7,
        show_border=False,
        scripts_dir=tmp_path / "scripts",
        lenses_path=lenses_path,
        projects_dir=projects_dir,
    )
    assert outcome == "done"
    assert recorded == [5, 7]
