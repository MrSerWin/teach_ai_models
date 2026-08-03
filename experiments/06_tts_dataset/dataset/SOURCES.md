# Sources and speakers in this dataset

`metadata.cyr.csv` / `metadata.lat.csv` are LJSpeech files, and LJSpeech has
no speaker column — it assumes one voice. Since the 2026-08-01 additions that
assumption no longer holds, so the same clips are also published split by
source. **The merged files are untouched**; pick the one that matches what you
are training.

| File | Clips | Voice |
|---|---|---|
| `metadata.sevil.*.csv` | 1372 | the original single narrator (`sevil-books`) — use this for single-speaker fine-tuning |
| `metadata.leylaemir.*.csv` | 575 | leylaemir.org readings — **several readers, none credited per record** |
| `metadata.trkmillet.*.csv` | 848 | TRK Millet audiobook «Чауш огълу» — one narrator (Elvide Bekirova) |
| `metadata.cyr.csv` (merged) | 2795 | everything; multi-speaker |

`sources.csv` maps every clip to its book and source group.

## Evidence

Median F0 over a random sample of clips: **≈206 Hz** for `sevil-books`,
**≈120 Hz** for the additions, which spread 107–226 Hz among themselves.
That is a cheap pitch check, not speaker verification — the repo's
`scripts/rvc/build-voice-centroid.py` does the real thing with speaker
embeddings, but `resemblyzer` is not installed in the `crh_align` env.
Run it before treating `metadata.leylaemir.*` as any fixed number of voices.

## Why the additions are still worth having

Multi-speaker material is what ASR and multi-speaker TTS want; it is only
wrong inside a single-speaker file. Keep both and choose per task.
