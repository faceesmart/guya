"""Intent routing, context, confirmation, and safe action execution."""

import logging
from pathlib import Path
from typing import List, Optional

from .actions import create_action_executor
from .context import AssistantContext
from .models import AssistantResponse, ParsedCommand, SearchMatch
from .normalizer import (
    clean_slot,
    detect_language,
    filename_match_score,
    normalize,
)
from .parser import CommandParser


log = logging.getLogger("Guya")


class AssistantService:
    """Stateful local assistant used by the voice widget."""

    def __init__(self, roots=None, default_directory=None, platform=None):
        self.parser = CommandParser()
        self.context = AssistantContext()
        self.actions = create_action_executor(
            roots=roots,
            default_directory=default_directory,
            platform=platform,
        )

    # Intents that may replace a pending question. Saying a fresh command while
    # the assistant waits for yes/no simply drops the question (nothing is
    # renamed or opened) and runs the new command; the user is not forced to
    # say "no" first. Answers that look like file choices stay with the
    # selection handler.
    _FRESH_COMMAND_INTENTS = frozenset({
        "create_word_document", "create_text_file", "create_folder", "open_app",
        "save_current", "close_current", "web_search", "open_website",
        "browser_navigation", "search", "rename", "sequence", "delete_unsupported",
        "save_as_unsupported", "open_file", "open_folder",
    })

    def handle(self, text: str) -> AssistantResponse:
        language = detect_language(text)
        if self.context.pending_expired():
            had_list = bool(self.context.pending_options)
            log.info("Assistant pending question expired; clearing it")
            self.context.clear_pending()
            if had_list and self.parser.selection_index(text) is not None:
                return self._response(
                    "error",
                    language,
                    "That list has expired. Please search again.",
                    "آن فهرست منقضی شده است. لطفاً دوباره جستجو کنید.",
                )
        if self.context.pending_options:
            return self._handle_pending_selection(text, language)
        if self.context.pending_command is not None:
            pending_language = self.context.pending_command.language
            pending_path = self.context.pending_path
            pending_action = self.context.pending_action
            if self.context.pending_slot is not None:
                return self._fill_pending_slot(text, language)
            # "yes, rename it" / «نه اسمش رو عوض نکن»: an answer that carries
            # extra words is still an answer, never a new command. A single
            # short word close to yes/no («بیلی» for «بله») is also an answer:
            # the question was just asked and nothing else is likely.
            answer = self.parser.leading_answer(text) or self.parser.fuzzy_answer(text)
            if answer == "confirm" or self.parser.is_confirmation(text):
                return self._execute_pending()
            if answer == "cancel" or self.parser.is_cancellation(text):
                self.context.clear_pending()
                if pending_action == "open_created" and pending_path is not None:
                    return self._response(
                        "cancelled",
                        pending_language,
                        f"Okay. {pending_path.name} was created and left closed.",
                        f"باشه. {pending_path.name} ساخته شد و بسته ماند.",
                        path=pending_path,
                    )
                return self._response(
                    "cancelled",
                    pending_language,
                    "Cancelled. Nothing was changed.",
                    "لغو شد و تغییری انجام نشد.",
                )
            fresh = self.parser.parse(text)
            replaces = fresh.intent in self._FRESH_COMMAND_INTENTS and not (
                fresh.intent == "rename" and not fresh.slots and pending_action == "rename"
            )
            if replaces:
                log.info("Assistant pending question dropped for a new command: %s", fresh.intent)
                self.context.clear_pending()
                return self._dispatch(fresh, language)
            return self._response(
                "needs_confirmation",
                pending_language,
                "Please say yes to confirm or no to cancel.",
                "برای تأیید بگویید بله و برای لغو بگویید نه.",
            )

        return self._dispatch(self.parser.parse(text), language)

    def _dispatch(self, command: ParsedCommand, language: str) -> AssistantResponse:
        intent = command.intent
        if intent == "set_language":
            target = command.slots.get("language")
            if target not in ("fa", "en", "dual"):
                return self._response(
                    "error", language,
                    "Which language: Persian, English, or dual?",
                    "کدام زبان: فارسی، انگلیسی یا دو زبانه؟",
                    command,
                )
            names_en = {"fa": "Persian", "en": "English", "dual": "Persian and English"}
            names_fa = {"fa": "فارسی", "en": "انگلیسی", "dual": "فارسی و انگلیسی"}
            # Reply in the language being switched TO, since that is what the
            # user will hear and read from now on.
            reply_language = "fa" if target == "fa" else ("en" if target == "en" else language)
            return self._response(
                "success",
                reply_language,
                f"Switched to {names_en.get(target, target)}.",
                f"زبان به {names_fa.get(target, target)} تغییر کرد.",
                command,
            )
        if intent == "delete_unsupported":
            return self._response(
                "error",
                language,
                "Guya never deletes or removes files. Please do that yourself in Finder or Explorer.",
                "گویا هیچ فایلی را حذف نمی‌کند. لطفاً این کار را خودتان در Finder یا Explorer انجام دهید.",
                command,
            )
        if intent == "unknown":
            return self._response(
                "error",
                language,
                "I did not understand. Try create, open, find, rename, or a browser command.",
                "متوجه نشدم. دستور ساختن، باز کردن، پیدا کردن، تغییر نام یا کنترل مرورگر را بگویید.",
                command,
            )
        if intent in ("confirm", "cancel"):
            return self._response(
                "error",
                language,
                "There is no action waiting for confirmation.",
                "هیچ کاری منتظر تأیید نیست.",
                command,
            )

        if intent == "sequence":
            return self._execute_sequence(command)
        if intent == "create_word_document":
            return self._create_and_offer_open(
                command,
                self.actions.create_word_document(command.slots.get("name")),
            )
        if intent == "create_text_file":
            return self._create_and_offer_open(
                command,
                self.actions.create_text_file(command.slots.get("name")),
            )
        if intent == "create_folder":
            return self._create_and_offer_open(
                command,
                self.actions.create_folder(command.slots.get("name")),
            )
        if intent == "open_app":
            app = command.slots.get("app")
            if not app:
                return self._response(
                    "error",
                    language,
                    "Please say which application to open.",
                    "لطفاً نام برنامه‌ای را که باید باز شود بگویید.",
                    command,
                )
            return self._from_outcome(
                self.actions.open_app(app),
                command,
            )
        if intent == "save_current":
            return self._from_outcome(self.actions.save_current(), command)
        if intent == "close_current":
            return self._from_outcome(self.actions.close_current(), command)
        if intent == "web_search":
            return self._web_search(command)
        if intent == "open_website":
            return self._open_website(command)
        if intent == "browser_navigation":
            action = command.slots.get("action")
            if not action:
                return self._response(
                    "error",
                    language,
                    "Please say how to move in the browser.",
                    "لطفاً بگویید در مرورگر چه حرکتی انجام شود.",
                    command,
                )
            return self._from_outcome(
                self.actions.browser_control(action),
                command,
            )
        if intent == "save_as_unsupported":
            return self._response(
                "error",
                language,
                "I can save the current file, but Save As to a new name or folder is not supported yet.",
                "می‌توانم فایل فعلی را ذخیره کنم، اما ذخیره با نام یا پوشه جدید هنوز پشتیبانی نمی‌شود.",
                command,
            )
        if intent in ("open_file", "open_folder"):
            kind = "folder" if intent == "open_folder" else "file"
            query = command.slots.get("query")
            if query:
                contextual = self._recent_exact_match(query, kind)
                if contextual is not None:
                    return self._from_outcome(
                        self.actions.open_path(contextual),
                        command,
                    )
                return self._open_search_result(command, query, kind)
            current = self.context.current_path
            if (
                current
                and current.exists()
                and (kind != "folder" or current.is_dir())
            ):
                return self._from_outcome(self.actions.open_path(current), command)
            return self._response(
                "error",
                language,
                f"Please say which {kind} to open.",
                "لطفاً نام پوشه را بگویید." if kind == "folder" else "لطفاً نام فایل را بگویید.",
                command,
            )
        if intent == "search":
            return self._search(command)
        if intent == "rename":
            return self._prepare_rename(command)

        return self._response(
            "error",
            language,
            "That action is not supported yet.",
            "این کار هنوز پشتیبانی نمی‌شود.",
            command,
        )

    def speak(self, text: str, language: Optional[str] = None) -> None:
        self.actions.speak(text, language or detect_language(text))

    def stop_speaking(self) -> None:
        self.actions.stop_speaking()

    def set_target_app(self, target_app) -> None:
        self.actions.set_target_app(target_app)

    def _execute_sequence(self, command: ParsedCommand) -> AssistantResponse:
        """Run up to three already-whitelisted steps and stop on first failure."""
        language = command.language
        if not 2 <= len(command.steps) <= 3:
            return self._response(
                "error",
                language,
                "A sequence must contain two or three supported steps.",
                "دستور چندمرحله‌ای باید دو یا سه مرحله پشتیبانی‌شده داشته باشد.",
                command,
            )

        # Validate every step BEFORE running any, so a disallowed third step
        # never leaves the first two already executed.
        allowed_steps = ("open_app", "web_search", "open_website", "save_current", "close_current")
        for step in command.steps:
            if step.intent not in allowed_steps:
                return self._response(
                    "error",
                    language,
                    "That step is not allowed inside a sequence, so nothing was done. "
                    "Sequences may only open apps or websites, search the web, save, or close.",
                    "این مرحله در دستور چندمرحله‌ای مجاز نیست، بنابراین هیچ کاری انجام نشد. "
                    "دستور چندمرحله‌ای فقط می‌تواند برنامه یا سایت باز کند، در وب جستجو کند، ذخیره یا ببندد.",
                    command,
                )

        completed = []
        last_path = None
        for step in command.steps:
            if step.intent == "open_app":
                app = step.slots.get("app")
                response = (
                    self._from_outcome(self.actions.open_app(app), step)
                    if app
                    else self._response(
                        "error", language, "Application name is missing.",
                        "نام برنامه مشخص نیست.", step,
                    )
                )
            elif step.intent == "web_search":
                response = self._web_search(step)
            elif step.intent == "open_website":
                response = self._open_website(step)
            elif step.intent == "save_current":
                response = self._from_outcome(self.actions.save_current(), step)
            elif step.intent == "close_current":
                response = self._from_outcome(self.actions.close_current(), step)
            else:
                return self._response(
                    "error",
                    language,
                    "That step is not allowed inside a sequence.",
                    "این مرحله در دستور چندمرحله‌ای مجاز نیست.",
                    command,
                )

            if not response.success:
                return self._response(
                    "error",
                    language,
                    f"Stopped after {len(completed)} step(s). {response.message}",
                    f"پس از {len(completed)} مرحله متوقف شد. {response.message}",
                    command,
                    response.path,
                )
            completed.append(response.message)
            last_path = response.path or last_path

        return self._response(
            "success",
            language,
            f"Completed {len(completed)} steps. " + " ".join(completed),
            f"{len(completed)} مرحله انجام شد. " + " ".join(completed),
            command,
            last_path,
        )

    def _web_search(self, command: ParsedCommand) -> AssistantResponse:
        query = command.slots.get("query")
        if not query:
            return self._response(
                "error",
                command.language,
                "Please say what to search for.",
                "لطفاً عبارت جستجو را بگویید.",
                command,
            )
        return self._from_outcome(
            self.actions.search_web(query, app=command.slots.get("app")),
            command,
        )

    def _open_website(self, command: ParsedCommand) -> AssistantResponse:
        target = command.slots.get("target")
        if not target:
            return self._response(
                "error",
                command.language,
                "Please say which website to open.",
                "لطفاً نام سایتی را که باید باز شود بگویید.",
                command,
            )
        return self._from_outcome(
            self.actions.open_website(target, app=command.slots.get("app")),
            command,
        )

    def _search(self, command: ParsedCommand) -> AssistantResponse:
        language = command.language
        query = command.slots.get("query")
        if not query:
            return self._response(
                "error",
                language,
                "Please say what to search for.",
                "لطفاً بگویید دنبال چه چیزی بگردم.",
                command,
            )
        matches = self._ranked_matches(query)
        if not matches:
            return self._response(
                "error",
                language,
                f"I could not find {query}.",
                f"{query} پیدا نشد.",
                command,
            )
        if not self._is_unambiguous(matches):
            return self._request_result_selection(command, matches)

        best = matches[0].path
        self.context.remember(best)
        if len(matches) == 1:
            return self._response(
                "success",
                language,
                f"Found {best.name}. Say open it to open it.",
                f"{best.name} پیدا شد. برای باز کردن بگویید بازش کن.",
                command,
                best,
            )
        return self._response(
            "success",
            language,
            f"The best match is {best.name}. Say open it to open it.",
            f"بهترین نتیجه {best.name} است. برای باز کردن بگویید بازش کن.",
            command,
            best,
        )

    def _open_search_result(
        self,
        command: ParsedCommand,
        query: str,
        kind: str,
    ) -> AssistantResponse:
        matches = self._ranked_matches(query, kind=kind)
        if not matches:
            return self._response(
                "error",
                command.language,
                f"I could not find {query}.",
                f"{query} پیدا نشد.",
                command,
            )
        if not self._is_unambiguous(matches):
            return self._request_result_selection(command, matches)
        return self._from_outcome(
            self.actions.open_path(matches[0].path),
            command,
        )

    def _ranked_matches(
        self,
        query: str,
        kind: Optional[str] = None,
    ) -> List[SearchMatch]:
        matches = self.actions.search_matches(query, kind=kind, limit=20)
        recent_order = {
            path: index for index, path in enumerate(self.context.recent_paths)
        }

        def sort_score(match: SearchMatch) -> float:
            if match.path not in recent_order:
                return match.score
            recency_bonus = max(
                0.0,
                0.03 - recent_order[match.path] * 0.005,
            )
            return match.score + recency_bonus

        return sorted(
            matches,
            key=lambda match: (
                -sort_score(match),
                not match.exact,
                len(match.path.name),
                str(match.path).casefold(),
            ),
        )

    @staticmethod
    def _is_unambiguous(matches: List[SearchMatch]) -> bool:
        if not matches:
            return False
        if len(matches) == 1:
            return matches[0].exact or matches[0].score >= 0.90
        first, second = matches[0], matches[1]
        if first.exact:
            return not second.exact and second.score < 0.96
        return first.score >= 0.86 and first.score - second.score >= 0.12

    def _request_result_selection(
        self,
        command: ParsedCommand,
        matches: List[SearchMatch],
    ) -> AssistantResponse:
        options = [match.path for match in matches[:3]]
        self.context.request_selection(command, options, action="open")
        log.info(
            "Assistant result selection requested: query=%r options=%s",
            command.slots.get("query"),
            [str(path) for path in options],
        )
        en_items = "; ".join(
            f"{index}. {path.name} in {path.parent.name}"
            for index, path in enumerate(options, 1)
        )
        fa_items = "؛ ".join(
            f"{index}. {path.name} در {path.parent.name}"
            for index, path in enumerate(options, 1)
        )
        return self._response(
            "needs_selection",
            command.language,
            f"I found {len(options)} close matches: {en_items}. "
            "Say first, second, third, or cancel.",
            f"{len(options)} نتیجه نزدیک پیدا شد: {fa_items}. "
            "بگویید اول، دوم، سوم یا لغو.",
            command,
            options=options,
        )

    def _handle_pending_selection(
        self,
        text: str,
        language: str,
    ) -> AssistantResponse:
        command = self.context.pending_command
        options = list(self.context.pending_options)
        pending_language = command.language if command else language
        if self.parser.is_cancellation(text):
            log.info(
                "Assistant result selection cancelled: heard=%r options=%s",
                text,
                [str(path) for path in options],
            )
            self.context.clear_pending()
            return self._response(
                "cancelled",
                pending_language,
                "Selection cancelled. Nothing was opened.",
                "انتخاب لغو شد و چیزی باز نشد.",
                command,
            )

        index = self.parser.selection_index(text)
        if index is None:
            index = self.parser.fuzzy_selection_index(text)
        if index is None:
            choice_text = text
            choice_command = self.parser.parse(text)
            if choice_command.intent in ("open_file", "open_folder"):
                choice_text = choice_command.slots.get("query") or text
            ranked_choices = sorted(
                (
                    (
                        *filename_match_score(choice_text, path.name),
                        option_index,
                    )
                    for option_index, path in enumerate(options)
                ),
                key=lambda item: (-item[0], not item[1], item[2]),
            )
            if ranked_choices:
                best_score, best_exact, best_index = ranked_choices[0]
                second_score = (
                    ranked_choices[1][0] if len(ranked_choices) > 1 else 0.0
                )
                if best_exact or (
                    best_score >= 0.86 and best_score - second_score >= 0.12
                ):
                    index = best_index

        if index is None or not 0 <= index < len(options):
            fresh = self.parser.parse(text)
            if fresh.intent in self._FRESH_COMMAND_INTENTS and fresh.intent not in (
                "open_file", "open_folder", "search",
            ):
                log.info("Assistant selection dropped for a new command: %s", fresh.intent)
                self.context.clear_pending()
                return self._dispatch(fresh, language)
            log.info(
                "Assistant result selection unclear: heard=%r options=%s",
                text,
                [str(path) for path in options],
            )
            return self._response(
                "needs_selection",
                pending_language,
                f"Please choose first through {len(options)}, or say cancel.",
                f"لطفاً یکی از گزینه‌های یک تا {len(options)} را انتخاب کنید یا بگویید لغو.",
                command,
                options=options,
            )

        selected = options[index]
        log.info(
            "Assistant result selected: heard=%r index=%s path=%s",
            text,
            index + 1,
            selected,
        )
        self.context.clear_pending()
        if not selected.exists():
            return self._response(
                "error",
                pending_language,
                f"{selected.name} is no longer available. Please search again.",
                f"{selected.name} دیگر در دسترس نیست. لطفاً دوباره جستجو کنید.",
                command,
            )
        return self._from_outcome(self.actions.open_path(selected), command)

    def _prepare_rename(self, command: ParsedCommand) -> AssistantResponse:
        language = command.language
        target: Optional[Path] = None
        old_name = command.slots.get("old_name")
        if old_name:
            target = self.actions.find_one(old_name)
        elif self.context.current_path and self.context.current_path.exists():
            target = self.context.current_path
        if target is None:
            return self._response(
                "error",
                language,
                "First find or create the file or folder you want to rename.",
                "ابتدا فایل یا پوشه موردنظر را پیدا یا ایجاد کنید.",
                command,
            )
        new_name = command.slots.get("new_name")
        if not new_name:
            self.context.request_slot(command, "new_name", target)
            return self._response(
                "needs_input",
                language,
                "What should the new name be?",
                "نام جدید چه باشد؟",
                command,
                target,
            )
        self.context.request_confirmation(command, target)
        return self._response(
            "needs_confirmation",
            language,
            f"Rename {target.name} to {new_name}? Say yes or no.",
            f"نام {target.name} به {new_name} تغییر کند؟ بگویید بله یا نه.",
            command,
            target,
        )

    def _fill_pending_slot(self, text: str, language: str) -> AssistantResponse:
        if self.parser.is_cancellation(text):
            self.context.clear_pending()
            return self._response(
                "cancelled",
                language,
                "Cancelled. Nothing was changed.",
                "لغو شد و تغییری انجام نشد.",
            )
        command = self.context.pending_command
        target = self.context.pending_path
        slot = self.context.pending_slot
        if command is None or slot is None:
            self.context.clear_pending()
            return self._response(
                "error",
                language,
                "The pending command was lost. Please try again.",
                "دستور در انتظار از بین رفت. لطفاً دوباره تلاش کنید.",
            )
        if self.parser.is_confirmation(text):
            # "yes" is an answer to a question we did not ask; never make it a filename.
            return self._response(
                "needs_input",
                command.language,
                "Please say the new name itself.",
                "لطفاً خود نام جدید را بگویید.",
                command,
                target,
            )
        # A clearly different command ("open calculator", "scroll down") is not
        # a name either: drop the rename and run it. A bare word stays a name.
        fresh = self.parser.parse(text)
        if fresh.intent in self._FRESH_COMMAND_INTENTS and fresh.intent != "rename" and (
            fresh.slots or fresh.intent in ("save_current", "close_current", "delete_unsupported")
        ):
            log.info("Assistant name question dropped for a new command: %s", fresh.intent)
            self.context.clear_pending()
            return self._dispatch(fresh, language)
        value = normalize(text)
        if language == "en":
            for prefix in (
                "the new name should be ", "the new name is ", "new name should be ",
                "new name is ", "name it ", "call it ", "change it to ", "to ",
            ):
                if value.startswith(prefix):
                    value = value[len(prefix):]
                    break
        else:
            for prefix in (
                "اسمش رو بذار ", "اسمش را بذار ", "اسمش رو بکن ",
                "اسمش را بکن ", "اسم جدیدش باشه ", "اسم جدیدش باشد ",
                "نام جدیدش باشه ", "نام جدیدش باشد ", "اسم جدید ",
                "نام جدید ", "بذار ", "بکن ",
            ):
                if value.startswith(prefix):
                    value = value[len(prefix):]
                    break
        value = clean_slot(value)
        if not value:
            return self._response(
                "needs_input",
                command.language,
                "I did not hear the new name. Please say it again.",
                "نام جدید شنیده نشد. لطفاً دوباره بگویید.",
                command,
                target,
            )
        command.slots[slot] = value
        self.context.clear_pending()
        if target is not None:
            self.context.remember(target)
        return self._prepare_rename(command)

    def _execute_pending(self) -> AssistantResponse:
        command = self.context.pending_command
        target = self.context.pending_path
        action = self.context.pending_action
        self.context.clear_pending()
        if command is None or target is None:
            return self._response(
                "error",
                "en",
                "There is no pending action.",
                "هیچ کار در انتظاری وجود ندارد.",
            )
        if action == "open_created":
            outcome = self.actions.open_path(target)
        else:
            outcome = self.actions.rename(target, command.slots["new_name"])
        return self._from_outcome(outcome, command)

    def _create_and_offer_open(
        self,
        command: ParsedCommand,
        outcome,
    ) -> AssistantResponse:
        if not outcome.success or outcome.path is None:
            return self._from_outcome(outcome, command)
        self.context.remember(outcome.path)
        self.context.request_confirmation(
            command,
            outcome.path,
            action="open_created",
        )
        return self._response(
            "needs_confirmation",
            command.language,
            f"Created {outcome.path.name}. Open it now? Say yes or no.",
            f"{outcome.path.name} ساخته شد. الان بازش کنم؟ بگویید بله یا نه.",
            command,
            outcome.path,
        )

    def _from_outcome(self, outcome, command: ParsedCommand) -> AssistantResponse:
        if outcome.path is not None and outcome.success:
            self.context.remember(outcome.path)
        return AssistantResponse(
            status="success" if outcome.success else "error",
            message=outcome.message_for(command.language),
            command=command,
            path=outcome.path,
            language=command.language,
        )

    @staticmethod
    def _path_matches(path: Path, query: str) -> bool:
        score, exact = filename_match_score(query, path.name)
        return exact or score >= 0.96

    def _recent_exact_match(
        self,
        query: str,
        kind: Optional[str] = None,
    ) -> Optional[Path]:
        for path in self.context.recent_paths:
            if not path.exists():
                continue
            if kind == "folder" and not path.is_dir():
                continue
            if kind == "file" and not path.is_file():
                continue
            if self._path_matches(path, query):
                return path
        return None

    @staticmethod
    def _response(
        status: str,
        language: str,
        message_en: str,
        message_fa: str,
        command: Optional[ParsedCommand] = None,
        path: Optional[Path] = None,
        options: Optional[List[Path]] = None,
    ) -> AssistantResponse:
        return AssistantResponse(
            status=status,
            message=message_fa if language == "fa" else message_en,
            command=command,
            path=path,
            language=language,
            options=list(options or []),
        )
