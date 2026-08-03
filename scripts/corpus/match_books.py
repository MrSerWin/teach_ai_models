#!/usr/bin/env python3
"""Match recordings to the book files that may hold their text.

Forced alignment needs the ground-truth text of what is being read. This finds
candidate book files for every recording in the raw sources, so the alignment
tier can start from a short list instead of 3148 files.

It proposes; it does not decide. Output is ranked candidates for review — a
filename match is evidence, not proof that the book contains that exact work
(collections and «Sailama eserler» volumes hold many works, and a title can
repeat across authors).

Matching key — deliberately not a transliteration
------------------------------------------------
Titles arrive in Cyrillic (library, trkmillet), in Crimean-Tatar Latin
(leylaemir), and in ad-hoc romanization (tg2026 filenames). Rather than
transliterate — which the project reserves for the vetted engine, and which is
explicitly wrong for personal names — both sides are folded to a coarse
*skeleton* where every ambiguous pair collapses to one symbol: q/k → k,
c/дж → j, ç/ч → c, ş/ш → s, ğ/гъ → g, ñ/нъ → n, ı/ы/и → i. The skeleton is a
lookup key, never shown as a spelling.

Usage
-----
    python3 match_books.py            # writes MATCHES.md + book_matches.json
    python3 match_books.py --min 0.5  # stricter title threshold
"""
from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import unicodedata

SOURCES = "/Volumes/T9/AnaYurt/Books/Qirimtatar/sources"
LIBRARY = "/Volumes/T9/AnaYurt/Books/Qirimtatar"
OUT_JSON = os.path.join(SOURCES, "book_matches.json")
OUT_MD = os.path.join(SOURCES, "MATCHES.md")

BOOK_EXTS = (".pdf", ".fb2", ".epub", ".docx", ".doc", ".djvu", ".odt", ".txt")
# Folders under the library root that are sources or assets, not the book shelf.
SKIP_DIRS = {"sources", "ana_tili_files"}

# Cyrillic → skeleton. Digraphs first; order matters.
_CYR = [
    ("къ", "k"), ("гъ", "g"), ("нъ", "n"), ("дж", "j"), ("ль", "l"),
    ("щ", "s"), ("ш", "s"), ("ч", "c"), ("ц", "ts"), ("ж", "j"), ("х", "h"),
    ("ю", "yu"), ("я", "ya"), ("ё", "yo"), ("э", "e"), ("ы", "i"), ("и", "i"),
    ("й", "y"), ("ъ", ""), ("ь", ""),
    ("а", "a"), ("б", "b"), ("в", "v"), ("г", "g"), ("д", "d"), ("е", "e"),
    ("з", "z"), ("к", "k"), ("л", "l"), ("м", "m"), ("н", "n"), ("о", "o"),
    ("п", "p"), ("р", "r"), ("с", "s"), ("т", "t"), ("у", "u"), ("ф", "f"),
]
# Latin (crh / Turkish / ad-hoc romanization) → the same skeleton.
_LAT = [
    ("dzh", "j"), ("sch", "s"), ("sh", "s"), ("ch", "c"), ("kh", "h"),
    ("gh", "g"), ("zh", "j"), ("ts", "ts"),
    ("ñ", "n"), ("ğ", "g"), ("ç", "c"), ("ş", "s"), ("ı", "i"), ("â", "a"),
    ("ö", "o"), ("ü", "u"), ("û", "u"), ("î", "i"), ("é", "e"),
    ("q", "k"), ("c", "j"), ("w", "v"), ("x", "h"), ("y", "y"),
]

STOP = {
    "the", "and", "ile", "ve", "bir", "chast", "qisim", "kisim", "bolyuk", "bolük",
    "part", "chapter", "roman", "povest", "esse", "hikaye", "sayfa", "tom",
    "izdanie", "sbornik", "kniga", "seriya", "god", "goda", "novel", "poems",
}


def skeleton(s: str) -> str:
    s = unicodedata.normalize("NFC", s).lower()
    for a, b in _CYR:
        s = s.replace(a, b)
    for a, b in _LAT:
        s = s.replace(a, b)
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def tokens(s: str, minlen: int = 4) -> list[str]:
    return [t for t in skeleton(s).split() if len(t) >= minlen and t not in STOP]


def similar(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b).ratio()


def best_token_hit(tok: str, pool: list[str], substring_ok: bool = True) -> float:
    """How well one token is represented in a filename's token pool.

    `substring_ok=False` for author names: containment turns "abilkerim" into a
    perfect match for "kerim", i.e. one poet's name swallowing another's.
    """
    best = 0.0
    for p in pool:
        if tok == p:
            return 1.0
        if substring_ok and len(tok) >= 6 and (tok in p or p in tok):
            return 1.0
        best = max(best, similar(tok, p))
    return best


def load_books() -> list[dict]:
    books = []
    for dirpath, dirnames, files in os.walk(LIBRARY):
        rel = os.path.relpath(dirpath, LIBRARY)
        top = rel.split(os.sep)[0]
        if top in SKIP_DIRS:
            dirnames[:] = []
            continue
        for f in files:
            if f.lower().endswith(BOOK_EXTS) and not f.startswith("."):
                books.append({
                    "path": os.path.join(rel, f) if rel != "." else f,
                    "name": f,
                    "tokens": tokens(f, 3),
                })
    return books


def load_recordings() -> list[dict]:
    recs: list[dict] = []

    ley = json.load(open(os.path.join(SOURCES, "leylaemir-org/INDEX.json")))
    for r in ley:
        author, work = r.get("author", ""), r.get("work", "")
        # Known defect in that index: for folk tales the two fields are swapped,
        # so the "work" reads "Qırım(tatar) halq masalı" and the title sits in
        # "author". Read them the right way round; the source stays untouched.
        if "halq masal" in work.lower():
            author, work = "", author
        recs.append({"source": "leylaemir-org", "author": author,
                     "work": work, "file": r.get("file", "")})

    trk = json.load(open(os.path.join(SOURCES, "trkmillet/INDEX.json")))
    for b in trk["books"]:
        recs.append({"source": "trkmillet", "author": b.get("author", ""),
                     "work": b.get("title", ""), "file": b.get("title", "")})

    # Maye Safet: titles carry "Author. Work" in most cases. Prefer the canonical
    # (Telegram) copies from the dedup map so duplicates are not matched twice.
    dm_path = os.path.join(SOURCES, "maye-safet/dedup_map.json")
    dupe_yt = set()
    if os.path.exists(dm_path):
        dm = json.load(open(dm_path))
        dupe_yt = {r["youtube"] for r in dm["duplicates"]}
    yt_dir = os.path.join(SOURCES, "maye-safet/youtube")
    for f in sorted(os.listdir(yt_dir)):
        if not f.endswith(".info.json"):
            continue
        stem = f[: -len(".info.json")]
        if stem + ".m4a" in dupe_yt or not os.path.exists(os.path.join(yt_dir, stem + ".m4a")):
            continue
        try:
            title = json.load(open(os.path.join(yt_dir, f))).get("title", stem)
        except Exception:
            continue
        author, _, work = title.partition(".")
        if not work.strip() or len(author.split()) > 4:
            author, work = "", title
        recs.append({"source": "maye-safet/youtube", "author": author.strip(),
                     "work": work.strip(" .") or title, "file": stem + ".m4a"})

    tg_dir = os.path.join(SOURCES, "maye-safet/telegram-arifler_ve_ses")
    for f in sorted(os.listdir(tg_dir)):
        if not f.lower().endswith((".mp3", ".mp4")):
            continue
        name = re.sub(r"^\d+_(\d+_)?", "", os.path.splitext(f)[0]).replace("_", " ")
        if re.fullmatch(r"[\d\s]*", name):  # bare "334_75" — no title to match on
            continue
        recs.append({"source": "maye-safet/telegram", "author": "",
                     "work": name.strip(), "file": f})
    return recs


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--min", type=float, default=0.6, help="title score for a strong match")
    ap.add_argument("--top", type=int, default=3, help="candidates kept per recording")
    args = ap.parse_args()

    books = load_books()
    recs = load_recordings()
    print(f"library: {len(books)} book files · recordings: {len(recs)}", flush=True)

    results = []
    for i, rec in enumerate(recs, 1):
        atoks = tokens(rec["author"], 4)
        wtoks = tokens(rec["work"], 4)
        if not wtoks and not atoks:
            continue
        scored = []
        for b in books:
            pool = b["tokens"]
            if not pool:
                continue
            a_hit = max((best_token_hit(t, pool, substring_ok=False) for t in atoks),
                        default=0.0)
            w_hits = [best_token_hit(t, pool) for t in wtoks]
            w_score = sum(1 for h in w_hits if h >= 0.85) / len(wtoks) if wtoks else 0.0
            score = 0.55 * w_score + 0.45 * (a_hit if a_hit >= 0.85 else 0.0)
            if score > 0.25:
                scored.append((round(score, 3), round(w_score, 2),
                               round(a_hit, 2), b["path"]))
        scored.sort(reverse=True)
        top = scored[: args.top]
        # A one-word title ("Yüregim", "Isteklerim") is not evidence: any book
        # whose filename happens to carry that word scores a perfect title match.
        # Such records can still be placed by their author, never by their title.
        title_usable = len(wtoks) >= 2
        tier = "none"
        if top:
            w, a = top[0][1], top[0][2]
            if w >= args.min and a >= 0.85 and title_usable:
                tier = "strong"
            elif w >= args.min and title_usable:
                tier = "title-only"
            elif a >= 0.85:
                tier = "author-only"
            else:
                tier = "weak"
        results.append({**rec, "tier": tier,
                        "key": f"{rec['source']}|{skeleton(rec['author'])}|{skeleton(rec['work'])}",
                        "candidates": [{"score": s, "title_score": w, "author_score": a,
                                        "book": p} for s, w, a, p in top]})
        if i % 50 == 0:
            print(f"  {i}/{len(recs)}", flush=True)

    tiers = {t: sum(1 for r in results if r["tier"] == t)
             for t in ("strong", "title-only", "author-only", "weak", "none")}
    payload = {"library_files": len(books), "recordings": len(results),
               "tiers": tiers, "matches": results}
    json.dump(payload, open(OUT_JSON, "w"), ensure_ascii=False, indent=2)

    md = [
        "# Recordings ⇄ books — candidate matches", "",
        "Generated by `scripts/corpus/match_books.py`. **Candidates for review, not",
        "decisions.** A filename match is evidence that a book *may* carry the text:",
        "collections and «Saylama eserler» volumes hold many works, and titles repeat",
        "across authors. Confirm before feeding a pair to forced alignment.", "",
        f"Library scanned: {len(books)} book files · recordings matched: {len(results)}", "",
        "| Tier | Meaning | Count |", "|---|---|---|",
        f"| strong | author *and* title agree | {tiers['strong']} |",
        f"| title-only | title agrees, author not found in the filename | {tiers['title-only']} |",
        f"| author-only | a book by this author exists, this work not identified | {tiers['author-only']} |",
        f"| weak | partial overlap only | {tiers['weak']} |",
        f"| none | no candidate above threshold | {tiers['none']} |", "",
    ]
    def cell(s: str) -> str:
        return s.replace("|", "/").replace("\n", " ").strip()

    for tier in ("strong", "title-only", "author-only"):
        rows = [r for r in results if r["tier"] == tier]
        if not rows:
            continue
        # Long works are split into many recordings (parts/chapters); collapse
        # them to one row per work so the table shows works, not file counts.
        grouped: dict[str, dict] = {}
        for r in rows:
            g = grouped.setdefault(r["key"], {**r, "parts": 0})
            g["parts"] += 1
            if r["candidates"][0]["score"] > g["candidates"][0]["score"]:
                g["candidates"] = r["candidates"]
        md += [f"## {tier} — {len(grouped)} works / {len(rows)} recordings", "",
               "| Source | Author | Work | Parts | Book candidate | Score |",
               "|---|---|---|---|---|---|"]
        for r in sorted(grouped.values(), key=lambda r: -r["candidates"][0]["score"]):
            c = r["candidates"][0]
            md.append(f"| {r['source']} | {cell(r['author']) or '—'} | {cell(r['work'])[:60]} "
                      f"| {r['parts']} | `{cell(c['book'])}` | {c['score']} |")
        md += [""]
    open(OUT_MD, "w").write("\n".join(md))

    print("tiers:", tiers)
    print(f"→ {OUT_JSON}\n→ {OUT_MD}")


if __name__ == "__main__":
    main()
