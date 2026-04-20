"""ImageFolder classification — finetune a torchvision backbone.

Auto-resumes from checkpoints/epoch-*.pt if present (see submit.sh --resume).
"""
from __future__ import annotations

import argparse, json
from pathlib import Path

import torch
import torch.nn as nn
import torch.nn.functional as F
import yaml
from torch.utils.data import DataLoader
from torchvision import datasets, models, transforms


def latest_ckpt(ckpt_dir: Path) -> Path | None:
    ckpts = sorted(ckpt_dir.glob("epoch-*.pt"), key=lambda p: int(p.stem.split("-")[1]))
    return ckpts[-1] if ckpts else None


def build_model(backbone: str, num_classes: int, pretrained: bool) -> nn.Module:
    ctor = getattr(models, backbone)
    weights = "DEFAULT" if pretrained else None
    net = ctor(weights=weights)
    # Swap the classifier head. Works for resnet / efficientnet / convnext.
    if hasattr(net, "fc"):
        net.fc = nn.Linear(net.fc.in_features, num_classes)
    elif hasattr(net, "classifier") and isinstance(net.classifier, nn.Sequential):
        last = net.classifier[-1]
        net.classifier[-1] = nn.Linear(last.in_features, num_classes)
    else:
        raise RuntimeError(f"don't know how to swap head on {backbone}")
    return net


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

    device = torch.device(cfg["train"]["device"] if torch.cuda.is_available() or cfg["train"]["device"] == "cpu" else "cpu")
    print(f"[train] device={device}")

    root = Path(cfg["data"]["dataset_path"])
    size = cfg["data"]["image_size"]
    train_tfm = transforms.Compose([
        transforms.Resize((size, size)),
        transforms.RandomHorizontalFlip(),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ])
    val_tfm = transforms.Compose([
        transforms.Resize((size, size)),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ])
    ds_train = datasets.ImageFolder(root / "train", transform=train_tfm)
    ds_val = datasets.ImageFolder(root / "val", transform=val_tfm)
    classes = ds_train.classes
    print(f"[train] classes={classes}  n_train={len(ds_train)}  n_val={len(ds_val)}")

    dl_train = DataLoader(ds_train, batch_size=cfg["data"]["batch_size"], shuffle=True, num_workers=cfg["data"]["num_workers"], pin_memory=True)
    dl_val = DataLoader(ds_val, batch_size=cfg["data"]["batch_size"], shuffle=False, num_workers=cfg["data"]["num_workers"], pin_memory=True)

    model = build_model(cfg["model"]["backbone"], num_classes=len(classes), pretrained=cfg["model"]["pretrained"]).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=cfg["train"]["lr"])

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
        for i, (x, y) in enumerate(dl_train):
            x, y = x.to(device, non_blocking=True), y.to(device, non_blocking=True)
            opt.zero_grad()
            loss = F.cross_entropy(model(x), y)
            loss.backward()
            opt.step()
            if i % 20 == 0:
                print(f"[train] epoch={epoch} step={i}/{len(dl_train)} loss={loss.item():.4f}", flush=True)

        model.eval()
        correct = total = 0
        with torch.no_grad():
            for x, y in dl_val:
                x, y = x.to(device, non_blocking=True), y.to(device, non_blocking=True)
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
    torch.save({"state_dict": model.state_dict(), "classes": classes, "backbone": cfg["model"]["backbone"]}, final_path)
    (out / "metrics.json").write_text(json.dumps({
        "final_val_acc": history[-1]["val_acc"],
        "history": history,
        "classes": classes,
        "model_path": str(final_path.relative_to(out)),
    }, indent=2))
    print(f"[train] wrote {final_path}")


if __name__ == "__main__":
    main()
