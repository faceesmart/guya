import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, call, patch

from guya.assistant.actions.common import SafeDesktopActions


class FakeDesktopActions(SafeDesktopActions):
    def open_path(self, path):
        path = Path(path)
        return self._success(f"Opened {path.name}.", f"{path.name} باز شد.", path)

    def open_app(self, app):
        return self._success(f"Opened {app}.", f"{app} باز شد.")


class AssistantActionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.actions = FakeDesktopActions(
            roots=[self.root],
            default_directory=self.root,
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_creates_valid_empty_docx_without_extra_dependency(self):
        outcome = self.actions.create_word_document("guya")
        self.assertTrue(outcome.success)
        self.assertEqual("guya.docx", outcome.path.name)
        self.assertTrue(zipfile.is_zipfile(outcome.path))
        with zipfile.ZipFile(outcome.path) as archive:
            self.assertIn("word/document.xml", archive.namelist())
            xml = archive.read("word/document.xml")
            self.assertIn(b"<w:document", xml)

    def test_search_sees_new_files_immediately(self):
        self.assertEqual([], self.actions.search("fresh"))
        fresh = self.root / "fresh report.txt"
        fresh.write_text("hello", encoding="utf-8")
        self.assertEqual(fresh, self.actions.find_one("fresh", kind="file"))

    def test_generic_voice_query_cannot_select_single_letter_item(self):
        unsafe = self.root / "A"
        unsafe.mkdir()

        self.assertEqual([], self.actions.search("a file"))
        self.assertEqual([], self.actions.search("system", kind="folder"))

    def test_search_does_not_enter_application_packages(self):
        package = self.root / "Example.app"
        internal = package / "Contents" / "Frameworks" / "Secret.framework"
        internal.mkdir(parents=True)
        (internal / "system report.txt").touch()

        self.assertEqual([], self.actions.search("system report", kind="file"))

    def test_spoken_number_and_extension_homophone_find_real_docx(self):
        expected = self.root / "test6.docx"
        expected.touch()
        nearby = self.root / "test6 notes.docx"
        nearby.touch()

        with self.assertLogs("Guya", level="INFO") as captured:
            matches = self.actions.search_matches("test six docks", kind="file")

        self.assertEqual(expected, matches[0].path)
        self.assertTrue(matches[0].exact)
        self.assertEqual(1.0, matches[0].score)
        diagnostic = "\n".join(captured.output)
        self.assertIn('"canonical": "test6docx"', diagnostic)
        self.assertIn('"score": 1.0', diagnostic)

    def test_identical_names_in_different_folders_are_both_returned(self):
        first_dir = self.root / "first"
        second_dir = self.root / "second"
        first_dir.mkdir()
        second_dir.mkdir()
        (first_dir / "report.docx").touch()
        (second_dir / "report.docx").touch()

        matches = self.actions.search_matches("report docs", kind="file")

        self.assertEqual(2, len(matches))
        self.assertTrue(all(match.exact for match in matches))

    def test_rename_preserves_extension(self):
        source = self.root / "old report.docx"
        source.touch()
        outcome = self.actions.rename(source, "final report")
        self.assertTrue(outcome.success)
        self.assertEqual(self.root / "final report.docx", outcome.path)

    def test_rename_never_overwrites(self):
        source = self.root / "first.txt"
        destination = self.root / "second.txt"
        source.write_text("first", encoding="utf-8")
        destination.write_text("second", encoding="utf-8")
        outcome = self.actions.rename(source, "second")
        self.assertFalse(outcome.success)
        self.assertEqual("first", source.read_text(encoding="utf-8"))
        self.assertEqual("second", destination.read_text(encoding="utf-8"))

    def test_path_outside_allowed_roots_is_rejected(self):
        with tempfile.TemporaryDirectory() as other:
            outside = Path(other) / "private.txt"
            outside.touch()
            outcome = self.actions.rename(outside, "changed")
            self.assertFalse(outcome.success)
            self.assertTrue(outside.exists())

    def test_spoken_website_names_and_domains_resolve_to_https(self):
        examples = {
            "youtube": "https://www.youtube.com",
            "یوتیوب": "https://www.youtube.com",
            "github dot com": "https://github.com",
            "ut ac ir": "https://ut.ac.ir",
            "example com": "https://example.com",
        }
        for target, expected in examples.items():
            with self.subTest(target=target):
                self.assertEqual(expected, self.actions.safe_website_url(target))

    def test_unsafe_or_incomplete_website_targets_are_rejected(self):
        for target in (
            "site five",
            "the fifth result",
            "javascript alert",
            "file users private",
            "unknown website",
            "123",
        ):
            with self.subTest(target=target):
                self.assertIsNone(self.actions.safe_website_url(target))

    @unittest.skipUnless(sys.platform == "darwin", "macOS-only shortcut safety test")
    def test_macos_shortcuts_can_never_target_guya_itself(self):
        from guya.assistant.actions.macos import MacOSActions

        actions = MacOSActions(roots=[self.root], default_directory=self.root)
        for bundle_id in ("com.guya.app", "org.python.python"):
            with self.subTest(bundle_id=bundle_id):
                actions.set_target_app(bundle_id)
                self.assertIsNone(actions._target_pid())
                self.assertFalse(actions._send_shortcut("w"))

    @unittest.skipUnless(sys.platform == "darwin", "macOS-only shortcut routing test")
    def test_macos_shortcut_is_posted_only_to_captured_target_pid(self):
        from guya.assistant.actions import macos

        actions = macos.MacOSActions(
            roots=[self.root],
            default_directory=self.root,
        )
        actions.set_target_app("com.microsoft.Word")

        running_app = MagicMock()
        running_app.bundleIdentifier.return_value = "com.microsoft.Word"
        running_app.processIdentifier.return_value = 4242
        workspace = MagicMock()
        workspace.runningApplications.return_value = [running_app]

        class FakeNSWorkspace:
            @staticmethod
            def sharedWorkspace():
                return workspace

        events = [object(), object(), object(), object()]
        with (
            patch.object(
                macos,
                "NSWorkspace",
                FakeNSWorkspace,
            ),
            patch.object(
                macos,
                "CGEventCreateKeyboardEvent",
                side_effect=events,
            ),
            patch.object(macos, "CGEventSetFlags") as set_flags,
            patch.object(macos, "CGEventPostToPid") as post_to_pid,
            patch.object(macos.time, "sleep"),
        ):
            self.assertTrue(actions._send_shortcut("s"))

        self.assertEqual(4, set_flags.call_count)
        self.assertEqual(
            [4242, 4242, 4242, 4242],
            [call.args[0] for call in post_to_pid.call_args_list],
        )

    @unittest.skipUnless(sys.platform == "darwin", "macOS-only browser routing test")
    def test_macos_browser_navigation_targets_only_the_captured_browser(self):
        from guya.assistant.actions import macos

        actions = macos.MacOSActions(
            roots=[self.root],
            default_directory=self.root,
        )
        actions.set_target_app("com.google.Chrome")

        running_app = MagicMock()
        running_app.bundleIdentifier.return_value = "com.google.Chrome"
        running_app.processIdentifier.return_value = 5252
        workspace = MagicMock()
        workspace.runningApplications.return_value = [running_app]

        class FakeNSWorkspace:
            @staticmethod
            def sharedWorkspace():
                return workspace

        events = [object(), object()]
        with (
            patch.object(macos, "NSWorkspace", FakeNSWorkspace),
            patch.object(
                macos,
                "CGEventCreateKeyboardEvent",
                side_effect=events,
            ),
            patch.object(macos, "CGEventSetFlags"),
            patch.object(macos, "CGEventPostToPid") as post_to_pid,
            patch.object(macos.time, "sleep"),
        ):
            outcome = actions.browser_control("scroll_down")

        self.assertTrue(outcome.success)
        self.assertEqual(
            [5252, 5252],
            [call.args[0] for call in post_to_pid.call_args_list],
        )

        actions.set_target_app("com.microsoft.Word")
        refused = actions.browser_control("scroll_down")
        self.assertFalse(refused.success)

    @unittest.skipUnless(sys.platform == "darwin", "macOS-only current-tab test")
    def test_macos_website_reuses_current_tab_and_restores_clipboard(self):
        from guya.assistant.actions import macos

        actions = macos.MacOSActions(
            roots=[self.root],
            default_directory=self.root,
        )
        actions.set_target_app("com.google.Chrome")
        with (
            patch.object(
                actions,
                "_send_key_code",
                side_effect=(True, True, True),
            ) as send_key,
            patch.object(macos.pyperclip, "paste", return_value="keep me"),
            patch.object(macos.pyperclip, "copy") as clipboard_copy,
            patch.object(macos.subprocess, "run") as subprocess_run,
            patch.object(macos.time, "sleep"),
        ):
            outcome = actions.open_website("youtube")

        self.assertTrue(outcome.success)
        self.assertEqual(3, send_key.call_count)
        self.assertEqual(
            [
                actions.ADDRESS_KEY_CODE,
                actions.PASTE_KEY_CODE,
                actions.RETURN_KEY_CODE,
            ],
            [call.args[0] for call in send_key.call_args_list],
        )
        self.assertEqual(
            [
                call("https://www.youtube.com"),
                call("keep me"),
            ],
            clipboard_copy.call_args_list,
        )
        subprocess_run.assert_not_called()

    def test_windows_current_tab_navigation_restores_clipboard(self):
        from guya.assistant.actions import windows

        actions = windows.WindowsActions(
            roots=[self.root],
            default_directory=self.root,
        )
        with (
            patch.object(
                actions,
                "_send_key_to_window",
                side_effect=(True, True, True),
            ) as send_key,
            patch.object(windows.pyperclip, "paste", return_value="keep me"),
            patch.object(windows.pyperclip, "copy") as clipboard_copy,
            patch.object(windows.time, "sleep"),
        ):
            self.assertTrue(
                actions._navigate_current_browser(
                    1234,
                    "https://www.youtube.com",
                )
            )

        self.assertEqual(
            [ord("L"), ord("V"), 0x0D],
            [call.args[1] for call in send_key.call_args_list],
        )
        self.assertEqual(
            [
                call("https://www.youtube.com"),
                call("keep me"),
            ],
            clipboard_copy.call_args_list,
        )

    @unittest.skipUnless(sys.platform == "darwin", "macOS-only speech test")
    def test_macos_never_uses_arabic_voice_for_persian(self):
        from guya.assistant.actions import macos

        actions = macos.MacOSActions(
            roots=[self.root],
            default_directory=self.root,
        )
        with patch.object(macos.subprocess, "Popen") as popen:
            actions.speak("فایل ساخته شد", "fa")

        popen.assert_not_called()

    @unittest.skipUnless(sys.platform == "darwin", "macOS-only speech test")
    def test_macos_spoken_feedback_can_be_interrupted(self):
        from guya.assistant.actions import macos

        actions = macos.MacOSActions(
            roots=[self.root],
            default_directory=self.root,
        )
        process = MagicMock()
        process.poll.return_value = None
        with patch.object(macos.subprocess, "Popen", return_value=process):
            actions.speak("Opened report", "en")
            actions.stop_speaking()

        process.terminate.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
