#!/usr/bin/env python3
"""Batch Crimean-Tatar Cyrillic -> Latin via the project's JS transliterator.

Shells out once to translit_bridge.mjs (Node), passing a JSON array of strings
and reading back the transliterated array. Used for two things:
  * the Latin dataset text (context-aware, sentence-level), and
  * a high-quality romanization source for forced alignment (folded to a-z+').
"""
import json
import subprocess
from pathlib import Path

_BRIDGE = Path(__file__).resolve().parent / "translit_bridge.mjs"


def translit_batch(strings):
    """Cyrillic -> Latin for a list of strings (order preserved)."""
    items = list(strings)
    if not items:
        return []
    proc = subprocess.run(
        ["node", str(_BRIDGE)],
        input=json.dumps(items, ensure_ascii=False),
        capture_output=True, text=True, check=True,
    )
    out = json.loads(proc.stdout)
    if len(out) != len(items):
        raise RuntimeError(f"translit count mismatch {len(out)} != {len(items)}")
    return out


if __name__ == "__main__":
    import sys
    print("\n".join(translit_batch([l.rstrip("\n") for l in sys.stdin])))
