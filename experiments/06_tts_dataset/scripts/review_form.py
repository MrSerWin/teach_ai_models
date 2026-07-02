#!/usr/bin/env python3
"""Render the audit review pages as an interactive VERDICT FORM.

Each suspect clip gets ✓верно / ✗неверно buttons + a comment field. Verdicts
persist in the browser (localStorage) and an Export button dumps the marked ones
to JSON (clipboard + file download) to hand back for action.

Reads the already-computed metrics (no re-scoring):
  A: <dataset>/segments.jsonl        -> <dataset>/review_audit.html
  B: <dataset>/hf_audit/metrics.jsonl -> <dataset>/hf_audit/review_hf_audit.html

Usage: review_form.py <A|B> <dataset_dir>
"""
import html
import json
import sys
from pathlib import Path

WEAK_WORD = -2.0
BADWORD, BADWORD2, LOWMATCH, WEAKFRAC, CRAMMED, SPARSE = -8.0, -11.0, -0.62, 0.30, 15.0, 7.5


def tags(r):
    t = []
    if r["min_wscore"] < BADWORD2: t.append("bad-word!!")
    elif r["min_wscore"] < BADWORD: t.append("bad-word")
    if r["score"] < LOWMATCH: t.append("low-match")
    if r["n_words"] and r["n_weak"] / r["n_words"] > WEAKFRAC: t.append("many-weak")
    if r["char_rate"] > CRAMMED: t.append("crammed")
    if r["char_rate"] < SPARSE: t.append("sparse")
    return t


def susp(r, tg):
    w = {"bad-word!!": 3, "bad-word": 2, "low-match": 2, "many-weak": 1, "crammed": 1, "sparse": 1}
    return sum(w[t] for t in tg) + max(0, -r["min_wscore"]) / 10.0


FORM_HEAD = """<style>
body{font:13px system-ui;margin:0}table{border-collapse:collapse;margin:12px}
td,th{padding:5px 7px;border:1px solid #ddd;vertical-align:top}.x{max-width:360px}
.t{background:#fdd;border-radius:3px;padding:1px 5px;margin:1px;display:inline-block;font-size:11px}
audio{width:220px}small{color:#777}
#bar{position:sticky;top:0;background:#fff;border-bottom:2px solid #ccc;padding:8px 12px;z-index:10}
#bar button{padding:4px 10px;font-size:13px}
.vd button{margin:1px 2px;padding:3px 9px;border:1px solid #bbb;border-radius:4px;cursor:pointer;background:#f6f6f6;font-size:12px}
.vd button.ok.on{background:#bff0bf;border-color:#2a2;font-weight:bold}
.vd button.bad.on{background:#f6b4b4;border-color:#c22;font-weight:bold}
.vd input{width:210px;margin-top:4px;display:block}
tr.done td{background:#f4fff0}tr.done td.baddone{background:#fff0f0}
#out{width:98%;height:90px;display:none;margin-top:6px;font:12px monospace}
</style>
<div id=bar>
 <b>Вердикты:</b> отмечено <span id=cnt>0</span> из <span id=tot>0</span> &nbsp;
 <button onclick="exportV()">📋 Экспорт вердиктов (копия+файл)</button>
 <button onclick="if(confirm('Сбросить все отметки?')){V={};save();}">сброс</button>
 <span id=msg style="color:#080"></span>
 <textarea id=out placeholder="сюда попадёт JSON — скопируй и передай"></textarea>
</div>
"""

FORM_JS = """<script>
const KEY='__KEY__';
let V=JSON.parse(localStorage.getItem(KEY)||'{}');
function cid(el){return el.closest('[data-id]').dataset.id;}
function setV(b,v){const id=cid(b);V[id]=V[id]||{};V[id].verdict=(V[id].verdict===v?null:v);save();}
function setC(i){const id=cid(i);V[id]=V[id]||{};V[id].comment=i.value;save();}
function save(){localStorage.setItem(KEY,JSON.stringify(V));render();}
function render(){
 document.querySelectorAll('[data-id]').forEach(c=>{
  const id=c.dataset.id,v=V[id]||{};
  c.querySelectorAll('button').forEach(b=>b.classList.toggle('on',b.classList.contains(v.verdict||'_')));
  const inp=c.querySelector('input');if(inp)inp.value=v.comment||'';
  const tr=c.closest('tr');const marked=!!(v.verdict||v.comment);
  tr.classList.toggle('done',marked);
  c.classList.toggle('baddone',v.verdict==='bad');
 });
 let m=0;for(const k in V)if(V[k].verdict||V[k].comment)m++;
 document.getElementById('cnt').textContent=m;
}
function exportV(){
 const o={};for(const k in V)if(V[k].verdict||V[k].comment)o[k]=V[k];
 const txt=JSON.stringify(o,null,1);
 const ta=document.getElementById('out');ta.style.display='block';ta.value=txt;ta.select();
 if(navigator.clipboard)navigator.clipboard.writeText(txt).catch(()=>{});
 try{const b=new Blob([txt],{type:'application/json'});const a=document.createElement('a');
  a.href=URL.createObjectURL(b);a.download='__FILE__';a.click();}catch(e){}
 document.getElementById('msg').textContent=' ✓ скопировано + скачано ('+Object.keys(o).length+')';
}
document.getElementById('tot').textContent=document.querySelectorAll('[data-id]').length;
render();
</script>"""


def vd_cell(cid):
    return (f"<td class=vd data-id='{html.escape(cid)}'>"
            f"<button class=ok onclick=\"setV(this,'ok')\">✓ верно</button>"
            f"<button class=bad onclick=\"setV(this,'bad')\">✗ неверно</button>"
            f"<input placeholder='комментарий' oninput='setC(this)'></td>")


def load_A(dd):
    rows = [json.loads(l) for l in open(dd / "segments.jsonl")]
    out = []
    for r in rows:
        for k in ("score", "min_wscore", "char_rate", "dur"): r[k] = float(r[k])
        r["n_weak"] = int(r["n_weak"]); r["n_words"] = int(r["n_words"])
        if not (r["keep"] is True or r["keep"] == "True"): continue
        out.append({"id": r["id"], "book": r["book"], "cyr": r["text_cyr"], "lat": r["text_lat"],
                    "wav": r["wav"], **{k: r[k] for k in ("score", "min_wscore", "char_rate", "dur", "n_weak", "n_words")}})
    return out


def load_B(dd):
    mp = dd / "hf_audit" / "metrics.jsonl"
    out = []
    for l in open(mp):
        r = json.loads(l)
        out.append({"id": r["id"], "book": "", "cyr": "", "lat": r["text"],
                    "wav": f"wavs/{r['id']}.wav", **{k: r[k] for k in ("score", "min_wscore", "char_rate", "dur", "n_weak", "n_words")}})
    return out


def main():
    mode, dd = sys.argv[1], Path(sys.argv[2])
    recs = load_A(dd) if mode == "A" else load_B(dd)
    for r in recs:
        r["_tags"] = tags(r); r["_susp"] = susp(r, r["_tags"])
    suspects = sorted([r for r in recs if r["_tags"]], key=lambda r: -r["_susp"])

    title = "Dataset A (exp-06 Sevil)" if mode == "A" else "Dataset B (HF tts-crh-sevil-fixed, 16 kHz)"
    key = "verdicts_dsA" if mode == "A" else "verdicts_dsB"
    fn = "verdicts_A.json" if mode == "A" else "verdicts_B.json"
    cyr_col = "<th>Cyrillic</th>" if mode == "A" else ""

    body = []
    for r in suspects:
        tg = " ".join(f'<span class=t>{html.escape(t)}</span>' for t in r["_tags"])
        meta = (f"minw {r['min_wscore']:.1f} · sc {r['score']:.2f} · cr {r['char_rate']:.1f} · {r['dur']:.1f}s")
        idcell = f"{html.escape(r['id'])}" + (f"<br><small>{html.escape(r['book'])}</small>" if r["book"] else "")
        cyr = f"<td class=x>{html.escape(r['cyr'])}</td>" if mode == "A" else ""
        body.append(
            f"<tr><td>{idcell}</td><td>{tg}<br><small>{meta}</small></td>{cyr}"
            f"<td class=x>{html.escape(r['lat'])}</td>"
            f"<td><audio controls preload=none src='{html.escape(r['wav'])}'></audio></td>"
            f"{vd_cell(r['id'])}</tr>")

    head = FORM_HEAD
    js = FORM_JS.replace("__KEY__", key).replace("__FILE__", fn)
    doc = (f"<!doctype html><meta charset=utf-8><title>Verdict form — {html.escape(title)}</title>"
           f"{head}<h3 style='margin:10px 12px'>Аудит-форма: {html.escape(title)} — "
           f"{len(suspects)} клипов (worst first)</h3>"
           f"<p style='margin:0 12px'>Отметь по каждому: ✓верно (аудио совпадает с текстом) / "
           f"✗неверно (сдвиг/несовпадение) + комментарий. Потом «Экспорт» и передай мне JSON.</p>"
           f"<table><tr><th>id</th><th>flags</th>{cyr_col}<th>Latin</th><th>audio</th><th>вердикт</th></tr>"
           f"{''.join(body)}</table>{js}")
    outp = (dd / "review_audit.html") if mode == "A" else (dd / "hf_audit" / "review_hf_audit.html")
    outp.write_text(doc, encoding="utf-8")
    print(f"{mode}: {len(suspects)} suspects -> {outp}")


if __name__ == "__main__":
    main()
