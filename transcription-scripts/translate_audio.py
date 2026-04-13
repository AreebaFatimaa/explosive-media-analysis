"""Translate audio_transcription_persian_v2 → audio_transcription_english using Haiku 4.5."""

import anthropic, os, time, json, re
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

client = anthropic.Anthropic()
CSV_FILE = "explosive_media_messages.csv"
BATCH_SIZE = 10
SAVE_EVERY = 50

df = pd.read_csv(CSV_FILE)

# Ensure audio_transcription_english column is string type
df["audio_transcription_english"] = df["audio_transcription_english"].astype(object)

# Find rows that need translation: have v2 persian transcription but no english
needs_translation = []
for idx in df.index:
    persian = str(df.at[idx, "audio_transcription_persian_v2"]).strip()
    english = str(df.at[idx, "audio_transcription_english"]).strip()
    if (persian and persian != "nan" and not persian.startswith("[ERROR")
            and english in ("", "nan", "[translation failed]")):
        needs_translation.append(idx)

print(f"{len(needs_translation)} rows need audio translation")

if len(needs_translation) == 0:
    print("Nothing to translate. Exiting.")
    exit(0)

translated_count = 0
error_count = 0

for batch_start in range(0, len(needs_translation), BATCH_SIZE):
    batch_indices = needs_translation[batch_start:batch_start + BATCH_SIZE]

    # Build numbered list of texts
    numbered_texts = []
    for i, idx in enumerate(batch_indices, 1):
        text = str(df.at[idx, "audio_transcription_persian_v2"]).strip()
        numbered_texts.append(f"[{i}] {text}")

    prompt = (
        "You are translating audio transcriptions from Persian/Farsi news videos to English.\n"
        "The transcriptions were produced by a speech-to-text model and contain phonetic "
        "approximations, misspellings, and garbled text. This is expected.\n"
        "Your job is to interpret the intended meaning as best you can and produce a natural "
        "English translation.\n"
        "Do NOT refuse, explain quality issues, or add caveats. Just translate.\n"
        "Return ONLY a JSON array of strings with the English translations in order. "
        "No extra text, no markdown formatting.\n\n"
        + "\n\n".join(numbered_texts)
    )

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}]
        )

        raw = response.content[0].text.strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        translations = json.loads(raw)

        for i, idx in enumerate(batch_indices):
            if i < len(translations):
                df.at[idx, "audio_transcription_english"] = translations[i]
                translated_count += 1
            else:
                df.at[idx, "audio_transcription_english"] = "[translation failed]"
                error_count += 1
    except Exception as e:
        print(f"  [batch error at row {batch_indices[0]}]: {e}")
        for idx in batch_indices:
            df.at[idx, "audio_transcription_english"] = "[translation failed]"
        error_count += len(batch_indices)

    # Progress + periodic save
    if translated_count % SAVE_EVERY < BATCH_SIZE:
        print(f"  [{translated_count}/{len(needs_translation)}] translated, {error_count} errors")
        df.to_csv(CSV_FILE, index=False)

    time.sleep(0.3)  # rate limit buffer

# Final save
df.to_csv(CSV_FILE, index=False)
print(f"\nDone. Translated {translated_count} rows, {error_count} errors.")
