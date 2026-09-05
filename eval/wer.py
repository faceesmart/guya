"""
Text normalization + Word/Character Error Rate — no external dependencies.

WER/CER are computed at the CORPUS level (total edits / total reference units),
which is the standard way to report them. normalize_* makes the comparison fair
by applying the SAME rules to the reference and the hypothesis:

  both languages
    - Unicode NFC, lowercase (Latin letters), punctuation removed
    - Persian/Arabic-Indic digits -> ASCII digits
    - spelled-out numbers 0-99 -> digits ("twelve" -> "12", "بیست و یک" -> "21"),
      because Whisper writes digits by default and a correct transcription must
      not be counted as an error
  Persian only
    - Arabic letter forms -> Persian forms (ي->ی, ك->ک, ة->ه ...); the genuine
      Persian letters آ and ئ are NOT folded, so «اب» for «آب» is an error
    - diacritics, tatweel, bidi marks and the zero-width non-joiner removed
      (ZWNJ usage is inconsistent between writers, so «می‌خواهم» and «میخواهم»
      are treated as the same word)

What is NOT normalised, on purpose: spacing of compound words («کتاب ها» vs
«کتابها»), numbers above 99, and spelling variants. These count as errors for
every model equally. CER is reported alongside WER because it is far less
sensitive to Persian word-boundary conventions.
"""

import re
import unicodedata

# Arabic → Persian character unification. Only Arabic letter FORMS are folded
# (ي/ك/ة and presentation forms); genuine Persian letters such as آ and ئ are
# kept, because writing «اب» for «آب» is a real error and must count as one.
_AR2FA = {
    "ي": "ی", "ى": "ی", "ﻯ": "ی", "ﻱ": "ی",
    "ك": "ک", "ﮎ": "ک",
    "إ": "ا", "أ": "ا", "ٱ": "ا",
    "ة": "ه", "ۀ": "ه",
}
_AR2FA_TABLE = str.maketrans(_AR2FA)
# Harakat (U+064B..U+065F), superscript alef, tatweel, ZWNJ/ZWJ, bidi marks.
_STRIP_FA = re.compile("[ً-ٰٟـ‌‍‎‏‪-‮]")
_STRIP_EN = re.compile("[‌‍‎‏‪-‮]")
# Persian + Arabic-Indic digits → ASCII
_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)
_WS = re.compile(r"\s+")

_EN_UNITS = {
    "zero": 0, "oh": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
    "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
    "seventeen": 17, "eighteen": 18, "nineteen": 19,
}
_EN_TENS = {
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
    "seventy": 70, "eighty": 80, "ninety": 90,
}
_FA_UNITS = {
    "صفر": 0, "یک": 1, "دو": 2, "سه": 3, "چهار": 4, "پنج": 5, "شش": 6,
    "شیش": 6, "هفت": 7, "هشت": 8, "نه": 9, "ده": 10, "یازده": 11,
    "دوازده": 12, "سیزده": 13, "چهارده": 14, "پانزده": 15, "پونزده": 15,
    "شانزده": 16, "شونزده": 16, "هفده": 17, "هیفده": 17, "هجده": 18,
    "هیجده": 18, "نوزده": 19,
}
_FA_TENS = {
    "بیست": 20, "سی": 30, "چهل": 40, "پنجاه": 50, "شصت": 60, "هفتاد": 70,
    "هشتاد": 80, "نود": 90,
}


def _words_to_digits(tokens, units, tens, connector):
    """Rewrite spelled-out 0-99 as digits. Only 'tens [connector] unit' is
    merged, so a bare connector ("and"/"و") elsewhere is left untouched."""
    out = []
    i = 0
    n = len(tokens)
    while i < n:
        tok = tokens[i]
        if tok in tens:
            value = tens[tok]
            j = i + 1
            if connector and j < n and tokens[j] == connector:
                j += 1
            if j < n and tokens[j] in units and 0 < units[tokens[j]] < 10:
                out.append(str(value + units[tokens[j]]))
                i = j + 1
                continue
            out.append(str(value))
            i += 1
            continue
        if tok in units:
            out.append(str(units[tok]))
            i += 1
            continue
        out.append(tok)
        i += 1
    return out


def normalize_fa(text: str) -> str:
    text = unicodedata.normalize("NFC", text or "").lower()
    text = text.translate(_AR2FA_TABLE)
    text = _STRIP_FA.sub("", text)
    text = text.translate(_DIGITS)
    text = _PUNCT.sub(" ", text)
    tokens = _words_to_digits(text.split(), _FA_UNITS, _FA_TENS, "و")
    return " ".join(tokens)


def normalize_en(text: str) -> str:
    text = unicodedata.normalize("NFC", (text or "").lower())
    text = _STRIP_EN.sub("", text)
    text = text.translate(_DIGITS)
    text = text.replace("-", " ")           # twenty-one -> twenty one
    text = _PUNCT.sub(" ", text)
    tokens = _words_to_digits(text.split(), _EN_UNITS, _EN_TENS, None)
    return " ".join(tokens)


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


def rate(edits: int, n_ref: int) -> float:
    """Error rate as a fraction. With an empty reference, any output is a
    100% error and no output is 0%; one rule for every code path."""
    if n_ref:
        return edits / n_ref
    return 1.0 if edits else 0.0


def wer(ref: str, hyp: str, lang: str) -> float:
    """Single-utterance WER as a fraction (1.0 == 100%)."""
    return rate(*wer_counts(ref, hyp, lang))


def cer(ref: str, hyp: str, lang: str) -> float:
    return rate(*cer_counts(ref, hyp, lang))
