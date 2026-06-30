#!/usr/bin/env python3
"""Forced-align one book and cut it into TTS-ready segments.

Pipeline per book:
  1. Read cleaned sentences (one per line) from prepare_text.py output.
  2. Forced-align the full transcript to the audio with the MMS CTC model
     (ONNX) -> per-word timestamps + per-word CTC log-prob.
  3. Pack consecutive words into segments of TARGET_DUR (4-12 s), preferring
     to close on sentence boundaries that sit in a silence gap; cut points are
     centred in the inter-word silence so clips never clip a word.
  4. Export 22.05 kHz mono wavs + a per-segment JSONL with QC metrics.

Gating/quarantine decisions are intentionally deferred to qc_report.py, which
reads the JSONL — so thresholds can be retuned without re-running alignment.

Usage:
    align_segment.py <audio_file> <clean_txt> <slug> <out_root>
"""
import json
import re
import sys
from pathlib import Path

import librosa
import numpy as np
import onnxruntime
import soundfile as sf
from ctc_forced_aligner import (
    Tokenizer, ensure_onnx_model, generate_emissions, get_alignments,
    get_spans, postprocess_results, MODEL_URL,
)

import romanize
from romanize import build_alignment_inputs
from translit import translit_batch

# --- segmentation / output config ------------------------------------------
SR_OUT = 22050           # XTTS / Coqui target sample rate
MIN_DUR = 4.0            # never emit a clip shorter than this (merge instead)
TARGET_DUR = 7.0         # aim for ~this length
MAX_DUR = 12.0           # hard ceiling
MIN_GAP = 0.12           # silence (s) that qualifies as a clean cut point
PAD = 0.06              # min padding kept around a clip edge (s)
MAX_PAD = 0.30           # max silence pulled into a clip edge (s)
PEAK = 0.95             # peak-normalisation target (linear)
FPS = 50                 # CTC frames per second (20 ms stride)
WEAK_WORD = -2.0         # per-word mean log-prob below this = likely misread/reorder

_SESSION = None
_TOK = None


def _model():
    global _SESSION, _TOK
    if _SESSION is None:
        mp = Path.home() / "ctc_forced_aligner" / "model.onnx"
        ensure_onnx_model(str(mp), MODEL_URL)
        _SESSION = onnxruntime.InferenceSession(str(mp))
        _TOK = Tokenizer()
    return _SESSION, _TOK


def _align_core(audio_sub, words_sub):
    """Align one audio span to its word list; times relative to the span start."""
    sess, tok = _model()
    emissions, stride = generate_emissions(sess, audio_sub, batch_size=8)
    tokens_starred, text_starred = build_alignment_inputs(words_sub)
    segments, scores, blank = get_alignments(emissions, tokens_starred, tok)
    spans = get_spans(tokens_starred, segments, blank)
    return postprocess_results(text_starred, spans, stride, scores)


# Books longer than this are aligned in sequential windows: the CTC alignment
# DP allocates ~frames*tokens and aborts (std::length_error) on very long books.
CHUNK_OVER_S = 1700
CHUNK_WORDS = 400       # words per window — keep well below the window's speech
CHUNK_WINDOW_S = 600    # audio window per chunk; must exceed the chunk's speech
CHUNK_OVERLAP_S = 8     # lead-in so the first word of a chunk has context
CHUNK_TAIL = 25         # trailing words per window left uncommitted (re-aligned)
CHUNK_MIN_REMAIN_S = 5  # stop if less audio than this remains (text > audio)


def align_words(audio16k, full_text):
    """Return list of dicts {text,start,end,score} aligned to the transcript.

    Long books are aligned in sequential windows (the CTC DP aborts on very long
    inputs). The last few words of a window are unreliable — the <star> wildcard
    parks them at the window edge — so we commit all but the last CHUNK_TAIL
    words and re-align that tail in the next window, taking the cursor from a
    reliable interior word. If the audio runs out before the text (over-long
    transcript), the unmatched tail words are simply dropped.
    """
    words_txt = full_text.split()
    total_s = len(audio16k) / 16000
    if total_s <= CHUNK_OVER_S:
        return _align_core(audio16k, words_txt)

    sr, n, i, cursor, out = 16000, len(words_txt), 0, 0.0, []
    while i < n:
        if total_s - cursor < CHUNK_MIN_REMAIN_S:
            print(f"    audio exhausted at {cursor:.0f}s; dropping {n - i} tail words", flush=True)
            break
        chunk = words_txt[i:i + CHUNK_WORDS]
        last = i + len(chunk) >= n
        ws = max(0, int((cursor - CHUNK_OVERLAP_S) * sr))
        we = len(audio16k) if last else min(len(audio16k), int((cursor + CHUNK_WINDOW_S) * sr))
        res = _align_core(audio16k[ws:we], chunk)
        if not res:
            break
        off = ws / sr
        for r in res:
            r["start"] += off
            r["end"] += off
        commit = len(res) if last else max(1, len(res) - CHUNK_TAIL)
        out.extend(res[:commit])
        cursor = res[commit - 1]["end"]
        i += commit
        print(f"    chunk →{i}/{n} words, audio→{cursor:.0f}s", flush=True)
    return out


def pack_segments(words, sent_end):
    """Greedy word packer. Returns list of (start_idx, end_idx) inclusive."""
    n = len(words)
    gaps = [words[i + 1]["start"] - words[i]["end"] for i in range(n - 1)] + [1e9]
    segs = []
    i = 0
    while i < n:
        best_j, best_score = i, -1e9
        j = i
        while j < n:
            dur = words[j]["end"] - words[i]["start"]
            if dur > MAX_DUR and j > i:
                break
            # Candidate must reach MIN_DUR (unless it's the very last word).
            if dur >= MIN_DUR or j == n - 1:
                s = -abs(dur - TARGET_DUR) * 0.15
                if j in sent_end:
                    s += 3.0
                if gaps[j] >= MIN_GAP:
                    s += 1.0
                if s > best_score:
                    best_score, best_j = s, j
            j += 1
        segs.append((i, best_j))
        i = best_j + 1
    # Merge a too-short tail into the previous segment.
    if len(segs) >= 2:
        a, b = segs[-1]
        if words[b]["end"] - words[a]["start"] < MIN_DUR:
            segs[-2] = (segs[-2][0], b)
            segs.pop()
    return segs


def cut_bounds(words, a, b):
    """Silence-centred [start,end] seconds for the segment words[a..b]."""
    n = len(words)
    if a > 0:
        mid = (words[a - 1]["end"] + words[a]["start"]) / 2
        start = min(max(mid, words[a]["start"] - MAX_PAD), words[a]["start"] - PAD)
    else:
        start = max(0.0, words[a]["start"] - PAD)
    if b < n - 1:
        mid = (words[b]["end"] + words[b + 1]["start"]) / 2
        end = max(min(mid, words[b]["end"] + MAX_PAD), words[b]["end"] + PAD)
    else:
        end = words[b]["end"] + PAD
    return start, end


def main():
    audio_path, clean_txt, slug, out_root = sys.argv[1:5]
    out_root = Path(out_root)
    wav_dir = out_root / "dataset" / "wavs"
    work_dir = out_root / "work" / slug
    wav_dir.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=True)

    sentences = [l.strip() for l in Path(clean_txt).read_text(encoding="utf-8").splitlines() if l.strip()]
    full_text = " ".join(sentences)
    words_txt = full_text.split()
    sent_end = set()
    idx = 0
    for s in sentences:
        idx += len(s.split())
        sent_end.add(idx - 1)

    # Books may be Cyrillic (most) or Latin script (e.g. the verse PDF). The
    # transliterator auto-detects direction, so we always derive the Latin form
    # and route alignment romanization through it (folding къ->q etc. for the
    # MMS model). For an already-Latin book the Latin form is the source itself.
    book_is_cyr = bool(re.search(r"[а-яёА-ЯЁ]", full_text))
    uniq = sorted(set(words_txt))
    latin = translit_batch(uniq) if book_is_cyr else uniq
    lat_map = dict(zip(uniq, latin))
    romanize.CRH_TRANSLITERATE = lambda t: lat_map.get(t, t)

    print(f"[{slug}] loading audio…", flush=True)
    audio16k = librosa.load(audio_path, sr=16000, mono=True)[0].astype(np.float32)
    print(f"[{slug}] aligning {len(words_txt)} words / {len(audio16k)/16000:.0f}s…", flush=True)
    res = align_words(audio16k, full_text)
    # Chunked alignment may stop early if the transcript outruns the audio;
    # res then covers the first len(res) words in order.
    assert len(res) <= len(words_txt), f"more results than words {len(res)} > {len(words_txt)}"
    if len(res) < len(words_txt):
        print(f"[{slug}] aligned {len(res)}/{len(words_txt)} words "
              f"({len(words_txt)-len(res)} unmatched tail dropped)", flush=True)
    # Attach original orthographic token to each aligned word, plus a
    # length-normalised per-word score (mean frame log-prob). Re-ordered or
    # misread words break monotonic CTC alignment and show up as a few very
    # low per-word scores even when the clip average still looks fine.
    words = []
    for k in range(len(res)):
        wframes = max((res[k]["end"] - res[k]["start"]) * FPS, 1)
        # Punctuation/dash tokens romanize to <2 chars and always score badly
        # (they are absorbed by the CTC <star> wildcard); they are not real
        # words, so exclude them from the misread/reorder detector.
        is_real = len(romanize.romanize_token(words_txt[k])) >= 2
        words.append({"text": words_txt[k], "start": res[k]["start"],
                      "end": res[k]["end"], "score": res[k]["score"],
                      "wscore": res[k]["score"] / wframes, "real": is_real})

    segs = pack_segments(words, sent_end)
    print(f"[{slug}] {len(segs)} segments; cutting at {SR_OUT} Hz…", flush=True)

    audio_hi = librosa.load(audio_path, sr=SR_OUT, mono=True)[0].astype(np.float32)
    jsonl = work_dir / "segments.jsonl"
    rows = []
    for n, (a, b) in enumerate(segs, 1):
        start, end = cut_bounds(words, a, b)
        clip = audio_hi[int(start * SR_OUT):int(end * SR_OUT)]
        if clip.size == 0:
            continue
        peak = float(np.max(np.abs(clip)))
        if peak > 0:
            clip = clip * (PEAK / peak)
        clip_id = f"{slug}_{n:04d}"
        sf.write(wav_dir / f"{clip_id}.wav", clip, SR_OUT, subtype="PCM_16")

        text = " ".join(words[k]["text"] for k in range(a, b + 1))
        span = words[b]["end"] - words[a]["start"]
        frames = max(span * FPS, 1)
        seg_score = sum(words[k]["score"] for k in range(a, b + 1)) / frames
        wscores = [words[k]["wscore"] for k in range(a, b + 1) if words[k]["real"]]
        if not wscores:
            wscores = [0.0]
        nchars = len(text.replace(" ", ""))
        rows.append({
            "id": clip_id, "book": slug, "text": text,
            "wav": f"wavs/{clip_id}.wav",
            "start": round(start, 3), "end": round(end, 3),
            "dur": round(end - start, 3),
            "score": round(seg_score, 4),
            "min_wscore": round(min(wscores), 3),
            "n_weak": sum(1 for w in wscores if w < WEAK_WORD),
            "char_rate": round(nchars / span, 2) if span > 0 else 0,
            "has_digit": any(c.isdigit() for c in text),
            "n_words": b - a + 1,
        })

    # Both dataset variants per clip (context-aware, one batch). `text` is the
    # source script; the transliterator yields the other script.
    other = translit_batch([r["text"] for r in rows])
    for r, o in zip(rows, other):
        r["text_cyr"], r["text_lat"] = (r["text"], o) if book_is_cyr else (o, r["text"])

    with open(jsonl, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    tot = sum(r["dur"] for r in rows)
    print(f"[{slug}] done: {len(rows)} clips, {tot/60:.1f} min -> {jsonl}", flush=True)


if __name__ == "__main__":
    main()
