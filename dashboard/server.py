#!/usr/bin/env python3
"""
Admin Dashboard for Explosive Media Telegram Analysis.
FastAPI server that serves media alongside CSV data with processing capabilities:
- Audio transcription (Whisper)
- Audio translation (Claude)
- OCR (EasyOCR)
- OCR translation (Claude)
- Keyword tagging
- Video screenshots
"""

import asyncio
import csv
import json
import os
import subprocess
import sys
from pathlib import Path
from datetime import datetime

from dotenv import load_dotenv
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

load_dotenv(Path(__file__).parent.parent / ".env")

app = FastAPI(title="Explosive Media Dashboard")

BASE_DIR = Path(__file__).parent.parent
MEDIA_DIR = BASE_DIR / "scraped-media"
SCREENSHOTS_DIR = BASE_DIR / "screenshots"

# Section-based CSV files
SECTIONS = {
    "anti-regime": {
        "csv": BASE_DIR / "anti_regime_footage.csv",
        "label": "Anti-Regime",
        "color": "#f85149",
    },
    "using-ai": {
        "csv": BASE_DIR / "using_ai_footage.csv",
        "label": "Using AI",
        "color": "#58a6ff",
    },
    "video-transcripts": {
        "csv": BASE_DIR / "videos_with_transcriptions.csv",
        "label": "Video Transcripts",
        "color": "#7ee787",
    },
    "golden-dataset": {
        "csv": BASE_DIR / "explosive-media-analysis" / "CSVs" / "golden_dataset.csv",
        "label": "Golden Dataset",
        "color": "#d2a8ff",
    },
}
EXTRA_THEME_FIELDS = ("theme2", "theme3", "theme4")
DEFAULT_SECTION = "anti-regime"
CSV_FILE = SECTIONS[DEFAULT_SECTION]["csv"]  # fallback for non-section code
MAIN_CSV_FILE = BASE_DIR / "explosive-media-analysis" / "CSVs" / "explosive_media_messages.csv"


PHASE1_PREDS = BASE_DIR / "explosive-media-analysis" / "CSVs" / "phase1_stance_predictions.csv"
THEME_CANON = {"gaza genocide": "Gaza Genocide", "lego": "LEGO"}


def canon_theme(value: str) -> str:
    v = (value or "").strip()
    return THEME_CANON.get(v.lower(), v)


def row_stance(row: dict) -> str:
    """Hand-coded stance for a golden row, reading all four theme columns."""
    themes = {canon_theme(row.get(c, "")) for c in
              ("theme",) + EXTRA_THEME_FIELDS}
    pro, anti = "Pro-regime" in themes, "Anti-regime" in themes
    if pro and anti:
        return "Both"
    return "Pro-regime" if pro else "Anti-regime" if anti else "Neither"


def load_phase1_predictions() -> dict:
    """Model stance predictions keyed by original_row, if the phase has been run."""
    if not PHASE1_PREDS.exists():
        return {}
    preds = {}
    with open(PHASE1_PREDS, "r", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            try:
                preds[int(r["original_row"])] = r
            except (KeyError, ValueError):
                continue
    return preds


def load_section_csv(section: str) -> list[dict]:
    """Load rows for a given section.

    Golden rows get the model's stance call attached under underscore-prefixed
    keys. Those are stripped on save, so reviewing predictions never writes
    model output into the hand-coded ground truth.
    """
    csv_path = SECTIONS.get(section, SECTIONS[DEFAULT_SECTION])["csv"]
    preds = load_phase1_predictions() if section == "golden-dataset" else {}
    rows = []
    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            row["_row_id"] = i
            if section == "golden-dataset":
                for fld in EXTRA_THEME_FIELDS:
                    row.setdefault(fld, "")
                row["_stance_truth"] = row_stance(row)
                try:
                    p = preds.get(int(row.get("original_row", -1)), {})
                except ValueError:
                    p = {}
                row["_p1_stance"] = p.get("p1_stance", "")
                row["_p1_confidence"] = p.get("p1_confidence", "")
                row["_p1_reason"] = p.get("p1_reason", "")
            rows.append(row)
    return rows

# Google Sheets config
GSHEET_ID = "1Gz7KgWNzbAcUG5R8LmGZ7lRn41orQKnbEzTc-mt6Zb0"
GSHEET_GID = "783599104"
_gsheet_client = None

SCREENSHOTS_DIR.mkdir(exist_ok=True)

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


def asset_version() -> str:
    """Cache-busting token derived from app.js's mtime.

    Without this the browser keeps serving a stale app.js after the file
    changes, so newly added handlers silently do not exist on the page.
    """
    js = Path(__file__).parent / "static" / "js" / "app.js"
    try:
        return str(int(js.stat().st_mtime))
    except OSError:
        return "0"


templates.env.globals["asset_version"] = asset_version
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")
app.mount("/media", StaticFiles(directory=str(MEDIA_DIR)), name="media")
app.mount("/screenshots", StaticFiles(directory=str(SCREENSHOTS_DIR)), name="screenshots")


# ---------------------------------------------------------------------------
# Data layer
# ---------------------------------------------------------------------------

def load_csv() -> list[dict]:
    """Load all rows from the CSV."""
    rows = []
    with open(CSV_FILE, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            row["_row_id"] = i
            rows.append(row)
    return rows


def save_csv(rows: list[dict]):
    """Write all rows back to CSV."""
    save_section_csv(DEFAULT_SECTION, rows)


def save_section_csv(section: str, rows: list[dict]):
    """Write all rows back to the given section's CSV."""
    if not rows:
        return
    csv_path = SECTIONS.get(section, SECTIONS[DEFAULT_SECTION])["csv"]
    # Underscore-prefixed keys are view-only (row id, model predictions) and must
    # never be written back into the hand-coded CSV.
    fieldnames = [k for k in rows[0].keys() if not k.startswith("_")]
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: v for k, v in row.items() if not k.startswith("_")})


def get_gsheet_client():
    """Get or create authenticated gspread client."""
    global _gsheet_client
    if _gsheet_client is not None:
        return _gsheet_client
    try:
        import gspread
        _gsheet_client = gspread.oauth()  # Uses ~/.config/gspread/authorized_user.json
        return _gsheet_client
    except Exception as e:
        print(f"[WARN] Google Sheets auth failed: {e}")
        print("[WARN] Run this in a terminal to authenticate:")
        print("  python3 -c \"import gspread; gspread.oauth()\"")
        return None


def sync_row_to_gsheet(row_id: int, row: dict):
    """Sync a single row's editable fields to Google Sheets."""
    try:
        gc = get_gsheet_client()
        if gc is None:
            return
        sh = gc.open_by_key(GSHEET_ID)
        worksheet = sh.get_worksheet_by_id(int(GSHEET_GID))

        # Find the row in the sheet (row_id + 2: 1 for header, 1 for 0-index)
        sheet_row = row_id + 2

        # Get header to find column positions
        headers = worksheet.row_values(1)
        for field in ("audio_transcription_persian_v2", "audio_transcription_english",
                      "ocr_text_persian", "ocr_text_english",
                      "keywords", "theme", "include_person", "AI_generated"):
            if field in headers and field in row:
                col = headers.index(field) + 1
                val = row.get(field, "")
                if val and val != "nan":
                    worksheet.update_cell(sheet_row, col, val)

        print(f"[GSHEET] Synced row {row_id}")
    except Exception as e:
        print(f"[GSHEET] Sync failed for row {row_id}: {e}")


def sync_to_main_csv(row_id: int, row: dict):
    """Also update the corresponding row in the main CSV using original_row index."""
    try:
        import pandas as pd
        original_row = int(row.get("original_row", -1))
        if original_row < 0:
            return
        df = pd.read_csv(MAIN_CSV_FILE)
        for field in ("audio_transcription_persian_v2", "audio_transcription_english",
                      "ocr_text_persian", "ocr_text_english",
                      "keywords", "theme", "include_person", "AI_generated"):
            if field in row and field in df.columns:
                # Cast column to object to accept string values
                df[field] = df[field].astype(object)
                val = row.get(field, "")
                if val and val != "nan":
                    df.at[original_row, field] = val
        df.to_csv(MAIN_CSV_FILE, index=False)
        print(f"[MAIN CSV] Synced row {row_id} (original_row {original_row})")
    except Exception as e:
        print(f"[MAIN CSV] Sync failed for row {row_id} (original_row {row.get('original_row')}): {e}")


def get_media_filename(row: dict) -> str | None:
    """Get the media filename for a row if it exists."""
    if row.get("media_filename"):
        return row["media_filename"]
    return None


def map_media_to_rows(rows: list[dict]) -> list[dict]:
    """Map media files to CSV rows by date ordering."""
    media_files = sorted(os.listdir(MEDIA_DIR))
    media_files = [f for f in media_files if f.endswith(('.mp4', '.jpg', '.png', '.gif', '.webp', '.mov'))]

    # Group media files by date
    from collections import defaultdict
    files_by_date = defaultdict(list)
    for f in media_files:
        date_part = f.rsplit("_", 1)[0]
        files_by_date[date_part].append(f)

    # Sort each date's files by sequence number
    for date in files_by_date:
        files_by_date[date].sort()

    # Assign to rows
    date_counters = {}
    for row in rows:
        if row.get("has_media") == "Y":
            date = row.get("date", "")
            if date not in date_counters:
                date_counters[date] = 0
            idx = date_counters[date]
            if date in files_by_date and idx < len(files_by_date[date]):
                row["media_filename"] = files_by_date[date][idx]
            date_counters[date] = idx + 1

    return rows


# Ensure media_filename column exists
def ensure_media_mapping():
    """One-time operation to add media_filename column if missing."""
    rows = load_csv()
    if rows and "media_filename" not in rows[0]:
        rows = map_media_to_rows(rows)
        # Add missing columns
        for row in rows:
            row.setdefault("media_filename", "")
            row.setdefault("audio_transcription_persian", "")
            row.setdefault("audio_transcription_english", "")
            row.setdefault("ocr_text_persian", "")
            row.setdefault("ocr_text_english", "")
            row.setdefault("keywords", "")
            row.setdefault("screenshots", "")
        save_csv(rows)
        print(f"[+] Added media_filename mapping and new columns to {CSV_FILE}")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def startup():
    ensure_media_mapping()


def _is_repetitive(text: str) -> bool:
    """Check if transcription is repetitive hallucination."""
    if not text or not text.strip():
        return False
    words = text.split()
    if len(words) > 10:
        return len(set(words)) / len(words) < 0.3
    return False


def apply_filters(rows: list[dict], date_filter: str = "", media_only: str = "",
                  search: str = "", error_filter: str = "") -> list[dict]:
    """Narrow rows to the active filter set.

    Shared by the index listing and the row-detail Prev/Next navigation so that
    stepping through a filtered queue never wanders into rows outside it.
    """
    if date_filter:
        rows = [r for r in rows if r.get("date", "").startswith(date_filter)]
    if media_only == "Y":
        rows = [r for r in rows if r.get("has_media") == "Y"]
    if search:
        search_lower = search.lower()
        rows = [r for r in rows if search_lower in r.get("message_text_persian", "").lower()
                or search_lower in r.get("message_text_english", "").lower()
                or search_lower in r.get("keywords", "").lower()]

    # Error filter for transcription QA
    if error_filter == "v2_errors":
        rows = [r for r in rows if r.get("audio_transcription_persian_v2", "").startswith("[ERROR")]
    elif error_filter == "v2_repetitive":
        rows = [r for r in rows if _is_repetitive(r.get("audio_transcription_persian_v2", ""))]
    elif error_filter == "translation_failures":
        rows = [r for r in rows if r.get("audio_transcription_english", "") in ("[translation failed]", "")
                and r.get("audio_transcription_persian_v2", "").strip()
                and not r.get("audio_transcription_persian_v2", "").startswith("[ERROR")]
    elif error_filter == "weather_clips":
        import re
        weather_re = re.compile(r'(?i)\b(weather|rain|snow)\b')
        rows = [r for r in rows if
                _is_repetitive(r.get("audio_transcription_persian_v2", ""))
                and weather_re.search(r.get("message_text_english", ""))]
    elif error_filter == "non_weather_repetitive":
        import re
        weather_re = re.compile(r'(?i)\b(weather|rain|snow)\b')
        rows = [r for r in rows if
                _is_repetitive(r.get("audio_transcription_persian_v2", ""))
                and not weather_re.search(r.get("message_text_english", ""))]
    elif error_filter == "sports_clips":
        import re
        weather_re = re.compile(r'(?i)\b(weather|rain|snow)\b')
        sports_re = re.compile(r'(?i)\b(sport|soccer|football|basketball|tennis|volleyball|wrestling|athlete|goal|match|team|game|stadium|coach|player|championship|league|tournament|boxing|medal|olympic)\b')
        rows = [r for r in rows if
                _is_repetitive(r.get("audio_transcription_persian_v2", ""))
                and not weather_re.search(r.get("message_text_english", ""))
                and sports_re.search(r.get("message_text_english", ""))]
    elif error_filter == "stance_review":
        # Every golden row where the Phase 1 classifier disagreed with the
        # hand-coded stance — the review queue for fixing labels and the schema.
        rows = [r for r in rows if r.get("_p1_stance")
                and r.get("_p1_stance") != r.get("_stance_truth")]
    elif error_filter == "stance_flips":
        # Polarity flips only: you said Pro and model said Anti, or vice versa.
        # The most serious disagreements — review these first.
        rows = [r for r in rows
                if {r.get("_stance_truth"), r.get("_p1_stance")} ==
                   {"Pro-regime", "Anti-regime"}]
    elif error_filter == "unlabelled":
        # Golden-dataset hand-coding queue: no theme yet, and the row has something to code.
        rows = [r for r in rows if not r.get("theme", "").strip()
                and (r.get("message_text_persian", "").strip()
                     or r.get("message_text_english", "").strip()
                     or r.get("media_filename", "").strip())]
    elif error_filter == "empty_rows":
        # Messages with no text and no media — nothing to hand-code; candidates to drop.
        rows = [r for r in rows if not r.get("message_text_persian", "").strip()
                and not r.get("message_text_english", "").strip()
                and not r.get("media_filename", "").strip()]
    elif error_filter == "needs_review":
        rows = [r for r in rows if r.get("audio_transcription_persian_v2", "").startswith("[NEEDS MANUAL REVIEW")]
    elif error_filter == "all_issues":
        rows = [r for r in rows if
                r.get("audio_transcription_persian_v2", "").startswith("[ERROR")
                or _is_repetitive(r.get("audio_transcription_persian_v2", ""))
                or (r.get("audio_transcription_english", "") in ("[translation failed]", "")
                    and r.get("audio_transcription_persian_v2", "").strip()
                    and not r.get("audio_transcription_persian_v2", "").startswith("[ERROR"))]

    return rows


@app.get("/", response_class=HTMLResponse)
async def index(request: Request, page: int = 1, per_page: int = 50,
                date_filter: str = "", media_only: str = "", search: str = "",
                error_filter: str = "", section: str = DEFAULT_SECTION):
    if section not in SECTIONS:
        section = DEFAULT_SECTION
    rows = apply_filters(load_section_csv(section), date_filter, media_only,
                         search, error_filter)

    total = len(rows)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = max(1, min(page, total_pages))
    start = (page - 1) * per_page
    page_rows = rows[start:start + per_page]

    # Get unique dates for filter dropdown
    all_rows = load_section_csv(section)
    dates = sorted(set(r.get("date", "") for r in all_rows))

    cur_section = SECTIONS[section]
    return templates.TemplateResponse(request, name="index.html", context={
        "rows": page_rows,
        "page": page,
        "per_page": per_page,
        "total": total,
        "total_pages": total_pages,
        "dates": dates,
        "date_filter": date_filter,
        "media_only": media_only,
        "search": search,
        "error_filter": error_filter,
        "section": section,
        "section_label": cur_section["label"],
        "section_color": cur_section["color"],
        "sections": SECTIONS,
    })


@app.get("/row/{row_id}", response_class=HTMLResponse)
async def row_detail(request: Request, row_id: int, section: str = DEFAULT_SECTION,
                     date_filter: str = "", media_only: str = "", search: str = "",
                     error_filter: str = ""):
    if section not in SECTIONS:
        section = DEFAULT_SECTION
    rows = load_section_csv(section)
    if row_id < 0 or row_id >= len(rows):
        raise HTTPException(404, "Row not found")

    row = rows[row_id]
    row["_row_id"] = row_id

    # Prev/Next must step through the FILTERED queue, not the whole CSV —
    # otherwise "Next" walks out of e.g. the unlabelled queue and into rows
    # that are already hand-coded.
    siblings = apply_filters(load_section_csv(section), date_filter, media_only,
                             search, error_filter)
    sibling_ids = [r["_row_id"] for r in siblings]
    if row_id in sibling_ids:
        pos = sibling_ids.index(row_id)
        prev_id = sibling_ids[pos - 1] if pos > 0 else None
        next_id = sibling_ids[pos + 1] if pos < len(sibling_ids) - 1 else None
        queue_pos, queue_total = pos + 1, len(sibling_ids)
    else:
        # Row has dropped out of the filter (e.g. you just labelled it) — offer
        # the next remaining row in the queue rather than a dead end.
        ahead = [i for i in sibling_ids if i > row_id]
        behind = [i for i in sibling_ids if i < row_id]
        prev_id = behind[-1] if behind else None
        next_id = ahead[0] if ahead else None
        queue_pos, queue_total = None, len(sibling_ids)

    # Get screenshots list
    screenshots = []
    if row.get("screenshots"):
        screenshots = [s.strip() for s in row["screenshots"].split(",") if s.strip()]

    cur_section = SECTIONS[section]
    return templates.TemplateResponse(request, name="row_detail.html", context={
        "row": row,
        "row_id": row_id,
        "prev_id": prev_id,
        "next_id": next_id,
        "screenshots": screenshots,
        "media_is_video": row.get("media_filename", "").endswith((".mp4", ".mov", ".mkv")),
        "media_is_image": row.get("media_filename", "").endswith((".jpg", ".png", ".gif", ".webp")),
        "section": section,
        "section_label": cur_section["label"],
        "section_color": cur_section["color"],
        "date_filter": date_filter,
        "media_only": media_only,
        "search": search,
        "error_filter": error_filter,
        "queue_pos": queue_pos,
        "queue_total": queue_total,
    })


# ---------------------------------------------------------------------------
# Processing API endpoints
# ---------------------------------------------------------------------------

@app.post("/api/transcribe/{row_id}")
async def transcribe_audio(row_id: int, section: str = DEFAULT_SECTION):
    """Transcribe video audio using Whisper."""
    if section not in SECTIONS:
        section = DEFAULT_SECTION
    rows = load_section_csv(section)
    if row_id >= len(rows):
        raise HTTPException(404)

    row = rows[row_id]
    media_file = row.get("media_filename", "")
    if not media_file or not media_file.endswith((".mp4", ".mov", ".mkv")):
        return JSONResponse({"error": "No video file for this row"}, 400)

    media_path = MEDIA_DIR / media_file
    if not media_path.exists():
        return JSONResponse({"error": f"File not found: {media_file}"}, 404)

    try:
        # Transcribe with faster-whisper (medium model — good Persian accuracy, reasonable speed)
        from faster_whisper import WhisperModel
        model = WhisperModel("medium", device="cpu", compute_type="int8")
        segments, info = model.transcribe(str(media_path), language="fa", beam_size=3)
        transcription = " ".join(seg.text for seg in segments)

        # Translate transcription
        translation = await _translate_with_claude(transcription)

        # Save to CSV
        rows[row_id]["audio_transcription_persian"] = transcription
        rows[row_id]["audio_transcription_english"] = translation
        save_section_csv(section, rows)
        sync_to_main_csv(row_id, rows[row_id])

        return {"transcription_persian": transcription, "transcription_english": translation}

    except FileNotFoundError:
        return JSONResponse({"error": "ffmpeg not found. Install with: brew install ffmpeg"}, 500)
    except Exception as e:
        return JSONResponse({"error": str(e)}, 500)


@app.post("/api/ocr/{row_id}")
async def ocr_media(row_id: int, section: str = DEFAULT_SECTION):
    """OCR text from image or video frame."""
    if section not in SECTIONS:
        section = DEFAULT_SECTION
    rows = load_section_csv(section)
    if row_id >= len(rows):
        raise HTTPException(404)

    row = rows[row_id]
    media_file = row.get("media_filename", "")
    if not media_file:
        return JSONResponse({"error": "No media file for this row"}, 400)

    media_path = MEDIA_DIR / media_file
    image_path = media_path

    try:
        # If video, extract a frame first
        if media_file.endswith((".mp4", ".mov", ".mkv")):
            image_path = MEDIA_DIR / f"_temp_ocr_{row_id}.jpg"
            subprocess.run([
                "ffmpeg", "-y", "-i", str(media_path),
                "-ss", "00:00:02", "-frames:v", "1", "-q:v", "2",
                str(image_path)
            ], capture_output=True, check=True)

        # Use Claude Vision for OCR (much better for Persian text)
        import base64
        import anthropic
        with open(image_path, "rb") as f:
            img_data = base64.standard_b64encode(f.read()).decode("utf-8")

        media_type = "image/jpeg" if str(image_path).endswith(".jpg") else "image/png"
        client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=2048,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": img_data}},
                    {"type": "text", "text": "Extract ALL text visible in this image. Return the Persian/Farsi text first, then on a new line starting with 'ENGLISH:', provide the English translation. If there is no text, respond with 'NO TEXT'."}
                ]
            }]
        )
        ocr_result = response.content[0].text.strip()

        # Clean up temp frame
        if media_file.endswith((".mp4", ".mov", ".mkv")):
            image_path.unlink(missing_ok=True)

        # Parse OCR result
        if "NO TEXT" in ocr_result.upper():
            ocr_text = ""
            translation = ""
        elif "ENGLISH:" in ocr_result:
            parts = ocr_result.split("ENGLISH:", 1)
            ocr_text = parts[0].strip()
            translation = parts[1].strip()
        else:
            ocr_text = ocr_result
            translation = await _translate_with_claude(ocr_text)

        # Save
        rows[row_id]["ocr_text_persian"] = ocr_text
        rows[row_id]["ocr_text_english"] = translation
        save_section_csv(section, rows)
        sync_to_main_csv(row_id, rows[row_id])
        sync_row_to_gsheet(row_id, rows[row_id])

        return {"ocr_persian": ocr_text, "ocr_english": translation}

    except Exception as e:
        return JSONResponse({"error": str(e)}, 500)


@app.post("/api/screenshots/{row_id}")
async def take_screenshots(row_id: int, section: str = DEFAULT_SECTION):
    """Extract 3 screenshots from video: beginning, middle, end."""
    if section not in SECTIONS:
        section = DEFAULT_SECTION
    rows = load_section_csv(section)
    if row_id >= len(rows):
        raise HTTPException(404)

    row = rows[row_id]
    media_file = row.get("media_filename", "")
    if not media_file or not media_file.endswith((".mp4", ".mov", ".mkv")):
        return JSONResponse({"error": "No video file for this row"}, 400)

    media_path = MEDIA_DIR / media_file
    base_name = Path(media_file).stem  # e.g. "2026-01-15_003"
    date_str = row.get("date", "unknown")

    # Create date subfolder for organized screenshots
    date_dir = SCREENSHOTS_DIR / date_str
    date_dir.mkdir(parents=True, exist_ok=True)

    try:
        # Get video duration
        probe = subprocess.run([
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(media_path)
        ], capture_output=True, text=True, check=True)
        duration = float(probe.stdout.strip())

        screenshot_files = []
        # Extract 3 frames: beginning (1s), middle, end (-1s)
        timestamps = [
            ("begin", max(0, min(1, duration - 0.1))),
            ("middle", duration / 2),
            ("end", max(0, duration - 1)),
        ]
        for label, t in timestamps:
            ss_name = f"{base_name}_{label}.jpg"
            ss_path = date_dir / ss_name
            subprocess.run([
                "ffmpeg", "-y", "-ss", str(t), "-i", str(media_path),
                "-frames:v", "1", "-q:v", "2", str(ss_path)
            ], capture_output=True, check=True)
            screenshot_files.append(f"{date_str}/{ss_name}")

        # Save to CSV
        rows[row_id]["screenshots"] = ",".join(screenshot_files)
        save_section_csv(section, rows)

        return {"screenshots": screenshot_files, "count": len(screenshot_files)}

    except Exception as e:
        return JSONResponse({"error": str(e)}, 500)


@app.post("/api/keywords/{row_id}")
async def update_keywords(row_id: int, request: Request, section: str = DEFAULT_SECTION):
    """Update keywords for a row."""
    if section not in SECTIONS:
        section = DEFAULT_SECTION
    body = await request.json()
    keywords = body.get("keywords", "")

    rows = load_section_csv(section)
    if row_id >= len(rows):
        raise HTTPException(404)

    rows[row_id]["keywords"] = keywords
    save_section_csv(section, rows)
    sync_to_main_csv(row_id, rows[row_id])
    sync_row_to_gsheet(row_id, rows[row_id])
    return {"keywords": keywords}


@app.post("/api/theme/{row_id}")
async def update_theme(row_id: int, request: Request, section: str = DEFAULT_SECTION):
    """Update theme for a row."""
    if section not in SECTIONS:
        section = DEFAULT_SECTION
    body = await request.json()
    rows = load_section_csv(section)
    if row_id >= len(rows):
        raise HTTPException(404)
    rows[row_id]["theme"] = body.get("theme", "")
    save_section_csv(section, rows)
    sync_to_main_csv(row_id, rows[row_id])
    return {"theme": rows[row_id]["theme"]}


@app.post("/api/theme-extra/{row_id}")
async def update_theme_extra(row_id: int, request: Request, section: str = DEFAULT_SECTION):
    """Update theme2 / theme3 / theme4 for a row in the Golden Dataset only."""
    if section != "golden-dataset":
        raise HTTPException(400, "Extra theme columns only exist on the golden-dataset section")
    body = await request.json()
    field = body.get("field", "")
    if field not in EXTRA_THEME_FIELDS:
        raise HTTPException(400, f"field must be one of {EXTRA_THEME_FIELDS}")
    rows = load_section_csv(section)
    if row_id >= len(rows):
        raise HTTPException(404)
    rows[row_id][field] = body.get("value", "")
    save_section_csv(section, rows)
    return {field: rows[row_id][field]}


@app.post("/api/person/{row_id}")
async def update_person(row_id: int, request: Request, section: str = DEFAULT_SECTION):
    """Update include_person for a row."""
    if section not in SECTIONS:
        section = DEFAULT_SECTION
    body = await request.json()
    rows = load_section_csv(section)
    if row_id >= len(rows):
        raise HTTPException(404)
    rows[row_id]["include_person"] = body.get("include_person", "")
    save_section_csv(section, rows)
    sync_to_main_csv(row_id, rows[row_id])
    return {"include_person": rows[row_id]["include_person"]}


@app.post("/api/ai-generated/{row_id}")
async def update_ai_generated(row_id: int, request: Request, section: str = DEFAULT_SECTION):
    """Update AI_generated for a row."""
    if section not in SECTIONS:
        section = DEFAULT_SECTION
    body = await request.json()
    rows = load_section_csv(section)
    if row_id >= len(rows):
        raise HTTPException(404)
    rows[row_id]["AI_generated"] = body.get("AI_generated", "")
    save_section_csv(section, rows)
    sync_to_main_csv(row_id, rows[row_id])
    return {"AI_generated": rows[row_id]["AI_generated"]}


@app.post("/api/save-ocr/{row_id}")
async def save_ocr(row_id: int, request: Request, section: str = DEFAULT_SECTION):
    """Save edited OCR fields to section CSV and sync back to main CSV."""
    if section not in SECTIONS:
        section = DEFAULT_SECTION
    body = await request.json()
    rows = load_section_csv(section)
    if row_id >= len(rows):
        raise HTTPException(404)

    for field in ("ocr_text_persian", "ocr_text_english"):
        if field in body:
            rows[row_id][field] = body[field]

    save_section_csv(section, rows)
    sync_to_main_csv(row_id, rows[row_id])
    sync_row_to_gsheet(row_id, rows[row_id])
    return {"status": "saved"}


@app.post("/api/save-transcription/{row_id}")
async def save_transcription(row_id: int, request: Request, section: str = DEFAULT_SECTION):
    """Save edited transcription fields to section CSV, main CSV, and Google Sheet."""
    if section not in SECTIONS:
        section = DEFAULT_SECTION
    body = await request.json()
    rows = load_section_csv(section)
    if row_id >= len(rows):
        raise HTTPException(404)

    for field in ("audio_transcription_persian_v2", "audio_transcription_english"):
        if field in body:
            rows[row_id][field] = body[field]

    save_section_csv(section, rows)
    sync_to_main_csv(row_id, rows[row_id])
    sync_row_to_gsheet(row_id, rows[row_id])
    return {"status": "saved"}


@app.post("/api/auto-keywords/{row_id}")
async def auto_keywords(row_id: int, section: str = DEFAULT_SECTION):
    """Generate keywords automatically using Claude."""
    if section not in SECTIONS:
        section = DEFAULT_SECTION
    rows = load_section_csv(section)
    if row_id >= len(rows):
        raise HTTPException(404)

    row = rows[row_id]
    persian = row.get("message_text_persian", "")
    english = row.get("message_text_english", "")
    text = english if english and english != "[translation failed]" else persian

    if not text.strip():
        return {"keywords": ""}

    import anthropic
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=200,
        system="Extract 3-6 keywords/tags from this Telegram message. Return ONLY comma-separated keywords in English, no explanation.",
        messages=[{"role": "user", "content": text}],
    )
    keywords = response.content[0].text.strip()

    rows[row_id]["keywords"] = keywords
    save_section_csv(section, rows)
    sync_to_main_csv(row_id, rows[row_id])
    return {"keywords": keywords}


# ---------------------------------------------------------------------------
# Translation helper
# ---------------------------------------------------------------------------

async def _translate_with_claude(text: str) -> str:
    if not text or not text.strip():
        return ""
    import anthropic
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2048,
        system="You are a Persian/Farsi to English translator. Translate the text below into English. The text is a speech transcription so it may have informal grammar, typos, or phonetic spellings — do your best to interpret the intended meaning. Do NOT comment on text quality. Do NOT refuse. Do NOT explain. Output ONLY the English translation, nothing else.",
        messages=[{"role": "user", "content": text}],
    )
    return response.content[0].text.strip()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8080)
