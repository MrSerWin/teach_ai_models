#!/usr/bin/env python3
"""Deep alignment audit of the built dataset — find CRITICAL clips still in the
KEPT set (they're in training and can teach the model wrong text↔sound mappings).

Reads segments.jsonl (per-clip forced-alignment metrics) and flags:
  bad-word   min_wscore very negative → one word badly matched (word shift!)
  low-match  low mean score           → whole clip weakly matched
  many-weak  high weak-word fraction   → several words off
  crammed    char_rate too high        → words merged/missing (cut too tight)
  sparse     char_rate too low         → silence/mismatch (cut too loose)
  long/short duration outliers

Outputs:
  AUDIT_REPORT.md        per-book table + summary + top suspects
  review_audit.html      worst-first, cyr+lat+audio+metrics (open next to wavs/)

Usage: audit_dataset.py <dataset_dir>
"""
import html
import json
import sys
from pathlib import Path

# thresholds (derived from the kept-clip distribution)
BADWORD = -8.0      # min_wscore below this = a badly-matched word
BADWORD2 = -11.0    # severe
LOWMATCH = -0.62    # mean score below this = weak whole clip
WEAKFRAC = 0.30     # n_weak / n_words
CRAMMED = 15.0      # char_rate
SPARSE = 7.5
LONG = 12.0
SHORT = 4.0


def tags(r):
    t = []
    if r["min_wscore"] < BADWORD2: t.append(("bad-word!!", 3))
    elif r["min_wscore"] < BADWORD: t.append(("bad-word", 2))
    if r["score"] < LOWMATCH: t.append(("low-match", 2))
    if r["n_words"] and r["n_weak"] / r["n_words"] > WEAKFRAC: t.append(("many-weak", 1))
    if r["char_rate"] > CRAMMED: t.append(("crammed", 1))
    if r["char_rate"] < SPARSE: t.append(("sparse", 1))
    if r["dur"] > LONG: t.append(("long", 1))
    if r["dur"] < SHORT: t.append(("short", 1))
    return t


def main():
    dd = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    rows = [json.loads(l) for l in open(dd / "segments.jsonl")]
    for r in rows:
        for k in ("score", "min_wscore", "char_rate", "dur"):
            r[k] = float(r[k])
        r["n_weak"] = int(r["n_weak"]); r["n_words"] = int(r["n_words"])
        r["keep"] = r["keep"] is True or r["keep"] == "True"
    kept = [r for r in rows if r["keep"]]

    for r in kept:
        r["_tags"] = tags(r)
        r["_susp"] = sum(w for _, w in r["_tags"]) + max(0, -r["min_wscore"]) / 10.0
    suspects = sorted([r for r in kept if r["_tags"]], key=lambda r: -r["_susp"])

    # per-book aggregation
    books = {}
    for r in kept:
        b = books.setdefault(r["book"], {"n": 0, "susp": 0, "badword": 0,
                                         "scores": [], "minw": []})
        b["n"] += 1
        b["scores"].append(r["score"]); b["minw"].append(r["min_wscore"])
        if r["_tags"]: b["susp"] += 1
        if r["min_wscore"] < BADWORD: b["badword"] += 1
    for b in books.values():
        b["mean_score"] = sum(b["scores"]) / len(b["scores"])
        b["med_minw"] = sorted(b["minw"])[len(b["minw"]) // 2]
        b["susp_pct"] = 100 * b["susp"] / b["n"]

    # --- report ---
    rep = ["# Deep alignment audit — dataset A (exp-06 Sevil)\n",
           f"Kept clips: **{len(kept)}** · flagged suspects: **{len(suspects)}** "
           f"({100*len(suspects)/len(kept):.1f}%)\n",
           "Severity counts (kept set):",
           f"- bad-word (min_wscore<{BADWORD}): **{sum(1 for r in kept if r['min_wscore']<BADWORD)}** "
           f"(severe <{BADWORD2}: {sum(1 for r in kept if r['min_wscore']<BADWORD2)})",
           f"- low-match (score<{LOWMATCH}): {sum(1 for r in kept if r['score']<LOWMATCH)}",
           f"- many-weak (>{WEAKFRAC:.0%} weak words): {sum(1 for r in kept if r['n_words'] and r['n_weak']/r['n_words']>WEAKFRAC)}",
           f"- crammed (cr>{CRAMMED}): {sum(1 for r in kept if r['char_rate']>CRAMMED)} · "
           f"sparse (cr<{SPARSE}): {sum(1 for r in kept if r['char_rate']<SPARSE)}\n",
           "## Per-book (sorted by % suspect — spot systematic drift)\n",
           "| book | kept | %suspect | bad-word | mean score | median min_wscore |",
           "|---|---|---|---|---|---|"]
    for name, b in sorted(books.items(), key=lambda kv: -kv[1]["susp_pct"]):
        rep.append(f"| {name} | {b['n']} | {b['susp_pct']:.0f}% | {b['badword']} | "
                   f"{b['mean_score']:.2f} | {b['med_minw']:.1f} |")
    rep.append(f"\n## Top 40 critical clips\n")
    rep.append("| id | tags | min_wscore | score | cr | dur | text (lat) |")
    rep.append("|---|---|---|---|---|---|---|")
    for r in suspects[:40]:
        tg = ",".join(t for t, _ in r["_tags"])
        rep.append(f"| {r['id']} | {tg} | {r['min_wscore']:.1f} | {r['score']:.2f} | "
                   f"{r['char_rate']:.1f} | {r['dur']:.1f} | {html.escape(r['text_lat'][:60])} |")
    (dd / "AUDIT_REPORT.md").write_text("\n".join(rep), encoding="utf-8")

    # --- review HTML (worst-first, audio) ---
    def row(r):
        tg = " ".join(f'<span class=t>{html.escape(t)}</span>' for t, _ in r["_tags"])
        return (f"<tr><td>{html.escape(r['id'])}<br><small>{html.escape(r['book'])}</small></td>"
                f"<td>{tg}<br><small>minw {r['min_wscore']:.1f} · sc {r['score']:.2f} · "
                f"cr {r['char_rate']:.1f} · {r['dur']:.1f}s</small></td>"
                f"<td class=x>{html.escape(r['text_cyr'])}</td>"
                f"<td class=x>{html.escape(r['text_lat'])}</td>"
                f"<td><audio controls preload=none src='{html.escape(r['wav'])}'></audio></td></tr>")
    body = "".join(row(r) for r in suspects)
    (dd / "review_audit.html").write_text(
        "<!doctype html><meta charset=utf-8><title>Deep audit — critical clips</title>"
        "<style>body{font:13px system-ui;margin:18px}table{border-collapse:collapse}"
        "td,th{padding:5px 7px;border:1px solid #ddd;vertical-align:top}.x{max-width:340px}"
        ".t{background:#fdd;border-radius:3px;padding:1px 5px;margin:1px;display:inline-block;font-size:11px}"
        "audio{width:230px}small{color:#777}</style>"
        f"<h2>Deep alignment audit — {len(suspects)} critical clips (worst first)</h2>"
        "<p>Listen &amp; verify: does the audio match BOTH texts? Red tags flag likely word-shift / "
        "mismatch. <b>bad-word!!</b> = one word very poorly aligned.</p>"
        "<table><tr><th>id / book</th><th>flags</th><th>Cyrillic</th><th>Latin</th><th>audio</th></tr>"
        f"{body}</table>", encoding="utf-8")
    print(f"kept={len(kept)} suspects={len(suspects)} -> {dd/'review_audit.html'}, {dd/'AUDIT_REPORT.md'}")


if __name__ == "__main__":
    main()
