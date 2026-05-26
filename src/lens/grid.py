"""Coordinate-grid overlay painted onto the captured image.

The grid is a perception aid: the model can read approximate coordinates off
the labelled gridlines instead of guessing pixel positions from raw imagery.

Draws light gridlines every `spacing` pixels and labels every `label_every`th
intersection. Coordinates are lens-relative (matching what the model emits).
"""

from __future__ import annotations

from PIL import Image, ImageDraw, ImageFont

DEFAULT_SPACING = 50
DEFAULT_LABEL_EVERY = 2
LINE_COLOR = (255, 255, 0, 90)
BOLD_COLOR = (255, 255, 0, 160)
LABEL_COLOR = (255, 255, 0, 220)
LABEL_BG = (0, 0, 0, 140)


def draw_grid(
    img: Image.Image,
    spacing: int = DEFAULT_SPACING,
    label_every: int = DEFAULT_LABEL_EVERY,
) -> Image.Image:
    """Return a new RGB image with a coordinate grid drawn over the original."""
    if spacing <= 0:
        raise ValueError("spacing must be positive")

    base = img.convert("RGBA")
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    w, h = base.size

    try:
        font = ImageFont.truetype("arial.ttf", 11)
    except OSError:
        font = ImageFont.load_default()

    for i, x in enumerate(range(0, w, spacing)):
        color = BOLD_COLOR if i % label_every == 0 else LINE_COLOR
        draw.line([(x, 0), (x, h)], fill=color, width=1)
    for i, y in enumerate(range(0, h, spacing)):
        color = BOLD_COLOR if i % label_every == 0 else LINE_COLOR
        draw.line([(0, y), (w, y)], fill=color, width=1)

    for ix, x in enumerate(range(0, w, spacing)):
        for iy, y in enumerate(range(0, h, spacing)):
            if ix % label_every != 0 or iy % label_every != 0:
                continue
            label = f"{x},{y}"
            bbox = draw.textbbox((x + 2, y + 2), label, font=font)
            pad = 2
            draw.rectangle(
                (bbox[0] - pad, bbox[1] - pad, bbox[2] + pad, bbox[3] + pad),
                fill=LABEL_BG,
            )
            draw.text((x + 2, y + 2), label, fill=LABEL_COLOR, font=font)

    return Image.alpha_composite(base, overlay).convert("RGB")
