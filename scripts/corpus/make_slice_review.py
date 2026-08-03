#!/usr/bin/env python3
"""Build SLICES.html — fix the transcripts that had to be cut out of a collection.

When the recording is one work and the book is an anthology, `stage_alignment.py`
locates the work's title and takes a span of the expected length. The start is
usually right; the end is a guess from the speech-rate estimate, and the start
can be off by a paragraph. A forced aligner will not complain about either — it
will stretch whatever text it is given across the audio.

So this page puts the three things side by side: the recording, the proposed
transcript as an editable box, and the book's full text with search. Listen to
the opening, make the box start where the reader starts; listen to the end, cut
where they stop. Export, then apply with `apply_slice_review.py`.

    python3 make_slice_review.py
"""
from __future__ import annotations

import hashlib
import html
import json
import os

LIBRARY = "/Volumes/T9/AnaYurt/Books/Qirimtatar"
STAGE = os.path.join(LIBRARY, "align-staging")
REVIEW = os.path.join(STAGE, "needs-review")
OUT = os.path.join(REVIEW, "SLICES.html")
FULL_TEXT_LIMIT = 400_000


def full_book_text(book_rel: str) -> str:
    import subprocess
    path = os.path.join(LIBRARY, book_rel)
    if not os.path.exists(path):
        return ""
    try:
        r = subprocess.run(["nice", "-n", "19", "pdftotext", "-q", path, "-"],
                           capture_output=True, text=True, timeout=600)
        return r.stdout[:FULL_TEXT_LIMIT]
    except Exception:
        return ""


def main() -> None:
    items = []
    for name in sorted(os.listdir(REVIEW)):
        folder = os.path.join(REVIEW, name)
        if not os.path.isdir(folder):
            continue
        tpath = os.path.join(folder, "transcript.txt")
        spath = os.path.join(folder, "SOURCE.md")
        if not os.path.exists(tpath):
            continue
        meta = open(spath).read() if os.path.exists(spath) else ""
        book = ""
        for line in meta.splitlines():
            if line.startswith("- book:"):
                book = line.split("`")[1] if "`" in line else ""
        audio = next((f for f in sorted(os.listdir(folder))
                      if f.lower().endswith((".mp3", ".m4a", ".wav"))), None)
        items.append({
            "name": name, "book": book, "meta": meta,
            "audio": f"{name}/{audio}" if audio else "",
            "text": open(tpath, errors="ignore").read(),
            "full": full_book_text(book),
            "id": hashlib.sha1(name.encode()).hexdigest()[:12],
        })
        print(f"  {name}: transcript {len(items[-1]['text'])} chars, "
              f"book text {len(items[-1]['full'])} chars", flush=True)

    cards = []
    for it in items:
        media = (f'<audio controls preload="none" src="{html.escape(it["audio"])}"></audio>'
                 if it["audio"] else '<span class="muted">аудио не найдено</span>')
        cards.append(f"""
<article class="card" data-id="{it['id']}" data-name="{html.escape(it['name'])}">
  <h3>{html.escape(it['name'])}</h3>
  <p class="book">Сборник: <code>{html.escape(it['book'])}</code></p>
  <div class="media">{media}</div>
  <p class="hint">Послушайте <b>начало</b> — текст в поле должен начинаться с тех же слов.
     Затем перемотайте в <b>конец</b> и обрежьте лишнее. Ищите нужное место в полном
     тексте книги ниже и переносите оттуда.</p>
  <label>Транскрипт для выравнивания
    <textarea data-text rows="14">{html.escape(it['text'])}</textarea>
  </label>
  <div class="row">
    <span class="stat" data-stat></span>
    <button class="ok" data-v="ok">Годится</button>
    <button class="no" data-v="reject">Не то произведение</button>
    <button class="rst" data-reset>Вернуть исходный срез</button>
  </div>
  <details>
    <summary>Полный текст книги ({len(it['full'])} знаков) — для поиска нужного места</summary>
    <input class="search" data-search placeholder="найти в книге…">
    <pre data-full>{html.escape(it['full'])}</pre>
  </details>
  <div class="state" data-state></div>
</article>""")

    payload = json.dumps([{"id": i["id"], "name": i["name"], "book": i["book"],
                           "original": i["text"]} for i in items], ensure_ascii=False)

    page = f"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Срезы из сборников — проверка</title>
<style>
:root {{ color-scheme: light dark; --bg:#fff; --fg:#1a1a1a; --mut:#6b7280;
  --line:#e5e7eb; --card:#fff; --accent:#2563eb; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#0f1115; --fg:#e8eaed;
  --mut:#9aa0a6; --line:#2a2f3a; --card:#161a21; }} }}
* {{ box-sizing:border-box; }}
body {{ margin:0; padding:24px 16px 96px; background:var(--bg); color:var(--fg);
  font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; }}
.wrap {{ max-width:900px; margin:0 auto; }}
h1 {{ font-size:22px; margin:0 0 8px; }}
.lead {{ color:var(--mut); }}
.steps {{ background:var(--card); border:1px solid var(--line); border-radius:10px;
  padding:12px 16px; margin:16px 0 20px; }}
.steps li {{ margin:4px 0; }}
.bar {{ position:sticky; top:0; z-index:5; background:var(--bg); padding:10px 0;
  border-bottom:1px solid var(--line); margin-bottom:16px; display:flex; gap:10px;
  align-items:center; }}
.bar button {{ font:inherit; padding:7px 12px; border-radius:8px; cursor:pointer;
  border:1px solid var(--line); background:var(--card); color:var(--fg); }}
.bar .primary {{ background:var(--accent); color:#fff; border-color:transparent; }}
.count {{ color:var(--mut); margin-left:auto; }}
.card {{ border:1px solid var(--line); border-radius:12px; padding:16px;
  margin-bottom:16px; background:var(--card); }}
h3 {{ margin:0 0 4px; font-size:17px; }}
.book code {{ font-size:12px; color:var(--mut); word-break:break-all; }}
.hint {{ font-size:13px; color:var(--mut); }}
audio {{ width:100%; margin:6px 0 10px; }}
label {{ display:block; font-size:13px; color:var(--mut); }}
textarea {{ width:100%; font:13px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace;
  margin-top:6px; padding:10px; border-radius:8px; border:1px solid var(--line);
  background:var(--bg); color:var(--fg); resize:vertical; }}
.row {{ display:flex; gap:8px; align-items:center; margin:10px 0; flex-wrap:wrap; }}
.row button {{ font:inherit; padding:8px 14px; border-radius:8px; cursor:pointer;
  border:1px solid var(--line); background:transparent; color:var(--fg); }}
.row button.sel {{ color:#fff; border-color:transparent; }}
.ok.sel {{ background:#16a34a; }} .no.sel {{ background:#dc2626; }}
.stat {{ font-size:12px; color:var(--mut); margin-right:auto; }}
details {{ margin-top:8px; }}
summary {{ cursor:pointer; font-size:13px; color:var(--accent); }}
.search {{ width:100%; font:inherit; padding:8px; margin:8px 0; border-radius:8px;
  border:1px solid var(--line); background:var(--bg); color:var(--fg); }}
pre {{ max-height:340px; overflow:auto; white-space:pre-wrap; font-size:12px;
  color:var(--mut); border-left:3px solid var(--line); padding-left:10px; }}
mark {{ background:#fde68a; color:#111; }}
.state {{ font-size:12px; color:#16a34a; min-height:16px; }}
</style></head><body><div class="wrap">
<h1>Срезы из сборников — проверка</h1>
<p class="lead">Запись — одно произведение, книга — сборник. Машина вырезала кусок
по названию, но границы приблизительные.</p>
<ol class="steps">
  <li>Включите запись и послушайте <b>первые секунды</b>.</li>
  <li>Текст в поле должен начинаться <b>с тех же слов</b>. Если нет — найдите нужное
      место в полном тексте книги (раскройте панель внизу карточки) и поправьте.</li>
  <li>Перемотайте в <b>конец записи</b> и обрежьте текст там, где чтец замолкает.</li>
  <li>Нажмите «Годится». Если книга вообще не та — «Не то произведение».</li>
  <li>В конце — «Скачать правки».</li>
</ol>
<div class="bar">
  <button id="export" class="primary">Скачать правки</button>
  <span class="count" id="count"></span>
</div>
{''.join(cards)}
</div>
<script>
const ITEMS = {payload};
const KEY = 'crh-slice-review-v1';
const store = JSON.parse(localStorage.getItem(KEY) || '{{}}');
const byId = Object.fromEntries(ITEMS.map(i => [i.id, i]));

function save() {{ localStorage.setItem(KEY, JSON.stringify(store)); paint(); }}
function touch(id) {{ store[id] = store[id] || {{}}; return store[id]; }}

function paint() {{
  let done = 0;
  document.querySelectorAll('.card').forEach(card => {{
    const id = card.dataset.id, rec = store[id] || {{}};
    card.querySelectorAll('.row button[data-v]').forEach(b =>
      b.classList.toggle('sel', rec.verdict === b.dataset.v));
    const ta = card.querySelector('[data-text]');
    const chars = ta.value.length;
    card.querySelector('[data-stat]').textContent =
      chars + ' знаков · ≈' + Math.round(chars / 14 / 60) + ' мин речи';
    card.querySelector('[data-state]').textContent =
      rec.verdict ? 'сохранено: ' + rec.verdict + (rec.edited ? ' (текст правлен)' : '') : '';
    if (rec.verdict) done++;
  }});
  document.getElementById('count').textContent = done + ' из ' + ITEMS.length + ' проверено';
}}

document.querySelectorAll('.card').forEach(card => {{
  const id = card.dataset.id;
  const ta = card.querySelector('[data-text]');
  if (store[id] && typeof store[id].text === 'string') ta.value = store[id].text;
  ta.oninput = () => {{
    const r = touch(id);
    r.text = ta.value;
    r.edited = ta.value !== byId[id].original;
    save();
  }};
  card.querySelectorAll('.row button[data-v]').forEach(b => {{
    b.onclick = () => {{ touch(id).verdict = b.dataset.v; save(); }};
  }});
  card.querySelector('[data-reset]').onclick = () => {{
    ta.value = byId[id].original;
    const r = touch(id); r.text = ta.value; r.edited = false; save();
  }};
  const search = card.querySelector('[data-search]');
  const pre = card.querySelector('[data-full]');
  const raw = pre.textContent;
  search.oninput = () => {{
    const q = search.value.trim();
    if (!q) {{ pre.textContent = raw; return; }}
    const esc = s => s.replace(/[.*+?^${{}}()|[\\]\\\\]/g, '\\\\$&');
    pre.innerHTML = raw.replace(new RegExp(esc(q), 'gi'), m => '<mark>' + m + '</mark>');
    const first = pre.querySelector('mark');
    if (first) first.scrollIntoView({{block: 'center'}});
  }};
}});

document.getElementById('export').onclick = () => {{
  const out = ITEMS.map(i => {{
    const r = store[i.id] || {{}};
    return {{ name: i.name, book: i.book, verdict: r.verdict || null,
             edited: !!r.edited, transcript: (r.text !== undefined ? r.text : i.original) }};
  }});
  const blob = new Blob([JSON.stringify({{reviewed_at: new Date().toISOString(),
    judged: out.filter(o => o.verdict).length, items: out}}, null, 2)],
    {{type: 'application/json'}});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'slice_review.json';
  a.click();
}};
paint();
</script></body></html>"""
    open(OUT, "w").write(page)
    print(f"→ {OUT}  ({len(items)} items)")


if __name__ == "__main__":
    main()
