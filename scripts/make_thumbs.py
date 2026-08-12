#!/usr/bin/env python3
"""Generate small thumbnails for the interactive pro/anti key-frame timeline.

The chart draws one tile per classified post at roughly 18px. Shipping the full
screenshots would add tens of megabytes to the repo for images nobody sees at
full size, so this writes a 96px-wide JPEG per post into ``thumbs/`` instead —
about 3KB each.

Sources, in order of preference:
    images  -> ../scraped-media/<file>            (outside the repo)
               media/<file>                        (already committed)
    videos  -> ../screenshots/<date>/<stem>.jpg    (outside the repo)
               screenshots/<date>/<stem>.jpg       (already committed)

Run:  .venv/bin/python explosive-media-analysis/scripts/make_thumbs.py
Idempotent — existing thumbnails are skipped, so re-runs are cheap.
"""

import csv
import os
import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    sys.exit("Pillow is required:  .venv/bin/python -m pip install pillow")

SCRIPT_DIR = Path(__file__).resolve().parent
SITE_ROOT = SCRIPT_DIR.parent                 # explosive-media-analysis/
PROJECT_ROOT = SITE_ROOT.parent               # explosive-media-footage/

MAIN_CSV = SITE_ROOT / "CSVs" / "explosive_media_messages.csv"
STANCE_CSV = SITE_ROOT / "CSVs" / "phase1_stance_predictions.csv"
THUMBS = SITE_ROOT / "thumbs"
THUMB_W = 96


def source_image(media: str, date: str):
    """First existing source for a post's visual, or None."""
    media = (media or "").strip()
    if not media:
        return None
    if media.lower().endswith((".jpg", ".jpeg", ".png")):
        candidates = [PROJECT_ROOT / "scraped-media" / media, SITE_ROOT / "media" / media]
    elif media.lower().endswith((".mp4", ".mov")):
        stem = Path(media).stem + ".jpg"
        candidates = [PROJECT_ROOT / "screenshots" / date / stem,
                      SITE_ROOT / "screenshots" / date / stem]
    else:
        return None
    return next((c for c in candidates if c.exists()), None)


def main():
    with open(STANCE_CSV, encoding="utf-8-sig") as f:
        stance = {int(r["original_row"]): r["p1_stance"].strip()
                  for r in csv.DictReader(f) if r.get("original_row", "").isdigit()}
    with open(MAIN_CSV, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    THUMBS.mkdir(exist_ok=True)
    made = skipped = missing = 0

    for i, row in enumerate(rows):
        if stance.get(i) not in ("Pro-regime", "Anti-regime"):
            continue
        media = (row.get("media_filename") or "").strip()
        if not media:
            continue                       # text-only post — drawn as a solid tile
        out = THUMBS / (Path(media).stem + ".jpg")
        if out.exists():
            skipped += 1
            continue
        src = source_image(media, row.get("date", ""))
        if not src:
            missing += 1
            continue
        try:
            im = Image.open(src).convert("RGB")
            w, h = im.size
            im = im.resize((THUMB_W, max(1, round(h * THUMB_W / w))), Image.LANCZOS)
            im.save(out, "JPEG", quality=72, optimize=True)
            made += 1
        except Exception as e:
            print(f"  !! {media}: {type(e).__name__}")
            missing += 1

    total = sum(f.stat().st_size for f in THUMBS.glob("*.jpg"))
    print(f"created {made}, already present {skipped}, no source {missing}")
    print(f"{len(list(THUMBS.glob('*.jpg')))} thumbnails, {total/1e6:.1f} MB total")


if __name__ == "__main__":
    main()
