#!/usr/bin/env python3
"""Merge the old HF dataset (servinosmanov/tts-crh-sevil-fixed) with the new
experiment-06 Sevil corpus into one unified LJSpeech dir for from-scratch XTTS.

Both are the same speaker (Sevil, female, crh) and share the same Latin
convention (ç ğ ı ñ ö ş ü â), so the text merges cleanly. We only need to
unify the audio: the old set is 16 kHz, the new is 22.05 kHz. We resample the
old up to 22.05 kHz (high-quality soxr) and peak-normalize both to a common
level so the merged corpus is acoustically uniform.

Old rows come from parquet (audio bytes + transcription). New rows come from
metadata.lat.csv + wavs/. We dedup by normalized text and write a single
metadata.lat.csv (text|text). The old set has no Cyrillic, so the merged set is
Latin-only (XTTS trains on Latin + the `tr` token anyway).

Usage:
    build_merged_dataset.py <old_parquet_dir> <new_dataset_dir> <out_dir>
      old_parquet_dir : has train/validation/test.parquet
      new_dataset_dir : exp-06 dataset (metadata.lat.csv + wavs/)
      out_dir         : merged LJSpeech (wavs/ + metadata.lat.csv + MERGE_REPORT.md)
"""
import io
import re
import sys
import unicodedata
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq
import soundfile as sf
import soxr

SR_OUT = 22050
PEAK = 0.95


def norm_key(text: str) -> str:
    """Normalize text for dedup: lowercase, strip punctuation/whitespace."""
    t = unicodedata.normalize("NFC", text).lower()
    t = re.sub(r"[^0-9a-zçğıñöşüâ]+", "", t)
    return t


def peak_normalize(wav: np.ndarray) -> np.ndarray:
    m = np.max(np.abs(wav))
    return wav * (PEAK / m) if m > 0 else wav


def csv_escape(text: str) -> str:
    """LJSpeech uses `|` as the separator; quote fields that contain it."""
    if '"' in text:
        text = text.replace('"', '""')
    if "|" in text or '"' in text or "\n" in text:
        return f'"{text}"'
    return text


def read_lat_metadata(path: Path):
    """Yield (id, text) from a LJSpeech metadata.csv with optional quoting."""
    import csv
    with open(path, encoding="utf-8") as f:
        for row in csv.reader(f, delimiter="|", quotechar='"'):
            if len(row) >= 2 and row[0].strip():
                yield row[0].strip(), row[1].strip()


def main():
    old_dir, new_dir, out_dir = map(Path, sys.argv[1:4])
    wav_out = out_dir / "wavs"
    wav_out.mkdir(parents=True, exist_ok=True)

    seen: dict[str, str] = {}        # norm_key -> source id (first wins)
    rows: list[tuple[str, str]] = []  # (id, text)
    dur_new = dur_old = 0.0
    dups = 0

    # --- new set first (it's the cleaner, higher-quality 22.05 kHz source) ---
    new_wavs = new_dir / "wavs"
    for sid, text in read_lat_metadata(new_dir / "metadata.lat.csv"):
        src = new_wavs / f"{sid}.wav"
        if not src.exists():
            print(f"  [new] missing wav, skip: {sid}", flush=True)
            continue
        k = norm_key(text)
        if k and k in seen:
            dups += 1
            continue
        seen[k] = sid
        wav, sr = sf.read(src)
        if wav.ndim > 1:
            wav = wav.mean(axis=1)
        if sr != SR_OUT:
            wav = soxr.resample(wav, sr, SR_OUT)
        sf.write(wav_out / f"{sid}.wav", peak_normalize(wav).astype(np.float32), SR_OUT)
        dur_new += len(wav) / SR_OUT
        rows.append((sid, text))
    n_new = len(rows)
    print(f"[new] kept {n_new} clips, {dur_new/3600:.2f} h", flush=True)

    # --- old HF set: parquet audio bytes (16 kHz) -> resample 22.05 kHz ---
    for split in ["train", "validation", "test"]:
        pqf = old_dir / f"{split}.parquet"
        if not pqf.exists():
            continue
        df = pq.read_table(pqf).to_pandas()
        for _, r in df.iterrows():
            text = str(r["transcription"]).strip()
            k = norm_key(text)
            if k and k in seen:
                dups += 1
                continue
            seen[k] = "old"
            stem = Path(r["audio"]["path"]).stem        # e.g. sevil_1366
            sid = f"hf_{stem}"
            wav, sr = sf.read(io.BytesIO(r["audio"]["bytes"]))
            if wav.ndim > 1:
                wav = wav.mean(axis=1)
            if sr != SR_OUT:
                wav = soxr.resample(wav, sr, SR_OUT)
            sf.write(wav_out / f"{sid}.wav", peak_normalize(wav).astype(np.float32), SR_OUT)
            dur_old += len(wav) / SR_OUT
            rows.append((sid, text))
    n_old = len(rows) - n_new
    print(f"[old] kept {n_old} clips, {dur_old/3600:.2f} h", flush=True)

    # --- write merged metadata.lat.csv (LJSpeech: id|text|text) ---
    meta = out_dir / "metadata.lat.csv"
    with open(meta, "w", encoding="utf-8") as f:
        for sid, text in rows:
            t = csv_escape(text)
            f.write(f"{sid}|{t}|{t}\n")

    report = out_dir / "MERGE_REPORT.md"
    report.write_text(
        f"# Merged dataset (new exp-06 + old HF fixed)\n\n"
        f"- new clips: {n_new}  ({dur_new/3600:.2f} h)\n"
        f"- old clips: {n_old}  ({dur_old/3600:.2f} h)\n"
        f"- **total: {len(rows)} clips, {(dur_new+dur_old)/3600:.2f} h**\n"
        f"- duplicates dropped (by normalized text): {dups}\n"
        f"- sample rate: {SR_OUT} Hz mono, peak-normalized to {PEAK}\n"
        f"- text: Latin only (old set has no Cyrillic)\n",
        encoding="utf-8")
    print(f"[done] {len(rows)} clips, {(dur_new+dur_old)/3600:.2f} h, "
          f"{dups} dups dropped -> {meta}", flush=True)


if __name__ == "__main__":
    main()
