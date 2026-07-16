#!/usr/bin/env python3
"""Curate a tight RVC training subset from a large clean segment pool.

RVC learns a single timbre and needs only ~30-60 min of clean voice; more
gives diminishing returns. This picks the best ~N minutes from the full pool
produced by prep-audiobook.py, balanced across source books so no single
recording session dominates the timbre.

Selection:
  - keep only segments with sim >= --min-sim (extra-safe voice match)
  - keep only 4-9s segments (ideal RVC utterance length)
  - round-robin across books, highest-sim first, until --minutes reached
  - copy chosen WAVs into <out>/  (flat dir, ready for push-data.sh)

Usage:
  python3 scripts/rvc/curate-rvc-subset.py \
    --pool experiments/04_rvc_voice_clone/data/elvide_crh \
    --out  experiments/04_rvc_voice_clone/data/elvide_rvc \
    --minutes 60
"""
import argparse, csv, shutil
from pathlib import Path
from collections import defaultdict


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pool", required=True, help="prep-audiobook.py output dir (has manifest.csv + wav/)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--minutes", type=float, default=60.0)
    ap.add_argument("--min-sim", type=float, default=0.90)
    ap.add_argument("--min-s", type=float, default=4.0)
    ap.add_argument("--max-s", type=float, default=9.0)
    args = ap.parse_args()

    pool = Path(args.pool)
    rows = [r for r in csv.DictReader(open(pool / "manifest.csv"))]
    ok = [r for r in rows
          if float(r["sim"]) >= args.min_sim
          and args.min_s <= float(r["dur"]) <= args.max_s]

    by_book = defaultdict(list)
    for r in ok:
        by_book[r["book"]].append(r)
    for b in by_book:
        by_book[b].sort(key=lambda r: -float(r["sim"]))   # best first

    out = Path(args.out)
    (out / "wav").mkdir(parents=True, exist_ok=True)
    chosen, secs = [], 0.0
    target = args.minutes * 60
    books = sorted(by_book)
    ptr = {b: 0 for b in books}
    while secs < target:
        progressed = False
        for b in books:
            if secs >= target:
                break
            i = ptr[b]
            if i < len(by_book[b]):
                r = by_book[b][i]
                ptr[b] += 1
                chosen.append(r)
                secs += float(r["dur"])
                progressed = True
        if not progressed:
            break

    mf = open(out / "manifest.csv", "w", newline="")
    w = csv.writer(mf)
    w.writerow(["seg", "book", "chapter", "start_s", "end_s", "dur", "sim", "lufs_in", "transcript"])
    per_book = defaultdict(float)
    for r in chosen:
        shutil.copy2(pool / "wav" / r["seg"], out / "wav" / r["seg"])
        w.writerow([r[k] for k in ("seg", "book", "chapter", "start_s", "end_s", "dur", "sim", "lufs_in", "transcript")])
        per_book[r["book"]] += float(r["dur"])
    mf.close()

    print(f"curated {len(chosen)} segments / {secs/60:.1f} min -> {out}/wav")
    print(f"pool had {len(ok)}/{len(rows)} eligible (sim>={args.min_sim}, {args.min_s}-{args.max_s}s)")
    print("per-book minutes:")
    for b in sorted(per_book):
        print(f"  book {b}: {per_book[b]/60:.1f} min")


if __name__ == "__main__":
    main()
