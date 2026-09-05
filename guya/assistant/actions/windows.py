"""Windows application launching and spoken feedback."""

import ctypes
import os
import subprocess
import time
from pathlib import Path
from urllib.parse import quote_plus

import pyperclip

from .common import SafeDesktopActions


class WindowsActions(SafeDesktopActions):
    BROWSER_WINDOW_CLASSES = {"Chrome_WidgetWin_1", "MozillaWindowClass"}
    BROWSER_KEYS = {
        "scroll_up": 0x21,     # Page Up
        "scroll_down": 0x22,   # Page Down
        "bottom": 0x23,        # End
        "top": 0x24,           # Home
        "back": 0xA6,          # Browser Back
        "forward": 0xA7,       # Browser Forward
    }
    APP_CANDIDATES = {
        "word": ("winword.exe",),
        "text_editor": ("notepad.exe",),
        "calculator": ("calc.exe",),
        "file_manager": ("explorer.exe",),
        "browser": ("msedge.exe", "chrome.exe"),
        "chrome": ("chrome.exe",),
        "safari": (),
        "pages": (),
    }

    def open_path(self, path: Path):
        path = Path(path).expanduser().resolve()
        if not self._is_allowed(path) or not path.exists():
            return self._failure(
                "That file or folder is not available.",
                "این فایل یا پوشه در دسترس نیست.",
            )
        try:
            os.startfile(str(path))  # type: ignore[attr-defined]
            return self._success(
                f"Opened {path.name}.",
                f"{path.name} باز شد.",
                path,
            )
        except Exception as exc:
            return self._failure(
                f"Could not open {path.name}: {exc}",
                f"باز کردن {path.name} ممکن نشد: {exc}",
            )

    def open_app(self, app: str):
        for executable in self.APP_CANDIDATES.get(app, ()):
            try:
                os.startfile(executable)  # type: ignore[attr-defined]
                return self._success(
                    f"Opened {app.replace('_', ' ')}.",
                    f"برنامه {app.replace('_', ' ')} باز شد.",
                )
            except Exception:
                try:
                    subprocess.Popen(
                        [executable],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    return self._success(
                        f"Opened {app.replace('_', ' ')}.",
                        f"برنامه {app.replace('_', ' ')} باز شد.",
                    )
                except Exception:
                    continue
        return self._failure(
            "That application is not installed or could not be opened.",
            "این برنامه نصب نیست یا باز کردن آن ممکن نشد.",
        )

    def save_current(self):
        if self._send_shortcut(ord("S")):
            time.sleep(0.25)
            return self._success(
                "Saved the current file.",
                "فایل فعلی ذخیره شد.",
            )
        return self._failure(
            "Could not send Save to the active application.",
            "ارسال دستور ذخیره به برنامه فعال ممکن نشد.",
        )

    def close_current(self):
        if self._send_shortcut(ord("W")):
            return self._success(
                "Closed the current window. If it has unsaved changes, the application may ask you what to do.",
                "پنجره فعلی بسته شد. اگر تغییر ذخیره‌نشده‌ای باشد، برنامه از شما سؤال می‌کند.",
            )
        return self._failure(
            "Could not close the active window.",
            "بستن پنجره فعال ممکن نشد.",
        )

    def search_web(self, query: str, app=None):
        query = (query or "").strip()
        if not query:
            return self._failure("The web search is empty.", "عبارت جستجوی وب خالی است.")
        url = f"https://www.google.com/search?q={quote_plus(query)}"
        if self._open_browser_url(url, app=app):
            return self._success(
                f"Searched the web for {query}.",
                f"عبارت {query} در وب جستجو شد.",
            )
        return self._failure(
            "Could not open the web search.",
            "باز کردن جستجوی وب ممکن نشد.",
        )

    def open_website(self, target: str, app=None):
        url = self.safe_website_url(target)
        if not url:
            return self._failure(
                "Please say a known website name or a complete domain, such as YouTube or github dot com.",
                "لطفاً نام یک سایت شناخته‌شده یا دامنه کامل، مثل یوتیوب یا github.com را بگویید.",
            )
        if self._open_browser_url(url, app=app):
            return self._success(
                f"Opened {url}.",
                f"سایت {url} باز شد.",
            )
        return self._failure(
            "Could not open that website.",
            "باز کردن این سایت ممکن نشد.",
        )

    def _open_browser_url(self, url: str, app=None) -> bool:
        hwnd = self._target_browser_hwnd()
        if hwnd is not None and app in (None, "browser", "chrome"):
            if self._navigate_current_browser(hwnd, url):
                return True
        if app in ("chrome", "browser"):
            for executable in self.APP_CANDIDATES.get(app, ()):
                try:
                    subprocess.Popen(
                        [executable, url],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    return True
                except Exception:
                    continue
        try:
            os.startfile(url)  # type: ignore[attr-defined]
            return True
        except Exception:
            return False

    def _navigate_current_browser(self, hwnd: int, url: str) -> bool:
        try:
            previous_clipboard = pyperclip.paste()
        except Exception:
            previous_clipboard = None
        try:
            pyperclip.copy(url)
            return (
                self._send_key_to_window(hwnd, ord("L"), modifier=0x11)
                and self._send_key_to_window(hwnd, ord("V"), modifier=0x11)
                and self._send_key_to_window(hwnd, 0x0D)
            )
        except Exception:
            return False
        finally:
            time.sleep(0.20)
            if previous_clipboard is not None:
                try:
                    pyperclip.copy(previous_clipboard)
                except Exception:
                    pass

    def browser_control(self, action: str):
        key_code = self.BROWSER_KEYS.get(action)
        if key_code is None:
            return self._failure(
                "That browser movement is not supported.",
                "این حرکت مرورگر پشتیبانی نمی‌شود.",
            )
        hwnd = self._target_browser_hwnd()
        if hwnd is None:
            return self._failure(
                "Focus Chrome, Edge, or Firefox, then try the command again.",
                "ابتدا کروم، اج یا فایرفاکس را فعال کنید و دوباره دستور را بگویید.",
            )
        if not self._send_key_to_window(hwnd, key_code):
            return self._failure(
                "Could not control the active browser.",
                "کنترل مرورگر فعال ممکن نشد.",
            )
        messages = {
            "scroll_up": ("Scrolled up.", "صفحه به بالا رفت."),
            "scroll_down": ("Scrolled down.", "صفحه به پایین رفت."),
            "top": ("Moved to the top of the page.", "به ابتدای صفحه رفت."),
            "bottom": ("Moved to the bottom of the page.", "به انتهای صفحه رفت."),
            "back": ("Went back one page.", "یک صفحه به عقب رفت."),
            "forward": ("Went forward one page.", "یک صفحه به جلو رفت."),
        }
        message_en, message_fa = messages[action]
        return self._success(message_en, message_fa)

    def _target_browser_hwnd(self):
        try:
            hwnd = int(self.target_app or 0)
            user32 = ctypes.windll.user32
            if hwnd <= 0 or not user32.IsWindow(hwnd):
                return None
            class_name = ctypes.create_unicode_buffer(256)
            if not user32.GetClassNameW(hwnd, class_name, len(class_name)):
                return None
            if class_name.value not in self.BROWSER_WINDOW_CLASSES:
                return None
            return hwnd
        except Exception:
            return None

    @staticmethod
    def _send_key_to_window(
        hwnd: int,
        key_code: int,
        modifier: int = None,
    ) -> bool:
        """Refocus the captured browser and refuse a global key if that fails."""
        try:
            user32 = ctypes.windll.user32
            user32.SetForegroundWindow(hwnd)
            time.sleep(0.05)
            if int(user32.GetForegroundWindow()) != int(hwnd):
                return False
            key_up = 0x0002
            if modifier is not None:
                user32.keybd_event(modifier, 0, 0, 0)
            user32.keybd_event(key_code, 0, 0, 0)
            user32.keybd_event(key_code, 0, key_up, 0)
            if modifier is not None:
                user32.keybd_event(modifier, 0, key_up, 0)
            return True
        except Exception:
            return False

    def _send_shortcut(self, key_code: int) -> bool:
        """Ctrl+<key> to the window captured at hotkey press.

        A global keybd_event used to be sent to whatever was in front, so
        Save/Close could land in the wrong window (or in Guya). Now the
        captured HWND is refocused first and the key is refused if that fails.
        """
        try:
            hwnd = int(self.target_app or 0)
        except (TypeError, ValueError):
            hwnd = 0
        if hwnd <= 0:
            return False
        try:
            if not ctypes.windll.user32.IsWindow(hwnd):
                return False
        except Exception:
            return False
        return self._send_key_to_window(hwnd, key_code, modifier=0x11)

    def speak(self, text: str, language: str = "en") -> None:
        if not text:
            return
        # The text is passed on stdin, never on the command line: `-Command`
        # treats everything after the script as more script, so `$args` was
        # always empty and nothing was ever spoken.
        lang = "fa" if language == "fa" else "en"
        script = (
            "Add-Type -AssemblyName System.Speech; "
            "$voice = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            f"if ('{lang}' -eq 'fa') {{ "
            "$candidate = $voice.GetInstalledVoices() | "
            "Where-Object { $_.VoiceInfo.Culture.Name -like 'fa*' } | "
            "Select-Object -First 1; "
            "if (-not $candidate) { exit 0 }; "
            "$voice.SelectVoice($candidate.VoiceInfo.Name) }; "
            "[Console]::InputEncoding = [System.Text.Encoding]::UTF8; "
            "$msg = [Console]::In.ReadToEnd(); "
            "$voice.Speak($msg)"
        )
        self.stop_speaking()
        try:
            self._speech_process = subprocess.Popen(
                ["powershell", "-NoProfile", "-Command", script],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            try:
                self._speech_process.stdin.write(text.encode("utf-8"))
                self._speech_process.stdin.close()
            except Exception:
                pass
        except Exception:
            self._speech_process = None

    def stop_speaking(self) -> None:
        process = getattr(self, "_speech_process", None)
        if process is None:
            return
        try:
            if process.poll() is None:
                process.terminate()
        except Exception:
            pass
        finally:
            self._speech_process = None
