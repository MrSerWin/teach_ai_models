#!/usr/bin/env python3
"""Build a target-voice centroid (resemblyzer embedding) for the speaker gate.

The centroid is the average voice embedding of the target speaker, used by
prep-audiobook.py to keep only that speaker's segments (dropping music
jingles, announcer intros, guest voices).

It also doubles as a speaker-verification tool: run it on a whole corpus to
confirm it's a single reader (report the min/mean cosine across books). That's
how we verified the TRK Millet audiobooks are all one narrator before training.

Method:
  - sample 2 clean windows (skip intro jingle) per source file, mono 16k
  - resemblyzer embed each
  - iterative trimmed mean: drop clips < 0.90 to the running centroid, recompute
  - save centroid.npy; print per-book similarity matrix + outlier clips

Usage:
  python3 scripts/rvc/build-voice-centroid.py \
    --src '/path/to/audiobooks' \
    --out experiments/04_rvc_voice_clone/data/elvide_crh/centroid.npy
"""
import argparse, subprocess, tempfile, os
from pathlib import Path
import numpy as np


def window(src, ss, dur=25):
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
        tmp = tf.name
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(ss), "-i", str(src),
                    "-t", str(dur), "-ac", "1", "-ar", "16000", tmp], check=True)
    return tmp


def dur_of(src):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", str(src)], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--skip-intro", type=float, default=90.0)
    args = ap.parse_args()

    from resemblyzer import VoiceEncoder, preprocess_wav
    enc = VoiceEncoder("cpu", verbose=False)

    src = Path(args.src)
    books = sorted(d for d in src.iterdir() if d.is_dir())
    embs, meta = [], []
    for bk in books:
        prefix = bk.name.split(" - ")[0]
        for mp3 in sorted(bk.glob("*.mp3")):
            d = dur_of(mp3)
            if d < args.skip_intro + 35:
                continue
            for ss in (args.skip_intro, max(args.skip_intro, d * 0.5)):
                if ss + 25 > d:
                    continue
                tmp = window(mp3, ss)
                try:
                    embs.append(enc.embed_utterance(preprocess_wav(Path(tmp))))
                    meta.append(prefix)
                finally:
                    os.unlink(tmp)

    E = np.array(embs)
    En = E / np.linalg.norm(E, axis=1, keepdims=True)
    c = En.mean(0); c /= np.linalg.norm(c)
    for _ in range(3):
        keep = (En @ c) >= 0.90
        c = En[keep].mean(0); c /= np.linalg.norm(c)

    meta = np.array(meta)
    uniq = sorted(set(meta))
    means = np.array([En[meta == b].mean(0) for b in uniq])
    means = means / np.linalg.norm(means, axis=1, keepdims=True)
    sim = means @ means.T
    off = sim[~np.eye(len(uniq), dtype=bool)]
    print("per-book similarity: min={:.3f} mean={:.3f}".format(off.min(), off.mean()))
    print("=> {} reader(s): {}".format(
        "ONE" if off.min() > 0.80 else "MULTIPLE (min<0.80 — split before training!)",
        "all books consistent" if off.min() > 0.80 else "inspect the matrix"))

    out = Path(args.out); out.parent.mkdir(parents=True, exist_ok=True)
    np.save(out, c.astype(np.float32))
    print(f"saved {out}  (from {int((En @ c >= 0.90).sum())}/{len(En)} clean clips)")


if __name__ == "__main__":
    main()
