"""Re-transcribe repetitive hallucinations using faster-whisper medium model.
Marks non-speech audio (music, chanting, ambient noise) as [NEEDS MANUAL REVIEW]
so the user can handle them via the dashboard."""

import os
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

import json, time
import pandas as pd
from faster_whisper import WhisperModel

CSV_FILE = "explosive_media_messages.csv"
MEDIA_DIR = "scraped-media"
PROGRESS_FILE = "retranscribe_progress.json"

# Thresholds
NO_SPEECH_THRESHOLD = 0.7  # segments above this are likely not speech
MIN_SPEECH_RATIO = 0.3     # if less than 30% of segments are speech, mark for review


def is_repetitive(text):
    if not isinstance(text, str) or not text.strip():
        return False
    words = text.split()
    if len(words) > 10:
        return len(set(words)) / len(words) < 0.3
    return False


# Load progress from previous run (if interrupted)
progress = {}
if os.path.exists(PROGRESS_FILE):
    progress = json.load(open(PROGRESS_FILE))
    print(f"Resuming: {len(progress)} already done from previous run")

# Load CSV and find repetitive rows
df = pd.read_csv(CSV_FILE)
df["audio_transcription_persian_v2"] = df["audio_transcription_persian_v2"].astype(object)

to_process = []
for idx in df.index:
    v2 = str(df.at[idx, "audio_transcription_persian_v2"]).strip()
    if is_repetitive(v2) and str(idx) not in progress:
        filename = str(df.at[idx, "media_filename"]).strip()
        if filename and filename != "nan":
            to_process.append((idx, filename))

print(f"{len(to_process)} repetitive hallucinations to re-transcribe")

# Load model once
print("Loading faster-whisper medium model (int8)...")
t0 = time.time()
model = WhisperModel("medium", device="cpu", compute_type="int8")
print(f"Model loaded in {time.time()-t0:.1f}s")

# Process each file
done = 0
manual_review = 0
for i, (idx, filename) in enumerate(to_process):
    path = os.path.join(MEDIA_DIR, filename)
    print(f"[{i+1}/{len(to_process)}] {filename}", end="", flush=True)

    if not os.path.exists(path):
        progress[str(idx)] = "[ERROR: file not found]"
        print(" — file not found")
        continue

    try:
        segments_list = []
        segments, info = model.transcribe(path, language="fa", beam_size=3)
        for seg in segments:
            segments_list.append({
                "text": seg.text.strip(),
                "no_speech": seg.no_speech_prob,
            })

        if not segments_list:
            progress[str(idx)] = "[NEEDS MANUAL REVIEW: no audio segments detected]"
            manual_review += 1
            print(" — no segments, needs review")
            continue

        # Separate speech from non-speech
        speech_segs = [s for s in segments_list if s["no_speech"] < NO_SPEECH_THRESHOLD]
        total_segs = len(segments_list)
        speech_ratio = len(speech_segs) / total_segs

        if speech_ratio < MIN_SPEECH_RATIO:
            # Mostly music/noise/chanting — flag for manual review
            progress[str(idx)] = "[NEEDS MANUAL REVIEW: mostly non-speech audio]"
            manual_review += 1
            print(f" — {speech_ratio:.0%} speech, needs review")
        else:
            # Has real speech — join only the speech segments
            text = " ".join(s["text"] for s in speech_segs if s["text"]).strip()
            if not text:
                progress[str(idx)] = "[NEEDS MANUAL REVIEW: speech detected but no text produced]"
                manual_review += 1
                print(" — empty text, needs review")
            elif is_repetitive(text):
                # Still repetitive even with medium model — flag for review
                progress[str(idx)] = "[NEEDS MANUAL REVIEW: still repetitive with medium model]"
                manual_review += 1
                print(" — still repetitive, needs review")
            else:
                progress[str(idx)] = text
                done += 1
                print(f" — OK ({len(text)} chars, {speech_ratio:.0%} speech)")

    except Exception as e:
        progress[str(idx)] = f"[ERROR: {e}]"
        print(f" — ERROR: {e}")

    # Save progress every 10 files
    if (i + 1) % 10 == 0:
        with open(PROGRESS_FILE, "w") as f:
            json.dump(progress, f)
        print(f"  [progress saved: {done} transcribed, {manual_review} needs review]")

# Save final progress
with open(PROGRESS_FILE, "w") as f:
    json.dump(progress, f)

# Merge into CSV
df = pd.read_csv(CSV_FILE)
df["audio_transcription_persian_v2"] = df["audio_transcription_persian_v2"].astype(object)
merged = 0
for idx_str, text in progress.items():
    idx = int(idx_str)
    df.at[idx, "audio_transcription_persian_v2"] = text
    merged += 1

df.to_csv(CSV_FILE, index=False)
print(f"\nDone. Transcribed {done}, flagged {manual_review} for manual review, merged {merged} into CSV.")
