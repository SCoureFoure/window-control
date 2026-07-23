"""Tests for the access-border band geometry.

The load-bearing invariant: every band rect must lie OUTSIDE the lens rect, so
the on-screen border is never captured into the screenshot sent to Claude.
"""

from src.lens.border import band_rects


def _overlaps(a, b) -> bool:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah


def test_bands_never_overlap_lens():
    lens = (200, 300, 800, 600)
    for band in band_rects(lens, thickness=8):
        assert not _overlaps(band, lens), f"band {band} intrudes into lens {lens}"


def test_four_bands():
    assert len(band_rects((0, 0, 100, 100), thickness=5)) == 4


def test_origin_offset_is_subtracted():
    # A lens flush with the virtual-desktop origin maps to negative-inset bands
    # in surface-local space (top/left bands sit just off the top-left corner).
    bands = band_rects((50, 50, 100, 100), thickness=10, origin=(50, 50))
    top = bands[0]
    assert top == (-10, -10, 120, 10)


def test_frame_encloses_lens_bounds():
    lens = (10, 20, 40, 30)
    t = 4
    top, bottom, left, right = band_rects(lens, thickness=t)
    x, y, w, h = lens
    # inner edges are flush with the lens boundary
    assert top[1] + top[3] == y            # top band bottom edge == lens top
    assert bottom[1] == y + h              # bottom band top edge == lens bottom
    assert left[0] + left[2] == x          # left band right edge == lens left
    assert right[0] == x + w               # right band left edge == lens right
