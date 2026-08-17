import unittest

from guya.assistant.parser import CommandParser


class CommandParserTests(unittest.TestCase):
    def setUp(self):
        self.parser = CommandParser()

    def assert_command(self, text, intent, **slots):
        command = self.parser.parse(text)
        self.assertEqual(intent, command.intent, text)
        for key, value in slots.items():
            self.assertEqual(value, command.slots.get(key), text)

    def test_persian_word_variants(self):
        for text in (
            "برام یه فایل ورد بساز",
            "یک فایل ورد بساز",
            "یه فایل ورد برام درست کن",
        ):
            self.assert_command(text, "create_word_document")

    def test_english_word_variants(self):
        for text in (
            "Create a Word document",
            "Make me a new Word file",
            "Open Word and create a document",
        ):
            self.assert_command(text, "create_word_document")

    def test_extracts_bilingual_document_names(self):
        self.assert_command(
            "create a word file named guya",
            "create_word_document",
            name="guya",
        )
        self.assert_command(
            "create a word file name report alpha",
            "create_word_document",
            name="report alpha",
        )
        self.assert_command(
            "یه فایل ورد به اسم گویا بساز",
            "create_word_document",
            name="گویا",
        )
        self.assert_command(
            "create a file named notes",
            "create_text_file",
            name="notes",
        )
        self.assert_command(
            "یک فایل به اسم یادداشت بساز",
            "create_text_file",
            name="یادداشت",
        )

    def test_extracts_rename_from_and_to(self):
        self.assert_command(
            "rename it from ghasem to jamshid",
            "rename",
            old_name="ghasem",
            new_name="jamshid",
        )
        self.assert_command(
            "اسمش رو بکن جمشید جای قاسم",
            "rename",
            old_name="قاسم",
            new_name="جمشید",
        )
        self.assert_command(
            "اسمش رو بکن جمشید به جای چیزی که الان هست",
            "rename",
            new_name="جمشید",
        )
        self.assert_command(
            "Rename text1 to text2",
            "rename",
            old_name="text1",
            new_name="text2",
        )
        self.assert_command(
            "اسم فایل ساخته شده رو به نمونه نهایی تغییر بده",
            "rename",
            new_name="نمونه نهایی",
        )

    def test_contextual_rename_can_ask_for_name(self):
        self.assert_command("اسمش رو عوض کن", "rename")
        self.assert_command("change its name", "rename")

    def test_search_and_open_slots(self):
        self.assert_command("فایل گزارش رو پیدا کن", "search", query="گزارش")
        self.assert_command("find my guya file", "search", query="guya")
        self.assert_command(
            "open the folder named university",
            "open_folder",
            query="university",
        )
        self.assert_command("open calculator", "open_app", app="calculator")
        self.assert_command("find and open calculate for me", "open_app", app="calculator")
        self.assert_command(
            "find Guya folder on my computer",
            "search",
            query="guya",
        )
        self.assert_command(
            "Find and open text 6 docs file",
            "open_file",
            query="text 6 docs",
        )
        self.assert_command(
            "فایل تست شش رو پیدا کن و باز کن",
            "open_file",
            query="تست شش",
        )
        self.assert_command("open it again", "open_file")

    def test_voice_result_selection_variants(self):
        self.assertEqual(0, self.parser.selection_index("open the first one"))
        self.assertEqual(1, self.parser.selection_index("second"))
        self.assertEqual(2, self.parser.selection_index("option three"))
        self.assertEqual(0, self.parser.selection_index("اولی رو باز کن"))
        self.assertEqual(1, self.parser.selection_index("گزینه دو"))
        self.assertEqual(2, self.parser.selection_index("سوم"))

    def test_save_close_and_save_as_limit(self):
        self.assert_command("save the current file", "save_current")
        self.assert_command("فایل فعلی رو ذخیره کن", "save_current")
        self.assert_command("close calculator", "close_current")
        self.assert_command("پنجره فعلی رو ببند", "close_current")
        self.assert_command(
            "save this file as Guya Report on the Desktop",
            "save_as_unsupported",
        )

    def test_safe_browser_and_document_sequences(self):
        command = self.parser.parse("Open Chrome, then search for YouTube")
        self.assertEqual("sequence", command.intent)
        self.assertEqual(
            [("open_app", {"app": "chrome"}), (
                "web_search", {"query": "youtube", "app": "chrome"}
            )],
            [(step.intent, step.slots) for step in command.steps],
        )

        command = self.parser.parse("فایل فعلی رو ذخیره کن و پنجره فعلی رو ببند")
        self.assertEqual("sequence", command.intent)
        self.assertEqual(
            ["save_current", "close_current"],
            [step.intent for step in command.steps],
        )

    def test_bilingual_browser_navigation(self):
        examples = (
            ("scroll down", "scroll_down"),
            ("scroll the page down", "scroll_down"),
            ("page down", "scroll_down"),
            ("go a little down", "scroll_down"),
            ("scroll up the page", "scroll_up"),
            ("scroll the page up", "scroll_up"),
            ("page up", "scroll_up"),
            ("go to the top of the page", "top"),
            ("go to the bottom of the page", "bottom"),
            ("go back", "back"),
            ("go forward", "forward"),
            ("صفحه رو پایین ببر", "scroll_down"),
            ("صفحه رو ببر پایین", "scroll_down"),
            ("اسکرول کن پایین", "scroll_down"),
            ("یکم برو پایین", "scroll_down"),
            ("صفحه را بالا ببر", "scroll_up"),
            ("صفحه رو ببر بالا", "scroll_up"),
            ("اسکرول کن بالا", "scroll_up"),
            ("برو اول صفحه", "top"),
            ("برو آخر صفحه", "bottom"),
            ("برو عقب", "back"),
            ("برو جلو", "forward"),
        )
        for text, action in examples:
            with self.subTest(text=text):
                self.assert_command(
                    text,
                    "browser_navigation",
                    action=action,
                )

    def test_known_names_and_domains_open_websites(self):
        self.assert_command("go to YouTube", "open_website", target="youtube")
        self.assert_command(
            "visit github.com",
            "open_website",
            target="github com",
        )
        self.assert_command(
            "سایت ویکی پدیا رو باز کن",
            "open_website",
            target="ویکی پدیا",
        )
        self.assert_command(
            "برو به دانشگاه تهران",
            "open_website",
            target="دانشگاه تهران",
        )

    def test_open_browser_then_website_is_a_safe_sequence(self):
        command = self.parser.parse("Open Chrome, then go to YouTube")
        self.assertEqual("sequence", command.intent)
        self.assertEqual(
            [
                ("open_app", {"app": "chrome"}),
                ("open_website", {"target": "youtube", "app": "chrome"}),
            ],
            [(step.intent, step.slots) for step in command.steps],
        )

    def test_confirmation_and_cancellation(self):
        self.assertTrue(self.parser.is_confirmation("بله"))
        self.assertTrue(self.parser.is_confirmation("yes"))
        self.assertTrue(self.parser.is_cancellation("بیخیال"))
        self.assertTrue(self.parser.is_cancellation("cancel"))

    def test_unknown_text_is_not_executed(self):
        self.assert_command("what is the weather tomorrow", "unknown")

    def test_every_documented_phrase_maps_to_its_intent(self):
        for language, intents in self.parser.phrases.items():
            for expected, examples in intents.items():
                for text in examples:
                    with self.subTest(language=language, text=text):
                        self.assertEqual(expected, self.parser.parse(text).intent)


if __name__ == "__main__":
    unittest.main()
