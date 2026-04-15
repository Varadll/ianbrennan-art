#!/usr/bin/env python3
"""
Reconcile parsed PDF catalog records against existing markdown frontmatter.

Build a per-painting truth table: each unique title gets one canonical
(year, medium, dim_cm, dim_in). Then compare to current markdown files.

Outputs:
  - scripts/truth.json     — canonical title → metadata
  - scripts/diff.txt       — human-readable diff vs current markdown

Run:
    python3 scripts/reconcile.py
"""
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "scripts" / "catalog.json"
ARTWORKS_DIR = ROOT / "src" / "content" / "artworks"
TRUTH_OUT = ROOT / "scripts" / "truth.json"
DIFF_OUT = ROOT / "scripts" / "diff.txt"


def slugify(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = s.lower()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s_-]+", "-", s).strip("-")
    return s


def read_frontmatter(path: Path) -> dict:
    text = path.read_text()
    m = re.match(r"---\n(.*?)\n---", text, re.DOTALL)
    if not m:
        return {}
    fm = {}
    for line in m.group(1).splitlines():
        m2 = re.match(r'^([a-zA-Z_]+):\s*"?(.*?)"?\s*$', line)
        if m2:
            fm[m2.group(1)] = m2.group(2)
    return fm


def main():
    records = json.loads(CATALOG.read_text())

    # Build truth table: title_slug -> best record
    by_slug: dict[str, dict] = {}
    for r in records:
        cap = r["caption"]
        if not cap["title"] or not cap["dim_cm"]:
            continue
        slug = slugify(cap["title"])
        if not slug:
            continue
        # Prefer records with all fields filled
        existing = by_slug.get(slug)
        score = (1 if cap["medium"] else 0) + (1 if cap["year"] else 0)
        if existing is None or score > existing["_score"]:
            by_slug[slug] = {
                "title": cap["title"],
                "year": cap["year"],
                "medium": cap["medium"],
                "dim_cm": list(cap["dim_cm"]),
                "dim_in": list(cap["dim_in"]),
                "_score": score,
                "page": r["page"],
            }

    # Strip _score
    for v in by_slug.values():
        v.pop("_score", None)

    TRUTH_OUT.write_text(json.dumps(by_slug, indent=2, ensure_ascii=False, sort_keys=True))
    print(f"Truth table: {len(by_slug)} unique paintings → {TRUTH_OUT}")

    # Diff against markdown
    md_files = sorted(ARTWORKS_DIR.glob("**/*.md"))
    diff_lines = []
    matched = 0
    unmatched_md = []
    for mdf in md_files:
        fm = read_frontmatter(mdf)
        title = fm.get("title", "")
        slug = slugify(title)
        truth = by_slug.get(slug)
        if not truth:
            unmatched_md.append((mdf.name, title))
            continue
        matched += 1

        cur_dim = fm.get("dimensions", "")
        new_dim_cm = f"{truth['dim_cm'][0]:g} x {truth['dim_cm'][1]:g} cm"
        new_dim_in = f"{truth['dim_in'][0]:g} x {truth['dim_in'][1]:g} in"

        # Compare year + medium too
        notes = []
        if fm.get("year") != truth["year"]:
            notes.append(f"YEAR cur={fm.get('year')} pdf={truth['year']}")
        if truth["medium"] and fm.get("medium", "").lower() != (truth["medium"] or "").lower():
            notes.append(f"MEDIUM cur={fm.get('medium')!r} pdf={truth['medium']!r}")
        # Dim check (compare normalised)
        if new_dim_in not in cur_dim and new_dim_cm not in cur_dim:
            notes.append(f"DIM cur={cur_dim!r} → {new_dim_cm} ({new_dim_in})")
        if notes:
            diff_lines.append(f"{mdf.relative_to(ROOT)}  [{title}]")
            for n in notes:
                diff_lines.append(f"    {n}")

    print(f"Matched {matched}/{len(md_files)} markdown files")
    print(f"Unmatched: {len(unmatched_md)}")
    for name, title in unmatched_md:
        print(f"   - {name}  (title='{title}')")

    DIFF_OUT.write_text("\n".join(diff_lines) + "\n")
    print(f"\nDiff written to {DIFF_OUT} ({len(diff_lines)} lines)")


if __name__ == "__main__":
    main()
