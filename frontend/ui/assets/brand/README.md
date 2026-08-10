# Brand assets

Two kinds of file live here, and they are maintained differently.

## The HARMAN marks — real artwork

Cut from the supplied `_source_harman.jpg` by `scripts/import_brand_logo.py`.
The source is a JPEG on a white card, so the script keys the white away by
distance-from-white and un-premultiplies the result: a plain threshold leaves a
jagged edge, and a luminance key turns the cyan swoosh half-transparent.

| File | Used for |
|---|---|
| `harman.png` | Full-colour wordmark: sign-in screen, light letterheads |
| `harman-white.png` | Reversed wordmark, for a dark masthead band |
| `harman-mark.png` | Square app mark: brand-blue tile, white arc and H |
| `harman-mark-64.png` | The same mark at favicon size |

`seed_brand_assets.py` deliberately does **not** build these. If it did,
`--force` would overwrite the company's own logo with a hand-drawn stand-in.
To re-cut them after replacing the source image:

    python scripts/import_brand_logo.py

## The vendor marks — stand-ins

Drawn here so the Studio, the letterhead templates and the rendered PDFs have
something to show without shipping a third party's trademarked artwork.

| File | Used for |
|---|---|
| `maruti-suzuki.svg` | Maruti Suzuki vendor letterhead |
| `mahindra.svg` | Mahindra vendor letterhead |
| `tata.svg`, `tata-white.svg` | Tata Motors vendor letterhead |
| `stamp-approved.svg` | "Approved" seal, insertable from the image library |
| `stamp-confidential.svg` | "Confidential" seal, insertable from the image library |

`scripts/seed_brand_assets.py` renders a PNG next to each of these. The web
canvas uses the SVG where one exists; the PDF renderer always embeds the PNG,
because ReportLab does not read SVG. `doc_templates._logo()` picks whichever is
actually on disk, so dropping in official artwork needs no code change — keep
the filename and everything downstream follows.
