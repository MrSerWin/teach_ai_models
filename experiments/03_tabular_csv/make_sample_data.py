"""Generate a toy tabular dataset for quick end-to-end testing.

Produces train.csv and val.csv with 5 numeric features and a target column.
Default task = regression (y = linear combo + noise). Pass --classification
to instead produce binary labels.

Then upload once:
  ./scripts/push-data.sh experiments/03_tabular_csv/sample_data demo_tabular
"""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

OUT = Path(__file__).parent / "sample_data"
N_TRAIN, N_VAL = 2000, 500
N_FEATURES = 5


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--classification", action="store_true")
    args = ap.parse_args()

    rng = np.random.default_rng(0)
    weights = rng.normal(size=N_FEATURES)

    def make(n: int) -> pd.DataFrame:
        X = rng.normal(size=(n, N_FEATURES))
        signal = X @ weights
        if args.classification:
            y = (signal > 0).astype(int)
        else:
            y = signal + rng.normal(scale=0.3, size=n)
        cols = {f"x{i}": X[:, i] for i in range(N_FEATURES)}
        cols["y"] = y
        return pd.DataFrame(cols)

    OUT.mkdir(parents=True, exist_ok=True)
    make(N_TRAIN).to_csv(OUT / "train.csv", index=False)
    make(N_VAL).to_csv(OUT / "val.csv", index=False)
    task = "classification" if args.classification else "regression"
    print(f"wrote {task} demo dataset -> {OUT}  (train={N_TRAIN}, val={N_VAL}, features={N_FEATURES})")


if __name__ == "__main__":
    main()
