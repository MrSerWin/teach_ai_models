#!/usr/bin/env python3
"""Prepare a clean single-speaker dataset from audiobook MP3s.

Purpose-built for the TRK Millet Crimean-Tatar audiobooks (one narrator,
Elvide Bekirova, across ~28h) but generic for any solo-reader corpus with
music intro/outro jingles.

Pipeline per source file:
  ffmpeg decode -> mono 48k
  -> librosa silence-split into 3.5-10s utterances (breath-pause merge)
  -> SPEAKER-EMBEDDING GATE: resemblyzer embed each segment, keep only those
     whose cosine sim to the target-voice centroid >= --min-sim.
     This is what removes the music jingles, the station-announcer intros,
     and any non-target audio automatically -- no manual auditioning / UVR.
  -> quality gate (clip/peak, min duration)
  -> loudness normalize (EBU R128, -23 LUFS, -3 dB peak) via pyloudnorm
  -> write <out>/wav/*.wav + <out>/manifest.csv

The manifest maps every segment back to (book, chapter file, start_s, end_s,
sim, lufs) so the same clean set is reusable for TTS (add transcripts later).

Build the centroid once from known-good clips of the target speaker (see
build-voice-centroid.py). One physical speaker == one centroid == one RVC model.

Deps: pip install resemblyzer librosa soundfile pyloudnorm numpy
"""
import argparse, csv, subprocess, sys, tempfile, os
from pathlib import Path
import numpy as np


def decode_mono(path: Path, sr: int) -> np.ndarray:
    """ffmpeg -> mono float32 at sr (robust MP3 decode, faster than librosa)."""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
        tmp = tf.name
    try:
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-i", str(path),
             "-ac", "1", "-ar", str(sr), "-f", "wav", tmp],
            check=True)
        import soundfile as sf
        a, _ = sf.read(tmp, dtype="float32")
        return a
    finally:
        os.unlink(tmp)


def merge_close(intervals, gap_samples):
    if len(intervals) == 0:
        return intervals
    out = [list(intervals[0])]
    for s, e in intervals[1:]:
        if s - out[-1][1] < gap_samples:
            out[-1][1] = e
        else:
            out.append([s, e])
    return out


def segments(audio, sr, top_db, min_s, max_s, merge_gap_s):
    """Yield (start, end) sample ranges of 3.5-10s speech chunks."""
    import librosa
    raw = librosa.effects.split(audio, top_db=top_db)
    merged = merge_close(raw, int(merge_gap_s * sr))
    for start, end in merged:
        dur = (end - start) / sr
        if dur < min_s:
            continue
        if dur > max_s:
            step = int(max_s * sr)
            c = start
            while c < end:
                ce = min(c + step, end)
                if (ce - c) / sr < min_s:
                    break
                yield c, ce
                c = ce
        else:
            yield start, end


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True, help="root dir of audiobook folders")
    ap.add_argument("--out", required=True, help="output dataset dir")
    ap.add_argument("--centroid", required=True, help="target-voice centroid .npy")
    ap.add_argument("--min-sim", type=float, default=0.84,
                    help="min cosine sim to centroid to keep a segment")
    ap.add_argument("--sr", type=int, default=48000)
    ap.add_argument("--min-s", type=float, default=3.5)
    ap.add_argument("--max-s", type=float, default=10.0)
    ap.add_argument("--top-db", type=float, default=38.0)
    ap.add_argument("--merge-gap-s", type=float, default=0.4)
    ap.add_argument("--target-lufs", type=float, default=-23.0)
    ap.add_argument("--peak-db", type=float, default=-3.0)
    ap.add_argument("--books", default="", help="comma list of book prefixes (e.g. 01,02); empty=all")
    ap.add_argument("--limit", type=int, default=0, help="stop after N source files (0=all)")
    args = ap.parse_args()

    import librosa, soundfile as sf, pyloudnorm as pyln
    from resemblyzer import VoiceEncoder

    centroid = np.load(args.centroid).astype(np.float32)
    centroid = centroid / np.linalg.norm(centroid)
    enc = VoiceEncoder("cpu", verbose=False)
    meter = pyln.Meter(args.sr)

    src = Path(args.src)
    out = Path(args.out)
    wav_dir = out / "wav"
    wav_dir.mkdir(parents=True, exist_ok=True)

    want = set(b.strip() for b in args.books.split(",") if b.strip())
    books = sorted(d for d in src.iterdir() if d.is_dir())

    manifest = out / "manifest.csv"
    mf = open(manifest, "w", newline="")
    w = csv.writer(mf)
    w.writerow(["seg", "book", "chapter", "start_s", "end_s", "dur", "sim", "lufs_in", "transcript"])

    n_files = kept = rejected_sim = rejected_q = 0
    kept_s = 0.0
    for bk in books:
        prefix = bk.name.split(" - ")[0]
        if want and prefix not in want:
            continue
        for mp3 in sorted(bk.glob("*.mp3")):
            if args.limit and n_files >= args.limit:
                break
            n_files += 1
            try:
                audio = decode_mono(mp3, args.sr)
            except Exception as e:
                print(f"[skip] {mp3.name}: {e}", file=sys.stderr)
                continue
            stem = f"{prefix}_{mp3.stem}".replace(" ", "_")
            idx = 0
            for s, e in segments(audio, args.sr, args.top_db, args.min_s,
                                 args.max_s, args.merge_gap_s):
                seg = audio[s:e]
                peak = float(np.max(np.abs(seg))) if len(seg) else 0.0
                if peak >= 0.999 or peak < 1e-3:   # clipped or ~silent
                    rejected_q += 1
                    continue
                emb16 = librosa.resample(seg, orig_sr=args.sr, target_sr=16000)
                emb = enc.embed_utterance(emb16)
                sim = float(np.dot(emb / np.linalg.norm(emb), centroid))
                if sim < args.min_sim:
                    rejected_sim += 1
                    continue
                try:
                    lufs = meter.integrated_loudness(seg)
                    norm = pyln.normalize.loudness(seg, lufs, args.target_lufs)
                except Exception:
                    rejected_q += 1
                    continue
                p = float(np.max(np.abs(norm)))
                ceil = 10 ** (args.peak_db / 20)
                if p > ceil:
                    norm = norm * (ceil / p)
                name = f"{stem}_{idx:05d}.wav"
                sf.write(str(wav_dir / name), norm.astype(np.float32), args.sr)
                dur = (e - s) / args.sr
                w.writerow([name, prefix, mp3.name, f"{s/args.sr:.2f}",
                            f"{e/args.sr:.2f}", f"{dur:.2f}", f"{sim:.3f}",
                            f"{lufs:.1f}", ""])
                kept += 1
                kept_s += dur
                idx += 1
            print(f"[{prefix}] {mp3.name}: +{idx} kept  "
                  f"(running: {kept} segs, {kept_s/60:.1f} min)", flush=True)
        if args.limit and n_files >= args.limit:
            break

    mf.close()
    print(f"\nDONE: {kept} segments / {kept_s/60:.1f} min kept from {n_files} files")
    print(f"  rejected by speaker-gate (<{args.min_sim} sim): {rejected_sim}")
    print(f"  rejected by quality (clip/silence/lufs): {rejected_q}")
    print(f"  manifest: {manifest}")


if __name__ == "__main__":
    main()
