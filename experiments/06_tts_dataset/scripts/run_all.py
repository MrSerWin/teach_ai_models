#!/usr/bin/env python3
"""Run the full corpus: prepare text + align/segment every book, then QC.

Auto-discovers, in each book sub-folder of BOOKS_DIR, one audio file
(.wav/.mp3) and one transcript (.txt/.odt/.pdf), derives an ASCII slug from
the folder name, and runs prepare_text.py + align_segment.py for each.

Usage:
    run_all.py [BOOKS_DIR] [--only slug1,slug2] [--skip-existing]
"""
import argparse
import subprocess
import sys
from pathlib import Path

from unidecode import unidecode

BOOKS_DIR = "/Volumes/T9/AnaYurt/Books/Qirimtatar/sevil-books"
HERE = Path(__file__).resolve().parent
OUT_ROOT = HERE.parent
AUDIO_EXT = (".wav", ".mp3", ".m4a", ".flac")
TEXT_EXT = (".txt", ".odt", ".pdf")


def slugify(name):
    s = unidecode(name).lower()
    return "".join(c if c.isalnum() else "_" for c in s).strip("_")


def pick(folder, exts):
    cands = [p for p in folder.iterdir() if p.suffix.lower() in exts]
    return max(cands, key=lambda p: p.stat().st_size) if cands else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("books_dir", nargs="?", default=BOOKS_DIR)
    ap.add_argument("--only", default="")
    ap.add_argument("--skip-existing", action="store_true")
    a = ap.parse_args()

    only = set(s for s in a.only.split(",") if s)
    books = sorted(p for p in Path(a.books_dir).iterdir() if p.is_dir())
    done, skipped, failed = [], [], []

    for folder in books:
        slug = slugify(folder.name)
        if only and slug not in only:
            continue
        audio = pick(folder, AUDIO_EXT)
        text = pick(folder, TEXT_EXT)
        if not audio or not text:
            print(f"!! {folder.name}: missing audio/text — skipped")
            skipped.append(slug)
            continue
        seg = OUT_ROOT / "work" / slug / "segments.jsonl"
        if a.skip_existing and seg.exists():
            print(f"== {slug}: already done — skipped")
            continue

        clean_txt = OUT_ROOT / "work" / slug / "text.clean.txt"
        print(f"\n########## {slug}  ({folder.name}) ##########")
        try:
            subprocess.run([sys.executable, str(HERE / "prepare_text.py"),
                            str(text), str(clean_txt)], check=True)
            subprocess.run([sys.executable, str(HERE / "align_segment.py"),
                            str(audio), str(clean_txt), slug, str(OUT_ROOT)], check=True)
            done.append(slug)
        except subprocess.CalledProcessError as e:
            print(f"!! {slug}: FAILED ({e})")
            failed.append(slug)

    print(f"\n=== done: {len(done)}  skipped: {len(skipped)}  failed: {len(failed)} ===")
    if failed:
        print("failed:", ", ".join(failed))
    print("\nNow run:  python scripts/qc_report.py .")


if __name__ == "__main__":
    main()
