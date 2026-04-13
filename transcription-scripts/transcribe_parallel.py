"""Parallel whisper-persian transcription for all videos in the CSV."""

import multiprocessing as mp
import json, math, os, subprocess, tempfile
import torch, torchaudio
import pandas as pd
from transformers import WhisperForConditionalGeneration, AutoProcessor
from peft import LoraConfig, get_peft_model
from safetensors.torch import load_file
from huggingface_hub import hf_hub_download

MEDIA_DIR = "scraped-media"
CSV_FILE = "explosive_media_messages.csv"
NUM_WORKERS = 6
TEMP_DIR = "transcription_chunks"

VIDEO_EXT = {".mp4", ".mkv", ".mov", ".avi", ".webm"}
AUDIO_EXT = {".mp3", ".wav", ".ogg", ".m4a", ".opus"}


def load_model():
    device = "cpu"
    base_model = WhisperForConditionalGeneration.from_pretrained("openai/whisper-base").to(device)
    proc = AutoProcessor.from_pretrained("Paulwalker4884/whisper-persian")
    lora_config = LoraConfig(
        r=16, lora_alpha=32, target_modules=["q_proj", "v_proj"],
        lora_dropout=0.1, bias="none", inference_mode=True,
    )
    mdl = get_peft_model(base_model, lora_config)
    adapter_path = hf_hub_download("Paulwalker4884/whisper-persian", "adapter_model.safetensors")
    adapter_weights = load_file(adapter_path)
    mdl.load_state_dict(adapter_weights, strict=False)
    mdl.eval()
    return mdl, proc


def worker_fn(args):
    worker_id, items = args
    mdl, proc = load_model()
    device = "cpu"

    results = {}
    for i, (idx, filename) in enumerate(items):
        path = os.path.join(MEDIA_DIR, filename)
        print(f"  [Worker {worker_id}] [{i+1}/{len(items)}] {filename}", flush=True)

        if not os.path.exists(path):
            results[idx] = f"[ERROR: file not found: {path}]"
            continue

        wav_path = None
        try:
            ext = os.path.splitext(filename.lower())[1]
            is_video = ext in VIDEO_EXT

            if is_video:
                wav_path = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
                subprocess.run(
                    ["ffmpeg", "-y", "-i", path, "-ac", "1", "-ar", "16000", wav_path],
                    check=True, capture_output=True
                )
            else:
                wav_path = path

            wav, sr = torchaudio.load(wav_path)
            if sr != 16000:
                wav = torchaudio.transforms.Resample(sr, 16000)(wav)
            wav = wav.mean(0)

            chunk_len = 16000 * 28
            pieces = []
            for j in range(0, wav.shape[0], chunk_len):
                seg = wav[j:j + chunk_len]
                feats = proc(seg.numpy(), sampling_rate=16000,
                             return_tensors="pt").input_features.to(device)
                with torch.no_grad():
                    ids = mdl.generate(feats, max_new_tokens=440)
                pieces.append(proc.batch_decode(ids, skip_special_tokens=True)[0])

            results[idx] = " ".join(pieces).strip()
        except Exception as e:
            results[idx] = f"[ERROR: {e}]"
        finally:
            if wav_path and wav_path != path and os.path.exists(wav_path):
                os.unlink(wav_path)

        # save partial results after each video
        with open(f"{TEMP_DIR}/worker_{worker_id}.json", "w") as f:
            json.dump({str(k): v for k, v in results.items()}, f)

    return results


if __name__ == "__main__":
    os.makedirs(TEMP_DIR, exist_ok=True)

    df = pd.read_csv(CSV_FILE)
    to_process = []
    for idx in df.index:
        if df.at[idx, "has_media"] != "Y":
            continue
        filename = df.at[idx, "media_filename"]
        if not isinstance(filename, str) or not filename.strip():
            continue
        ext = os.path.splitext(filename.lower())[1]
        if ext not in VIDEO_EXT and ext not in AUDIO_EXT:
            continue
        existing = df.at[idx, "audio_transcription_persian"]
        if isinstance(existing, str) and existing.strip() and not existing.startswith("[ERROR"):
            continue
        to_process.append((idx, filename))

    print(f"{len(to_process)} videos to transcribe with {NUM_WORKERS} workers")

    chunk_size = math.ceil(len(to_process) / NUM_WORKERS)
    chunks = [to_process[i:i + chunk_size] for i in range(0, len(to_process), chunk_size)]

    with mp.Pool(NUM_WORKERS) as pool:
        all_results = pool.map(worker_fn, [(wid, chunk) for wid, chunk in enumerate(chunks)])

    # merge results back into CSV
    df = pd.read_csv(CSV_FILE)
    merged = 0
    for results in all_results:
        for idx_str, text in results.items():
            idx = int(idx_str) if isinstance(idx_str, str) else idx_str
            df.at[idx, "audio_transcription_persian"] = text
            merged += 1

    df.to_csv(CSV_FILE, index=False)
    print(f"\nDone. Merged {merged} transcriptions into {CSV_FILE}.")
