"""Evaluate the LLM classifier against hand-coded golden labels.

Reproduces the same few-shot selection as classify_llm.py (25 examples, seed=42),
runs Claude Haiku on the remaining golden rows, and writes predictions to
eval_predictions.csv for precision/recall analysis in the notebook.
"""

import os, json, random, time
import pandas as pd
import anthropic
from dotenv import load_dotenv

load_dotenv()
client = anthropic.Anthropic()

GOLDEN_FILE = "/Users/towcenter/Desktop/explosive-media-footage/explosive-media-analysis/CSVs/golden_dataset.csv"
OUT_FILE = "/Users/towcenter/Desktop/explosive-media-footage/explosive-media-analysis/CSVs/eval_predictions.csv"
MODEL = "claude-haiku-4-5-20251001"
BATCH_SIZE = 10

golden = pd.read_csv(GOLDEN_FILE)
golden = golden[golden["theme"].notna() & (golden["theme"].astype(str).str.strip() != "")].copy()
golden = golden.reset_index(drop=True)
print(f"Golden rows with hand-coded theme: {len(golden)}")


def fmt_example(row):
    text = str(row.get("message_text_english", "")).strip()[:400]
    media = str(row.get("media_filename", "")).strip()
    return {
        "text": "(no text)" if text == "nan" else text,
        "has_media": str(row.get("has_media", "")).strip(),
        "media_type": "video" if media.endswith((".mp4", ".mov")) else ("image" if media.endswith((".jpg", ".png")) else "none"),
        "theme": str(row.get("theme", "")).strip(),
        "keywords": str(row.get("keywords", "")).strip() if str(row.get("keywords", "")).strip() != "nan" else "",
        "include_person": str(row.get("include_person", "")).strip() if str(row.get("include_person", "")).strip() != "nan" else "",
        "AI_generated": str(row.get("AI_generated", "")).strip() if str(row.get("AI_generated", "")).strip() != "nan" else "",
    }


# Same few-shot picking logic as classify_llm.py, so we can hold out the rest.
by_theme = {}
for i, r in golden.iterrows():
    by_theme.setdefault(str(r["theme"]).strip(), []).append((i, fmt_example(r)))

few_shot_pairs = []
for theme, items in by_theme.items():
    few_shot_pairs.extend(items[:2])

random.seed(42)
random.shuffle(few_shot_pairs)
few_shot_pairs = few_shot_pairs[:25]
fs_indices = set(idx for idx, _ in few_shot_pairs)
few_shot = [ex for _, ex in few_shot_pairs]

eval_df = golden[~golden.index.isin(fs_indices)].copy()
print(f"Few-shot examples: {len(few_shot)} | held-out eval rows: {len(eval_df)}")

available_themes = sorted(by_theme.keys())
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

predictions = {}
eval_indices = list(eval_df.index)
total_batches = (len(eval_indices) + BATCH_SIZE - 1) // BATCH_SIZE

for batch_num, start in enumerate(range(0, len(eval_indices), BATCH_SIZE), 1):
    chunk = eval_indices[start:start + BATCH_SIZE]
    items = []
    for i, idx in enumerate(chunk, 1):
        r = eval_df.loc[idx]
        text = str(r.get("message_text_english", "")).strip()[:400]
        media = str(r.get("media_filename", "")).strip()
        items.append({
            "_id": i,
            "text": "(no text)" if text == "nan" else text,
            "has_media": str(r.get("has_media", "")).strip(),
            "media_type": "video" if media.endswith((".mp4", ".mov")) else ("image" if media.endswith((".jpg", ".png")) else "none"),
        })

    user_msg = f"Classify these {len(items)} messages. Return a JSON array with {len(items)} objects.\n\n{json.dumps(items, ensure_ascii=False)}"

    try:
        resp = client.messages.create(
            model=MODEL,
            max_tokens=2048,
            system=system_prompt,
            messages=[{"role": "user", "content": user_msg}],
        )
        raw = resp.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        cls = json.loads(raw)
        for j, idx in enumerate(chunk):
            if j < len(cls):
                predictions[idx] = cls[j]
            else:
                predictions[idx] = {"theme": "", "keywords": "", "include_person": "", "AI_generated": ""}
    except Exception as e:
        print(f"  [batch error at row {chunk[0]}]: {e}")
        for idx in chunk:
            predictions[idx] = {"theme": "", "keywords": "", "include_person": "", "AI_generated": "[error]"}

    print(f"  batch {batch_num}/{total_batches} done")
    time.sleep(0.3)

eval_df["predicted_theme"] = eval_df.index.map(lambda i: predictions.get(i, {}).get("theme", ""))
eval_df["predicted_keywords"] = eval_df.index.map(lambda i: predictions.get(i, {}).get("keywords", ""))
eval_df["predicted_AI_generated"] = eval_df.index.map(lambda i: predictions.get(i, {}).get("AI_generated", ""))
eval_df["predicted_include_person"] = eval_df.index.map(lambda i: predictions.get(i, {}).get("include_person", ""))

cols = ["original_row", "message_text_english", "theme", "predicted_theme",
        "keywords", "predicted_keywords", "AI_generated", "predicted_AI_generated",
        "include_person", "predicted_include_person"]
cols = [c for c in cols if c in eval_df.columns]
eval_df[cols].to_csv(OUT_FILE, index=False)
print(f"\nWrote {len(eval_df)} predictions to {OUT_FILE}")
