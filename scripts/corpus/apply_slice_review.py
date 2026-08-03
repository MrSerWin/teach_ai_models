#!/usr/bin/env python3
"""Apply the corrections made in SLICES.html.

Takes the exported `slice_review.json` and, for every item marked "годится",
writes the corrected transcript into `align-staging/ready/` so the alignment run
picks it up. Items marked "не то произведение" stay where they are.

Nothing is deleted: the original folder under `needs-review/` keeps its own
transcript, and the previous version is preserved as `transcript.orig.txt` the
first time a correction is applied.

    python3 apply_slice_review.py ~/Downloads/slice_review.json
"""
from __future__ import annotations

import json
import os
import shutil
import sys

LIBRARY = "/Volumes/T9/AnaYurt/Books/Qirimtatar"
STAGE = os.path.join(LIBRARY, "align-staging")
REVIEW = os.path.join(STAGE, "needs-review")
READY = os.path.join(STAGE, "ready")


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    data = json.load(open(sys.argv[1]))
    moved, rejected, untouched = [], [], []

    for item in data["items"]:
        src = os.path.join(REVIEW, item["name"])
        if not os.path.isdir(src):
            untouched.append((item["name"], "folder not found"))
            continue
        if item.get("verdict") == "reject":
            rejected.append(item["name"])
            continue
        if item.get("verdict") != "ok":
            untouched.append((item["name"], "not judged"))
            continue

        text = item.get("transcript") or ""
        if len(text.strip()) < 200:
            untouched.append((item["name"], "corrected transcript is too short"))
            continue

        # Keep the machine's first attempt next to the corrected one.
        tpath = os.path.join(src, "transcript.txt")
        opath = os.path.join(src, "transcript.orig.txt")
        if os.path.exists(tpath) and not os.path.exists(opath):
            shutil.copy2(tpath, opath)
        with open(tpath, "w") as fh:
            fh.write(text)

        dst = os.path.join(READY, item["name"])
        os.makedirs(dst, exist_ok=True)
        for f in sorted(os.listdir(src)):
            s, d = os.path.join(src, f), os.path.join(dst, f)
            if os.path.isdir(s) or os.path.exists(d):
                continue
            if os.path.islink(s):
                os.symlink(os.readlink(s), d)
            elif f.endswith((".mp3", ".m4a", ".wav")):
                os.symlink(s, d)          # audio stays single-copy
            else:
                shutil.copy2(s, d)
        moved.append((item["name"], len(text), item.get("edited")))

    print(f"promoted to ready: {len(moved)}")
    for name, n, edited in moved:
        print(f"  {name}  ({n} chars{', edited by hand' if edited else ', unchanged'})")
    if rejected:
        print(f"\nrejected, left in needs-review: {len(rejected)}")
        for n in rejected:
            print(f"  {n}")
    if untouched:
        print(f"\nleft alone: {len(untouched)}")
        for n, why in untouched:
            print(f"  {n}: {why}")
    if moved:
        print("\nNext: re-run the alignment over ready/ — only the new folders will be built:")
        print("  cd experiments/06_tts_dataset && conda activate crh_align")
        print(f"  python scripts/run_all.py {READY} --skip-existing")
        print("  python scripts/qc_report.py . && python scripts/split_by_source.py")


if __name__ == "__main__":
    main()
