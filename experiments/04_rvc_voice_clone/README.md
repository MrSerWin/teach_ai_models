# 04_rvc_voice_clone — RVC v2 для крымскотатарского мультфильма

5 голосов из ТЗ ([RVC_TZ_Crimean_Tatar_Cartoon.md](../../RVC_TZ_Crimean_Tatar_Cartoon.md)):
narrator / boy / teacher / girl / grandpa. Один `train.py` + 5 пресетов в
[characters/](characters/).

## Архитектура

`train.py` — тонкий оркестратор поверх **Applio** CLI:

```
preprocess  →  extract (rmvpe + contentvec)  →  train  →  index  →  copy → final_model/
```

Финальный артефакт каждой модели: `<name>.pth` + `<name>.index` + 5 последних
снэпшотов в `final_model/checkpoints/` (для выбора лучшей эпохи по слуху, §5.4 ТЗ).

## Одноразовая настройка на Windows (WSL Ubuntu)

```bash
# В ml_base (или клоне) на Win/WSL:
cd /mnt/d
git clone https://github.com/IAHispano/Applio.git applio
cd applio
pip install -r requirements.txt
# (Applio сам подкачает базовые претрейны при первом train.)
echo 'export APPLIO_DIR=/mnt/d/applio' >> ~/.bashrc
```

Дальше `train.py` сам скачает Ov2Super 48k в
`$APPLIO_DIR/rvc/models/pretraineds/pretraineds_custom/` при первом запуске.

## Pipeline на каждый голос

### 1. Подготовить датасет (на Mac)

ТЗ §4 — обязательная очистка:
- UVR5 GUI (Win): MDX-Net Voc FT → DeNoise → DeEcho-DeReverb
- Нарезка 4–10 сек (audio-slicer)
- Нормализация -3 dB peak / -23 LUFS (ffmpeg-normalize)
- **Ручная фильтрация** — слушать всё, выкидывать мусор

Складывайте в `./data/<character>/*.wav` локально на Mac.

### 2. Залить датасет на Win

```bash
./scripts/push-data.sh ./data/narrator rvc/narrator
# окажется в /mnt/d/datasets/rvc/narrator/ — путь уже прописан в characters/01_narrator.yaml
```

### 3. Запустить обучение

Каждый персонаж — отдельный submit (5 запусков, последовательно или с `--queue`):

```bash
# Скопировать пресет в config.yaml — submit.sh всегда читает его:
cp experiments/04_rvc_voice_clone/characters/01_narrator.yaml \
   experiments/04_rvc_voice_clone/config.yaml

./scripts/submit.sh experiments/04_rvc_voice_clone
# повторить для 02_boy, 03_teacher, 04_girl, 05_grandpa
```

Или одной строкой через цикл (с `--queue` — встанут в очередь под GPU lock):

```bash
for char in 01_narrator 02_boy 03_teacher 04_girl 05_grandpa; do
  cp experiments/04_rvc_voice_clone/characters/${char}.yaml \
     experiments/04_rvc_voice_clone/config.yaml
  ./scripts/submit.sh -d --queue experiments/04_rvc_voice_clone
done
```

### 4. Если недотрен — продолжить с того же чекпойнта

```bash
# подними epochs в config.yaml до 450, затем:
./scripts/submit.sh --resume <exp-id>
```

Applio сам поднимет последний `G_*.pth` из `logs/<model_name>/`.

### 5. Забрать модели

```bash
./scripts/fetch.sh <exp-id>     # положит в models/<exp-id>/final_model/
```

## Гиперпараметры под каждый голос

Уже зашиты в `characters/*.yaml`. Главные отличия:

| Голос | hop_length | epochs | Заметки |
|-------|------------|--------|---------|
| narrator | 128 | 300 | Стандарт |
| boy | 64 | 350 | Маленький hop под быструю F0 |
| teacher | 128 | 300 | Стандарт |
| girl | 64 | 350 | Маленький hop |
| grandpa | 160 | 300 | Большой hop — F0 двигается медленно |

Batch size = 8 (под 8GB VRAM). Если GPU мощнее — поднимите в YAML.

## Выбор претрейна

`pretrained` в YAML:
- **`ov2super_48k`** *(дефолт)* — community pretrain, лучший на маленьких датасетах
  (10–30 мин). Быстрая сходимость, чище на низких эпохах.
- **`ov2super_40k`** — если переключаетесь на `sample_rate: 40000`.
- **`default`** — стандартный `f0G/D{sr}k.pth` от Applio. Fallback, если
  Ov2Super даёт металлические артефакты на конкретном голосе.

**Заметка по языку:** RVC учит тембр, фонемы — задача универсального
ContentVec/HuBERT. Турецко-специфичных RVC-претрейнов в обиходе нет (это не
XTTS). Не тратьте время на поиск — Ov2Super справится с ñ/q/ğ/ç/ş при условии,
что они есть в тренировочном датасете.

## Тестовая проверка (ТЗ §6)

После `fetch.sh` — открыть Applio WebUI на Win, загрузить `.pth` + `.index` из
`models/<exp-id>/final_model/`, прогнать тестовую начитку на крымскотатарском.
Если артефакты или «не похоже» — в `final_model/checkpoints/` лежат 5
последних эпох, прогоните каждую через тот же тестовый файл, выберите лучшую
по слуху.

## Структура поставки по ТЗ §7

После всех 5 fetch — реорганизовать в `models/release/` руками:

```bash
mkdir -p models/release/{01_narrator,02_boy,03_teacher,04_girl,05_grandpa}
cp models/<exp-id-narrator>/final_model/narrator.{pth,index} models/release/01_narrator/
# ...и так далее
```
