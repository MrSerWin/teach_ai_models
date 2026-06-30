# 06 — TTS dataset builder (Sevil / Crimean Tatar audiobooks)

Turns long audiobook recordings + their full transcripts into an LJSpeech-style
single-speaker TTS dataset (for XTTS / Coqui fine-tuning), by **forced
alignment** — we already have the ground-truth text, so we never depend on weak
`crh` ASR.

## Approach

1. **Text prep** (`prepare_text.py`) — extract `.txt` / `.odt` (pandoc) / `.pdf`
   (pdftotext), un-wrap hard line breaks, keep paragraph/title boundaries,
   split into sentences. Output keeps the **original Cyrillic orthography** —
   that is the dataset text.
2. **Forced alignment** (`align_segment.py`) — Meta **MMS** CTC model (ONNX, via
   `ctc-forced-aligner`) aligns the transcript to the audio and returns
   per-word timestamps + per-word CTC log-prob. Cyrillic is romanized only to
   feed the acoustic model (see `romanize.py`); the dataset text is unaffected.
3. **Segmentation** — words are packed into **4–12 s** clips (target ~7 s),
   preferring to close on sentence boundaries that sit in a silence gap; cut
   points are centred in inter-word silence so no word is clipped. Short
   sentences are merged, never emitted alone. Clips are exported at **22.05 kHz
   mono**, peak-normalised.
4. **QC / verification** (`qc_report.py`) — each clip carries a mean per-frame
   CTC log-prob (`score`, a direct audio↔text match measure) and a `char_rate`
   (chars/s). Clips that match poorly, have implausible speaking rate, run too
   long, or contain digits are **quarantined** (moved to `metadata.review.csv`),
   not silently kept. Thresholds live in `qc_report.py` and can be retuned
   without re-running alignment.

## Output (`dataset/`)

```
wavs/<slug>_NNNN.wav      22.05 kHz mono clips (shared by both variants)
metadata.cyr.csv          id|text|text     (kept clips, Cyrillic — LJSpeech)
metadata.lat.csv          id|text|text     (kept clips, Latin crh — LJSpeech)
metadata.review.csv       id|reason|text   (quarantined — fix or drop)
segments.jsonl            every clip with full metrics + keep flag
QC_REPORT.md              summary + per-book table
```

Two transcript variants over the **same** audio clips, so you can train and
compare Cyrillic vs Latin models. Latin uses the project's transliterator
(`StranslinService.js` via `translit.py`).

## Run

```bash
conda activate crh_align               # ctc-forced-aligner, onnxruntime, librosa, unidecode
python scripts/run_all.py              # all books  (--only slug  /  --skip-existing)
python scripts/qc_report.py .          # gate + report (re-runnable, fast)
```

## Romanization (`romanize.py`)

Alignment-only. The generic `unidecode` default mis-handles crh digraphs
(`къ→k` instead of `q`, `гъ→g`, `нъ→n`, `дж→dzh`). To use a higher-quality
crh Cyrillic→Latin transliterator, set `CRH_TRANSLITERATE` to a `str->str`
function in `romanize.py`; folding to the MMS `a-z+'` vocab is automatic. This
only improves alignment accuracy — it never changes the dataset text.

## Notes / known outliers

- **Солнечная система** — Latin-script (Qırımtatar Latin) children's verse from
  a PDF; expect more quarantine (verse line breaks, metadata header). Review it
  separately.
- Digits are quarantined for manual/LLM expansion to spoken form (num2words has
  no `crh`); good task to run through Gemini/Grok on the `has_digit` lines.
- Build is CPU-only and local (no API/GPU needed); full corpus ≈ tens of minutes.
```
