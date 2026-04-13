#!/usr/bin/env python3
"""
Phase 1: Batch translate Persian messages to English using Claude Haiku.
Reads explosive_media_messages.csv, translates the message_text_persian column,
and writes results to message_text_english column (overwriting failed translations).

Resumable: tracks progress in .translate_progress.json.
"""

import csv
import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
import anthropic

load_dotenv()

# Use translated CSV if it exists (for incremental runs), otherwise original
_translated = Path("explosive_media_messages_translated.csv")
_original = Path("explosive_media_messages.csv")
CSV_FILE = _translated if _translated.exists() else _original
OUTPUT_FILE = _translated
PROGRESS_FILE = Path(".translate_progress.json")

BATCH_SIZE = 15  # messages per API call
MODEL = "claude-haiku-4-5-20251001"

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

SYSTEM_PROMPT = """You are a professional Persian/Farsi to English translator working on Telegram channel messages for a journalism project.

Rules:
- Translate each numbered message accurately, preserving tone, slang, and meaning.
- Keep emoji in their original positions.
- Keep Telegram channel identifiers like @akhbarenfejari as-is.
- Keep URLs, hashtags, and usernames untranslated.
- If a message is just emoji or has no translatable text, return the original content.
- Return ONLY the translations in the same numbered format. No commentary.
- Preserve the numbering exactly (1:, 2:, 3:, etc.)"""


def load_progress() -> int:
    """Return the index of the last successfully translated row."""
    if PROGRESS_FILE.exists():
        with open(PROGRESS_FILE) as f:
            return json.load(f).get("last_row", 0)
    return 0


def save_progress(last_row: int):
    with open(PROGRESS_FILE, "w") as f:
        json.dump({"last_row": last_row}, f)


def read_csv() -> list[dict]:
    """Read all rows from the CSV."""
    rows = []
    with open(CSV_FILE, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


def translate_batch(messages: list[tuple[int, str]]) -> dict[int, str]:
    """Send a batch of (index, persian_text) to Claude and return {index: english_text}."""
    # Build the prompt with numbered messages
    prompt_lines = []
    for idx, (row_idx, text) in enumerate(messages, 1):
        # Truncate extremely long messages to avoid token limits
        truncated = text[:3000] if len(text) > 3000 else text
        prompt_lines.append(f"{idx}: {truncated}")

    user_prompt = "Translate each of these Persian/Farsi Telegram messages to English:\n\n" + "\n\n".join(prompt_lines)

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )
        response_text = response.content[0].text

        # Parse numbered responses
        results = {}
        current_num = None
        current_lines = []

        for line in response_text.split("\n"):
            # Check if line starts with a number followed by colon
            stripped = line.strip()
            matched = False
            for i in range(1, len(messages) + 2):
                prefix = f"{i}:"
                if stripped.startswith(prefix):
                    # Save previous
                    if current_num is not None and current_num <= len(messages):
                        original_idx = messages[current_num - 1][0]
                        results[original_idx] = "\n".join(current_lines).strip()
                    current_num = i
                    current_lines = [stripped[len(prefix):].strip()]
                    matched = True
                    break
            if not matched and current_num is not None:
                current_lines.append(line)

        # Save last one
        if current_num is not None and current_num <= len(messages):
            original_idx = messages[current_num - 1][0]
            results[original_idx] = "\n".join(current_lines).strip()

        return results

    except anthropic.RateLimitError:
        print("  [rate limit] waiting 60s...")
        time.sleep(60)
        return translate_batch(messages)
    except Exception as exc:
        print(f"  [error] {exc.__class__.__name__}: {exc}")
        return {}


def main():
    print("=" * 60)
    print("  Phase 1: Translate Persian → English (Claude Haiku)")
    print("=" * 60)

    rows = read_csv()
    total = len(rows)
    print(f"  Total rows: {total}")

    last_done = load_progress()
    if last_done > 0:
        print(f"  Resuming from row {last_done}")

    # Collect rows that need translation (empty or failed)
    to_translate = []
    for i, row in enumerate(rows):
        if i < last_done:
            continue
        text = row.get("message_text_persian", "").strip()
        existing = row.get("message_text_english", "").strip()
        needs_translation = not existing or existing == "[translation failed]"
        if text and needs_translation:
            to_translate.append((i, text))

    print(f"  Rows needing translation: {len(to_translate)}")
    print(f"  Batches of {BATCH_SIZE}: {(len(to_translate) + BATCH_SIZE - 1) // BATCH_SIZE}")
    print("=" * 60)

    # Process in batches
    translated_count = 0
    for batch_start in range(0, len(to_translate), BATCH_SIZE):
        batch = to_translate[batch_start:batch_start + BATCH_SIZE]
        batch_num = batch_start // BATCH_SIZE + 1
        total_batches = (len(to_translate) + BATCH_SIZE - 1) // BATCH_SIZE

        print(f"  Batch {batch_num}/{total_batches} ({len(batch)} messages)...", end=" ", flush=True)

        results = translate_batch(batch)

        # Update rows with translations
        for row_idx, translation in results.items():
            if translation:
                rows[row_idx]["message_text_english"] = translation
                translated_count += 1

        # Track progress by the last row index in this batch
        last_row_in_batch = batch[-1][0]
        save_progress(last_row_in_batch)

        print(f"✓ ({translated_count} translated so far)")

        # Small delay to be respectful of rate limits
        time.sleep(0.5)

    # Write output CSV
    print(f"\n  Writing {OUTPUT_FILE}...")
    fieldnames = list(rows[0].keys())
    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    print(f"\n{'=' * 60}")
    print(f"  DONE — {translated_count} messages translated")
    print(f"  Output: {OUTPUT_FILE.resolve()}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
