"""macOS application launching and spoken feedback."""

import logging
import subprocess
import time
from pathlib import Path
from urllib.parse import quote_plus

import pyperclip

from .common import SafeDesktopActions

try:
    from AppKit import NSWorkspace
except ImportError:
    NSWorkspace = None

try:
    from ApplicationServices import (
        AXUIElementCopyAttributeValue,
        AXUIElementCreateApplication,
        AXUIElementPerformAction,
        kAXCloseButtonAttribute,
        kAXErrorSuccess,
        kAXFocusedWindowAttribute,
        kAXPressAction,
    )
except ImportError:
    AXUIElementCopyAttributeValue = None
    AXUIElementCreateApplication = None
    AXUIElementPerformAction = None
    kAXCloseButtonAttribute = None
    kAXErrorSuccess = 0
    kAXFocusedWindowAttribute = None
    kAXPressAction = None

try:
    from Quartz import (
        CGEventCreateKeyboardEvent,
        CGEventPostToPid,
        CGEventSetFlags,
        kCGEventFlagMaskCommand,
    )
except ImportError:
    CGEventCreateKeyboardEvent = None
    CGEventPostToPid = None
    CGEventSetFlags = None
    kCGEventFlagMaskCommand = 0


log = logging.getLogger("Guya")


class MacOSActions(SafeDesktopActions):
    SELF_BUNDLE_IDS = {"com.guya.app", "org.python.python"}
    KEY_CODES = {"s": 0x01, "w": 0x0D}
    COMMAND_KEY_CODE = 0x37
    ADDRESS_KEY_CODE = 0x25  # L
    PASTE_KEY_CODE = 0x09    # V
    RETURN_KEY_CODE = 0x24
    BROWSER_KEYS = {
        "scroll_up": (0x74, False),     # Page Up
        "scroll_down": (0x79, False),   # Page Down
        "top": (0x7E, True),            # Cmd+Up
        "bottom": (0x7D, True),         # Cmd+Down
        "back": (0x21, True),           # Cmd+[
        "forward": (0x1E, True),        # Cmd+]
    }
    BROWSER_BUNDLE_IDS = {
        "com.apple.Safari",
        "com.google.Chrome",
        "com.google.Chrome.beta",
        "com.google.Chrome.canary",
        "com.microsoft.edgemac",
        "org.mozilla.firefox",
        "com.brave.Browser",
        "company.thebrowser.Browser",
    }

    APP_CANDIDATES = {
        "word": ("Microsoft Word", "Pages", "LibreOffice"),
        "text_editor": ("TextEdit",),
        "calculator": ("Calculator",),
        "file_manager": ("Finder",),
        "browser": ("Safari", "Google Chrome"),
        "chrome": ("Google Chrome",),
        "safari": ("Safari",),
        "pages": ("Pages",),
    }

    def open_path(self, path: Path):
        try:
            path = Path(path).expanduser().resolve()
        except (OSError, RuntimeError):
            return self._failure(
                "That file or folder is not available.",
                "این فایل یا پوشه در دسترس نیست.",
            )
        if not self._is_allowed(path) or not path.exists():
            return self._failure(
                "That file or folder is not available.",
                "این فایل یا پوشه در دسترس نیست.",
            )
        try:
            subprocess.Popen(
                ["open", str(path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
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
        candidates = self.APP_CANDIDATES.get(app, ())
        for candidate in candidates:
            try:
                result = subprocess.run(
                    ["open", "-a", candidate],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=5,
                    check=False,
                )
                if result.returncode == 0:
                    return self._success(
                        f"Opened {candidate}.",
                        f"{candidate} باز شد.",
                    )
            except Exception:
                continue
        return self._failure(
            "That application is not installed or could not be opened.",
            "این برنامه نصب نیست یا باز کردن آن ممکن نشد.",
        )

    def save_current(self):
        if self._send_shortcut("s"):
            # Give applications such as Word a moment to finish before a
            # following "close" step is allowed to run.
            time.sleep(0.25)
            return self._success(
                "Save was sent to the active file.",
                "دستور ذخیره برای فایل فعال ارسال شد.",
            )
        return self._failure(
            "Could not send Save to the active application.",
            "ارسال دستور ذخیره به برنامه فعال ممکن نشد.",
        )

    def close_current(self):
        # Prefer the target app's accessibility close button. This addresses
        # the captured window directly and cannot accidentally close Guya.
        # Some apps do not expose that button, so keep a process-addressed
        # Cmd+W as a safe fallback.
        if self._press_target_close_button() or self._send_shortcut("w"):
            return self._success(
                "Close was sent to the active window.",
                "دستور بستن برای پنجره فعال ارسال شد.",
            )
        return self._failure(
            "Could not close the active window.",
            "بستن پنجره فعال ممکن نشد.",
        )

    def search_web(self, query: str, app=None):
        query = (query or "").strip()
        if not query:
            return self._failure(
                "The web search is empty.",
                "عبارت جستجوی وب خالی است.",
            )
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
        """Reuse a captured browser tab, with a safe normal-open fallback."""
        if self._browser_target_matches(app) and self._navigate_current_browser(url):
            log.info(
                "Assistant navigated current browser tab: app=%s url=%s",
                self.target_app,
                url,
            )
            return True

        command = ["open", url]
        candidates = self.APP_CANDIDATES.get(app, ()) if app else ()
        if not candidates:
            captured_browser = self._browser_app_for_target()
            candidates = (captured_browser,) if captured_browser else ()
        if candidates:
            command = ["open", "-a", candidates[0], url]
        try:
            result = subprocess.run(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
                check=False,
            )
            success = result.returncode == 0
            log.info(
                "Assistant browser URL fallback: app=%s url=%s success=%s",
                app,
                url,
                success,
            )
            return success
        except Exception as exc:
            log.warning("Assistant browser URL failed: url=%s error=%s", url, exc)
            return False

    def _navigate_current_browser(self, url: str) -> bool:
        """Enter a validated URL in the captured browser's address bar."""
        try:
            previous_clipboard = pyperclip.paste()
        except Exception:
            previous_clipboard = None
        try:
            pyperclip.copy(url)
            if not self._send_key_code(
                self.ADDRESS_KEY_CODE,
                command=True,
                label="browser address bar",
            ):
                return False
            time.sleep(0.05)
            if not self._send_key_code(
                self.PASTE_KEY_CODE,
                command=True,
                label="paste browser URL",
            ):
                return False
            time.sleep(0.05)
            if not self._send_key_code(
                self.RETURN_KEY_CODE,
                command=False,
                label="open browser URL",
            ):
                return False
            time.sleep(0.20)
            return True
        except Exception as exc:
            log.warning("Could not navigate current browser tab: %s", exc)
            return False
        finally:
            if previous_clipboard is not None:
                try:
                    pyperclip.copy(previous_clipboard)
                except Exception:
                    pass

    def browser_control(self, action: str):
        key = self.BROWSER_KEYS.get(action)
        if key is None:
            return self._failure(
                "That browser movement is not supported.",
                "این حرکت مرورگر پشتیبانی نمی‌شود.",
            )
        if not self._is_browser_target():
            return self._failure(
                "Focus a supported browser, then try the command again.",
                "ابتدا مرورگر پشتیبانی‌شده را فعال کنید و دوباره دستور را بگویید.",
            )
        key_code, command = key
        if not self._send_key_code(key_code, command=command, label=action):
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

    def _target_pid(self):
        if NSWorkspace is None or not self.target_app:
            return None
        if str(self.target_app) in self.SELF_BUNDLE_IDS:
            log.warning(
                "Blocked assistant action targeting Guya itself: %s",
                self.target_app,
            )
            return None
        try:
            workspace = NSWorkspace.sharedWorkspace()
            for app in workspace.runningApplications():
                bundle_id = app.bundleIdentifier()
                if bundle_id and str(bundle_id) == str(self.target_app):
                    pid = int(app.processIdentifier())
                    log.info(
                        "Assistant target resolved: app=%s pid=%s",
                        self.target_app,
                        pid,
                    )
                    return pid if pid > 0 else None
        except Exception as exc:
            log.warning("Could not resolve assistant target %s: %s", self.target_app, exc)
        return None

    def _is_browser_target(self) -> bool:
        target = str(self.target_app or "")
        return target in self.BROWSER_BUNDLE_IDS

    def _browser_target_matches(self, app=None) -> bool:
        if not self._is_browser_target():
            return False
        target = str(self.target_app)
        if app in (None, "browser"):
            return True
        if app == "chrome":
            return target.startswith("com.google.Chrome")
        if app == "safari":
            return target == "com.apple.Safari"
        return False

    def _browser_app_for_target(self):
        target = str(self.target_app or "")
        if target.startswith("com.google.Chrome"):
            return "Google Chrome"
        if target == "com.apple.Safari":
            return "Safari"
        if target == "com.microsoft.edgemac":
            return "Microsoft Edge"
        if target == "org.mozilla.firefox":
            return "Firefox"
        if target == "com.brave.Browser":
            return "Brave Browser"
        if target == "company.thebrowser.Browser":
            return "Arc"
        return None

    def _press_target_close_button(self) -> bool:
        """Press the captured app's focused window close button through AX."""
        if (
            AXUIElementCreateApplication is None
            or AXUIElementCopyAttributeValue is None
            or AXUIElementPerformAction is None
        ):
            return False

        pid = self._target_pid()
        if pid is None:
            return False

        try:
            application = AXUIElementCreateApplication(pid)
            window_error, window = AXUIElementCopyAttributeValue(
                application,
                kAXFocusedWindowAttribute,
                None,
            )
            if window_error != kAXErrorSuccess or window is None:
                log.info(
                    "Target app did not expose a focused window: app=%s pid=%s error=%s",
                    self.target_app,
                    pid,
                    window_error,
                )
                return False

            button_error, close_button = AXUIElementCopyAttributeValue(
                window,
                kAXCloseButtonAttribute,
                None,
            )
            if button_error != kAXErrorSuccess or close_button is None:
                log.info(
                    "Target window did not expose a close button: app=%s pid=%s error=%s",
                    self.target_app,
                    pid,
                    button_error,
                )
                return False

            action_error = AXUIElementPerformAction(close_button, kAXPressAction)
            success = action_error == kAXErrorSuccess
            log.info(
                "Assistant close button pressed: app=%s pid=%s success=%s error=%s",
                self.target_app,
                pid,
                success,
                action_error,
            )
            return success
        except Exception as exc:
            log.warning(
                "Assistant accessibility close failed: app=%s pid=%s error=%s",
                self.target_app,
                pid,
                exc,
            )
            return False

    def _send_shortcut(self, key: str) -> bool:
        """Post Cmd+key directly to the captured app's process.

        CGEventPostToPid is intentionally used instead of a global keyboard
        controller. A global event can be delivered back to Guya if macOS
        changes focus at the wrong moment; a PID-addressed event cannot.
        """
        key_code = self.KEY_CODES.get(str(key).lower())
        if key_code is None:
            log.warning("Unsupported assistant shortcut: Cmd+%s", key)
            return False

        return self._send_key_code(
            key_code,
            command=True,
            label=f"Cmd+{key.upper()}",
        )

    def _send_key_code(self, key_code: int, command: bool, label: str) -> bool:
        """Post one key, optionally with Command, to the captured process."""
        if (
            CGEventCreateKeyboardEvent is None
            or CGEventPostToPid is None
            or CGEventSetFlags is None
        ):
            return False

        pid = self._target_pid()
        if pid is None:
            log.warning(
                "Assistant key blocked because target was not resolved: key=%s target=%s",
                label,
                self.target_app,
            )
            return False

        try:
            key_down = CGEventCreateKeyboardEvent(None, key_code, True)
            key_up = CGEventCreateKeyboardEvent(None, key_code, False)
            if command:
                command_down = CGEventCreateKeyboardEvent(
                    None, self.COMMAND_KEY_CODE, True
                )
                command_up = CGEventCreateKeyboardEvent(
                    None, self.COMMAND_KEY_CODE, False
                )
                events = (command_down, key_down, key_up, command_up)
            else:
                events = (key_down, key_up)
            if any(event is None for event in events):
                return False

            if command:
                CGEventSetFlags(command_down, kCGEventFlagMaskCommand)
                CGEventSetFlags(key_down, kCGEventFlagMaskCommand)
                CGEventSetFlags(key_up, kCGEventFlagMaskCommand)
                CGEventSetFlags(command_up, 0)
            else:
                CGEventSetFlags(key_down, 0)
                CGEventSetFlags(key_up, 0)

            for event in events:
                CGEventPostToPid(pid, event)
                time.sleep(0.01)

            log.info(
                "Assistant key sent directly: key=%s target=%s pid=%s",
                label,
                self.target_app,
                pid,
            )
            return True
        except Exception as exc:
            log.warning(
                "Assistant key %s failed for target=%s pid=%s: %s",
                label,
                self.target_app,
                pid,
                exc,
            )
            return False

    def speak(self, text: str, language: str = "en") -> None:
        if not text:
            return
        # Never read Persian with an Arabic voice. If macOS has no real
        # Persian voice, Guya keeps the accurate visual response instead.
        if language == "fa":
            self.stop_speaking()
            log.info("Persian spoken feedback skipped: no Persian macOS voice")
            return
        command = ["say", text]
        self.stop_speaking()
        try:
            self._speech_process = subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            self._speech_process = None

    def stop_speaking(self) -> None:
        process = getattr(self, "_speech_process", None)
        if process is None:
            return
        try:
            if process.poll() is None:
                process.terminate()
                log.info("Assistant speech interrupted")
        except Exception:
            pass
        finally:
            self._speech_process = None
