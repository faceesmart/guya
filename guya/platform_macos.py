"""
macOS platform adapter for Voice Widget.

Provides the same function/class names that voice_widget.py uses on Windows,
backed by macOS APIs:

  - Global hotkey:    pynput.keyboard.Listener (CGEventTap under the hood)
  - Paste to target:  pyperclip + Cmd+V via pynput
  - Foreground app:   NSWorkspace.frontmostApplication
  - Permissions:      AXIsProcessTrusted (Accessibility)
  - GPU check:        no-op (M1 has no CUDA; faster-whisper has no MPS yet)

Hotkeys: Right Option (⌥) for dictation and Right Command (⌘) for the
assistant. Modifier keys do not type stray characters when pressed alone.
"""

import logging
import threading
import time
import subprocess

import pyperclip

log = logging.getLogger("Guya")


# ============================================================
# OPTIONAL DEPS (pynput, pyobjc)
# ============================================================
# Imported lazily so the module is importable for inspection even if
# the deps aren't installed yet (install.sh handles them).

try:
    from pynput import keyboard as _pynput_kb
    _PYNPUT_OK = True
except ImportError as e:
    _pynput_kb = None
    _PYNPUT_OK = False
    log.warning(f"pynput not available: {e}. Install with: pip install pynput")

try:
    from AppKit import NSWorkspace, NSRunningApplication, NSApplicationActivateIgnoringOtherApps
    _APPKIT_OK = True
except ImportError as e:
    NSWorkspace = None
    NSRunningApplication = None
    NSApplicationActivateIgnoringOtherApps = 0
    _APPKIT_OK = False
    log.warning(f"AppKit not available: {e}. Install with: pip install pyobjc-framework-Cocoa")

try:
    from ApplicationServices import (
        AXIsProcessTrusted,
        AXIsProcessTrustedWithOptions,
        kAXTrustedCheckOptionPrompt,
    )
    from CoreFoundation import CFDictionaryCreate, kCFTypeDictionaryKeyCallBacks, kCFTypeDictionaryValueCallBacks
    _AX_OK = True
except ImportError as e:
    AXIsProcessTrusted = None
    AXIsProcessTrustedWithOptions = None
    kAXTrustedCheckOptionPrompt = None
    _AX_OK = False
    log.warning(f"ApplicationServices not available: {e}.")


# ============================================================
# HOTKEY: Right Option (⌥)
# ============================================================

# The "key" we listen for. Right Option is a modifier — pressing it alone
# produces no character, so no suppression is needed and no stray characters
# leak into the target app while held.
HOTKEY_NAME = "Right Option (⌥)"
ASSISTANT_HOTKEY_NAME = "Right Command (⌘)"

# Stable hardware virtual-key codes used by macOS. Comparing the vk as well as
# pynput's enum makes detection resilient across pynput/PyObjC versions.
_VK_RIGHT_OPTION = 61
_VK_RIGHT_COMMAND = 54
_VK_RIGHT_CONTROL = 62  # keep the old MVP key working on full keyboards


def _key_vk(key):
    value = getattr(key, "value", key)
    return getattr(value, "vk", getattr(key, "vk", None))


def _is_hotkey(key) -> bool:
    """Return True if the pynput key is our push-to-talk key."""
    if _pynput_kb is None:
        return False
    # On macOS pynput exposes Key.alt_r for right option.
    return key == _pynput_kb.Key.alt_r or _key_vk(key) == _VK_RIGHT_OPTION


def _is_assistant_hotkey(key) -> bool:
    """Return True for the assistant push-to-talk key."""
    if _pynput_kb is None:
        return False
    return (
        key in (_pynput_kb.Key.cmd_r, _pynput_kb.Key.ctrl_r)
        or _key_vk(key) in (_VK_RIGHT_COMMAND, _VK_RIGHT_CONTROL)
    )


# ============================================================
# FOREGROUND APP CAPTURE
# ============================================================
#
# On macOS we can't easily reference a single text input "control"
# the way Win32 does (NSView hierarchy varies by app). Instead we
# remember the frontmost NSRunningApplication and reactivate it
# before sending Cmd+V. AppKit + the system clipboard handle the rest.

def get_foreground_window():
    """Return an opaque token representing the frontmost app.

    On macOS this is the bundle identifier (string) of the front app,
    or None if AppKit unavailable.
    """
    if not _APPKIT_OK:
        return None
    try:
        app = NSWorkspace.sharedWorkspace().frontmostApplication()
        if app is None:
            return None
        bundle_id = app.bundleIdentifier()
        return str(bundle_id) if bundle_id else None
    except Exception as e:
        log.warning(f"get_foreground_window failed: {e}")
        return None


def force_foreground_window(token) -> bool:
    """Bring the app identified by `token` (bundle id) back to the front."""
    if not _APPKIT_OK or not token:
        return False
    try:
        # Find the running app by bundle id and activate it.
        apps = NSWorkspace.sharedWorkspace().runningApplications()
        for app in apps:
            bid = app.bundleIdentifier()
            if bid and str(bid) == token:
                app.activateWithOptions_(NSApplicationActivateIgnoringOtherApps)
                return True
        log.debug(f"No running app for bundle id {token}")
        return False
    except Exception as e:
        log.warning(f"force_foreground_window failed: {e}")
        return False


def get_focused_control(token):
    """No-op on macOS: we operate at app granularity, not view granularity."""
    return token


# ============================================================
# TEXT INPUT: clipboard + Cmd+V into the target app
# ============================================================

def _send_cmd_v():
    """Press Cmd+V via pynput. Cmd up/down each character."""
    if _pynput_kb is None:
        return False
    try:
        controller = _pynput_kb.Controller()
        with controller.pressed(_pynput_kb.Key.cmd):
            controller.press('v')
            controller.release('v')
        return True
    except Exception as e:
        log.error(f"Cmd+V via pynput failed: {e}")
        return False


def paste_text_to_window(target_token, text: str) -> bool:
    """Copy `text` to clipboard and paste it (Cmd+V) into the frontmost app.

    IMPORTANT: we deliberately paste into whatever is frontmost RIGHT NOW rather
    than re-activating `target_token`. Reasons:
      * The widget is non-activating (WA_ShowWithoutActivating +
        WindowDoesNotAcceptFocus), so the user's text field is still the
        frontmost window at paste time — no need to switch back to it.
      * `target_token` was captured inside the pynput background thread, where
        NSWorkspace.frontmostApplication() returns a STALE value (the app that
        launched Guya, e.g. the terminal). Re-activating it pasted into the
        wrong app. Ignoring it fixes that.

    This function is called on the Qt main thread, so the frontmost app here is
    the correct, current one.
    """
    if not text:
        return False

    try:
        pyperclip.copy(text)
    except Exception as e:
        log.error(f"Clipboard copy failed: {e}")
        return False

    # Give the clipboard a moment to settle, then paste into the current app.
    time.sleep(0.05)
    ok = _send_cmd_v()
    if ok:
        try:
            front = get_foreground_window()
        except Exception:
            front = "?"
        log.info(f"Pasted {len(text)} chars into frontmost app ({front})")
    return ok


def erase_text_in_window(target_token, count: int):
    """Delete `count` characters by sending Backspace via pynput."""
    if count <= 0 or _pynput_kb is None:
        return
    if target_token:
        force_foreground_window(target_token)
        time.sleep(0.05)
    try:
        controller = _pynput_kb.Controller()
        for _ in range(count):
            controller.press(_pynput_kb.Key.backspace)
            controller.release(_pynput_kb.Key.backspace)
    except Exception as e:
        log.warning(f"erase_text_in_window failed: {e}")


# ============================================================
# KEYBOARD HOOK: same interface as the Windows KeyboardHookThread
# ============================================================

class KeyboardHookThread(threading.Thread):
    """Global hotkey listener for Right Option (⌥) on macOS.

    Matches the Windows KeyboardHookThread interface so voice_widget.py
    doesn't need to know the difference. Uses pynput's Listener which
    sits on top of a CGEventTap. Requires Accessibility permission
    (System Settings → Privacy & Security → Accessibility).

    Press/release of the hotkey trigger on_press / on_release callbacks
    on this thread. The widget then marshals to the Qt main thread.
    """

    def __init__(
        self,
        on_press,
        on_release,
        is_enabled_func,
        on_assistant_press=None,
        on_assistant_release=None,
        assistant_enabled_func=None,
    ):
        super().__init__(daemon=True)
        self.on_press = on_press
        self.on_release = on_release
        self.is_enabled_func = is_enabled_func
        self.on_assistant_press = on_assistant_press
        self.on_assistant_release = on_assistant_release
        self.assistant_enabled_func = assistant_enabled_func or is_enabled_func
        self._listener = None
        self._held_mode = None
        # Captured frontmost app at hotkey press — read by widget on _start_recording
        self.captured_hwnd = None

    def _on_press(self, key):
        try:
            mode = None
            callback = None
            if _is_hotkey(key) and self.is_enabled_func():
                mode, callback = "dictation", self.on_press
            elif (
                _is_assistant_hotkey(key)
                and self.on_assistant_press is not None
                and self.assistant_enabled_func()
            ):
                mode, callback = "assistant", self.on_assistant_press
            if mode is None:
                return
            if self._held_mode is not None:
                return  # ignore key repeat
            self._held_mode = mode
            # Capture frontmost app NOW, before Qt focus changes
            self.captured_hwnd = get_foreground_window()
            log.info(f"Hook captured mode={mode} target app={self.captured_hwnd}")
            callback()
        except Exception as e:
            log.error(f"Hook on_press error: {e}")

    def _on_release(self, key):
        try:
            mode = "dictation" if _is_hotkey(key) else (
                "assistant" if _is_assistant_hotkey(key) else None
            )
            if mode is None or self._held_mode != mode:
                return
            self._held_mode = None
            if mode == "assistant" and self.on_assistant_release is not None:
                self.on_assistant_release()
            else:
                self.on_release()
        except Exception as e:
            log.error(f"Hook on_release error: {e}")

    def run(self):
        if _pynput_kb is None:
            log.error("pynput unavailable — keyboard hook disabled")
            return
        log.info(
            f"Keyboard hook starting (dictation: {HOTKEY_NAME}; "
            f"assistant: {ASSISTANT_HOTKEY_NAME})"
        )
        # suppress=False: we don't want to swallow keys globally.
        # Right Option alone produces no character, so suppression is unnecessary.
        try:
            with _pynput_kb.Listener(
                on_press=self._on_press,
                on_release=self._on_release,
                suppress=False,
            ) as listener:
                self._listener = listener
                listener.join()
        except Exception as e:
            log.error(f"Keyboard listener crashed: {e}")
            log.error("If this is a permissions error: grant Accessibility in "
                      "System Settings → Privacy & Security → Accessibility")

    def stop(self):
        if self._listener is not None:
            try:
                self._listener.stop()
            except Exception:
                pass
            self._listener = None


# ============================================================
# PERMISSION & PRE-FLIGHT CHECKS
# ============================================================

def is_accessibility_granted() -> bool:
    """Return True if our process has Accessibility permission.

    Without this, the global keyboard listener won't receive events and
    pynput can't synthesize Cmd+V into other apps.
    """
    if not _AX_OK:
        return False
    try:
        return bool(AXIsProcessTrusted())
    except Exception:
        return False


def prompt_accessibility_grant():
    """Ask macOS for Accessibility access and open Settings as a fallback."""
    if _AX_OK and AXIsProcessTrustedWithOptions is not None:
        try:
            return bool(AXIsProcessTrustedWithOptions({
                kAXTrustedCheckOptionPrompt: True,
            }))
        except Exception as e:
            log.warning(f"Accessibility prompt failed: {e}")
    try:
        subprocess.Popen([
            "open",
            "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility",
        ])
    except Exception as e:
        log.warning(f"Failed to open Accessibility settings: {e}")
    return False


def check_admin() -> bool:
    """Drop-in replacement for Windows check_admin(): logs whether Accessibility
    has been granted. Returns True if granted."""
    ok = is_accessibility_granted()
    if ok:
        log.info("Accessibility permission: GRANTED")
    else:
        log.warning("Accessibility permission: NOT GRANTED")
        log.warning("Global hotkey and paste will NOT work without it.")
        log.warning("Grant access: System Settings → Privacy & Security → Accessibility")
        prompt_accessibility_grant()
    return ok


def check_gpu_lightweight():
    """Return (gpu_ok, info_str). On macOS faster-whisper has no Metal/MPS
    backend, so we always report CPU — but we tell the user it's Apple Silicon."""
    try:
        # Get the chip name from sysctl (e.g. "Apple M1 Pro")
        out = subprocess.run(
            ["sysctl", "-n", "machdep.cpu.brand_string"],
            capture_output=True, text=True, timeout=2,
        )
        chip = out.stdout.strip() or "Apple Silicon"
    except Exception:
        chip = "Apple Silicon"
    return False, f"CPU ({chip})"


# ============================================================
# WINDOW STYLING (no-op on macOS — Qt flags handle it)
# ============================================================

def apply_nonactivating_style(qwidget):
    """On Windows this sets WS_EX_NOACTIVATE so clicks don't steal focus.

    On macOS, Qt.WindowDoesNotAcceptFocus + Qt.Tool flags (set in the
    widget's setWindowFlags call) already achieve this. No extra work
    needed here.
    """
    return True
