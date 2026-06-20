"""
Text normalization + Word/Character Error Rate — no external dependencies.

WER/CER are computed at the CORPUS level (total edits / total reference units),
which is the standard way to report them. normalize_* makes the comparison fair
by removing punctuation/diacritics and unifying Arabic↔Persian characters and
digit forms — the same normalization is applied to reference and hypothesis.
"""

import re
import unicodedata

# Arabic → Persian character unification + remove zero-width non-joiner.
_AR2FA = {
    "ي": "ی", "ك": "ک", "ى": "ی", "ﻯ": "ی", "ﻱ": "ی",
    "ؤ": "و", "إ": "ا", "أ": "ا", "آ": "ا", "ة": "ه",
    "ي": "ی", "ك": "ک",
}
_AR2FA_TABLE = str.maketrans(_AR2FA)
_DIACRITICS = re.compile(r"[ً-ٰٟ‌‏‎]")
# digits: Arabic-Indic + Persian → ASCII
_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)
_WS = re.compile(r"\s+")


def normalize_fa(text: str) -> str:
    text = unicodedata.normalize("NFC", text or "")
    text = text.translate(_AR2FA_TABLE)
    text = _DIACRITICS.sub("", text)
    text = text.translate(_DIGITS)
    text = _PUNCT.sub(" ", text)
    return _WS.sub(" ", text).strip()


def normalize_en(text: str) -> str:
    text = unicodedata.normalize("NFC", (text or "").lower())
    text = text.translate(_DIGITS)
    text = _PUNCT.sub(" ", text)
    return _WS.sub(" ", text).strip()


def normalize(text: str, lang: str) -> str:
    return normalize_fa(text) if lang == "fa" else normalize_en(text)


def _edit_distance(ref, hyp):
    """Levenshtein distance between two sequences (lists/strings)."""
    n, m = len(ref), len(hyp)
    if n == 0:
        return m
    prev = list(range(m + 1))
    for i in range(1, n + 1):
        cur = [i] + [0] * m
        for j in range(1, m + 1):
            cost = 0 if ref[i - 1] == hyp[j - 1] else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
        prev = cur
    return prev[m]


def wer_counts(ref: str, hyp: str, lang: str):
    """Return (edits, n_ref_words) for word error rate."""
    r = normalize(ref, lang).split()
    h = normalize(hyp, lang).split()
    return _edit_distance(r, h), len(r)


def cer_counts(ref: str, hyp: str, lang: str):
    """Return (edits, n_ref_chars) for character error rate (no spaces)."""
    r = normalize(ref, lang).replace(" ", "")
    h = normalize(hyp, lang).replace(" ", "")
    return _edit_distance(r, h), len(r)
