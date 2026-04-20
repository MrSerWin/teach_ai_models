#!/usr/bin/env python3
"""Render a MODEL_CARD.md from a fetched experiment dir.

Usage: python3 _model_card.py <models/exp-id>
Reads metrics.json + git_info.json + config.yaml from that dir; writes
MODEL_CARD.md next to them. Designed to be called by fetch.sh.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path


def load_json(p: Path):
    try:
        return json.loads(p.read_text())
    except FileNotFoundError:
        return None


def read_text(p: Path) -> str:
    try:
        return p.read_text().strip()
    except FileNotFoundError:
        return ""


def format_metric_table(history: list[dict]) -> str:
    if not history:
        return "_(no epoch history recorded)_"
    keys = [k for k in history[0].keys() if k != "epoch"]
    head = "| epoch | " + " | ".join(keys) + " |"
    sep = "|" + "|".join(["---"] * (len(keys) + 1)) + "|"
    rows = []
    for row in history:
        cells = [str(row.get("epoch", ""))]
        for k in keys:
            v = row.get(k, "")
            cells.append(f"{v:.4f}" if isinstance(v, float) else str(v))
        rows.append("| " + " | ".join(cells) + " |")
    return "\n".join([head, sep, *rows])


def main() -> None:
    if len(sys.argv) != 2:
        print("usage: _model_card.py <models/exp-id>", file=sys.stderr)
        sys.exit(2)

    exp_dir = Path(sys.argv[1]).resolve()
    metrics = load_json(exp_dir / "metrics.json") or {}
    git = load_json(exp_dir / "git_info.json") or {}
    status = read_text(exp_dir / "status") or "unknown"
    cfg_text = read_text(exp_dir / "config.yaml")

    exp_id = exp_dir.name
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    history = metrics.get("history", [])
    final = {k: v for k, v in metrics.items() if k not in {"history"}}

    commit = git.get("commit") or "—"
    branch = git.get("branch") or "—"
    dirty = git.get("dirty")
    dirty_tag = " **(dirty working tree)**" if dirty else ""
    submitted_at = git.get("submitted_at", "—")
    subject = (git.get("subject") or "").strip()
    remote = git.get("remote") or ""

    lines = [
        f"# {exp_id}",
        "",
        f"- **status:** `{status}`",
        f"- **fetched:** {now}",
        f"- **submitted:** {submitted_at}",
        f"- **commit:** `{commit}`{dirty_tag}",
        f"- **branch:** `{branch}`",
    ]
    if subject:
        lines.append(f"- **commit subject:** {subject}")
    if remote:
        lines.append(f"- **remote:** {remote}")

    lines += [
        "",
        "## Final metrics",
        "",
        "```json",
        json.dumps(final, indent=2),
        "```",
        "",
        "## Per-epoch history",
        "",
        format_metric_table(history),
        "",
        "## Config",
        "",
        "```yaml",
        cfg_text,
        "```",
        "",
        "## Artifacts",
        "",
        "- `final_model/` — the trained model (whatever your `train.py` saved there)",
        "- `metrics.json` — machine-readable metrics",
        "- `train.log` — full training stdout",
        "- `git_info.json` — code provenance",
        "",
    ]

    out = exp_dir / "MODEL_CARD.md"
    out.write_text("\n".join(lines))
    print(f"[model-card] wrote {out}")


if __name__ == "__main__":
    main()
