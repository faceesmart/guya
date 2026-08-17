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

    CREATE_VERBS = (
        "create", "make", "build", "new", "بساز", "درست کن", "ایجاد کن",
    )
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
        "search", "find", "look for", "جستجو", "سرچ", "پیدا کن", "بگرد",
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
        "github", "git hub", "gmail", "openai", "open ai",
        "university of tehran", "tehran university",
        "گوگل", "یوتیوب", "ویکی پدیا", "ویکیپدیا", "گیت هاب",
        "جی میل", "دانشگاه تهران",
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
        return value in self._confirm[lang]

    def is_cancellation(self, text: str) -> bool:
        lang = detect_language(text)
        value = normalize(text)
        return value in self._cancel[lang]

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

        if value in self._confirm[language]:
            return ParsedCommand("confirm", language=language, original_text=text)
        if value in self._cancel[language]:
            return ParsedCommand("cancel", language=language, original_text=text)

        parts = self._sequence_parts(value, language)
        if len(parts) > 1:
            if len(parts) > 3:
                return ParsedCommand("unknown", language=language, original_text=text)
            steps = [
                self._parse_single(part, language, original_text=part)
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
    ) -> ParsedCommand:
        base = {"language": language, "original_text": original_text}

        # Creation phrases may contain "name it", so detect them before rename.
        if self._has_any(value, self.CREATE_WORD_WORDS) and self._has_any(value, self.CREATE_VERBS):
            name = self._create_name(value, language)
            return ParsedCommand(
                "create_word_document", slots=self._slot("name", name), **base
            )
        if self._has_any(value, self.FOLDER_WORDS) and self._has_any(value, self.CREATE_VERBS):
            name = self._create_name(value, language)
            return ParsedCommand("create_folder", slots=self._slot("name", name), **base)
        if self._has_any(value, self.TEXT_FILE_WORDS) and self._has_any(value, self.CREATE_VERBS):
            name = self._create_name(value, language)
            return ParsedCommand("create_text_file", slots=self._slot("name", name), **base)
        if self._has_any(value, self.FILE_WORDS) and self._has_any(value, self.CREATE_VERBS):
            name = self._create_name(value, language)
            return ParsedCommand("create_text_file", slots=self._slot("name", name), **base)
        if self._looks_like_rename(value, language):
            return ParsedCommand("rename", slots=self._rename_slots(value, language), **base)
        if self._has_any(value, self.SAVE_VERBS):
            if self._looks_like_save_as(value, language):
                return ParsedCommand("save_as_unsupported", **base)
            return ParsedCommand("save_current", **base)
        if self._has_any(value, self.CLOSE_VERBS):
            return ParsedCommand("close_current", **base)

        browser_action = self._browser_navigation_action(value, language)
        if browser_action:
            return ParsedCommand(
                "browser_navigation",
                slots={"action": browser_action},
                **base,
            )

        website = self._website_target(value, language)
        if website:
            slots = {"target": website}
            app = self._app_name(value)
            if app in ("browser", "chrome", "safari"):
                slots["app"] = app
            return ParsedCommand("open_website", slots=slots, **base)

        # Prefer opening a named application when both "find" and "open" occur,
        # e.g. a slightly noisy transcript: "find and open calculate for me".
        app = self._app_name(value)
        if app and self._has_any(value, self.OPEN_VERBS):
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
            query = self._search_query(value, language)
            return ParsedCommand("search", slots=self._slot("query", query), **base)

        if self._has_any(value, self.OPEN_VERBS):
            if self._has_any(value, self.FOLDER_WORDS):
                query = self._open_query(value, language, kind="folder")
                return ParsedCommand("open_folder", slots=self._slot("query", query), **base)
            query = self._open_query(value, language, kind="file")
            return ParsedCommand("open_file", slots=self._slot("query", query), **base)

        # The phrase packs also catch short natural variants that omit a verb.
        corpus_intent = self._closest_corpus_intent(value, language)
        if corpus_intent:
            if corpus_intent == "open_app":
                app = self._app_name(value)
                if not app:
                    return ParsedCommand("unknown", **base)
                return ParsedCommand("open_app", slots={"app": app}, **base)
            return ParsedCommand(corpus_intent, **base)
        return ParsedCommand("unknown", **base)

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
        return None

    def _website_target(self, value: str, language: str) -> Optional[str]:
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
            if candidate in self.WEBSITE_NAMES or self._looks_like_domain(candidate):
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
    def _looks_like_domain(value: str) -> bool:
        tokens = value.split()
        if len(tokens) < 2 or not all(re.fullmatch(r"[a-z0-9-]+", token) for token in tokens):
            return False
        return tokens[-1] in {
            "com", "org", "net", "edu", "gov", "io", "co", "ir", "me",
            "dev", "app", "ai",
        }

    def _looks_like_rename(self, value: str, language: str) -> bool:
        if self._has_any(value, self.RENAME_VERBS):
            return True
        if language == "en":
            return bool(re.search(r"\brename\b|\bchange\b.*\bname\b", value))
        return bool(
            re.search(
                r"(?:اسم|نام).*(?:عوض|تغییر|بکن|کن|بذار|بزار)"
                r"|(?:تغییر|عوض)\s+(?:اسم|نام)",
                value,
            )
        )

    @staticmethod
    def _looks_like_save_as(value: str, language: str) -> bool:
        if language == "en":
            return bool(
                re.search(
                    r"\bsave\s+(?:this|the current|current)?\s*(?:file|document)?\s+as\b",
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
            suffix = r"\s+(?:بساز|درست کن|ایجاد کن|لطفا|لطفاً|برام)$"
        for pattern in patterns:
            match = re.search(pattern, value)
            if match:
                result = re.sub(suffix, "", match.group(1)).strip()
                return self._strip_type_words(clean_slot(result))
        return None

    def _search_query(self, value: str, language: str) -> Optional[str]:
        if language == "en":
            match = re.search(r"(?:search(?: for)?|look for|find)\s+(?:my |the )?(.+)$", value)
            result = match.group(1) if match else ""
            result = re.sub(
                r"\s+(?:on|in)\s+(?:my|this|the)\s+(?:computer|pc|mac)$",
                "",
                result,
            )
            result = re.sub(r"\s+for me$", "", result)
        else:
            match = re.search(r"دنبال\s+(.+?)(?:\s+بگرد)?$", value)
            if not match:
                match = re.search(r"(.+?)(?: رو| را)?\s+(?:پیدا کن|سرچ کن|جستجو کن)$", value)
            result = match.group(1) if match else ""
            result = re.sub(
                r"\s+(?:روی|تو|در)\s+(?:کامپیوتر|سیستم|مک)(?:م| من)?$",
                "",
                result,
            )
            result = re.sub(r"\s+(?:برام|برای من)$", "", result)
        return self._strip_type_words(clean_slot(result))

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
            if single:
                slots["new_name"] = clean_slot(single.group(1))
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
            slots["new_name"] = clean_slot(candidate)
        return slots

    def _strip_type_words(self, value: str) -> str:
        result = value
        words = (
            "word document", "word file", "text file", "txt file", "document",
            "file", "folder", "directory", "سند ورد", "فایل ورد", "فایل متنی",
            "تکست فایل", "فایل", "پوشه", "فولدر",
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
