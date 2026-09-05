"""Parser behaviour that the held-out evaluation (eval/data/intents.jsonl)
showed to be missing: filler words, safe handling of "new", domains that
must be spoken as domains, Persian rename false positives, and the explicit
refusal of deletion."""

import unittest

from guya.assistant.parser import CommandParser


class FillerToleranceTests(unittest.TestCase):
    def setUp(self):
        self.parser = CommandParser()

    def parse(self, text):
        command = self.parser.parse(text)
        return command.intent, command.slots

    def test_english_scroll_with_fillers(self):
        for text in ("Let's scroll down", "Again, scroll down", "please scroll down a bit",
                     "I scroll down", "Scroll down please", "Just scroll down", "Down"):
            self.assertEqual(("browser_navigation", {"action": "scroll_down"}), self.parse(text), text)

    def test_persian_scroll_with_fillers(self):
        for text in ("یه کم برو پایین", "لطفا صفحه رو ببر پایین", "دوباره برو پایین", "بیا پایین"):
            self.assertEqual(("browser_navigation", {"action": "scroll_down"}), self.parse(text), text)
        self.assertEqual(("browser_navigation", {"action": "back"}), self.parse("یه صفحه برو عقب"))
        self.assertEqual(("browser_navigation", {"action": "top"}), self.parse("برو ابتدای صفحه"))

    def test_navigation_never_steals_app_or_file_commands(self):
        self.assertEqual(("open_app", {"app": "chrome"}), self.parse("Start Google Chrome"))
        self.assertEqual(("open_app", {"app": "text_editor"}), self.parse("start notepad"))
        self.assertEqual("open_file", self.parse("open the next file")[0])

    def test_confirmation_and_cancel_with_fillers(self):
        for text in ("yes please", "Sure, go ahead", "بله لطفا", "باشه"):
            self.assertTrue(self.parser.is_confirmation(text), text)
        for text in ("no thanks", "cancel that", "نه ممنون", "لغو کن"):
            self.assertTrue(self.parser.is_cancellation(text), text)


class SafetyTests(unittest.TestCase):
    def setUp(self):
        self.parser = CommandParser()

    def test_open_or_find_the_new_folder_never_creates(self):
        self.assertEqual("open_folder", self.parser.parse("open the new folder").intent)
        self.assertEqual("open_file", self.parser.parse("open the new file").intent)
        self.assertEqual("search", self.parser.parse("find the new folder").intent)
        self.assertEqual("open_folder", self.parser.parse("پوشه جدید رو باز کن").intent)

    def test_new_at_the_start_still_creates(self):
        command = self.parser.parse("New word document named chapter one")
        self.assertEqual("create_word_document", command.intent)
        self.assertEqual("chapter one", command.slots["name"])

    def test_delete_is_refused_explicitly(self):
        for text in ("Delete the report file", "remove the photos folder", "فایل گزارش رو پاک کن", "پوشه عکس ها رو حذف کن"):
            self.assertEqual("delete_unsupported", self.parser.parse(text).intent, text)

    def test_app_words_are_not_domains(self):
        self.assertNotEqual("open_website", self.parser.parse("open note app").intent)
        self.assertNotEqual("open_website", self.parser.parse("open the camera app").intent)
        self.assertEqual(("open_folder", "me"), (self.parser.parse("open the me folder").intent,
                                                 self.parser.parse("open the me folder").slots["query"]))

    def test_spoken_or_written_domains_are_websites(self):
        for text, target in (("Visit github.com", "github com"), ("go to github dot com", "github com"),
                             ("Visit Instagram.com", "instagram com")):
            command = self.parser.parse(text)
            self.assertEqual("open_website", command.intent, text)
            self.assertEqual(target, command.slots["target"].replace(" dot ", " "), text)

    def test_known_site_names(self):
        self.assertEqual({"target": "instagram"}, self.parser.parse("Go to Instagram").slots)
        self.assertEqual("open_website", self.parser.parse("برو به سایت اینستاگرام").intent)

    def test_sequence_keeps_a_domain_step(self):
        command = self.parser.parse("Open Chrome and go to github.com")
        self.assertEqual("sequence", command.intent)
        self.assertEqual(["open_app", "open_website"], [s.intent for s in command.steps])


class PersianSlotTests(unittest.TestCase):
    def setUp(self):
        self.parser = CommandParser()

    def test_letter_word_is_not_a_rename(self):
        # «نامه» (letter) contains «نام» (name); it used to trigger rename.
        command = self.parser.parse("سند پایان نامه رو باز کن")
        self.assertEqual(("open_file", "پایان نامه"), (command.intent, command.slots["query"]))
        self.assertEqual("search", self.parser.parse("فایل پایان نامه رو پیدا کن").intent)

    def test_persian_save_as_is_reported_not_renamed(self):
        self.assertEqual("save_as_unsupported",
                         self.parser.parse("این فایل رو با اسم گزارش روی دسکتاپ ذخیره کن").intent)

    def test_word_file_named_in_persian_opens_the_file_not_word(self):
        command = self.parser.parse("فایل تست شش ورد رو باز کن")
        self.assertEqual("open_file", command.intent)

    def test_object_marker_is_stripped_from_search_query(self):
        command = self.parser.parse("گزارش هفتگی رو برام پیدا کن")
        self.assertEqual({"query": "گزارش هفتگی"}, command.slots)

    def test_rename_new_name_without_preposition(self):
        self.assertEqual("نسخه دوم", self.parser.parse("اسمش رو عوض کن به نسخه دوم").slots["new_name"])
        self.assertEqual("نسخه تمیز", self.parser.parse("اسم جدیدش بشه نسخه تمیز").slots["new_name"])

    def test_second_person_create_verb(self):
        command = self.parser.parse("میشه یه فایل ورد به اسم جزوه بسازی")
        self.assertEqual(("create_word_document", "جزوه"), (command.intent, command.slots["name"]))

    def test_bare_app_name_opens_it(self):
        self.assertEqual({"app": "calculator"}, self.parser.parse("ماشین حساب").slots)


class WebSearchTests(unittest.TestCase):
    def test_search_on_a_browser_is_a_web_search(self):
        parser = CommandParser()
        command = parser.parse("Search for GitHub on Chrome")
        self.assertEqual(("web_search", {"query": "github", "app": "chrome"}), (command.intent, command.slots))
        self.assertEqual("search", parser.parse("search for the report").intent)


if __name__ == "__main__":
    unittest.main()
