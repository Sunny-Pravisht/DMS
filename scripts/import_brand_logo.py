#!/usr/bin/env python
"""
Turn the supplied HARMAN logo into the variants the product needs.

The source is a JPEG on a white background, which is the wrong thing to put on
a navy sidebar: JPEG has no transparency, so it arrives as a white rectangle
with a logo in it. This produces, from that one file:

    harman.png        full colour, transparent  - light backgrounds
    harman-white.png  reversed to white         - dark mastheads and the sidebar
    harman-mark.png   square app mark           - favicon and small tiles

Cutting the white out is not a threshold. A hard cut leaves jagged edges; a
luminance key makes the cyan swoosh half-transparent because light colours look
like "nearly white" to it. What works is measuring each pixel's distance from
white, using that as the alpha, and then removing the white that the source
mixed into the anti-aliased edges. Without that last step every edge pixel keeps
a pale fringe, which reads as a halo the moment the logo sits on dark navy.

    python scripts/import_brand_logo.py [path/to/Harman_logo.jpg]
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
BRAND = ROOT / "frontend" / "ui" / "assets" / "brand"
SOURCE = BRAND / "_source_harman.jpg"

# How far from white a pixel must be before it counts as fully part of the
# logo. Small enough to keep thin strokes solid, large enough that the edges
# still ramp rather than staircase.
EDGE = 62.0

# Rendered wide enough to stay crisp on a high-density screen and in print.
WORDMARK_W = 960
MARK_SIZE = 512


def cut_white(img: Image.Image) -> Image.Image:
    """White background out, alpha in, no halo left behind."""
    img = img.convert("RGB")
    w, h = img.size
    out = Image.new("RGBA", (w, h))

    src = img.load()
    dst = out.load()

    for y in range(h):
        for x in range(w):
            r, g, b = src[x, y]
            # Distance from white, normalised into an alpha ramp.
            dr, dg, db = 255 - r, 255 - g, 255 - b
            dist = (dr * dr + dg * dg + db * db) ** 0.5
            a = dist / EDGE
            if a <= 0.004:
                dst[x, y] = (0, 0, 0, 0)
                continue
            if a > 1.0:
                a = 1.0

            if a >= 0.999:
                dst[x, y] = (r, g, b, 255)
            else:
                # The source blended this pixel with white. Undo that blend so
                # the colour is the logo's own, not a paler version of it.
                inv = 255.0 * (1.0 - a)
                dst[x, y] = (
                    max(0, min(255, int((r - inv) / a))),
                    max(0, min(255, int((g - inv) / a))),
                    max(0, min(255, int((b - inv) / a))),
                    int(a * 255),
                )
    return out


def trim(img: Image.Image, pad: int = 0) -> Image.Image:
    """Crop to what is actually drawn, so layout controls the whitespace."""
    box = img.getbbox()
    if not box:
        return img
    if pad:
        l, t, r, b = box
        box = (max(0, l - pad), max(0, t - pad),
               min(img.width, r + pad), min(img.height, b + pad))
    return img.crop(box)


def to_white(img: Image.Image) -> Image.Image:
    """
    The reversed lockup: same shape, every pixel white.

    Used wherever the logo sits on a dark band. Recolouring rather than
    supplying a second artwork file means the two can never drift apart.
    """
    alpha = img.getchannel("A")
    white = Image.new("RGBA", img.size, (255, 255, 255, 0))
    white.putalpha(alpha)
    return white


def find_letters(logo: Image.Image) -> tuple[tuple[int, int, int, int], list[tuple[int, int]]]:
    """
    Locate the wordmark's letters within the artwork.

    The letters are deep blue and the swoosh is cyan, so they separate cleanly
    by colour. Reading the shapes out of the file beats hard-coding crop
    fractions: swap the source artwork and this still finds the right glyph.

    Returns the letters' bounding box and the column span of each letter.
    """
    px = logo.load()
    w, h = logo.size
    cols = [0] * w
    rows = [0] * h

    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if a > 140 and b > 140 and g < 150 and r < 110:   # the letterform blue
                cols[x] += 1
                rows[y] += 1

    xs = [x for x, v in enumerate(cols) if v]
    ys = [y for y, v in enumerate(rows) if v]
    if not xs or not ys:
        return (0, 0, w, h), []

    runs, start = [], None
    for x in range(w):
        if cols[x] and start is None:
            start = x
        elif not cols[x] and start is not None:
            runs.append((start, x - 1))
            start = None
    if start is not None:
        runs.append((start, w - 1))

    return (xs[0], ys[0], xs[-1] + 1, ys[-1] + 1), runs


def square_mark(logo: Image.Image) -> Image.Image:
    """
    A square app mark: the logo's own H under its own arc, on the brand blue.

    A wordmark is illegible at 16 pixels, so the favicon and any small tile need
    something square. Rather than draw a new glyph, this lifts the real "H" and
    the top of the swoosh straight out of the supplied artwork, so the mark is
    the logo rather than a lookalike.
    """
    from PIL import ImageDraw

    size = MARK_SIZE
    tile = Image.new("RGBA", (size, size), (0, 0, 0, 0))

    plate = Image.new("RGBA", (size, size), (0x00, 0x66, 0xC2, 255))
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size - 1, size - 1],
                                           radius=int(size * 0.235), fill=255)
    plate.putalpha(mask)
    tile.alpha_composite(plate)

    (lx0, ly0, lx1, ly1), runs = find_letters(logo)
    w, h = logo.size

    # The arc above the wordmark: thin, and mostly a cue at small sizes.
    arc = to_white(trim(logo.crop((lx0, 0, lx1, max(1, ly0 - 2)))))
    if arc.width > 4:
        arc_w = int(size * 0.60)
        arc = arc.resize((arc_w, max(1, int(arc.height * arc_w / arc.width))), Image.LANCZOS)
        tile.alpha_composite(arc, (int((size - arc.width) / 2), int(size * 0.20)))

    # The first letter run is the H.
    if runs:
        hx0, hx1 = runs[0]
        letter = to_white(trim(logo.crop((hx0, ly0, hx1 + 1, ly1))))
        letter_h = int(size * 0.40)
        letter = letter.resize(
            (max(1, int(letter.width * letter_h / letter.height)), letter_h), Image.LANCZOS)
        tile.alpha_composite(letter, (int((size - letter.width) / 2), int(size * 0.44)))

    return tile


def main() -> int:
    source = Path(sys.argv[1]) if len(sys.argv) > 1 else SOURCE
    if not source.exists():
        print(f"Source logo not found: {source}")
        return 1

    BRAND.mkdir(parents=True, exist_ok=True)
    print(f"Reading {source.name}")

    raw = Image.open(source)
    cut = trim(cut_white(raw))
    print(f"  cut to {cut.size} with transparency")

    # Full colour, for light backgrounds.
    wordmark = cut.resize(
        (WORDMARK_W, max(1, int(cut.height * WORDMARK_W / cut.width))), Image.LANCZOS)
    wordmark.save(BRAND / "harman.png", "PNG", optimize=True)
    print(f"  + harman.png        {wordmark.size}")

    # Reversed, for dark mastheads.
    to_white(wordmark).save(BRAND / "harman-white.png", "PNG", optimize=True)
    print(f"  + harman-white.png  {wordmark.size}")

    # Square mark.
    mark = square_mark(cut)
    mark.save(BRAND / "harman-mark.png", "PNG", optimize=True)
    print(f"  + harman-mark.png   {mark.size}")

    # A small favicon, so the browser tab is not scaling a 512px image.
    mark.resize((64, 64), Image.LANCZOS).save(BRAND / "harman-mark-64.png", "PNG", optimize=True)
    print("  + harman-mark-64.png (64, 64)")

    print("\nDone. The SVG placeholders for HARMAN are no longer referenced; the "
          "PNGs above are the real artwork.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
