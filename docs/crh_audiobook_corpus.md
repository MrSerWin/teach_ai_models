# Crimean Tatar audiobook corpus — Elvide Bekirova (TRK Millet)

Single source of truth for the TRK Millet Crimean-Tatar audiobooks: what audio
we have, its quality, the matching book **texts** (for TTS), and processing
status. Built so we never have to re-analyze the raw books from scratch.

> **Mirror:** a copy lives at the data root as
> `/Volumes/T9/Drive/MyD/Books/Qirimtatar/_AUDIOBOOK_CORPUS_README.md` so it's
> obvious where to dig when browsing the library. Keep the two in sync — after
> editing this one: `cp docs/crh_audiobook_corpus.md '/Volumes/T9/Drive/MyD/Books/Qirimtatar/_AUDIOBOOK_CORPUS_README.md'`

- **Raw audio:** `/Volumes/T9/Drive/MyD/Books/Qirimtatar/trkmillet-audiobooks/`
  (source: https://trkmillet.ru/specials/audio-knigi/ ; re-scrapable via that
  folder's `scrape.py`; audio metadata in its `INDEX.json` / `INDEX.md`)
- **Book texts:** `/Volumes/T9/Drive/MyD/Books/Qirimtatar/` (flat, mixed formats)
- **Processed datasets + scripts:** this repo (see [Artifacts](#artifacts)).

## Key facts (verified, not from metadata)

- **One narrator across all 11 books / 28h: Elvide Bekirova** (adult female).
  Verified acoustically with resemblyzer speaker embeddings — min cosine **0.876**
  across 260 clips, agglomerative clustering finds no second speaker. So it is
  **one voice → one RVC model**; no voice-mixing risk. (Metadata `narrator`
  field also uniformly says so, but we did not trust the scrape — we measured.)
- **Clean solo narration, no music bed.** Demucs probe: mid-narration music stem
  at −50…−67 dB (= silence); only the **intro/outro jingle** carries music
  (voice−music gap ~2–3 dB there). So "remove music" = trim jingles + drop the
  few leftover non-voice segments, **not** demucs the whole 28h.
- **Bandwidth 11.5–13.8 kHz** even on the 1957 recordings — not telephone-band;
  fine for 40k RVC and 22–24k TTS.

## Per-book table

Durations in minutes. `clean` = kept after speaker-gate + declip/normalize.
`sim` = median cosine to the Elvide voice centroid (higher = purer timbre).
`text` = Crimean-Tatar source text status for TTS (see legend below).

| # | Author | Work | Year | Ch | raw | clean | ret% | segs | sim | BW | text |
|---|--------|------|------|----|-----|-------|------|------|-----|-----|------|
| 01 | Ş. Alâdin | Çauş oğlu (Чауш огълу) | 1957 | 9 | 140 | 71 | 51% | 580 | 0.924 | 12.0k | 🟢 digital (Lat) |
| 02 | Ş. Alâdin | Teselli (Теселли) | 1957 | 11 | 176 | 43 | 24% | 364 | 0.926 | 12.3k | 🟢 digital (Lat+Cyr) |
| 03 | Çerkez-Ali | Yeşil dalğalar | 1976 | 9 | 102 | 53 | 52% | 425 | 0.932 | 13.5k | 🔴 RU translation only |
| 04 | Çerkez-Ali | Doğmuşlar (Родные) | 1988 | 6 | 49 | 36 | 74% | 256 | 0.932 | 13.8k | 🔴 not found |
| 05 | Çerkez-Ali | Sabalar quçağında 1 | 1973 | 14 | 212 | 103 | 49% | 848 | 0.935 | 12.6k | 🔴 not found |
| 06 | Çerkez-Ali | Sabalar quçağında 2 | 1973 | 19 | 250 | 147 | 59% | 1057 | 0.935 | 11.5k | 🔴 not found |
| 07 | Çerkez-Ali | Sabalar quçağında 3 | 1973 | 13 | 206 | 161 | 78% | 1095 | 0.921 | 13.4k | 🔴 not found |
| 08 | Çerkez-Ali | Sabalar quçağında 4 | 1973 | 9 | 123 | 116 | 94% | 731 | 0.929 | 13.2k | 🔴 not found |
| 09 | U. Edemova | Baş yazısı 1 | 1981 | 20 | 213 | 203 | 96% | 1304 | 0.940 | 11.8k | 🟡 scanned (OCR) |
| 10 | U. Edemova | Baş yazısı 2 | 1981 | 9 | 118 | 99 | 84% | 612 | 0.941 | 13.8k | 🟡 scanned (OCR) |
| 11 | U. Edemova | Baş yazısı 3 | 1981 | 11 | 113 | 60 | 53% | 391 | 0.943 | 12.1k | 🟡 scanned (OCR) |
| **Σ** | | | | **130** | **1702** | **1093** | **64%** | **7663** | — | — | |

Totals: **raw 28.4h → clean 18.2h**, 7663 segments, one speaker.
Per author clean: **U. Edemova 6.0h** (best quality), Çerkez-Ali 10.3h, Ş. Alâdin 1.9h.

Text legend: 🟢 digital Crimean-Tatar text (ready to align) · 🟡 scanned CT text
(needs OCR) · 🔴 no CT text (needs ASR, or find the book).

## Book-text files (in `/Volumes/T9/Drive/MyD/Books/Qirimtatar/`)

| audio # | text file | format | script | words | usable |
|---|---|---|---|---|---|
| 01 | `Shamil Aladin - Chaush oghlu lat.fb2` (+`.pdf`) | fb2 | Latin | ~15,910 | 🟢 extract now |
| 01 | `ŞAMİL ALÂDİN. Çauş Oğlu . Qırımtatar Tilinde.pdf` | pdf | Latin | — | alt |
| 01 | `ШАМИЛЬ АЛЯДИН. Сын Чавуша … Перевод На Русский.pdf` | pdf | RU | — | translation |
| 02 | `Shamil Aladin - Teselli lat.fb2` (+`.pdf`) | fb2 | Latin | ~19,252 | 🟢 extract now |
| 02 | `ШАМИЛЬ АЛЯДИН. Teselli . Kiril … Qırımtatar Tilinde.pdf` | pdf | Cyrillic | — | alt |
| 02 | `tg2026/kirimakademiyasi/8735_shamil__aladin_…_teselli_2020.pdf` | pdf | ? | — | alt ed. |
| 03 | `Черкез Али Зеленые волны 1982 год.pdf` | pdf | RU | — | 🔴 translation, not for align |
| 09–11 | `bash yazisi.pdf` (102 pp) + `bash yazisi.docx` | pdf/docx | scanned img | 0 extractable | 🟡 **OCR required** |

Not found (searched author + title, Latin & Cyrillic): Çerkez-Ali **Sabalar
quçağında** (05–08, the biggest chunk ~9h raw) and **Doğmuşlar** (04). The
`tg2026/kirimakademiyasi/` folder has many *other* Çerkez-Ali books (Yer nefesi,
Pişkinlik, Ruçyi…) but none of these four works. Worth a wider disk search or
sourcing the printed editions before committing to align these.

## Transcript strategy for TTS (per book)

TTS needs text aligned to audio. Three tiers, best first:

1. **Digital text → forced alignment** (01, 02): extract fb2 → normalize →
   align audio↔text with `robinhad/wav2vec2-xls-r-300m-crh` (or MFA). Gold quality.
2. **Scanned text → OCR → align** (09–11, the best 6h audio): OCR the 102-page
   `bash yazisi` scan (Tesseract; pick Cyrillic vs Turkish model per the scan's
   script — TBD), clean, then align as tier 1. High ROI — unlocks the top voice.
3. **No text → ASR** (03–08): transcribe with our own
   `servinosmanov/whisper-large-v3-crh`, agreement-filter against robinhad
   wav2vec2, keep only high-confidence segments. Lower purity but usable.

Even tier 3 makes all 18.2h usable for TTS; tiers 1–2 give the cleanest ~8h.
See [[crh_resources]] for the ASR/alignment/LM assets and [[crh_tts_journey]].

## Artifacts (this repo)

```
scripts/rvc/build-voice-centroid.py     speaker centroid + reader-count verify
scripts/rvc/prep-audiobook.py           decode→VAD-slice→speaker-gate→normalize→manifest
scripts/rvc/curate-rvc-subset.py        pick best ~Nmin, balanced across books
experiments/04_rvc_voice_clone/
  characters/06_elvide.yaml             RVC training preset (Ov2Super 40k)
  data/elvide_crh/                      FULL clean pool: 7663 wav + manifest.csv + centroid.npy (18.2h)
  data/elvide_rvc/                      curated RVC set: 513 wav + manifest.csv (60min, sim≥0.92)
```
`data/` is gitignored (regenerable). Re-run end-to-end:
```bash
python3 scripts/rvc/build-voice-centroid.py --src <audiobooks> --out <ds>/centroid.npy
python3 scripts/rvc/prep-audiobook.py --src <audiobooks> --out <ds> --centroid <ds>/centroid.npy
python3 scripts/rvc/curate-rvc-subset.py --pool <ds> --out <ds>_rvc --minutes 60 --min-sim 0.92
```

## Status

- ✅ Audio studied, single reader verified, jingles/music removed, 18.2h clean.
- ✅ RVC dataset curated (60min) — ready to train (`06_elvide.yaml`). **Training on hold.**
- ☐ TTS: transcripts pending (align 01/02, OCR+align 09–11, ASR 03–08) + optional denoise.
