"""Crop the rendered glyph, then centre it on a 1024 icon canvas.

`render_emoji.swift` deliberately draws small inside a large canvas so nothing
gets clipped: the glyph therefore ends up off-centre, surrounded by emptiness,
at a scale that depends on the font. No icon can be made from that directly.

This module makes up for it by trusting the only reliable landmark — the alpha
channel's bounding box, that is, the pixels actually drawn. The glyph is brought
down to `CONTENT` px then centred, which makes the result independent of the
font size chosen upstream.

usage: python compose_icon.py <source.png> <output.png>
"""

import sys

from PIL import Image

CANVAS = 1024
# macOS lets free-form icons breathe: without this margin, the icon looks
# bigger than its neighbours in the Dock.
CONTENT = 840
# Near-transparent pixels are antialiasing halo, not drawing. Counting them
# would widen the bounding box and shift the centring.
ALPHA_THRESHOLD = 8


def compose(src: str, dst: str) -> None:
    image = Image.open(src).convert("RGBA")
    mask = image.getchannel("A").point(lambda v: 255 if v > ALPHA_THRESHOLD else 0)
    bbox = mask.getbbox()
    if bbox is None:
        raise SystemExit(f"{src}: no pixel drawn, nothing to crop")

    glyph = image.crop(bbox)
    scale = CONTENT / max(glyph.size)
    glyph = glyph.resize(
        (round(glyph.width * scale), round(glyph.height * scale)),
        Image.LANCZOS,
    )

    icon = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    icon.paste(glyph, ((CANVAS - glyph.width) // 2, (CANVAS - glyph.height) // 2))
    icon.save(dst)
    print(f"wrote {dst} (crop {bbox}, glyph {glyph.size})")


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: python compose_icon.py <source.png> <output.png>")
    compose(sys.argv[1], sys.argv[2])


if __name__ == "__main__":
    main()
