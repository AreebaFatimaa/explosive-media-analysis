"""Re-transcribe repetitive hallucinations with 4 parallel workers + VAD filter.
VAD skips silent/non-speech sections, dramatically speeding up music/noise files."""

import os
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

import multiprocessing as mp
import json, math, time
import pandas as pd

CSV_FILE = "explosive_media_messages.csv"
MEDIA_DIR = "scraped-media"
PROGRESS_DIR = "retranscribe_chunks_v3"
NUM_WORKERS = 4
NO_SPEECH_THRESHOLD = 0.7
MIN_SPEECH_RATIO = 0.3


def is_repetitive(text):
    if not isinstance(text, str) or not text.strip():
        return False
    words = text.split()
    if len(words) > 10:
        return len(set(words)) / len(words) < 0.3
    return False


def worker_fn(args):
    worker_id, items = args
    os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
    from faster_whisper import WhisperModel

    print(f"[Worker {worker_id}] Loading medium model...", flush=True)
    model = WhisperModel("medium", device="cpu", compute_type="int8")
    print(f"[Worker {worker_id}] Model loaded, processing {len(items)} files", flush=True)

    results = {}
    for i, (idx, filename) in enumerate(items):
        path = os.path.join(MEDIA_DIR, filename)
        print(f"[W{worker_id}] [{i+1}/{len(items)}] {filename}", flush=True)

        if not os.path.exists(path):
            results[str(idx)] = "[ERROR: file not found]"
            continue

        try:
            # VAD filter skips silent sections - dramatic speedup for music/noise files
            segments, info = model.transcribe(
                path,
                language="fa",
                beam_size=3,
                vad_filter=True,
                vad_parameters=dict(min_silence_duration_ms=500),
            )

            segs = []
            for seg in segments:
                segs.append({"text": seg.text.strip(), "no_speech": seg.no_speech_prob})

            if not segs:
                results[str(idx)] = "[NEEDS MANUAL REVIEW: no speech detected by VAD]"
                continue

            speech_segs = [s for s in segs if s["no_speech"] < NO_SPEECH_THRESHOLD]
            speech_ratio = len(speech_segs) / len(segs)

            if speech_ratio < MIN_SPEECH_RATIO:
                results[str(idx)] = "[NEEDS MANUAL REVIEW: mostly non-speech audio]"
            else:
                text = " ".join(s["text"] for s in speech_segs if s["text"]).strip()
                if not text:
                    results[str(idx)] = "[NEEDS MANUAL REVIEW: speech detected but no text]"
                elif is_repetitive(text):
                    results[str(idx)] = "[NEEDS MANUAL REVIEW: still repetitive with medium model]"
                else:
                    results[str(idx)] = text

        except Exception as e:
            results[str(idx)] = f"[ERROR: {e}]"

        # Save progress every file (in case of interrupt)
        with open(f"{PROGRESS_DIR}/worker_{worker_id}.json", "w") as f:
            json.dump(results, f)

    return results


if __name__ == "__main__":
    mp.set_start_method("spawn")
    os.makedirs(PROGRESS_DIR, exist_ok=True)

    # Load existing progress from both old single-worker and previous runs
    existing = {}
    old_progress = "retranscribe_progress.json"
    if os.path.exists(old_progress):
        existing = json.load(open(old_progress))
        print(f"Loaded {len(existing)} from old single-worker progress")

    for f in os.listdir(PROGRESS_DIR):
        if f.endswith(".json"):
            existing.update(json.load(open(os.path.join(PROGRESS_DIR, f))))
    print(f"Total already done: {len(existing)}")

    # Find repetitive rows still needing transcription
    df = pd.read_csv(CSV_FILE)
    to_process = []
    for idx in df.index:
        v2 = str(df.at[idx, "audio_transcription_persian_v2"]).strip()
        if is_repetitive(v2) and str(idx) not in existing:
            filename = str(df.at[idx, "media_filename"]).strip()
            if filename and filename != "nan":
                to_process.append((idx, filename))

    print(f"{len(to_process)} files to process with {NUM_WORKERS} workers + VAD")

    if not to_process:
        print("Nothing to do. Merging existing progress...")
    else:
        # Split into chunks
        chunk_size = math.ceil(len(to_process) / NUM_WORKERS)
        chunks = [to_process[i:i + chunk_size] for i in range(0, len(to_process), chunk_size)]

        t0 = time.time()
        with mp.Pool(NUM_WORKERS) as pool:
            all_results = pool.map(worker_fn, [(wid, chunk) for wid, chunk in enumerate(chunks)])

        # Merge worker results into existing
        for results in all_results:
            existing.update(results)

        elapsed = (time.time() - t0) / 60
        print(f"\nDone in {elapsed:.1f} min")

    # Save combined progress
    with open(old_progress, "w") as f:
        json.dump(existing, f)

    # Merge into CSV
    df = pd.read_csv(CSV_FILE)
    df["audio_transcription_persian_v2"] = df["audio_transcription_persian_v2"].astype(object)
    merged = 0
    for idx_str, text in existing.items():
        idx = int(idx_str)
        df.at[idx, "audio_transcription_persian_v2"] = text
        merged += 1

    df.to_csv(CSV_FILE, index=False)
    print(f"Merged {merged} transcriptions into CSV.")
