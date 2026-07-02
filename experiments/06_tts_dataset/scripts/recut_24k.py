#!/usr/bin/env python3
"""Re-cut the CLEANED crh Sevil dataset at 24 kHz for StyleTTS2.

No re-alignment: segments.jsonl already holds the final cut bounds (start/end).
We take only the ids in the cleaned+fixed metadata.lat.csv (post-audit, 1371),
load each book's 44.1 kHz source, downsample to 24 kHz, cut [start:end], peak-
normalise to 0.95, and write PCM_16. This recovers the full <=12 kHz band that
the 22.05 kHz build (then upsampled by StyleTTS2's loader) threw away.

Output: <out>/wavs/<id>.wav + <out>/metadata.csv (LJSpeech id|text|text, Latin).

Usage: recut_24k.py <books_dir> <exp06_dataset_dir> <out_dir>
"""
import csv
import json
import sys
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf
from unidecode import unidecode

SR_OUT = 24000
PEAK = 0.95
AUDIO_EXT = (".wav", ".mp3", ".m4a", ".flac")


def slugify(name):
    s = unidecode(name).lower()
    return "".join(c if c.isalnum() else "_" for c in s).strip("_")


def pick_audio(folder):
    cands = [p for p in folder.iterdir() if p.suffix.lower() in AUDIO_EXT]
    return max(cands, key=lambda p: p.stat().st_size) if cands else None


def main():
    books_dir, ds_dir, out_dir = map(Path, sys.argv[1:4])
    out_wavs = out_dir / "wavs"
    out_wavs.mkdir(parents=True, exist_ok=True)

    # slug -> source audio path
    book_audio = {}
    for folder in sorted(p for p in books_dir.iterdir() if p.is_dir()):
        a = pick_audio(folder)
        if a:
            book_audio[slugify(folder.name)] = a
    print(f"[recut] {len(book_audio)} source books discovered", flush=True)

    # id -> (book, start, end) from segments.jsonl
    seg = {}
    for line in (ds_dir / "segments.jsonl").read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        seg[r["id"]] = (r["book"], r["start"], r["end"])

    # cleaned/fixed ids + text from metadata.lat.csv
    rows = []
    with (ds_dir / "metadata.lat.csv").open(encoding="utf-8") as f:
        for parts in csv.reader(f, delimiter="|"):
            if len(parts) < 2:
                continue
            rows.append((parts[0], parts[1]))
    print(f"[recut] {len(rows)} cleaned clips to cut", flush=True)

    audio_cache = {}
    meta_out = []
    missing, done = 0, 0
    for cid, text in rows:
        if cid not in seg:
            missing += 1
            continue
        book, start, end = seg[cid]
        if book not in book_audio:
            missing += 1
            continue
        if book not in audio_cache:
            audio_cache[book] = librosa.load(str(book_audio[book]), sr=SR_OUT, mono=True)[0].astype(np.float32)
            print(f"[recut] loaded {book} @24k ({len(audio_cache[book])/SR_OUT:.0f}s)", flush=True)
        hi = audio_cache[book]
        clip = hi[int(start * SR_OUT):int(end * SR_OUT)]
        if clip.size == 0:
            missing += 1
            continue
        peak = float(np.max(np.abs(clip)))
        if peak > 0:
            clip = clip * (PEAK / peak)
        sf.write(str(out_wavs / f"{cid}.wav"), clip, SR_OUT, subtype="PCM_16")
        meta_out.append(f"{cid}|{text}|{text}")
        done += 1

    (out_dir / "metadata.csv").write_text("\n".join(meta_out) + "\n", encoding="utf-8")
    print(f"[recut] wrote {done} wavs @ {SR_OUT} Hz -> {out_wavs}  (missing {missing})", flush=True)


if __name__ == "__main__":
    main()
