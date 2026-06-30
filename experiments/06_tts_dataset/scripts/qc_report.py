#!/usr/bin/env python3
"""Aggregate per-book segments.jsonl into a gated LJSpeech dataset + QC report.

Reads every work/<slug>/segments.jsonl, applies quality thresholds, and writes:
  dataset/metadata.csv         kept clips, LJSpeech format  (id|text|text)
  dataset/metadata.review.csv  quarantined clips + reason   (id|reason|text)
  dataset/segments.jsonl       all clips with metrics + keep flag
  dataset/QC_REPORT.md         human-readable summary

Gating is here (not in align_segment) so thresholds can be retuned without
re-running alignment. "score" is the mean per-frame CTC log-prob — a direct
audio<->text match measure; closer to 0 is better. char_rate (chars/s) flags
clips where audio and text length disagree (missed/extra speech).

Usage:
    qc_report.py <out_root> [--score MIN] [--cr-lo LO] [--cr-hi HI] [--max-dur D]
"""
import argparse
import json
from pathlib import Path

# Defaults calibrated on the corpus (median score ~-0.3, char_rate ~11).
SCORE_MIN = -0.95     # quarantine clips whose acoustics poorly match the text
CR_LO, CR_HI = 6.0, 19.0   # plausible Crimean-Tatar speaking-rate band (chars/s)
MAX_DUR = 13.0        # allow slight overrun past the 12 s packing ceiling
MIN_DUR = 3.5


def reason(r, a):
    if r["score"] < a.score:
        return f"low_score({r['score']:.2f})"
    if not (a.cr_lo <= r["char_rate"] <= a.cr_hi):
        return f"char_rate({r['char_rate']:.1f})"
    if r["dur"] > a.max_dur or r["dur"] < MIN_DUR:
        return f"duration({r['dur']:.1f})"
    if r["has_digit"]:
        return "has_digit"   # needs spoken-form expansion before training
    return ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out_root")
    ap.add_argument("--score", type=float, default=SCORE_MIN, dest="score")
    ap.add_argument("--cr-lo", type=float, default=CR_LO, dest="cr_lo")
    ap.add_argument("--cr-hi", type=float, default=CR_HI, dest="cr_hi")
    ap.add_argument("--max-dur", type=float, default=MAX_DUR, dest="max_dur")
    a = ap.parse_args()

    out = Path(a.out_root)
    rows = []
    for jl in sorted((out / "work").glob("*/segments.jsonl")):
        rows.extend(json.loads(l) for l in jl.read_text(encoding="utf-8").splitlines() if l.strip())
    if not rows:
        raise SystemExit("no segments.jsonl found — run align_segment.py first")

    for r in rows:
        r["reason"] = reason(r, a)
        r["keep"] = not r["reason"]

    ds = out / "dataset"
    kept = [r for r in rows if r["keep"]]
    rej = [r for r in rows if not r["keep"]]

    def field(s):
        # LJSpeech metadata is raw '|'-delimited (no CSV quoting); keep text on
        # one line and free of the delimiter.
        return " ".join(str(s).replace("|", "/").split())

    # Two dataset variants (same wavs): Cyrillic and Latin transcripts.
    with open(ds / "metadata.cyr.csv", "w", encoding="utf-8") as f:
        for r in kept:
            cyr = field(r.get("text_cyr", r["text"]))
            f.write(f"{r['id']}|{cyr}|{cyr}\n")
    with open(ds / "metadata.lat.csv", "w", encoding="utf-8") as f:
        for r in kept:
            lat = field(r.get("text_lat", r["text"]))
            f.write(f"{r['id']}|{lat}|{lat}\n")
    with open(ds / "metadata.review.csv", "w", encoding="utf-8") as f:
        for r in rej:
            f.write(f"{r['id']}|{r['reason']}|{field(r['text'])}\n")
    with open(ds / "segments.jsonl", "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # ---- report ----
    def hms(s):
        return f"{int(s//3600)}h{int(s%3600//60):02d}m"

    by_book = {}
    for r in rows:
        b = by_book.setdefault(r["book"], {"n": 0, "keep": 0, "dur": 0.0, "kdur": 0.0})
        b["n"] += 1
        b["dur"] += r["dur"]
        if r["keep"]:
            b["keep"] += 1
            b["kdur"] += r["dur"]

    reasons = {}
    for r in rej:
        key = r["reason"].split("(")[0]
        reasons[key] = reasons.get(key, 0) + 1

    lines = ["# TTS dataset QC report", ""]
    lines.append(f"- Total segments: **{len(rows)}**  ({hms(sum(r['dur'] for r in rows))})")
    lines.append(f"- Kept: **{len(kept)}** ({hms(sum(r['dur'] for r in kept))}, "
                 f"{100*len(kept)//max(len(rows),1)}%)")
    lines.append(f"- Quarantined: **{len(rej)}**")
    lines.append(f"- Thresholds: score≥{a.score}, char_rate∈[{a.cr_lo},{a.cr_hi}], "
                 f"dur∈[{MIN_DUR},{a.max_dur}]s")
    lines.append("")
    lines.append("## Quarantine reasons")
    for k, v in sorted(reasons.items(), key=lambda x: -x[1]):
        lines.append(f"- {k}: {v}")
    lines.append("")
    lines.append("## Per book")
    lines.append("| book | segs | kept | kept min |")
    lines.append("|---|---|---|---|")
    for b, s in sorted(by_book.items()):
        lines.append(f"| {b} | {s['n']} | {s['keep']} | {s['kdur']/60:.1f} |")
    (ds / "QC_REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"kept {len(kept)}/{len(rows)} clips "
          f"({hms(sum(r['dur'] for r in kept))} train audio)")
    print(f"quarantined {len(rej)}: " +
          ", ".join(f"{k}={v}" for k, v in sorted(reasons.items(), key=lambda x: -x[1])))
    print(f"-> {ds/'metadata.cyr.csv'} | {ds/'metadata.lat.csv'} | {ds/'QC_REPORT.md'}")


if __name__ == "__main__":
    main()
