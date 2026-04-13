"""LLM classification using golden dataset as few-shot examples.
Classifies theme, keywords, AI_generated, include_person for all rows in explosive_media_messages.csv
that aren't already in the golden set."""

import os, time, json, random
import pandas as pd
import anthropic
from dotenv import load_dotenv

load_dotenv()
client = anthropic.Anthropic()

CSV_FILE = "explosive_media_messages.csv"
GOLDEN_FILE = "golden_dataset.csv"
PROGRESS_FILE = "classify_progress.json"
BATCH_SIZE = 10
SAVE_EVERY = 5  # save after every 5 batches
MODEL = "claude-haiku-4-5-20251001"

# Load progress from previous runs
progress = {}
if os.path.exists(PROGRESS_FILE):
    progress = json.load(open(PROGRESS_FILE))
    print(f"Resuming: {len(progress)} rows already classified")

# Load data
golden = pd.read_csv(GOLDEN_FILE)
df = pd.read_csv(CSV_FILE)

# Cast columns to object for writing
for col in ("theme", "keywords", "include_person", "AI_generated"):
    if col in df.columns:
        df[col] = df[col].astype(object)

# Get golden set row indices (already classified, don't redo)
golden_orig_rows = set(int(r) for r in golden["original_row"].dropna())

# Build few-shot examples from golden set — pick diverse, high-quality examples
def format_example(row):
    """Format a golden row as a few-shot example."""
    text = str(row.get("message_text_english", "")).strip()[:400]
    theme = str(row.get("theme", "")).strip()
    keywords = str(row.get("keywords", "")).strip()
    person = str(row.get("include_person", "")).strip()
    ai_gen = str(row.get("AI_generated", "")).strip()
    has_media = str(row.get("has_media", "")).strip()
    media = str(row.get("media_filename", "")).strip()

    if text == "nan":
        text = "(no text)"
    return {
        "text": text,
        "has_media": has_media,
        "media_type": "video" if media.endswith((".mp4", ".mov")) else ("image" if media.endswith((".jpg", ".png")) else "none"),
        "theme": theme if theme and theme != "nan" else "",
        "keywords": keywords if keywords and keywords != "nan" else "",
        "include_person": person if person and person != "nan" else "",
        "AI_generated": ai_gen if ai_gen and ai_gen != "nan" else "",
    }

# Get diverse examples — 2 per theme max
examples_by_theme = {}
for _, row in golden.iterrows():
    theme = str(row.get("theme", "")).strip()
    if not theme or theme == "nan":
        continue
    examples_by_theme.setdefault(theme, []).append(format_example(row))

few_shot = []
for theme, examples in examples_by_theme.items():
    few_shot.extend(examples[:2])  # up to 2 per theme

# Limit total few-shot to 25 examples to keep context manageable
random.seed(42)
random.shuffle(few_shot)
few_shot = few_shot[:25]

print(f"Using {len(few_shot)} few-shot examples across {len(examples_by_theme)} themes")

# Build list of rows to classify (not in golden, not already done)
to_classify = []
for idx in df.index:
    if idx in golden_orig_rows:
        continue
    if str(idx) in progress:
        continue
    to_classify.append(idx)

print(f"{len(to_classify)} rows to classify")

if not to_classify:
    print("Nothing to do. Merging existing progress...")
else:
    # Build the system prompt with few-shot examples
    available_themes = sorted(set(str(r.get("theme", "")).strip() for _, r in golden.iterrows() if str(r.get("theme", "")).strip() and str(r.get("theme", "")).strip() != "nan"))

    system_prompt = f"""You are classifying Telegram messages from @ExplosiveMedia (Persian channel).

For each message, return a JSON object with:
- theme: ONE of these exact values: {available_themes}
- keywords: comma-separated English keywords (3-6 tags)
- include_person: person/figure named in post (if any, else empty string)
- AI_generated: "Yes" if AI-generated content, "No" otherwise

You will receive a batch of messages. Return a JSON array of classification objects, one per message, in order.

Here are {len(few_shot)} examples of correctly classified messages:

{json.dumps(few_shot, ensure_ascii=False, indent=2)}

Rules:
- Output ONLY a JSON array. No prose, no markdown.
- Pick the SINGLE best theme from the allowed list.
- Keywords should be concise, English, comma-separated.
- If no person mentioned, use empty string for include_person.
- Use "Yes"/"No" for AI_generated, not true/false."""

    done_this_run = 0
    for batch_start in range(0, len(to_classify), BATCH_SIZE):
        batch_indices = to_classify[batch_start:batch_start + BATCH_SIZE]
        batch_items = []
        for i, idx in enumerate(batch_indices, 1):
            r = df.iloc[idx]
            text = str(r.get("message_text_english", "")).strip()[:400]
            has_media = str(r.get("has_media", "")).strip()
            media = str(r.get("media_filename", "")).strip()
            media_type = "video" if media.endswith((".mp4", ".mov")) else ("image" if media.endswith((".jpg", ".png")) else "none")
            if text == "nan":
                text = "(no text)"
            batch_items.append({
                "_id": i,
                "text": text,
                "has_media": has_media,
                "media_type": media_type,
            })

        user_msg = f"Classify these {len(batch_items)} messages. Return a JSON array with {len(batch_items)} objects.\n\n{json.dumps(batch_items, ensure_ascii=False)}"

        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=2048,
                system=system_prompt,
                messages=[{"role": "user", "content": user_msg}]
            )
            raw = response.content[0].text.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            classifications = json.loads(raw)

            for i, idx in enumerate(batch_indices):
                if i < len(classifications):
                    c = classifications[i]
                    progress[str(idx)] = c
                    done_this_run += 1
                else:
                    progress[str(idx)] = {"theme": "", "keywords": "", "include_person": "", "AI_generated": ""}
        except Exception as e:
            print(f"  [batch error at row {batch_indices[0]}]: {e}")
            for idx in batch_indices:
                progress[str(idx)] = {"theme": "", "keywords": "", "include_person": "", "AI_generated": "[classify failed]"}

        batch_num = batch_start // BATCH_SIZE + 1
        total_batches = (len(to_classify) + BATCH_SIZE - 1) // BATCH_SIZE
        print(f"  [{done_this_run}/{len(to_classify)}] batch {batch_num}/{total_batches}")

        if batch_num % SAVE_EVERY == 0:
            with open(PROGRESS_FILE, "w") as f:
                json.dump(progress, f)

        time.sleep(0.3)

    with open(PROGRESS_FILE, "w") as f:
        json.dump(progress, f)

# Merge classifications into CSV
df = pd.read_csv(CSV_FILE)
for col in ("theme", "keywords", "include_person", "AI_generated"):
    if col in df.columns:
        df[col] = df[col].astype(object)

merged = 0
for idx_str, c in progress.items():
    idx = int(idx_str)
    for field in ("theme", "keywords", "include_person", "AI_generated"):
        val = c.get(field, "")
        if val:
            df.at[idx, field] = val
    merged += 1

df.to_csv(CSV_FILE, index=False)
print(f"\nDone. Classified and merged {merged} rows into CSV.")
