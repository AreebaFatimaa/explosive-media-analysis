"""Re-transcribe repetitive hallucinations from Feb 27 onwards only.
Aggressively skips music/noise via VAD and no_speech threshold."""

import os
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

import multiprocessing as mp
import json, math, time
import pandas as pd

CSV_FILE = "explosive_media_messages.csv"
MEDIA_DIR = "scraped-media"
PROGRESS_DIR = "retranscribe_feb27_chunks"
NUM_WORKERS = 4
CUTOFF_DATE = "2026-02-27"

# AGGRESSIVE thresholds - skip music/noise quickly
NO_SPEECH_THRESHOLD = 0.5   # lowered from 0.7 - more strict about "speech"
MIN_SPEECH_RATIO = 0.5      # raised from 0.3 - require 50% speech segments


def is_repetitive(text):
    if not isinstance(text, str) or not text.strip():
        return False
    words = text.split()
    if len(words) > 10:
        return len(set(words)) / len(words) < 0.3
    return False


_MODEL = None
_WORKER_ID = None

def _init_worker():
    """Each worker loads model once on init."""
    global _MODEL, _WORKER_ID
    os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
    from faster_whisper import WhisperModel
    _WORKER_ID = os.getpid() % 100
    print(f"[W{_WORKER_ID}] Loading model...", flush=True)
    _MODEL = WhisperModel("medium", device="cpu", compute_type="int8", cpu_threads=2)
    print(f"[W{_WORKER_ID}] Ready", flush=True)


def process_one(item):
    """Process a single file. Returns (idx, result_text)."""
    global _MODEL, _WORKER_ID
    model = _MODEL

    idx, filename = item
    path = os.path.join(MEDIA_DIR, filename)
    print(f"[W{_WORKER_ID}] {filename}", flush=True)

    if not os.path.exists(path):
        return (idx, "[ERROR: file not found]")

    try:
        segments, info = model.transcribe(
            path,
            language="fa",
            beam_size=1,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=300, threshold=0.5),
            condition_on_previous_text=False,
            no_speech_threshold=0.5,
        )

        segs = list(segments)
        if not segs:
            return (idx, "[no speech detected]")

        speech_segs = [s for s in segs if s.no_speech_prob < NO_SPEECH_THRESHOLD]
        speech_ratio = len(speech_segs) / len(segs)

        if speech_ratio < MIN_SPEECH_RATIO:
            return (idx, "[music or noise - no clear speech]")

        text = " ".join(s.text.strip() for s in speech_segs if s.text.strip()).strip()
        if not text:
            return (idx, "[no clear speech]")
        elif is_repetitive(text):
            return (idx, "[repetitive - likely music with occasional vocals]")
        else:
            return (idx, text)

    except Exception as e:
        return (idx, f"[ERROR: {e}]")


if __name__ == "__main__":
    mp.set_start_method("spawn")
    os.makedirs(PROGRESS_DIR, exist_ok=True)

    # Load existing progress
    existing = {}
    for f in os.listdir(PROGRESS_DIR):
        if f.endswith(".json"):
            existing.update(json.load(open(os.path.join(PROGRESS_DIR, f))))
    print(f"Already done: {len(existing)}")

    # Find repetitive Feb 27+ rows
    df = pd.read_csv(CSV_FILE)
    to_process = []
    for idx in df.index:
        v2 = str(df.at[idx, "audio_transcription_persian_v2"]).strip()
        date = str(df.at[idx, "date"]).strip()
        if (is_repetitive(v2)
                and date >= CUTOFF_DATE
                and str(idx) not in existing):
            filename = str(df.at[idx, "media_filename"]).strip()
            if filename and filename != "nan":
                to_process.append((idx, filename))

    print(f"{len(to_process)} files from {CUTOFF_DATE} onwards to process")

    if not to_process:
        print("Nothing to do.")
    else:
        t0 = time.time()
        done = 0
        with mp.Pool(NUM_WORKERS, initializer=_init_worker) as pool:
            # imap_unordered: workers pull files one at a time, no one idles
            for idx, text in pool.imap_unordered(process_one, to_process):
                existing[str(idx)] = text
                done += 1
                # Save after every result
                with open(f"{PROGRESS_DIR}/main_progress.json", "w") as f:
                    json.dump(existing, f)
                print(f"  [{done}/{len(to_process)}] done", flush=True)

        print(f"Completed in {(time.time()-t0)/60:.1f} min")

    # Merge into CSV
    df = pd.read_csv(CSV_FILE)
    df["audio_transcription_persian_v2"] = df["audio_transcription_persian_v2"].astype(object)
    merged = 0
    for idx_str, text in existing.items():
        idx = int(idx_str)
        df.at[idx, "audio_transcription_persian_v2"] = text
        merged += 1
    df.to_csv(CSV_FILE, index=False)
    print(f"Merged {merged} into CSV")
