# RVC voice-cloning — полный процесс (end-to-end)

Master-документ всего пайплайна: от сырого аудио до сданного дубляжа.
Подробности по каждому шагу — в специализированных файлах (ссылки по ходу).
Карта документов:

| Документ | О чём |
|---|---|
| **этот файл** | сквозной процесс, порядок шагов, что чем запускать |
| [README.md](README.md) | детали обучения, гиперпараметры по голосам, претрейны |
| [DATASETS.md](DATASETS.md) | где искать голоса-доноры под каждого персонажа |
| [../../RVC_TZ_Crimean_Tatar_Cartoon.md](../../RVC_TZ_Crimean_Tatar_Cartoon.md) | исходное ТЗ заказчика |

Машинная схема: **Mac готовит → Windows/WSL (GPU) обучает и генерит → Mac забирает.**
Базовый транспорт — те же `scripts/*.sh` что и для остальных экспериментов
(submit/fetch/...). RVC-специфика живёт в [scripts/rvc/](../../scripts/rvc/).

---

## Этап 0 — однократная настройка

**Windows / WSL:** Applio CLI + conda env (см. [README.md](README.md) §«Одноразовая настройка»).
**Mac:** инструменты подготовки данных:
```bash
brew install yt-dlp ffmpeg
pip install librosa soundfile ffmpeg-normalize
```

---

## Этап 1 — подготовка датасета (Mac)

Цель: 20–30 мин **чистого голоса ОДНОГО человека** на персонажа (RVC учит один
тембр — мульти-спикер корпуса не годятся, см. [DATASETS.md](DATASETS.md)).

```bash
# YouTube / локальные файлы / папка — всё на вход prep-скрипта.
# qzip URL в кавычки (zsh ест '?').
YT_COOKIES_BROWSER=safari \
  ./scripts/rvc/prep-rvc-dataset.sh ./data/teacher \
  "https://youtu.be/VIDEO_ID" ./extra_local_clips/
```
[prep-rvc-dataset.sh](../../scripts/rvc/prep-rvc-dataset.sh) делает: download →
mono/48k → нарезка 4–10 с (с merge коротких пауз) → нормализация -23 LUFS/-3 dB.

**Обязательная ручная работа (не пропускать):**
1. **UVR5 GUI** (на Win) на сырых `_raw/`: MDX-Net Voc FT → DeNoise → DeEcho-DeReverb.
2. **Прослушать** каждый `data/teacher/*.wav`, удалить мусор (кашель, чужие
   голоса, музыка, оговорки). Самый высокий ROI всего пайплайна.

Опционально проверить покрытие фонем крым.тат (ñ/q/ğ/ç/ş):
```bash
python scripts/rvc/phoneme-coverage.py data/teacher
```

---

## Этап 2 — залить датасет на Windows

```bash
./scripts/push-data.sh ./data/teacher rvc/teacher
# → /mnt/d/datasets/rvc/teacher/  (путь уже прописан в characters/03_teacher.yaml)
```
Идемпотентно: повторный запуск дольёт только дельту.

---

## Этап 3 — обучение

Один `train.py` + 5 пресетов в [characters/](characters/). `submit.sh` всегда
читает `config.yaml`, поэтому перед запуском копируем нужный пресет в него:

```bash
cp experiments/04_rvc_voice_clone/characters/03_teacher.yaml \
   experiments/04_rvc_voice_clone/config.yaml
./scripts/submit.sh experiments/04_rvc_voice_clone        # shared env, live-логи
```

Все 5 голосов очередью под GPU-локом:
```bash
for c in 01_narrator 02_boy 03_teacher 04_girl 05_grandpa; do
  cp experiments/04_rvc_voice_clone/characters/$c.yaml \
     experiments/04_rvc_voice_clone/config.yaml
  ./scripts/submit.sh -d --queue experiments/04_rvc_voice_clone
done
./scripts/list.sh        # наблюдать как очередь рассасывается
```

Недотрен → поднять `epochs` в YAML и `./scripts/submit.sh --resume <exp-id>`
(Applio подхватит последний `G_*.pth`). Гиперпараметры по голосам — в
[README.md](README.md) §«Гиперпараметры».

---

## Этап 4 — забрать и выбрать лучшую эпоху (A/B по слуху)

```bash
./scripts/fetch.sh <exp-id>      # → models/<exp-id>/final_model/{<name>.pth,.index,checkpoints/}
```

Прогнать одну тестовую начитку через несколько чекпоинтов и сравнить ушами:
```bash
./scripts/rvc/infer.sh teacher /path/to/test_crh.wav \
  --epochs "200 250 280 best" --pitch 12 --index-rate 0.5
# результаты → models/teacher_tests/*.wav  →  open models/teacher_tests
```
[infer.sh](../../scripts/rvc/infer.sh) — все параметры (pitch, index-rate,
protect, formant для кросс-гендера) задокументированы в его шапке. ТЗ §5.4 —
выбор эпохи по слуху, поэтому fetch тянет 5 последних снэпшотов.

---

## Этап 5 — дубляж (генерация)

Когда модели приняты — пакетный дубляж папки исходных реплик. Персонаж
определяется по имени родительской папки (крым.тат роль-слова) либо форсится
`--role`:

```bash
./scripts/rvc/dub.sh ./scripts/Mult/episode_01
# → models/episode_01_dubbed/  (зеркалит структуру входа)

# форсировать одного персонажа для всей папки:
./scripts/rvc/dub.sh --role narrator ./scripts/Mult/intro
```
[dub.sh](../../scripts/rvc/dub.sh): аплоад дерева → один проход инференса на Win
(3 модели покрывают 5 ролей через pitch/formant-рецепты) → скачивание дубляжа.
**Резюмируемо** — повторный запуск пропускает уже озвученные файлы и дотягивает
упавшие.

Текущая раскладка ролей (из dub.sh):

| Папка-ключ | Роль | Модель | pitch | formant |
|---|---|---|---|---|
| `*oca*` | teacher | teacher | +12 | — |
| `*qartbaba*` | grandpa | narrator v1 | −4 | — |
| `*qiz*` | girl | teacher | +17 | 1.4 |
| `*oglan*` | boy | narrator_v2 | +10 | 1.2 |
| прочее | narrator | narrator_v2 | −1 | — |

---

## Этап 6 — сдача (ТЗ §7)

После приёмки всех голосов — реорганизовать поставку вручную:
```bash
mkdir -p models/release/{01_narrator,02_boy,03_teacher,04_girl,05_grandpa}
cp models/<exp-id-teacher>/final_model/teacher.{pth,index} models/release/03_teacher/
# …аналогично остальные
```
Дубляж эпизодов — в `models/<episode>_dubbed/`.

---

## Карта артефактов (что где лежит)

```
data/<character>/*.wav                       сырой подготовленный датасет (Mac, gitignored)
/mnt/d/datasets/rvc/<character>/             датасет на Win (после push-data)
/mnt/d/runs/<exp-id>/                        прогон обучения на Win
/home/<user>/applio/logs/<model>/            чекпоинты + .index (Win, живут для resume/infer)
models/<exp-id>/final_model/                 забранная модель (.pth/.index/checkpoints)
models/<model>_tests/                        A/B результаты infer.sh
models/<episode>_dubbed/                     готовый дубляж (зеркало входа)
models/release/                              финальная поставка по ТЗ
```

## Типовые грабли (уже отловлены)

- **`?` в YouTube-URL** → zsh-глоб. Кавычки или убрать `?si=...`.
- **YouTube 403/SABR** → `YT_COOKIES_BROWSER=safari` перед prep.
- **MP4 переименован в .wav** → infer/dub сами прогоняют через ffmpeg в 40k mono.
- **WSL IP слетел после ребута Win** → portproxy чинится сам ([scripts/windows/](../../scripts/windows/)).
- **requirements.txt extras в shared-env** → не ставятся (засорят общий env); нужен `--clone`.
