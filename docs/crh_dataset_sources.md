# Crimean Tatar dataset — raw source registry

Single source of truth for **where all raw Crimean-Tatar speech/text material
lives, how it was obtained, and under what permission**. Covers local scrapes,
Telegram rips, and site mirrors; Hugging Face resources are catalogued
separately in [[crh_resources]], and the processed Elvide audiobook corpus in
[[crh_audiobook_corpus]].

> **Mirror:** a copy lives at the data root as
> `/Volumes/T9/AnaYurt/Books/Qirimtatar/_DATASET_SOURCES.md`. Keep in sync:
> `cp docs/crh_dataset_sources.md '/Volumes/T9/AnaYurt/Books/Qirimtatar/_DATASET_SOURCES.md'`

Data roots:
- **Scraped sources:** `/Volumes/T9/AnaYurt/Books/Qirimtatar/sources/` — grouped
  by author since 2026-07-30, see its `README.md` and generated `AUTHORS.md`
- **Book library:** `/Volumes/T9/AnaYurt/Books/Qirimtatar/` (flat root)
- **Telegram media rips:** `/Volumes/T9/AnaYurt/tg-media/`

Every scraped source folder carries its own `README.md` + a **re-runnable
script** (incremental: skips what's on disk), so refreshing a source = rerun
its script. Source folders are **immutable raw input** — cleaning and dedup
happen downstream in the dataset build, never by editing them in place.

## Speech (audio) sources

| # | Source | Location (under data roots) | Contents | Size | Refresh | Permission / license |
|---|--------|------------------------------|----------|------|---------|----------------------|
| S1 | TRK Millet audiobooks | `sources/trkmillet/` | 11 audiobooks, 130 mp3, 28.4h, **one narrator (Elvide Bekirova)**; processed corpus → [[crh_audiobook_corpus]] | 2.1 GB | `scrape.py` (geo-gate bypassed via Googlebot UA) | public broadcaster site; internal dataset use |
| S2 | leylaemir.org sound gallery | `sources/leylaemir-org/` | 95 mp3 readings of CT prose/poetry (Yusuf Bolat, Ş. Bektöre, Ş. Alâdin, Cevheriy, Ğ. Murad, Ş. Appaz, …); `INDEX.json/md` with author/work/genre; **speakers not identified per record** | 558 MB | `scrape.py` | ✅ author permission for dataset use (2026-07) |
| S3 | YouTube @mayesafet | `sources/maye-safet/youtube/` | 174 m4a (audio-only) + 235 info.json + 222 vtt subs; U. Edemova «Aydın gecede» roman readings + short poem readings (Giraybay, Şemyi-Zade, Qurtnezir, …), 2010→2026 | 2.0 GB | `download.sh` (yt-dlp, `archive.txt` incremental) | ✅ author permission for dataset use (2026-07) |
| S4 | TG @arifler_ve_ses | `sources/maye-safet/telegram-arifler_ve_ses/` → `tg-media/arifler_ve_ses/` | Same author's TG channel (Maye Safet / «Arifler ve ses»): mp3+mp4 readings incl. «Aydın gecede» episodes, Dağcı «Olar da insan edi», O. Aqçoqraqlı, etc. **complete 2026-07-30**: 260 files — 181 mp4, 54 jpg, 22 mp3, 3 pdf; verified against Telegram (`downloaded 0, skipped 260`) | 34 GB | tg-grabber | ✅ author permission for dataset use (2026-07) |
| S5 | TRK Millet radio archive | (not yet ripped) | trkmillet.ru WP REST: program-episode/specials = 210 items; only the 11 audiobooks (S1) taken so far | — | extend S1 `scrape.py` | as S1 |

**S3⇄S4 dedup:** the YouTube and TG channels overlap heavily. 60 long YT items
(~24h, incl. most «Aydın gecede» episodes) were **not downloaded** — marked done
in `sources/maye-safet/youtube/archive.txt` after matching TG files by ffprobe duration
(±2 s) + filename. **Redone properly on 2026-07-30** against the finished rip,
by Chromaprint fingerprint rather than duration —
`scripts/corpus/dedup_recordings.py`, results in
`sources/maye-safet/dedup_map.json` + `DEDUP_REPORT.md`:

| | |
|---|---|
| Duplicate pairs (same recording on both channels) | 109 |
| YouTube-only recordings | 65 |
| Telegram-only recordings | 94 |
| **Distinct recordings by this reader** | **268** |
| Equal duration but different audio — both kept | 177 pairs |
| Skipped YT items with no TG counterpart | 0 (the old skip decision holds) |

Separation is unambiguous: duplicates peak at 0.135 bit-error, the nearest
non-duplicate sits at 0.408, threshold 0.25 — no borderline verdicts.
**Canonical copy = Telegram in all 109 pairs:** YouTube re-encodes every upload
to a flat 127 kbps, while Telegram keeps the author's original (127 kbps at
worst, 163–198 kbps in 55 pairs). Build from Telegram, keep YouTube for its
`vtt` subtitles and `info.json` metadata.

**Dedup rule (applies corpus-wide):** the unit is a *recording*, not a work. The
same text read by a different person is not a duplicate — both stay, that is the
multi-speaker material the corpus wants. Titles and durations never decide;
only fingerprint agreement does. So `leylaemir-org` and `trkmillet` are never
deduped against Maye Safet — different readers by construction.

## Text sources

| # | Source | Location | Contents | Size | Refresh | Permission / license |
|---|--------|----------|----------|------|---------|----------------------|
| T1 | CT library (books) | `Books/Qirimtatar/` (flat root) | ~400 PDFs/fb2/docx/epub: CT literature, dictionaries, textbooks, press (Yıldız, Tan, Günsel); incl. digital-text sources for S1 alignment | ~15 GB | manual curation | mixed (public library scans, purchased, donated) |
| T2 | Maye Safet site mirror | `sources/maye-safet/site-mozello/` | Full wget mirror of maye-safet-metinler.mozello.com: 63 pages (metinler, balalar içün, yırlar, tercimeler UA/RU, articles) + 622 CDN files | 58 MB | `mirror.sh` | ✅ author permission for dataset use (2026-07) |
| T3 | TG book channels (tg-grabber) | `Books/Qirimtatar/tg2026/` | crimeacademy 1446 files/42 GB · kirimakademiyasi 960/20 GB · qirimjrkitap 280/9.7 GB · tiLim8 36 · QIRIM_TOPONIMIKA 13 · Qirim_yurtu 2 — books/PDF/media from CT Telegram channels; `manifest.json` = idempotency | ~72 GB | tg-grabber (`TG_FILES_DIR`, run `index` after moves) | public TG channels; internal dataset use |
| T4 | kirimakademiyasi.ru | inside T3 (`tg2026/kirimakademiyasi/`) + site | Crimean Academy digital library (crh books/PDFs) | — | — | public library |
| T5 | HF text corpora | Hugging Face | `QIRIM/crh_web`, `crh_monocorpus`, `crh-parallel-corpora` (gated), goldfish LMs, … — full catalogue in [[crh_resources]] | — | HF | CC-BY-4.0 mostly; see [[crh_resources]] |

## Recording ⇄ book matching

`scripts/corpus/match_books.py` proposes which library file may hold the text of
each recording — the short list forced alignment starts from. Output:
`sources/book_matches.json` + `MATCHES.md`. **Candidates for review, not
decisions:** a filename match is evidence, and «Saylama eserler» collections hold
many works under one name.

Run of 2026-07-30 — 3148 book files × 304 recordings:

| Tier | Meaning | Count |
|---|---|---|
| strong | author *and* multi-word title agree | 7 |
| title-only | title agrees, author absent from the filename | 16 |
| author-only | a book by this author exists, this work not identified | 86 |
| weak / none | partial or nothing | 193 |

Matching folds both sides to a coarse **skeleton key** (q/k → k, c/дж → j,
ç/ч → c, ğ/гъ → g, ñ/нъ → n, ı/ы/и → i) so Cyrillic, crh-Latin and the ad-hoc
romanization in `tg2026` filenames compare directly. It is a lookup key, never a
spelling — transliteration proper stays with the vetted engine, which does not
apply to personal names anyway.

Two rules the numbers above depend on, both learned from false positives:
substring matching is **off for author names** (else "Abilkerim" matches
"Kerim", one poet swallowing another), and a **one-word title cannot confirm a
match** (any book carrying that word scores perfectly). Records with one-word
titles can still be placed by author.

### Verification of the candidates (2026-07-31)

`scripts/corpus/verify_matches.py` opens each candidate book and looks for the
work's title in its own text (first 12 pages + last 10, where Soviet editions
print the contents). Results: `sources/verified_matches.json` + `VERIFIED.md`.

| Verdict | Count | Meaning |
|---|---|---|
| confirmed | 13 | title found in the book's text — safe to align |
| weak | 8 | partial evidence, needs a human look |
| absent | 46 | text readable, work not in it — filename matched the wrong book |
| unreadable | 26 | image-only scan, no text layer; needs OCR before judging |
| inconclusive | 16 | title too short to decide (one distinctive word) |

`absent` dominating the `author-only` tier (46 of 66) is the expected answer, not
a failure: a collection named after its author usually does *not* contain the
particular work being read.

Matching a title needs a **phrase** hit, not a bag of words — "Sen bir yana, men
bir yana" is otherwise satisfied by any book containing those common words, and
a Ukrainian textbook duly "confirmed" it. The phrase test tolerates spelling
drift (`hanım`/`hanum` across editions) by comparing windows anchored on the
title's rarest word.

### Staging for alignment (2026-08-01)

`scripts/corpus/stage_alignment.py` turns confirmed pairs into the folder layout
`experiments/06_tts_dataset/scripts/run_all.py` expects, under
`Books/Qirimtatar/align-staging/`. Audio is **symlinked** (the corpus is 34 GB);
the only new bytes are transcripts and, for a work split over several
recordings, one concatenated file. Report: `sources/STAGING.md`.

The gate is **scale**, not filenames: crh reading runs ≈14 characters per
second, so transcript length against audio duration says whether a pair is a
whole work or one poem inside a collection. A forced aligner handed a 190k-char
collection and a 20-minute recording does not fail loudly — it returns confident
nonsense.

- `ready/` — 3 items, transcript and audio agree in scale
- `needs-review/` — 4 items where the work had to be cut out of a collection by
  locating its title; the span is approximate and must be checked before use

Two `confirmed` pairs were **not** staged: «Чауш огълу» (trkmillet splits a book
into a dozen files — needs its own concatenation rule) and Maye Safet's
collection (image-only scan).

**The tg2026 OCR cache is not a transcript source.** It holds 3–6 pages per book
— title page and imprint — because the cataloguing task only needed metadata.
It is right for *finding* a title (`verify_matches.py` uses it, which is how 26
`unreadable` verdicts fell to 7) and wrong for alignment: an early draft staged
a 1397-character title page as a whole work. Full text comes from `pdftotext`
over the whole document, or the book is reported as needing a real OCR pass.

### Long multi-part books (2026-08-01)

`align_segment.py` aborts above roughly 80 minutes (`std::length_error` from its
C++ backtracking), which is what «Чауш огълу» (2h20m) hit. The reader already
split the book into nine files, so `scripts/corpus/align_multipart.py` aligns
those instead. The hard part is the *text*: this book has no usable chapter
markers (six roman numerals for nine parts, the rest page numbers).

Text boundaries are **absolute** — part *i* ends at
`chars × (seconds so far / total seconds)`, snapped to the nearest paragraph
break — and the reading rate is measured from the book itself (12.9 chars/s
here, not the 14 assumed corpus-wide). Absolute boundaries matter: parts 4–5
misaligned and parts 6–9 were unaffected, because no boundary inherits the
previous one's error.

A first attempt chained the parts instead, giving each a 35% text margin and
taking the last aligned clip as the next part's anchor. That cannot work:
forced alignment fits *whatever* text it is given into the audio, so the anchor
always landed at the end of the margin, every part over-consumed by exactly that
margin, and the text ran out two parts early. Those runs are kept in
`work-superseded/` rather than deleted.

Parts 4 and 5 kept only 16 of 147 clips; realigned as one unit (the split
between them was wrong, their combined share was right) that became 68 of 120.
Still below the ~90% the other parts reach, so the audio there probably departs
from the book — the QC gate keeps that out of the dataset rather than hiding it.

### Dataset build (2026-08-01)

Four items aligned; QC kept 575 clips from the three leylaemir readings and 848
from «Чауш огълу». With the pre-existing corpus the dataset is now **2795 clips
/ 6h08m**, quarantining 281 (`low_score` 112, `char_rate` 109, `has_digit` 49,
`duration` 11).

| Book | Segments | Kept | Minutes |
|---|---|---|---|
| nenkejan_hanim_turbesi | 564 | 506 | 66.1 |
| altin_basnen_hiyar_bas | 74 | 48 | 6.2 |
| adam_ve_kopek | 23 | 21 | 2.9 |

**The dataset stopped being single-speaker, and LJSpeech cannot say so.**
`metadata.cyr.csv` has no speaker column; the pre-existing corpus is one
narrator, and these additions are leylaemir readings whose readers are not
credited per record. Median F0 over a random sample: **≈206 Hz** for the old
clips, **≈120 Hz** for the new ones, which themselves spread 107–226 Hz. So
`scripts/split_by_source.py` now also writes `metadata.sevil.*` (1372 clips,
single voice — use for single-speaker fine-tuning), `metadata.trkmillet.*` (848,
one narrator: Elvide Bekirova) and `metadata.leylaemir.*` (575, several voices),
plus `sources.csv` and `SOURCES.md`. Three distinct voices now, not one. The merged files are
left untouched. That pitch check is an indicator, not speaker verification —
`scripts/rvc/build-voice-centroid.py` does the real thing, but `resemblyzer` is
not installed in the `crh_align` env.

### Open tasks

1. The 13 `confirmed` pairs are ready for the forced-alignment pipeline in
   `experiments/06_tts_dataset`; build from the **Telegram** copy of any deduped
   recording.
2. The 8 `weak` + 16 `inconclusive` pairs need a human decision.
3. The 26 `unreadable` books are image-only — they can only be judged after OCR.
4. `absent` pairs should not be re-matched by filename; locating a work inside a
   collection needs a table-of-contents pass.

## Cross-source opportunities (audio ⇄ text)

- **«Aydın gecede»** (S3/S4 audio, ~41 episodes ≈ 16h): U. Edemova digital texts
  exist — `14. Сайлама эсерлер учт томлыкъ Урие Эдемова.pdf` (T1) and
  `QIRIM/crh_monocorpus` (T5) → candidate for tier-1 forced alignment, same
  pipeline as the Elvide corpus ([[crh_audiobook_corpus]] §Transcript strategy).
- **leylaemir readings** (S2): several works exist as text in T1 (e.g. Yusuf
  Bolat «Tufanda qalğan qoyun sürüsi» = `7. Туфанда къалгъан къой сюрюси…pdf`,
  Ş. Alâdin works as fb2) → alignment candidates after speaker diarization.
- **Maye Safet poems**: site texts (T2) ⇄ her own readings (S3/S4) — small but
  author-voiced, exact-text pairs.

## Permissions summary

- **Maye Safet / leylaemir materials (S2, S3, S4, T2):** Servin contacted the
  author(s) in July 2026 — permission granted to use the materials for dataset
  building.
- Public-web sources (S1, S5, T3, T4): scraped for internal research/dataset
  use; no explicit grant — review before any public dataset release.
- HF sources: follow each dataset's license/gating ([[crh_resources]]).

## Changelog

- **2026-08-01** — first dataset build from these sources: 3 pairs aligned
  (661 clips, 575 kept), dataset now 1947 clips / 4h17m, and split by source
  after a pitch check showed it is no longer one voice. tg2026 OCR finished (1525/1525); re-verified with its text
  (unreadable 26→7, confirmed 13→15) and staged the confirmed pairs for
  forced alignment (3 ready, 4 needing a checked slice).
- **2026-07-31** — candidates verified against the books' own text
  (`verify_matches.py`): 13 confirmed, 8 weak, 46 absent, 26 unreadable,
  16 inconclusive. A title now needs a phrase hit, not matching tokens.
- **2026-07-30** — recording⇄book matching added (`match_books.py`): 7 strong,
  16 title-only, 86 author-only across 304 recordings. S3⇄S4 dedup redone by audio fingerprint: 268 distinct
  recordings (109 duplicate pairs), Telegram canonical everywhere. S4 rip
  finished (260 files / 34 GB, 0 failures, verified
  against Telegram). Scraped sources moved out of the flat book root into
  `Books/Qirimtatar/sources/`, grouped by author; `AUTHORS.md` generated there
  (36 authors + 13 anonymous folk records across 5 source folders). Two defects
  found in `leylaemir-org/INDEX.json` (author/work swapped for 7 folk tales;
  same person spelled 3 ways across sources) — handled by readers, source
  indexes left untouched.
- **2026-07-29** — added S2 (95 mp3), S3 (174 m4a + subs, TG-dedup'd), T2
  (full mirror); registry created.
- **2026-07-27** — T1 batch of 18 digital-text PDFs filed; S1 corpus text
  coverage 7/11 books.
- earlier — S1 rip + Elvide corpus, T3 tg2026 archive.
