#!/usr/bin/env python3
"""Phase 1 stance classifier, round 3 — golden rows only.

Round 2 ran the whole 2,840-message corpus and scored 0.664 on the golden set,
with 103 of its 114 errors being posts hand-coded Neither that the model called
Pro-regime. The v3 prompt replaces the round-2 bullet that told the model
criticism of foreign governments "is often implicitly pro-regime" with an
explicit instruction to exclude it. This run therefore only needs the 339
hand-coded rows: it is a prompt test, not a corpus pass.

Evidence per message is identical to rounds 1 and 2 (message_payload), and the
rows come from the corpus by positional index, which is what golden's
`original_row` refers to.

Writes CSVs/phase1_stance_predictions_v3.csv (339 rows) and prints the score
against the golden labels next to round 2's.

    python scripts/classify_phase1_v3.py
"""

import hashlib
import json
import os
import sys
import time
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI

BASE = Path(__file__).resolve().parent.parent.parent
load_dotenv(BASE / ".env", override=True)

CSVS = BASE / "explosive-media-analysis" / "CSVs"
MAIN_CSV = CSVS / "explosive_media_messages.csv"
GOLDEN_CSV = CSVS / "golden_dataset.csv"
V2_CSV = CSVS / "phase1_stance_predictions.csv"
OUT_CSV = CSVS / "phase1_stance_predictions_v3.csv"
SCHEMA_PATH = BASE / "explosive-media-analysis" / "schema.md"

# Round 3 gets its own cache directory. Sharing round 2's would be harmless
# (keys hash the prompt) but keeping them apart makes it obvious which run a
# cached response belongs to.
CACHE_DIR = BASE / "explosive-media-analysis" / "cache_p1v3"
CACHE_DIR.mkdir(exist_ok=True)

MODEL_TEXT = "anthropic/claude-opus-5"
COST = {"anthropic/claude-opus-5": (5.00, 25.00)}  # $ per Mtok (in, out)
BATCH_SIZE = 10

client = OpenAI(base_url="https://openrouter.ai/api/v1",
                api_key=os.environ["OPENROUTER_API_KEY"])

_spend = {"in": 0, "out": 0, "usd": 0.0}


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

def load_schema(path=SCHEMA_PATH):
    """Parse schema.md into {theme: definition}."""
    import re
    defs = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("---"):
            continue
        m = (re.match(r"^\*\*(.+?):\*\*\s*(.+)$", line)
             or re.match(r"^([A-Z][A-Za-z &]+):\s*(.+)$", line))
        if m:
            defs[m.group(1).strip()] = m.group(2).strip()
    return defs


CANON = {"gaza genocide": "Gaza Genocide", "lego": "LEGO"}


def canon(t):
    t = str(t).strip()
    return CANON.get(t.lower(), t)


SCHEMA = {canon(k): v for k, v in load_schema().items()}

PHASE1_PROMPT_V3 = f"""You are classifying messages from @ExplosiveMedia, a Persian-language Telegram news channel, for a journalism project studying how the channel's messaging changed before and after the Iran-US war that began 28 February 2026.
Your task: decide whether each message expresses a PRO-REGIME stance, an ANTI-REGIME stance, or NEITHER, with respect to the Iranian government and state.
These are the stance definitions, written by the researcher:
**Pro-regime:** {SCHEMA['Pro-regime']}
**Anti-regime:** {SCHEMA['Anti-regime']}
Guidance:
  - "The regime" means the Iranian state, its government, leadership and institutions.
  - Do not include posts where opponents of the Iranian government like Netanyahu are criticized because they are criticized outside of any opinions about the state as ewell
  - Neutral factual reporting with no evaluative framing is Neither. The test for Pro-regime is whether the framing reflects well on the Iranian state, not merely whether the subject is Iranian. Reporting that Iran did something is not pro-regime; celebrating it is.
  - A post can carry a stance while being mainly about something else. Use `is_primary` to record whether the stance is the post's main subject or a secondary aspect.
  - Sarcasm and mockery are central to this channel's voice. A headline that undercuts or ridicules the official statement beneath it is anti-regime; a headline that cheers an official on is pro-regime.
  - If the message has no text, judge from the audio transcription if present. If there is no usable evidence at all, answer Neither with low confidence.

  For each message return an object with:
  - "stance": exactly one of "Pro-regime", "Anti-regime", "Neither"
  - "is_primary": true if the stance is the post's main subject, false if secondary. Use false when stance is "Neither".
  - "confidence": "high", "medium" or "low"
  - "reason": one short sentence citing the specific wording or content that decided it

  Output ONLY a JSON array. No prose, no markdown fences."""


# ---------------------------------------------------------------------------
# Call harness — same caching and payload shape as rounds 1 and 2
# ---------------------------------------------------------------------------

def _cache_key(model, system, payload):
    blob = json.dumps([model, system, payload], ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:24]


def call_batch(system, payload, model=MODEL_TEXT, max_tokens=4096, retries=4):
    """Send one batch, return the parsed JSON array. Cached on disk."""
    cached = CACHE_DIR / f"{_cache_key(model, system, payload)}.json"
    if cached.exists():
        return json.loads(cached.read_text())

    user = (f"Classify these {len(payload)} messages. "
            f"Return a JSON array of exactly {len(payload)} objects, in the same order.\n\n"
            + json.dumps(payload, ensure_ascii=False))

    for attempt in range(retries):
        try:
            r = client.chat.completions.create(
                model=model, max_tokens=max_tokens, temperature=0,
                messages=[{"role": "system", "content": system},
                          {"role": "user", "content": user}],
            )
            raw = r.choices[0].message.content.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            out = json.loads(raw)
            if not isinstance(out, list) or len(out) != len(payload):
                raise ValueError(f"expected {len(payload)} objects, got "
                                 f"{len(out) if isinstance(out, list) else type(out)}")

            u = r.usage
            cin, cout = COST.get(model, (0, 0))
            _spend["in"] += u.prompt_tokens
            _spend["out"] += u.completion_tokens
            _spend["usd"] += u.prompt_tokens / 1e6 * cin + u.completion_tokens / 1e6 * cout

            cached.write_text(json.dumps(out, ensure_ascii=False))
            return out
        except Exception as e:
            if attempt == retries - 1:
                print(f"\n    [FAILED after {retries}] {type(e).__name__}: {str(e)[:120]}")
                return [{"_error": str(e)[:200]} for _ in payload]
            time.sleep(2 ** attempt)


def message_payload(row, idx):
    """The evidence the classifier sees — unchanged from rounds 1 and 2."""
    def clean(v, limit=1200):
        s = str(v).strip()
        return "" if s in ("", "nan") else s[:limit]

    media = clean(row.get("media_filename"), 100)
    item = {
        "_id": idx,
        "date": clean(row.get("date")),
        "text": clean(row.get("message_text_english")) or "(no text)",
        "media_type": ("video" if media.endswith((".mp4", ".mov"))
                       else "image" if media.endswith((".jpg", ".png")) else "none"),
    }
    if audio := clean(row.get("audio_transcription_english"), 800):
        item["audio_transcription"] = audio
    if ocr := clean(row.get("ocr_text_english"), 400):
        item["on_screen_text"] = ocr
    return item


def run_classifier(frame, system, batch_size=BATCH_SIZE, label="run"):
    rows, results = list(frame.iterrows()), []
    total = (len(rows) + batch_size - 1) // batch_size
    for b, i in enumerate(range(0, len(rows), batch_size), 1):
        chunk = rows[i:i + batch_size]
        payload = [message_payload(r, j) for j, (_, r) in enumerate(chunk, 1)]
        results.extend(call_batch(system, payload))
        print(f"\r  {label}: batch {b}/{total}  (${_spend['usd']:.2f})", end="", flush=True)
    print(f"\r  {label}: {len(results)} classified, ${_spend['usd']:.2f} this run")
    return results


# ---------------------------------------------------------------------------
# Ground truth
# ---------------------------------------------------------------------------

def stance_truth(row):
    """Hand-coded stance, reading all four theme columns."""
    th = {canon(row.get(c, "")) for c in ("theme", "theme2", "theme3", "theme4")}
    pro, anti = "Pro-regime" in th, "Anti-regime" in th
    return ("Both" if pro and anti else "Pro-regime" if pro
            else "Anti-regime" if anti else "Neither")


LABELS = ["Pro-regime", "Anti-regime", "Neither"]


def score(truth, pred, title):
    print(f"\n{title}")
    print(f"  accuracy {(truth == pred).mean():.3f}   "
          f"(majority-class baseline {(truth == 'Neither').mean():.3f})")
    print(f"  {'class':14s}{'P':>8}{'R':>8}{'F1':>8}{'support':>9}")
    f1s = []
    for c in LABELS:
        tp = ((truth == c) & (pred == c)).sum()
        fp = ((truth != c) & (pred == c)).sum()
        fn = ((truth == c) & (pred != c)).sum()
        P = tp / (tp + fp) if tp + fp else 0.0
        R = tp / (tp + fn) if tp + fn else 0.0
        F = 2 * P * R / (P + R) if P + R else 0.0
        f1s.append(F)
        print(f"  {c:14s}{P:8.3f}{R:8.3f}{F:8.3f}{(truth == c).sum():9d}")
    print(f"  macro F1: {sum(f1s) / 3:.3f}")
    return sum(f1s) / 3


def main():
    golden = pd.read_csv(GOLDEN_CSV, encoding="utf-8-sig")
    corpus = pd.read_csv(MAIN_CSV, encoding="utf-8-sig")

    golden = golden[golden["theme"].notna()
                    & (golden["theme"].astype(str).str.strip() != "")].copy()
    golden["_stance"] = golden.apply(stance_truth, axis=1)

    # golden.original_row is a positional index into the corpus.
    rows = corpus.loc[golden["original_row"].values].copy()
    print(f"golden rows: {len(golden)}   ground truth: "
          f"{golden['_stance'].value_counts().to_dict()}")

    n_batches = (len(rows) + BATCH_SIZE - 1) // BATCH_SIZE
    print(f"{len(rows)} messages -> {n_batches} batches, "
          f"~${n_batches * (3700 / 1e6 * 5 + 1300 / 1e6 * 25):.2f} if uncached\n")

    preds = run_classifier(rows, PHASE1_PROMPT_V3, label="phase1-v3/golden")

    out = pd.DataFrame({
        "original_row": golden["original_row"].values,
        "date": rows["date"].values,
        "message_text_english": rows["message_text_english"].values,
        "p1_stance": [c.get("stance", "") for c in preds],
        "p1_is_primary": [c.get("is_primary", False) for c in preds],
        "p1_confidence": [c.get("confidence", "") for c in preds],
        "p1_reason": [c.get("reason", "") for c in preds],
        "hand_coded_stance": golden["_stance"].values,
    })
    out["agrees"] = out["p1_stance"] == out["hand_coded_stance"]
    out.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")

    errors = sum(1 for c in preds if "_error" in c)
    print(f"errors: {errors}   ->  {OUT_CSV.name}")

    ev = out[out["p1_stance"].astype(str).str.strip() != ""]
    if len(ev) < len(out):
        print(f"WARNING: {len(out) - len(ev)} rows have no prediction — excluded")

    score(ev["hand_coded_stance"], ev["p1_stance"], "=== ROUND 3 (this run)")

    # Round 2, on the same rows, for a like-for-like comparison.
    v2 = pd.read_csv(V2_CSV, encoding="utf-8-sig").set_index("original_row")
    v2p = v2.loc[ev["original_row"].values, "p1_stance"]
    score(ev["hand_coded_stance"].reset_index(drop=True),
          v2p.reset_index(drop=True), "=== ROUND 2 (shipped, same rows)")

    print("\nRound 3 confusion (rows = hand-coded, cols = model):")
    print(pd.crosstab(ev["hand_coded_stance"], ev["p1_stance"])
            .reindex(index=LABELS, columns=LABELS, fill_value=0).to_string())

    print("\nRound 3 accuracy by model confidence:")
    print(ev.assign(ok=ev["agrees"]).groupby("p1_confidence")["ok"]
            .agg(["mean", "count"]).round(3).to_string())

    moved = (v2p.values != ev["p1_stance"].values).sum()
    fixed = ((v2p.values != ev["hand_coded_stance"].values)
             & (ev["p1_stance"].values == ev["hand_coded_stance"].values)).sum()
    broke = ((v2p.values == ev["hand_coded_stance"].values)
             & (ev["p1_stance"].values != ev["hand_coded_stance"].values)).sum()
    print(f"\nvs round 2: {moved} predictions changed — {fixed} newly correct, "
          f"{broke} newly wrong")

    dis = ev[~ev["agrees"]]
    print(f"\n{'=' * 70}\nRemaining disagreements ({len(dis)}):")
    for _, r in dis.head(25).iterrows():
        print(f"  [{r.original_row}] you: {r.hand_coded_stance:12s} "
              f"model: {r.p1_stance:12s} ({r.p1_confidence})")
        print(f"     {str(r.message_text_english)[:120]}")
        print(f"     why: {r.p1_reason}")


if __name__ == "__main__":
    sys.exit(main())
