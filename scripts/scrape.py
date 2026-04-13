#!/usr/bin/env python3
"""
Telegram Channel Scraper — @ExplosiveMedia
Extracts messages, translates Persian text to English, downloads all media.
Outputs a CSV with bilingual text, timestamps in US Eastern time.

Usage:
    pip install -r requirements.txt
    python scrape.py

First run will prompt for phone number / 2FA code for Telegram auth.
Subsequent runs resume from the last scraped message.
"""

import asyncio
import csv
import json
import os
import signal
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytz
from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.tl.types import (
    MessageMediaDocument,
    MessageMediaPhoto,
    MessageMediaWebPage,
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

load_dotenv()

API_ID = int(os.environ["TELEGRAM_API_ID"])
API_HASH = os.environ["TELEGRAM_API_HASH"]
PHONE = os.environ.get("TELEGRAM_PHONE")
SESSION_NAME = "explosive_media_session"

CHANNEL = "ExplosiveMedia"  # public username (no @)
START_DATE = datetime(2026, 1, 1, tzinfo=timezone.utc)
END_DATE_STR = "2026-04-09"  # stop after this date (Eastern time)

MEDIA_DIR = Path("scraped-media")
CSV_FILE = Path("explosive_media_messages.csv")
PROGRESS_FILE = Path(".scrape_progress.json")

EASTERN = pytz.timezone("US/Eastern")

# Rate‐limit safety: pause between batches
BATCH_PAUSE_SECONDS = 1.0
MEDIA_PAUSE_SECONDS = 0.5

# ---------------------------------------------------------------------------
# Translation helper (googletrans — free, no API key)
# ---------------------------------------------------------------------------

_translator = None


def _get_translator():
    """Lazy-init the translator so import errors surface early."""
    global _translator
    if _translator is None:
        from googletrans import Translator
        _translator = Translator()
    return _translator


async def translate_text(text: str) -> str:
    """Translate Persian/Farsi text to English. Returns empty string on failure."""
    if not text or not text.strip():
        return ""
    try:
        translator = _get_translator()
        # googletrans is synchronous; run in executor to avoid blocking
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None, lambda: translator.translate(text, src="fa", dest="en")
        )
        return result.text if result and result.text else ""
    except Exception as exc:
        print(f"  [translate warning] {exc.__class__.__name__}: {exc}")
        return "[translation failed]"


# ---------------------------------------------------------------------------
# Media helpers
# ---------------------------------------------------------------------------

def _media_extension(message) -> str:
    """Guess a file extension from the message media."""
    media = message.media
    if isinstance(media, MessageMediaPhoto):
        return ".jpg"
    if isinstance(media, MessageMediaDocument):
        doc = media.document
        if doc and doc.mime_type:
            mime = doc.mime_type
            ext_map = {
                "video/mp4": ".mp4",
                "video/quicktime": ".mov",
                "video/x-matroska": ".mkv",
                "audio/mpeg": ".mp3",
                "audio/ogg": ".ogg",
                "image/jpeg": ".jpg",
                "image/png": ".png",
                "image/gif": ".gif",
                "image/webp": ".webp",
                "application/pdf": ".pdf",
                "application/zip": ".zip",
                "application/x-rar-compressed": ".rar",
            }
            if mime in ext_map:
                return ext_map[mime]
            # fallback: use subtype
            parts = mime.split("/")
            if len(parts) == 2:
                return f".{parts[1]}"
        # check for filename attribute
        if doc:
            for attr in doc.attributes:
                if hasattr(attr, "file_name") and attr.file_name:
                    return Path(attr.file_name).suffix or ".bin"
    return ".bin"


# ---------------------------------------------------------------------------
# Progress / resume support
# ---------------------------------------------------------------------------

def load_progress() -> dict:
    if PROGRESS_FILE.exists():
        with open(PROGRESS_FILE, "r") as f:
            return json.load(f)
    return {}


def save_progress(data: dict):
    with open(PROGRESS_FILE, "w") as f:
        json.dump(data, f)


# ---------------------------------------------------------------------------
# Media‐per‐day counter for filename labeling
# ---------------------------------------------------------------------------

class MediaCounter:
    """Tracks how many media files have been saved per date string (YYYY-MM-DD)."""

    def __init__(self, media_dir: Path):
        self.media_dir = media_dir
        self._counts: dict[str, int] = {}
        # Scan existing files to initialise counts for resume
        if media_dir.exists():
            for f in media_dir.iterdir():
                if f.is_file():
                    # Expected pattern: YYYY-MM-DD_NNN.ext
                    name = f.stem  # e.g. "2026-01-15_003"
                    parts = name.rsplit("_", 1)
                    if len(parts) == 2:
                        date_str = parts[0]
                        try:
                            num = int(parts[1])
                            self._counts[date_str] = max(
                                self._counts.get(date_str, 0), num
                            )
                        except ValueError:
                            pass

    def next_filename(self, date_str: str, ext: str) -> str:
        count = self._counts.get(date_str, 0) + 1
        self._counts[date_str] = count
        return f"{date_str}_{count:03d}{ext}"


# ---------------------------------------------------------------------------
# CSV writer with resume awareness
# ---------------------------------------------------------------------------

class CSVWriter:
    FIELDNAMES = [
        "message_text_persian",
        "message_text_english",
        "time_est",
        "date",
        "has_media",
    ]

    def __init__(self, path: Path):
        self.path = path
        self._existing_ids: set[str] = set()
        if path.exists():
            # Load existing date+time keys so we don't duplicate rows on resume
            with open(path, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    key = f"{row.get('date')}|{row.get('time_est')}"
                    self._existing_ids.add(key)
        write_header = not path.exists() or path.stat().st_size == 0
        self._file = open(path, "a", newline="", encoding="utf-8-sig")
        self._writer = csv.DictWriter(self._file, fieldnames=self.FIELDNAMES)
        if write_header:
            self._writer.writeheader()
            self._file.flush()

    def write_row(self, row: dict):
        key = f"{row.get('date')}|{row.get('time_est')}"
        if key in self._existing_ids:
            return  # skip duplicate
        self._existing_ids.add(key)
        self._writer.writerow(row)
        self._file.flush()

    def close(self):
        self._file.close()


# ---------------------------------------------------------------------------
# Main scraper
# ---------------------------------------------------------------------------

async def main():
    MEDIA_DIR.mkdir(exist_ok=True)

    print("=" * 60)
    print("  Telegram Scraper — @ExplosiveMedia")
    print("=" * 60)
    print(f"  Channel   : @{CHANNEL}")
    print(f"  From      : {START_DATE.strftime('%Y-%m-%d')}")
    print(f"  Media dir : {MEDIA_DIR.resolve()}")
    print(f"  CSV file  : {CSV_FILE.resolve()}")
    print("=" * 60)

    # --- Telethon client ---
    client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
    await client.start(phone=PHONE)
    print("\n[+] Authenticated successfully.\n")

    # --- Resolve channel ---
    try:
        entity = await client.get_entity(CHANNEL)
    except Exception as exc:
        print(f"[ERROR] Could not resolve channel @{CHANNEL}: {exc}")
        await client.disconnect()
        sys.exit(1)

    print(f"[+] Channel resolved: {getattr(entity, 'title', CHANNEL)}")

    # --- Resume support ---
    progress = load_progress()
    last_id = progress.get("last_message_id", 0)
    total_saved = progress.get("total_saved", 0)
    if last_id:
        print(f"[+] Resuming after message ID {last_id} ({total_saved} already saved)")

    csv_writer = CSVWriter(CSV_FILE)
    media_counter = MediaCounter(MEDIA_DIR)

    # Graceful shutdown
    shutdown_requested = False

    def handle_signal(*_):
        nonlocal shutdown_requested
        shutdown_requested = True
        print("\n[!] Shutdown requested — finishing current batch...")

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    # --- Iterate messages ---
    batch_count = 0
    new_messages = 0

    print("[+] Fetching messages...\n")

    async for message in client.iter_messages(
        entity,
        offset_date=None,  # start from newest
        reverse=True,       # oldest first
        limit=None,         # all messages
    ):
        if shutdown_requested:
            break

        # Skip messages before our start date
        if message.date.replace(tzinfo=timezone.utc) < START_DATE:
            continue

        # Skip already-processed messages (resume)
        if message.id <= last_id:
            continue

        # --- Timestamp conversion ---
        utc_dt = message.date.replace(tzinfo=timezone.utc)
        est_dt = utc_dt.astimezone(EASTERN)
        date_str = est_dt.strftime("%Y-%m-%d")
        time_str = est_dt.strftime("%Y-%m-%d %H:%M:%S %Z")

        # Stop if we've passed the end date
        if END_DATE_STR and date_str > END_DATE_STR:
            print(f"[+] Reached end date ({END_DATE_STR}), stopping.")
            break

        # --- Text ---
        raw_text = message.text or ""

        # --- Translation ---
        english_text = await translate_text(raw_text) if raw_text.strip() else ""

        # --- Media download ---
        has_media = "N"
        if message.media and not isinstance(message.media, MessageMediaWebPage):
            has_media = "Y"
            ext = _media_extension(message)
            filename = media_counter.next_filename(date_str, ext)
            filepath = MEDIA_DIR / filename
            try:
                await client.download_media(message, file=str(filepath))
                print(f"  [media] saved {filename}")
            except Exception as exc:
                print(f"  [media error] msg {message.id}: {exc}")
            await asyncio.sleep(MEDIA_PAUSE_SECONDS)

        # --- Write CSV row ---
        csv_writer.write_row({
            "message_text_persian": raw_text,
            "message_text_english": english_text,
            "time_est": time_str,
            "date": date_str,
            "has_media": has_media,
        })

        new_messages += 1
        total_saved += 1

        # Progress reporting
        if new_messages % 10 == 0:
            print(f"  [{total_saved} messages processed] latest: {date_str}")

        # Save progress every 25 messages
        batch_count += 1
        if batch_count % 25 == 0:
            save_progress({
                "last_message_id": message.id,
                "total_saved": total_saved,
                "last_run": datetime.now(timezone.utc).isoformat(),
            })
            await asyncio.sleep(BATCH_PAUSE_SECONDS)

    # --- Final save ---
    save_progress({
        "last_message_id": message.id if new_messages > 0 else last_id,
        "total_saved": total_saved,
        "last_run": datetime.now(timezone.utc).isoformat(),
    })
    csv_writer.close()
    await client.disconnect()

    print("\n" + "=" * 60)
    print(f"  DONE — {new_messages} new messages this run")
    print(f"  Total messages in CSV: {total_saved}")
    print(f"  CSV   : {CSV_FILE.resolve()}")
    print(f"  Media : {MEDIA_DIR.resolve()}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
