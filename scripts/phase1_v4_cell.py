# PHASE 1 v4 — run v4_structured.txt on the FULL corpus (2,840 messages).
#
# Differences from the round-2 cell above, all forced by v4_structured.txt:
#   - model is google/gemini-2.5-flash, not Opus 5
#   - the prompt is read from disk, not built from SCHEMA at runtime
#   - the METRICS footer is stripped before sending AND before hashing, so
#     lab.py rewriting the score block does not invalidate the cache
#   - v4 returns `reasoning` (not `reason`) and has NO is_primary field
#
# Self-contained: does not depend on cells 5-13 having been run.

import hashlib, json, os, random, re, shutil, threading, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI

BASE = Path("/Users/towcenter/Desktop/explosive-media-footage")
CSVS = BASE / "explosive-media-analysis" / "CSVs"
load_dotenv(BASE / ".env", override=True)

PROMPT_FILE = BASE / "v4_structured.txt"
MAIN_CSV    = CSVS / "explosive_media_messages.csv"
GOLDEN_CSV  = CSVS / "golden_dataset.csv"
OUT_CSV     = CSVS / "phase1_stance_predictions_v4.csv"
CANONICAL   = CSVS / "phase1_stance_predictions.csv"   # what build.py + the site read

MODEL      = "google/gemini-2.5-flash"
COST       = (0.30, 2.50)          # $ per Mtok (in, out)
BATCH_SIZE = 10
MAX_WORKERS = 8                    # concurrent API calls; 1 restores serial behaviour
CACHE_DIR  = BASE / "explosive-media-analysis" / "cache_p1v4"
CACHE_DIR.mkdir(exist_ok=True)

# Flip to True to make v4 the file the charts build from. Round 2 is copied to
# phase1_stance_predictions_v2.csv first, so nothing is lost.
PROMOTE = False

client = OpenAI(base_url="https://openrouter.ai/api/v1",
                api_key=os.environ["OPENROUTER_API_KEY"])
_spend = {"in": 0, "out": 0, "usd": 0.0, "cached": 0}
_spend_lock = threading.Lock()     # `+=` on a dict item is not atomic across threads
_draw_lock  = threading.Lock()     # keeps concurrent progress writes from interleaving


def load_prompt(path=PROMPT_FILE):
    """The prompt without lab.py's METRICS footer.

    The footer is a scoreboard, not an instruction — leaving it in would both
    tell the model its own past accuracy and bust every cache key each time
    lab.py rewrites it.
    """
    txt = path.read_text(encoding="utf-8")
    return re.split(r"\n-{3,}\s*\n\s*<!--\s*METRICS", txt)[0].strip()


PROMPT_V4 = load_prompt()
print(f"prompt: {len(PROMPT_V4)} chars, METRICS footer stripped "
      f"({'still present!' if 'METRICS' in PROMPT_V4 else 'clean'})")


def _cache_key(model, system, payload):
    blob = json.dumps([model, system, payload], ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:24]


def call_batch(system, payload, model=MODEL, max_tokens=4096, retries=4):
    cached = CACHE_DIR / f"{_cache_key(model, system, payload)}.json"
    if cached.exists():
        with _spend_lock:
            _spend["cached"] += 1
        return json.loads(cached.read_text())

    user = (f"Classify these {len(payload)} messages. "
            f"Return a JSON array of exactly {len(payload)} objects, in the same order.\n\n"
            + json.dumps(payload, ensure_ascii=False))

    for attempt in range(retries):
        try:
            r = client.chat.completions.create(
                model=model, max_tokens=max_tokens, temperature=0,
                messages=[{"role": "system", "content": system},
                          {"role": "user", "content": user}])
            raw = r.choices[0].message.content.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            out = json.loads(raw)
            if not isinstance(out, list) or len(out) != len(payload):
                raise ValueError(f"expected {len(payload)} objects, got "
                                 f"{len(out) if isinstance(out, list) else type(out)}")
            u = r.usage
            with _spend_lock:
                _spend["in"]  += u.prompt_tokens
                _spend["out"] += u.completion_tokens
                _spend["usd"] += (u.prompt_tokens / 1e6 * COST[0]
                                  + u.completion_tokens / 1e6 * COST[1])
            cached.write_text(json.dumps(out, ensure_ascii=False))
            return out
        except Exception as e:
            if attempt == retries - 1:
                print(f"\n    [FAILED after {retries}] {type(e).__name__}: {str(e)[:120]}")
                return [{"_error": str(e)[:200]} for _ in payload]
            # Concurrency makes 429s likely, so back off harder on rate limits and
            # jitter every sleep so all workers do not retry in lockstep.
            blob = f"{type(e).__name__} {e}".lower()
            rate_limited = any(k in blob for k in ("429", "rate limit", "quota",
                                                   "too many requests", "overloaded"))
            time.sleep((2 ** attempt) * (4 if rate_limited else 1)
                       + random.uniform(0, 0.75))


def message_payload(row, idx):
    """Identical evidence to rounds 1-3, so the comparison stays like-for-like."""
    def clean(v, limit=1200):
        s = str(v).strip()
        return "" if s in ("", "nan") else s[:limit]

    media = clean(row.get("media_filename"), 100)
    item = {"_id": idx,
            "date": clean(row.get("date")),
            "text": clean(row.get("message_text_english")) or "(no text)",
            "media_type": ("video" if media.endswith((".mp4", ".mov"))
                           else "image" if media.endswith((".jpg", ".png")) else "none")}
    if audio := clean(row.get("audio_transcription_english"), 800):
        item["audio_transcription"] = audio
    if ocr := clean(row.get("ocr_text_english"), 400):
        item["on_screen_text"] = ocr
    return item


def _draw(label, done, total, t0, width=26):
    """One in-place progress line: bar, count, spend, throughput, ETA."""
    el   = time.time() - t0
    rate = done / el if el > 0 else 0          # batches/sec
    eta  = (total - done) / rate if rate else None
    pct  = done / total
    bar  = "█" * int(width * pct) + "░" * (width - int(width * pct))
    eta_s = f"{int(eta) // 60}:{int(eta) % 60:02d}" if eta is not None else "--:--"
    with _draw_lock:
        print(f"\r  {label}: {bar} {done}/{total} {pct:5.1%}  "
              f"${_spend['usd']:.2f}  {rate * 60:5.1f} b/min  ETA {eta_s}  "
              f"cache {_spend['cached']}   ", end="", flush=True)


def run_classifier(frame, system, batch_size=BATCH_SIZE, label="run",
                   workers=MAX_WORKERS):
    """Classify `frame` with `workers` concurrent API calls.

    Batches are submitted with their index and written back into a preallocated
    list, so the returned order matches the frame even though completion order
    does not — the callers assign these results positionally onto df columns.
    """
    rows = list(frame.iterrows())
    batches = [[message_payload(r, j) for j, (_, r) in enumerate(rows[i:i + batch_size], 1)]
               for i in range(0, len(rows), batch_size)]
    total, t0 = len(batches), time.time()
    slots, done = [None] * total, 0

    _draw(label, 0, total, t0)
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(call_batch, system, p): b for b, p in enumerate(batches)}
        for fut in as_completed(futures):
            b = futures[fut]
            try:
                slots[b] = fut.result()
            except Exception as e:      # call_batch swallows its own, this is belt-and-braces
                slots[b] = [{"_error": str(e)[:200]} for _ in batches[b]]
            done += 1
            _draw(label, done, total, t0)

    results = [item for slot in slots for item in slot]
    live = total - _spend["cached"]
    print(f"\r  {label}: {len(results)} classified in {time.time() - t0:.0f}s, "
          f"${_spend['usd']:.2f} this run "
          f"({live} live, {_spend['cached']} cached, {workers} workers)" + " " * 20)
    return results


# --- classify the whole corpus ---------------------------------------------
df = pd.read_csv(MAIN_CSV, encoding="utf-8-sig")
n_batches = (len(df) + BATCH_SIZE - 1) // BATCH_SIZE
print(f"{len(df):,} messages -> {n_batches} batches, "
      f"~${n_batches * (3700 / 1e6 * COST[0] + 1300 / 1e6 * COST[1]):.2f} if uncached\n")

p1v4 = run_classifier(df, PROMPT_V4, label="phase1-v4/corpus")

df["p1_stance"]     = [c.get("stance", "") for c in p1v4]
df["p1_confidence"] = [c.get("confidence", "") for c in p1v4]
df["p1_reason"]     = [c.get("reasoning", c.get("reason", "")) for c in p1v4]
df["p1_is_primary"] = ""          # v4 does not ask for it; kept so the schema matches

(df[["date", "message_text_english", "p1_stance", "p1_is_primary",
     "p1_confidence", "p1_reason"]]
   .rename_axis("original_row").to_csv(OUT_CSV, encoding="utf-8-sig"))

errors = sum(1 for c in p1v4 if "_error" in c)
blank  = (df["p1_stance"].astype(str).str.strip() == "").sum()
print(f"errors: {errors}   blank: {blank}   ->  {OUT_CSV.name}")
print(df["p1_stance"].value_counts().to_string())

# --- score on the golden set ------------------------------------------------
CANON = {"gaza genocide": "Gaza Genocide", "lego": "LEGO"}
canon = lambda t: CANON.get(str(t).strip().lower(), str(t).strip())

golden = pd.read_csv(GOLDEN_CSV, encoding="utf-8-sig")
golden = golden[golden["theme"].notna()
                & (golden["theme"].astype(str).str.strip() != "")].copy()


def stance_truth(row):
    th = {canon(row.get(c, "")) for c in ("theme", "theme2", "theme3", "theme4")}
    pro, anti = "Pro-regime" in th, "Anti-regime" in th
    return ("Both" if pro and anti else "Pro-regime" if pro
            else "Anti-regime" if anti else "Neither")


golden["_stance"] = golden.apply(stance_truth, axis=1)
ev = golden[["original_row", "_stance", "message_text_english"]].copy()
sub = df.loc[ev["original_row"]]
ev["pred"] = sub["p1_stance"].values
ev["conf"] = sub["p1_confidence"].values
ev["why"]  = sub["p1_reason"].values
ev = ev[ev["pred"].astype(str).str.strip() != ""]

LABELS = ["Pro-regime", "Anti-regime", "Neither"]
print(f"\n{'=' * 70}\nScored on {len(ev)} golden rows")
print(f"Accuracy: {(ev._stance == ev.pred).mean():.3f}   "
      f"(majority-class baseline {(ev._stance == 'Neither').mean():.3f})\n")
print(f"{'class':14s}{'P':>8}{'R':>8}{'F1':>8}{'truth':>7}{'pred':>6}")
f1s = []
for c in LABELS:
    tp = ((ev._stance == c) & (ev.pred == c)).sum()
    fp = ((ev._stance != c) & (ev.pred == c)).sum()
    fn = ((ev._stance == c) & (ev.pred != c)).sum()
    P = tp / (tp + fp) if tp + fp else 0.0
    R = tp / (tp + fn) if tp + fn else 0.0
    F = 2 * P * R / (P + R) if P + R else 0.0
    f1s.append(F)
    print(f"{c:14s}{P:8.3f}{R:8.3f}{F:8.3f}{(ev._stance == c).sum():7d}{(ev.pred == c).sum():6d}")
print(f"\nmacro F1: {sum(f1s) / 3:.3f}")

print("\nConfusion (rows = hand-coded, cols = model):")
print(pd.crosstab(ev._stance, ev.pred).reindex(index=LABELS, columns=LABELS,
                                               fill_value=0).to_string())

# --- what the charts will actually show -------------------------------------
print("\nCorpus by war period (this is what the site's charts redraw from):")
print(pd.crosstab(df["date"] >= "2026-02-28", df["p1_stance"])
        .rename(index={False: "pre-war", True: "post-war"}).to_string())

if CANONICAL.exists():
    shipped = pd.read_csv(CANONICAL, encoding="utf-8-sig").set_index("original_row")
    prev = shipped["p1_stance"].reindex(df.index)
    print(f"\nvs the shipped round-2 predictions, corpus-wide: "
          f"{(prev.values != df['p1_stance'].values).sum():,} of {len(df):,} labels change")
    print(pd.crosstab(prev, df["p1_stance"]).to_string())

# --- optional promotion -----------------------------------------------------
if PROMOTE:
    if CANONICAL.exists():
        shutil.copy2(CANONICAL, CSVS / "phase1_stance_predictions_v2.csv")
        print("\nround 2 backed up -> phase1_stance_predictions_v2.csv")
    shutil.copy2(OUT_CSV, CANONICAL)
    print(f"v4 promoted -> {CANONICAL.name}. Now rerun:")
    print("    python scripts/make_thumbs.py && python scripts/build.py")
else:
    print(f"\nPROMOTE is False — {CANONICAL.name} untouched, charts still show round 2.")
