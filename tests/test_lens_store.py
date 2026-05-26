"""Tests for lens persistence."""

from pathlib import Path

import pytest

from src.lens import store
from src.lens.model import Lens


@pytest.fixture()
def tmp_lenses(tmp_path: Path) -> Path:
    return tmp_path / "lenses.json"


def test_save_and_load_roundtrip(tmp_lenses: Path):
    lens = Lens(name="alpha", x=10, y=20, w=300, h=400)
    store.save(lens, path=tmp_lenses)
    loaded = store.load("alpha", path=tmp_lenses)
    assert loaded == lens


def test_load_missing_returns_none(tmp_lenses: Path):
    assert store.load("ghost", path=tmp_lenses) is None


def test_list_names_sorted(tmp_lenses: Path):
    store.save(Lens("beta", 0, 0, 10, 10), path=tmp_lenses)
    store.save(Lens("alpha", 0, 0, 10, 10), path=tmp_lenses)
    assert store.list_names(path=tmp_lenses) == ["alpha", "beta"]


def test_delete_removes_entry(tmp_lenses: Path):
    store.save(Lens("alpha", 0, 0, 10, 10), path=tmp_lenses)
    assert store.delete("alpha", path=tmp_lenses) is True
    assert store.load("alpha", path=tmp_lenses) is None
    assert store.delete("alpha", path=tmp_lenses) is False
