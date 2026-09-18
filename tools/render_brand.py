#!/usr/bin/env python3
"""Regenerate custom_components/ha_syslog/brand/*.png from one geometry.

Run with Pillow available: `python3 tools/render_brand.py`

The mark is drawn in code rather than rasterised from `icon.svg` so this has
no cairo/rsvg dependency; `icon.svg` is the readable source of the same
geometry and the two must be kept in step by hand.

Home Assistant serves these directly for custom integrations (see
custom_components/ha_syslog/brand/README.md), so the filenames are core's and
not arbitrary.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

BLUE = (24, 188, 242, 255)
PAPER = (244, 247, 250, 255)
WHITE = (255, 255, 255, 255)
FOLD = (159, 179, 200, 255)
SLATE = (44, 62, 80, 255)
LIGHT_PLATE = (236, 240, 243, 255)
RACK_SLOT = (44, 62, 80, 217)

BRAND_DIR = Path(__file__).resolve().parents[1] / "custom_components/ha_syslog/brand"


def render(px: int, *, dark: bool = False, wide: bool = False) -> Image.Image:
    """Draw the mark.

    `wide` gives the logo a 1.6:1 canvas, because Home Assistant shows logos
    in wide slots and a square image there sits oddly. `dark` swaps the plate
    for a light one so the mark stays legible against a dark theme header
    rather than becoming a dark square on a dark background.
    """
    plate = LIGHT_PLATE if dark else SLATE
    page = WHITE if dark else PAPER
    width = int(px * 1.6) if wide else px
    scale = px / 512
    offset = (width - px) / 2

    def s(value: float) -> float:
        return value * scale

    def x(value: float) -> float:
        return value * scale + offset

    img = Image.new("RGBA", (width, px), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    draw.rounded_rectangle([offset, 0, offset + px - 1, px - 1], s(96), fill=plate)

    # log page, with a folded corner
    draw.polygon(
        [
            (x(72), s(140)),
            (x(188), s(140)),
            (x(232), s(184)),
            (x(232), s(372)),
            (x(72), s(372)),
        ],
        fill=page,
    )
    draw.polygon([(x(188), s(140)), (x(232), s(184)), (x(188), s(184))], fill=FOLD)
    for line_y, line_w in ((212, 68), (246, 112), (280, 88), (314, 112)):
        draw.rounded_rectangle(
            [x(96), s(line_y), x(96 + line_w), s(line_y + 14)], s(7), fill=SLATE
        )

    # packet in flight, on the same axis as page and rack
    draw.rounded_rectangle([x(252), s(244), x(310), s(268)], s(12), fill=BLUE)
    draw.polygon([(x(306), s(226)), (x(352), s(256)), (x(306), s(286))], fill=BLUE)

    # server rack
    draw.rounded_rectangle([x(356), s(140), x(440), s(372)], s(16), fill=BLUE)
    for slot_y in (164, 200, 272, 308):
        draw.rounded_rectangle(
            [x(372), s(slot_y), x(424), s(slot_y + 16)], s(8), fill=RACK_SLOT
        )
    for led_x in (382, 410):
        draw.ellipse([x(led_x - 8), s(236), x(led_x + 8), s(252)], fill=page)

    return img


VARIANTS = {
    "icon.png": {"px": 256},
    "icon@2x.png": {"px": 512},
    "logo.png": {"px": 256, "wide": True},
    "logo@2x.png": {"px": 512, "wide": True},
    "dark_icon.png": {"px": 256, "dark": True},
    "dark_icon@2x.png": {"px": 512, "dark": True},
    "dark_logo.png": {"px": 256, "dark": True, "wide": True},
    "dark_logo@2x.png": {"px": 512, "dark": True, "wide": True},
}


def main() -> None:
    BRAND_DIR.mkdir(parents=True, exist_ok=True)
    for name, kwargs in VARIANTS.items():
        px = kwargs.pop("px")
        image = render(px, **kwargs)
        path = BRAND_DIR / name
        image.save(path)
        print(f"{name:20s} {image.size}")


if __name__ == "__main__":
    main()
