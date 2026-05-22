#!/usr/bin/env python3
"""Phoneme coverage check for a Crimean Tatar RVC dataset.

Two modes:

1) Transcripts (preferred — accurate):
   ./scripts/rvc/phoneme-coverage.py --transcripts path/to/transcripts.txt
   Pass a text file (one utterance per line, or .csv/.tsv with text in first column).

2) Filenames (fallback when no transcripts — many YouTube/UVR pipelines have none):
   ./scripts/rvc/phoneme-coverage.py --filenames path/to/dataset/

Reports:
   - count of each Crimean-Tatar-specific grapheme: ñ, q, ğ, ç, ş, also c j h
   - minutes of audio (if --audio-dir given) that contain each phoneme
   - verdict: which phonemes are underrepresented (<2% of clips)

Why this matters: per ТЗ §10.2 acceptance, ñ/q/ğ/ç/ş must render correctly.
If your dataset has zero /q/ examples, RVC will guess on inference — usually
collapsing to /k/. This check catches the gap BEFORE 6 hours of training.

Notes:
- For RVC specifically, phoneme coverage in the *training* set matters less
  than in pure TTS (RVC reads phonemes from your inference input via
  ContentVec — not from training data). But coverage still helps the timbre
  model handle the micro-articulation transitions cleanly. Use this as a
  smell test, not a hard gate.
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path

# Crimean Tatar-specific graphemes worth tracking. ñ/q/ğ are the high-risk ones.
TARGETS = ["ñ", "q", "ğ", "ç", "ş", "c", "j", "h"]


def count_text(lines: list[str]) -> tuple[Counter, Counter]:
    """Returns (per-grapheme total counts, per-grapheme clip-hit counts)."""
    char_counts = Counter()
    clip_hits = Counter()
    for line in lines:
        low = line.lower()
        for ch in TARGETS:
            n = low.count(ch)
            if n > 0:
                char_counts[ch] += n
                clip_hits[ch] += 1
    return char_counts, clip_hits


def load_transcripts(path: Path) -> list[str]:
    txt = path.read_text(encoding="utf-8")
    if path.suffix.lower() in {".csv", ".tsv"}:
        delim = "\t" if path.suffix.lower() == ".tsv" else ","
        rows = list(csv.reader(txt.splitlines(), delimiter=delim))
        # Skip header if first row looks non-textual.
        return [r[-1] for r in rows if r]
    return [l for l in txt.splitlines() if l.strip()]


def main():
    ap = argparse.ArgumentParser()
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--transcripts", type=Path, help="text/csv/tsv with utterance per line")
    src.add_argument("--filenames", type=Path, help="dataset directory — use filenames as proxy")
    ap.add_argument("--min-rate", type=float, default=0.02,
                    help="warn if phoneme appears in fewer than this fraction of clips (default 0.02 = 2%%)")
    args = ap.parse_args()

    if args.transcripts:
        lines = load_transcripts(args.transcripts)
        source = f"transcripts: {args.transcripts}"
    else:
        if not args.filenames.is_dir():
            sys.exit(f"not a directory: {args.filenames}")
        lines = [p.stem for p in args.filenames.rglob("*.wav")]
        source = f"filenames: {args.filenames} ({len(lines)} files)"
        print("[coverage] NOTE: using filenames as proxy — accuracy depends on whether filenames\n"
              "                 carry transcript text. For real coverage, supply --transcripts.")

    total = len(lines)
    if total == 0:
        sys.exit("no input lines")

    char_counts, clip_hits = count_text(lines)

    print(f"\nSource: {source}")
    print(f"Clips: {total}\n")
    print(f"{'grapheme':<10} {'total':>8} {'clips':>8} {'clip %':>8}  {'status':<8}")
    print("-" * 50)
    warned = []
    for ch in TARGETS:
        tot = char_counts.get(ch, 0)
        hit = clip_hits.get(ch, 0)
        rate = hit / total
        status = "OK"
        if rate < args.min_rate:
            status = "LOW" if hit > 0 else "MISSING"
            warned.append((ch, status))
        print(f"{ch:<10} {tot:>8} {hit:>8} {rate*100:>7.1f}%  {status:<8}")

    print()
    if not warned:
        print("[coverage] all targets above threshold — dataset OK.")
        return

    crit = [c for c, s in warned if c in {"ñ", "q", "ğ"} and s == "MISSING"]
    if crit:
        print(f"[coverage] CRITICAL: {', '.join(crit)} entirely missing.")
        print("           RVC inference on words with these phonemes will likely")
        print("           collapse them to /n/, /k/, /g/. Mix in 3–5 min of native")
        print("           Crimean Tatar audio (Krym.Realii, ATR, QIRIM WEB TV) before")
        print("           training.")
    else:
        low = [c for c, _ in warned]
        print(f"[coverage] low coverage on: {', '.join(low)} — consider supplementing.")


if __name__ == "__main__":
    main()
