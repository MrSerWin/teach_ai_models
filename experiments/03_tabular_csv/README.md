# 03 — Tabular CSV (regression or classification)

MLP on flat tabular data in CSV. Pick `regression` or `classification` via `config.yaml`.

## Task
- **Regression** (default): predict a real-valued target, loss = MSE, metric = RMSE.
- **Classification**: predict a discrete label, loss = cross-entropy, metric = accuracy.

## Required dataset layout

Two CSV files with the same columns:

```
/mnt/d/datasets/my_data/
├── train.csv
└── val.csv
```

**Example `train.csv`:**

```
age,income,credit_score,n_dependents,y
35,75000,720,1,1
42,52000,610,3,0
28,98000,780,0,1
...
```

**Rules:**
- Every column except the target is treated as a **numeric feature** (strings / dates / booleans will fail — convert them first).
- Target column name is set in `config.yaml` (`data.target_column`, default `y`).
- For **classification**: the target can be ints or strings — mapped to class indices internally.
- For **regression**: the target must be numeric.
- `train.csv` and `val.csv` must have identical columns.
- Features are z-scored using train statistics (no leakage).

## How to upload your data

```bash
# prepare locally:
~/my_data/
├── train.csv
└── val.csv

# upload:
./scripts/push-data.sh ~/my_data my_data

# edit config.yaml:
#   data.dataset_path: /mnt/d/datasets/my_data
#   data.target_column: <your-target-column-name>
#   train.task: regression  (or classification)
```

## Try it with a demo dataset

```bash
# regression demo (y = linear combo of 5 features + noise):
python experiments/03_tabular_csv/make_sample_data.py

# or a classification demo:
python experiments/03_tabular_csv/make_sample_data.py --classification

./scripts/push-data.sh experiments/03_tabular_csv/sample_data demo_tabular

# config.yaml already points at /mnt/d/datasets/demo_tabular.
# If you ran with --classification, also change train.task: classification

./scripts/submit.sh experiments/03_tabular_csv
```

## Tune for your data

| Key                | Meaning                                                    |
|--------------------|------------------------------------------------------------|
| `target_column`    | Name of the column to predict                              |
| `model.hidden_sizes` | List, e.g. `[128, 64]` = two hidden layers               |
| `train.task`       | `regression` or `classification` — must match the target  |
| `train.epochs`     | Tabular models usually converge in 20–100 epochs           |

## Output
- `models/<exp-id>/final_model/model.pt` — dict with state_dict + task + classes (if any) + feature mean/std (so you can normalise inputs at inference time) + architecture dims.
- `models/<exp-id>/metrics.json` — final RMSE (regression) or accuracy (classification), per-epoch history.
