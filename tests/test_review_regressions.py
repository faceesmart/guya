"""Regressions found by the adversarial review of the September 2026 changes.
Each test is a phrasing that worked before, broke, and must keep working."""

import tempfile
import unittest
from pathlib import Path

from guya.assistant.actions.common import SafeDesktopActions
from guya.assistant.parser import CommandParser
from guya.assistant.service import AssistantService


class ParserRegressionTests(unittest.TestCase):
    def setUp(self):
        self.parser = CommandParser()

    def parse(self, text):
        c = self.parser.parse(text)
        return c.intent, c.slots

    def test_word_file_without_a_name_opens_word(self):
        for text in ("open word file", "open the word file", "فایل ورد رو باز کن", "سند ورد رو باز کن", "یه فایل ورد باز کن"):
            self.assertEqual(("open_app", {"app": "word"}), self.parse(text), text)
        self.assertEqual(("open_file", {"query": "report"}), self.parse("open the word file report"))

    def test_spoken_contraction_rename(self):
        self.assertEqual(("rename", {"new_name": "گزارش نهایی"}), self.parse("اسمشو بذار گزارش نهایی"))
        self.assertEqual(("rename", {"new_name": "گزارش"}), self.parse("نامشو بذار گزارش"))
        self.assertEqual("rename", self.parse("اسمشو عوض کن به نسخه دوم")[0])

    def test_direction_words_alone_are_not_navigation(self):
        for text in ("shut down the computer", "back up my thesis", "look up the weather",
                     "pull up my thesis", "what's up", "turn it down", "go to the next tab", "ورد رو بیار بالا"):
            self.assertNotEqual("browser_navigation", self.parse(text)[0], text)
        self.assertEqual(("browser_navigation", {"action": "scroll_down"}), self.parse("Down"))
        self.assertEqual(("browser_navigation", {"action": "forward"}), self.parse("Next page"))

    def test_pack_phrase_heard_without_the_dot_still_opens_the_site(self):
        self.assertEqual(("open_website", {"target": "github com"}), self.parse("visit github com"))

    def test_delete_words_inside_other_commands(self):
        self.assertEqual(("open_folder", {"query": "trash"}), self.parse("open the trash folder"))
        self.assertEqual(("rename", {"new_name": "trash bin"}), self.parse("rename it to trash bin"))
        self.assertEqual(("search", {"query": "remove"}), self.parse("find the file named remove"))
        self.assertEqual("delete_unsupported", self.parse("remove the photos folder")[0])

    def test_fillers_before_new_and_new_name(self):
        self.assertEqual("create_folder", self.parse("Okay, new folder")[0])
        self.assertEqual(("rename", {"new_name": "draft"}), self.parse("okay the new name should be draft"))

    def test_leading_answer(self):
        self.assertEqual("cancel", self.parser.leading_answer("no don't rename it"))
        self.assertEqual("confirm", self.parser.leading_answer("yes rename it"))
        self.assertEqual("confirm", self.parser.leading_answer("بله بازش کن"))
        self.assertEqual("cancel", self.parser.leading_answer("نه اسمش رو عوض نکن"))
        self.assertIsNone(self.parser.leading_answer("open chrome"))


class FakeDesktopActions(SafeDesktopActions):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.calls = []

    def open_path(self, path):
        self.calls.append(("open_path", str(path)))
        return self._success("Opened.", "باز شد.", Path(path))

    def open_app(self, app):
        self.calls.append(("open_app", app))
        return self._success(f"Opened {app}.", f"{app} باز شد.")

    def speak(self, text, language="en"):
        pass


class ServiceRegressionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.service = AssistantService(roots=[self.root], default_directory=self.root, platform="darwin")
        self.service.actions = FakeDesktopActions(roots=[self.root], default_directory=self.root)

    def tearDown(self):
        self.temp.cleanup()

    def test_spoken_refusal_with_extra_words_cancels(self):
        (self.root / "draft.txt").touch()
        self.service.context.remember(self.root / "draft.txt")
        self.assertEqual("needs_confirmation", self.service.handle("rename it to final").status)
        response = self.service.handle("no don't rename it")
        self.assertEqual("cancelled", response.status)
        self.assertTrue((self.root / "draft.txt").exists())
        self.assertIsNone(self.service.context.pending_command)

    def test_spoken_yes_with_extra_words_confirms(self):
        (self.root / "draft.txt").touch()
        self.service.context.remember(self.root / "draft.txt")
        self.service.handle("rename it to final")
        response = self.service.handle("yes rename it")
        self.assertEqual("success", response.status)
        self.assertTrue((self.root / "final.txt").exists())

    def test_command_while_a_name_is_awaited_runs_the_command(self):
        (self.root / "draft.txt").touch()
        self.service.context.remember(self.root / "draft.txt")
        self.assertEqual("needs_input", self.service.handle("rename it").status)
        response = self.service.handle("open calculator")
        self.assertEqual("success", response.status)
        self.assertEqual([("open_app", "calculator")], self.service.actions.calls)
        self.assertTrue((self.root / "draft.txt").exists())

    def test_bare_word_while_a_name_is_awaited_is_the_name(self):
        (self.root / "draft.txt").touch()
        self.service.context.remember(self.root / "draft.txt")
        self.service.handle("rename it")
        response = self.service.handle("memo")
        self.assertEqual("needs_confirmation", response.status)
        self.assertIn("memo", response.message)

    def test_folder_named_build_is_still_found(self):
        (self.root / "build").mkdir()
        (self.root / "build" / "thesis.pdf").touch()
        self.assertEqual("success", self.service.handle("open the build folder").status)
        self.assertEqual("success", self.service.handle("open thesis pdf").status)

    def test_word_file_after_a_remembered_folder_opens_word(self):
        (self.root / "backend").mkdir()
        self.service.handle("find backend folder")
        response = self.service.handle("open word file")
        self.assertEqual("success", response.status)
        self.assertEqual(("open_app", "word"), self.service.actions.calls[-1])



class LanguageSwitchAndAnswerTests(unittest.TestCase):
    """From the first manual test: short Persian words were misheard («بازش کن» →
    «بازشگو», «بله» → «بیلی»), and the user asked to switch languages by voice."""

    def setUp(self):
        self.parser = CommandParser()
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.service = AssistantService(roots=[self.root], default_directory=self.root, platform="darwin")
        self.service.actions = FakeDesktopActions(roots=[self.root], default_directory=self.root)

    def tearDown(self):
        self.temp.cleanup()

    def test_language_switch_phrasings(self):
        for text, code in (("switch to persian", "fa"), ("persian mode", "fa"), ("use english please", "en"),
                           ("switch to dual", "dual"), ("both languages", "dual"),
                           ("برو فارسی", "fa"), ("زبان رو انگلیسی کن", "en"), ("دو زبانه", "dual")):
            command = self.parser.parse(text)
            self.assertEqual(("set_language", code), (command.intent, command.slots.get("language")), text)

    def test_a_bare_language_name_is_not_a_switch(self):
        self.assertEqual("unknown", self.parser.parse("english").intent)
        self.assertEqual("open_file", self.parser.parse("open the english file").intent)

    def test_switch_reply_is_in_the_new_language(self):
        response = self.service.handle("switch to persian")
        self.assertEqual(("success", "fa"), (response.status, response.language))
        self.assertEqual("set_language", response.command.intent)

    def test_misheard_single_word_answers_a_pending_question(self):
        self.service.handle("create a text file named memo")
        response = self.service.handle("بیلی")   # Whisper's rendering of «بله»
        self.assertEqual("success", response.status)
        self.assertEqual("open_path", self.service.actions.calls[-1][0])

    def test_misheard_answer_is_never_used_without_a_question(self):
        response = self.service.handle("بیلی")
        self.assertEqual("error", response.status)
        self.assertEqual([], self.service.actions.calls)

class PersianWebSearchTests(unittest.TestCase):
    """From the second manual test: Persian puts the query after the verb."""

    def setUp(self):
        self.parser = CommandParser()

    def test_query_after_the_verb(self):
        for text in ("توی گوگل سرچ کن مدل موی پسرانه", "برو گوگل سرچ کن مدل موی پسرانه", "توی کروم سیچ کن مدل موی پسرانه"):
            command = self.parser.parse(text)
            self.assertEqual(("web_search", "مدل موی پسرانه"), (command.intent, command.slots.get("query")), text)
        self.assertEqual("chrome", self.parser.parse("توی کروم سرچ کن هوا").slots.get("app"))

    def test_google_as_a_verb(self):
        self.assertEqual(("web_search", "مدل موی پسرانه"),
                         (lambda c: (c.intent, c.slots.get("query")))(self.parser.parse("مدل موی پسرانه رو گوگل کن")))

    def test_open_browser_then_search_is_a_sequence(self):
        command = self.parser.parse("کروم رو باز کن و سیرچ کن مدل موی پسرونه")
        self.assertEqual(["open_app", "web_search"], [s.intent for s in command.steps])
        self.assertEqual("مدل موی پسرونه", command.steps[1].slots.get("query"))

    def test_colloquial_numbers_and_docx_in_filenames(self):
        from guya.assistant.normalizer import normalize_spoken_filename, filename_match_score
        self.assertEqual("ازمون 6 docx", normalize_spoken_filename("آزمون شیش دکس").replace("آ", "ا"))
        self.assertGreaterEqual(filename_match_score("شیش", "آزمون شیش.docx")[0], 0.58)

    def test_a_spoken_number_alone_is_a_real_query(self):
        temp = tempfile.TemporaryDirectory()
        root = Path(temp.name).resolve()
        (root / "آزمون پنج.docx").touch()
        service = AssistantService(roots=[root], default_directory=root, platform="darwin")
        service.actions = FakeDesktopActions(roots=[root], default_directory=root)
        response = service.handle("فایل ورد پنج رو پیدا کن")
        self.assertIn(response.status, ("success", "needs_selection"))
        temp.cleanup()

    def test_youtube_on_chrome_is_a_website(self):
        command = self.parser.parse("Open YouTube on Chrome")
        self.assertEqual(("open_website", {"target": "youtube", "app": "chrome"}), (command.intent, command.slots))


class ThirdManualTestTests(unittest.TestCase):
    def test_search_after_open_chrome_uses_chrome(self):
        command = CommandParser().parse("کروم رو باز کن و سیچ کن هوای تهران")
        self.assertEqual("chrome", command.steps[1].slots.get("app"))

    def test_misheard_choice_word_picks_the_option(self):
        parser = CommandParser()
        self.assertEqual(0, parser.fuzzy_selection_index("عوال"))
        self.assertEqual(0, parser.fuzzy_selection_index("آبال"))
        self.assertEqual(1, parser.fuzzy_selection_index("دومی"))
        self.assertIsNone(parser.fuzzy_selection_index("گزارش"))
        self.assertIsNone(parser.fuzzy_selection_index("open the second file"))


if __name__ == "__main__":
    unittest.main()
