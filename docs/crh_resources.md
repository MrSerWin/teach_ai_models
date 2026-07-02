# Crimean Tatar (crh) Hugging Face resources — what each is good for

Research pass 2026-07-01 over the URLs in `docs/huggingface_models.txt`, mapped
to this project's needs: (1) crh TTS voice "Sevil", (2) improving crh Whisper ASR
`servinosmanov/whisper-large-v3-crh`, (3) new RVC voiceover voices, plus text
tooling (normalization, Cyrillic↔Latin transliteration, G2P for /q/=къ, LM, MT).

## TL;DR priorities

1. **RVC voices are free wins** → `speech-uk/tts-crh-abibullah` (male, ~2h50m, 48 kHz) and `…-arslan` (male, ~1h20m) are clean single-speaker real recordings = two ready new voiceover voices. RVC clones timbre, so speech-uk's weak *pronunciation* doesn't matter.
2. **ASR alignment/baseline** → `robinhad/wav2vec2-xls-r-300m-crh` (CTC, WER~45%, MIT) for forced alignment + agreement-filtered pseudo-labeling against our Whisper.
3. **ASR / LM text** → `QIRIM/crh_web` (125k rows, biggest) + `crh_monocorpus` (dual-script) for a crh LM to rescore Whisper; `goldfish-models/crh_latn_full` + `crh_cyrl_5mb` as ready tiny LM scorers.
4. **Transliteration & /q/ G2P validation** → `QIRIM/crh-parallel-corpora` gives paired **Cyrillic↔Latin** sentences (gated) — ideal to validate our translit + q=къ rules.
5. **MT (crh↔tr)** → `mshamrai/crh-tur-llama32-1b-qlora` as a reproducible baseline (1-epoch, undocumented — extend, don't ship).

---

## By project need

### 🎙️ New RVC voiceover voices (needs clean SINGLE-speaker audio)
| resource | speaker | amount | SR | script | verdict |
|---|---|---|---|---|---|
| `speech-uk/tts-crh-abibullah` | Abibullah (m) | ~2h50m, 2824 clips | 48 kHz | Latin | ⭐ best new voice |
| `speech-uk/tts-crh-arslan` | Arslan (m) | ~1h20m, 1506 clips | 48 kHz | Latin | ✅ workable (RVC needs less) |
| `speech-uk/tts-crh-sevil` | Sevil (f) | ~2h29m, 1649 clips | 48 kHz | Cyrillic | ✅ but redundant (we have a better Sevil) |
| `robinhad/crh-tts-output` | multi/ambiguous | ~1142 rows | unknown | mixed | ⛔ synthetic TTS output — avoid |

All speech-uk sets: real read speech, Apache-2.0, not gated. RVC doesn't care about
pronunciation quality → these are the fastest path to distinct new voices.

### 🎧 crh Whisper ASR improvement
- **Training audio+text:** the three `speech-uk` sets (sevil=Cyr, abibullah/arslan=Lat) add 3 speakers + both scripts. ⚠️ **QA transcripts first** — speech-uk pronunciation is weak, and bad audio↔text pairs teach the ASR wrong mappings.
- **Forced alignment / 2nd-opinion decoder:** `robinhad/wav2vec2-xls-r-300m-crh` — CTC (per-frame logits), WER 0.449 / CER 0.125, MIT, Latin. Good for aligning our audiobooks and for pseudo-label *agreement filtering* (keep only where it and Whisper agree). Training corpus undocumented.
- **LM rescoring of ASR n-best:** `goldfish-models/crh_latn_full` (GPT-2 124M, Latin, Apache-2.0), `crh_cyrl_5mb` (39M, **only Cyrillic** goldfish), plus a bigger LM trained on `QIRIM/crh_web`. goldfish = tiny comparability LMs (350 langs), no published perplexity → lightweight scorers only. `crh_latn_10mb`/`crh_latn_5mb` are strictly dominated by `_full`.

### 📝 TTS text / transliteration / G2P (for /q/=къ)
- `QIRIM/crh-parallel-corpora` — crh↔en/ru/uk sentence pairs, **each crh sentence in both Cyrillic AND Latin** → ready-made translit table to validate our converter + q=къ mapping. 39.5 MB, CC-BY-4.0, **GATED** (accept agreement).
- `QIRIM/crh_web` — 125,453 rows web text (Ukrainer + Wikipedia), Latin only, 148 MB, CC-BY-4.0, ungated → biggest text asset; prompt expansion + LM.
- `QIRIM/crh_monocorpus` — 137 documents (books/subtitles/folklore/press), **both scripts**, 26.5 MB, CC-BY-4.0, ungated → clean dual-script LM/text-norm material (needs cleaning).
- `QIRIM/crh_books` — literary Cyrillic, 138 MB, **GATED + license unstated + empty README** → verify before use.
- `QIRIM/crh-parallel-corpora-document-level-noisy` — 15k doc-level crh↔en/ru/uk news, Latin (Cyr null), noisy → MT/domain text only, weaker for translit.

### 🌐 MT / LLM / tokenizers / embeddings
- `mshamrai/crh-tur-llama32-1b-qlora` — QLoRA adapter on **Llama-3.2-1B** for crh↔Turkish MT. 1 epoch, val loss 1.68, no BLEU, unnamed data → **baseline to reproduce/extend**, not production. (Turkish = closest high-resource relative → best MT bridge.) Base model gated (Llama license).
- `transhumanist-already-exists/crh_monocorpus-bpe-50_256` — byte-level **BPE tokenizer** (vocab 50,256, CC-BY-4.0, Latin) trained on crh_monocorpus; ~2× more compact than base Aya on crh. Useful for LM/TTS text front-ends; also a pointer to the monocorpus.
- `wikilangs/crh` — MIT collection (~3.7 GB) from Wikipedia: **fastText embeddings**, BPE tokenizers (8k/16k/32k/64k), n-gram (2–5) + Markov LMs, morphology analysis. Auxiliary text-tooling baselines (Latin, small formal register).
- `LangGao/crh_data_results` — a single undocumented `CRH_paperviz.tar.xz` (77.5 MB), no card, unknown license → **skip** (research paper figures, not a usable resource).

---

## Flags
- **Gated:** `crh-parallel-corpora`, `crh_books` (also no license/empty README).
- **Avoid for training a real voice:** `robinhad/crh-tts-output` (synthetic, multi-speaker, junk strings, no license).
- **Cyrillic gap:** most text/LM resources are Latin-only; Cyrillic-side options are `crh_monocorpus`, `crh_books` (gated), `goldfish crh_cyrl_5mb`, and `speech-uk/tts-crh-sevil`.
- **No audio** in any QIRIM/goldfish/LLM/tokenizer resource — those help only the text/G2P/LM/MT side.

## Concrete next actions this unlocks
- **Now:** grab `abibullah` (+`arslan`) → new RVC voice(s) via the exp-04 pipeline. See [[project_rvc_new_voice]].
- **Whisper:** assemble ASR set = our Sevil corpus + QA'd speech-uk sets; use robinhad wav2vec2 for alignment/agreement filtering; build an LM from `crh_web`. See [[project_whisper_crh]].
- **/q/ work:** pull `crh-parallel-corpora` (gated) to validate transliteration + q=къ against real Cyr↔Lat pairs. See [[project_crh_q_phoneme]].
