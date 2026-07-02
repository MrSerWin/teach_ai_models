#!/usr/bin/env python3
"""CTC-score the HF dataset (servinosmanov/tts-crh-sevil-fixed) the SAME way as
our exp-06 dataset, to find critical audio<->text mismatches (word shifts).

The HF clips are already segmented (audio + Latin transcription, 16 kHz). We
align each clip to its transcription with the MMS CTC aligner and compute the
same per-clip metrics (score, min_wscore, n_weak, char_rate). Suspects (bad-word
etc.) get their audio written out + a worst-first review HTML.

Usage: hf_audit.py <parquet_dir> <out_dir>
"""
import html
import io
import json
import sys
from pathlib import Path

import librosa
import numpy as np
import onnxruntime
import pyarrow.parquet as pq
import soundfile as sf
from ctc_forced_aligner import (
    Tokenizer, ensure_onnx_model, generate_emissions, get_alignments,
    get_spans, postprocess_results, MODEL_URL,
)

import romanize
from romanize import build_alignment_inputs, romanize_token

# HF transcription is already Latin crh → fold directly (skip unidecode).
romanize.CRH_TRANSLITERATE = lambda t: t

FPS = 50
WEAK_WORD = -2.0
BADWORD, BADWORD2, LOWMATCH, WEAKFRAC = -8.0, -11.0, -0.62, 0.30
CRAMMED, SPARSE = 15.0, 7.5

mp = Path.home() / "ctc_forced_aligner" / "model.onnx"
ensure_onnx_model(str(mp), MODEL_URL)
SESS, TOK = onnxruntime.InferenceSession(str(mp)), Tokenizer()


def score_clip(audio16k, text):
    words_txt = text.split()
    if not words_txt:
        return None
    emissions, stride = generate_emissions(SESS, audio16k, batch_size=8)
    tokens_starred, text_starred = build_alignment_inputs(words_txt)
    segments, scores, blank = get_alignments(emissions, tokens_starred, TOK)
    spans = get_spans(tokens_starred, segments, blank)
    res = postprocess_results(text_starred, spans, stride, scores)
    words = []
    for k in range(len(res)):
        wframes = max((res[k]["end"] - res[k]["start"]) * FPS, 1)
        is_real = len(romanize_token(words_txt[k])) >= 2
        words.append({"score": res[k]["score"], "wscore": res[k]["score"] / wframes,
                      "real": is_real, "start": res[k]["start"], "end": res[k]["end"]})
    if not words:
        return None
    span = words[-1]["end"] - words[0]["start"]
    frames = max(span * FPS, 1)
    seg_score = sum(w["score"] for w in words) / frames
    wsc = [w["wscore"] for w in words if w["real"]] or [0.0]
    nchars = len(text.replace(" ", ""))
    return {"score": round(seg_score, 4), "min_wscore": round(min(wsc), 3),
            "n_weak": sum(1 for w in wsc if w < WEAK_WORD),
            "char_rate": round(nchars / span, 2) if span > 0 else 0,
            "dur": round(len(audio16k) / 16000, 3), "n_words": len(words_txt)}


def tags(r):
    t = []
    if r["min_wscore"] < BADWORD2: t.append(("bad-word!!", 3))
    elif r["min_wscore"] < BADWORD: t.append(("bad-word", 2))
    if r["score"] < LOWMATCH: t.append(("low-match", 2))
    if r["n_words"] and r["n_weak"] / r["n_words"] > WEAKFRAC: t.append(("many-weak", 1))
    if r["char_rate"] > CRAMMED: t.append(("crammed", 1))
    if r["char_rate"] < SPARSE: t.append(("sparse", 1))
    return t


def main():
    import os
    pdir, out = Path(sys.argv[1]), Path(sys.argv[2])
    STEP = int(os.environ.get("STEP", "1"))   # process every STEP-th clip (sampling)
    (out / "wavs").mkdir(parents=True, exist_ok=True)
    mjsonl = open(out / "metrics.jsonl", "w", encoding="utf-8")  # persist incrementally
    allrows, suspects = [], []
    n = 0
    for split in ["train", "validation", "test"]:
        pf = pdir / f"{split}.parquet"
        if not pf.exists():
            continue
        df = pq.read_table(pf).to_pandas()
        for _, row in df.iterrows():
            n += 1
            if (n - 1) % STEP != 0:
                continue
            text = str(row["transcription"]).strip()
            wav, sr = sf.read(io.BytesIO(row["audio"]["bytes"]))
            if wav.ndim > 1:
                wav = wav.mean(axis=1)
            a16 = librosa.resample(wav.astype(np.float32), orig_sr=sr, target_sr=16000) if sr != 16000 else wav.astype(np.float32)
            m = score_clip(a16, text)
            if m is None:
                continue
            sid = f"hf_{Path(row['audio']['path']).stem}"
            m.update(id=sid, text=text)
            m["_tags"] = tags(m)
            allrows.append(m)
            mjsonl.write(json.dumps({k: v for k, v in m.items() if k != "_tags"}, ensure_ascii=False) + "\n")
            mjsonl.flush()
            if m["_tags"]:
                m["_susp"] = sum(w for _, w in m["_tags"]) + max(0, -m["min_wscore"]) / 10.0
                sf.write(out / "wavs" / f"{sid}.wav", a16, 16000, subtype="PCM_16")
                suspects.append(m)
            if len(allrows) % 50 == 0:
                print(f"...{len(allrows)} scored (n={n}), {len(suspects)} suspects", flush=True)
    suspects.sort(key=lambda r: -r["_susp"])

    # report
    kept = allrows
    def cnt(f): return sum(1 for r in kept if f(r))
    rep = [f"# CTC audit — dataset B (HF tts-crh-sevil-fixed, 16 kHz)\n",
           f"Scored clips: **{len(kept)}** · suspects: **{len(suspects)}** ({100*len(suspects)/max(1,len(kept)):.1f}%)\n",
           f"- bad-word (min_wscore<{BADWORD}): **{cnt(lambda r: r['min_wscore']<BADWORD)}** "
           f"(severe <{BADWORD2}: {cnt(lambda r: r['min_wscore']<BADWORD2)})",
           f"- low-match (score<{LOWMATCH}): {cnt(lambda r: r['score']<LOWMATCH)}",
           f"- crammed cr>{CRAMMED}: {cnt(lambda r: r['char_rate']>CRAMMED)} · sparse cr<{SPARSE}: {cnt(lambda r: r['char_rate']<SPARSE)}\n",
           "## Top 40 critical clips\n",
           "| id | tags | min_wscore | score | cr | dur | text |",
           "|---|---|---|---|---|---|---|"]
    for r in suspects[:40]:
        tg = ",".join(t for t, _ in r["_tags"])
        rep.append(f"| {r['id']} | {tg} | {r['min_wscore']:.1f} | {r['score']:.2f} | "
                   f"{r['char_rate']:.1f} | {r['dur']:.1f} | {html.escape(r['text'][:60])} |")
    (out / "HF_AUDIT_REPORT.md").write_text("\n".join(rep), encoding="utf-8")

    def hrow(r):
        tg = " ".join(f'<span class=t>{html.escape(t)}</span>' for t, _ in r["_tags"])
        return (f"<tr><td>{html.escape(r['id'])}</td>"
                f"<td>{tg}<br><small>minw {r['min_wscore']:.1f} · sc {r['score']:.2f} · "
                f"cr {r['char_rate']:.1f} · {r['dur']:.1f}s</small></td>"
                f"<td class=x>{html.escape(r['text'])}</td>"
                f"<td><audio controls preload=none src='wavs/{html.escape(r['id'])}.wav'></audio></td></tr>")
    body = "".join(hrow(r) for r in suspects)
    (out / "review_hf_audit.html").write_text(
        "<!doctype html><meta charset=utf-8><title>HF dataset CTC audit</title>"
        "<style>body{font:13px system-ui;margin:18px}table{border-collapse:collapse}"
        "td,th{padding:5px 7px;border:1px solid #ddd;vertical-align:top}.x{max-width:420px}"
        ".t{background:#fdd;border-radius:3px;padding:1px 5px;margin:1px;display:inline-block;font-size:11px}"
        "audio{width:230px}small{color:#777}</style>"
        f"<h2>HF tts-crh-sevil-fixed — {len(suspects)} critical clips (worst first, 16 kHz)</h2>"
        "<table><tr><th>id</th><th>flags</th><th>Latin text</th><th>audio</th></tr>"
        f"{body}</table>", encoding="utf-8")
    print(f"[done] scored={len(kept)} suspects={len(suspects)} -> {out/'review_hf_audit.html'}")


if __name__ == "__main__":
    main()
