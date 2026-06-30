#!/usr/bin/env python3
"""Extract and clean a book's transcript into one sentence per line.

Handles .txt / .odt (via pandoc) / .pdf (via pdftotext). The output is the
*ground-truth orthography* used both for forced alignment and for the final
dataset metadata, so we keep original casing and punctuation and only fix
mechanical artefacts (soft hyphens, line-wrap hyphenation, stray whitespace).

Usage:
    prepare_text.py <source_file> <out_clean_txt>
"""
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

# Sentence-ending punctuation for Crimean Tatar (Cyrillic) prose.
SENT_END = ".!?…"
# Minimum words for a standalone sentence; shorter fragments get glued to the
# following sentence so we never emit a lone "–" or single interjection.
MIN_SENT_WORDS = 2


def extract_text(src: Path) -> str:
    ext = src.suffix.lower()
    if ext == ".txt":
        return src.read_text(encoding="utf-8", errors="replace")
    if ext == ".odt":
        return subprocess.run(
            ["pandoc", "-t", "plain", "--wrap=none", str(src)],
            capture_output=True, text=True, check=True,
        ).stdout
    if ext == ".pdf":
        return subprocess.run(
            ["pdftotext", "-nopgbrk", "-enc", "UTF-8", str(src), "-"],
            capture_output=True, text=True, check=True,
        ).stdout
    raise ValueError(f"unsupported source type: {ext}")


def clean(raw: str) -> str:
    # Normalise unicode and unify dash / quote variants that hurt tokenisation.
    # Newlines are PRESERVED here: source lines are paragraph/verse units
    # (.txt and pandoc --wrap=none .odt are not wrapped), so each line is a
    # natural break that keeps titles/bylines from gluing onto prose.
    txt = unicodedata.normalize("NFC", raw)
    txt = txt.replace("­", "")            # soft hyphen (line-wrap artefact)
    txt = txt.replace("﻿", "")            # BOM
    # Join words split across a line break by a hyphen: "сло-\nво" -> "слово".
    txt = re.sub(r"(\w)[-‐]\n(\w)", r"\1\2", txt)
    txt = txt.replace("\r", "\n")
    # Unify quote and dash glyphs (kept in text, but consistent).
    txt = txt.replace("«", '"').replace("»", '"').replace("“", '"').replace("”", '"')
    txt = txt.replace("—", "–").replace("―", "–")
    return txt


_ENDS_SENTENCE = re.compile(rf'[{SENT_END}]["\')\]]?$')


def unwrap(txt: str) -> list[str]:
    """Reflow source lines into paragraphs.

    Real data is inconsistent: some files hard-wrap mid-sentence, others put
    one paragraph per line. Rule: a blank line is a hard paragraph break;
    otherwise a line is joined to the running paragraph unless that paragraph
    already ends with sentence punctuation (then it starts a new one). This
    both un-wraps mid-sentence breaks and keeps unpunctuated titles/headings
    (followed by a blank line) from gluing onto the body.
    """
    paragraphs: list[str] = []
    cur = ""
    for line in txt.split("\n"):
        s = re.sub(r"\s+", " ", line).strip()
        if not s:
            if cur:
                paragraphs.append(cur)
                cur = ""
            continue
        if not cur:
            cur = s
        elif _ENDS_SENTENCE.search(cur):
            paragraphs.append(cur)
            cur = s
        else:
            cur = f"{cur} {s}"
    if cur:
        paragraphs.append(cur)
    return paragraphs


def split_sentences(txt: str) -> list[str]:
    pattern = re.compile(rf'(?<=[{SENT_END}])["\')\]]?\s+')
    parts: list[str] = []
    for para in unwrap(txt):
        # Split each paragraph after sentence-ending punctuation (plus an
        # optional closing quote), keeping the punctuation on the left part.
        parts.extend(p.strip() for p in pattern.split(para) if p.strip())

    # Glue fragments that are too short onto the following sentence.
    merged: list[str] = []
    buf = ""
    for p in parts:
        cand = (buf + " " + p).strip() if buf else p
        if len(cand.split()) < MIN_SENT_WORDS:
            buf = cand
        else:
            merged.append(cand)
            buf = ""
    if buf:
        if merged:
            merged[-1] = (merged[-1] + " " + buf).strip()
        else:
            merged.append(buf)
    return merged


def main() -> None:
    src = Path(sys.argv[1])
    out = Path(sys.argv[2])
    sentences = split_sentences(clean(extract_text(src)))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(sentences) + "\n", encoding="utf-8")
    n_digit = sum(1 for s in sentences if re.search(r"\d", s))
    print(f"{src.name}: {len(sentences)} sentences "
          f"({n_digit} contain digits) -> {out}")


if __name__ == "__main__":
    main()
