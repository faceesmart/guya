"""Deterministic Persian/English intent and slot parser.

The parser is intentionally small and inspectable. Phrase packs provide sample
coverage while rules extract variable values such as file and folder names.
"""

import json
import os
import re
from difflib import SequenceMatcher
from typing import Dict, Iterable, Optional

from .models import ParsedCommand
from .normalizer import clean_slot, detect_language, normalize


_DATA_DIR = os.path.dirname(os.path.abspath(__file__))


def _load_phrases(language: str) -> Dict[str, list]:
    path = os.path.join(_DATA_DIR, "commands_fa.json" if language == "fa" else "commands_en.json")
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


class CommandParser:
    """Parse the limited command set used by the MVP."""

    APP_ALIASES = {
        "word": (
            "word", "microsoft word", "ورد", "مایکروسافت ورد",
        ),
        "text_editor": (
            "textedit", "text edit", "notepad", "text editor",
            "تکست ادیت", "تکست ادیتور", "نوت پد", "ویرایشگر متن",
        ),
        "calculator": ("calculator", "calc", "ماشین حساب"),
        "file_manager": (
            "finder", "file explorer", "explorer", "فایندر",
            "فایل اکسپلورر", "مدیریت فایل",
        ),
        "chrome": ("chrome", "google chrome", "کروم", "گوگل کروم"),
        "safari": ("safari", "سافاری"),
        "browser": (
            "browser", "web browser", "مرورگر",
        ),
        "pages": ("pages", "پیجز"),
    }

    CREATE_WORD_WORDS = ("word", "word document", "word file", "ورد", "سند ورد", "فایل ورد")
    FOLDER_WORDS = ("folder", "directory", "پوشه", "فولدر")
    TEXT_FILE_WORDS = ("text file", "txt file", "فایل متنی", "تکست فایل")
    FILE_WORDS = ("file", "document", "فایل", "سند")

    # "new" and "build" are deliberately NOT create verbs: "open the new
    # folder" / "open the build folder" are open requests, and creation must
    # never happen because of an adjective or a folder name.
    CREATE_VERBS = (
        "create", "make",
        "بساز", "بسازی", "درست کن", "درست کنی", "ایجاد کن", "ایجاد کنی",
    )
    # Deletion is outside V1 on purpose. It is recognised only so that the
    # assistant can say so clearly instead of "I did not understand".
    DELETE_VERBS = (
        "delete", "remove", "erase", "trash",
        "پاک کن", "پاکش کن", "حذف کن", "حذفش کن", "بریز دور",
    )
    # Words that carry no meaning for a command. They are stripped from the
    # edges of an utterance before the strict grammars run, so that
    # "let's scroll down", "again, scroll down" or «یه کم برو پایین» resolve.
    FILLERS = {
        "en": (
            "please", "just", "now", "again", "okay", "ok", "so", "well", "hey",
            "guya", "can you", "could you", "would you", "will you", "let's",
            "let s", "lets", "i want to", "i want you to", "i d like to",
            "i would like to", "i", "a bit", "a little", "a little bit",
            "for me", "thanks", "thank you", "the page", "of the page",
        ),
        "fa": (
            "لطفا", "لطفاً", "یه کم", "یکم", "کمی", "یه ذره", "یه خورده", "دوباره",
            "باز", "الان", "حالا", "میشه", "می شه", "می‌شه", "برام", "برای من",
            "گویا", "بی زحمت", "لطف کن", "ممنون", "مرسی", "خب", "دیگه", "تر",
        ),
    }
    OPEN_VERBS = (
        "open", "reopen", "launch", "start",
        "باز کن", "بازش کن", "دوباره باز کن", "دوباره بازش کن", "اجرا کن",
    )
    CLOSE_VERBS = (
        "close", "close it", "close this", "ببند", "ببندش",
        "بسته شود", "بسته شه",
    )
    SAVE_VERBS = (
        "save", "save it", "ذخیره کن", "ذخیره اش کن", "ذخیره ش کن",
        "سیو کن", "سیوش کن",
    )
    SEARCH_VERBS = (
        "search", "find", "look for", "where is", "where s", "where are",
        "جستجو", "سرچ", "پیدا کن", "بگرد", "کجاست", "کجا هست", "کجاس",
    )
    RENAME_VERBS = (
        "rename", "change its name", "change the name",
        "اسمش رو عوض", "اسمش را عوض", "اسمش رو تغییر", "اسمش را تغییر",
        "اسمش رو بکن", "اسمش را بکن", "اسمش رو کن", "اسمش را کن",
        "اسم فایل رو", "اسم فایل را", "نامش رو", "نامش را",
        "تغییر نامش", "تغییر نام فایل", "تغییر نام پوشه",
    )

    WEBSITE_NAMES = {
        "google", "youtube", "you tube", "wikipedia", "wiki pedia",
        "github", "git hub", "gmail", "openai", "open ai", "chatgpt", "chat gpt",
        "university of tehran", "tehran university",
        "instagram", "twitter", "facebook", "linkedin", "telegram", "whatsapp",
        "aparat", "digikala", "divar", "stackoverflow", "stack overflow",
        "گوگل", "یوتیوب", "ویکی پدیا", "ویکیپدیا", "گیت هاب", "گیتهاب",
        "جی میل", "جیمیل", "دانشگاه تهران", "چت جی پی تی",
        "اینستاگرام", "اینستا", "توییتر", "فیسبوک", "فیس بوک", "لینکدین",
        "تلگرام", "واتساپ", "واتس اپ", "آپارات", "اپارات", "دیجی کالا",
        "دیجیکالا", "دیوار", "استک اورفلو",
    }

    def __init__(self):
        self.phrases = {"fa": _load_phrases("fa"), "en": _load_phrases("en")}
        self._confirm = {
            lang: {normalize(item) for item in values["confirm"]}
            for lang, values in self.phrases.items()
        }
        self._cancel = {
            lang: {normalize(item) for item in values["cancel"]}
            for lang, values in self.phrases.items()
        }

    def is_confirmation(self, text: str) -> bool:
        lang = detect_language(text)
        value = normalize(text)
        return value in self._confirm[lang] or self._strip_fillers(value, lang) in self._confirm[lang]

    def is_cancellation(self, text: str) -> bool:
        lang = detect_language(text)
        value = normalize(text)
        return value in self._cancel[lang] or self._strip_fillers(value, lang) in self._cancel[lang]

    @classmethod
    def _strip_fillers(cls, value: str, language: str) -> str:
        """Remove filler words from the edges of a normalised utterance.

        Only the edges are touched, and only whole words, so a filename in the
        middle of a command is never altered.
        """
        fillers = [normalize(f) for f in cls.FILLERS.get(language, ())]
        fillers.sort(key=len, reverse=True)
        changed = True
        while changed and value:
            changed = False
            for filler in fillers:
                if value == filler:
                    return ""
                if value.startswith(filler + " "):
                    value = value[len(filler) + 1:]
                    changed = True
                if value.endswith(" " + filler):
                    value = value[: -len(filler) - 1]
                    changed = True
        return value.strip()

    @staticmethod
    def selection_index(text: str) -> Optional[int]:
        """Return a zero-based spoken choice index for the top three results."""
        value = normalize(text)
        selection_words = {
            0: (
                "first", "first one", "one", "1", "number one", "option one",
                "open first", "open the first", "open the first one",
                "اول", "اولی", "یک", "1", "شماره یک", "گزینه یک",
                "اول رو باز کن", "اولی رو باز کن", "اول را باز کن",
            ),
            1: (
                "second", "second one", "two", "2", "number two", "option two",
                "open second", "open the second", "open the second one",
                "دوم", "دومی", "دو", "2", "شماره دو", "گزینه دو",
                "دوم رو باز کن", "دومی رو باز کن", "دوم را باز کن",
            ),
            2: (
                "third", "third one", "three", "3", "number three", "option three",
                "open third", "open the third", "open the third one",
                "سوم", "سومی", "سه", "3", "شماره سه", "گزینه سه",
                "سوم رو باز کن", "سومی رو باز کن", "سوم را باز کن",
            ),
        }
        for index, choices in selection_words.items():
            if value in {normalize(choice) for choice in choices}:
                return index
        return None

    def parse(self, text: str) -> ParsedCommand:
        language = detect_language(text)
        value = normalize(text)
        if not value:
            return ParsedCommand("unknown", language=language, original_text=text)

        stripped = self._strip_fillers(value, language)
        if value in self._confirm[language] or stripped in self._confirm[language]:
            return ParsedCommand("confirm", language=language, original_text=text)
        if value in self._cancel[language] or stripped in self._cancel[language]:
            return ParsedCommand("cancel", language=language, original_text=text)

        parts = self._sequence_parts(value, language)
        if len(parts) > 1:
            if len(parts) > 3:
                return ParsedCommand("unknown", language=language, original_text=text)
            steps = [
                self._parse_single(part, language, original_text=part, raw_text=text)
                for part in parts
            ]
            if all(step.intent != "unknown" for step in steps):
                for index, step in enumerate(steps):
                    if (
                        step.intent == "search"
                        and index > 0
                        and steps[index - 1].intent == "open_app"
                        and steps[index - 1].slots.get("app")
                        in ("browser", "chrome", "safari")
                    ):
                        step.intent = "web_search"
                        step.slots["app"] = steps[index - 1].slots["app"]
                    if (
                        step.intent == "open_website"
                        and index > 0
                        and steps[index - 1].intent == "open_app"
                        and steps[index - 1].slots.get("app")
                        in ("browser", "chrome", "safari")
                    ):
                        step.slots["app"] = steps[index - 1].slots["app"]
                return ParsedCommand(
                    "sequence",
                    language=language,
                    original_text=text,
                    steps=steps,
                )

        return self._parse_single(value, language, original_text=text)

    def _parse_single(
        self,
        value: str,
        language: str,
        original_text: str,
        raw_text: str = "",
    ) -> ParsedCommand:
        base = {"language": language, "original_text": original_text}
        raw_text = raw_text or original_text
        stripped = self._strip_fillers(value, language)
        core = stripped or value
        wants_creation = self._wants_creation(core, language)

        # Deleting is not supported in V1. Say so explicitly rather than
        # letting the fuzzy fallback turn "delete the report" into a search.
        # Only when the delete word is the command verb: "open the trash
        # folder" and "rename it to remove" are ordinary commands.
        delete_at = self._first_match_pos(core, self.DELETE_VERBS)
        if delete_at is not None:
            other_verbs = (self.OPEN_VERBS + self.RENAME_VERBS + self.SEARCH_VERBS
                           + self.CREATE_VERBS + self.SAVE_VERBS + self.CLOSE_VERBS)
            other_at = self._first_match_pos(core, other_verbs)
            if other_at is None or delete_at < other_at:
                return ParsedCommand("delete_unsupported", **base)

        # A bare application name ("calculator", «ماشین حساب») is an open request.
        bare_app = self._exact_app_name(stripped)
        if bare_app:
            return ParsedCommand("open_app", slots={"app": bare_app}, **base)

        # "switch to Persian" / «برو انگلیسی»: changes the recognition language.
        target_language = self._language_switch(core, language)
        if target_language:
            return ParsedCommand("set_language", slots={"language": target_language}, **base)

        # Creation phrases may contain "name it", so detect them before rename.
        if self._has_any(value, self.CREATE_WORD_WORDS) and wants_creation:
            name = self._create_name(value, language)
            return ParsedCommand(
                "create_word_document", slots=self._slot("name", name), **base
            )
        if self._has_any(value, self.FOLDER_WORDS) and wants_creation:
            name = self._create_name(value, language)
            return ParsedCommand("create_folder", slots=self._slot("name", name), **base)
        if self._has_any(value, self.TEXT_FILE_WORDS) and wants_creation:
            name = self._create_name(value, language)
            return ParsedCommand("create_text_file", slots=self._slot("name", name), **base)
        if self._has_any(value, self.FILE_WORDS) and wants_creation:
            name = self._create_name(value, language)
            return ParsedCommand("create_text_file", slots=self._slot("name", name), **base)
        if self._looks_like_rename(core, language):
            return ParsedCommand("rename", slots=self._rename_slots(core, language), **base)
        if self._has_any(value, self.SAVE_VERBS):
            if self._looks_like_save_as(value, language):
                return ParsedCommand("save_as_unsupported", **base)
            return ParsedCommand("save_current", **base)
        if self._has_any(value, self.CLOSE_VERBS):
            return ParsedCommand("close_current", **base)

        browser_action = self._browser_navigation_action(stripped or value, language)
        if browser_action:
            return ParsedCommand(
                "browser_navigation",
                slots={"action": browser_action},
                **base,
            )

        website = self._website_target(stripped or value, language, raw_text)
        if website:
            slots = {"target": website}
            app = self._app_name(value)
            if app in ("browser", "chrome", "safari"):
                slots["app"] = app
            return ParsedCommand("open_website", slots=slots, **base)

        # Prefer opening a named application when both "find" and "open" occur,
        # e.g. a slightly noisy transcript: "find and open calculate for me".
        # Exception: "open the word file report" names a FILE, not the Word app.
        app = self._app_name(value)
        if app and self._has_any(value, self.OPEN_VERBS):
            names_a_file = False
            if app in ("word", "pages") and self._has_any(value, self.FILE_WORDS + self.FOLDER_WORDS):
                # "open the word file report" names a file; "open word file"
                # names nothing and still means the application.
                kind = "folder" if self._has_any(value, self.FOLDER_WORDS) else "file"
                remainder = self._open_query(value, language, kind=kind)
                names_a_file = bool(remainder) and not self._exact_app_name(remainder)
            if not names_a_file:
                return ParsedCommand("open_app", slots={"app": app}, **base)

        combined_query = self._find_and_open_query(value, language)
        if combined_query:
            intent = (
                "open_folder"
                if self._has_any(value, self.FOLDER_WORDS)
                else "open_file"
            )
            return ParsedCommand(
                intent,
                slots={"query": combined_query},
                **base,
            )

        if self._has_any(value, self.SEARCH_VERBS):
            web = self._web_search_query(value, language)
            if web:
                query, app = web
                return ParsedCommand("web_search", slots={"query": query, "app": app}, **base)
            query = self._search_query(value, language)
            return ParsedCommand("search", slots=self._slot("query", query), **base)

        if self._has_any(value, self.OPEN_VERBS):
            if self._has_any(value, self.FOLDER_WORDS):
                query = self._open_query(value, language, kind="folder")
                return ParsedCommand("open_folder", slots=self._slot("query", query), **base)
            query = self._open_query(value, language, kind="file")
            return ParsedCommand("open_file", slots=self._slot("query", query), **base)

        # The phrase packs also catch short natural variants that omit a verb.
        # When they do, still extract the slot the intent needs.
        corpus_intent = self._closest_corpus_intent(stripped or value, language)
        if corpus_intent:
            if corpus_intent == "open_app":
                app = self._app_name(value)
                if not app:
                    return ParsedCommand("unknown", **base)
                return ParsedCommand("open_app", slots={"app": app}, **base)
            if corpus_intent == "browser_navigation":
                action = self._navigation_keywords(stripped or value, language)
                if not action:
                    return ParsedCommand("unknown", **base)
                return ParsedCommand("browser_navigation", slots={"action": action}, **base)
            if corpus_intent in ("create_word_document", "create_folder", "create_text_file"):
                return ParsedCommand(
                    corpus_intent, slots=self._slot("name", self._create_name(value, language)), **base
                )
            if corpus_intent == "search":
                return ParsedCommand(
                    corpus_intent, slots=self._slot("query", self._search_query(value, language)), **base
                )
            if corpus_intent in ("open_file", "open_folder"):
                kind = "folder" if corpus_intent == "open_folder" else "file"
                return ParsedCommand(
                    corpus_intent, slots=self._slot("query", self._open_query(value, language, kind=kind)), **base
                )
            if corpus_intent == "rename":
                return ParsedCommand(corpus_intent, slots=self._rename_slots(core, language), **base)
            if corpus_intent == "open_website":
                # "visit github com" (the dot was not heard): accept a known name
                # or a bare well-known TLD here, since the phrase list matched.
                target = self._loose_website_target(core, language)
                if not target:
                    return ParsedCommand("unknown", **base)
                return ParsedCommand(corpus_intent, slots={"target": target}, **base)
            if corpus_intent == "sequence":
                return ParsedCommand("unknown", **base)
            return ParsedCommand(corpus_intent, **base)
        return ParsedCommand("unknown", **base)

    def _loose_website_target(self, value: str, language: str) -> Optional[str]:
        if language == "fa":
            match = re.fullmatch(r"(?:برو(?: به)?\s+)?(?:سایت\s+)?(.+?)(?: رو| را)?(?:\s+باز کن)?", value)
        else:
            match = re.fullmatch(r"(?:go to|visit|open)\s+(?:the\s+)?(?:website\s+|site\s+)?(.+)", value)
        if not match:
            return None
        candidate = self._clean_website_target(match.group(1))
        if candidate in self.WEBSITE_NAMES:
            return candidate
        tokens = candidate.split()
        if len(tokens) >= 2 and all(re.fullmatch(r"[a-z0-9-]+", t) for t in tokens) \
                and tokens[-1] in {"com", "org", "net", "edu", "gov", "ir"}:
            return candidate
        return None

    def leading_answer(self, text: str) -> Optional[str]:
        """'confirm' or 'cancel' when the utterance STARTS with a yes/no word
        ("yes, rename it", «نه اسمش رو عوض نکن»), else None. Used while a
        question is pending so a natural answer is never re-parsed as a new
        command."""
        language = detect_language(text)
        value = self._strip_fillers(normalize(text), language)
        if not value:
            return None
        for kind, phrases in (("cancel", self._cancel[language]), ("confirm", self._confirm[language])):
            for phrase in sorted(phrases, key=len, reverse=True):
                if value == phrase or value.startswith(phrase + " "):
                    return kind
        return None

    def fuzzy_answer(self, text: str) -> Optional[str]:
        """For a ONE-word utterance while a question is pending: 'confirm' or
        'cancel' if it is close to a yes/no word (Whisper writes «بیلی» for
        «بله»). Multi-word utterances are never guessed."""
        language = detect_language(text)
        value = self._strip_fillers(normalize(text), language)
        if not value or " " in value or len(value) < 2:
            return None
        best, best_kind = 0.0, None
        for kind, phrases in (("confirm", self._confirm[language]), ("cancel", self._cancel[language])):
            for phrase in phrases:
                if " " in phrase:
                    continue
                score = SequenceMatcher(None, value, phrase).ratio()
                if score > best:
                    best, best_kind = score, kind
        return best_kind if best >= 0.75 else None

    @staticmethod
    def _first_match_pos(value: str, candidates: Iterable[str]) -> Optional[int]:
        best = None
        for candidate in candidates:
            match = re.search(r"(?<!\w)" + re.escape(normalize(candidate)) + r"(?!\w)", value)
            if match and (best is None or match.start() < best):
                best = match.start()
        return best

    @staticmethod
    def _sequence_parts(value: str, language: str) -> list:
        """Split only explicit, safe command connectors (maximum three steps)."""
        if language == "fa":
            pattern = (
                r"\s+(?:و\s+بعد(?:ش)?|بعد(?:ش)?|سپس)\s+"
                r"|\s+و\s+(?=(?:ذخیره|سیو|ببند|جستجو|سرچ|پنجره|برو|سایت)\b)"
            )
        else:
            pattern = (
                r"\s+(?:and\s+then|then)\s+"
                r"|\s+and\s+(?=(?:save|close|search|go|visit)\b)"
            )
        return [part.strip() for part in re.split(pattern, value) if part.strip()]

    def _wants_creation(self, value: str, language: str) -> bool:
        """A create verb, or an English phrasing that clearly asks for a new
        item ("I need a word file", "new word document named ...")."""
        if self._has_any(value, self.CREATE_VERBS):
            return True
        if language == "en":
            return bool(
                re.search(
                    r"^new\b|\b(?:need|want|give me|get me)\s+(?:a|an|another|new)\b",
                    value,
                )
            )
        return False

    @staticmethod
    def _has_any(value: str, candidates: Iterable[str]) -> bool:
        return any(
            re.search(
                r"(?<!\w)" + re.escape(normalize(candidate)) + r"(?!\w)",
                value,
            )
            for candidate in candidates
        )

    @staticmethod
    def _slot(key: str, value: Optional[str]) -> Dict[str, str]:
        return {key: value} if value else {}

    def _app_name(self, value: str) -> Optional[str]:
        # Whisper sometimes outputs the verb "calculate" for "calculator".
        if re.search(r"(?<!\w)calculat(?:e|or)(?!\w)", value):
            return "calculator"
        for canonical, aliases in self.APP_ALIASES.items():
            if self._has_any(value, aliases):
                return canonical
        return None

    LANGUAGE_NAMES = {
        "fa": ("persian", "farsi", "فارسی", "پارسی"),
        "en": ("english", "انگلیسی", "اینگلیسی"),
        "dual": ("dual", "both", "bilingual", "both languages", "دو زبانه", "دوزبانه",
                 "هر دو", "هر دو زبان", "دو زبان"),
    }

    @classmethod
    def _language_switch(cls, value: str, language: str) -> Optional[str]:
        """'switch to persian', 'persian mode', «برو فارسی», «زبان رو انگلیسی کن»."""
        if not value or len(value.split()) > 6:
            return None
        if language == "fa":
            frame = re.fullmatch(
                r"(?:(?:زبان|زبون)(?: رو| را)?\s+)?(?:برو\s+|بشه\s+|بشو\s+|کن\s+)?(.+?)"
                r"(?:\s+(?:کن|بشه|بشو|شو|باشه))?(?:\s+زبان)?",
                value,
            )
        else:
            frame = re.fullmatch(
                r"(?:(?:switch|change|go|set|turn)\s+(?:the\s+)?(?:language\s+)?(?:to\s+)?"
                r"|(?:speak|use|language)\s+)?(.+?)(?:\s+(?:mode|language|please))?",
                value,
            )
        if not frame:
            return None
        name = frame.group(1).strip()
        for code, names in cls.LANGUAGE_NAMES.items():
            if name in {normalize(n) for n in names}:
                # A bare language name alone ("english") is too easily a
                # dictated word; require a verb or the word mode/language/زبان.
                bare = value == name
                if bare and code != "dual":
                    return None
                return code
        return None

    def _exact_app_name(self, value: str) -> Optional[str]:
        """The whole utterance is an application name and nothing else."""
        if not value:
            return None
        for canonical, aliases in self.APP_ALIASES.items():
            if value in {normalize(alias) for alias in aliases}:
                return canonical
        return None

    @staticmethod
    def _navigation_keywords(value: str, language: str) -> Optional[str]:
        """Loose browser-movement detection used after the strict grammar fails.

        The utterance must be short, contain a movement word and a direction,
        and contain nothing that names a file, folder or application, so a
        command such as "open the next file" is never treated as navigation.
        """
        tokens = value.split()
        if not tokens or len(tokens) > 7:
            return None
        # Nothing that names an application is a page movement («ورد رو بیار بالا»).
        for aliases in CommandParser.APP_ALIASES.values():
            if any(re.search(r"(?<!\w)" + re.escape(normalize(a)) + r"(?!\w)", value) for a in aliases):
                return None
        if language == "fa":
            blockers = ("فایل", "پوشه", "فولدر", "سند", "برنامه", "باز کن", "بساز", "پیدا", "سایت",
                        "صدا", "کامپیوتر", "سیستم", "پنجره", "تب")
            # A bare direction is a movement by itself; otherwise a movement
            # word must accompany the direction, so «خاموش کن پایین» is nothing.
            bare = {"پایین": "scroll_down", "بالا": "scroll_up", "عقب": "back", "جلو": "forward",
                    "برگرد": "back", "اسکرول دان": "scroll_down", "اسکرول آپ": "scroll_up"}
            if value in bare:
                return bare[value]
            movers = ("برو", "بیا", "بیار", "ببر", "بکش", "اسکرول", "صفحه", "برگرد")
            if any(re.search(r"(?<!\w)" + re.escape(b) + r"(?!\w)", value) for b in blockers):
                return None
            if not any(re.search(r"(?<!\w)" + re.escape(m) + r"(?!\w)", value) for m in movers):
                return None
            has_page = bool(re.search(r"(?<!\w)صفحه(?!\w)", value))
            if re.search(r"(?<!\w)(?:اول|ابتدا|ابتدای|بالای)(?!\w)", value) and has_page:
                return "top"
            if re.search(r"(?<!\w)(?:آخر|اخر|ته|انتها|انتهای|پایین)(?!\w)", value) and has_page \
                    and re.search(r"(?<!\w)برو(?!\w)", value) \
                    and not re.search(r"(?<!\w)(?:ببر|بیار|بکش)(?!\w)", value):
                return "bottom"
            if re.search(r"(?<!\w)(?:عقب|برگرد|قبل|قبلی)(?!\w)", value):
                return "back"
            if re.search(r"(?<!\w)(?:جلو|بعد|بعدی)(?!\w)", value):
                return "forward"
            if re.search(r"(?<!\w)(?:پایین|دان)(?!\w)", value):
                return "scroll_down"
            if re.search(r"(?<!\w)(?:بالا|آپ)(?!\w)", value):
                return "scroll_up"
            return None
        blockers = ("file", "folder", "directory", "document", "app", "application",
                    "open", "create", "make", "find", "search", "website", "site", "rename",
                    "launch", "start", "close", "save", "tab", "window", "computer", "volume",
                    "sound", "shut", "turn", "set", "look", "pull", "pick", "what")
        # A bare direction is a movement by itself ("down", "next page");
        # otherwise a movement word must accompany the direction, so "shut
        # down the computer" and "back up my thesis" are not page movements.
        bare = {"down": "scroll_down", "up": "scroll_up", "back": "back", "forward": "forward",
                "top": "top", "bottom": "bottom", "next page": "forward", "previous page": "back",
                "page down": "scroll_down", "page up": "scroll_up"}
        if value in bare:
            return bare[value]
        movers = ("scroll", "page", "go", "went", "move", "jump", "bring")
        if any(re.search(r"(?<!\w)" + re.escape(b) + r"(?!\w)", value) for b in blockers):
            return None
        if not any(re.search(r"(?<!\w)" + re.escape(m) + r"(?!\w)", value) for m in movers):
            return None
        # "the end"/"the beginning" only count as page positions at the end of
        # the utterance ("jump to the end"), never as a verb ("end it").
        if re.search(r"(?<!\w)top(?!\w)", value) or re.search(r"(?<!\w)(?:the )?(?:beginning|start)$", value):
            return "top"
        if re.search(r"(?<!\w)bottom(?!\w)", value) or re.search(r"(?<!\w)(?:the )?end$", value):
            return "bottom"
        if re.search(r"(?<!\w)(?:back|previous)(?!\w)", value):
            return "back"
        if re.search(r"(?<!\w)(?:forward|next)(?!\w)", value):
            return "forward"
        if re.search(r"(?<!\w)down(?:wards)?(?!\w)", value):
            return "scroll_down"
        if re.search(r"(?<!\w)up(?:wards)?(?!\w)", value):
            return "scroll_up"
        return None

    @staticmethod
    def _browser_navigation_action(value: str, language: str) -> Optional[str]:
        """Return a whitelisted browser movement without reading page content."""
        if language == "fa":
            patterns = (
                ("scroll_down", (
                    r"^(?:لطفا )?(?:صفحه(?: رو| را)?|اسکرول)?\s*پایین(?: ببر| برو)?$",
                    r"^(?:لطفا )?برو پایین صفحه$",
                    r"^(?:لطفا )?صفحه(?: رو| را)? (?:ببر|بکش) پایین$",
                    r"^(?:لطفا )?اسکرول(?: کن)? (?:به )?پایین$",
                    r"^(?:لطفا )?(?:یکم )?برو پایین$",
                    r"^(?:لطفا )?اسکرول دان$",
                )),
                ("scroll_up", (
                    r"^(?:لطفا )?(?:صفحه(?: رو| را)?|اسکرول)?\s*بالا(?: ببر| برو)?$",
                    r"^(?:لطفا )?برو بالا صفحه$",
                    r"^(?:لطفا )?صفحه(?: رو| را)? (?:ببر|بکش) بالا$",
                    r"^(?:لطفا )?اسکرول(?: کن)? (?:به )?بالا$",
                    r"^(?:لطفا )?(?:یکم )?برو بالا$",
                    r"^(?:لطفا )?اسکرول آپ$",
                )),
                ("top", (
                    r"^(?:لطفا )?برو (?:به )?(?:اول|ابتدا|بالای) صفحه$",
                    r"^(?:لطفا )?(?:اول|ابتدای|بالای) صفحه(?: رو| را)? باز کن$",
                )),
                ("bottom", (
                    r"^(?:لطفا )?برو (?:به )?(?:آخر|انتهای|پایین) صفحه$",
                    r"^(?:لطفا )?(?:آخر|انتهای) صفحه$",
                )),
                ("back", (
                    r"^(?:لطفا )?(?:برو )?عقب$",
                    r"^(?:لطفا )?برگرد$",
                    r"^(?:لطفا )?برو (?:به )?صفحه (?:قبل|قبلی)$",
                )),
                ("forward", (
                    r"^(?:لطفا )?(?:برو )?جلو$",
                    r"^(?:لطفا )?برو (?:به )?صفحه (?:بعد|بعدی)$",
                )),
            )
        else:
            patterns = (
                ("scroll_down", (
                    r"^(?:please )?scroll down(?: the page)?$",
                    r"^(?:please )?go down(?: the)? page$",
                    r"^(?:please )?scroll(?:ing)?(?: the page)?(?: a little)? down(?:wards)?$",
                    r"^(?:please )?scroll(?: a little)? down(?:wards)?(?: the page)?$",
                    r"^(?:please )?(?:go|move)(?: a little)? down(?: the page)?$",
                    r"^(?:please )?page down$",
                )),
                ("scroll_up", (
                    r"^(?:please )?scroll up(?: the page)?$",
                    r"^(?:please )?go up(?: the)? page$",
                    r"^(?:please )?scroll(?:ing)?(?: the page)?(?: a little)? up(?:wards)?$",
                    r"^(?:please )?scroll(?: a little)? up(?:wards)?(?: the page)?$",
                    r"^(?:please )?(?:go|move)(?: a little)? up(?: the page)?$",
                    r"^(?:please )?page up$",
                )),
                ("top", (
                    r"^(?:please )?go to (?:the )?(?:top|start|beginning)(?: of the page)?$",
                    r"^(?:please )?(?:page )?top$",
                )),
                ("bottom", (
                    r"^(?:please )?go to (?:the )?(?:bottom|end)(?: of the page)?$",
                    r"^(?:please )?(?:page )?bottom$",
                )),
                ("back", (
                    r"^(?:please )?(?:go )?back$",
                    r"^(?:please )?go (?:back )?to (?:the )?previous page$",
                )),
                ("forward", (
                    r"^(?:please )?(?:go )?forward$",
                    r"^(?:please )?go (?:forward )?to (?:the )?next page$",
                )),
            )
        for action, candidates in patterns:
            if any(re.fullmatch(pattern, value) for pattern in candidates):
                return action
        return CommandParser._navigation_keywords(value, language)

    def _website_target(self, value: str, language: str, original_text: str = "") -> Optional[str]:
        """Extract only explicit website requests or known website names."""
        if language == "fa":
            explicit_patterns = (
                r"^(?:لطفا )?برو(?: به)?\s+(?:سایت|وب سایت)\s+(.+)$",
                r"^(?:لطفا )?(?:سایت|وب سایت)\s+(.+?)(?: رو| را)?\s+باز کن$",
            )
            known_patterns = (
                r"^(?:لطفا )?برو(?: به)?\s+(.+)$",
                r"^(?:لطفا )?(.+?)(?: رو| را)?\s+باز کن$",
            )
        else:
            explicit_patterns = (
                r"^(?:please )?(?:go to|visit)\s+(?:the\s+)?(?:website|site)\s+(.+)$",
                r"^(?:please )?(?:go to|visit)\s+(?:the\s+)?(.+?)\s+(?:website|site)$",
                r"^(?:please )?open\s+(?:the\s+)?(?:website|site)\s+(.+)$",
                r"^(?:please )?open\s+(.+?)\s+(?:website|site)$",
            )
            known_patterns = (
                r"^(?:please )?(?:go to|visit)\s+(.+)$",
                r"^(?:please )?open\s+(.+)$",
            )

        for pattern in explicit_patterns:
            match = re.fullmatch(pattern, value)
            if match:
                return self._clean_website_target(match.group(1))

        for pattern in known_patterns:
            match = re.fullmatch(pattern, value)
            if not match:
                continue
            candidate = self._clean_website_target(match.group(1))
            candidate = re.sub(r"^(?:the|my)\s+", "", candidate)
            if candidate in self.WEBSITE_NAMES or self._looks_like_domain(candidate, original_text):
                return candidate
        return None

    @staticmethod
    def _clean_website_target(value: str) -> str:
        result = clean_slot(value)
        result = re.sub(
            r"\s+(?:in|with)\s+(?:chrome|safari|the browser)$",
            "",
            result,
        )
        result = re.sub(
            r"\s+(?:در|تو)\s+(?:کروم|سافاری|مرورگر)$",
            "",
            result,
        )
        return result.strip()

    @staticmethod
    def _looks_like_domain(value: str, original_text: str = "") -> bool:
        """True only for a domain the user actually SPOKE as one.

        Normalisation turns "github.com" into "github com", which is also what
        "open note app" or "open the me folder" look like. So the tokens must
        end in a known TLD *and* the original transcript must contain them
        joined by a literal dot or a spoken "dot"/«دات»/«نقطه».
        """
        tokens = [t for t in value.split() if t not in ("dot", "دات", "نقطه")]
        if len(tokens) < 2 or not all(re.fullmatch(r"[a-z0-9-]+", token) for token in tokens):
            return False
        if tokens[-1] not in {
            "com", "org", "net", "edu", "gov", "io", "co", "ir", "me",
            "dev", "app", "ai", "info", "biz", "ac",
        }:
            return False
        original = (original_text or "").lower()
        dotted = ".".join(tokens)
        spoken = r"\s+(?:dot|دات|نقطه)\s+".join(re.escape(t) for t in tokens)
        return dotted in original or bool(re.search(spoken, original))

    def _looks_like_rename(self, value: str, language: str) -> bool:
        if self._has_any(value, self.RENAME_VERBS):
            return True
        if language == "en":
            return bool(
                re.search(
                    r"\brename\b|\bchange\b.*\bname\b"
                    r"|^(?:the )?new name (?:should be|is|will be|must be)\b",
                    value,
                )
            )
        # «اسم»/«نام» must be a whole word (so «نامه» — letter — never matches;
        # the spoken contraction «اسمشو» = «اسمش رو» does) and the verb must be
        # a real rename verb, never a bare «کن».
        return bool(
            re.search(
                r"(?<!\w)(?:اسم|نام)(?:شو?| فایل| پوشه)?(?!\w).*(?:عوض|تغییر|بکن|بذار|بزار)"
                r"|(?<!\w)(?:تغییر|عوض)\s+(?:اسم|نام)"
                r"|(?<!\w)اسم جدید(?:ش)?(?: رو| را)?\s+(?:بشه|باشه|بذار|بزار)",
                value,
            )
        )

    @staticmethod
    def _looks_like_save_as(value: str, language: str) -> bool:
        if language == "en":
            return bool(
                re.search(
                    r"\bsave(?:\s+(?:this|the current|current|the|it|my))?"
                    r"(?:\s+(?:file|document))?\s+as\b",
                    value,
                )
                or re.search(
                    r"\bsave\b.*\b(?:on|to|in)\s+(?:the\s+)?"
                    r"(?:desktop|documents|downloads|folder)\b",
                    value,
                )
            )
        return bool(
            re.search(
                r"(?:با|به)\s+(?:اسم|نام).*(?:ذخیره|سیو)"
                r"|(?:ذخیره|سیو).*(?:روی|در)\s+(?:دسکتاپ|پوشه)",
                value,
            )
            or re.search(
                r"(?:روی|در)\s+(?:دسکتاپ|پوشه).*(?:ذخیره|سیو)",
                value,
            )
        )

    def _create_name(self, value: str, language: str) -> Optional[str]:
        if language == "en":
            patterns = (
                r"(?:named|called|name it|name is|with the name|name)\s+(.+)$",
            )
            suffix = r"\s+(?:please|for me)$"
        else:
            patterns = (
                r"(?:به اسم|به نام|با اسم)\s+(.+)$",
                r"(?:اسمش|نامش)(?: رو| را)?\s*(?:بذار|بزار|بکن|کن)\s+(.+)$",
            )
            suffix = (
                r"\s+(?:بساز|بسازی|بسازید|درست کن|درست کنی|درست کنید|ایجاد کن|ایجاد کنی|"
                r"ایجاد کنید|لطفا|لطفاً|برام|برای من)$"
            )
        for pattern in patterns:
            match = re.search(pattern, value)
            if match:
                result = re.sub(suffix, "", match.group(1)).strip()
                return self._strip_type_words(clean_slot(result))
        return None

    def _search_query(self, value: str, language: str) -> Optional[str]:
        if language == "en":
            match = re.search(
                r"(?:search(?: for)?|look for|find|where is|where s|where are)\s+(?:my |the )?(.+)$",
                value,
            )
            result = match.group(1) if match else ""
            result = re.sub(
                r"\s+(?:on|in)\s+(?:my|this|the)\s+(?:computer|pc|mac)$",
                "",
                result,
            )
            result = re.sub(r"\s+for me$", "", result)
            result = re.sub(r"^(?:the\s+)?(?:file|folder|document)\s+(?:named|called)\s+", "", result)
            result = re.sub(r"^(?:named|called)\s+", "", result)
        else:
            match = re.search(r"دنبال\s+(.+?)(?:\s+بگرد)?$", value)
            if not match:
                match = re.search(
                    r"(.+?)(?: رو| را)?(?:\s+(?:برام|برای من))?\s+(?:پیدا کن|سرچ کن|جستجو کن|کجاست|کجا هست|کجاس)$",
                    value,
                )
            result = match.group(1) if match else ""
            result = re.sub(
                r"\s+(?:روی|تو|در)\s+(?:کامپیوتر|سیستم|مک)(?:م| من)?$",
                "",
                result,
            )
            result = re.sub(r"\s+(?:برام|برای من)$", "", result)
        return self._strip_type_words(clean_slot(result))

    def _web_search_query(self, value: str, language: str):
        """A search that names the web or a browser is a web search, not a
        file search: "search for github on chrome", «تو گوگل دنبال هوا بگرد»."""
        if language == "en":
            match = re.search(
                r"^(?:please )?(?:search|look|google)(?: for)?\s+(.+?)\s+"
                r"(?:on|in|with|using)\s+(?:the\s+)?(?:web|internet|google|browser|chrome|safari)$",
                value,
            )
            if not match:
                match = re.search(
                    r"^(?:please )?(?:search|look)(?: for)?\s+(?:the\s+)?(?:web|internet|google)\s+for\s+(.+)$",
                    value,
                )
            if not match:
                match = re.search(r"^(?:please )?google\s+(.+)$", value)
            if not match:
                return None
            query = self._strip_type_words(clean_slot(match.group(1)))
        else:
            match = re.search(
                r"^(?:لطفا )?(?:تو|توی|در|با)\s+(?:گوگل|اینترنت|وب|مرورگر|کروم|سافاری)\s+"
                r"(?:دنبال\s+)?(.+?)(?: رو| را)?\s+(?:بگرد|سرچ کن|جستجو کن|پیدا کن)$",
                value,
            )
            if not match:
                match = re.search(
                    r"^(?:لطفا )?(.+?)(?: رو| را)?\s+(?:تو|توی|در|با)\s+(?:گوگل|اینترنت|وب|مرورگر|کروم|سافاری)"
                    r"\s+(?:بگرد|سرچ کن|جستجو کن|پیدا کن)$",
                    value,
                )
            if not match:
                match = re.search(r"^(?:لطفا )?(.+?)(?: رو| را)?\s+گوگل کن$", value)
            if not match:
                return None
            query = self._strip_type_words(clean_slot(match.group(1)))
        if not query:
            return None
        app = "chrome" if re.search(r"(?<!\w)(?:chrome|کروم)(?!\w)", value) else (
            "safari" if re.search(r"(?<!\w)(?:safari|سافاری)(?!\w)", value) else "browser"
        )
        return query, app

    def _find_and_open_query(
        self,
        value: str,
        language: str,
    ) -> Optional[str]:
        """Extract a filename from a combined find-and-open command."""
        if language == "en":
            patterns = (
                r"^(?:please )?(?:find|search for|look for)\s+and\s+open\s+(?:my |the )?(.+)$",
                r"^(?:please )?(?:find|search for|look for)\s+(?:my |the )?(.+?)\s+and\s+open(?: it)?$",
            )
        else:
            patterns = (
                r"^(.+?)(?: رو| را)?\s+(?:پیدا کن|سرچ کن|جستجو کن)\s+و\s+(?:باز کن|بازش کن)$",
                r"^(?:پیدا کن|سرچ کن|جستجو کن)\s+و\s+(?:باز کن|بازش کن)\s+(.+)$",
            )
        for pattern in patterns:
            match = re.search(pattern, value)
            if match:
                return self._strip_type_words(clean_slot(match.group(1)))
        return None

    def _open_query(self, value: str, language: str, kind: str) -> Optional[str]:
        context_words = {
            "open it", "open it again", "open again", "reopen it",
            "بازش کن", "دوباره بازش کن", "دوباره باز کن",
            "اونو باز کن", "آن را باز کن",
        }
        if value in context_words:
            return None
        if language == "en":
            result = re.sub(r"^(?:please )?(?:open|reopen|launch|start)\s+", "", value)
            result = re.sub(r"^(?:my |the )?", "", result)
            result = re.sub(r"\s+for me$", "", result)
        else:
            result = re.sub(r"\s*(?:رو|را)?\s*(?:باز کن|بازش کن|اجرا کن)$", "", value)
            result = re.sub(r"\s+(?:برام|برای من)$", "", result)
            result = re.sub(r"^(?:لطفا\s+)?(?:یه|یک|یه دونه)\s+", "", result)
        result = self._strip_type_words(clean_slot(result))
        if language == "en":
            result = re.sub(r"^(?:named|called)\s+", "", result)
        if result in ("", "it", "this", "این", "اون", "آن"):
            return None
        return result

    def _rename_slots(self, value: str, language: str) -> Dict[str, str]:
        slots: Dict[str, str] = {}
        if language == "en":
            pair = re.search(r"\bfrom\s+(.+?)\s+to\s+(.+)$", value)
            if pair:
                slots["old_name"] = clean_slot(pair.group(1))
                slots["new_name"] = clean_slot(pair.group(2))
                return slots
            pair = re.search(r"\brename\s+(.+?)\s+to\s+(.+)$", value)
            if pair and pair.group(1).strip() not in ("it", "this", "the file", "the folder"):
                slots["old_name"] = clean_slot(pair.group(1))
                slots["new_name"] = clean_slot(pair.group(2))
                return slots
            single = re.search(
                r"(?:rename(?: it)?|change (?:its|the file|the folder|the) name)"
                r"(?:\s+it)?(?:\s+to|\s+as)\s+(.+)$",
                value,
            )
            if not single:
                single = re.search(r"^(?:the )?new name (?:should be|is|will be|must be)\s+(.+)$", value)
            if single:
                slots["new_name"] = clean_slot(single.group(1))
            return slots

        # «اسم جدیدش بشه گزارش نهایی»
        new_only = re.search(
            r"(?<!\w)اسم جدید(?:ش)?(?: رو| را)?\s+(?:بشه|باشه|بذار|بزار)\s+(.+)$", value
        )
        if new_only:
            slots["new_name"] = clean_slot(new_only.group(1))
            return slots

        # "اسمش رو بکن جمشید جای قاسم" says the new name before the old one.
        new_then_old = re.search(
            r"(?:اسمش|نامش|اسم فایل|اسم پوشه).*?"
            r"(?:بکن|کن|بذار|بزار)\s+(.+?)\s+(?:به جای|جای)\s+(.+)$",
            value,
        )
        if new_then_old:
            slots["new_name"] = clean_slot(new_then_old.group(1))
            old_name = clean_slot(new_then_old.group(2))
            if old_name not in ("چیزی که الان هست", "اسم فعلی", "نام فعلی"):
                slots["old_name"] = old_name
            return slots
        old_then_new = re.search(r"\bاز\s+(.+?)\s+به\s+(.+?)(?:\s+تغییر بده)?$", value)
        if old_then_new:
            slots["old_name"] = clean_slot(old_then_new.group(1))
            slots["new_name"] = clean_slot(old_then_new.group(2))
            return slots
        contextual = re.search(
            r"(?:اسم|نام).*?(?:رو|را)?\s+به\s+(.+?)\s+"
            r"(?:تغییر بده|عوض کن)$",
            value,
        )
        if not contextual:
            contextual = re.search(
                r"(?:تغییر|عوض)\s+(?:اسم|نام)(?:ش| فایل| پوشه)?"
                r"(?:\s+بده|\s+کن)?\s+به\s+(.+)$",
                value,
            )
        if contextual:
            slots["new_name"] = clean_slot(contextual.group(1))
            return slots
        single = re.search(
            r"(?:اسمش|نامش)(?: رو| را)?.*?(?:بکن|کن|بذار|بزار|به)\s+(.+)$",
            value,
        )
        if single:
            candidate = re.sub(
                r"\s+(?:به جای چیزی که الان هست|جای چیزی که الان هست)$", "", single.group(1)
            )
            candidate = re.sub(r"^(?:به|رو|را)\s+", "", candidate)
            slots["new_name"] = clean_slot(candidate)
        return slots

    def _strip_type_words(self, value: str) -> str:
        result = value
        words = (
            "word document", "word file", "text file", "txt file", "document",
            "file", "folder", "directory", "سند ورد", "فایل ورد", "فایل متنی",
            "تکست فایل", "فایل", "سند", "پوشه", "فولدر",
        )
        for word in words:
            result = re.sub(
                r"(?:^|\s)" + re.escape(word) + r"(?:\s|$)",
                " ",
                result,
                flags=re.IGNORECASE,
            )
        return re.sub(r"\s+", " ", result).strip()

    def _closest_corpus_intent(self, value: str, language: str) -> Optional[str]:
        best_intent = None
        best_score = 0.0
        for intent, examples in self.phrases[language].items():
            if intent in ("confirm", "cancel"):
                continue
            for example in examples:
                score = SequenceMatcher(None, value, normalize(example)).ratio()
                if score > best_score:
                    best_intent, best_score = intent, score
        return best_intent if best_score >= 0.82 else None
