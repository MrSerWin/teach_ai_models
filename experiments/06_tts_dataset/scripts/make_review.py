#!/usr/bin/env python3
"""Generate an HTML page to listen to clips next to their text (QC by ear).

Usage: make_review.py <out_root> [slug]   # slug optional, filters one book
"""
import html
import json
import sys
from pathlib import Path

out = Path(sys.argv[1])
slug = sys.argv[2] if len(sys.argv) > 2 else None
rows = [json.loads(l) for l in (out / "dataset" / "segments.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
if slug:
    rows = [r for r in rows if r["book"] == slug]

cards = []
for r in rows:
    bg = "#fff" if r["keep"] else "#fde8e8"
    flag = "" if r["keep"] else f'<b style="color:#b00">⚠ {html.escape(r["reason"])}</b>'
    cards.append(f"""
    <div class="c" style="background:{bg}">
      <div class="m">{r['id']} · {r['dur']}s · score {r['score']} · cr {r['char_rate']} {flag}</div>
      <audio controls preload="none" src="wavs/{r['id']}.wav"></audio>
      <div class="t">{html.escape(r['text'])}</div>
      <div class="l">{html.escape(r.get('text_lat',''))}</div>
    </div>""")

title = slug or "all books"
doc = f"""<!doctype html><meta charset="utf-8"><title>review {title}</title>
<style>
body{{font:15px/1.5 system-ui;margin:24px;max-width:900px}}
.c{{border:1px solid #ddd;border-radius:8px;padding:10px 14px;margin:10px 0}}
.m{{color:#666;font-size:12px;margin-bottom:6px}}
.t{{margin-top:6px}} .l{{color:#247;margin-top:2px}}
audio{{width:100%}}
</style>
<h2>QC review — {title} ({len(rows)} clips)</h2>
<p>Cyrillic (black) + Latin (blue). Red = quarantined.</p>
{''.join(cards)}"""

dst = out / "dataset" / (f"review_{slug}.html" if slug else "review.html")
dst.write_text(doc, encoding="utf-8")
print(f"-> {dst}")
