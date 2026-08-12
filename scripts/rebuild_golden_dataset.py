"""Rebuild golden_dataset.csv to a clean 339 rows with no empty messages.

Why this exists
---------------
The golden set as originally built (notebook3, cells 3-4) ended up at 336 rows,
not the 339 the sample-size calculator called for: the 3 "extra" rows were
appended to a file in the notebooks/ directory instead of the real golden CSV.
Four of the 336 rows are also empty messages — no Persian text, no English
text, no media — which cannot be hand-coded and must not sit in a ground-truth
set as permanently blank labels.

What this does
--------------
1. Keeps the 332 non-empty rows of the current golden set VERBATIM, so every
   hand-coded label, corrected transcription and OCR edit is preserved.
2. Drops the 4 empty rows (original_row 1213, 1720, 1846, 2429).
3. Adds 7 replacement rows drawn from the non-empty sampling frame, taking the
   339 total:
     - 469, 932, 2148  — the 3 intended extras (random_state=43, as notebook3)
     - 843, 1039, 1212, 1676 — 4 further rows (random_state=44) standing in for
       the dropped empties
4. Leaves the 7 new rows' label columns blank so they enter the hand-coding
   queue rather than inheriting any machine-generated value.

Sampling note for the methodology writeup: empty messages are excluded from the
sampling frame, not merely dropped after sampling. An empty row carries no
content to classify, so it is out of scope for the classifier and therefore out
of scope for its ground truth. The frame is the 2,794 non-empty rows of the
2,840-row corpus.

Run:  .venv/bin/python explosive-media-analysis/scripts/rebuild_golden_dataset.py
Idempotent — safe to re-run. Backs up the previous CSV first.
"""

import shutil
from pathlib import Path

import pandas as pd

BASE = Path(__file__).resolve().parents[2]
MAIN_CSV = BASE / "explosive-media-analysis" / "CSVs" / "explosive_media_messages.csv"
GOLDEN_CSV = BASE / "explosive-media-analysis" / "CSVs" / "golden_dataset.csv"

TARGET_ROWS = 339
LABEL_COLS = ("keywords", "theme", "include_person", "AI_generated",
              "theme2", "theme3", "theme4")


def is_blank(series: pd.Series) -> pd.Series:
    """True where a cell is NaN, empty, or the literal string 'nan'."""
    return series.isna() | series.astype(str).str.strip().isin(["", "nan"])


def empty_message_mask(df: pd.DataFrame) -> pd.Series:
    """Rows with no Persian text, no English text and no media — nothing to code."""
    return (is_blank(df["message_text_persian"])
            & is_blank(df["message_text_english"])
            & is_blank(df["media_filename"]))


def main():
    main_df = pd.read_csv(MAIN_CSV, encoding="utf-8-sig")
    golden = pd.read_csv(GOLDEN_CSV, encoding="utf-8-sig")
    golden_cols = list(golden.columns)

    # Sanity check: the original draw must still be reproducible, otherwise the
    # main CSV has been reordered and original_row no longer means anything.
    reproduced = set(main_df.sample(n=336, random_state=42).index)
    if reproduced != set(golden["original_row"]):
        raise SystemExit(
            "Refusing to rebuild: sample(n=336, random_state=42) no longer "
            "reproduces the golden set. The main CSV's row order has changed, "
            "so original_row cannot be trusted as a join key."
        )

    # 1-2. Keep every non-empty existing row exactly as it is.
    dropped = golden[empty_message_mask(golden)]
    keep = golden[~empty_message_mask(golden)].copy()

    # 3. Draw the replacements, reproducing notebook3's random_state=43 extras.
    original_idx = main_df.sample(n=336, random_state=42).index
    extras_3 = main_df.drop(original_idx).sample(n=3, random_state=43)

    non_empty = ~empty_message_mask(main_df)
    frame = main_df.index.difference(original_idx).difference(extras_3.index)
    frame = [i for i in frame if non_empty[i]]

    needed = TARGET_ROWS - len(keep) - len(extras_3)
    if needed < 0:
        raise SystemExit(f"Already at or above {TARGET_ROWS} rows; nothing to add.")
    replacements = main_df.loc[frame].sample(n=needed, random_state=44)

    new_rows = pd.concat([extras_3, replacements])
    new_rows = new_rows.reset_index().rename(columns={"index": "original_row"})

    # 4. Blank the label columns so these rows enter the hand-coding queue.
    for col in golden_cols:
        if col not in new_rows.columns:
            new_rows[col] = ""
    for col in LABEL_COLS:
        new_rows[col] = ""
    new_rows = new_rows[golden_cols]

    out = pd.concat([keep, new_rows], ignore_index=True)

    if len(out) != TARGET_ROWS:
        raise SystemExit(f"Expected {TARGET_ROWS} rows, produced {len(out)}.")
    if empty_message_mask(out).any():
        raise SystemExit("Rebuild produced empty rows; aborting.")
    if out["original_row"].duplicated().any():
        raise SystemExit("Rebuild produced duplicate original_row values; aborting.")

    shutil.copy2(GOLDEN_CSV, GOLDEN_CSV.with_suffix(".csv.bak"))
    out.to_csv(GOLDEN_CSV, index=False, encoding="utf-8-sig")

    unlabelled = out[is_blank(out["theme"])]
    print(f"Backed up previous golden set to {GOLDEN_CSV.name}.bak")
    print(f"Dropped {len(dropped)} empty rows: {sorted(dropped['original_row'])}")
    print(f"Added {len(new_rows)} rows: {sorted(new_rows['original_row'])}")
    print(f"Golden dataset is now {len(out)} rows, 0 empty.")
    print(f"{len(unlabelled)} rows need hand-coding: {sorted(unlabelled['original_row'])}")


if __name__ == "__main__":
    main()
