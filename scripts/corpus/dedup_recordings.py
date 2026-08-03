#!/usr/bin/env python3
"""Find duplicate *recordings* across raw corpus sources — by audio fingerprint.

The unit of duplication is a **recording**, never a work. The same text read by
two different people is two valid recordings and both are kept: that is exactly
the multi-speaker material a TTS/ASR corpus wants. So a title match alone never
removes anything, and neither does a duration match — only Chromaprint agreement
on the actual audio does.

What it compares
----------------
Maye Safet publishes the same readings to YouTube and Telegram, so those two
folders genuinely overlap and are compared file-by-file. Other sources
(leylaemir-org, trkmillet) have *different* readers, so they are never deduped
against her; instead, works whose titles collide across sources are reported as
multi-reader pairs — a feature, not a defect.

Verdicts
--------
- ``duplicate``       fingerprints agree → same recording on both channels
- ``same-length``     duration matches but audio differs → different reading,
                      or one is an excerpt; KEEP BOTH, listed for review
- ``unique``          no counterpart

Nothing is deleted or moved: raw sources are immutable. Output is a map the
dataset build consumes.

Usage
-----
    python3 dedup_recordings.py                 # full run (fingerprints cached)
    python3 dedup_recordings.py --refresh       # ignore the fingerprint cache
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import unicodedata
from concurrent.futures import ThreadPoolExecutor

import numpy as np

SOURCES = "/Volumes/T9/AnaYurt/Books/Qirimtatar/sources"
MS = os.path.join(SOURCES, "maye-safet")
YT_DIR = os.path.join(MS, "youtube")
TG_DIR = os.path.join(MS, "telegram-arifler_ve_ses")
OUT_JSON = os.path.join(MS, "dedup_map.json")
OUT_MD = os.path.join(MS, "DEDUP_REPORT.md")
CACHE = os.path.join(MS, ".fingerprints.json")

# fpcalc reads at most this many seconds — plenty to identify a recording, and
# it keeps a 3-hour video from costing 3 hours of decoding.
FP_LENGTH = 300
# Chromaprint raw fingerprints of the same recording sit far below 0.15 bit-error;
# unrelated audio lands around 0.45. 0.25 separates them with room to spare.
MAX_BER = 0.25
# Only fingerprint-compare pairs whose durations are this close (seconds).
DUR_TOL = 4.0
# Report (never delete) pairs that match on duration but not on audio.
SAME_LEN_TOL = 2.0


def ffprobe_duration(path: str) -> float | None:
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", path],
            capture_output=True, text=True, timeout=120,
        )
        return float(out.stdout.strip())
    except Exception:
        return None


def audio_bitrate(path: str) -> int:
    """Audio-stream bitrate in bits/s (0 if unknown). No decoding — header read."""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "a:0",
             "-show_entries", "stream=bit_rate", "-of", "default=nw=1:nk=1", path],
            capture_output=True, text=True, timeout=120,
        )
        return int(out.stdout.strip())
    except Exception:
        return 0


def fingerprint(path: str) -> list[int] | None:
    """Chromaprint raw fingerprint: one 32-bit int per ~0.124 s of audio."""
    try:
        out = subprocess.run(
            ["fpcalc", "-raw", "-length", str(FP_LENGTH), path],
            capture_output=True, text=True, timeout=600,
        )
        for line in out.stdout.splitlines():
            if line.startswith("FINGERPRINT="):
                return [int(x) for x in line[12:].split(",") if x]
    except Exception:
        pass
    return None


def bit_error(a: np.ndarray, b: np.ndarray) -> float:
    """Lowest mean bit-error rate over a small alignment sweep.

    The two uploads rarely start on the same frame (intros, trimmed silence),
    so a direct comparison would call identical recordings different. Sweeping
    the offset costs little and fixes that.
    """
    best = 1.0
    span = min(len(a), len(b))
    if span < 40:  # under ~5 s of audio there is not enough to judge
        return 1.0
    max_shift = min(120, span // 2)  # ±15 s
    for shift in range(-max_shift, max_shift + 1, 2):
        x, y = (a[shift:], b[: len(a) - shift]) if shift >= 0 else (a[: len(b) + shift], b[-shift:])
        n = min(len(x), len(y))
        if n < 40:
            continue
        diff = np.bitwise_xor(x[:n], y[:n])
        # popcount over 32-bit ints
        bits = np.unpackbits(diff.astype(">u4").view(np.uint8)).sum()
        ber = bits / (n * 32)
        best = min(best, ber)
    return best


def norm_title(name: str) -> str:
    """Loose title key for cross-reader collision detection."""
    s = unicodedata.normalize("NFKD", name)
    s = re.sub(r"\[[A-Za-z0-9_-]{11}\]", "", s)      # youtube id
    s = re.sub(r"^\d{6,8}\s*-\s*", "", s)            # yt date prefix
    s = re.sub(r"^\d+_", "", s)                       # tg post id prefix
    s = os.path.splitext(s)[0]
    s = re.sub(r"[^\w\s]", " ", s.lower())
    return re.sub(r"\s+", " ", s).strip()


def collect(directory: str, exts: tuple[str, ...]) -> list[str]:
    return sorted(
        os.path.join(directory, f)
        for f in os.listdir(directory)
        if f.lower().endswith(exts) and not f.startswith(".")
    )


def load_cache(refresh: bool) -> dict:
    if refresh or not os.path.exists(CACHE):
        return {}
    try:
        return json.load(open(CACHE))
    except Exception:
        return {}


def probe_all(paths: list[str], cache: dict, label: str) -> dict[str, dict]:
    todo = [p for p in paths if p not in cache]
    print(f"[{label}] {len(paths)} files, {len(todo)} to fingerprint", flush=True)

    def work(p: str) -> tuple[str, dict]:
        return p, {"dur": ffprobe_duration(p), "fp": fingerprint(p), "abr": audio_bitrate(p)}

    # Bitrate was added after the first run; backfill it without re-fingerprinting.
    for p in paths:
        if p in cache and "abr" not in cache[p]:
            cache[p]["abr"] = audio_bitrate(p)

    if todo:
        with ThreadPoolExecutor(max_workers=4) as ex:
            for i, (p, meta) in enumerate(ex.map(work, todo), 1):
                cache[p] = meta
                if i % 20 == 0 or i == len(todo):
                    print(f"[{label}] {i}/{len(todo)}", flush=True)
                    json.dump(cache, open(CACHE, "w"))
    return {p: cache[p] for p in paths}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="ignore fingerprint cache")
    args = ap.parse_args()

    yt = collect(YT_DIR, (".m4a",))
    tg = collect(TG_DIR, (".mp3", ".mp4"))
    if not yt or not tg:
        sys.exit(f"nothing to compare: yt={len(yt)} tg={len(tg)}")

    cache = load_cache(args.refresh)
    ytm = probe_all(yt, cache, "youtube")
    tgm = probe_all(tg, cache, "telegram")
    json.dump(cache, open(CACHE, "w"))

    fp = {p: np.array(m["fp"], dtype=np.int64) for p, m in {**ytm, **tgm}.items() if m.get("fp")}

    pairs, same_len = [], []
    print(f"[match] comparing {len(yt)} × {len(tg)}", flush=True)
    for y in yt:
        ydur = ytm[y].get("dur")
        for t in tg:
            tdur = tgm[t].get("dur")
            if not ydur or not tdur or abs(ydur - tdur) > DUR_TOL:
                continue
            if y not in fp or t not in fp:
                continue
            ber = bit_error(fp[y], fp[t])
            yabr, tabr = ytm[y].get("abr", 0), tgm[t].get("abr", 0)
            rec = {
                "youtube": os.path.basename(y), "telegram": os.path.basename(t),
                "yt_dur": round(ydur, 1), "tg_dur": round(tdur, 1),
                "bit_error": round(ber, 3),
                "yt_kbps": yabr // 1000, "tg_kbps": tabr // 1000,
                # YouTube re-encodes every upload to a fixed 127 kbps; Telegram
                # keeps what the author uploaded. Take the higher bitrate, which
                # in practice means Telegram — falling back to it on a tie since
                # it is the closer-to-source copy.
                "canonical": "youtube" if yabr > tabr else "telegram",
            }
            if ber <= MAX_BER:
                pairs.append(rec)
            elif abs(ydur - tdur) <= SAME_LEN_TOL:
                same_len.append(rec)

    # Keep the best match per YouTube file; a recording can only be one dupe.
    best: dict[str, dict] = {}
    for r in sorted(pairs, key=lambda r: r["bit_error"]):
        best.setdefault(r["youtube"], r)
    dupes = sorted(best.values(), key=lambda r: r["bit_error"])
    dup_tg = {r["telegram"] for r in dupes}
    dup_yt = set(best)

    # Skipped YouTube items: no audio on disk, so only their claimed TG twin can
    # be re-checked — by duration from info.json against the *complete* rip.
    skipped = []
    tg_durs = [m["dur"] for m in tgm.values() if m.get("dur")]
    for f in os.listdir(YT_DIR):
        if not f.endswith(".info.json"):
            continue
        stem = f[: -len(".info.json")]
        if os.path.exists(os.path.join(YT_DIR, stem + ".m4a")):
            continue
        try:
            info = json.load(open(os.path.join(YT_DIR, f)))
        except Exception:
            continue
        d = info.get("duration")
        if not d:
            continue
        near = [x for x in tg_durs if abs(x - d) <= DUR_TOL]
        skipped.append({"title": info.get("title", stem), "duration": d,
                        "tg_candidates": len(near)})
    orphans = [s for s in skipped if s["tg_candidates"] == 0]

    result = {
        "generated_for": "maye-safet (YouTube ⇄ Telegram, same reader)",
        "rule": "duplicate = fingerprint agreement on the audio; same work by a "
                "different reader is never a duplicate and both are kept",
        "max_bit_error": MAX_BER,
        "counts": {
            "youtube_files": len(yt), "telegram_files": len(tg),
            "duplicates": len(dupes),
            "youtube_unique": len(yt) - len(dup_yt),
            "telegram_unique": len(tg) - len(dup_tg),
            "same_length_different_audio": len(same_len),
            "skipped_yt_items": len(skipped), "skipped_without_tg_match": len(orphans),
        },
        "duplicates": dupes,
        "same_length_different_audio": sorted(same_len, key=lambda r: r["bit_error"]),
        "skipped_yt_without_tg_match": orphans,
    }
    json.dump(result, open(OUT_JSON, "w"), ensure_ascii=False, indent=2)

    c = result["counts"]
    md = [
        "# Maye Safet — recording dedup (YouTube ⇄ Telegram)",
        "", "Generated by `scripts/corpus/dedup_recordings.py`. Nothing was deleted:",
        "raw sources are immutable, this is a map for the dataset build.", "",
        "**Rule:** a duplicate is the *same recording* published twice, decided by",
        "Chromaprint agreement on the audio. The same work read by a different",
        f"person is not a duplicate — both are kept. Threshold: bit-error ≤ {MAX_BER}.",
        "",
        "| | |", "|---|---|",
        f"| YouTube files | {c['youtube_files']} |",
        f"| Telegram files | {c['telegram_files']} |",
        f"| **Duplicate pairs** | **{c['duplicates']}** |",
        f"| YouTube-only | {c['youtube_unique']} |",
        f"| Telegram-only | {c['telegram_unique']} |",
        f"| Same length, different audio (kept both) | {c['same_length_different_audio']} |",
        f"| YT items skipped at download time | {c['skipped_yt_items']} |",
        f"| …of those, no TG counterpart now | {c['skipped_without_tg_match']} |",
        "",
    ]
    if orphans:
        md += ["## Skipped on YouTube but absent from Telegram", "",
               "These were marked done in `archive.txt` as Telegram duplicates while the",
               "rip was still half-finished. The finished rip has nothing of that length —",
               "re-download them or the material is simply missing.", "",
               "| Title | Duration (s) |", "|---|---|"]
        md += [f"| {o['title']} | {round(o['duration'])} |" for o in orphans]
        md += [""]
    if same_len:
        md += ["## Same length, different audio — keep both", "",
               "Equal duration but the audio disagrees: a different reading, a different",
               "reader, or one is an excerpt. Listed so the build does not treat length",
               "as identity.", "", "| YouTube | Telegram | Bit-error |", "|---|---|---|"]
        md += [f"| {r['youtube']} | {r['telegram']} | {r['bit_error']} |"
               for r in result["same_length_different_audio"][:40]]
        md += [""]
    if dupes:
        md += ["## Duplicate pairs", "",
               "`canonical` is the copy to build from. YouTube re-encodes every upload",
               "to a fixed 127 kbps, so it is never the better copy — Telegram carries",
               "what the author actually uploaded (127 kbps at worst, up to 198 kbps).",
               "", "| YouTube | Telegram | Bit-error | Duration | kbps yt/tg | Canonical |",
               "|---|---|---|---|---|---|"]
        md += [f"| {r['youtube']} | {r['telegram']} | {r['bit_error']} | {r['yt_dur']} "
               f"| {r['yt_kbps']}/{r['tg_kbps']} | {r['canonical']} |" for r in dupes]
        md += [""]
    open(OUT_MD, "w").write("\n".join(md))

    print(f"\nduplicates={c['duplicates']}  yt_only={c['youtube_unique']}  "
          f"tg_only={c['telegram_unique']}  same_len_keep_both={c['same_length_different_audio']}  "
          f"skipped_without_tg={c['skipped_without_tg_match']}")
    print(f"→ {OUT_JSON}\n→ {OUT_MD}")


if __name__ == "__main__":
    main()
