# 01 — MNIST (built-in dataset)

**Simplest possible example.** Used to smoke-test the whole pipeline end-to-end. The MNIST dataset is downloaded automatically by `torchvision` on first run — **you don't upload any data**.

## Task
Digit classification (0–9) on 28×28 grayscale images with a tiny MLP.

## Data — nothing to upload
`torchvision.datasets.MNIST(..., download=True)` pulls the dataset into `dataset_path` (on Windows `/mnt/d/datasets/mnist/`). After the first run it's cached — subsequent runs reuse it.

## Run
```bash
./scripts/submit.sh experiments/01_mnist_builtin
```

## Output
- `models/<exp-id>/final_model/model.pt` — state dict
- `models/<exp-id>/metrics.json` — `{final_val_acc, history[]}`

Expected: ~97–98% val accuracy after 3 epochs on a GPU, ~1–2 min total.
