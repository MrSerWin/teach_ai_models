"""Tabular MLP — regression or classification on CSV data.

Auto-resumes from checkpoints/epoch-*.pt if present (see submit.sh --resume).
"""
from __future__ import annotations

import argparse, json
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.nn.functional as F
import yaml
from torch.utils.data import DataLoader, TensorDataset


def latest_ckpt(ckpt_dir: Path) -> Path | None:
    ckpts = sorted(ckpt_dir.glob("epoch-*.pt"), key=lambda p: int(p.stem.split("-")[1]))
    return ckpts[-1] if ckpts else None


def load_split(root: Path, split: str, target_col: str):
    df = pd.read_csv(root / f"{split}.csv")
    if target_col not in df.columns:
        raise KeyError(f"'{target_col}' not in {split}.csv — columns are {list(df.columns)}")
    y = df[target_col].to_numpy()
    X = df.drop(columns=[target_col]).to_numpy(dtype=np.float32)
    return X, y


def build_mlp(in_dim: int, hidden: list[int], out_dim: int) -> nn.Module:
    layers = []
    prev = in_dim
    for h in hidden:
        layers += [nn.Linear(prev, h), nn.ReLU()]
        prev = h
    layers += [nn.Linear(prev, out_dim)]
    return nn.Sequential(*layers)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--output-dir", required=True)
    args = ap.parse_args()

    cfg = yaml.safe_load(Path(args.config).read_text())
    out = Path(args.output_dir)
    (out / "final_model").mkdir(parents=True, exist_ok=True)
    (out / "checkpoints").mkdir(parents=True, exist_ok=True)
    torch.manual_seed(cfg["seed"])
    np.random.seed(cfg["seed"])

    device = torch.device(cfg["train"]["device"] if torch.cuda.is_available() or cfg["train"]["device"] == "cpu" else "cpu")
    task = cfg["train"]["task"]
    assert task in {"regression", "classification"}

    root = Path(cfg["data"]["dataset_path"])
    target = cfg["data"]["target_column"]
    X_tr, y_tr = load_split(root, "train", target)
    X_va, y_va = load_split(root, "val", target)
    print(f"[train] task={task} n_train={len(X_tr)} n_val={len(X_va)} n_features={X_tr.shape[1]}")

    # z-score features using train stats
    mu, sd = X_tr.mean(0), X_tr.std(0) + 1e-6
    X_tr = (X_tr - mu) / sd
    X_va = (X_va - mu) / sd

    if task == "classification":
        classes = sorted(np.unique(np.concatenate([y_tr, y_va])).tolist())
        cls_to_idx = {c: i for i, c in enumerate(classes)}
        y_tr = np.array([cls_to_idx[c] for c in y_tr], dtype=np.int64)
        y_va = np.array([cls_to_idx[c] for c in y_va], dtype=np.int64)
        out_dim = len(classes)
        print(f"[train] classes={classes}")
    else:
        y_tr = y_tr.astype(np.float32)
        y_va = y_va.astype(np.float32)
        out_dim = 1
        classes = None

    tr_ds = TensorDataset(torch.from_numpy(X_tr), torch.from_numpy(y_tr))
    va_ds = TensorDataset(torch.from_numpy(X_va), torch.from_numpy(y_va))
    dl_tr = DataLoader(tr_ds, batch_size=cfg["data"]["batch_size"], shuffle=True, num_workers=cfg["data"]["num_workers"])
    dl_va = DataLoader(va_ds, batch_size=cfg["data"]["batch_size"], shuffle=False, num_workers=cfg["data"]["num_workers"])

    model = build_mlp(X_tr.shape[1], cfg["model"]["hidden_sizes"], out_dim).to(device)
    opt = torch.optim.Adam(model.parameters(), lr=cfg["train"]["lr"])

    ckpt_dir = out / "checkpoints"
    start_epoch = 1
    history: list[dict] = []
    last = latest_ckpt(ckpt_dir)
    if last is not None:
        print(f"[train] resuming from {last.name}")
        ck = torch.load(last, map_location=device)
        model.load_state_dict(ck["state_dict"])
        opt.load_state_dict(ck["optimizer"])
        start_epoch = ck["epoch"] + 1
        history = ck.get("history", [])

    total_epochs = cfg["train"]["epochs"]
    for epoch in range(start_epoch, total_epochs + 1):
        model.train()
        for x, y in dl_tr:
            x, y = x.to(device), y.to(device)
            opt.zero_grad()
            pred = model(x)
            if task == "regression":
                loss = F.mse_loss(pred.squeeze(-1), y)
            else:
                loss = F.cross_entropy(pred, y)
            loss.backward()
            opt.step()

        model.eval()
        with torch.no_grad():
            if task == "regression":
                preds, ys = [], []
                for x, y in dl_va:
                    preds.append(model(x.to(device)).squeeze(-1).cpu().numpy())
                    ys.append(y.numpy())
                preds = np.concatenate(preds); ys = np.concatenate(ys)
                rmse = float(np.sqrt(((preds - ys) ** 2).mean()))
                print(f"[train] epoch={epoch} val_rmse={rmse:.4f}", flush=True)
                history.append({"epoch": epoch, "val_rmse": rmse})
            else:
                correct = total = 0
                for x, y in dl_va:
                    correct += (model(x.to(device)).argmax(1).cpu() == y).sum().item()
                    total += y.size(0)
                acc = correct / total
                print(f"[train] epoch={epoch} val_acc={acc:.4f}", flush=True)
                history.append({"epoch": epoch, "val_acc": acc})

        torch.save({
            "state_dict": model.state_dict(),
            "optimizer": opt.state_dict(),
            "epoch": epoch,
            "history": history,
        }, ckpt_dir / f"epoch-{epoch}.pt")

    final_path = out / "final_model" / "model.pt"
    torch.save({
        "state_dict": model.state_dict(),
        "task": task,
        "classes": classes,
        "feature_mean": mu.tolist(),
        "feature_std": sd.tolist(),
        "hidden_sizes": cfg["model"]["hidden_sizes"],
        "in_dim": int(X_tr.shape[1]),
    }, final_path)
    (out / "metrics.json").write_text(json.dumps({
        "task": task,
        "final": history[-1],
        "history": history,
        "classes": classes,
        "n_features": int(X_tr.shape[1]),
    }, indent=2))
    print(f"[train] wrote {final_path}")


if __name__ == "__main__":
    main()
