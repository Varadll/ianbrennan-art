#!/usr/bin/env python3
"""
Extract catalog metadata from Ian Brennan Portfolio PDF.

For every page, finds all images and all text blocks (with bounding boxes).
For each image, locates the nearest text block(s) and parses out:
  - title
  - year
  - medium
  - dimensions (cm + inches)

Outputs scripts/catalog.json — a flat list of records, one per image+caption pair.

Run:
    python3 scripts/extract-catalog.py
"""

import json
import re
import sys
from pathlib import Path

import fitz  # PyMuPDF

PDF_PATH = Path("/Users/varad/Documents/Freelance/art/Ian Brennan Portfolio (High Resolution).pdf")
OUT_PATH = Path(__file__).resolve().parent / "catalog.json"

# Regexes for parsing caption text
DIM_RE = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*[x×]\s*(\d+(?:[.,]\d+)?)\s*(cm|in|inches|inch|mm|\"|''|\u201d)",
    re.IGNORECASE,
)
YEAR_RE = re.compile(r"\b(19\d{2}|20\d{2})\b")
MEDIUM_HINTS = re.compile(
    r"(oil|acrylic|mixed media|watercolour|watercolor|gouache|charcoal|ink|pencil|"
    r"pastel|on canvas|on paper|on board|on linen|on panel)",
    re.IGNORECASE,
)


def normalize(text: str) -> str:
    return " ".join(text.replace("\u00a0", " ").split()).strip()


def parse_caption(text: str) -> dict:
    """Pull title/year/medium/dimensions from a caption blob."""
    text = normalize(text)
    out = {"raw": text, "title": None, "year": None, "medium": None,
           "dim_w": None, "dim_h": None, "dim_unit": None,
           "dim_cm": None, "dim_in": None}

    if not text:
        return out

    # Year
    m = YEAR_RE.search(text)
    if m:
        out["year"] = m.group(1)

    # Dimensions
    m = DIM_RE.search(text)
    if m:
        w = float(m.group(1).replace(",", "."))
        h = float(m.group(2).replace(",", "."))
        unit_raw = m.group(3).lower()
        if unit_raw in ('"', "''", "\u201d", "in", "inch", "inches"):
            unit = "in"
        elif unit_raw == "mm":
            unit = "mm"
        else:
            unit = "cm"
        out["dim_w"], out["dim_h"], out["dim_unit"] = w, h, unit

        # Convert to cm + inches
        if unit == "cm":
            out["dim_cm"] = (round(w, 1), round(h, 1))
            out["dim_in"] = (round(w / 2.54, 1), round(h / 2.54, 1))
        elif unit == "in":
            out["dim_in"] = (round(w, 1), round(h, 1))
            out["dim_cm"] = (round(w * 2.54, 1), round(h * 2.54, 1))
        elif unit == "mm":
            out["dim_cm"] = (round(w / 10, 1), round(h / 10, 1))
            out["dim_in"] = (round((w / 10) / 2.54, 1), round((h / 10) / 2.54, 1))

    # Medium
    m = MEDIUM_HINTS.search(text)
    if m:
        # Capture a short phrase around the medium hint
        start = max(0, m.start() - 0)
        end = min(len(text), m.end() + 30)
        # Take the sentence-ish slice and strip noise
        slice_ = text[start:end]
        # Stop at common delimiters
        for delim in [",", "  ", " - ", " — ", " · "]:
            if delim in slice_:
                pass
        out["medium"] = slice_.split(",")[0].strip()

    # Title parsing — the captions in this PDF follow:
    #   "Title, YEAR Medium WxH unit [pageNum]"
    # or
    #   "Title YEAR Medium WxH unit [pageNum]"
    # Title is everything before the year. Strip trailing comma.
    if out["year"]:
        idx = text.find(out["year"])
        if idx > 0:
            title = text[:idx].rstrip(", ").strip()
            # Bail out if title is suspiciously long
            if 1 < len(title) < 100:
                out["title"] = title

    return out


def rect_distance(r1, r2) -> float:
    """Min distance between two fitz.Rect objects."""
    dx = max(0, max(r1.x0 - r2.x1, r2.x0 - r1.x1))
    dy = max(0, max(r1.y0 - r2.y1, r2.y0 - r1.y1))
    return (dx * dx + dy * dy) ** 0.5


def extract():
    if not PDF_PATH.exists():
        sys.exit(f"PDF not found: {PDF_PATH}")

    doc = fitz.open(PDF_PATH)
    records = []

    for page_num, page in enumerate(doc, start=1):
        page_rect = page.rect

        # Image rectangles
        image_rects = []
        for img in page.get_images(full=True):
            xref = img[0]
            for r in page.get_image_rects(xref):
                image_rects.append({"xref": xref, "rect": r})

        if not image_rects:
            continue

        # Text blocks with bounding boxes
        text_blocks = []
        for blk in page.get_text("blocks"):
            x0, y0, x1, y1, txt, *_ = blk
            txt = normalize(txt)
            if not txt:
                continue
            text_blocks.append({"rect": fitz.Rect(x0, y0, x1, y1), "text": txt})

        # For each image, find nearest text block(s) within a reasonable radius
        for img in image_rects:
            ir = img["rect"]
            # Skip images that are larger than ~70% of page area (likely full-bleed hero, not catalog thumb)
            img_area = ir.width * ir.height
            page_area = page_rect.width * page_rect.height
            is_hero = img_area > page_area * 0.55

            # Candidates: text blocks within a vertical band near the image
            scored = []
            for tb in text_blocks:
                d = rect_distance(ir, tb["rect"])
                if d > max(page_rect.width, page_rect.height) * 0.35:
                    continue
                scored.append((d, tb))
            scored.sort(key=lambda s: s[0])

            # Combine the closest 1-3 text blocks into a caption
            caption_parts = [tb["text"] for _, tb in scored[:3]]
            caption = "\n".join(caption_parts)
            parsed = parse_caption(caption)

            records.append({
                "page": page_num,
                "image_xref": img["xref"],
                "image_rect": [round(ir.x0, 1), round(ir.y0, 1),
                               round(ir.x1, 1), round(ir.y1, 1)],
                "image_size": [round(ir.width, 1), round(ir.height, 1)],
                "is_hero": is_hero,
                "caption": parsed,
                "nearest_text": caption_parts,
            })

    OUT_PATH.write_text(json.dumps(records, indent=2, ensure_ascii=False))
    print(f"Wrote {len(records)} records to {OUT_PATH}")

    # Print a quick summary
    with_dims = [r for r in records if r["caption"]["dim_cm"]]
    with_titles = [r for r in records if r["caption"]["title"]]
    print(f"  {len(with_dims)} records have parsed dimensions")
    print(f"  {len(with_titles)} records have parsed titles")


if __name__ == "__main__":
    extract()
