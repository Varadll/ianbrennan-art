#!/usr/bin/env python3
"""
Apply truth.json into markdown frontmatter:
  - Add widthCm / heightCm numeric fields (for View on the Wall scaling)
  - Normalise `dimensions` string to "W x H cm (W x H in)" format
  - Fix any year mismatches (single year only — preserve ranges like "2022-24")
"""
import json
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ARTWORKS_DIR = ROOT / "src" / "content" / "artworks"
TRUTH = json.loads((ROOT / "scripts" / "truth.json").read_text())


def slugify(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = s.lower()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s_-]+", "-", s).strip("-")
    return s


def fmt_num(n: float) -> str:
    return f"{n:g}"


def update_file(md: Path):
    text = md.read_text()
    m = re.match(r"---\n(.*?)\n---\n(.*)", text, re.DOTALL)
    if not m:
        return False
    fm_block, body = m.group(1), m.group(2)

    # Parse frontmatter (simple)
    fm = {}
    fm_order = []
    for line in fm_block.splitlines():
        m2 = re.match(r'^([a-zA-Z_]+):\s*(.*)$', line)
        if m2:
            key, val = m2.group(1), m2.group(2)
            fm[key] = val
            fm_order.append(key)

    title_raw = fm.get("title", "").strip().strip('"')
    slug = slugify(title_raw)
    truth = TRUTH.get(slug)
    if not truth:
        print(f"  SKIP (no truth): {md.name}")
        return False

    w_cm, h_cm = truth["dim_cm"]
    w_in, h_in = truth["dim_in"]

    # Set numeric fields
    fm["widthCm"] = str(w_cm)
    fm["heightCm"] = str(h_cm)

    # Normalise dimensions string
    new_dim = f'"{fmt_num(w_cm)} × {fmt_num(h_cm)} cm ({fmt_num(w_in)} × {fmt_num(h_in)} in)"'
    fm["dimensions"] = new_dim

    # Fix year only if current is a single 4-digit year that disagrees
    cur_year = fm.get("year", "").strip().strip('"')
    if re.fullmatch(r"\d{4}", cur_year) and truth["year"] and cur_year != truth["year"]:
        print(f"  YEAR FIX: {md.name}: {cur_year} → {truth['year']}")
        fm["year"] = f'"{truth["year"]}"'

    # Make sure new keys come after existing 'dimensions' for readability
    for k in ("widthCm", "heightCm"):
        if k not in fm_order:
            # insert after 'dimensions' if present, else append
            if "dimensions" in fm_order:
                idx = fm_order.index("dimensions") + 1
                # also push past any already-inserted new key
                while idx < len(fm_order) and fm_order[idx] in ("widthCm", "heightCm"):
                    idx += 1
                fm_order.insert(idx, k)
            else:
                fm_order.append(k)

    # Rebuild
    out_lines = []
    for k in fm_order:
        v = fm[k]
        # Numeric fields: no quotes
        if k in ("widthCm", "heightCm", "order"):
            v = v.strip().strip('"')
        out_lines.append(f"{k}: {v}")
    new_text = "---\n" + "\n".join(out_lines) + "\n---\n" + body

    if new_text != text:
        md.write_text(new_text)
        return True
    return False


def main():
    changed = 0
    for md in sorted(ARTWORKS_DIR.glob("**/*.md")):
        if update_file(md):
            changed += 1
    print(f"\nUpdated {changed} files")


if __name__ == "__main__":
    main()
