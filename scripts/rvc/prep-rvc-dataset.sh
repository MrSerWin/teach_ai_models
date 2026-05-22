#!/usr/bin/env bash
# Prepare an RVC training dataset from raw sources.
#
# Usage:
#   ./scripts/rvc/prep-rvc-dataset.sh <out-dir> <source>...
#
# Source forms:
#   - YouTube URL (single video or playlist)  — handled by yt-dlp
#   - Local .wav/.mp3/.m4a/.mp4/.webm file    — handled directly
#   - Local directory                          — recurses through audio files
#
# Pipeline per source:
#   download (yt-dlp) -> ffmpeg (mono, 48k, wav) -> audio-slicer (4-10s segments)
#   -> ffmpeg-normalize (-23 LUFS / -3 dB peak) -> <out-dir>/*.wav
#
# What you still must do manually:
#   1. UVR5 GUI: MDX-Net Voc FT -> DeNoise -> DeEcho-DeReverb
#      (run on the raw downloads BEFORE this script, or on its output before
#       training — your call. UVR's quality beats any CLI alternative.)
#   2. Audition every output WAV in Audacity/Reaper, delete trash (coughs,
#      other speakers, mistakes, music bleed). This is the single highest-ROI
#      step in dataset prep. Do not skip.
#
# Dependencies (Mac):
#   brew install yt-dlp ffmpeg
#   pip install librosa soundfile ffmpeg-normalize
#
# Shell note: zsh treats '?' as a glob — wrap YouTube share URLs in quotes
# or strip the '?si=...' tracker param:
#   ./prep-rvc-dataset.sh ./data/x "https://youtu.be/ID?si=TRACKER"
#   ./prep-rvc-dataset.sh ./data/x  https://youtu.be/ID
#
# YouTube cookies (recommended — bypasses 403/SABR streaming restrictions):
#   YT_COOKIES_BROWSER=safari ./prep-rvc-dataset.sh ./data/x <urls>
# Other values: chrome, firefox, edge, brave. yt-dlp will read your logged-in
# session from that browser. Required for many newer videos.
set -euo pipefail

if [ $# -lt 2 ]; then
  echo "usage: $0 <out-dir> <source>..." >&2
  exit 2
fi

OUT="$1"; shift
mkdir -p "$OUT"
RAW="$OUT/_raw"
SLICED="$OUT/_sliced"
mkdir -p "$RAW" "$SLICED"

# Sanity-check dependencies.
for cmd in yt-dlp ffmpeg ffmpeg-normalize; do
  command -v "$cmd" >/dev/null || { echo "[prep] missing: $cmd" >&2; exit 1; }
done
python3 -c "import librosa, soundfile" 2>/dev/null || \
  { echo "[prep] missing librosa/soundfile (pip install librosa soundfile)" >&2; exit 1; }

idx=0
for src in "$@"; do
  idx=$((idx + 1))
  case "$src" in
    http*youtube*|http*youtu.be*|http*://*)
      echo "[prep] yt-dlp: $src"
      YTDLP_OPTS=(--no-playlist-reverse
                  --extract-audio --audio-format wav --audio-quality 0
                  --output "$RAW/%(playlist_index)03d-%(id)s.%(ext)s"
                  --progress)
      [ -n "${YT_COOKIES_BROWSER:-}" ] && \
        YTDLP_OPTS+=(--cookies-from-browser "$YT_COOKIES_BROWSER")
      yt-dlp "${YTDLP_OPTS[@]}" "$src"
      ;;
    *)
      if [ -d "$src" ]; then
        echo "[prep] copying dir: $src"
        find "$src" -type f \( -iname '*.wav' -o -iname '*.mp3' -o -iname '*.m4a' \
                              -o -iname '*.mp4' -o -iname '*.mkv' -o -iname '*.webm' \
                              -o -iname '*.opus' -o -iname '*.flac' -o -iname '*.aac' \
                              -o -iname '*.mov' \) \
          -exec cp -n {} "$RAW/" \;
      elif [ -f "$src" ]; then
        echo "[prep] copying file: $src"
        cp -n "$src" "$RAW/"
      else
        echo "[prep] skipping unknown source: $src" >&2
      fi
      ;;
  esac
done

# Step 1: normalize everything to mono 48kHz WAV.
echo "[prep] -> mono 48k WAV"
mkdir -p "$RAW/wav"
shopt -s nullglob
raw_count=0
for f in "$RAW"/*; do
  [ -d "$f" ] && continue
  raw_count=$((raw_count + 1))
done
if [ "$raw_count" -eq 0 ]; then
  echo "[prep] ERROR: nothing in $RAW — no recognized source files found." >&2
  echo "[prep]        supported extensions: wav mp3 m4a mp4 mkv webm opus flac aac mov" >&2
  exit 1
fi
echo "[prep]    $raw_count source file(s) to transcode"
for f in "$RAW"/*; do
  [ -d "$f" ] && continue
  base=$(basename "${f%.*}")
  out="$RAW/wav/${base}.wav"
  [ -f "$out" ] && { echo "[prep]    skip (exists): $base.wav"; continue; }
  echo "[prep]    transcoding: $(basename "$f")"
  ffmpeg -hide_banner -loglevel error -y -i "$f" -ac 1 -ar 48000 "$out"
done

# Step 2: slice into 4-10s segments using librosa silence-split.
# Strategy: detect non-silent regions, MERGE regions separated by short
# breath pauses, then enforce 4-10s lengths. Avoids the trap where every
# inter-sentence pause fragments a monologue into sub-4s pieces.
echo "[prep] -> slicing"
python3 - <<PY
from pathlib import Path
import numpy as np
import librosa, soundfile as sf

SR = 48000
MIN_S = 4.0
MAX_S = 10.0
TOP_DB = 40             # >40 dB below peak = silence (looser than default cut)
MERGE_GAP_S = 0.4       # merge non-silent regions if gap < this (breath pauses)

src_dir = Path("$RAW/wav")
dst_dir = Path("$SLICED")
dst_dir.mkdir(exist_ok=True)

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

total_in_s = 0.0
total_out_s = 0.0
n = 0
for wav in sorted(src_dir.glob("*.wav")):
    audio, sr = librosa.load(str(wav), sr=SR, mono=True)
    total_in_s += len(audio) / sr

    raw_intervals = librosa.effects.split(audio, top_db=TOP_DB)
    intervals = merge_close(raw_intervals, int(MERGE_GAP_S * sr))

    for (start, end) in intervals:
        dur = (end - start) / sr
        if dur < MIN_S:
            continue
        # Split long stretches into ~MAX_S chunks at silence-free cuts.
        if dur > MAX_S:
            step = int(MAX_S * sr)
            for cstart in range(start, end, step):
                cend = min(cstart + step, end)
                # Keep the tail even if a bit short — better than dropping it.
                if (cend - cstart) / sr < MIN_S:
                    # try to extend backward so the tail has full MIN_S
                    if (end - cstart) / sr < MIN_S:
                        continue
                    cend = cstart + int(MIN_S * sr)
                out = dst_dir / f"{wav.stem}_{n:05d}.wav"
                sf.write(str(out), audio[cstart:cend], sr)
                total_out_s += (cend - cstart) / sr
                n += 1
        else:
            out = dst_dir / f"{wav.stem}_{n:05d}.wav"
            sf.write(str(out), audio[start:end], sr)
            total_out_s += dur
            n += 1

ret = 100 * total_out_s / total_in_s if total_in_s > 0 else 0
print(f"[slice] {n} segments  ({total_out_s/60:.1f} min from {total_in_s/60:.1f} min input — {ret:.0f}% retained)")
PY

# Step 3: loudness normalize to -23 LUFS / -3 dB peak.
echo "[prep] -> loudness normalize"
for f in "$SLICED"/*.wav; do
  base=$(basename "$f")
  out="$OUT/$base"
  [ -f "$out" ] && continue
  ffmpeg-normalize "$f" -nt ebu -t -23 --true-peak -3 -o "$out" -ar 48000 -f -q 2>/dev/null
done

count=$(find "$OUT" -maxdepth 1 -name '*.wav' | wc -l | tr -d ' ')
echo "[prep] done. $count segments in $OUT"
echo "[prep] NEXT STEPS:"
echo "       1) audition $OUT/*.wav, delete trash"
echo "       2) if not yet done: run UVR5 GUI on _raw/ (DeNoise + DeReverb)"
echo "       3) ./scripts/push-data.sh $OUT rvc/<character>"
