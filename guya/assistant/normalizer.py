"""Text normalization used before bilingual command parsing."""

import re
from difflib import SequenceMatcher
from typing import Optional, Tuple


_PERSIAN_TRANSLATION = str.maketrans({
    "ي": "ی",
    "ى": "ی",
    "ك": "ک",
    "ة": "ه",
    "ۀ": "ه",
    "ؤ": "و",
    "إ": "ا",
    "أ": "ا",
})

_PERSIAN_DIACRITICS = re.compile(r"[\u064B-\u065F\u0670\u06D6-\u06ED]")
_PUNCTUATION = re.compile(r"""[،؛؟,.!?;:"'“”‘’()\[\]{}]""")
_SPACES = re.compile(r"\s+")
_FILENAME_SEPARATORS = re.compile(r"[\s._-]+")
_DIGIT_TRANSLATION = str.maketrans(
    "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩",
    "01234567890123456789",
)

_EN_SMALL_NUMBERS = {
    "zero": 0,
    "oh": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
}
_EN_TENS = {
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
    "sixty": 60,
    "seventy": 70,
    "eighty": 80,
    "ninety": 90,
}
_FA_SMALL_NUMBERS = {
    "صفر": 0,
    "یک": 1,
    "یه": 1,
    "دو": 2,
    "سه": 3,
    "چهار": 4,
    "چار": 4,
    "پنج": 5,
    "شش": 6,
    "شیش": 6,
    "هفت": 7,
    "هشت": 8,
    "نه": 9,
    "ده": 10,
    "یازده": 11,
    "دوازده": 12,
    "سیزده": 13,
    "چهارده": 14,
    "پانزده": 15,
    "پونزده": 15,
    "شانزده": 16,
    "شونزده": 16,
    "هفده": 17,
    "هیفده": 17,
    "هجده": 18,
    "هیجده": 18,
    "نوزده": 19,
}
_FA_TENS = {
    "بیست": 20,
    "سی": 30,
    "چهل": 40,
    "پنجاه": 50,
    "شصت": 60,
    "هفتاد": 70,
    "هشتاد": 80,
    "نود": 90,
}
_EXTENSIONS = {"docx", "doc", "txt", "pdf", "xlsx", "pptx"}
_TRAILING_TYPE_WORDS = {
    "file",
    "document",
    "folder",
    "directory",
    "فایل",
    "سند",
    "پوشه",
    "فولدر",
}
_LEADING_FILENAME_WORDS = {
    "the",
    "my",
    "named",
    "called",
    "فایل",
    "سند",
    "پوشه",
    "فولدر",
}


def has_persian(text: str) -> bool:
    return bool(re.search(r"[\u0600-\u06FF\uFB50-\uFDFF\uFE70-\uFEFF]", text or ""))


def detect_language(text: str) -> str:
    return "fa" if has_persian(text) else "en"


def normalize(text: str) -> str:
    value = (text or "").strip().lower().translate(_DIGIT_TRANSLATION)
    value = value.translate(_PERSIAN_TRANSLATION)
    value = _PERSIAN_DIACRITICS.sub("", value)
    value = value.replace("\u200c", " ").replace("_", " ")
    value = _PUNCTUATION.sub(" ", value)
    return _SPACES.sub(" ", value).strip()


def clean_slot(value: str) -> str:
    """Remove speech punctuation and common trailing command words."""
    value = (value or "").strip().strip(" .،؟?!\"'")
    value = re.sub(
        r"\s+(?:please|for me|لطفا|لطفاً|برام|برای من)$",
        "",
        value,
        flags=re.IGNORECASE,
    )
    return value.strip()


def _replace_spoken_numbers(tokens: list) -> list:
    """Convert common English/Persian number words from zero through 99."""
    output = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        small = _FA_SMALL_NUMBERS if token in _FA_SMALL_NUMBERS else _EN_SMALL_NUMBERS
        tens = _FA_TENS if token in _FA_TENS else _EN_TENS
        connector = "و" if token in _FA_TENS else None

        if token in small:
            output.append(str(small[token]))
            index += 1
            continue

        if token in tens:
            number = tens[token]
            next_index = index + 1
            if connector and next_index < len(tokens) and tokens[next_index] == connector:
                next_index += 1
            if next_index < len(tokens):
                following = tokens[next_index]
                following_small = (
                    _FA_SMALL_NUMBERS.get(following)
                    if token in _FA_TENS
                    else _EN_SMALL_NUMBERS.get(following)
                )
                if following_small is not None and 0 < following_small < 10:
                    number += following_small
                    index = next_index + 1
                    output.append(str(number))
                    continue
            output.append(str(number))
            index += 1
            continue

        output.append(token)
        index += 1
    return output


def normalize_spoken_filename(text: str) -> str:
    """Canonical, readable filename form for speech and disk names.

    Examples:
      ``test six docks`` → ``test 6 docx``
      ``test6.docx``     → ``test6 docx``
      ``گزارش شش ورد``  → ``گزارش 6 docx``
    """
    value = normalize(text)
    value = _FILENAME_SEPARATORS.sub(" ", value)
    tokens = _replace_spoken_numbers(value.split())

    while tokens and tokens[0] in _LEADING_FILENAME_WORDS:
        tokens.pop(0)

    # Whisper commonly hears the DOCX suffix as "docs", "docks", or
    # two tokens ("doc x"). Only rewrite suffix-like words at the end so a
    # legitimate filename containing "docs" in the middle remains intact.
    if len(tokens) >= 2 and tokens[-2:] in (
        ["word", "file"],
        ["word", "document"],
        ["فایل", "ورد"],
        ["سند", "ورد"],
    ):
        tokens[-2:] = ["docx"]
    else:
        while tokens and tokens[-1] in _TRAILING_TYPE_WORDS:
            tokens.pop()

    # Only rewrite a suffix-like last token when something precedes it; an
    # item literally named "docs" or "text" keeps its name.
    if len(tokens) >= 2 and tokens[-2:] == ["doc", "x"]:
        tokens[-2:] = ["docx"]
    elif len(tokens) >= 2 and tokens[-1] in {"docs", "docks", "docx", "ورد", "دکس", "داکس", "داکیومنت"}:
        tokens[-1] = "docx"
    elif len(tokens) >= 2 and tokens[-1] in {"text", "تکست", "txt"}:
        tokens[-1] = "txt"

    return " ".join(tokens).strip()


def filename_keys(text: str) -> Tuple[str, str, Optional[str]]:
    """Return compact full key, stem key, and recognized extension."""
    normalized = normalize_spoken_filename(text)
    tokens = normalized.split()
    extension = tokens[-1] if tokens and tokens[-1] in _EXTENSIONS else None
    stem_tokens = tokens[:-1] if extension else tokens
    full_key = "".join(tokens)
    stem_key = "".join(stem_tokens)
    return full_key, stem_key, extension


def filename_match_score(query: str, candidate: str) -> Tuple[float, bool]:
    """Score a spoken query against a filename without guessing too broadly."""
    query_full, query_stem, query_extension = filename_keys(query)
    item_full, item_stem, item_extension = filename_keys(candidate)
    if not query_stem or not item_stem:
        return 0.0, False

    if query_full == item_full:
        return 1.0, True
    if query_stem == item_stem:
        extension_conflict = (
            query_extension
            and item_extension
            and query_extension != item_extension
        )
        return (0.90 if extension_conflict else 0.98), not extension_conflict

    score = SequenceMatcher(None, query_stem, item_stem).ratio() * 0.76
    # Never grant a strong containment score from a one- or two-character
    # fragment.  Without this guard, a query such as "system" could treat a
    # folder named "m" as a confident match simply because "m" occurs in the
    # word "system".
    shorter_length = min(len(query_stem), len(item_stem))
    if shorter_length >= 3 and (
        item_stem.startswith(query_stem) or query_stem.startswith(item_stem)
    ):
        score = max(score, 0.86)
    elif shorter_length >= 3 and (
        query_stem in item_stem or item_stem in query_stem
    ):
        score = max(score, 0.82)

    query_tokens = set(normalize_spoken_filename(query).split())
    item_tokens = set(normalize_spoken_filename(candidate).split())
    query_tokens -= _EXTENSIONS
    item_tokens -= _EXTENSIONS
    if query_tokens:
        overlap = len(query_tokens & item_tokens) / len(query_tokens)
        score = max(score, overlap * 0.80)

    if query_extension and item_extension:
        score += 0.04 if query_extension == item_extension else -0.08
    return max(0.0, min(score, 0.97)), False
