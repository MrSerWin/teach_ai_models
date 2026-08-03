# Crimean Tatar audiobook corpus — Elvide Bekirova (TRK Millet)

Single source of truth for the TRK Millet Crimean-Tatar audiobooks: what audio
we have, its quality, the matching book **texts** (for TTS), and processing
status. Built so we never have to re-analyze the raw books from scratch.
All other raw speech/text sources are registered in [[crh_dataset_sources]].

> **Mirror:** a copy lives at the data root as
> `/Volumes/T9/AnaYurt/Books/Qirimtatar/_AUDIOBOOK_CORPUS_README.md` so it's
> obvious where to dig when browsing the library. Keep the two in sync — after
> editing this one: `cp docs/crh_audiobook_corpus.md '/Volumes/T9/AnaYurt/Books/Qirimtatar/_AUDIOBOOK_CORPUS_README.md'`

- **Raw audio:** `/Volumes/T9/AnaYurt/Books/Qirimtatar/sources/trkmillet/`
  (source: https://trkmillet.ru/specials/audio-knigi/ ; re-scrapable via that
  folder's `scrape.py`; audio metadata in its `INDEX.json` / `INDEX.md`)
- **Book texts:** `/Volumes/T9/AnaYurt/Books/Qirimtatar/` (flat, mixed formats)
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
| 03 | Çerkez-Ali | Yeşil dalğalar | 1976 | 9 | 102 | 53 | 52% | 425 | 0.932 | 13.5k | 🟢 digital (Cyr) |
| 04 | Çerkez-Ali | Doğmuşlar (Родные) | 1988 | 6 | 49 | 36 | 74% | 256 | 0.932 | 13.8k | 🟢 digital (Cyr) |
| 05 | Çerkez-Ali | Sabalar quçağında 1 | 1973 | 14 | 212 | 103 | 49% | 848 | 0.935 | 12.6k | 🔴 not found |
| 06 | Çerkez-Ali | Sabalar quçağında 2 | 1973 | 19 | 250 | 147 | 59% | 1057 | 0.935 | 11.5k | 🔴 not found |
| 07 | Çerkez-Ali | Sabalar quçağında 3 | 1973 | 13 | 206 | 161 | 78% | 1095 | 0.921 | 13.4k | 🔴 not found |
| 08 | Çerkez-Ali | Sabalar quçağında 4 | 1973 | 9 | 123 | 116 | 94% | 731 | 0.929 | 13.2k | 🔴 not found |
| 09 | U. Edemova | Baş yazısı 1 | 1981 | 20 | 213 | 203 | 96% | 1304 | 0.940 | 11.8k | 🟢 digital (Cyr) |
| 10 | U. Edemova | Baş yazısı 2 | 1981 | 9 | 118 | 99 | 84% | 612 | 0.941 | 13.8k | 🟢 digital (Cyr) |
| 11 | U. Edemova | Baş yazısı 3 | 1981 | 11 | 113 | 60 | 53% | 391 | 0.943 | 12.1k | 🟢 digital (Cyr) |
| **Σ** | | | | **130** | **1702** | **1093** | **64%** | **7663** | — | — | |

Totals: **raw 28.4h → clean 18.2h**, 7663 segments, one speaker.
Per author clean: **U. Edemova 6.0h** (best quality), Çerkez-Ali 10.3h, Ş. Alâdin 1.9h.

**Text coverage (2026-07-27): ~9.4h ready to align, 8.8h still open.**
- 🟢 **Ready (books 01,02,03,04,09,10,11 — ~9.4h)**: digital Crimean-Tatar text on
  disk, forced-alignment tier 1.
- 🔴 **Open (books 05–08, Sabalar quçağında ~8.8h)**: the standalone novel is still
  not sourced — see [Not found](#) below.

Text legend: 🟢 digital Crimean-Tatar text (ready to align) · 🟡 scanned CT text
(needs OCR) · 🔴 no CT text (needs ASR, or find the book).

## Book-text files (in `/Volumes/T9/AnaYurt/Books/Qirimtatar/`)

| audio # | text file | format | script | words | usable |
|---|---|---|---|---|---|
| 01 | `Shamil Aladin - Chaush oghlu lat.fb2` (+`.pdf`) | fb2 | Latin | ~15,910 | 🟢 extract now |
| 01 | `ŞAMİL ALÂDİN. Çauş Oğlu . Qırımtatar Tilinde.pdf` | pdf | Latin | — | alt |
| 01 | `ШАМИЛЬ АЛЯДИН. Сын Чавуша … Перевод На Русский.pdf` | pdf | RU | — | translation |
| 02 | `Shamil Aladin - Teselli lat.fb2` (+`.pdf`) | fb2 | Latin | ~19,252 | 🟢 extract now |
| 02 | `ШАМИЛЬ АЛЯДИН. Teselli . Kiril … Qırımtatar Tilinde.pdf` | pdf | Cyrillic | — | alt |
| 02 | `tg2026/kirimakademiyasi/8735_shamil__aladin_…_teselli_2020.pdf` | pdf | ? | — | alt ed. |
| 03 | `13.  Сайлама эсерлер Черкез-Али Аметов.pdf` (p.422 «Ешиль далгъалар») | pdf | Cyrillic | ~1,410 lines | 🟢 **extract now** |
| 03 | `Черкез Али Зеленые волны 1982 год.pdf` | pdf | RU | — | translation (reference only) |
| 04 | `13.  Сайлама эсерлер Черкез-Али Аметов.pdf` (p.464 «Догъмушлар») | pdf | Cyrillic | ~1,128 lines | 🟢 **extract now** |
| 09–11 | `14.  Сайлама эсерлер учт томлыкъ Урие Эдемова.pdf` (497 pp, vol.1 повести) | pdf | Cyrillic | ~49,700 words | 🟢 **extract now** |
| 09–11 | `QIRIM/crh_monocorpus` → «Baş yazısı» record | jsonl | Cyrillic | 363,918 chars | 🟢 alt (digital) |
| 09–11 | `bash yazisi.pdf` (102 pp) + `bash yazisi.docx` | pdf/docx | scanned img | 0 extractable | 🟡 superseded by the two above |

**Source of the digital texts (added 2026-07-27):** a batch of 18 CT-library PDFs
(originally in `~/Downloads/new books`, now filed into the library root). №13 =
Çerkez-Ali *Сайлама эсерлер* (2020 Gaspirali Mediamerkez, 529 pp, digital text
layer) — its ПОВЕСТЬЛЕР section holds **Yeşil dalğalar (p.422)** and **Doğmuşlar
(p.464)**, closing books 03/04. №14 = Üriye Edemova *Сайлама эсерлер, 3 vols*
(497 pp) — the digital source for **Baş yazısı** (books 09–11), also mirrored in
`QIRIM/crh_monocorpus` on Hugging Face. See the batch list at the bottom.

Still not found (searched author + title, Latin & Cyrillic): Çerkez-Ali **Sabalar
quçağında** (books 05–08, the biggest chunk ~8.8h clean). It is a full-length
*roman* (1973), so it did **not** appear in the 2020 selected-works anthology
(№13, which carries only the shorter повести). `QIRIM/crh_monocorpus` has other
Çerkez-Ali works (Köz nurlarım 1985, Bizim Nikita) but not this one. Next moves:
ask the qirimca / `crimeantatar_corpora` project directly, or source the printed
1973 edition, before committing to align these.

## Transcript strategy for TTS (per book)

TTS needs text aligned to audio. Three tiers, best first:

1. **Digital text → forced alignment** (01, 02, 03, 04, 09, 10, 11 — ~9.4h):
   extract from fb2 (01/02) or the batch PDFs №13/№14 (03/04/09–11) → normalize
   Cyrillic↔Latin → align audio↔text with `robinhad/wav2vec2-xls-r-300m-crh`
   (or MFA). Gold quality. This is now the path for 7 of 11 books.
2. **No text → ASR** (05–08, Sabalar quçağında ~8.8h): until the novel is
   sourced, transcribe with our own `servinosmanov/whisper-large-v3-crh`,
   agreement-filter against robinhad wav2vec2, keep only high-confidence
   segments. Lower purity but usable; swap to tier 1 once the text is found.

Tier 2 makes all 18.2h usable for TTS; tier 1 now covers the cleanest ~9.4h.
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

## Book batch filed 2026-07-27 (`~/Downloads/new books` → library root)

18 Crimean-Tatar / Crimea-related PDFs (~913 MB), all with a digital text layer
(not pure scans), moved into `/Volumes/T9/AnaYurt/Books/Qirimtatar/`. Filenames
keep their download batch numbers. **Corpus-relevant** = matches an Elvide book.

| # | File | Note |
|---|------|------|
| 01 | `1. Анамнынъ сымасы манъа мешъаль олды Сейяре Меджитова.pdf` | — |
| 02 | `2. О чём говорят животные Чергеев.pdf` | Asan Çergeev |
| 05 | `5. Къырымтатар халкъынынь къараман къызы У. Эдемова.pdf` | Edemova (other work) |
| 06 | `6. Кърымчахлар альманах Сумина.pdf` | Krymchak almanac |
| 07 | `7. Туфанда къалгъан къой сюрюси Юсуф Болат.pdf` | Yusuf Bolat, novel |
| 08 | `8. АМЕТ ХАН.pdf` | Amet-Han Sultan (161 MB) |
| 10 | `10. Живые свидетели событий … Крикля.pdf` | WWII memoir |
| 12 | `12.Легенды Крыма для детей Файзи.pdf` | Crimea legends (kids) |
| **13** | `13.  Сайлама эсерлер Черкез-Али Аметов.pdf` | **⭐ Çerkez-Ali sel. works → books 03,04 text** |
| **14** | `14.  Сайлама эсерлер учт томлыкъ Урие Эдемова.pdf` | **⭐ Edemova sel. works → books 09–11 text** |
| 15 | `15. Верные дочери Крыма Халилова.pdf` | 123 MB |
| 16 | `16.  Къырымтатар къадан-къызлары … Аблязиз Велиев.pdf` | Ablâziz Veliyev |
| 17 | `17.Тебессюм иле Яша Сервер Какура.pdf` | Server Kakura |
| 18 | `18. Линяре Дерменджи в ргб.pdf` | Linâre Dermenci |
| 19 | `19. Крымскотатарско-русский словарь Терлекчи.pdf` | ⭐ CT–RU dictionary (lugat) |
| 20 | `20. Шамиль Алядин в ргб.pdf` | Ş. Alâdin (rel. to books 01/02) |
| 22 | `22. Фольклорное наследие фракийских греков.pdf` | Thracian-Greek folklore |
| 23 | `23.Между Крымом и Парижем Кенжикаева.pdf` | Kencikaeva memoir |

## Status

- ✅ Audio studied, single reader verified, jingles/music removed, 18.2h clean.
- ✅ RVC dataset curated (60min) — ready to train (`06_elvide.yaml`). **Training on hold.**
- ✅ Text sourced 2026-07-27: books 03,04 (№13) and 09–11 (№14 + HF corpus) found →
  digital text now covers **7 of 11 books (~9.4h)**.
- ☐ TTS: align 01–04 + 09–11 (tier 1, ~9.4h); ASR-transcribe 05–08 (Sabalar
  quçağında, ~8.8h) until the novel text is sourced; optional denoise.
