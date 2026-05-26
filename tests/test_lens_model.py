"""Tests for the Lens dataclass and coord math."""

import pytest

from src.lens.model import Lens


def test_rect_origin_size():
    lens = Lens(name="x", x=100, y=200, w=800, h=600)
    assert lens.rect == (100, 200, 800, 600)
    assert lens.origin == (100, 200)
    assert lens.size == (800, 600)


def test_contains_rel():
    lens = Lens(name="x", x=0, y=0, w=10, h=10)
    assert lens.contains_rel(0, 0)
    assert lens.contains_rel(9, 9)
    assert not lens.contains_rel(10, 10)
    assert not lens.contains_rel(-1, 0)


def test_to_screen_adds_origin():
    lens = Lens(name="x", x=100, y=200, w=50, h=50)
    assert lens.to_screen(0, 0) == (100, 200)
    assert lens.to_screen(49, 49) == (149, 249)


def test_to_screen_rejects_out_of_bounds():
    lens = Lens(name="x", x=0, y=0, w=10, h=10)
    with pytest.raises(ValueError, match="outside lens"):
        lens.to_screen(10, 0)


def test_serialise_roundtrip():
    lens = Lens(name="myzone", x=5, y=6, w=7, h=8)
    assert Lens.from_dict(lens.to_dict()) == lens
