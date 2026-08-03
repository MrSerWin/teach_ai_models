#!/usr/bin/env python3
"""Confirm candidate recording⇄book pairs by looking inside the book.

`match_books.py` matches filenames, which only ever produces *candidates*: a
collection named after its author says nothing about which works it holds. This
opens each candidate and checks whether the work's title actually appears in the
book's own text — front matter, and the table of contents, which in Soviet
editions sits at the back.

Verdicts
--------
- ``confirmed``   the work's title occurs in the book's text
- ``absent``      text was readable and the title is not in it
- ``unreadable``  scanned image-only PDF with no text layer (OCR not attempted
                  here — that is a separate, expensive pass)

Only `confirmed` pairs are safe to feed to forced alignment. `absent` is a real
answer: it means the filename matched but the book is the wrong one, or the
collection does not include that work.

Deliberately cheap: a page window at each end, `pdftotext` only, niced. It is
meant to run alongside other work without competing for the machine.
"""
from __future__ import annotations

import difflib
import json
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from match_books import skeleton, tokens  # noqa: E402  same key on both sides

SOURCES = "/Volumes/T9/AnaYurt/Books/Qirimtatar/sources"
LIBRARY = "/Volumes/T9/AnaYurt/Books/Qirimtatar"
IN_JSON = os.path.join(SOURCES, "book_matches.json")
OUT_JSON = os.path.join(SOURCES, "verified_matches.json")
OUT_MD = os.path.join(SOURCES, "VERIFIED.md")

HEAD_PAGES = 12   # title page, contents in modern editions
TAIL_PAGES = 10   # imprint + contents in Soviet editions
# Share of the title's tokens that must appear for the work to count as present.
HIT_RATIO = 0.6


def phrase_hit(phrase: str, text: str) -> float:
    """Best similarity of `phrase` against any same-length window of `text`.

    A plain substring test is too brittle for this corpus: the same work is
    printed as «Nenkecan hanım türbesi» and «Nenkecan hanum turbesi» in editions
    a decade apart, and OCR adds its own drift. Anchoring on the phrase's rarest
    word keeps this cheap — we compare a handful of windows, not the whole book.
    """
    if not phrase or not text:
        return 0.0
    words = phrase.split()
    if not words:
        return 0.0
    anchor = max(words, key=len)          # longest word ≈ the most distinctive
    span = len(phrase)
    best = 0.0
    start = 0
    for _ in range(40):                    # cap the number of anchors examined
        i = text.find(anchor, start)
        if i < 0:
            break
        lo = max(0, i - span)
        window = text[lo: lo + 2 * span + len(anchor)]
        for off in range(0, max(1, len(window) - span + 1), 4):
            best = max(best, difflib.SequenceMatcher(
                None, phrase, window[off: off + span]).ratio())
            if best >= 0.97:
                return best
        start = i + len(anchor)
    return best


def pdftotext(path: str, first: int, last: int) -> str:
    try:
        r = subprocess.run(
            ["nice", "-n", "19", "pdftotext", "-f", str(first), "-l", str(last),
             "-q", path, "-"],
            capture_output=True, text=True, timeout=120,
        )
        return r.stdout
    except Exception:
        return ""


def page_count(path: str) -> int:
    try:
        r = subprocess.run(["nice", "-n", "19", "pdfinfo", path],
                           capture_output=True, text=True, timeout=60)
        m = re.search(r"Pages:\s+(\d+)", r.stdout)
        return int(m.group(1)) if m else 0
    except Exception:
        return 0


# The tg2026 cataloguing run OCR'd every book in that archive; reuse its text
# instead of paying for OCR twice. Layout: text_cache/<channel>/<file>.txt
OCR_CACHE = ("/Users/servin/1_dev/my/anayurt/tg-grabber/out/ocr_catalogue/text_cache")


def cached_ocr(rel: str) -> str:
    if not rel.startswith("tg2026/"):
        return ""
    p = os.path.join(OCR_CACHE, rel[len("tg2026/"):] + ".txt")
    try:
        return open(p, errors="ignore").read() if os.path.exists(p) else ""
    except Exception:
        return ""


def book_text(rel: str) -> str:
    path = os.path.join(LIBRARY, rel)
    if not os.path.exists(path) or not path.lower().endswith(".pdf"):
        return cached_ocr(rel)
    n = page_count(path)
    head = pdftotext(path, 1, HEAD_PAGES)
    tail = pdftotext(path, max(1, n - TAIL_PAGES), n) if n > HEAD_PAGES else ""
    native = head + "\n" + tail
    # An image-only scan yields a handful of stray characters, not a page.
    if len(native.strip()) < 200:
        ocr = cached_ocr(rel)
        if len(ocr.strip()) > len(native.strip()):
            return ocr
    return native


def main() -> None:
    data = json.load(open(IN_JSON))
    todo = [m for m in data["matches"]
            if m["tier"] in ("strong", "title-only", "author-only") and m["candidates"]]
    # One book may back several recordings (a collection); read each book once.
    books = sorted({m["candidates"][0]["book"] for m in todo})
    print(f"{len(todo)} candidate pairs over {len(books)} distinct books", flush=True)

    cache: dict[str, str] = {}

    def load(rel: str) -> tuple[str, str]:
        return rel, skeleton(book_text(rel))

    with ThreadPoolExecutor(max_workers=2) as ex:  # gentle: OCR may be running
        for i, (rel, sk) in enumerate(ex.map(load, books), 1):
            cache[rel] = sk
            if i % 10 == 0 or i == len(books):
                print(f"  read {i}/{len(books)}", flush=True)

    results = []
    for m in todo:
        rel = m["candidates"][0]["book"]
        sk = cache.get(rel, "")
        wt = tokens(m["work"], 4)
        if not sk:
            verdict, ratio = "unreadable", 0.0
        elif len(wt) < 2:
            # One distinctive word is not evidence — the same trap that makes
            # filename matching unreliable. Leave it for a human.
            verdict, ratio = "inconclusive", 0.0
        else:
            hits = sum(1 for t in wt if t in sk)
            ratio = hits / len(wt)
            # A bag of tokens confirms nothing: "sen bir yana men bir yana" is
            # satisfied by any book containing those common words. Require the
            # title to occur as a phrase — its words adjacent, in order — and
            # keep the token ratio only as a secondary signal.
            phrase = " ".join(skeleton(m["work"]).split())
            sim = phrase_hit(phrase, sk)
            if sim >= 0.85:
                verdict = "confirmed"
            elif sim >= 0.70 or ratio >= HIT_RATIO:
                verdict = "weak"
            else:
                verdict = "absent"
            ratio = max(ratio, round(sim, 2))
        results.append({**{k: m[k] for k in ("source", "author", "work", "file", "tier")},
                        "book": rel, "title_tokens_found": round(ratio, 2),
                        "verdict": verdict})

    counts: dict[str, int] = {}
    for r in results:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    json.dump({"counts": counts, "checked": len(results), "results": results},
              open(OUT_JSON, "w"), ensure_ascii=False, indent=2)

    md = ["# Verified recording ⇄ book pairs", "",
          "Generated by `scripts/corpus/verify_matches.py`: each candidate from",
          "`MATCHES.md` was opened and searched for the work's title in its own text",
          "(front matter + table of contents at both ends).", "",
          "Only **confirmed** pairs are safe for forced alignment. **absent** means the",
          "filename matched but the book does not contain that work — a real answer, not",
          "a failure. **unreadable** is an image-only scan with no text layer; it needs",
          "OCR before it can be judged.", "",
          "| Verdict | Count |", "|---|---|"]
    md += [f"| {k} | {v} |" for k, v in sorted(counts.items(), key=lambda kv: -kv[1])]
    md += [""]
    for v in ("confirmed", "weak", "absent", "unreadable", "inconclusive"):
        rows = [r for r in results if r["verdict"] == v]
        if not rows:
            continue
        md += [f"## {v} ({len(rows)})", "",
               "| Source | Author | Work | Book | Title tokens found |",
               "|---|---|---|---|---|"]
        for r in sorted(rows, key=lambda r: -r["title_tokens_found"]):
            md.append(f"| {r['source']} | {(r['author'] or '—')[:26]} | {r['work'][:44]} "
                      f"| `{r['book'][:64]}` | {r['title_tokens_found']} |")
        md += [""]
    open(OUT_MD, "w").write("\n".join(md))
    print("verdicts:", counts)
    print(f"→ {OUT_JSON}\n→ {OUT_MD}")


if __name__ == "__main__":
    main()
