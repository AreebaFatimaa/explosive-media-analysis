"""Parallel whisper-persian transcription v2 — fixes adapter loading and language forcing."""

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
TEMP_DIR = "transcription_chunks_v2"

VIDEO_EXT = {".mp4", ".mkv", ".mov", ".avi", ".webm"}
AUDIO_EXT = {".mp3", ".wav", ".ogg", ".m4a", ".opus"}


def load_model():
    """Load whisper-base + LoRA adapter with correct key renaming for peft 0.10."""
    device = "cpu"
    base_model = WhisperForConditionalGeneration.from_pretrained("openai/whisper-base").to(device)
    proc = AutoProcessor.from_pretrained("Paulwalker4884/whisper-persian")

    cfg = LoraConfig(
        r=16, lora_alpha=32, target_modules=["q_proj", "v_proj"],
        lora_dropout=0.1, bias="none", inference_mode=True,
    )
    mdl = get_peft_model(base_model, cfg)

    # Load adapter weights and rename keys: peft 0.10 expects '.lora_A.default.weight'
    # but the adapter file (saved with peft 0.17) has '.lora_A.weight'
    adapter_path = hf_hub_download("Paulwalker4884/whisper-persian", "adapter_model.safetensors")
    adapter_weights = load_file(adapter_path)
    renamed = {}
    for k, v in adapter_weights.items():
        new_key = k.replace(".lora_A.weight", ".lora_A.default.weight").replace(".lora_B.weight", ".lora_B.default.weight")
        renamed[new_key] = v
    result = mdl.load_state_dict(renamed, strict=False)
    if result.unexpected_keys:
        raise RuntimeError(f"Adapter keys not found in model: {result.unexpected_keys}")
    # Verify LoRA weights actually loaded (lora_B should be non-zero)
    sd = mdl.state_dict()
    sample_key = [k for k in sd if "lora_B.default.weight" in k][0]
    assert sd[sample_key].norm().item() > 0.01, "LoRA adapter weights not loaded — lora_B is near-zero"
    mdl.eval()

    # Force Persian language on the generation config (kwarg may be ignored in transformers 4.44)
    forced_ids = proc.get_decoder_prompt_ids(language="fa", task="transcribe")
    mdl.generation_config.forced_decoder_ids = forced_ids

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
        needs_cleanup = False
        try:
            # Convert ALL media to 16kHz mono wav via ffmpeg (handles video, mp3, opus, ogg, etc.)
            wav_path = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
            needs_cleanup = True
            subprocess.run(
                ["ffmpeg", "-y", "-i", path, "-ac", "1", "-ar", "16000", wav_path],
                check=True, capture_output=True
            )

            wav, sr = torchaudio.load(wav_path)
            wav = wav.mean(0)  # mono

            if wav.shape[0] == 0:
                results[idx] = "[ERROR: empty audio]"
                continue

            chunk_len = 16000 * 30  # use full 30s window (whisper native)
            pieces = []
            for j in range(0, wav.shape[0], chunk_len):
                seg = wav[j:j + chunk_len]
                feats = proc(seg.numpy(), sampling_rate=16000,
                             return_tensors="pt").input_features.to(device)
                with torch.no_grad():
                    ids = mdl.generate(
                        feats,
                        max_new_tokens=440,
                    )
                pieces.append(proc.batch_decode(ids, skip_special_tokens=True)[0])

            results[idx] = " ".join(pieces).strip() or "[ERROR: no transcription produced]"
        except Exception as e:
            results[idx] = f"[ERROR: {e}]"
        finally:
            if needs_cleanup and wav_path and os.path.exists(wav_path):
                os.unlink(wav_path)

        # save partial results after each video
        with open(f"{TEMP_DIR}/worker_{worker_id}.json", "w") as f:
            json.dump({str(k): v for k, v in results.items()}, f)

    return results


if __name__ == "__main__":
    mp.set_start_method("spawn")
    os.makedirs(TEMP_DIR, exist_ok=True)

    df = pd.read_csv(CSV_FILE)

    # Add v2 column if it doesn't exist
    if "audio_transcription_persian_v2" not in df.columns:
        # Insert right after audio_transcription_persian
        cols = list(df.columns)
        insert_pos = cols.index("audio_transcription_persian") + 1
        df.insert(insert_pos, "audio_transcription_persian_v2", pd.NA)
        df.to_csv(CSV_FILE, index=False)
        print("Added audio_transcription_persian_v2 column to CSV")

    # Find rows that need transcription
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
        existing = df.at[idx, "audio_transcription_persian_v2"]
        if isinstance(existing, str) and existing.strip() and not existing.startswith("[ERROR"):
            continue
        to_process.append((idx, filename))

    print(f"{len(to_process)} videos to transcribe with {NUM_WORKERS} workers")

    chunk_size = math.ceil(len(to_process) / NUM_WORKERS)
    chunks = [to_process[i:i + chunk_size] for i in range(0, len(to_process), chunk_size)]

    with mp.Pool(NUM_WORKERS) as pool:
        all_results = pool.map(worker_fn, [(wid, chunk) for wid, chunk in enumerate(chunks)])

    # Merge results back into CSV — force column to object dtype first
    df = pd.read_csv(CSV_FILE)
    df["audio_transcription_persian_v2"] = df["audio_transcription_persian_v2"].astype(object)
    merged = 0
    for results in all_results:
        for idx_str, text in results.items():
            idx = int(idx_str) if isinstance(idx_str, str) else idx_str
            df.at[idx, "audio_transcription_persian_v2"] = text
            merged += 1

    df.to_csv(CSV_FILE, index=False)
    print(f"\nDone. Merged {merged} transcriptions into {CSV_FILE} (audio_transcription_persian_v2).")
