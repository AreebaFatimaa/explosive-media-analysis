"""Prompt lab for the pro/anti-regime stance classifier.

Usage:
  python lab.py run <prompt_name> [--model M] [--limit N] [--batch-size N]
  python lab.py compare <prompt_a> <prompt_b>
  python lab.py errors <prompt_name> [--class Pro-regime|Anti-regime|Neither] [--n 20]
  python lab.py list

Prompts live in prompts/*.txt as plain system prompts.
Ground truth is the primary `theme` column of CSVs/golden_dataset.csv:
  theme == "Pro-regime"  -> Pro-regime
  theme == "Anti-regime" -> Anti-regime
  anything else          -> Neither

Structured outputs are enforced via OpenRouter json_schema response_format.
Requests are cached per (model, prompt, payload) hash — editing a prompt
invalidates only that prompt's cache.
"""

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
GOLDEN_CSV = REPO / "CSVs" / "golden_dataset.csv"
PROMPTS_DIR = ROOT / "prompts"
RUNS_DIR = ROOT / "runs"
CACHE_DIR = ROOT / ".cache"

DEFAULT_MODEL = "google/gemini-2.5-flash"
BATCH_SIZE = 25
CONCURRENCY = 5
LABELS = ["Pro-regime", "Anti-regime", "Neither"]
THEME_COLS = ["theme", "theme2", "theme3", "theme4"]
METRICS_MARKER = "\n---\n<!-- METRICS: auto-updated by lab.py, ignored by cache -->\n"

RESPONSE_SCHEMA = {
    "name": "stance_classifications",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["classifications"],
        "properties": {
            "classifications": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["id", "stance", "confidence", "reasoning"],
                    "properties": {
                        "id": {"type": "integer"},
                        "stance": {"type": "string", "enum": LABELS},
                        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                        "reasoning": {"type": "string"},
                    },
                },
            }
        },
    },
}


def load_client():
    load_dotenv(REPO / ".env")
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        sys.exit("OPENROUTER_API_KEY not set in .env")
    return OpenAI(base_url="https://openrouter.ai/api/v1", api_key=key)


def load_golden():
    """Ground truth checks theme, theme2, theme3, theme4:
      Pro-regime in any col  -> Pro-regime
      else Anti-regime in any col -> Anti-regime
      else -> Neither
    Only rows with a hand-coded primary `theme` are included in scoring."""
    df = pd.read_csv(GOLDEN_CSV)
    df = df[df["theme"].notna() & (df["theme"].astype(str).str.strip() != "")].copy()

    def truth(row):
        vals = {str(row.get(c, "")).strip() for c in THEME_COLS}
        if "Pro-regime" in vals:
            return "Pro-regime"
        if "Anti-regime" in vals:
            return "Anti-regime"
        return "Neither"

    df["_truth"] = df.apply(truth, axis=1)
    return df.reset_index(drop=True)


def payload_for(row, idx):
    def clean(v, limit=1200):
        s = str(v).strip()
        return "" if s in ("", "nan") else s[:limit]

    item = {
        "id": idx,
        "text": clean(row.get("message_text_english")) or "(no text)",
    }
    if audio := clean(row.get("audio_transcription_english"), 800):
        item["audio_transcription"] = audio
    if ocr := clean(row.get("ocr_text_english"), 400):
        item["on_screen_text"] = ocr
    return item


def cache_key(model, prompt, batch):
    blob = json.dumps([model, prompt, batch], ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:24]


def call_batch(client, model, prompt, batch):
    CACHE_DIR.mkdir(exist_ok=True)
    key = cache_key(model, prompt, batch)
    cached = CACHE_DIR / f"{key}.json"
    if cached.exists():
        return json.loads(cached.read_text()), True

    user_msg = (
        f"Classify these {len(batch)} messages. Return one classification per message, "
        f"using each message's `id` in the output.\n\n"
        + json.dumps(batch, ensure_ascii=False)
    )
    r = client.chat.completions.create(
        model=model,
        temperature=0,
        max_tokens=4096,
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": user_msg},
        ],
        response_format={"type": "json_schema", "json_schema": RESPONSE_SCHEMA},
    )
    parsed = json.loads(r.choices[0].message.content)
    out = parsed["classifications"]
    cached.write_text(json.dumps(out, ensure_ascii=False))
    return out, False


def read_prompt(name):
    """Return (path, prompt_only, full_file_text). Strips the auto-updated
    METRICS block so cache hashes stay stable across score updates."""
    path = PROMPTS_DIR / f"{name}.txt"
    if not path.exists():
        sys.exit(f"Missing prompt: {path}")
    full = path.read_text()
    prompt = full.split(METRICS_MARKER, 1)[0].rstrip() + "\n"
    return path, prompt, full


def run_prompt(name, model=DEFAULT_MODEL, limit=None, batch_size=BATCH_SIZE, concurrency=CONCURRENCY):
    prompt_path, prompt, _ = read_prompt(name)

    df = load_golden()
    if limit:
        df = df.head(limit).copy()

    client = load_client()
    predictions = {}
    starts = list(range(0, len(df), batch_size))
    n_batches = len(starts)
    t0 = time.time()
    lock = threading.Lock()
    state = {"hits": 0, "done": 0}

    print(f"[{name}] {len(df)} rows, {n_batches} batches of {batch_size}, "
          f"concurrency={concurrency}, model={model}", flush=True)

    def do_batch(i, start):
        chunk = df.iloc[start:start + batch_size]
        batch = [payload_for(r, int(r["original_row"])) for _, r in chunk.iterrows()]
        b0 = time.time()
        try:
            out, cached = call_batch(client, model, prompt, batch)
            by_id = {o["id"]: o for o in out}
            local_preds = {}
            for _, r in chunk.iterrows():
                rid = int(r["original_row"])
                local_preds[rid] = by_id.get(rid, {"stance": "", "confidence": "", "reasoning": "[missing]"})
            counts = {"Pro": 0, "Anti": 0, "Neither": 0}
            for o in out:
                s = o.get("stance", "")
                if s == "Pro-regime": counts["Pro"] += 1
                elif s == "Anti-regime": counts["Anti"] += 1
                elif s == "Neither": counts["Neither"] += 1
            with lock:
                predictions.update(local_preds)
                if cached:
                    state["hits"] += 1
                state["done"] += 1
                tag = "cache" if cached else f"{time.time()-b0:4.1f}s"
                print(f"  batch {i:>3}/{n_batches}  {tag}  "
                      f"Pro={counts['Pro']:>2} Anti={counts['Anti']:>2} Neither={counts['Neither']:>2}  "
                      f"({state['done']}/{n_batches} batches, {state['hits']} cached, elapsed {time.time()-t0:5.1f}s)",
                      flush=True)
        except Exception as e:
            with lock:
                state["done"] += 1
                print(f"  batch {i:>3}/{n_batches}  ERROR  {type(e).__name__}: {str(e)[:180]}", flush=True)
                for _, r in chunk.iterrows():
                    predictions[int(r["original_row"])] = {"stance": "", "confidence": "", "reasoning": f"[error] {e}"}

    with ThreadPoolExecutor(max_workers=concurrency) as ex:
        futures = [ex.submit(do_batch, i, start) for i, start in enumerate(starts, 1)]
        for f in as_completed(futures):
            f.result()

    elapsed = round(time.time() - t0, 1)
    fresh_batches = n_batches - state["hits"]
    if fresh_batches:
        print(f"[{name}] finished in {elapsed}s "
              f"({fresh_batches} fresh + {state['hits']} cached batches, "
              f"~{elapsed/fresh_batches:.1f}s/fresh-batch)", flush=True)
    else:
        print(f"[{name}] finished in {elapsed}s (all cached)", flush=True)
    metrics = compute_metrics(df, predictions)
    metrics["elapsed_seconds"] = elapsed
    metrics["batches"] = n_batches
    metrics["fresh_batches"] = fresh_batches
    metrics["concurrency"] = concurrency
    save_run(name, model, df, predictions, metrics)
    write_prompt_metrics(prompt_path, prompt, model, metrics)
    print_metrics(name, metrics)


def format_metrics_block(model, metrics):
    lines = [f"model: {model}", f"scored: {metrics['n']}", f"accuracy: {metrics['accuracy']:.3f}"]
    if "elapsed_seconds" in metrics:
        lines.append(f"elapsed: {metrics['elapsed_seconds']}s "
                     f"({metrics.get('fresh_batches', 0)}/{metrics.get('batches', 0)} fresh, "
                     f"concurrency={metrics.get('concurrency', 1)})")
    lines.append("")
    lines.append(f"  {'class':<14} {'P':>6} {'R':>6} {'F1':>6}  truth  pred")
    for label in LABELS:
        c = metrics["per_class"][label]
        lines.append(f"  {label:<14} {c['precision']:6.3f} {c['recall']:6.3f} {c['f1']:6.3f}  {c['n_truth']:>5}  {c['n_pred']:>4}")
    lines.append("")
    lines.append("  confusion (rows=truth, cols=pred):")
    lines.append("  " + " " * 14 + "".join(f"{l:>12}" for l in LABELS))
    for t in LABELS:
        lines.append(f"  {t:<14}" + "".join(f"{metrics['confusion'][t][p]:>12}" for p in LABELS))
    return "\n".join(lines)


def write_prompt_metrics(path, prompt, model, metrics):
    """Rewrite prompt file = original prompt + auto-updated METRICS block.
    read_prompt() strips the block on load so cache hashes stay stable."""
    block = format_metrics_block(model, metrics)
    path.write_text(prompt.rstrip() + "\n" + METRICS_MARKER + block + "\n")


def compute_metrics(df, predictions):
    scored = df.copy()
    scored["pred"] = scored["original_row"].map(lambda i: predictions.get(int(i), {}).get("stance", ""))

    per_class = {}
    for label in LABELS:
        tp = int(((scored["_truth"] == label) & (scored["pred"] == label)).sum())
        fp = int(((scored["_truth"] != label) & (scored["pred"] == label)).sum())
        fn = int(((scored["_truth"] == label) & (scored["pred"] != label)).sum())
        p = tp / (tp + fp) if tp + fp else 0.0
        r = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * p * r / (p + r) if p + r else 0.0
        per_class[label] = {
            "precision": round(p, 4),
            "recall": round(r, 4),
            "f1": round(f1, 4),
            "n_truth": int((scored["_truth"] == label).sum()),
            "n_pred": int((scored["pred"] == label).sum()),
            "tp": tp, "fp": fp, "fn": fn,
        }

    ct = pd.crosstab(scored["_truth"], scored["pred"], dropna=False)
    for label in LABELS:
        if label not in ct.columns:
            ct[label] = 0
        if label not in ct.index:
            ct.loc[label] = 0
    ct = ct.reindex(index=LABELS, columns=LABELS, fill_value=0)

    return {
        "n": int(len(scored)),
        "accuracy": round(float((scored["_truth"] == scored["pred"]).mean()), 4),
        "per_class": per_class,
        "confusion": {t: {p: int(ct.loc[t, p]) for p in LABELS} for t in LABELS},
    }


def save_run(name, model, df, predictions, metrics):
    """CSV = every golden column, then stance_truth + stance_pred/conf/reasoning."""
    RUNS_DIR.mkdir(exist_ok=True)
    out = df.drop(columns=["_truth"]).copy()
    out["stance_truth"] = df["_truth"].values
    out["stance_pred"] = [predictions.get(int(r), {}).get("stance", "") for r in df["original_row"]]
    out["stance_confidence"] = [predictions.get(int(r), {}).get("confidence", "") for r in df["original_row"]]
    out["stance_reasoning"] = [predictions.get(int(r), {}).get("reasoning", "") for r in df["original_row"]]
    (RUNS_DIR / f"{name}.csv").write_text(out.to_csv(index=False))
    meta = {"model": model, **metrics}
    (RUNS_DIR / f"{name}.meta.json").write_text(json.dumps(meta, indent=2))


def print_metrics(name, metrics):
    print(f"\n=== {name}  ({metrics['n']} scored) ===")
    print(f"\n  {'class':<14} {'P':>6} {'R':>6} {'F1':>6}  truth  pred")
    for label in LABELS:
        c = metrics["per_class"][label]
        print(f"  {label:<14} {c['precision']:6.3f} {c['recall']:6.3f} {c['f1']:6.3f}  {c['n_truth']:>5}  {c['n_pred']:>4}")

    print("\n  confusion (rows=truth, cols=pred):")
    header = " " * 14 + "".join(f"{l:>12}" for l in LABELS)
    print("  " + header)
    for t in LABELS:
        row = f"  {t:<14}" + "".join(f"{metrics['confusion'][t][p]:>12}" for p in LABELS)
        print(row)

    print(f"\n  accuracy: {metrics['accuracy']:.3f}")
    print(f"  wrote runs/{name}.csv + runs/{name}.meta.json")


def compare(a, b):
    for name in (a, b):
        path = RUNS_DIR / f"{name}.csv"
        if not path.exists():
            sys.exit(f"No run for '{name}'. Run it first: python lab.py run {name}")

    da = pd.read_csv(RUNS_DIR / f"{a}.csv")[["original_row", "stance_truth", "stance_pred", "message_text_english"]]
    db = pd.read_csv(RUNS_DIR / f"{b}.csv")[["original_row", "stance_pred"]]
    da = da.rename(columns={"stance_pred": f"pred_{a}"})
    db = db.rename(columns={"stance_pred": f"pred_{b}"})
    merged = da.merge(db, on="original_row")

    def f1(df, col, label):
        tp = ((df["stance_truth"] == label) & (df[col] == label)).sum()
        fp = ((df["stance_truth"] != label) & (df[col] == label)).sum()
        fn = ((df["stance_truth"] == label) & (df[col] != label)).sum()
        p = tp / (tp + fp) if tp + fp else 0.0
        r = tp / (tp + fn) if tp + fn else 0.0
        return 2 * p * r / (p + r) if p + r else 0.0

    print(f"\n  {'class':<14} {'F1 '+a:>14} {'F1 '+b:>14} {'Δ':>8}")
    for label in LABELS:
        fa, fb = f1(merged, f"pred_{a}", label), f1(merged, f"pred_{b}", label)
        print(f"  {label:<14} {fa:>14.3f} {fb:>14.3f} {fb-fa:>+8.3f}")

    flips = merged[merged[f"pred_{a}"] != merged[f"pred_{b}"]]
    print(f"\n  {len(flips)} rows changed prediction")
    for _, r in flips.head(15).iterrows():
        truth = r["stance_truth"]
        ma = "✓" if r[f"pred_{a}"] == truth else "✗"
        mb = "✓" if r[f"pred_{b}"] == truth else "✗"
        print(f"    [{truth[:4]}] {a}={r[f'pred_{a}'][:4]} {ma}  {b}={r[f'pred_{b}'][:4]} {mb}   {str(r['message_text_english'])[:80]}")


def show_errors(name, klass=None, n=20):
    path = RUNS_DIR / f"{name}.csv"
    if not path.exists():
        sys.exit(f"No run for '{name}'.")
    df = pd.read_csv(path)
    errs = df[df["stance_truth"] != df["stance_pred"]]
    if klass:
        errs = errs[(errs["stance_truth"] == klass) | (errs["stance_pred"] == klass)]
    print(f"\n  {len(errs)} errors" + (f" involving {klass}" if klass else ""))
    for _, r in errs.head(n).iterrows():
        print(f"\n  row {r['original_row']}  truth={r['stance_truth']}  pred={r['stance_pred']}  ({r['stance_confidence']})")
        print(f"    text: {str(r['message_text_english'])[:200]}")
        print(f"    reason: {r['stance_reasoning']}")


def list_prompts():
    prompts = sorted(PROMPTS_DIR.glob("*.txt"))
    runs = {p.stem for p in RUNS_DIR.glob("*.csv")} if RUNS_DIR.exists() else set()
    for p in prompts:
        marker = "●" if p.stem in runs else "○"
        print(f"  {marker} {p.stem}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run")
    r.add_argument("name")
    r.add_argument("--model", default=DEFAULT_MODEL)
    r.add_argument("--limit", type=int)
    r.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    r.add_argument("--concurrency", type=int, default=CONCURRENCY)

    c = sub.add_parser("compare")
    c.add_argument("a")
    c.add_argument("b")

    e = sub.add_parser("errors")
    e.add_argument("name")
    e.add_argument("--class", dest="klass", choices=LABELS)
    e.add_argument("--n", type=int, default=20)

    sub.add_parser("list")

    args = ap.parse_args()
    if args.cmd == "run":
        run_prompt(args.name, model=args.model, limit=args.limit,
                   batch_size=args.batch_size, concurrency=args.concurrency)
    elif args.cmd == "compare":
        compare(args.a, args.b)
    elif args.cmd == "errors":
        show_errors(args.name, klass=args.klass, n=args.n)
    elif args.cmd == "list":
        list_prompts()


if __name__ == "__main__":
    main()
