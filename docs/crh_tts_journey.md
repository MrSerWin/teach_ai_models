# Building a Crimean Tatar TTS voice from audiobooks — full journey

> Article-notes / lab journal. Standalone narrative that ties experiments 06
> (dataset) and 07 (fine-tuning) into one story, with every step, number, and
> gotcha captured so it can be turned into an article later. Technical reference
> stays in each experiment's `README.md`; this file is the *why* and the *path*.

---

## 0. Context & goal

Crimean Tatar (`crh`) is a severely under-resourced Turkic language. The goal:
a **high-quality single-speaker TTS voice** ("Sevil", female) good enough for the
Ana-Yurt educational apps and dictionary tools — not a research toy.

Prior art (the author's own, the starting point of this journey):
- `servinosmanov/tts-crh-sevil-fixed` — a cleaned-up HF dataset derived from
  `speech-uk/tts-crh-sevil` (1566 clips, 16 kHz, Latin). Audio corruption,
  transcripts and metadata were fixed, but the *pronunciation* is inherited from
  the source recordings, which are known to be weak.
- `servinosmanov/xtts-crh-sevil-v1` (Coqui XTTS v2, ~7 h training) and
  `servinosmanov/speecht5-crh-sevil` (SpeechT5 + a phonetic Latin→English map).

The two open questions this journey answers:
1. **Can we build a better dataset** from real Sevil audiobooks (cleaner
   pronunciation than the public corpora)?
2. **Which base model + data strategy** gives the most realistic voice — and is
   it worth *merging* the new and old data?

Hardware: RTX 5090 Laptop 24 GB, WSL on Windows, driven over SSH from a Mac.
Constraint from the user: **local models only**, no paid API traffic.

---

## 1. Phase 1 — Dataset from audiobooks (experiment 06)

### 1.1 The core idea: forced alignment, not ASR

We already have the **ground-truth transcript** for each audiobook. So we never
need a (weak) Crimean Tatar ASR. Instead we **force-align** the known text to the
audio and cut on the resulting word timestamps. This is the single most important
decision — it sidesteps the language's lack of good ASR entirely.

### 1.2 Pipeline (18 books in → LJSpeech out)

1. **Text prep** (`prepare_text.py`) — extract `.txt` / `.odt` (pandoc) / `.pdf`
   (pdftotext); un-wrap hard line breaks (blank line = hard break, otherwise join
   unless the previous line ends in sentence punctuation); unify quotes/dashes,
   strip soft hyphens; split into sentences. **Original Cyrillic orthography is
   preserved** — that is the dataset text.
2. **Forced alignment** (`align_segment.py`) — Meta **MMS-300M** CTC model (ONNX,
   via `ctc-forced-aligner`, no torch dependency). Returns per-word timestamps +
   per-word CTC log-prob. Cyrillic is romanized *only* to feed the acoustic model
   (`romanize.py`); the stored dataset text is untouched.
3. **Segmentation** — pack words into **4–12 s** clips (target ~7 s), preferring
   to close on a sentence boundary that lands in a silence gap; cut points are
   **centred in inter-word silence** so no word is clipped. Short sentences are
   merged, never emitted alone. Export **22.05 kHz mono, peak-normalised**.
4. **QC** (`qc_report.py`) — every clip carries a mean per-frame CTC log-prob
   (`score`, a direct audio↔text match measure) and a `char_rate` (chars/s).
   Clips that match poorly, have an implausible speaking rate, run too long, or
   contain digits are **quarantined** to `metadata.review.csv`, not silently kept.

### 1.3 Dual orthography (Cyrillic + Latin)

The author prefers Latin but had seen more phonetic errors in Latin before. So we
emit **both** `metadata.cyr.csv` and `metadata.lat.csv` from the *same* clips,
using the author's own production transliteration (`StranslinService.js`, bridged
to Python via a small Node script). This lets us train/compare both scripts
without rebuilding audio.

### 1.4 Result

| metric | value |
|---|---|
| books processed | 18 |
| total segments | 1437 (3 h 10 m) |
| **kept** | **1372 (3 h 02 m, 95 %)** |
| quarantined | 65 (char_rate 27, low_score 18, has_digit 15, duration 5) |
| format | 22.05 kHz mono, LJSpeech, `id|text|text`, cyr + lat |

QC thresholds: `score ≥ -0.95`, `char_rate ∈ [6, 19]`, `dur ∈ [3.5, 13] s`.
One book (`solnechnaia_sistema`) was fully quarantined (digits/units-heavy).

### 1.5 Gotchas worth telling in the article

- **Hard-wrapped text.** Source `.txt` was wrapped mid-sentence; a naive
  line-based split breaks prosody. Fixed with punctuation-aware un-wrapping.
- **C++ DP overflow on long books.** The aligner's monotonic DP threw
  `std::length_error` on very long inputs. Fixed with **chunked alignment**: a
  sliding window over the transcript, committing all but the last `CHUNK_TAIL`
  words and re-aligning the tail (an early version had a "cramming" bug where the
  cursor jumped to the window end — words got crammed into one clip).
- **Romanize vs store.** Keeping the acoustic-model romanization strictly
  separate from the stored dataset text avoided polluting the corpus.

> *"Some passages have words read in a different order than the text."* — the
> author asked whether this hurts training. Answer for the article: a handful of
> local word-order swaps in a 1372-clip set is negligible; the model learns
> acoustics-to-text statistics, and QC `score` already catches the worst
> mismatches. Not worth hand-fixing.

---

## 2. Phase 2 — Fine-tuning experiments (experiment 07)

Three bases, chosen to span the trade-offs. Each renders the **same 20 held-out
probe phrases** (`probe20.json`) for blind A/B listening.

### 2.1 Model A — `facebook/mms-tts-crh` (VITS, 16 kHz)

**Why:** the only base that is *already Crimean Tatar* (native phonetics, no
foreign accent), Cyrillic input. Fine-tuned with `ylacombe/finetune-hf-vits`.

**Setup:** 100 epochs, batch 16 (~8 GB), ~1 h on the 5090. Snapshot every 5
epochs for A/B (kept 5/15/30/60/100 to save disk).

**Trainer patches** (`box_repo/run_vits_finetuning.py` — the source of truth,
re-push, don't re-clone):
1. Collator returns a plain `dict` so accelerate skips the `None` speaker_id
   (single-speaker) — upstream returns a `BatchEncoding` and crashes.
2. **Non-destructive snapshots.** Upstream's in-loop save block destructively
   removes weight-norm every epoch (corrupts training after epoch 1). Replaced
   with: clone `state_dict` to CPU → rebuild `type(m)(config)` → `apply_weight_norm`
   → load → `remove_weight_norm` → `save_pretrained` to `checkpoint-epoch<N>`.

**Result:** mixed. Some phrases perfect, some quite bad; a **metallic timbre**
across almost all epochs. Root causes (full analysis in
`experiments/07_tts_finetune/NOTES_mms_crh.md`):
- *Per-phrase inconsistency* → VITS **stochastic duration predictor** + flow
  sampling (non-deterministic). Mitigable at inference (`noise_scale≈0.4`,
  `noise_scale_duration≈0`, fixed seed) without retraining.
- *Metallic* → **16 kHz ceiling** (primary, unfixable at 16 kHz) + HiFi-GAN
  vocoder artifacts + fp16 GAN training. (Note: only 3 of 18 source books are
  mp3; 15 are 44.1 kHz float wav — mp3 is a minor factor, the 16 kHz ceiling
  dominates.)

**Verdict:** keep as a *baseline*, not the goal. The 16 kHz ceiling alone is why
we move to 24 kHz models next.

### 2.2 Model B — XTTS v2 (Coqui, 24 kHz output)

**Why:** the author's prior best; 24 kHz output → far less metallic. Crimean
Tatar isn't a native XTTS language, so we borrow the closest in-set token: **`tr`**
(Turkic + Latin script, matches `metadata.lat.csv`).

**Setup:** GPTTrainer fine-tune from the XTTS v2 base, fp32, 100 epochs, batch 3,
grad-accum 42, lr 5e-6. Base staged at `/mnt/d/models/xtts_base`
(model.pth + vocab.json + config.json from the public v2; dvae.pth + mel_norms.pth
from the author's v1 repo).

**Gotchas (gold for the article):**
- **torch ≥ 2.6 vs Coqui 0.22.** `torch.load` now defaults to `weights_only=True`
  and *rejects XTTS's pickled config*. Fix: a `torch.load` shim restoring
  `weights_only=False` **before** any TTS import.
- **fp16 NaNs the XTTS GPT from step 0.** Must train **fp32** (fits in 24 GB).
  This cost real debugging time — see the false-conclusion note below.
- **`save_step` is in raw forward batches**, not optimizer steps. Coqui
  increments `GLOBAL_STEP` per forward pass, so
  `save_step = ceil(n_train / batch) * save_every_epochs`.
- **Checkpoints are ~2–5 GB each.** Keep only `KEEP_N` rolling, render A/B before
  they roll off. (Contrast: VITS snapshots are ~317 MB — we kept 20.)
- **`pkill -f train_xtts.py` self-matches the SSH command line** and kills the
  relaunch. A "fp32 still NaNs" conclusion was *false* — the relaunch had killed
  itself. Use `pkill -f '[t]rain_xtts.py'`. **Lesson: verify your kill actually
  killed the right PID before concluding anything about the run.**

### 2.3 The `/q/` problem — XTTS's Turkish prior mispronounces къ (THE key finding)

Listening to the v1-vs-new A/B, the author pinpointed *why* the Turkish base
always sounded subtly wrong: **it reads Crimean Tatar `q` (Cyrillic къ, the
uvular /q/) as a plain Turkish /k/.** Crimean Tatar has /q/ and /k/ as **separate
phonemes**; Turkish does not (one /k/ with positional allophones), and the `tr`
language prior collapses them.

We verified the mechanism rather than guessing:
- **It is not a text/tokenizer bug.** In the XTTS vocab `q`→token 30, `k`→token
  24 — *distinct* tokens; the `tr` cleaner leaves `q` untouched (`qara qırım`
  stays `qara qırım`). The model *can* tell them apart.
- **It is not lack of data.** In the 1372-clip set, **88 % of clips contain `q`**
  (3257 `q` chars, *more* than `k`'s 3032; top words `yoq`, `qaç`, `qadar`,
  `vaqıt`, `qız`). The model saw `q`↔/q/ audio thousands of times.
- **It is the cross-lingual acoustic prior.** Token 30 (`q`) is already voiced as
  /k/ in the base (English/Spanish/French "q" = /k/), and fine-tuning at lr 5e-6
  did not override it. **Corollary: more data (the merge run) will NOT fix /q/** —
  it carries the same 88 % exposure against the same prior.

This exposes the project's central trade-off:

| model | /q/ (uvular) | timbre |
|---|---|---|
| **mms-tts-crh** (native crh) | ✅ correct | ❌ metallic (16 kHz) |
| **XTTS v2** (Turkish base) | ❌ reads /k/ | ✅ natural (24 kHz) |

Each is strong exactly where the other is weak. Candidate fixes to probe (after
the merge run, per the author's call):
1. **`lang=ar`** instead of `tr` — Arabic has the qāf phoneme /q/; its language
   embedding may pull `q`→/q/.
2. **Grapheme respelling** of `q` to a sequence the base already renders back/uvular.
3. **Lower inference temperature** (0.3 vs 0.7) — sharper consonants.
4. Confirm `q`≈`k` audibly as the baseline.
Longer term: native mms-crh + bandwidth-extension (16→24 kHz) is the other route
to "correct /q/ *and* good timbre".

### 2.4 Model C — SpeechT5 (planned)

The author's prior SpeechT5 used a phonetic-v4 Latin→English mapping
(ğ→gh, ç→ch, ş→sh, ñ→ng, ı→y, ö→o, ü→u, j→zh, c→dj). To be re-run on the new
dataset after XTTS, for a three-way comparison. (Pending.) Note: that map leaves
`q` as-is → likely the same /q/ issue; worth testing a `q→q`-vs-respelling there
too.

### 2.5 Infra lessons (operational, but real)

- **Wrong filesystem = self-inflicted disk crisis (with a trap).** Runs were
  written to `/mnt/d` — the Windows **NTFS** data drive, mounted in WSL, sitting
  at ~99 % (a few GB free on 1.1 TB). XTTS saves a `best_model` *every epoch* on
  eval-improvement (5.6 GB each) plus periodic checkpoints, so it filled fast.
  **The trap:** the obvious "fix" — relocate to the WSL **ext4 home (`/`), which
  `df` reported as 176 GB free** — made it *worse*. That ext4 lives in a
  **dynamic `.vhdx` whose backing file physically sits on D:**. Its "free GB" is
  fiction: writing there grows the vhdx into the already-full D:, the host write
  fails, and **WSL I/O wedges** — `sshd` started resetting connections at
  key-exchange (`kex_exchange_identification: read: Connection reset by peer`)
  while the box still pinged. The real fix: **write to `/mnt/c` (the C: drive,
  629 GB free, independent of D:)**; keep read-only inputs (dataset, base) on
  /mnt/d (reads don't grow the vhdx). Recovery when locked out: open the WSL
  terminal *directly* on the box (bypasses sshd) to confirm WSL is alive, then
  `sudo service ssh restart`. Lesson: `df -h` lies for WSL ext4 — know which
  physical host drive each mount's storage actually consumes before pointing
  multi-GB writes at it.
- **Disk discipline.** The MMS run silently ate 15 GB via HF *step*-checkpoints
  (952 MB each, with optimizer state) — disable/prune them. XTTS checkpoints are
  ~5.6 GB each; always know per-checkpoint size × count × save-frequency
  (remember the per-epoch `best_model` saves, not just `save_step`).
- **Single source of truth for patched files.** The trainer was patched in the
  repo and pushed; never re-clone over it.
- **Reproducible launch.** XTTS was first launched by hand; that made the
  relaunch error-prone. Captured as `train_xtts.sh` (pushes the trainer + A/B
  scripts, sets the env, writes to `~/runs`) so both the new-only and merge runs
  use the identical recipe — required for an honest dataset A/B.

### 2.6 The pivot to phoneme input — espeak-ng crh, VITS, StyleTTS2

After the XTTS runs, the user's verdict was blunt: `merge_e90` was the best XTTS
variant but still "far from ideal", and — decisively — **no grapheme XTTS can
ever say /q/ right** (its Turkish prior collapses къ→/k/, Arabic→/g/). So we
stopped fixing the *model* and fixed the *input representation*.

- **espeak-ng crh is the /q/ fix.** Built espeak-ng ≥1.52 from source on the box
  (apt's 1.50 is too old); it carries a Crimean Tatar voice (`crh`, merged
  May 2025) that renders `qara`→/qɑɾɑ/ (uvular) vs `kara`→/kɑɾɑ/, plus ğ→/ɣ/,
  ñ→/ŋ/, ı→/ɯ/. Feed a model **IPA from espeak crh** and /q/ is correct by
  construction — for *any* phoneme-input model.
- **Phoneme-VITS (from scratch), 22 kHz.** `train_vits_ph.py` (Coqui) with
  `use_phonemes`, `phonemizer=espeak`, `phoneme_language=crh`. /q/ direction was
  right, but the timbre was "очень плохо" — 3 h from scratch caps quality.
  Confirmed: on this little data we must **fine-tune**, not train from scratch.
- **StyleTTS2 (fine-tune from LibriTTS), 24 kHz.** `~/StyleTTS2`, 2nd-stage FT.
  Its IPA symbol set already covers every crh phoneme (no resize). Data lists are
  `wav|IPA|0` with IPA from `espeak-ng -v crh -q --ipa=3`. Inference
  (`scripts/synth_st2.py`, a port of the LibriTTS demo) phonemizes by calling the
  espeak-ng **binary** (our build is static — no `libespeak-ng.so`, so the Python
  `phonemizer` lib can't load it); text goes on **stdin** (a leading `-` is else
  parsed as a flag). **Verdict on the first run (e39, 3 h, 22 kHz upsampled):**
  the *most realistic timbre of every model tried*, but unstable — off intonation,
  word-endings, occasional mispronunciation; single-word inputs make the diffusion
  sampler *screech* (degenerate short input — use a carrier phrase). Raising
  `embedding_scale`/`diffusion_steps` made an undertrained model **worse**, not
  better: stability comes from training, not the sampler.

### 2.7 True 24 kHz — the sample-rate lever

StyleTTS2 is a 24 kHz model, but the exp-06 wavs are 22.05 kHz; its loader
*upsamples* 22.05→24, leaving the spectrum above ~11 kHz empty (dull, veiled).
Because the book sources are 44.1 kHz and `segments.jsonl` already holds the final
cut bounds, we **re-cut the cleaned corpus at true 24 kHz** with no re-alignment
(`experiments/06_tts_dataset/scripts/recut_24k.py`): slug→source via
`slugify(unidecode(folder))`, cut `[start:end]` at 24 kHz, peak-norm 0.95, PCM_16.
Result: 1371 clips, **energy >11 kHz = 0.0137** (vs ~0 for the upsampled build) —
the top octave is really back. The espeak-crh IPA lists are reused verbatim (text
unchanged → same phonemes/ids), so only `root_path` changes and the retrain is a
clean A/B isolating the single SR variable. StyleTTS2 is the current direction;
XTTS `merge_e90` is kept only as a fallback baseline (wrong /q/).

---

## 3. Comparing datasets & the merge decision

The author has **two datasets for the same speaker**: the new audiobook corpus
(3.02 h, 22.05 kHz, clean pronunciation) and the old HF `tts-crh-sevil-fixed`
(2.58 h, 16 kHz, derived from speech-uk). Two questions:

### 3.1 How to compare fairly

Same probe phrases, same sample rate, same inference params, same reference wav.
But beware: v1 (old data, ~7 h) vs the new run (100 epochs, new data) differ in
**both** data *and* training length — so a naive A/B compares *models*, not
*datasets*. To isolate the dataset's contribution you must train both with the
**same recipe**. The clean three-way benchmark we settle on:

| run | data | meaning |
|---|---|---|
| v1 | old only | old dataset baseline |
| new-only | new only | new dataset alone |
| **merge** | old + new | does combining help? |

### 3.2 Fine-tune vs merge-from-scratch

Options weighed: (A) fine-tune v1 on new data — fast but inherits v1's quirks and
can't attribute gains; (B) merge + train fresh from base — cleanest, best ceiling;
(C) merge + warm-start from v1 — fastest path to high quality. **The author chose
(B): merge + from-scratch**, for the cleanest dataset benchmark.

### 3.3 Two honest risks of merging (named up front)

1. **16 kHz → 22.05 kHz upsampling adds no real high frequencies.** The old clips
   stay band-limited ("dull/metallic") and inject band-limited mel targets into
   the merged model. (XTTS output is fixed 24 kHz, so not catastrophic, but it is
   non-uniform.)
2. **Pronunciation provenance.** The old set descends from `speech-uk/tts-crh`,
   whose *pronunciation* is weak; fixing corruption didn't fix how words are
   spoken. Merging can mildly dilute the clean audiobook voice. → The merge A/B
   must check it didn't **regress**.

### 3.4 Unifying the two sets (`build_merged_dataset.py`)

- Resample old 16 kHz → 22.05 kHz (high-quality `soxr`).
- Peak-normalise both to 0.95.
- **Latin convention already matches** (ç ğ ı ñ ö ş ü â, no Cyrillic, ~no digits)
  → text merges cleanly, no re-transliteration.
- **Dedup by normalized text** (lowercase, strip punctuation/whitespace).

**Merge result:**

| source | clips | duration |
|---|---|---|
| new (exp 06, 22.05 k) | 1370 | 3.03 h |
| old (HF fixed, 16→22.05 k) | 1233 | 1.91 h |
| **total** | **2603** | **4.94 h** |

**335 duplicate clips dropped** by normalized text — a genuine surprise: the old
speech-uk corpus and the new audiobooks share that many sentences. Deduping
prevents over-weighting the overlap. QC clean: no empty clips, old clips audible
(rms healthy), durations within XTTS limits.

---

## 4. Status & next steps

- [x] Dataset built (1372 clips, 3.02 h, cyr+lat); audited & fixed → 1371.
- [x] mms-tts-crh fine-tuned (100 ep, 20-snapshot A/B); correct /q, 16 kHz ceiling.
- [x] XTTS v2 new-only / merge / `ar` trained & A/B'd — `merge_e90` best XTTS but
      /q/ wrong (grapheme `tr`); **grapheme XTTS abandoned for crh**.
- [x] Merged dataset built & validated (2603 clips, 4.94 h) — did not beat new-only.
- [x] espeak-ng crh built & verified (/q/ = uvular къ) — the phoneme-level /q/ fix.
- [x] phoneme-VITS from scratch — /q/ ok, timbre poor (3 h too little from scratch).
- [x] StyleTTS2 FT (LibriTTS→crh, espeak IPA), e39/22 kHz — best timbre, unstable.
- [x] Re-cut corpus at **true 24 kHz** from 44.1 kHz sources (`recut_24k.py`).
- [~] StyleTTS2 retrain on true-24 kHz data (80 ep, same LibriTTS base) — running.
- [ ] A/B: **StyleTTS2-24k vs e39 (22k) vs merge_e90** → judge /q/ + naturalness.
- [ ] If timbre still capped: more clean Sevil data (do NOT add speech-uk — weak
      pronunciation); SpeechT5 remains an optional cross-check.

---

## 5. Article angle (for later)

This is the sequel to the author's dev.to post *"My journey improving a TTS model
for the Crimean Tatar language."* The new story: **stop fixing a weak public
corpus — build your own from audiobooks via forced alignment, then prove with a
controlled A/B whether merging the old data still helps.** The honest negative
risks (§3.3) and the debugging war-stories (§2.2 gotchas) are what make it
credible rather than a tutorial.
