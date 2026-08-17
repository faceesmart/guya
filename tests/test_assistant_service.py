import tempfile
import unittest
from pathlib import Path

from guya.assistant.actions.common import SafeDesktopActions
from guya.assistant.service import AssistantService


class FakeDesktopActions(SafeDesktopActions):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.calls = []

    def open_path(self, path):
        path = Path(path)
        self.calls.append(("open_path", str(path)))
        return self._success(f"Opened {path.name}.", f"{path.name} باز شد.", path)

    def open_app(self, app):
        self.calls.append(("open_app", app))
        return self._success(f"Opened {app}.", f"{app} باز شد.")

    def save_current(self):
        self.calls.append(("save_current", None))
        return self._success("Saved.", "ذخیره شد.")

    def close_current(self):
        self.calls.append(("close_current", None))
        return self._success("Closed.", "بسته شد.")

    def search_web(self, query, app=None):
        self.calls.append(("search_web", query, app))
        return self._success(f"Searched for {query}.", f"{query} جستجو شد.")

    def open_website(self, target, app=None):
        self.calls.append(("open_website", target, app))
        return self._success(f"Opened {target}.", f"{target} باز شد.")

    def browser_control(self, action):
        self.calls.append(("browser_control", action))
        return self._success(f"Browser {action}.", f"مرورگر {action}.")

    def speak(self, text, language="en"):
        pass


class AssistantServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.service = AssistantService(
            roots=[self.root],
            default_directory=self.root,
            platform="darwin",
        )
        self.service.actions = FakeDesktopActions(
            roots=[self.root],
            default_directory=self.root,
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_create_then_contextual_rename_requires_confirmation(self):
        created = self.service.handle("create a text file named notes")
        self.assertEqual("needs_confirmation", created.status)
        self.assertEqual(self.root / "notes.txt", created.path)
        left_closed = self.service.handle("no")
        self.assertEqual("cancelled", left_closed.status)

        proposed = self.service.handle("rename it to university notes")
        self.assertEqual("needs_confirmation", proposed.status)
        self.assertTrue((self.root / "notes.txt").exists())

        confirmed = self.service.handle("yes")
        self.assertTrue(confirmed.success)
        self.assertEqual(self.root / "university notes.txt", confirmed.path)
        self.assertFalse((self.root / "notes.txt").exists())

    def test_created_document_opens_only_after_confirmation(self):
        created = self.service.handle("create a word file named report")

        self.assertEqual("needs_confirmation", created.status)
        self.assertTrue((self.root / "report.docx").exists())
        self.assertEqual([], self.service.actions.calls)

        opened = self.service.handle("yes")

        self.assertTrue(opened.success)
        self.assertEqual(self.root / "report.docx", opened.path)
        self.assertEqual(
            [("open_path", str(self.root / "report.docx"))],
            self.service.actions.calls,
        )

    def test_created_document_can_be_left_closed(self):
        created = self.service.handle("create a word file named notes")
        self.assertEqual("needs_confirmation", created.status)

        declined = self.service.handle("no")

        self.assertEqual("cancelled", declined.status)
        self.assertTrue((self.root / "notes.docx").exists())
        self.assertEqual([], self.service.actions.calls)

    def test_cancelled_rename_changes_nothing(self):
        item = self.root / "report.txt"
        item.touch()
        self.service.context.remember(item)
        proposed = self.service.handle("change its name to final")
        self.assertEqual("needs_confirmation", proposed.status)
        cancelled = self.service.handle("no")
        self.assertEqual("cancelled", cancelled.status)
        self.assertTrue(item.exists())

    def test_can_answer_rename_name_in_a_second_utterance(self):
        item = self.root / "report.txt"
        item.touch()
        self.service.context.remember(item)
        question = self.service.handle("اسمش رو عوض کن")
        self.assertEqual("needs_input", question.status)
        confirmation = self.service.handle("اسمش رو بذار گزارش نهایی")
        self.assertEqual("needs_confirmation", confirmation.status)
        renamed = self.service.handle("بله")
        self.assertTrue(renamed.success)
        self.assertEqual(self.root / "گزارش نهایی.txt", renamed.path)

    def test_pending_rename_strips_natural_answer_prefix(self):
        item = self.root / "test1.docx"
        item.touch()
        self.service.context.remember(item)
        question = self.service.handle("rename it")
        self.assertEqual("needs_input", question.status)
        confirmation = self.service.handle("The new name should be text2")
        self.assertEqual("needs_confirmation", confirmation.status)
        self.assertEqual(
            "text2",
            self.service.context.pending_command.slots["new_name"],
        )

    def test_search_then_open_it_uses_context(self):
        item = self.root / "project report.txt"
        item.touch()
        found = self.service.handle("find project report")
        self.assertTrue(found.success)
        opened = self.service.handle("open it")
        self.assertTrue(opened.success)
        self.assertEqual(item, opened.path)

    def test_open_spoken_number_and_docx_homophone(self):
        item = self.root / "test6.docx"
        item.touch()

        response = self.service.handle("open test six docks")

        self.assertTrue(response.success)
        self.assertEqual(item, response.path)
        self.assertEqual([("open_path", str(item))], self.service.actions.calls)

    def test_find_and_open_is_one_open_request(self):
        item = self.root / "text6.docx"
        item.touch()

        response = self.service.handle("find and open text 6 docs file")

        self.assertTrue(response.success)
        self.assertEqual(item, response.path)

    def test_open_it_again_uses_recent_context(self):
        item = self.root / "test6.docx"
        item.touch()
        self.service.context.remember(item)

        response = self.service.handle("open it again")

        self.assertTrue(response.success)
        self.assertEqual(item, response.path)

    def test_ambiguous_results_wait_for_spoken_choice(self):
        first_dir = self.root / "first"
        second_dir = self.root / "second"
        first_dir.mkdir()
        second_dir.mkdir()
        first = first_dir / "report.docx"
        second = second_dir / "report.docx"
        first.touch()
        second.touch()

        question = self.service.handle("open report docs")

        self.assertEqual("needs_selection", question.status)
        self.assertEqual([first, second], question.options)
        self.assertEqual([], self.service.actions.calls)

        opened = self.service.handle("second")

        self.assertTrue(opened.success)
        self.assertEqual(second, opened.path)
        self.assertEqual([("open_path", str(second))], self.service.actions.calls)
        self.assertEqual([], self.service.context.pending_options)

    def test_ambiguous_results_can_be_cancelled(self):
        for folder in ("first", "second"):
            directory = self.root / folder
            directory.mkdir()
            (directory / "report.docx").touch()

        question = self.service.handle("find report docs")
        self.assertEqual("needs_selection", question.status)

        cancelled = self.service.handle("cancel")

        self.assertEqual("cancelled", cancelled.status)
        self.assertEqual([], self.service.actions.calls)

    def test_ambiguous_result_can_be_selected_by_filename(self):
        alpha = self.root / "report alpha.docx"
        beta = self.root / "report beta.docx"
        alpha.touch()
        beta.touch()

        question = self.service.handle("open report docs")
        self.assertEqual("needs_selection", question.status)

        opened = self.service.handle("open report beta")

        self.assertTrue(opened.success)
        self.assertEqual(beta, opened.path)

    def test_unrecognized_command_does_not_run_any_action(self):
        response = self.service.handle("send all of my files to the internet")
        self.assertEqual("error", response.status)
        self.assertEqual([], list(self.root.iterdir()))

    def test_system_folder_cannot_open_unrelated_short_name(self):
        unrelated = self.root / "m"
        unrelated.mkdir()

        response = self.service.handle("open the system folder")

        self.assertEqual("error", response.status)
        self.assertEqual([], self.service.actions.calls)

    def test_generic_rename_target_is_rejected(self):
        (self.root / "A").mkdir()

        response = self.service.handle(
            "rename a file to an existing file name"
        )

        self.assertEqual("error", response.status)
        self.assertEqual([], self.service.actions.calls)
        self.assertIsNone(self.service.context.pending_command)

    def test_close_command_is_supported_and_never_loses_an_app_slot(self):
        self.service.set_target_app("com.microsoft.Word")
        response = self.service.handle("close calculator")
        self.assertTrue(response.success)
        self.assertEqual("com.microsoft.Word", self.service.actions.target_app)
        self.assertEqual([("close_current", None)], self.service.actions.calls)

    def test_save_then_close_sequence_runs_in_order(self):
        response = self.service.handle(
            "save the current file and close the current window"
        )
        self.assertTrue(response.success)
        self.assertEqual(
            [("save_current", None), ("close_current", None)],
            self.service.actions.calls,
        )

    def test_browser_search_sequence_is_limited_and_ordered(self):
        response = self.service.handle("open Chrome, then search for YouTube")
        self.assertTrue(response.success)
        self.assertEqual(
            [
                ("open_app", "chrome"),
                ("search_web", "youtube", "chrome"),
            ],
            self.service.actions.calls,
        )

    def test_browser_navigation_routes_only_a_whitelisted_action(self):
        response = self.service.handle("scroll down")
        self.assertTrue(response.success)
        self.assertEqual(
            [("browser_control", "scroll_down")],
            self.service.actions.calls,
        )

    def test_direct_website_opening_is_routed(self):
        response = self.service.handle("visit github.com")
        self.assertTrue(response.success)
        self.assertEqual(
            [("open_website", "github com", None)],
            self.service.actions.calls,
        )

    def test_browser_then_website_sequence_is_ordered(self):
        response = self.service.handle("open Chrome then go to YouTube")
        self.assertTrue(response.success)
        self.assertEqual(
            [
                ("open_app", "chrome"),
                ("open_website", "youtube", "chrome"),
            ],
            self.service.actions.calls,
        )

    def test_save_as_explains_the_current_mvp_limit(self):
        response = self.service.handle(
            "save this file as Guya Report on the Desktop"
        )
        self.assertEqual("error", response.status)
        self.assertIn("Save As", response.message)
        self.assertEqual([], self.service.actions.calls)


if __name__ == "__main__":
    unittest.main()
