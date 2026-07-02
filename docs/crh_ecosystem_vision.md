# Crimean Tatar (crh) language-AI ecosystem — vision & roadmap

Beyond any single training task: how the models and datasets we have (ours +
public) combine into **products for education, content, and preservation** of
Crimean Tatar. This doc is also the **link registry** — every tool is linked so
we don't lose track of it. Companion to the resource analysis in
[crh_resources.md](crh_resources.md) and the model journey in
[crh_tts_journey.md](crh_tts_journey.md).

Framing: think **engines** (models that *do* something) fed by **fuel**
(datasets). Combine engines + fuel into products. Each product also *produces*
new fuel — the flywheel (§5).

---

## 1. Resource registry (all links)

### Our own assets (Servin Osmanov)
| asset | what | link |
|---|---|---|
| XTTS crh Sevil v1 | 24 kHz TTS voice | https://huggingface.co/servinosmanov/xtts-crh-sevil-v1 |
| SpeechT5 crh Sevil | TTS voice | https://huggingface.co/servinosmanov/speecht5-crh-sevil |
| Whisper-large-v3-crh | crh ASR | https://huggingface.co/servinosmanov/whisper-large-v3-crh |
| tts-crh-sevil-fixed | cleaned Sevil TTS dataset | https://huggingface.co/datasets/servinosmanov/tts-crh-sevil-fixed |
| Sevil audiobook corpus | ~3 h forced-aligned LJSpeech (cyr+lat) | `experiments/06_tts_dataset` |
| RVC voice-clone pipeline | train+infer, validated | `experiments/04_rvc_voice_clone` |
| Video generator | Wan 2.2 + LTX + voice | `experiments/05_video_gen` |
| TTS fine-tuning | XTTS/VITS/SpeechT5 | `experiments/07_tts_finetune` |
| Ana-Yurt transliterator | Cyrillic↔Latin (`StranslinService.js`) | Ana-Yurt dictionary app |

### Engines — public models
| engine | type | link | note |
|---|---|---|---|
| wav2vec2-xls-r-300m-crh | CTC ASR | https://huggingface.co/robinhad/wav2vec2-xls-r-300m-crh | WER~45%, MIT; great for **forced alignment** |
| crh-tur-llama32-1b-qlora | MT crh↔tr (Llama-3.2-1B QLoRA) | https://huggingface.co/mshamrai/crh-tur-llama32-1b-qlora | baseline only (1 epoch) |
| goldfish crh_latn_full | GPT-2 LM (Latin) | https://huggingface.co/goldfish-models/crh_latn_full | tiny; LM scoring |
| goldfish crh_cyrl_5mb | GPT-2 LM (Cyrillic) | https://huggingface.co/goldfish-models/crh_cyrl_5mb | only Cyrillic LM |
| goldfish crh_latn_10mb / _5mb | GPT-2 LM (Latin) | https://huggingface.co/goldfish-models/crh_latn_10mb · https://huggingface.co/goldfish-models/crh_latn_5mb | dominated by _full |
| wikilangs/crh | fastText + BPE + n-gram/Markov | https://huggingface.co/wikilangs/crh | MIT; embeddings + LM baselines |
| crh_monocorpus BPE tokenizer | byte-level BPE (vocab 50k) | https://huggingface.co/transhumanist-already-exists/crh_monocorpus-bpe-50_256 | compact crh subwords |

### Fuel — public datasets
| dataset | content | link | script | flag |
|---|---|---|---|---|
| QIRIM/crh_web | 125k rows web text | https://huggingface.co/datasets/QIRIM/crh_web | Latin | biggest text |
| QIRIM/crh_monocorpus | 137 docs books/subs/folklore | https://huggingface.co/datasets/QIRIM/crh_monocorpus | cyr+lat | dual-script |
| QIRIM/crh-parallel-corpora | crh↔en/ru/uk sentence pairs, **cyr↔lat** | https://huggingface.co/datasets/QIRIM/crh-parallel-corpora | both | ⚠️ gated |
| QIRIM/crh-parallel-corpora-document-level-noisy | 15k doc-level news bitext | https://huggingface.co/datasets/QIRIM/crh-parallel-corpora-document-level-noisy | Latin | noisy |
| QIRIM/crh_books | literary Cyrillic corpus | https://huggingface.co/datasets/QIRIM/crh_books | Cyrillic | ⚠️ gated, no license |
| speech-uk/tts-crh-sevil | Sevil (f), ~2h29m, 48 kHz | https://huggingface.co/datasets/speech-uk/tts-crh-sevil | Cyrillic | real speech |
| speech-uk/tts-crh-abibullah | Abibullah (m), ~2h50m, 48 kHz | https://huggingface.co/datasets/speech-uk/tts-crh-abibullah | Latin | ⭐ RVC donor |
| speech-uk/tts-crh-arslan | Arslan (m), ~1h20m, 48 kHz | https://huggingface.co/datasets/speech-uk/tts-crh-arslan | Latin | RVC donor |
| robinhad/crh-tts-output | synthetic TTS dump | https://huggingface.co/datasets/robinhad/crh-tts-output | mixed | ⛔ avoid |
| LangGao/crh_data_results | undocumented paperviz archive | https://huggingface.co/LangGao/crh_data_results | ? | ⛔ skip |

---

## 2. Products for EDUCATION

| product | what it does | engines | fuel |
|---|---|---|---|
| **Read-along reader** | any crh text read aloud, words highlighted in sync | TTS (Sevil) + forced alignment (wav2vec2-crh) | [crh_web](https://huggingface.co/datasets/QIRIM/crh_web), [crh_books](https://huggingface.co/datasets/QIRIM/crh_books) |
| **Pronunciation coach** | learner speaks → ASR scores & gives feedback | [Whisper-crh](https://huggingface.co/servinosmanov/whisper-large-v3-crh), [wav2vec2-crh](https://huggingface.co/robinhad/wav2vec2-xls-r-300m-crh) | — |
| **Dictation drills** | TTS dictates → learner writes → auto-check | TTS | text corpora |
| **Talking dictionary** | audio for every Ana-Yurt entry + examples | TTS | Ana-Yurt dict |
| **Voice tutor chatbot** | spoken crh dialogue: ASR→LLM→TTS | Whisper-crh + [crh-tr LLM](https://huggingface.co/mshamrai/crh-tur-llama32-1b-qlora) + TTS | — |
| **Script converter (cyr↔lat)** | instant transliteration of texts/textbooks | `StranslinService.js` | [crh-parallel-corpora](https://huggingface.co/datasets/QIRIM/crh-parallel-corpora) to validate |

## 3. Products for CONTENT & POPULARIZATION (biggest lever — crh content is scarce)

| product | what it does | engines | fuel |
|---|---|---|---|
| **Audiobooks** | narrate books; multiple voices for dialogue | TTS (Sevil) + RVC ([abibullah](https://huggingface.co/datasets/speech-uk/tts-crh-abibullah)/[arslan](https://huggingface.co/datasets/speech-uk/tts-crh-arslan) donors) | [crh_books](https://huggingface.co/datasets/QIRIM/crh_books) |
| **Dub cartoons/films into crh** | subtitle → MT → TTS/RVC → video | [crh-tr MT](https://huggingface.co/mshamrai/crh-tur-llama32-1b-qlora) + TTS + RVC + `experiments/05_video_gen` | — |
| **Audio news / podcast** | daily crh news read aloud | TTS | [crh_web](https://huggingface.co/datasets/QIRIM/crh_web) (news) |
| **Social/YouTube video** | generated crh clips for youth & diaspora | video gen + voices | — |
| **Two-way subtitles** | ASR → crh subs; MT → ru/tr/en (and reverse) | Whisper-crh + MT | — |

## 4. Products for PRESERVATION & INFRASTRUCTURE

| product | what it does | engines | fuel |
|---|---|---|---|
| **Archive digitization** | transcribe old radio/folklore/elders → searchable text | Whisper-crh + wav2vec2-crh | — |
| **Permanent linguistic corpora** | aligned speech+text for future research | our alignment pipeline (`experiments/06_tts_dataset`) | — |
| **Wikipedia expansion** | draft/translate crh Wiki articles | MT + LM | [wikilangs/crh](https://huggingface.co/wikilangs/crh) |
| **crh keyboard w/ autocomplete/autocorrect** | daily typing aid (drives adoption) | LM ([goldfish](https://huggingface.co/goldfish-models/crh_latn_full), [wikilangs n-gram](https://huggingface.co/wikilangs/crh)) + [BPE tokenizer](https://huggingface.co/transhumanist-already-exists/crh_monocorpus-bpe-50_256) | — |
| **Spell checker** | flag unusual spellings (matters with 2 scripts) | LM | text corpora |
| **Translator crh↔ru/tr/en/uk** | diaspora, learners, officialdom | [crh-tr LLM](https://huggingface.co/mshamrai/crh-tur-llama32-1b-qlora) | [parallel-corpora](https://huggingface.co/datasets/QIRIM/crh-parallel-corpora) |
| **Semantic search over crh texts** | find content by meaning | [wikilangs fastText](https://huggingface.co/wikilangs/crh) | crh_web |

---

## 5. The data flywheel

Everything self-reinforces:
- **ASR** transcribes archives/media → more text + audio↔text pairs → better **TTS** and **MT**.
- **TTS + RVC** produce content → people listen & speak → more speech collected → better **ASR**.
- **MT** unlocks foreign content → dubbed into crh → more crh media.

For an endangered, low-resource language this is how you **bootstrap out of
low-resource** with your own tools instead of waiting for big-tech coverage.

## 6. Priority matrix (impact × feasibility, today)

| rank | product | why now |
|---|---|---|
| 1 | **Read-along reader / audiobooks** | TTS + text + video already in hand; instant visible content |
| 2 | **Dub cartoons into crh** | max emotional impact for kids/families; exercises the whole stack (MT+TTS+RVC+video) |
| 3 | **Keyboard + script converter** | daily practical tool; quietly moves crh into digital life |
| 4 | **Archive digitization** | time-sensitive (native speakers) heritage capture |

## 7. Related internal notes
- Resource-by-resource analysis: [crh_resources.md](crh_resources.md)
- TTS model journey & /q/ phoneme problem: [crh_tts_journey.md](crh_tts_journey.md)
- Parked build tasks: crh Whisper (`project_whisper_crh`), new RVC voice (`project_rvc_new_voice`).

> Links above are the canonical registry — update this table if a resource moves
> or a new crh model/dataset appears.
