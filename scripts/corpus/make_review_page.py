#!/usr/bin/env python3
"""Build REVIEW.html — an in-place editor for judging recording⇄book pairs.

The machine can prove a book *contains* a work; it cannot prove the opposite,
because an unreadable scan and a wrong book look identical from outside. So the
`absent` verdicts especially need a human: play the recording, look at the book,
decide — or point at a different book entirely.

The page is written next to the data (`sources/REVIEW.html`) so that relative
`file://` paths reach the audio and the PDFs directly. It keeps state in
localStorage as you go and exports one JSON with every verdict.

    python3 make_review_page.py            # all pairs, absent first
    python3 make_review_page.py --only absent
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor

SOURCES = "/Volumes/T9/AnaYurt/Books/Qirimtatar/sources"
LIBRARY = "/Volumes/T9/AnaYurt/Books/Qirimtatar"
IN_JSON = os.path.join(SOURCES, "verified_matches.json")
OUT_HTML = os.path.join(SOURCES, "REVIEW.html")
BOOK_EXTS = (".pdf", ".fb2", ".epub", ".docx", ".doc", ".djvu", ".odt", ".txt")
SKIP_DIRS = {"sources", "ana_tili_files"}
EXCERPT_CHARS = 700


def audio_rel(rec: dict) -> str | None:
    """Path to the recording, relative to sources/ (where the page lives)."""
    src, f = rec["source"], rec["file"]
    cands = {
        # leylaemir's index already stores the path as "audio/record-001.mp3",
        # so try it as-is before assuming a bare filename.
        "leylaemir-org": [f"leylaemir-org/{f}", f"leylaemir-org/audio/{f}"],
        "maye-safet/youtube": [f"maye-safet/youtube/{f}"],
        "maye-safet/telegram": [f"maye-safet/telegram-arifler_ve_ses/{f}"],
    }.get(src, [])
    for c in cands:
        if os.path.exists(os.path.join(SOURCES, c)):
            return c
    return None


def trkmillet_dir(work: str) -> str | None:
    """trkmillet records name a book, not a file — link to its folder."""
    base = os.path.join(SOURCES, "trkmillet")
    if not os.path.isdir(base):
        return None
    key = "".join(ch for ch in work.lower() if ch.isalnum())[:12]
    for d in sorted(os.listdir(base)):
        flat = "".join(ch for ch in d.lower() if ch.isalnum())
        if key and key in flat:
            return f"trkmillet/{d}"
    return None


def excerpt(rel: str) -> str:
    path = os.path.join(LIBRARY, rel)
    if not path.lower().endswith(".pdf") or not os.path.exists(path):
        return ""
    try:
        r = subprocess.run(["nice", "-n", "19", "pdftotext", "-f", "1", "-l", "3",
                            "-q", path, "-"], capture_output=True, text=True, timeout=90)
        txt = " ".join(r.stdout.split())
        return txt[:EXCERPT_CHARS]
    except Exception:
        return ""


def library_files() -> list[str]:
    out = []
    for dirpath, dirnames, files in os.walk(LIBRARY):
        rel = os.path.relpath(dirpath, LIBRARY)
        if rel.split(os.sep)[0] in SKIP_DIRS:
            dirnames[:] = []
            continue
        for f in files:
            if f.lower().endswith(BOOK_EXTS) and not f.startswith("."):
                out.append(os.path.join(rel, f) if rel != "." else f)
    return sorted(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="restrict to one verdict (e.g. absent)")
    args = ap.parse_args()

    rows = json.load(open(IN_JSON))["results"]
    if args.only:
        rows = [r for r in rows if r["verdict"] == args.only]
    order = {"absent": 0, "unreadable": 1, "inconclusive": 2, "weak": 3, "confirmed": 4}
    rows.sort(key=lambda r: (order.get(r["verdict"], 9), r["source"], r["work"]))

    books = sorted({r["book"] for r in rows})
    print(f"{len(rows)} pairs, {len(books)} distinct books — reading excerpts", flush=True)
    with ThreadPoolExecutor(max_workers=2) as ex:
        ex_map = dict(zip(books, ex.map(excerpt, books)))

    lib = library_files()
    def pair_id(r: dict) -> str:
        """Stable key: survives regeneration, so saved verdicts are not lost when
        the page is rebuilt after a new verification run."""
        raw = f"{r['source']}|{r['work']}|{r['file']}|{r['book']}"
        return hashlib.sha1(raw.encode()).hexdigest()[:12]

    cards = []
    for i, r in enumerate(rows):
        pid = pair_id(r)
        a = audio_rel(r)
        if not a and r["source"] == "trkmillet":
            d = trkmillet_dir(r["work"])
            a = None
            media = (f'<a class="lnk" href="{html.escape(d)}">открыть папку записи</a>'
                     if d else '<span class="muted">запись не найдена</span>')
        elif a:
            media = f'<audio controls preload="none" src="{html.escape(a)}"></audio>'
        else:
            media = '<span class="muted">аудиофайл не найден</span>'
        ex_txt = ex_map.get(r["book"], "")
        cards.append(f"""
<article class="card" data-i="{pid}" data-verdict="{html.escape(r['verdict'])}">
  <header>
    <span class="badge v-{html.escape(r['verdict'])}">{html.escape(r['verdict'])}</span>
    <span class="tier">{html.escape(r['tier'])}</span>
    <span class="src">{html.escape(r['source'])}</span>
    <span class="num">#{i + 1}</span>
  </header>
  <h3>{html.escape(r['work'])}</h3>
  <p class="author">{html.escape(r['author'] or '— автор не указан —')}</p>
  <div class="media">{media}</div>
  <div class="book">
    <div class="book-head">
      <strong>Книга-кандидат</strong>
      <a class="lnk" href="../{html.escape(r['book'])}" target="_blank">открыть PDF</a>
      <span class="score">совпадение: {r['title_tokens_found']}</span>
    </div>
    <code>{html.escape(r['book'])}</code>
    <details><summary>первые страницы книги</summary>
      <p class="excerpt">{html.escape(ex_txt) or '<нет текстового слоя — только скан>'}</p>
    </details>
  </div>
  <div class="verdict">
    <button class="ok"  data-v="confirmed">Это оно</button>
    <button class="no"  data-v="rejected">Не то</button>
    <button class="hm"  data-v="unsure">Не уверен</button>
    <button class="sk"  data-v="no_text">Нет текста / нужен OCR</button>
  </div>
  <label class="alt">Другая книга:
    <input list="books" placeholder="начните вводить название файла…" data-alt>
  </label>
  <label class="note">Заметка:
    <input type="text" placeholder="что услышали / что за издание" data-note>
  </label>
  <div class="state"></div>
</article>""")

    datalist = "".join(f"<option value=\"{html.escape(b)}\">" for b in lib)
    payload = json.dumps([dict({k: r[k] for k in
                                ("source", "author", "work", "file", "tier", "book", "verdict")},
                               pair_id=pair_id(r)) for r in rows], ensure_ascii=False)

    page = f"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Сверка: запись ⇄ книга</title>
<style>
:root {{ color-scheme: light dark; --bg:#fff; --fg:#1a1a1a; --mut:#6b7280;
  --line:#e5e7eb; --card:#fff; --accent:#2563eb; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#0f1115; --fg:#e8eaed;
  --mut:#9aa0a6; --line:#2a2f3a; --card:#161a21; }} }}
* {{ box-sizing:border-box; }}
body {{ margin:0; padding:24px 16px 96px; background:var(--bg); color:var(--fg);
  font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; }}
.wrap {{ max-width:900px; margin:0 auto; }}
h1 {{ font-size:22px; margin:0 0 6px; }}
.lead {{ color:var(--mut); margin:0 0 20px; }}
.bar {{ position:sticky; top:0; z-index:5; background:var(--bg);
  border-bottom:1px solid var(--line); padding:10px 0; margin-bottom:16px;
  display:flex; gap:10px; align-items:center; flex-wrap:wrap; }}
.bar button, .bar select {{ font:inherit; padding:7px 12px; border-radius:8px;
  border:1px solid var(--line); background:var(--card); color:var(--fg); cursor:pointer; }}
.bar .primary {{ background:var(--accent); color:#fff; border-color:transparent; }}
.count {{ color:var(--mut); margin-left:auto; }}
.card {{ border:1px solid var(--line); border-radius:12px; padding:16px;
  margin-bottom:14px; background:var(--card); }}
.card header {{ display:flex; gap:8px; align-items:center; font-size:12px;
  color:var(--mut); margin-bottom:6px; flex-wrap:wrap; }}
.badge {{ padding:2px 8px; border-radius:999px; font-weight:600; color:#fff; }}
.v-absent {{ background:#dc2626; }} .v-unreadable {{ background:#6b7280; }}
.v-inconclusive {{ background:#d97706; }} .v-weak {{ background:#ca8a04; }}
.v-confirmed {{ background:#16a34a; }}
.num {{ margin-left:auto; }}
h3 {{ margin:2px 0 2px; font-size:17px; }}
.author {{ margin:0 0 10px; color:var(--mut); }}
audio {{ width:100%; margin:4px 0 12px; }}
.book {{ border:1px solid var(--line); border-radius:8px; padding:10px; margin-bottom:12px; }}
.book-head {{ display:flex; gap:10px; align-items:center; margin-bottom:6px; flex-wrap:wrap; }}
.book code {{ font-size:12px; color:var(--mut); word-break:break-all; display:block; }}
.score {{ margin-left:auto; font-size:12px; color:var(--mut); }}
.lnk {{ color:var(--accent); }}
.excerpt {{ font-size:13px; color:var(--mut); max-height:150px; overflow:auto;
  border-left:3px solid var(--line); padding-left:10px; }}
.verdict {{ display:flex; gap:8px; flex-wrap:wrap; margin-bottom:10px; }}
.verdict button {{ font:inherit; padding:8px 14px; border-radius:8px; cursor:pointer;
  border:1px solid var(--line); background:transparent; color:var(--fg); }}
.verdict button.sel {{ color:#fff; border-color:transparent; }}
.ok.sel {{ background:#16a34a; }} .no.sel {{ background:#dc2626; }}
.hm.sel {{ background:#d97706; }} .sk.sel {{ background:#6b7280; }}
label {{ display:block; font-size:13px; color:var(--mut); margin-bottom:8px; }}
label input {{ width:100%; font:inherit; padding:8px; margin-top:4px; border-radius:8px;
  border:1px solid var(--line); background:var(--bg); color:var(--fg); }}
.state {{ font-size:12px; color:#16a34a; min-height:16px; }}
.done {{ opacity:.55; }}
table {{ border-collapse:collapse; }}
</style></head><body><div class="wrap">
<h1>Сверка: запись ⇄ книга</h1>
<p class="lead">Послушайте запись, посмотрите книгу и вынесите вердикт. Если книга
не та — впишите правильную в поле «Другая книга». Всё сохраняется в браузере
само; в конце нажмите «Скачать вердикты» и передайте файл.</p>
<div class="bar">
  <select id="filter">
    <option value="">все ({len(rows)})</option>
    <option value="absent">absent — машина не нашла текст</option>
    <option value="unreadable">unreadable — скан без текста</option>
    <option value="inconclusive">inconclusive</option>
    <option value="weak">weak</option>
    <option value="confirmed">confirmed</option>
    <option value="__todo">только неотсуженные</option>
  </select>
  <button id="export" class="primary">Скачать вердикты</button>
  <button id="reset">Сбросить</button>
  <span class="count" id="count"></span>
</div>
<datalist id="books">{datalist}</datalist>
{''.join(cards)}
</div>
<script>
const ROWS = {payload};
const KEY = 'crh-review-verdicts-v1';
const store = JSON.parse(localStorage.getItem(KEY) || '{{}}');

function save() {{ localStorage.setItem(KEY, JSON.stringify(store)); paint(); }}

function paint() {{
  let done = 0;
  document.querySelectorAll('.card').forEach(card => {{
    const i = card.dataset.i, rec = store[i];
    card.querySelectorAll('.verdict button').forEach(b =>
      b.classList.toggle('sel', !!rec && rec.human === b.dataset.v));
    card.classList.toggle('done', !!rec && !!rec.human);
    card.querySelector('.state').textContent =
      rec && rec.human ? 'сохранено: ' + rec.human + (rec.alt ? ' → ' + rec.alt : '') : '';
    if (rec && rec.human) done++;
  }});
  document.getElementById('count').textContent = done + ' из ' + ROWS.length + ' отсужено';
}}

function touch(i) {{ store[i] = store[i] || {{}}; return store[i]; }}

document.querySelectorAll('.card').forEach(card => {{
  const i = card.dataset.i;
  card.querySelectorAll('.verdict button').forEach(btn => {{
    btn.onclick = () => {{ touch(i).human = btn.dataset.v; save(); }};
  }});
  const alt = card.querySelector('[data-alt]'), note = card.querySelector('[data-note]');
  if (store[i]) {{ alt.value = store[i].alt || ''; note.value = store[i].note || ''; }}
  alt.oninput  = () => {{ touch(i).alt = alt.value.trim(); save(); }};
  note.oninput = () => {{ touch(i).note = note.value.trim(); save(); }};
}});

document.getElementById('filter').onchange = e => {{
  const v = e.target.value;
  document.querySelectorAll('.card').forEach(c => {{
    const judged = store[c.dataset.i] && store[c.dataset.i].human;
    const show = !v ? true : v === '__todo' ? !judged : c.dataset.verdict === v;
    c.style.display = show ? '' : 'none';
  }});
}};

document.getElementById('export').onclick = () => {{
  const out = ROWS.map(r => Object.assign({{}}, r, {{
    machine_verdict: r.verdict,
    human_verdict: (store[r.pair_id] || {{}}).human || null,
    replacement_book: (store[r.pair_id] || {{}}).alt || null,
    note: (store[r.pair_id] || {{}}).note || null
  }}));
  const blob = new Blob([JSON.stringify({{
    reviewed_at: new Date().toISOString(),
    judged: out.filter(o => o.human_verdict).length,
    total: out.length, results: out
  }}, null, 2)], {{type: 'application/json'}});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'review_verdicts.json';
  a.click();
}};

document.getElementById('reset').onclick = () => {{
  if (confirm('Стереть все вердикты?')) {{
    localStorage.removeItem(KEY);
    for (const k in store) delete store[k];
    document.querySelectorAll('[data-alt],[data-note]').forEach(el => el.value = '');
    save();
  }}
}};
paint();
</script></body></html>"""
    open(OUT_HTML, "w").write(page)
    print(f"→ {OUT_HTML}  ({len(rows)} pairs, {len(lib)} books in the picker)")


if __name__ == "__main__":
    main()
