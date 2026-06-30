#!/usr/bin/env python3
"""Build a 16 kHz audiofolder dataset for MMS-TTS (VITS) fine-tuning.

Reads the Cyrillic LJSpeech metadata produced by experiment 06 and writes an
HF `audiofolder` layout with train/ and test/ splits:

    <out>/train/<id>.wav + <out>/train/metadata.csv   (file_name,transcription)
    <out>/test/<id>.wav  + <out>/test/metadata.csv

mms-tts-crh is 16 kHz and consumes Cyrillic text (its tokenizer lowercases and
strips punctuation itself), so we resample to 16 kHz and pass text verbatim.

Usage:
    build_vits_dataset.py <ds06_dir> <out_dir> [--eval N] [--variant cyr|lat]
"""
import argparse
import csv
import shutil
from pathlib import Path

import librosa
import soundfile as sf

SR = 16000


def read_meta(path):
    rows = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        cid, text, _ = line.split("|", 2)
        rows.append((cid, text))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ds06_dir")
    ap.add_argument("out_dir")
    ap.add_argument("--eval", type=int, default=40, dest="n_eval")
    ap.add_argument("--variant", choices=["cyr", "lat"], default="cyr")
    a = ap.parse_args()

    ds06 = Path(a.ds06_dir)
    out = Path(a.out_dir)
    rows = read_meta(ds06 / f"dataset/metadata.{a.variant}.csv")
    rows.sort(key=lambda r: r[0])

    # Deterministic eval split: every k-th clip, spread across all books.
    k = max(1, len(rows) // a.n_eval)
    eval_ids = {rows[i][0] for i in range(0, len(rows), k)}
    eval_ids = set(list(eval_ids)[: a.n_eval])

    if out.exists():
        shutil.rmtree(out)
    counts = {"train": 0, "test": 0}
    writers = {}
    files = {}
    for split in ("train", "test"):
        (out / split).mkdir(parents=True)
        files[split] = open(out / split / "metadata.csv", "w", newline="", encoding="utf-8")
        writers[split] = csv.writer(files[split])
        writers[split].writerow(["file_name", "transcription"])

    for cid, text in rows:
        split = "test" if cid in eval_ids else "train"
        wav = ds06 / "dataset" / "wavs" / f"{cid}.wav"
        if not wav.exists():
            continue
        y = librosa.load(wav, sr=SR, mono=True)[0]
        sf.write(out / split / f"{cid}.wav", y, SR, subtype="PCM_16")
        writers[split].writerow([f"{cid}.wav", text])
        counts[split] += 1

    for f in files.values():
        f.close()
    print(f"wrote {counts['train']} train + {counts['test']} test clips "
          f"({a.variant}, {SR} Hz) -> {out}")


if __name__ == "__main__":
    main()
