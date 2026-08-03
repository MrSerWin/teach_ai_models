#!/usr/bin/env python3
"""Split the LJSpeech metadata by source, because the corpus is no longer one voice.

The build was originally one narrator reading the `sevil-books` audiobooks, and
`metadata.cyr.csv` is an LJSpeech file — a format with no speaker column, which
silently assumes there is only one. On 2026-08-01 readings from `leylaemir-org`
were aligned into the same `work/` tree, and their clips landed in the same
metadata. Nothing is wrong with the clips; what is wrong is training a
single-speaker model on a file that now holds several voices.

Measured, not assumed: median F0 over a random sample is ≈206 Hz for the
`sevil-books` clips and ≈120 Hz for the new ones, and the new set spreads
107–226 Hz on its own — leylaemir credits no reader per record, so it is
several people.

This writes per-source metadata files and a manifest **alongside** the originals.
Nothing is deleted or overwritten: the merged files stay exactly as they are, so
whoever wants the mixed set still has it.

    python3 split_by_source.py [DATASET_DIR]
"""
from __future__ import annotations

import csv
import os
import sys

# Books aligned from Books/Qirimtatar/align-staging (leylaemir readers).
# Everything else came from the original sevil-books run.
LEYLAEMIR = {"adam_ve_kopek", "altin_basnen_hiyar_bas", "nenkejan_hanim_turbesi"}
GROUPS = {
    "leylaemir": LEYLAEMIR,
    # «Чауш огълу» from the TRK Millet audiobooks — one narrator (Elvide
    # Bekirova), a third voice again, so it gets its own group rather than
    # joining either of the others.
    "trkmillet": None,          # matched by prefix, see group_of()
}


def group_of(book: str) -> str:
    if book.startswith("jaus_oglu"):
        return "trkmillet"
    for g, books in GROUPS.items():
        if books and book in books:
            return g
    return "sevil"


def main() -> None:
    ds = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "dataset")
    ds = os.path.abspath(ds)

    written: dict[str, int] = {}
    manifest: list[tuple[str, str, str]] = []
    for variant in ("cyr", "lat"):
        src = os.path.join(ds, f"metadata.{variant}.csv")
        if not os.path.exists(src):
            continue
        rows = list(csv.reader(open(src), delimiter="|"))
        buckets: dict[str, list[list[str]]] = {}
        for r in rows:
            book = r[0].rsplit("_", 1)[0]
            g = group_of(book)
            buckets.setdefault(g, []).append(r)
            if variant == "cyr":
                manifest.append((r[0], book, g))
        for g, rs in buckets.items():
            out = os.path.join(ds, f"metadata.{g}.{variant}.csv")
            with open(out, "w", newline="") as fh:
                csv.writer(fh, delimiter="|").writerows(rs)
            written[f"{g}.{variant}"] = len(rs)

    if manifest:
        with open(os.path.join(ds, "sources.csv"), "w", newline="") as fh:
            w = csv.writer(fh, delimiter="|")
            w.writerow(["clip_id", "book", "source_group"])
            w.writerows(manifest)

    counts: dict[str, int] = {}
    for _cid, _book, g in manifest:
        counts[g] = counts.get(g, 0) + 1

    doc = [
        "# Sources and speakers in this dataset", "",
        "`metadata.cyr.csv` / `metadata.lat.csv` are LJSpeech files, and LJSpeech has",
        "no speaker column — it assumes one voice. Since the 2026-08-01 additions that",
        "assumption no longer holds, so the same clips are also published split by",
        "source. **The merged files are untouched**; pick the one that matches what you",
        "are training.", "",
        "| File | Clips | Voice |", "|---|---|---|",
        f"| `metadata.sevil.*.csv` | {counts.get('sevil', 0)} | the original single narrator "
        "(`sevil-books`) — use this for single-speaker fine-tuning |",
        f"| `metadata.leylaemir.*.csv` | {counts.get('leylaemir', 0)} | leylaemir.org readings — "
        "**several readers, none credited per record** |",
        f"| `metadata.trkmillet.*.csv` | {counts.get('trkmillet', 0)} | TRK Millet audiobook "
        "«Чауш огълу» — one narrator (Elvide Bekirova) |",
        f"| `metadata.cyr.csv` (merged) | {sum(counts.values())} | everything; multi-speaker |",
        "",
        "`sources.csv` maps every clip to its book and source group.", "",
        "## Evidence",
        "",
        "Median F0 over a random sample of clips: **≈206 Hz** for `sevil-books`,",
        "**≈120 Hz** for the additions, which spread 107–226 Hz among themselves.",
        "That is a cheap pitch check, not speaker verification — the repo's",
        "`scripts/rvc/build-voice-centroid.py` does the real thing with speaker",
        "embeddings, but `resemblyzer` is not installed in the `crh_align` env.",
        "Run it before treating `metadata.leylaemir.*` as any fixed number of voices.",
        "",
        "## Why the additions are still worth having",
        "",
        "Multi-speaker material is what ASR and multi-speaker TTS want; it is only",
        "wrong inside a single-speaker file. Keep both and choose per task.",
        "",
    ]
    open(os.path.join(ds, "SOURCES.md"), "w").write("\n".join(doc))
    print("wrote:", ", ".join(f"{k}={v}" for k, v in sorted(written.items())))
    print(f"→ {ds}/sources.csv\n→ {ds}/SOURCES.md")


if __name__ == "__main__":
    main()
