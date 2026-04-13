#!/usr/bin/env python3
"""Extract one screenshot (at midpoint) from each video and update CSV."""

import csv
import os
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).parent
MEDIA_DIR = BASE_DIR / "scraped-media"
SCREENSHOTS_DIR = BASE_DIR / "screenshots"
CSV_FILE = BASE_DIR / "explosive_media_messages.csv"

SCREENSHOTS_DIR.mkdir(exist_ok=True)

# Load CSV
rows = []
with open(CSV_FILE, "r", encoding="utf-8-sig") as f:
    reader = csv.DictReader(f)
    fieldnames = reader.fieldnames
    for row in reader:
        rows.append(row)

# Ensure screenshots column exists
if "screenshots" not in fieldnames:
    fieldnames.append("screenshots")

video_exts = (".mp4", ".mov", ".mkv")
processed = 0
skipped = 0
errors = 0

for row in rows:
    media_file = row.get("media_filename", "")
    if not media_file or not media_file.endswith(video_exts):
        continue

    media_path = MEDIA_DIR / media_file
    if not media_path.exists():
        print(f"  MISSING: {media_file}")
        skipped += 1
        continue

    # Build screenshot path: screenshots/<date>/<filename>_mid.jpg
    date_str = row.get("date", "unknown")
    date_dir = SCREENSHOTS_DIR / date_str
    date_dir.mkdir(parents=True, exist_ok=True)

    ss_name = f"{Path(media_file).stem}.jpg"
    ss_path = date_dir / ss_name
    ss_relative = f"{date_str}/{ss_name}"

    # Skip if already exists
    if ss_path.exists():
        row["screenshots"] = ss_relative
        skipped += 1
        continue

    try:
        # Get duration
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(media_path)],
            capture_output=True, text=True, check=True
        )
        duration = float(probe.stdout.strip())
        midpoint = duration / 2

        # Extract frame at midpoint
        subprocess.run(
            ["ffmpeg", "-y", "-ss", str(midpoint), "-i", str(media_path),
             "-frames:v", "1", "-q:v", "2", str(ss_path)],
            capture_output=True, check=True
        )

        row["screenshots"] = ss_relative
        processed += 1
        print(f"  [{processed}] {media_file} -> {ss_relative}")

    except Exception as e:
        print(f"  ERROR: {media_file}: {e}")
        errors += 1

# Save CSV
with open(CSV_FILE, "w", newline="", encoding="utf-8-sig") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow(row)

print(f"\nDone. Processed: {processed}, Skipped: {skipped}, Errors: {errors}")
