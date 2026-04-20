"""Minimal PyTorch training script.

Contract with submit.sh:
  python train.py --config <path> --output-dir <path>

Writes to <output-dir>:
  final_model/model.pt   final artifact (fetched back to Mac)
  metrics.json           summary metrics (fetched back)
  checkpoints/*.pt       per-epoch state (stays on Windows; used for resume)

Auto-resume: on startup, the script looks in <output-dir>/checkpoints/ for the
highest-numbered epoch-N.pt and picks up where it left off. Triggered by
`./scripts/submit.sh --resume <exp-id>` which reuses the same output dir.
"""
from __future__ import annotations

import argparse, json, random
from pathlib import Path

import torch
import torch.nn as nn
import torch.nn.functional as F
import yaml
from torch.utils.data import DataLoader
from torchvision import datasets, transforms


class MLP(nn.Module):
    def __init__(self, hidden_size: int):
        super().__init__()
        self.fc1 = nn.Linear(28 * 28, hidden_size)
        self.fc2 = nn.Linear(hidden_size, 10)

    def forward(self, x):
        x = x.view(x.size(0), -1)
        return self.fc2(F.relu(self.fc1(x)))


def latest_ckpt(ckpt_dir: Path) -> Path | None:
    ckpts = sorted(ckpt_dir.glob("epoch-*.pt"), key=lambda p: int(p.stem.split("-")[1]))
    return ckpts[-1] if ckpts else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--output-dir", required=True)
    args = ap.parse_args()

    cfg = yaml.safe_load(Path(args.config).read_text())
    out = Path(args.output_dir)
    (out / "final_model").mkdir(parents=True, exist_ok=True)
    ckpt_dir = out / "checkpoints"
    ckpt_dir.mkdir(parents=True, exist_ok=True)

    random.seed(cfg["seed"])
    torch.manual_seed(cfg["seed"])

    device = torch.device(cfg["train"]["device"] if torch.cuda.is_available() or cfg["train"]["device"] == "cpu" else "cpu")
    print(f"[train] device={device}")

    tfm = transforms.Compose([transforms.ToTensor(), transforms.Normalize((0.1307,), (0.3081,))])
    ds_train = datasets.MNIST(cfg["data"]["dataset_path"], train=True, download=True, transform=tfm)
    ds_test = datasets.MNIST(cfg["data"]["dataset_path"], train=False, download=True, transform=tfm)
    dl_train = DataLoader(ds_train, batch_size=cfg["data"]["batch_size"], shuffle=True, num_workers=cfg["data"]["num_workers"])
    dl_test = DataLoader(ds_test, batch_size=512, shuffle=False, num_workers=cfg["data"]["num_workers"])

    model = MLP(cfg["model"]["hidden_size"]).to(device)
    opt = torch.optim.Adam(model.parameters(), lr=cfg["train"]["lr"])

    # Resume if a prior run left checkpoints behind.
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
    if start_epoch > total_epochs:
        print(f"[train] already completed ({start_epoch - 1}/{total_epochs} epochs) — writing final artifacts")

    for epoch in range(start_epoch, total_epochs + 1):
        model.train()
        for i, (x, y) in enumerate(dl_train):
            x, y = x.to(device), y.to(device)
            opt.zero_grad()
            loss = F.cross_entropy(model(x), y)
            loss.backward()
            opt.step()
            if i % 100 == 0:
                print(f"[train] epoch={epoch} step={i} loss={loss.item():.4f}", flush=True)

        model.eval()
        correct = total = 0
        with torch.no_grad():
            for x, y in dl_test:
                x, y = x.to(device), y.to(device)
                correct += (model(x).argmax(1) == y).sum().item()
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
    torch.save(model.state_dict(), final_path)
    metrics = {
        "final_val_acc": history[-1]["val_acc"],
        "history": history,
        "model_path": str(final_path.relative_to(out)),
    }
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2))
    print(f"[train] wrote {final_path}")


if __name__ == "__main__":
    main()
