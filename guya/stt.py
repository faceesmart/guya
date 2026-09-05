"""
Guya speech-to-text pipeline — everything between raw microphone audio and the
final text, independent of the widget and of Qt.

This is the exact pipeline the desktop widget runs (widget.py imports it), so
the evaluation harness can measure *Guya* rather than stock faster-whisper:

    audio  -> RMS normalisation
           -> faster-whisper (beam 5, VAD, per-language prompt,
              no-speech threshold; temperature fallback in dual mode only)
           -> per-segment hallucination filter
           -> Persian post-processing (Arabic->Persian characters, diacritics,
              spacing, word corrections, colloquial preservation)

The online (cloud) backend goes through the same post-processing so the two
paths produce comparable text.
"""

import logging
import re
from collections import Counter

import numpy as np

try:
    from . import cloud_engine
except ImportError:  # run as a loose script
    import cloud_engine

log = logging.getLogger("Guya")


# ============================================================
# PERSIAN TEXT NORMALIZATION
# ============================================================

# Arabic-to-Persian character map (lightweight, no external deps)
_ARABIC_TO_PERSIAN = str.maketrans({
    '\u064A': '\u06CC',  # ي → ی
    '\u0643': '\u06A9',  # ك → ک
    '\u0629': '\u0647',  # ة → ه
    '\u0649': '\u06CC',  # ى → ی
    '\u06C0': '\u0647',  # ۀ → ه
    '\u0624': '\u0648',  # ؤ → و
})

# Arabic diacritics to strip (fathah, dammah, kasrah, sukun, shadda, tanwin, etc.)
_ARABIC_DIACRITICS = re.compile(r'[\u064B-\u065F\u0670]')

# Common Whisper hallucination phrases (Persian & cross-language)
_HALLUCINATION_PATTERNS = [
    # Whole hallucination phrases only. Single words such as «ترجمه» or
    # "subscribe" used to be here and deleted real sentences containing them.
    "ساب اسکرایب",
    "سابسکرایب",
    "please subscribe",
    "like and subscribe",
    "thanks for watching",
    "ممنون از اینکه",
    "ممنون که گوش دادید",
    "ادامه دارد",
    "تماشا کنید",
    "لطفا لایک کنید",
    "زیرنویس توسط",
    "ترجمه و زیرنویس",
    "زیرنویس و ترجمه",
    "www.",
    "http://",
    "https://",
]


def normalize_persian(text: str) -> str:
    """Normalize Persian text: fix Arabic chars, spacing, half-spaces, punctuation.

    Lightweight — no external dependencies (hazm removed to avoid CUDA conflicts).
    """
    if not text:
        return text

    # Step 1: Arabic→Persian character substitution
    text = text.translate(_ARABIC_TO_PERSIAN)

    # Step 2: Strip Arabic diacritics (اعراب)
    text = _ARABIC_DIACRITICS.sub('', text)

    # Step 3: Fix common spacing issues
    # Remove space before punctuation: "سلام ." → "سلام."
    text = re.sub(r'\s+([\.،؛:؟!])', r'\1', text)
    # Ensure space after punctuation when it sits between two words, but not
    # inside numbers: «ساعت 10:30» and «نسخه 3.5» must stay intact.
    text = re.sub(r'(?<!\d)([\.،؛:؟!])(\w)', r'\1 \2', text)
    # Collapse multiple spaces
    text = re.sub(r'  +', ' ', text)

    return text.strip()


# ============================================================
# WORD CORRECTION (post-processing)
# ============================================================

_WORD_CORRECTIONS = {
    # --- Original project-specific corrections ---
    "اقامدگاه": "اقامتگاه",
    "عقامتگاه": "اقامتگاه",
    "عقامتگاهی": "اقامتگاهی",
    "حزینه": "هزینه",
    "رزروع": "رزرو",
    "پنشمبه": "پنجشنبه",
    "تقمیمش": "تقویمش",
    "مرای": "برای",
    "سرچ گردن": "سرچ کردن",
    "فل تک سرچ": "فول تکست سرچ",
    "اویلبل": "اوِیلبل",
    "جا باما": "جاباما",
    "جاواما": "جاباما",
    "بابا ما": "جاباما",
    "جواب آما": "جاباما",
    "فرایده": "فرایدی",

    # --- Character confusion (similar-sounding letters: ب↔پ، د↔ت، ز↔ذ، ر↔ب) ---
    "گفتاب": "گفتار",
    "مودل": "مدل",
    "برگذار": "برگزار",
    "برگذاری": "برگزاری",
    "فندی": "فنی",
    "اسنب": "اسنپ",
    "تیجیکالا": "دیجیکالا",
    "دیجی‌کالا": "دیجیکالا",
    "پرو سراغ": "برو سراغ",

    # --- Word splitting / merging errors ---
    "عمل کرده سیستم": "عملکرد سیستم",
    "پارامت های": "پارامترهای",
    "پارامت‌های": "پارامترهای",
    "گفتاب متر": "گفتار به متن",
    "گفتار بمتن": "گفتار به متن",

    # --- Common Whisper misrecognitions for Persian ---
    "مثلی": "متنی",
    "سراغمون": "سراغ اون",
    "دیری": "دیر",
    "جلسته": "جلسه",
    "اموز": "امروز",
    "هوم اسفند": "اسفند",
    "روابط پایتون": "رابط پایتون",
    "دوازده هام": "دوازدهم",
    "دوازده‌هام": "دوازدهم",
    "محمد رزا": "محمدرضا",
    "محمد رضا": "محمدرضا",
    "دیژیکاله ها": "دیجیکالا",
    "دیژیکالا": "دیجیکالا",
    "دیجی کالا": "دیجیکالا",

    # --- Tech terms Whisper often gets wrong ---
    "اپ دیت": "آپدیت",
    "اپلود": "آپلود",
    "دانلد": "دانلود",
    "سروور": "سرور",
    "سرویر": "سرور",
    "ریپازیتوری": "ریپوزیتوری",
    "دیتا بیس": "دیتابیس",
    "فریم ورک": "فریمورک",
    "ایندکس": "ایندکس",
    "تایم اوت": "تایم‌اوت",
    "لاگ این": "لاگین",
    "باگ فیکس": "باگ‌فیکس",

    # --- Brand names ---
    "اسنب فود": "اسنپ‌فود",
    "اسنب‌فود": "اسنپ‌فود",
    "تلگرم": "تلگرام",
    "واتس اپ": "واتساپ",
    "واتس‌اپ": "واتساپ",
    "گیت هاب": "گیتهاب",
    "گیت‌هاب": "گیتهاب",

    # --- Common Persian word errors ---
    "میکروفن": "میکروفون",
    "میکروفم": "میکروفون",
}


_WORD_CORRECTION_PATTERNS = [
    # Whole words only: a bare substring replace turned «مدیریت» into «مدیرت»
    # and «اموزش» into «امروزش». Longer keys first so multi-word fixes win.
    (re.compile(r"(?<!\w)" + re.escape(wrong) + r"(?!\w)"), right)
    for wrong, right in sorted(_WORD_CORRECTIONS.items(), key=lambda x: -len(x[0]))
    if wrong != right
]


def apply_word_corrections(text: str) -> str:
    """Fix common Whisper misrecognitions using a lookup dictionary."""
    if not text:
        return text
    for pattern, right in _WORD_CORRECTION_PATTERNS:
        text = pattern.sub(right, text)
    return text


# ============================================================
# COLLOQUIAL PRESERVATION (formal → colloquial)
# ============================================================

# Whisper often formalizes colloquial Persian speech. These regex rules
# convert formal verb forms back to their colloquial equivalents.
# Order matters: longer/more-specific patterns first.
_COLLOQUIAL_RULES = [
    # ---- «می‌خواهم/میخواهم» family → «میخوام» ----
    (re.compile(r'\bمی‌?خواهم\b'), 'میخوام'),
    (re.compile(r'\bنمی‌?خواهم\b'), 'نمیخوام'),
    (re.compile(r'\bمی‌?خواهی\b'), 'میخوای'),
    (re.compile(r'\bنمی‌?خواهی\b'), 'نمیخوای'),
    (re.compile(r'\bمی‌?خواهد\b'), 'میخواد'),
    (re.compile(r'\bنمی‌?خواهد\b'), 'نمیخواد'),
    (re.compile(r'\bمی‌?خواهیم\b'), 'میخوایم'),
    (re.compile(r'\bنمی‌?خواهیم\b'), 'نمیخوایم'),

    # ---- «بخواهم» family → «بخوام» ----
    (re.compile(r'\bبخواهم\b'), 'بخوام'),
    (re.compile(r'\bبخواهی\b'), 'بخوای'),
    (re.compile(r'\bبخواهد\b'), 'بخواد'),
    (re.compile(r'\bبخواهیم\b'), 'بخوایم'),
    (re.compile(r'\bبخواهید\b'), 'بخواید'),
    (re.compile(r'\bبخواهند\b'), 'بخوان'),

    # ---- «است/هست» → «ه/ـه» (not always desired, so only specific forms) ----
    (re.compile(r'\bهستم\b'), 'هستم'),  # keep as-is (ambiguous)

    # ---- Common formal→colloquial verb endings ----
    (re.compile(r'\bمی‌?دانم\b'), 'میدونم'),
    (re.compile(r'\bنمی‌?دانم\b'), 'نمیدونم'),
    (re.compile(r'\bمی‌?دانی\b'), 'میدونی'),
    (re.compile(r'\bنمی‌?دانی\b'), 'نمیدونی'),
    (re.compile(r'\bمی‌?داند\b'), 'میدونه'),
    (re.compile(r'\bنمی‌?داند\b'), 'نمیدونه'),
    (re.compile(r'\bمی‌?دانیم\b'), 'میدونیم'),
    (re.compile(r'\bنمی‌?دانیم\b'), 'نمیدونیم'),

    # ---- «می‌توانم» family → «میتونم» ----
    (re.compile(r'\bمی‌?توانم\b'), 'میتونم'),
    (re.compile(r'\bنمی‌?توانم\b'), 'نمیتونم'),
    (re.compile(r'\bمی‌?توانی\b'), 'میتونی'),
    (re.compile(r'\bنمی‌?توانی\b'), 'نمیتونی'),
    (re.compile(r'\bمی‌?تواند\b'), 'میتونه'),
    (re.compile(r'\bنمی‌?تواند\b'), 'نمیتونه'),
    (re.compile(r'\bمی‌?توانیم\b'), 'میتونیم'),
    (re.compile(r'\bنمی‌?توانیم\b'), 'نمیتونیم'),
    (re.compile(r'\bبتوانم\b'), 'بتونم'),
    (re.compile(r'\bبتوانی\b'), 'بتونی'),
    (re.compile(r'\bبتواند\b'), 'بتونه'),
    (re.compile(r'\bبتوانیم\b'), 'بتونیم'),

    # ---- «اصلاً» → «اصن» (very common colloquial) ----
    (re.compile(r'\bاصلاً?\b'), 'اصن'),

    # ---- «آن» → «اون»، «این‌طور» → «اینجوری» etc. ----
    (re.compile(r'\bآنها\b'), 'اونا'),
    (re.compile(r'\bآن\b'), 'اون'),
    (re.compile(r'\bاین‌?طور\b'), 'اینجوری'),
    (re.compile(r'\bآن‌?طور\b'), 'اونجوری'),
    (re.compile(r'\bهمین‌?طور\b'), 'همینجوری'),
    (re.compile(r'\bچه‌?طور\b'), 'چطور'),
    (re.compile(r'\bچگونه\b'), 'چجوری'),
]


def preserve_colloquial(text: str) -> str:
    """Convert formal Persian verb forms back to colloquial.

    Whisper's training data is biased toward formal written Persian, so it
    tends to produce «میخواهم» even when the speaker said «میخوام». This
    function reverses that formalization.
    """
    if not text:
        return text
    for pattern, replacement in _COLLOQUIAL_RULES:
        text = pattern.sub(replacement, text)
    return text


# ============================================================
# HALLUCINATION FILTER
# ============================================================

def is_hallucination(text: str) -> bool:
    """Detect hallucinated or garbage transcription output."""
    if not text:
        return True
    if len(text) < 2:
        return True

    # Pure punctuation
    if re.match(r'^[\.\,\;\:\!\?\…\،\؛\؟\!\s\u200c]+$', text):
        return True

    # Single character repeated
    stripped = text.replace(" ", "").replace("\u200c", "")
    if len(set(stripped)) <= 1:
        return True

    # Phrase-level repetition: "سلام سلام سلام سلام سلام". Persian doubles
    # words for emphasis («خیلی خیلی خوب», «یواش یواش»), so only long runs count.
    words = text.split()
    if len(words) >= 5:
        counts = Counter(words)
        most_common_count = counts.most_common(1)[0][1]
        # If one word appears in >60% of all words → hallucination
        if most_common_count / len(words) > 0.6:
            log.info(f"Filtered repeated-word hallucination: {text[:50]}")
            return True

    # Known hallucination phrases — only when the phrase is (nearly) the whole
    # utterance, counted in words. A real sentence that merely contains
    # «ترجمه» or "subscribe" is kept; «ترجمه کن» (two words, one of them the
    # phrase) is still dropped, which is the price of the filter.
    text_lower = text.lower().strip()
    for pattern in _HALLUCINATION_PATTERNS:
        if pattern in text_lower and len(words) <= len(pattern.split()) + 1:
            log.info(f"Filtered known hallucination phrase '{pattern}': {text[:50]}")
            return True

    return False


# ============================================================
# AUDIO RMS NORMALIZATION
# ============================================================

def normalize_audio_volume(audio, target_rms=0.1):
    """Normalize audio volume using RMS normalization.

    Ensures consistent input volume regardless of mic type or speaking volume.
    """
    rms = np.sqrt(np.mean(audio ** 2))
    if rms < 1e-6:  # silence
        return audio
    gain = target_rms / rms
    # Limit gain to prevent noise amplification (max ~30dB boost)
    gain = min(gain, 30.0)
    return np.clip(audio * gain, -1.0, 1.0).astype(np.float32)



# ============================================================
# TRANSCRIPTION HELPERS
# ============================================================

class CloudModel:
    """Stand-in 'model' for the online backend. Holds the provider + API key so
    the transcription path can route to cloud_engine instead of a local Whisper
    model. Lets the rest of the widget treat cloud and offline uniformly."""
    is_cloud = True

    def __init__(self, provider, api_key):
        self.provider = provider
        self.api_key = api_key


def _postprocess_text(txt: str, language: str) -> str:
    """Apply Persian normalization / corrections / colloquial preservation.

    Shared by the offline (per-segment) and cloud (whole-text) paths.
    FA: always. DUAL: only when the text contains Persian script.
    """
    if language == "fa":
        txt = normalize_persian(txt)
        txt = apply_word_corrections(txt)
        txt = preserve_colloquial(txt)
    elif language == "dual":
        if _has_persian_chars(txt):
            txt = normalize_persian(txt)
            txt = apply_word_corrections(txt)
            txt = preserve_colloquial(txt)
    return txt


def transcribe_cloud(cloud_model, audio_data, language, sample_rate=16000) -> str:
    """Transcribe via the online provider, then apply the same Persian
    post-processing the offline path uses, so output quality is consistent."""
    audio_data = normalize_audio_volume(audio_data)
    raw = cloud_engine.transcribe(
        audio_data, language,
        api_key=cloud_model.api_key,
        provider=cloud_model.provider,
        sample_rate=sample_rate,
    )
    if not raw or is_hallucination(raw):
        return ""
    text = _postprocess_text(raw, language)
    return re.sub(r"  +", " ", text).strip()


def transcribe_audio(model, audio_data, language, audio_duration=None, sample_rate=16000,
                     overrides=None, postprocess=True, rms=True):
    """Run transcription and return cleaned text.

    Language modes:
      "fa"   — Persian only. Model forced to fa, Persian prompt & normalization.
      "en"   — English only. Model forced to en, English prompt, no Persian normalization.
      "dual" — Bilingual FA+EN. Uses multilingual=True for per-segment language detection.

    If `model` is a CloudModel, transcription is delegated to the online provider.

    `overrides` (dict) replaces individual model.transcribe() keyword arguments,
    `postprocess=False` skips the Persian text post-processing and `rms=False`
    skips volume normalisation. These exist for the evaluation harness, which
    measures the effect of every tuning knob separately (eval/accuracy.py
    --ablate); the widget never passes them.
    """

    # Online backend: delegate to the cloud provider.
    if isinstance(model, CloudModel):
        return transcribe_cloud(model, audio_data, language, sample_rate=sample_rate)

    # RMS-normalize audio volume for consistent input regardless of mic/volume
    if rms:
        audio_data = normalize_audio_volume(audio_data)

    # Domain-vocabulary prompts — include brand names, colloquial words, and loanwords
    # so Whisper biases toward correct spellings.
    # IMPORTANT: Do NOT use full sentences — Whisper may hallucinate them as output!
    initial_prompt = None
    whisper_language = language  # what we pass to model.transcribe(language=...)
    multilingual_flag = False
    temperature_val = 0.0  # single-pass beam search (fastest)

    if language == "fa":
        # Rich vocabulary prompt: colloquial forms, tech terms, brand names, punctuation.
        # Whisper uses this to bias its decoder toward correct spellings.
        # Keep as comma-separated words/phrases — NOT full sentences (avoids hallucination).
        # faster-whisper keeps only the LAST 223 prompt tokens; the previous
        # 298-token prompt silently lost its first 75 tokens, which were the
        # colloquial cue words it exists for. This one measures 214 tokens
        # (tokenizer.encode(" " + prompt.strip())): do not add words without
        # re-measuring.
        initial_prompt = (
            "خب، ببین، میخوام، نمیدونم، چجوری، بخوایم، اصن، دیگه، همینه، "
            "میشه، نمیشه، بگم، میگم، میکنیم، بریم، کردیم، "
            "گفتار به متن، تنظیمات، پایتون، مدل، ویسپر، دیتابیس، سرور، گیتهاب، "
            "اسنپ، دیجیکالا، تلگرام، واتساپ، جاباما، اقامتگاه، رزرو، هزینه، "
            "تقویم، پنجشنبه، اسفند، فروردین، فایل، پوشه، گزارش، دانشگاه."
        )
        whisper_language = "fa"
    elif language == "en":
        initial_prompt = (
            "Okay, so, let me, I want to, basically, "
            "Whisper, Python, framework, faster-whisper, database, server, GitHub, "
            "Snapp, Digikala, Jabama, accommodation, booking, reserve, available, "
            "full text search, event, feature, calendar, parameters, performance."
        )
        whisper_language = "en"
    elif language == "dual":
        # CRITICAL: multilingual=True enables per-segment language detection.
        # Without it, language=None detects once for the entire audio and
        # transcribes everything in that single language — breaking code-switching.
        initial_prompt = (
            "خب، ببین، میخوام، نمیدونم، عملکرد، پارامترهای، فریمورک، "
            "اسنپ، دیجیکالا، جاباما، اقامتگاه، رزرو، برگزار، "
            "Whisper, Python, framework, database, server, GitHub, "
            "booking, available, full text search, event, feature."
        )
        whisper_language = None  # auto-detect per segment
        multilingual_flag = True
        # Wider temperature fallback for mixed-language audio
        temperature_val = [0.0, 0.2, 0.4, 0.6]

    # For short recordings (<5s), disable condition_on_previous_text to prevent
    # hallucination loops — there's no meaningful "previous text" context.
    use_condition_on_prev = True
    if audio_duration is not None and audio_duration < 5.0:
        use_condition_on_prev = False

    decode_kwargs = dict(
        language=whisper_language,
        beam_size=5,
        best_of=5,
        vad_filter=True,
        vad_parameters=dict(
            threshold=0.3,                 # lower = more sensitive to quiet speech
            min_silence_duration_ms=250,   # shorter = better pause segmentation
            speech_pad_ms=500,             # wider padding keeps word edges intact
            min_speech_duration_ms=80,     # don't discard very short utterances
        ),
        initial_prompt=initial_prompt,
        # 1.0 = off. The 1.2 used until September 2026 made the decoder end
        # sentences early rather than repeat "the"/"of": measured on FLEURS it
        # cost `small` 9.6 points of English WER and even the shipped model
        # 1.8 points of Persian (docs/REPORT.md, Section 6.3). Loop protection
        # is the hallucination filter below and condition_on_previous_text=False
        # for short recordings.
        repetition_penalty=1.0,
        no_repeat_ngram_size=0,
        no_speech_threshold=0.5,           # a segment is dropped when no_speech_prob > this (0.6 default)
        condition_on_previous_text=use_condition_on_prev,
        temperature=temperature_val,
        multilingual=multilingual_flag,
    )
    if overrides:
        decode_kwargs.update(overrides)
    segments, info = model.transcribe(audio_data, **decode_kwargs)

    text_parts = []
    for segment in segments:
        txt = segment.text.strip()
        if is_hallucination(txt):
            log.debug(f"Filtered hallucination: {txt[:50]}")
            continue
        # Normalize Persian text (Arabic→Persian chars, diacritics, spacing).
        if postprocess:
            txt = _postprocess_text(txt, language)
        text_parts.append(txt)

    result = " ".join(text_parts).strip()

    # Final cleanup: collapse multiple spaces
    result = re.sub(r'  +', ' ', result)

    return result


def _has_persian_chars(text: str) -> bool:
    """Check if text contains Persian/Arabic script characters."""
    for ch in text:
        if '\u0600' <= ch <= '\u06FF' or '\uFB50' <= ch <= '\uFDFF' or '\uFE70' <= ch <= '\uFEFF':
            return True
    return False
