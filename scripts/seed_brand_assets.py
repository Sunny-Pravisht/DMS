#!/usr/bin/env python
"""
Render a PNG next to every brand SVG in frontend/ui/assets/brand.

The web canvas uses the SVG directly. ReportLab cannot read SVG, so the PDF
renderer embeds these PNGs instead. Both are produced from the same intent, so
what you see in the Studio is what lands in the PDF.

Nothing here needs a design tool or a network call: the marks are drawn with
Pillow using whatever sans-serif the host provides.

    python scripts/seed_brand_assets.py            # write any missing PNGs
    python scripts/seed_brand_assets.py --force    # redraw all of them
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
BRAND_DIR = ROOT / "frontend" / "ui" / "assets" / "brand"

# Scale everything up and let the PDF/browser scale down: a mark placed 22 mm
# wide on A4 at 300 dpi wants roughly 260 px, so 4x that keeps it crisp.
SCALE = 4

# Font candidates, best first. Windows first because that is where this runs
# during development; the Linux paths cover the Docker image.
BOLD_FONTS = [
    "C:/Windows/Fonts/segoeuib.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
]
REGULAR_FONTS = [
    "C:/Windows/Fonts/segoeui.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
]


def _font(candidates: list[str], size: int) -> ImageFont.FreeTypeFont:
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


def bold(size: int):
    return _font(BOLD_FONTS, size)


def regular(size: int):
    return _font(REGULAR_FONTS, size)


def _canvas(w: int, h: int) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGBA", (w * SCALE, h * SCALE), (255, 255, 255, 0))
    return img, ImageDraw.Draw(img)


def _tracked(draw, xy, text, font, fill, tracking=0):
    """Draw text with letter-spacing, which Pillow has no option for."""
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, font=font, fill=fill)
        x += draw.textlength(ch, font=font) + tracking
    return x


# ---------------------------------------------------------------- the marks


def wordmark(primary: str, secondary: str, colors: tuple, glyph) -> Image.Image:
    """A logo mark on the left, a two-line wordmark on the right."""
    img, d = _canvas(320, 72)
    s = SCALE
    glyph(img, d, s)
    d = ImageDraw.Draw(img)
    x = _tracked(d, (70 * s, 18 * s), primary, bold(30 * s), colors[0], tracking=1.2 * s)
    _tracked(d, (72 * s, 48 * s), secondary, regular(11 * s), colors[1], tracking=2.2 * s)
    return img.crop((0, 0, max(int(x) + 6 * s, 260 * s), 72 * s))




def tata_glyph_white(img, d, s):
    """Reversed Tata mark: a solid white disc carrying the blue device."""
    blue = (0x48, 0x6A, 0xAE, 255)
    d.ellipse([14 * s, 14 * s, 54 * s, 54 * s], fill=(255, 255, 255, 255))
    d.pieslice([18 * s, 18 * s, 50 * s, 50 * s], start=180, end=360, fill=blue)
    d.ellipse([26 * s, 28 * s, 42 * s, 46 * s], fill=(255, 255, 255, 255))


def maruti_glyph(img, d, s):
    red, blue = (0xE0, 0x1E, 0x26, 255), (0x00, 0x55, 0x9B, 255)
    d.polygon([(8 * s, 46 * s), (20 * s, 20 * s), (32 * s, 46 * s), (26 * s, 46 * s),
               (20 * s, 32 * s), (14 * s, 46 * s)], fill=red)
    d.polygon([(30 * s, 46 * s), (42 * s, 20 * s), (54 * s, 46 * s), (48 * s, 46 * s),
               (42 * s, 32 * s), (36 * s, 46 * s)], fill=blue)


def mahindra_glyph(img, d, s):
    red = (0xC8, 0x10, 0x2E, 255)
    d.polygon([(12 * s, 56 * s), (12 * s, 24 * s), (22 * s, 24 * s), (28 * s, 40 * s),
               (34 * s, 24 * s), (44 * s, 24 * s), (44 * s, 56 * s), (36 * s, 56 * s),
               (36 * s, 34 * s), (30 * s, 50 * s), (26 * s, 50 * s), (20 * s, 34 * s),
               (20 * s, 56 * s)], fill=red)


def tata_glyph(img, d, s):
    blue = (0x48, 0x6A, 0xAE, 255)
    d.ellipse([14 * s, 14 * s, 54 * s, 54 * s], fill=blue)
    d.pieslice([18 * s, 18 * s, 50 * s, 50 * s], start=180, end=360, fill=(255, 255, 255, 255))
    d.ellipse([26 * s, 28 * s, 42 * s, 46 * s], fill=blue)


def stamp_approved() -> Image.Image:
    img, d = _canvas(200, 200)
    s = SCALE
    blue = (0x00, 0x64, 0x99, 255)
    bright = (0x00, 0xA7, 0xE4, 255)
    d.ellipse([14 * s, 14 * s, 186 * s, 186 * s], outline=blue, width=5 * s)
    d.ellipse([26 * s, 26 * s, 174 * s, 174 * s], outline=blue, width=2 * s)
    f = bold(30 * s)
    w = d.textlength("APPROVED", font=f) + 8 * 2 * s
    _tracked(d, (100 * s - w / 2, 62 * s), "APPROVED", f, blue, tracking=2 * s)
    d.line([(42 * s, 102 * s), (158 * s, 102 * s)], fill=blue, width=3 * s)
    f2 = bold(14 * s)
    w2 = d.textlength("HARMAN . QUALITY", font=f2) + 15 * 3 * s
    _tracked(d, (100 * s - w2 / 2, 112 * s), "HARMAN . QUALITY", f2, bright, tracking=3 * s)
    f3 = regular(11 * s)
    w3 = d.textlength("DOCUMENT CONTROL", font=f3) + 16 * 2.4 * s
    _tracked(d, (100 * s - w3 / 2, 134 * s), "DOCUMENT CONTROL", f3, blue, tracking=2.4 * s)
    return img.rotate(12, resample=Image.BICUBIC, expand=False)


def stamp_confidential() -> Image.Image:
    img, d = _canvas(300, 120)
    s = SCALE
    red = (0xCE, 0x2F, 0x35, 255)
    d.rounded_rectangle([12 * s, 16 * s, 288 * s, 104 * s], radius=8 * s, outline=red, width=5 * s)
    d.rounded_rectangle([22 * s, 26 * s, 278 * s, 94 * s], radius=4 * s, outline=red, width=2 * s)
    f = bold(32 * s)
    w = d.textlength("CONFIDENTIAL", font=f) + 12 * 4 * s
    _tracked(d, (150 * s - w / 2, 38 * s), "CONFIDENTIAL", f, red, tracking=4 * s)
    f2 = regular(11 * s)
    w2 = d.textlength("INTERNAL USE ONLY", font=f2) + 17 * 3 * s
    _tracked(d, (150 * s - w2 / 2, 76 * s), "INTERNAL USE ONLY", f2, red, tracking=3 * s)
    return img.rotate(8, resample=Image.BICUBIC, expand=False)


NAVY = (0x0A, 0x2A, 0x3D, 255)
BRIGHT = (0x00, 0xA7, 0xE4, 255)
WHITE = (255, 255, 255, 255)
PALE_BLUE = (0x7F, 0xD6, 0xF4, 255)

# The HARMAN marks are deliberately absent. They are no longer drawn here —
# harman.png, harman-white.png and harman-mark.png are cut from the real
# supplied artwork by scripts/import_brand_logo.py. Re-adding them would let
# --force replace the company's own logo with a hand-drawn stand-in.
BUILDERS = {
    # Reversed lockups. A template with a filled masthead uses these, because a
    # dark wordmark on a dark band renders as nothing at all.
    "tata-white": lambda: wordmark("TATA", "MOTORS",
                                   (WHITE, (0xDC, 0xE5, 0xF5, 255)), tata_glyph_white),
    "maruti-suzuki": lambda: wordmark(
        "MARUTI SUZUKI", "WAY OF LIFE",
        ((0x00, 0x55, 0x9B, 255), (0xE0, 0x1E, 0x26, 255)), maruti_glyph),
    "mahindra": lambda: wordmark(
        "MAHINDRA", "RISE.",
        ((0xC8, 0x10, 0x2E, 255), (0x5B, 0x67, 0x70, 255)), mahindra_glyph),
    "tata": lambda: wordmark(
        "TATA", "MOTORS",
        ((0x48, 0x6A, 0xAE, 255), (0x5B, 0x67, 0x70, 255)), tata_glyph),
    "stamp-approved": stamp_approved,
    "stamp-confidential": stamp_confidential,
}


def main() -> int:
    force = "--force" in sys.argv
    BRAND_DIR.mkdir(parents=True, exist_ok=True)

    written = 0
    for name, build in BUILDERS.items():
        target = BRAND_DIR / f"{name}.png"
        if target.exists() and not force:
            print(f"  · {target.name} already there")
            continue
        build().save(target, "PNG")
        written += 1
        print(f"  + {target.name}")

    print(f"\n{written} mark(s) written to {BRAND_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
