import sys
import unittest


@unittest.skipUnless(sys.platform == "darwin", "macOS-only hotkey test")
class MacOSHotkeyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from guya import platform_macos

        if not platform_macos._PYNPUT_OK:
            raise unittest.SkipTest("pynput is not installed")
        cls.adapter = platform_macos
        cls.keyboard = platform_macos._pynput_kb

    def test_dictation_uses_right_option_only(self):
        self.assertTrue(self.adapter._is_hotkey(self.keyboard.Key.alt_r))
        self.assertFalse(self.adapter._is_hotkey(self.keyboard.Key.alt))

    def test_assistant_uses_right_command(self):
        self.assertTrue(self.adapter._is_assistant_hotkey(self.keyboard.Key.cmd_r))
        self.assertFalse(self.adapter._is_assistant_hotkey(self.keyboard.Key.cmd))

    def test_old_right_control_key_remains_compatible(self):
        self.assertTrue(self.adapter._is_assistant_hotkey(self.keyboard.Key.ctrl_r))


if __name__ == "__main__":
    unittest.main()
