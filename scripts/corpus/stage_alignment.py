#!/usr/bin/env python3
"""Stage confirmed recording⇄book pairs for forced alignment.

Builds the layout `experiments/06_tts_dataset/scripts/run_all.py` expects — one
folder per item holding a single audio file and a single transcript — from the
pairs `verify_matches.py` confirmed.

Nothing is deleted or moved. Audio is symlinked (the corpus is 34 GB); the only
new bytes are transcripts and, where a work is split across several recordings,
one concatenated audio file.

The decisive check is **scale**: a forced aligner given a whole poetry
collection and a two-minute recording of one poem will not fail loudly, it will
silently produce garbage timings. Crimean Tatar speech runs ≈12–16 characters
per second, so comparing the transcript's length against the audio duration
tells us whether the pair is a whole book or one work inside a collection:

- ratio within ``SCALE_OK`` → whole work, staged as is;
- transcript far longer → the book is a collection; the work's section is cut
  out by locating its title and taking the expected span, and the folder is
  flagged for review;
- transcript far shorter → not enough text; not staged.

    python3 stage_alignment.py            # analyse + stage
    python3 stage_alignment.py --dry-run  # analyse only, write nothing
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from match_books import skeleton  # noqa: E402

SOURCES = "/Volumes/T9/AnaYurt/Books/Qirimtatar/sources"
LIBRARY = "/Volumes/T9/AnaYurt/Books/Qirimtatar"
STAGE = os.path.join(LIBRARY, "align-staging")
READY = os.path.join(STAGE, "ready")
REVIEW = os.path.join(STAGE, "needs-review")
IN_JSON = os.path.join(SOURCES, "verified_matches.json")
REPORT = os.path.join(SOURCES, "STAGING.md")

CHARS_PER_SEC = 14.0          # crh reading pace, measured against the Elvide corpus
SCALE_OK = (0.45, 2.2)        # transcript/expected ratio accepted as "whole work"
MIN_SECONDS = 20.0            # shorter recordings are not worth aligning


def duration(path: str) -> float:
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", path],
            capture_output=True, text=True, timeout=120)
        return float(r.stdout.strip())
    except Exception:
        return 0.0


def full_text(rel: str) -> str:
    """Whole-document text — the only acceptable transcript source.

    Explicitly does **not** fall back to the tg2026 OCR cache. That cache holds
    3–6 pages per book (title page + imprint) because the cataloguing task only
    needed metadata; it is fine for *finding* a title, which is what
    `verify_matches.py` uses it for, but as a transcript it is a title page
    masquerading as a work. An image-only book returns "" here and is reported
    as needing a real full-text OCR pass, not quietly aligned against its cover.
    """
    path = os.path.join(LIBRARY, rel)
    if os.path.exists(path) and path.lower().endswith(".pdf"):
        try:
            r = subprocess.run(["nice", "-n", "19", "pdftotext", "-q", path, "-"],
                               capture_output=True, text=True, timeout=600)
            if len(r.stdout.strip()) > 200:
                return r.stdout
        except Exception:
            pass
    return ""


def audio_paths(rec: dict) -> list[str]:
    """Every audio file belonging to one record, in reading order.

    Most sources give one file per record. trkmillet instead splits a book into
    numbered parts inside a folder ("01 - 1-boljuk.mp3", …); those are one
    continuous reading, so all parts are returned and concatenated later — the
    pipeline cuts clips afterwards.
    """
    src, f = rec["source"], rec["file"]
    if src == "trkmillet":
        base = os.path.join(SOURCES, "trkmillet")
        key = "".join(ch for ch in rec["work"].lower() if ch.isalnum())[:12]
        for d in sorted(os.listdir(base)) if os.path.isdir(base) else []:
            flat = "".join(ch for ch in d.lower() if ch.isalnum())
            if key and key in flat:
                folder = os.path.join(base, d)
                return sorted(os.path.join(folder, x) for x in os.listdir(folder)
                              if x.lower().endswith((".mp3", ".m4a", ".wav")))
        return []
    for c in {
        "leylaemir-org": [f"leylaemir-org/{f}", f"leylaemir-org/audio/{f}"],
        "maye-safet/youtube": [f"maye-safet/youtube/{f}"],
        "maye-safet/telegram": [f"maye-safet/telegram-arifler_ve_ses/{f}"],
    }.get(src, []):
        p = os.path.join(SOURCES, c)
        if os.path.exists(p):
            return [p]
    return []


def slug(s: str) -> str:
    s = skeleton(s).replace(" ", "_")
    return re.sub(r"_+", "_", s).strip("_")[:60] or "item"


def cut_section(text: str, title: str, want_chars: int) -> tuple[str, str]:
    """Take the span that starts at the work's title inside a collection."""
    sk = skeleton(text)
    phrase = " ".join(skeleton(title).split())
    if not phrase:
        return "", "no title to search for"
    # Map skeleton offsets back approximately: both strings keep word order, so
    # locate in the skeleton and use the same relative position in the original.
    i = sk.find(phrase)
    if i < 0:
        anchor = max(phrase.split(), key=len)
        i = sk.find(anchor)
        if i < 0:
            return "", "title not found in the full text"
    rel = i / max(1, len(sk))
    start = int(rel * len(text))
    span = int(want_chars * 1.25)
    return text[start:start + span], f"cut {span} chars from offset {start}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    rows = [r for r in json.load(open(IN_JSON))["results"] if r["verdict"] == "confirmed"]

    # One work split over several recordings is one alignment item.
    groups: dict[tuple[str, str], list[dict]] = {}
    for r in rows:
        groups.setdefault((r["work"], r["book"]), []).append(r)

    staged, skipped = [], []
    for (work, book), recs in sorted(groups.items()):
        paths = [p for r in sorted(recs, key=lambda x: x["file"]) for p in audio_paths(r)]
        if not paths:
            skipped.append((work, book, "no audio found on disk"))
            continue
        secs = sum(duration(p) for p in paths)
        if secs < MIN_SECONDS:
            skipped.append((work, book, f"audio only {secs:.0f}s"))
            continue
        text = full_text(book)
        if len(text.strip()) < 200:
            skipped.append((work, book, "image-only scan — needs a real full-text OCR pass"))
            continue

        want = secs * CHARS_PER_SEC
        ratio = len(text) / want
        note = f"{secs:.0f}s audio · {len(text)} chars · ratio {ratio:.2f}"
        if SCALE_OK[0] <= ratio <= SCALE_OK[1]:
            kind, body = "whole", text
        elif ratio > SCALE_OK[1]:
            body, how = cut_section(text, work, int(want))
            if not body:
                skipped.append((work, book, f"collection, {how} ({note})"))
                continue
            kind, note = "sliced", note + " · " + how
        else:
            skipped.append((work, book, "transcript shorter than the audio needs " + note))
            continue

        name = slug(work) + ("__" + slug(os.path.basename(book))[:18] if kind == "sliced" else "")
        folder = os.path.join(READY if kind == "whole" else REVIEW, name)
        staged.append({"folder": name, "work": work, "book": book, "kind": kind,
                       "seconds": round(secs), "chars": len(body), "parts": len(paths),
                       "note": note})
        if args.dry_run:
            continue
        os.makedirs(folder, exist_ok=True)
        if len(paths) == 1:
            link = os.path.join(folder, os.path.basename(paths[0]))
            if not os.path.exists(link):
                os.symlink(paths[0], link)
        else:
            merged = os.path.join(folder, name + ".mp3")
            if not os.path.exists(merged):
                lst = os.path.join(folder, "_parts.txt")
                with open(lst, "w") as fh:
                    for p in paths:
                        fh.write(f"file '{p}'\n")
                subprocess.run(["nice", "-n", "19", "ffmpeg", "-hide_banner", "-loglevel",
                                "error", "-f", "concat", "-safe", "0", "-i", lst,
                                "-c", "copy", merged], timeout=1800)
        with open(os.path.join(folder, "transcript.txt"), "w") as fh:
            fh.write(body)
        with open(os.path.join(folder, "SOURCE.md"), "w") as fh:
            fh.write(f"# {work}\n\n- book: `{book}`\n- audio parts: {len(paths)}\n"
                     f"- transcript: {kind}\n- {note}\n\n"
                     "Audio is a symlink into the read-only sources tree; the transcript is\n"
                     "extracted text. Nothing here modifies the archive.\n")

    lines = ["# Alignment staging", "",
             "Built by `scripts/corpus/stage_alignment.py` from the `confirmed` pairs.",
             "Audio is symlinked, never copied or moved; transcripts are extracted text.", "",
             f"Staged: **{len(staged)}** · not staged: **{len(skipped)}**", "",
             "A `sliced` transcript was cut out of a collection by locating the work's",
             "title — the span is approximate and **must be checked** before its clips are",
             "trusted. `whole` means the book is the work.", "",
             "| Folder | Work | Kind | Audio | Chars | Note |", "|---|---|---|---|---|---|"]
    for s in staged:
        lines.append(f"| `{s['folder']}` | {s['work'][:34]} | {s['kind']} | {s['seconds']}s "
                     f"({s['parts']}) | {s['chars']} | {s['note']} |")
    if skipped:
        lines += ["", "## Not staged", "", "| Work | Book | Reason |", "|---|---|---|"]
        lines += [f"| {w[:34]} | `{b[-40:]}` | {r} |" for w, b, r in skipped]
    lines.append("")
    if not args.dry_run:
        open(REPORT, "w").write("\n".join(lines))
    print("\n".join(lines[:6]))
    for s in staged:
        print(f"  staged {s['kind']:7} {s['folder'][:44]:46} {s['note']}")
    for w, b, r in skipped:
        print(f"  skip           {w[:44]:46} {r}")
    if not args.dry_run:
        print(f"\n→ {STAGE}\n→ {REPORT}")


if __name__ == "__main__":
    main()
