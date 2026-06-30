#!/usr/bin/env python3
"""Crimean-Tatar Cyrillic -> ASCII romanization for forced alignment ONLY.

The MMS CTC alignment model speaks a romanized latin alphabet (a-z + ').
This module converts each source token to that alphabet so the acoustic model
can match it against the audio. It does NOT touch the dataset text — the final
metadata keeps the original orthography; this is purely an alignment aid.

Swapping in a higher-quality crh transliterator:
    Set CRH_TRANSLITERATE to a function `str -> str` that maps a Cyrillic
    token to latin crh (e.g. Turkish-style `q ñ ğ ç ş ı ö ü c`). Everything
    else (folding to the a-z+' MMS vocab) is handled by `romanize_token`.
    The default below uses generic `unidecode`, which mis-handles the crh
    digraphs (къ->k instead of q, нъ->n, гъ->g, дж->dzh).
"""
import re

from unidecode import unidecode

# Fold latin-crh letters with diacritics down to the MMS a-z+' vocabulary.
# `q` is kept distinct from `k` (uvular vs velar — MMS models them separately).
_FOLD = str.maketrans({
    "ñ": "n", "ğ": "g", "ç": "c", "ş": "s", "ı": "i",
    "ö": "o", "ü": "u", "â": "a", "û": "u", "î": "i", "ə": "e",
    "Ñ": "n", "Ğ": "g", "Ç": "c", "Ş": "s", "İ": "i",
    "Ö": "o", "Ü": "u", "Q": "q",
})

# Hook: assign a `str -> str` Cyrillic->latin-crh transliterator to override the
# generic default. Left None until the project's crh script is wired in.
CRH_TRANSLITERATE = None


def _to_ascii_vocab(latin: str) -> str:
    """Fold any latin string to the MMS a-z+' alphabet."""
    latin = latin.translate(_FOLD).lower()
    return re.sub(r"[^a-z']", "", latin)


def romanize_token(token: str) -> str:
    """Romanize one source token to the a-z+' alignment alphabet.

    May return "" for punctuation-only tokens; callers must preserve the empty
    slot so token<->word indexing stays 1:1.
    """
    if CRH_TRANSLITERATE is not None:
        return _to_ascii_vocab(CRH_TRANSLITERATE(token))
    return _to_ascii_vocab(unidecode(token))


def build_alignment_inputs(orig_tokens):
    """Replicate ctc_forced_aligner.preprocess_text(star_frequency='segment')
    but romanize per original token so:
      * the token count stays 1:1 with the source words, and
      * `text_starred` carries the ORIGINAL orthography (not the romanization).

    Returns (tokens_starred, text_starred) ready for get_alignments/get_spans.
    """
    tokens_starred, text_starred = [], []
    for tok in orig_tokens:
        spaced = " ".join(list(romanize_token(tok)))  # MMS expects spaced chars
        tokens_starred.extend(["<star>", spaced])
        text_starred.extend(["<star>", tok])
    return tokens_starred, text_starred
