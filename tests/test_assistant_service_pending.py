"""Pending-question behaviour: a question the assistant asked must never turn
into a wrong action, and must not trap the user either."""

import tempfile
import unittest
from pathlib import Path

from guya.assistant import context as context_module
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

    def browser_control(self, action):
        self.calls.append(("browser_control", action))
        return self._success(f"Browser {action}.", f"مرورگر {action}.")

    def speak(self, text, language="en"):
        pass


class PendingQuestionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.service = AssistantService(roots=[self.root], default_directory=self.root, platform="darwin")
        self.service.actions = FakeDesktopActions(roots=[self.root], default_directory=self.root)

    def tearDown(self):
        self.temp.cleanup()

    def test_new_command_replaces_a_pending_open_question(self):
        created = self.service.handle("create a word file named memo")
        self.assertEqual("needs_confirmation", created.status)
        response = self.service.handle("open calculator")
        self.assertEqual("success", response.status)
        self.assertEqual([("open_app", "calculator")], self.service.actions.calls)
        self.assertIsNone(self.service.context.pending_command)

    def test_open_it_answers_the_open_question(self):
        self.service.handle("create a text file named notes")
        response = self.service.handle("open it")
        self.assertEqual("success", response.status)
        self.assertEqual("open_path", self.service.actions.calls[0][0])

    def test_unrelated_chatter_keeps_the_question(self):
        self.service.handle("create a folder named photos")
        response = self.service.handle("hmm what was that")
        self.assertEqual("needs_confirmation", response.status)
        self.assertEqual([], self.service.actions.calls)
        self.assertIsNotNone(self.service.context.pending_command)

    def test_pending_rename_expires(self):
        (self.root / "stale.txt").touch()
        self.service.context.remember(self.root / "stale.txt")
        self.assertEqual("needs_confirmation", self.service.handle("rename it to renamed later").status)
        self.service.context.pending_since -= context_module.PENDING_TIMEOUT_SEC + 1
        response = self.service.handle("yes")
        self.assertEqual("error", response.status)
        self.assertTrue((self.root / "stale.txt").exists())
        self.assertFalse((self.root / "renamed later.txt").exists())

    def test_yes_is_not_accepted_as_a_new_name(self):
        (self.root / "draft.txt").touch()
        self.service.context.remember(self.root / "draft.txt")
        self.assertEqual("needs_input", self.service.handle("rename it").status)
        response = self.service.handle("yes")
        self.assertEqual("needs_input", response.status)
        self.assertTrue((self.root / "draft.txt").exists())
        self.assertFalse((self.root / "yes.txt").exists())

    def test_new_command_replaces_a_pending_selection(self):
        (self.root / "report a.docx").touch()
        (self.root / "report b.docx").touch()
        response = self.service.handle("open report docs")
        self.assertEqual("needs_selection", response.status)
        response = self.service.handle("scroll down")
        self.assertEqual("success", response.status)
        self.assertEqual([("browser_control", "scroll_down")], self.service.actions.calls)
        self.assertEqual([], self.service.context.pending_options)


class SafetyResponseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.service = AssistantService(roots=[self.root], default_directory=self.root, platform="darwin")
        self.service.actions = FakeDesktopActions(roots=[self.root], default_directory=self.root)

    def tearDown(self):
        self.temp.cleanup()

    def test_delete_is_refused_with_a_clear_message(self):
        (self.root / "report.docx").touch()
        for text in ("delete the report file", "فایل گزارش رو پاک کن"):
            response = self.service.handle(text)
            self.assertEqual("error", response.status, text)
            self.assertIn("حذف" if response.language == "fa" else "never deletes", response.message)
        self.assertTrue((self.root / "report.docx").exists())
        self.assertEqual([], self.service.actions.calls)

    def test_sequence_with_a_disallowed_step_runs_nothing(self):
        response = self.service.handle("open chrome then rename report to final")
        self.assertEqual("error", response.status)
        self.assertEqual([], self.service.actions.calls)
        self.assertIn("nothing was done", response.message)


if __name__ == "__main__":
    unittest.main()
