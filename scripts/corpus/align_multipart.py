#!/usr/bin/env python3
"""Align a book that is too long for one pass, part by part, without drifting.

`align_segment.py` handles ~80 minutes; «Чауш огълу» is 2h20m over nine files and
the aligner aborts on it (`std::length_error` from the C++ backtracking). The
audio is already split into the reader's own parts, so align those — the problem
is that the *text* has no matching split, and this book has no usable chapter
markers (six roman numerals for nine parts; the rest are page numbers).

Text boundaries come from **cumulative** duration: part *i* ends at
``chars * (seconds so far / total seconds)``. Each boundary is computed from the
whole, so an error at one seam cannot propagate to the next — unlike
chaining, where every part inherits the previous part's drift.

The reading rate is measured from this book (total characters over total audio),
not assumed. An earlier version fed each part a 35% margin and used the last
aligned clip as the anchor for the next part; that fails because forced
alignment fits *whatever* text it is given into the audio, so the anchor always
landed at the end of the margin. Parts then over-consumed by exactly the margin
and the text ran out two parts early.

Parts whose alignment looks unhealthy are reported, not silently kept: the
per-part retention after QC is the honest signal.

    python3 align_multipart.py <staged-folder-with-_parts.txt>
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from match_books import skeleton  # noqa: E402

EXP = "/Users/servin/1_dev/my/ai/teach_ai_models/experiments/06_tts_dataset"
PY = "/opt/homebrew/anaconda3/envs/crh_align/bin/python"
# No margin: extra text does not get skipped, it gets squeezed into the audio.


def duration(path: str) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=nw=1:nk=1", path],
                       capture_output=True, text=True, timeout=120)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def find_offset(text: str, phrase: str, hint: int) -> int:
    """Where does `phrase` sit in `text`? Searched on the skeleton, mapped back."""
    sk_text, sk_phrase = skeleton(text), " ".join(skeleton(phrase).split())
    if not sk_phrase:
        return hint
    i = sk_text.find(sk_phrase)
    if i < 0:
        words = sk_phrase.split()
        for n in (8, 5, 3):
            if len(words) >= n:
                i = sk_text.find(" ".join(words[-n:]))
                if i >= 0:
                    break
    if i < 0:
        return hint
    return int(i / max(1, len(sk_text)) * len(text))


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    folder = os.path.abspath(sys.argv[1])
    parts_file = os.path.join(folder, "_parts.txt")
    if not os.path.exists(parts_file):
        sys.exit(f"no _parts.txt in {folder} — this is not a multi-part item")

    parts = [m.group(1) for m in
             (re.match(r"file '(.*)'", ln) for ln in open(parts_file)) if m]
    full = open(os.path.join(folder, "transcript.txt"), errors="ignore").read()
    base = os.path.basename(folder)
    print(f"{base}: {len(parts)} parts, {len(full)} chars of text", flush=True)

    durs = [duration(a) for a in parts]
    total = sum(durs)
    rate = len(full) / total if total else 0
    print(f"  measured reading rate: {rate:.1f} chars/s over {total:.0f}s", flush=True)

    # Absolute boundaries, snapped to the nearest paragraph break so a part never
    # starts mid-sentence.
    bounds, acc = [0], 0.0
    for d in durs:
        acc += d
        pos = int(len(full) * acc / total)
        window = full[max(0, pos - 400):pos + 400]
        br = window.rfind("\n\n")
        bounds.append(max(0, pos - 400) + br if br > 0 else pos)
    bounds[-1] = len(full)

    results = []
    for n, audio in enumerate(parts, 1):
        secs = durs[n - 1]
        slice_txt = full[bounds[n - 1]:bounds[n]]
        if len(slice_txt.strip()) < 200:
            print(f"  part {n}: empty slice — skipping", flush=True)
            continue

        slug = f"{base}_p{n:02d}"
        work = os.path.join(EXP, "work", slug)
        os.makedirs(work, exist_ok=True)
        tpath = os.path.join(work, "slice.txt")
        open(tpath, "w").write(slice_txt)

        subprocess.run([PY, os.path.join(EXP, "scripts", "prepare_text.py"),
                        tpath, os.path.join(work, "text.clean.txt")],
                       check=False, capture_output=True)
        clean = os.path.join(work, "text.clean.txt")
        if not os.path.exists(clean):
            open(clean, "w").write(slice_txt)

        print(f"  part {n}/{len(parts)}: {secs:.0f}s, text[{bounds[n - 1]}:{bounds[n]}] "
              f"= {len(slice_txt)} chars ({len(slice_txt) / secs:.1f}/s)", flush=True)
        r = subprocess.run(["nice", "-n", "19", PY,
                            os.path.join(EXP, "scripts", "align_segment.py"),
                            audio, clean, slug, EXP],
                           capture_output=True, text=True)
        seg = os.path.join(work, "segments.jsonl")
        if r.returncode != 0 or not os.path.exists(seg):
            print(f"    FAILED: {(r.stderr or '').strip().splitlines()[-1:] }", flush=True)
            results.append({"part": n, "slug": slug, "ok": False})
            continue

        rows = [json.loads(x) for x in open(seg)]
        print(f"    {len(rows)} clips", flush=True)
        results.append({"part": n, "slug": slug, "ok": True, "clips": len(rows),
                        "seconds": round(secs), "chars": len(slice_txt)})

    print("\npart  clips  audio   chars")
    for x in results:
        print("  %2d  %5s  %5ss  %s" % (x["part"], x.get("clips", "—"),
                                        x.get("seconds", "—"), x.get("chars", "—")))
    ok = [x for x in results if x.get("ok")]
    print(f"\naligned {len(ok)}/{len(parts)} parts, "
          f"{sum(x.get('chars', 0) for x in ok)} of {len(full)} chars")
    print("Next: python scripts/qc_report.py .   (re-runnable, gates every clip)")


if __name__ == "__main__":
    main()
