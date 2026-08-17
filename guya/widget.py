"""
Persian Voice-to-Text Floating Widget — Windows & macOS
Push-to-talk STT using faster-whisper.
Hold the hotkey to speak; release to transcribe.

  - Windows: hotkey = G, GPU via CUDA + float16 if available
  - macOS:   hotkey = Right Option (⌥), CPU + int8 (M1/M2/M3 — no CUDA, no MPS)

CRITICAL (Windows only): CTranslate2's CUDA backend segfaults if PyQt6 is
imported first. The model MUST be loaded before any Qt imports. This file
is structured to ensure that order: main() loads model → imports Qt → creates widget.
"""

import sys
import os
import json
import time
import struct
import threading
import subprocess
import re
import math
import logging
import traceback
import faulthandler
from collections import Counter
from logging.handlers import RotatingFileHandler
import numpy as np
import pyperclip
import pyaudio

# ============================================================
# PLATFORM DETECTION
# ============================================================
IS_WIN = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"

if IS_WIN:
    import ctypes
    import ctypes.wintypes

# UI font: a concrete, always-present family per OS. An empty family makes Qt
# fall back to a poor default, so we name one explicitly.
if IS_WIN:
    UI_FONT = "Segoe UI"
elif IS_MAC:
    UI_FONT = "Helvetica Neue"
else:
    UI_FONT = "DejaVu Sans"

# Enable faulthandler to get tracebacks on native crashes (SIGSEGV etc.)
faulthandler.enable()

# ============================================================
# CONFIG SYSTEM
# ============================================================
# Guya reads all user choices from ~/.guya/config.json (written by the setup
# wizard). Works whether widget.py is imported as part of the `guya` package
# or run as a loose script.

try:
    from . import config as guya_config
    from . import cloud_engine
    from . import runtime as guya_runtime
    from .assistant import AssistantService
except ImportError:
    import config as guya_config
    import cloud_engine
    import runtime as guya_runtime
    from assistant import AssistantService

CFG = guya_config.load_config()

# ============================================================
# LOGGING SETUP
# ============================================================
# Logs go to ~/.guya/logs/ — always writable (never a TCC-protected folder
# like Desktop, and never needs admin), cross-platform.

LOG_DIR = os.path.join(guya_config.CONFIG_DIR, "logs")
try:
    os.makedirs(LOG_DIR, exist_ok=True)
except Exception:
    import tempfile
    LOG_DIR = tempfile.gettempdir()
LOG_FILE = os.path.join(LOG_DIR, "guya.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-7s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        RotatingFileHandler(
            LOG_FILE,
            mode="a",
            maxBytes=2 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        ),
    ],
)
log = logging.getLogger("Guya")

# Silence noisy HTTP libraries and PyTorch internals
for _lib in ("httpx", "httpcore", "urllib3", "filelock", "huggingface_hub",
             "torch", "torch.distributed", "torch._dynamo", "torch._inductor",
             "torch.fx", "torch._C"):
    logging.getLogger(_lib).setLevel(logging.WARNING)

# ============================================================
# CONFIGURATION (loaded from config.json, with sensible fallbacks)
# ============================================================

# Model — "auto" device/compute are resolved at load time by load_model_sync().
MODEL_SIZE = CFG["model"]["size"]
DEVICE = CFG["model"]["device"]              # "auto" | "cuda" | "cpu"
COMPUTE_TYPE = CFG["model"]["compute_type"]  # "auto" | "float16" | "int8" | ...
MODEL_BACKEND = CFG["model"]["backend"]      # "faster-whisper" | "cloud"
LANGUAGE = CFG["language"]
ASSISTANT_CFG = CFG.get("assistant", {})
ASSISTANT_ENABLED = bool(ASSISTANT_CFG.get("enabled", True))
ASSISTANT_SPEAK_FEEDBACK = bool(ASSISTANT_CFG.get("speak_feedback", True))

# Hybrid mode: an offline model AND a cloud key are both configured, so the
# widget can switch between them at runtime.
CLOUD_ENABLED = bool(CFG["cloud"].get("enabled") and CFG["cloud"].get("api_key"))
HYBRID = (MODEL_BACKEND == "faster-whisper") and CLOUD_ENABLED
OFFLINE_LANGUAGE = CFG["language"]            # the language offline mode uses

# Audio
SAMPLE_RATE = CFG["audio"]["sample_rate"]
CHUNK_SIZE = CFG["audio"]["chunk_size"]
REALTIME_CHUNK_SEC = CFG["audio"]["realtime_chunk_sec"]

# Widget — Collapsed (small circle) and Expanded (pill) sizes
WIDGET_COLLAPSED_SIZE = 40           # diameter of the small circle
WIDGET_EXPANDED_WIDTH = 280          # width when expanded
WIDGET_EXPANDED_HEIGHT = 42          # height when expanded
WIDGET_MARGIN_TOP = 18
# Legacy aliases used by some layout code
WIDGET_WIDTH = WIDGET_EXPANDED_WIDTH
WIDGET_HEIGHT = WIDGET_EXPANDED_HEIGHT
UI_STYLE = CFG["ui"]["style"]

# Behavior
MIN_RECORDING_DURATION = CFG["behavior"]["min_recording_duration"]
DONE_STATE_DURATION = CFG["behavior"]["done_state_duration_ms"]
TYPE_DELAY = CFG["behavior"]["type_delay_ms"]
ANIMATION_FPS = CFG["behavior"]["animation_fps"]

# ============================================================
# PLATFORM-SPECIFIC IMPORTS / DEFINITIONS
# ============================================================
# On macOS we pull the keyboard hook, paste helpers, foreground capture, and
# permission checks from platform_macos. On Windows the same names are defined
# inline below (legacy code path).

if IS_MAC:
    try:
        from .platform_macos import (
            KeyboardHookThread,
            paste_text_to_window,
            erase_text_in_window,
            get_foreground_window,
            get_focused_control,
            force_foreground_window,
            check_admin,
            is_accessibility_granted,
            check_gpu_lightweight as _check_cuda_lightweight,
            apply_nonactivating_style,
            HOTKEY_NAME,
            ASSISTANT_HOTKEY_NAME,
        )
    except ImportError:
        from platform_macos import (
            KeyboardHookThread,
            paste_text_to_window,
            erase_text_in_window,
            get_foreground_window,
            get_focused_control,
            force_foreground_window,
            check_admin,
            is_accessibility_granted,
            check_gpu_lightweight as _check_cuda_lightweight,
            apply_nonactivating_style,
            HOTKEY_NAME,
            ASSISTANT_HOTKEY_NAME,
        )
    HOTKEY_LABEL = "⌥"  # right option symbol used in widget labels
    ASSISTANT_HOTKEY_LABEL = "⌘"
else:
    # Windows: hotkey comes from config (vk + label), default 'G'.
    HOTKEY_NAME = CFG["hotkey"]["name"]
    HOTKEY_LABEL = CFG["hotkey"]["label"]
    ASSISTANT_HOTKEY_NAME = ASSISTANT_CFG["hotkey"]["name"]
    ASSISTANT_HOTKEY_LABEL = ASSISTANT_CFG["hotkey"]["label"]

    def is_accessibility_granted():
        return True

# Hotkey virtual-key code (Windows). macOS uses Right Option regardless.
if IS_WIN:
    VK_G = CFG["hotkey"]["vk"]
    VK_ASSISTANT = ASSISTANT_CFG["hotkey"]["vk"]

# ============================================================
# WINDOWS API CONSTANTS & STRUCTURES (Windows only)
# ============================================================

if IS_WIN:
    WH_KEYBOARD_LL = 13
    WM_KEYDOWN = 0x0100
    WM_KEYUP = 0x0101
    WM_SYSKEYDOWN = 0x0104
    WM_SYSKEYUP = 0x0105

    INPUT_KEYBOARD = 1
    KEYEVENTF_UNICODE = 0x0004
    KEYEVENTF_KEYUP = 0x0002

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

if IS_WIN:
    # Windows messages for direct window messaging (bypasses SendInput blocking)
    WM_CHAR = 0x0102
    WM_PASTE = 0x0302
    WM_CLEAR = 0x0303
    EM_SETSEL = 0x00B1
    EM_REPLACESEL = 0x00C2

    class KBDLLHOOKSTRUCT(ctypes.Structure):
        _fields_ = [
            ("vkCode", ctypes.wintypes.DWORD),
            ("scanCode", ctypes.wintypes.DWORD),
            ("flags", ctypes.wintypes.DWORD),
            ("time", ctypes.wintypes.DWORD),
            ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
        ]

    HOOKPROC = ctypes.CFUNCTYPE(
        ctypes.c_long,
        ctypes.c_int,
        ctypes.wintypes.WPARAM,
        ctypes.wintypes.LPARAM,
    )

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk", ctypes.wintypes.WORD),
            ("wScan", ctypes.wintypes.WORD),
            ("dwFlags", ctypes.wintypes.DWORD),
            ("time", ctypes.wintypes.DWORD),
            ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
        ]

    class INPUT(ctypes.Structure):
        class _INPUT_UNION(ctypes.Union):
            _fields_ = [("ki", KEYBDINPUT)]

        _fields_ = [
            ("type", ctypes.wintypes.DWORD),
            ("_input", _INPUT_UNION),
        ]

    # ============================================================
    # UNICODE TEXT INPUT via SendInput
    # ============================================================

    def get_foreground_window():
        """Return the handle of the current foreground window."""
        return user32.GetForegroundWindow()

    def force_foreground_window(hwnd):
        """Force a window to the foreground using multiple Windows API tricks."""
        if not hwnd:
            return False

        current_fg = user32.GetForegroundWindow()
        if current_fg == hwnd:
            return True

        our_tid = kernel32.GetCurrentThreadId()
        fg_tid = user32.GetWindowThreadProcessId(current_fg, None)
        target_tid = user32.GetWindowThreadProcessId(hwnd, None)

        attached_fg = False
        attached_target = False

        try:
            if fg_tid != our_tid:
                attached_fg = bool(user32.AttachThreadInput(our_tid, fg_tid, True))
            if target_tid != our_tid and target_tid != fg_tid:
                attached_target = bool(user32.AttachThreadInput(our_tid, target_tid, True))
            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)
            time.sleep(0.05)
        finally:
            if attached_fg:
                user32.AttachThreadInput(our_tid, fg_tid, False)
            if attached_target:
                user32.AttachThreadInput(our_tid, target_tid, False)

        result = user32.GetForegroundWindow() == hwnd
        if not result:
            log.warning(f"force_foreground_window({hwnd}) -> foreground is {user32.GetForegroundWindow()}")
        return result

    # Set proper argtypes for SendInput to handle 64-bit correctly
    user32.SendInput.argtypes = [ctypes.c_uint, ctypes.POINTER(INPUT), ctypes.c_int]
    user32.SendInput.restype = ctypes.c_uint

    # ============================================================
    # FOCUSED CHILD WINDOW DETECTION
    # ============================================================

    class GUITHREADINFO(ctypes.Structure):
        _fields_ = [
            ("cbSize", ctypes.wintypes.DWORD),
            ("flags", ctypes.wintypes.DWORD),
            ("hwndActive", ctypes.wintypes.HWND),
            ("hwndFocus", ctypes.wintypes.HWND),
            ("hwndCapture", ctypes.wintypes.HWND),
            ("hwndMenuOwner", ctypes.wintypes.HWND),
            ("hwndMoveSize", ctypes.wintypes.HWND),
            ("hwndCaret", ctypes.wintypes.HWND),
            ("rcCaret", ctypes.wintypes.RECT),
        ]

    user32.GetGUIThreadInfo.argtypes = [ctypes.wintypes.DWORD, ctypes.POINTER(GUITHREADINFO)]
    user32.GetGUIThreadInfo.restype = ctypes.wintypes.BOOL

    _TEXT_CONTROL_CLASSES = {
        "Edit", "RichEdit", "RichEdit20A", "RichEdit20W", "RichEditD2DPT",
        "RICHEDIT50W", "Scintilla", "TextBox", "_WwG",  # Word
    }

    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.wintypes.BOOL, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)

    user32.EnumChildWindows.argtypes = [ctypes.wintypes.HWND, WNDENUMPROC, ctypes.wintypes.LPARAM]
    user32.EnumChildWindows.restype = ctypes.wintypes.BOOL

    user32.GetClassNameW.argtypes = [ctypes.wintypes.HWND, ctypes.c_wchar_p, ctypes.c_int]
    user32.GetClassNameW.restype = ctypes.c_int

    user32.IsWindowVisible.argtypes = [ctypes.wintypes.HWND]
    user32.IsWindowVisible.restype = ctypes.wintypes.BOOL

    def _get_window_class(hwnd):
        buf = ctypes.create_unicode_buffer(256)
        n = user32.GetClassNameW(hwnd, buf, 256)
        return buf.value if n > 0 else ""

    def _find_text_control_child(parent_hwnd):
        found = []

        def enum_callback(child_hwnd, lParam):
            if user32.IsWindowVisible(child_hwnd):
                cls = _get_window_class(child_hwnd)
                if cls in _TEXT_CONTROL_CLASSES:
                    found.append((child_hwnd, cls))
            return True

        callback = WNDENUMPROC(enum_callback)
        user32.EnumChildWindows(parent_hwnd, callback, 0)
        return found

    def get_focused_control(hwnd):
        if not hwnd:
            return hwnd
        tid = user32.GetWindowThreadProcessId(hwnd, None)
        if tid:
            gti = GUITHREADINFO()
            gti.cbSize = ctypes.sizeof(GUITHREADINFO)
            if user32.GetGUIThreadInfo(tid, ctypes.byref(gti)):
                if gti.hwndFocus and gti.hwndFocus != hwnd:
                    cls = _get_window_class(gti.hwndFocus)
                    log.info(f"Focused control: hwnd={gti.hwndFocus} class={cls} (parent={hwnd})")
                    return gti.hwndFocus
        children = _find_text_control_child(hwnd)
        if children:
            child_hwnd, child_cls = children[0]
            log.info(f"Found text control: hwnd={child_hwnd} class={child_cls} (parent={hwnd}, total={len(children)})")
            return child_hwnd
        own_cls = _get_window_class(hwnd)
        if own_cls in _TEXT_CONTROL_CLASSES:
            log.info(f"Window itself is a text control: hwnd={hwnd} class={own_cls}")
            return hwnd
        log.info(f"No text control found in hwnd={hwnd} class={own_cls}")
        return hwnd

    # ============================================================
    # TEXT INPUT: clipboard + keybd_event Ctrl+V
    # ============================================================

    user32.SendMessageW.argtypes = [
        ctypes.wintypes.HWND,
        ctypes.c_uint,
        ctypes.wintypes.WPARAM,
        ctypes.wintypes.LPARAM,
    ]
    user32.SendMessageW.restype = ctypes.c_long

    user32.PostMessageW.argtypes = [
        ctypes.wintypes.HWND,
        ctypes.c_uint,
        ctypes.wintypes.WPARAM,
        ctypes.wintypes.LPARAM,
    ]
    user32.PostMessageW.restype = ctypes.wintypes.BOOL

    _keybd_event = user32.keybd_event
    _keybd_event.argtypes = [
        ctypes.c_byte,
        ctypes.c_byte,
        ctypes.wintypes.DWORD,
        ctypes.POINTER(ctypes.c_ulong),
    ]
    _keybd_event.restype = None

    def paste_text_to_window(window_hwnd, text):
        if not text:
            return False
        try:
            pyperclip.copy(text)
        except Exception as e:
            log.error(f"Clipboard copy failed: {e}")
            return False
        if not window_hwnd:
            log.warning("No target hwnd for paste")
            return False
        force_foreground_window(window_hwnd)
        time.sleep(0.03)
        _send_ctrl_v()
        log.info(f"Pasted {len(text)} chars to hwnd={window_hwnd}")
        return True

    def _send_ctrl_v():
        VK_CONTROL = 0x11
        VK_V = 0x56
        KUP = 0x0002
        _keybd_event(VK_CONTROL, 0, 0, None)
        _keybd_event(VK_V, 0, 0, None)
        _keybd_event(VK_V, 0, KUP, None)
        _keybd_event(VK_CONTROL, 0, KUP, None)

    def erase_text_in_window(target_hwnd, count):
        if count <= 0 or not target_hwnd:
            return
        VK_BACK = 0x08
        KUP = 0x0002
        force_foreground_window(target_hwnd)
        time.sleep(0.02)
        for _ in range(count):
            _keybd_event(VK_BACK, 0, 0, None)
            _keybd_event(VK_BACK, 0, KUP, None)
        log.debug(f"Erased {count} chars in hwnd={target_hwnd}")

    def apply_nonactivating_style(qwidget):
        """Set WS_EX_NOACTIVATE so the widget doesn't steal focus when clicked."""
        GWL_EXSTYLE = -20
        WS_EX_NOACTIVATE = 0x08000000
        WS_EX_TOPMOST = 0x00000008
        hwnd = int(qwidget.winId())
        try:
            _GetWindowLongPtrW = ctypes.windll.user32.GetWindowLongPtrW
            _SetWindowLongPtrW = ctypes.windll.user32.SetWindowLongPtrW
            style = _GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
            _SetWindowLongPtrW(hwnd, GWL_EXSTYLE, style | WS_EX_NOACTIVATE | WS_EX_TOPMOST)
            log.info(f"WS_EX_NOACTIVATE set on widget (hwnd={hwnd})")
            return True
        except Exception as e:
            log.warning(f"Could not set WS_EX_NOACTIVATE: {e}")
            return False


# ============================================================
# PERSIAN TEXT NORMALIZATION
# ============================================================

# Arabic-to-Persian character map (lightweight, no external deps)
_ARABIC_TO_PERSIAN = str.maketrans({
    '\u064A': '\u06CC',  # ي → ی
    '\u0643': '\u06A9',  # ك → ک
    '\u0629': '\u0647',  # ة → ه
    '\u0649': '\u06CC',  # ى → ی
    '\u06C0': '\u0647',  # ۀ → ه
    '\u0624': '\u0648',  # ؤ → و
})

# Arabic diacritics to strip (fathah, dammah, kasrah, sukun, shadda, tanwin, etc.)
_ARABIC_DIACRITICS = re.compile(r'[\u064B-\u065F\u0670]')

# Common Whisper hallucination phrases (Persian & cross-language)
_HALLUCINATION_PATTERNS = [
    "ساب اسکرایب",
    "سابسکرایب",
    "subscribe",
    "like and subscribe",
    "ممنون از اینکه",
    "ممنون که گوش دادید",
    "ادامه دارد",
    "تماشا کنید",
    "لطفا لایک کنید",
    "زیرنویس",
    "ترجمه",
    "www.",
    "http",
]


def normalize_persian(text: str) -> str:
    """Normalize Persian text: fix Arabic chars, spacing, half-spaces, punctuation.

    Lightweight — no external dependencies (hazm removed to avoid CUDA conflicts).
    """
    if not text:
        return text

    # Step 1: Arabic→Persian character substitution
    text = text.translate(_ARABIC_TO_PERSIAN)

    # Step 2: Strip Arabic diacritics (اعراب)
    text = _ARABIC_DIACRITICS.sub('', text)

    # Step 3: Fix common spacing issues
    # Remove space before punctuation: "سلام ." → "سلام."
    text = re.sub(r'\s+([\.،؛:؟!])', r'\1', text)
    # Ensure space after punctuation (if followed by a word char)
    text = re.sub(r'([\.،؛:؟!])(\w)', r'\1 \2', text)
    # Collapse multiple spaces
    text = re.sub(r'  +', ' ', text)

    return text.strip()


# ============================================================
# WORD CORRECTION (post-processing)
# ============================================================

_WORD_CORRECTIONS = {
    # --- Original project-specific corrections ---
    "اقامدگاه": "اقامتگاه",
    "عقامتگاه": "اقامتگاه",
    "عقامتگاهی": "اقامتگاهی",
    "حزینه": "هزینه",
    "رزروع": "رزرو",
    "پنشمبه": "پنجشنبه",
    "تقمیمش": "تقویمش",
    "مرای": "برای",
    "سرچ گردن": "سرچ کردن",
    "فل تک سرچ": "فول تکست سرچ",
    "اویلبل": "اوِیلبل",
    "جا باما": "جاباما",
    "جاواما": "جاباما",
    "بابا ما": "جاباما",
    "جواب آما": "جاباما",
    "فرایده": "فرایدی",

    # --- Character confusion (similar-sounding letters: ب↔پ، د↔ت، ز↔ذ، ر↔ب) ---
    "گفتاب": "گفتار",
    "مودل": "مدل",
    "برگذار": "برگزار",
    "برگذاری": "برگزاری",
    "فندی": "فنی",
    "اسنب": "اسنپ",
    "تیجیکالا": "دیجیکالا",
    "دیجی‌کالا": "دیجیکالا",
    "پرو سراغ": "برو سراغ",

    # --- Word splitting / merging errors ---
    "عمل کرده سیستم": "عملکرد سیستم",
    "پارامت های": "پارامترهای",
    "پارامت‌های": "پارامترهای",
    "گفتاب متر": "گفتار به متن",
    "گفتار بمتن": "گفتار به متن",

    # --- Common Whisper misrecognitions for Persian ---
    "مثلی": "متنی",
    "سراغمون": "سراغ اون",
    "دیری": "دیر",
    "جلسته": "جلسه",
    "اموز": "امروز",
    "هوم اسفند": "اسفند",
    "روابط پایتون": "رابط پایتون",
    "دوازده هام": "دوازدهم",
    "دوازده‌هام": "دوازدهم",
    "محمد رزا": "محمدرضا",
    "محمد رضا": "محمدرضا",
    "دیژیکاله ها": "دیجیکالا",
    "دیژیکالا": "دیجیکالا",
    "دیجی کالا": "دیجیکالا",

    # --- Tech terms Whisper often gets wrong ---
    "اپ دیت": "آپدیت",
    "اپلود": "آپلود",
    "دانلد": "دانلود",
    "سروور": "سرور",
    "سرویر": "سرور",
    "ریپازیتوری": "ریپوزیتوری",
    "دیتا بیس": "دیتابیس",
    "فریم ورک": "فریمورک",
    "ایندکس": "ایندکس",
    "تایم اوت": "تایم‌اوت",
    "لاگ این": "لاگین",
    "باگ فیکس": "باگ‌فیکس",

    # --- Brand names ---
    "اسنب فود": "اسنپ‌فود",
    "اسنب‌فود": "اسنپ‌فود",
    "تلگرم": "تلگرام",
    "واتس اپ": "واتساپ",
    "واتس‌اپ": "واتساپ",
    "گیت هاب": "گیتهاب",
    "گیت‌هاب": "گیتهاب",

    # --- Common Persian word errors ---
    "میکروفن": "میکروفون",
    "میکروفم": "میکروفون",
}


def apply_word_corrections(text: str) -> str:
    """Fix common Whisper misrecognitions using a lookup dictionary."""
    if not text:
        return text
    # Apply multi-word corrections first (longer keys first to avoid partial matches)
    for wrong, right in sorted(_WORD_CORRECTIONS.items(), key=lambda x: -len(x[0])):
        if wrong in text:
            text = text.replace(wrong, right)
    return text


# ============================================================
# COLLOQUIAL PRESERVATION (formal → colloquial)
# ============================================================

# Whisper often formalizes colloquial Persian speech. These regex rules
# convert formal verb forms back to their colloquial equivalents.
# Order matters: longer/more-specific patterns first.
_COLLOQUIAL_RULES = [
    # ---- «می‌خواهم/میخواهم» family → «میخوام» ----
    (re.compile(r'\bمی‌?خواهم\b'), 'میخوام'),
    (re.compile(r'\bنمی‌?خواهم\b'), 'نمیخوام'),
    (re.compile(r'\bمی‌?خواهی\b'), 'میخوای'),
    (re.compile(r'\bنمی‌?خواهی\b'), 'نمیخوای'),
    (re.compile(r'\bمی‌?خواهد\b'), 'میخواد'),
    (re.compile(r'\bنمی‌?خواهد\b'), 'نمیخواد'),
    (re.compile(r'\bمی‌?خواهیم\b'), 'میخوایم'),
    (re.compile(r'\bنمی‌?خواهیم\b'), 'نمیخوایم'),

    # ---- «بخواهم» family → «بخوام» ----
    (re.compile(r'\bبخواهم\b'), 'بخوام'),
    (re.compile(r'\bبخواهی\b'), 'بخوای'),
    (re.compile(r'\bبخواهد\b'), 'بخواد'),
    (re.compile(r'\bبخواهیم\b'), 'بخوایم'),
    (re.compile(r'\bبخواهید\b'), 'بخواید'),
    (re.compile(r'\bبخواهند\b'), 'بخوان'),

    # ---- «است/هست» → «ه/ـه» (not always desired, so only specific forms) ----
    (re.compile(r'\bهستم\b'), 'هستم'),  # keep as-is (ambiguous)

    # ---- Common formal→colloquial verb endings ----
    (re.compile(r'\bمی‌?دانم\b'), 'میدونم'),
    (re.compile(r'\bنمی‌?دانم\b'), 'نمیدونم'),
    (re.compile(r'\bمی‌?دانی\b'), 'میدونی'),
    (re.compile(r'\bنمی‌?دانی\b'), 'نمیدونی'),
    (re.compile(r'\bمی‌?داند\b'), 'میدونه'),
    (re.compile(r'\bنمی‌?داند\b'), 'نمیدونه'),
    (re.compile(r'\bمی‌?دانیم\b'), 'میدونیم'),
    (re.compile(r'\bنمی‌?دانیم\b'), 'نمیدونیم'),

    # ---- «می‌توانم» family → «میتونم» ----
    (re.compile(r'\bمی‌?توانم\b'), 'میتونم'),
    (re.compile(r'\bنمی‌?توانم\b'), 'نمیتونم'),
    (re.compile(r'\bمی‌?توانی\b'), 'میتونی'),
    (re.compile(r'\bنمی‌?توانی\b'), 'نمیتونی'),
    (re.compile(r'\bمی‌?تواند\b'), 'میتونه'),
    (re.compile(r'\bنمی‌?تواند\b'), 'نمیتونه'),
    (re.compile(r'\bمی‌?توانیم\b'), 'میتونیم'),
    (re.compile(r'\bنمی‌?توانیم\b'), 'نمیتونیم'),
    (re.compile(r'\bبتوانم\b'), 'بتونم'),
    (re.compile(r'\bبتوانی\b'), 'بتونی'),
    (re.compile(r'\bبتواند\b'), 'بتونه'),
    (re.compile(r'\bبتوانیم\b'), 'بتونیم'),

    # ---- «اصلاً» → «اصن» (very common colloquial) ----
    (re.compile(r'\bاصلاً?\b'), 'اصن'),

    # ---- «آن» → «اون»، «این‌طور» → «اینجوری» etc. ----
    (re.compile(r'\bآنها\b'), 'اونا'),
    (re.compile(r'\bآن\b'), 'اون'),
    (re.compile(r'\bاین‌?طور\b'), 'اینجوری'),
    (re.compile(r'\bآن‌?طور\b'), 'اونجوری'),
    (re.compile(r'\bهمین‌?طور\b'), 'همینجوری'),
    (re.compile(r'\bچه‌?طور\b'), 'چطور'),
    (re.compile(r'\bچگونه\b'), 'چجوری'),
]


def preserve_colloquial(text: str) -> str:
    """Convert formal Persian verb forms back to colloquial.

    Whisper's training data is biased toward formal written Persian, so it
    tends to produce «میخواهم» even when the speaker said «میخوام». This
    function reverses that formalization.
    """
    if not text:
        return text
    for pattern, replacement in _COLLOQUIAL_RULES:
        text = pattern.sub(replacement, text)
    return text


# ============================================================
# HALLUCINATION FILTER
# ============================================================

def is_hallucination(text: str) -> bool:
    """Detect hallucinated or garbage transcription output."""
    if not text:
        return True
    if len(text) < 2:
        return True

    # Pure punctuation
    if re.match(r'^[\.\,\;\:\!\?\…\،\؛\؟\!\s\u200c]+$', text):
        return True

    # Single character repeated
    stripped = text.replace(" ", "").replace("\u200c", "")
    if len(set(stripped)) <= 1:
        return True

    # Phrase-level repetition: "سلام سلام سلام" or "تست تست تست"
    words = text.split()
    if len(words) >= 3:
        counts = Counter(words)
        most_common_count = counts.most_common(1)[0][1]
        # If one word appears in >60% of all words → hallucination
        if most_common_count / len(words) > 0.6:
            log.debug(f"Hallucination (repeated word): {text[:50]}")
            return True

    # Known hallucination phrases
    text_lower = text.lower().strip()
    for pattern in _HALLUCINATION_PATTERNS:
        if pattern in text_lower:
            log.debug(f"Hallucination (known pattern '{pattern}'): {text[:50]}")
            return True

    return False


# ============================================================
# AUDIO RMS NORMALIZATION
# ============================================================

def normalize_audio_volume(audio, target_rms=0.1):
    """Normalize audio volume using RMS normalization.

    Ensures consistent input volume regardless of mic type or speaking volume.
    """
    rms = np.sqrt(np.mean(audio ** 2))
    if rms < 1e-6:  # silence
        return audio
    gain = target_rms / rms
    # Limit gain to prevent noise amplification (max ~30dB boost)
    gain = min(gain, 30.0)
    return np.clip(audio * gain, -1.0, 1.0).astype(np.float32)


# ============================================================
# KEYBOARD HOOK THREAD (Windows; macOS version comes from platform_macos)
# ============================================================

if IS_WIN:
    class KeyboardHookThread(threading.Thread):
        """Low-level Windows keyboard hook to capture G key globally."""

        _SetWindowsHookExW = ctypes.windll.user32.SetWindowsHookExW
        _SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, ctypes.wintypes.HMODULE, ctypes.wintypes.DWORD]
        _SetWindowsHookExW.restype = ctypes.c_void_p

        _UnhookWindowsHookEx = ctypes.windll.user32.UnhookWindowsHookEx
        _UnhookWindowsHookEx.argtypes = [ctypes.c_void_p]
        _UnhookWindowsHookEx.restype = ctypes.wintypes.BOOL

        _CallNextHookEx = ctypes.windll.user32.CallNextHookEx
        _CallNextHookEx.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM]
        _CallNextHookEx.restype = ctypes.c_long

        _GetMessageW = ctypes.windll.user32.GetMessageW
        _GetMessageW.argtypes = [ctypes.POINTER(ctypes.wintypes.MSG), ctypes.wintypes.HWND, ctypes.c_uint, ctypes.c_uint]
        _GetMessageW.restype = ctypes.wintypes.BOOL

        _TranslateMessage = ctypes.windll.user32.TranslateMessage
        _TranslateMessage.argtypes = [ctypes.POINTER(ctypes.wintypes.MSG)]
        _TranslateMessage.restype = ctypes.wintypes.BOOL

        _DispatchMessageW = ctypes.windll.user32.DispatchMessageW
        _DispatchMessageW.argtypes = [ctypes.POINTER(ctypes.wintypes.MSG)]
        _DispatchMessageW.restype = ctypes.c_long

        _GetModuleHandleW = ctypes.windll.kernel32.GetModuleHandleW
        _GetModuleHandleW.argtypes = [ctypes.wintypes.LPCWSTR]
        _GetModuleHandleW.restype = ctypes.wintypes.HMODULE

        _GetAsyncKeyState = ctypes.windll.user32.GetAsyncKeyState
        _GetAsyncKeyState.argtypes = [ctypes.c_int]
        _GetAsyncKeyState.restype = ctypes.c_short

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
            self._hook = None
            self._hook_proc = None
            self._held_mode = None
            self._thread_id = None
            self.captured_hwnd = 0

        def run(self):
            self._thread_id = kernel32.GetCurrentThreadId()
            log.info(f"Keyboard hook thread started (tid={self._thread_id})")

            def low_level_handler(nCode, wParam, lParam):
                try:
                    if nCode >= 0:
                        kb = ctypes.cast(lParam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                        if kb.vkCode in (VK_G, VK_ASSISTANT):
                            mode = "dictation" if kb.vkCode == VK_G else "assistant"
                            enabled = (
                                self.is_enabled_func() if mode == "dictation"
                                else self.assistant_enabled_func()
                            )
                            if enabled:
                                ctrl = (self._GetAsyncKeyState(0x11) & 0x8000) != 0
                                alt = (self._GetAsyncKeyState(0x12) & 0x8000) != 0
                                shift = (self._GetAsyncKeyState(0x10) & 0x8000) != 0
                                win = ((self._GetAsyncKeyState(0x5B) & 0x8000) != 0 or
                                       (self._GetAsyncKeyState(0x5C) & 0x8000) != 0)

                                if ctrl or alt or shift or win:
                                    return self._CallNextHookEx(self._hook, nCode, wParam, lParam)

                                if wParam in (WM_KEYDOWN, WM_SYSKEYDOWN):
                                    if self._held_mode is None:
                                        self._held_mode = mode
                                        self.captured_hwnd = user32.GetForegroundWindow()
                                        log.info(
                                            f"Hook captured mode={mode} "
                                            f"target hwnd={self.captured_hwnd}"
                                        )
                                        callback = (
                                            self.on_press if mode == "dictation"
                                            else self.on_assistant_press
                                        )
                                        if callback is not None:
                                            callback()
                                    return 1
                                elif wParam in (WM_KEYUP, WM_SYSKEYUP):
                                    if self._held_mode == mode:
                                        self._held_mode = None
                                        callback = (
                                            self.on_release if mode == "dictation"
                                            else self.on_assistant_release
                                        )
                                        if callback is not None:
                                            callback()
                                    return 1
                except Exception as e:
                    log.error(f"Hook handler error: {e}")
                return self._CallNextHookEx(self._hook, nCode, wParam, lParam)

            self._hook_proc = HOOKPROC(low_level_handler)

            h_mod_attempts = []
            try:
                python_dll = f"python{sys.version_info.major}{sys.version_info.minor}.dll"
                h = kernel32.GetModuleHandleW(python_dll)
                if h:
                    h_mod_attempts.append((h, python_dll))
            except Exception:
                pass

            h_mod_attempts.append((kernel32.GetModuleHandleW(None), "exe"))

            try:
                h = kernel32.GetModuleHandleW("user32.dll")
                if h:
                    h_mod_attempts.append((h, "user32.dll"))
            except Exception:
                pass

            h_mod_attempts.append((0, "NULL"))

            for h_mod, h_name in h_mod_attempts:
                self._hook = self._SetWindowsHookExW(
                    WH_KEYBOARD_LL,
                    self._hook_proc,
                    h_mod,
                    0,
                )
                if self._hook:
                    log.info(f"Hook installed with hMod={h_name} (handle={h_mod})")
                    break
                err = ctypes.GetLastError()
                log.warning(f"Hook failed with hMod={h_name}: error={err}")

            if not self._hook:
                err_code = ctypes.GetLastError()
                log.error(f"SetWindowsHookExW failed! GetLastError={err_code}")
                log.error("Try running as Administrator")
                return

            log.info(
                "Keyboard hook installed successfully! "
                f"(dictation={HOTKEY_LABEL}, assistant={ASSISTANT_HOTKEY_LABEL})"
            )

            msg = ctypes.wintypes.MSG()
            while self._GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
                self._TranslateMessage(ctypes.byref(msg))
                self._DispatchMessageW(ctypes.byref(msg))

            log.info("Keyboard hook message loop ended")

        def stop(self):
            if self._hook:
                self._UnhookWindowsHookEx(self._hook)
                self._hook = None
                log.info("Keyboard hook removed")
            if self._thread_id:
                user32.PostThreadMessageW(self._thread_id, 0x0012, 0, 0)


# ============================================================
# RECORDING THREAD
# ============================================================

class RecordingThread(threading.Thread):
    """Records audio from the microphone in a background thread."""

    def __init__(self):
        super().__init__(daemon=True)
        self.frames = []
        self.is_recording = False
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._pa = None
        self._stream = None

    def run(self):
        log.info("Recording started")
        try:
            self._pa = pyaudio.PyAudio()
            self._stream = self._pa.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=SAMPLE_RATE,
                input=True,
                frames_per_buffer=CHUNK_SIZE,
            )
            self.is_recording = True
            while not self._stop_event.is_set():
                try:
                    data = self._stream.read(CHUNK_SIZE, exception_on_overflow=False)
                    with self._lock:
                        self.frames.append(data)
                except OSError as e:
                    log.warning(f"Audio read error: {e}")
                    break
        except Exception as e:
            log.error(f"Recording init error: {e}")
            self.is_recording = False
        finally:
            if self._stream:
                try:
                    self._stream.stop_stream()
                    self._stream.close()
                except Exception:
                    pass
            if self._pa:
                try:
                    self._pa.terminate()
                except Exception:
                    pass
            log.info("Recording stopped")

    def stop_recording(self):
        self._stop_event.set()
        self.is_recording = False

    def get_audio_snapshot(self):
        """Get a copy of current audio frames (for real-time transcription)."""
        with self._lock:
            if not self.frames:
                return None
            raw = b"".join(self.frames)
        audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        duration = len(audio) / SAMPLE_RATE
        if duration < MIN_RECORDING_DURATION:
            return None
        return audio

    def get_audio_data(self):
        """Get final audio data after recording stops."""
        return self.get_audio_snapshot()


# ============================================================
# TRANSCRIPTION HELPERS
# ============================================================

class CloudModel:
    """Stand-in 'model' for the online backend. Holds the provider + API key so
    the transcription path can route to cloud_engine instead of a local Whisper
    model. Lets the rest of the widget treat cloud and offline uniformly."""
    is_cloud = True

    def __init__(self, provider, api_key):
        self.provider = provider
        self.api_key = api_key


def _postprocess_text(txt: str, language: str) -> str:
    """Apply Persian normalization / corrections / colloquial preservation.

    Shared by the offline (per-segment) and cloud (whole-text) paths.
    FA: always. DUAL: only when the text contains Persian script.
    """
    if language == "fa":
        txt = normalize_persian(txt)
        txt = apply_word_corrections(txt)
        txt = preserve_colloquial(txt)
    elif language == "dual":
        if _has_persian_chars(txt):
            txt = normalize_persian(txt)
            txt = apply_word_corrections(txt)
            txt = preserve_colloquial(txt)
    return txt


def transcribe_cloud(cloud_model, audio_data, language) -> str:
    """Transcribe via the online provider, then apply the same Persian
    post-processing the offline path uses, so output quality is consistent."""
    audio_data = normalize_audio_volume(audio_data)
    raw = cloud_engine.transcribe(
        audio_data, language,
        api_key=cloud_model.api_key,
        provider=cloud_model.provider,
        sample_rate=SAMPLE_RATE,
    )
    if not raw or is_hallucination(raw):
        return ""
    text = _postprocess_text(raw, language)
    return re.sub(r"  +", " ", text).strip()


def transcribe_audio(model, audio_data, language, audio_duration=None):
    """Run transcription and return cleaned text.

    Language modes:
      "fa"   — Persian only. Model forced to fa, Persian prompt & normalization.
      "en"   — English only. Model forced to en, English prompt, no Persian normalization.
      "dual" — Bilingual FA+EN. Uses multilingual=True for per-segment language detection.

    If `model` is a CloudModel, transcription is delegated to the online provider.
    """

    # Online backend: delegate to the cloud provider.
    if isinstance(model, CloudModel):
        return transcribe_cloud(model, audio_data, language)

    # RMS-normalize audio volume for consistent input regardless of mic/volume
    audio_data = normalize_audio_volume(audio_data)

    # Domain-vocabulary prompts — include brand names, colloquial words, and loanwords
    # so Whisper biases toward correct spellings.
    # IMPORTANT: Do NOT use full sentences — Whisper may hallucinate them as output!
    initial_prompt = None
    whisper_language = language  # what we pass to model.transcribe(language=...)
    multilingual_flag = False
    temperature_val = 0.0  # single-pass beam search (fastest)

    if language == "fa":
        # Rich vocabulary prompt: colloquial forms, tech terms, brand names, punctuation.
        # Whisper uses this to bias its decoder toward correct spellings.
        # Keep as comma-separated words/phrases — NOT full sentences (avoids hallucination).
        initial_prompt = (
            "خب، ببین، میخوام، نمیدونم، چجوری، بخوایم، اصن، دیگه، همینه، "
            "میشه، نمیشه، بگم، میگم، میکنیم، میریم، بریم، کردیم، "
            "عملکرد، گفتار به متن، پارامترهای، تنظیمات، فریمورک، پایتون، "
            "مدل، ویسپر، دیتابیس، سرور، ریپوزیتوری، گیتهاب، "
            "اسنپ، دیجیکالا، تلگرام، واتساپ، جاباما، "
            "اقامتگاه، رزرو، میزبان، مهمان، هزینه، تقویم، برگزار، "
            "پنجشنبه، جمعه، اسفند، فروردین، "
            "سرچ کردن، فول تکست سرچ، بوکینگ، ایونت، فیچر، "
            "فنی، متنی، امروز، عملکرد."
        )
        whisper_language = "fa"
    elif language == "en":
        initial_prompt = (
            "Okay, so, let me, I want to, basically, "
            "Whisper, Python, framework, faster-whisper, database, server, GitHub, "
            "Snapp, Digikala, Jabama, accommodation, booking, reserve, available, "
            "full text search, event, feature, calendar, parameters, performance."
        )
        whisper_language = "en"
    elif language == "dual":
        # CRITICAL: multilingual=True enables per-segment language detection.
        # Without it, language=None detects once for the entire audio and
        # transcribes everything in that single language — breaking code-switching.
        initial_prompt = (
            "خب، ببین، میخوام، نمیدونم، عملکرد، پارامترهای، فریمورک، "
            "اسنپ، دیجیکالا، جاباما، اقامتگاه، رزرو، برگزار، "
            "Whisper, Python, framework, database, server, GitHub, "
            "booking, available, full text search, event, feature."
        )
        whisper_language = None  # auto-detect per segment
        multilingual_flag = True
        # Wider temperature fallback for mixed-language audio
        temperature_val = [0.0, 0.2, 0.4, 0.6]

    # For short recordings (<5s), disable condition_on_previous_text to prevent
    # hallucination loops — there's no meaningful "previous text" context.
    use_condition_on_prev = True
    if audio_duration is not None and audio_duration < 5.0:
        use_condition_on_prev = False

    segments, info = model.transcribe(
        audio_data,
        language=whisper_language,
        beam_size=5,
        best_of=5,
        vad_filter=True,
        vad_parameters=dict(
            threshold=0.3,                 # lower = more sensitive to quiet speech
            min_silence_duration_ms=250,   # shorter = better pause segmentation
            speech_pad_ms=500,             # wider padding keeps word edges intact
            min_speech_duration_ms=80,     # don't discard very short utterances
        ),
        initial_prompt=initial_prompt,
        repetition_penalty=1.2,
        no_repeat_ngram_size=0,
        no_speech_threshold=0.5,           # higher = stricter silence detection (less hallucination)
        condition_on_previous_text=use_condition_on_prev,
        temperature=temperature_val,
        multilingual=multilingual_flag,
    )

    text_parts = []
    for segment in segments:
        txt = segment.text.strip()
        if is_hallucination(txt):
            log.debug(f"Filtered hallucination: {txt[:50]}")
            continue
        # Normalize Persian text (Arabic→Persian chars, diacritics, spacing).
        txt = _postprocess_text(txt, language)
        text_parts.append(txt)

    result = " ".join(text_parts).strip()

    # Final cleanup: collapse multiple spaces
    result = re.sub(r'  +', ' ', result)

    return result


def _has_persian_chars(text: str) -> bool:
    """Check if text contains Persian/Arabic script characters."""
    for ch in text:
        if '\u0600' <= ch <= '\u06FF' or '\uFB50' <= ch <= '\uFDFF' or '\uFE70' <= ch <= '\uFEFF':
            return True
    return False


# ============================================================
# REAL-TIME TRANSCRIPTION THREAD
# ============================================================

class RealtimeTranscriber(threading.Thread):
    """Periodically transcribes audio while recording is active."""

    def __init__(self, model, recording_thread, language, on_partial, on_error):
        super().__init__(daemon=True)
        self.model = model
        self.recording_thread = recording_thread
        self.language = language
        self.on_partial = on_partial
        self.on_error = on_error
        self._stop_event = threading.Event()

    def run(self):
        log.info("Real-time transcriber started")
        while not self._stop_event.is_set():
            self._stop_event.wait(REALTIME_CHUNK_SEC)
            if self._stop_event.is_set():
                break
            audio = self.recording_thread.get_audio_snapshot()
            if audio is None:
                continue
            try:
                t0 = time.time()
                dur = len(audio) / SAMPLE_RATE
                text = transcribe_audio(self.model, audio, self.language, audio_duration=dur)
                elapsed = time.time() - t0
                log.debug(f"Real-time partial ({elapsed:.1f}s): {text[:60]}")
                if text and not is_hallucination(text):
                    self.on_partial(text)
            except Exception as e:
                log.warning(f"Real-time transcription error: {e}")

    def stop(self):
        self._stop_event.set()


# ============================================================
# MODEL LOADING (MUST happen before PyQt6 imports!)
# ============================================================

if IS_WIN:
    def _check_cuda_lightweight():
        """Fast CUDA availability check without importing torch (~0s vs ~3s).

        Uses ctypes to probe the NVIDIA CUDA driver DLL directly.
        Returns (cuda_ok, gpu_info_str) — gpu_info_str is for logging only.
        """
        try:
            cuda_dll = ctypes.CDLL("nvcuda.dll")
            result = cuda_dll.cuInit(0)
            if result != 0:
                return False, None
            count = ctypes.c_int(0)
            cuda_dll.cuDeviceGetCount(ctypes.byref(count))
            if count.value == 0:
                return False, None
            name_buf = ctypes.create_string_buffer(256)
            cuda_dll.cuDeviceGetName(name_buf, 256, 0)
            gpu_name = name_buf.value.decode("utf-8", errors="replace")
            mem = ctypes.c_size_t(0)
            cuda_dll.cuDeviceTotalMem_v2(ctypes.byref(mem), 0)
            vram_gb = mem.value / (1024 ** 3)
            return True, f"{gpu_name} ({vram_gb:.1f} GB VRAM)"
        except (OSError, AttributeError):
            return False, None
# On macOS, _check_cuda_lightweight is imported from platform_macos (always returns CPU).


def load_model_sync(progress_callback=None):
    """Load the faster-whisper model.

    CRITICAL: This must be called BEFORE importing PyQt6 / creating
    QApplication. CTranslate2's CUDA backend segfaults if Qt's OpenGL
    context is initialized first.
    """

    def report(msg):
        log.info(msg)
        if progress_callback:
            progress_callback(msg)

    report("Importing faster-whisper...")

    # Resolve config values. DEVICE may be "auto" | "cuda" | "cpu".
    device = DEVICE
    compute_type = COMPUTE_TYPE
    model_size = MODEL_SIZE

    # If the user explicitly chose CPU, honor it — skip the GPU probe entirely.
    if device == "cpu":
        log.info("Config forces CPU (user choice).")
        report("Using CPU (configured)...")
        if compute_type == "auto":
            compute_type = "int8"
    else:
        # device is "auto" or "cuda": probe for CUDA and fall back if absent.
        log.info("Checking GPU availability (lightweight)...")
        cuda_ok, gpu_info = _check_cuda_lightweight()
        if cuda_ok:
            log.info(f"GPU OK: {gpu_info}")
            report(f"GPU: {gpu_info}")
            device = "cuda"
            if compute_type == "auto":
                compute_type = "float16"
        else:
            # No CUDA. macOS has no MPS backend either, so CPU + int8.
            # int8 quant ≈ float16 quality (within ~0.2% WER) — accuracy preserved.
            if IS_MAC:
                log.info(f"Apple Silicon detected: {gpu_info or 'M-series CPU'}")
                report(f"CPU (Apple Silicon): {gpu_info}")
            else:
                log.warning("CUDA not available, falling back to CPU")
                report("No GPU, using CPU...")
            device = "cpu"
            if compute_type == "auto":
                compute_type = "int8"

    # Safety: any unresolved "auto" compute_type defaults by device.
    if compute_type == "auto":
        compute_type = "float16" if device == "cuda" else "int8"

    # Ensure model is downloaded (skips subprocess if already cached)
    log.info(f"Loading model: {model_size} on {device} ({compute_type})")
    report(f"Downloading {model_size}...")
    cached_path = _ensure_model_downloaded(model_size, report)

    model_id = cached_path if cached_path else model_size
    log.info(f"Initializing model in-process from: {model_id}")
    report(f"Loading {model_size} on {device}...")

    from faster_whisper import WhisperModel

    t0 = time.time()
    try:
        # cpu_threads=0 means "use all available cores" — best for M1 Pro (8 cores)
        # and Windows CPU fallback. Ignored when device=cuda.
        kwargs = {"device": device, "compute_type": compute_type}
        if device == "cpu":
            kwargs["cpu_threads"] = 0
        model = WhisperModel(model_id, **kwargs)
    except Exception as e:
        err_str = str(e)
        log.error(f"WhisperModel init failed: {err_str}")
        if device == "cuda" and ("cuda" in err_str.lower() or "gpu" in err_str.lower()
                                 or "ctranslate2" in err_str.lower()):
            log.info("Retrying with CPU...")
            report("GPU failed, trying CPU...")
            model = WhisperModel(
                "medium" if not IS_MAC else model_size,
                device="cpu",
                compute_type="int8",
                cpu_threads=0,
            )
        else:
            raise

    elapsed = time.time() - t0
    log.info(f"Model loaded in {elapsed:.1f}s")
    report("Model ready!")
    return model


def _is_model_cached(model_size):
    """Check if the model is already in the HuggingFace cache.

    Returns the cache path if found, None otherwise.
    Avoids the expensive subprocess import of torch+faster_whisper (~87s).
    """
    import glob as _glob

    # HuggingFace cache: respect env var, fallback to ~/.cache/huggingface/hub
    cache_root = os.environ.get(
        "HUGGINGFACE_HUB_CACHE",
        os.path.join(os.path.expanduser("~"), ".cache", "huggingface", "hub"),
    )

    # faster-whisper model repos follow the pattern: *--faster-whisper-{model_size}
    pattern = os.path.join(
        cache_root,
        f"models--*--faster-whisper-{model_size}",
        "snapshots",
        "*",
    )
    matches = _glob.glob(pattern)
    if matches:
        # Return the first snapshot directory that contains model files
        for snapshot_dir in matches:
            model_bin = os.path.join(snapshot_dir, "model.bin")
            if os.path.isfile(model_bin):
                return snapshot_dir
    return None


def _ensure_model_downloaded(model_size, report):
    """Download the model in a subprocess (only if not already cached).

    Returns the cached path if found, None otherwise (WhisperModel will resolve it).
    """

    # Fast path: check local cache first to avoid slow subprocess (~87s import overhead)
    cached_path = _is_model_cached(model_size)
    if cached_path:
        log.info(f"Model already cached at: {cached_path}")
        report("Model cached!")
        return cached_path

    log.info("Model not in cache, downloading via subprocess...")
    script = f"""
import sys, os
os.environ['CT2_VERBOSE'] = '0'
try:
    from faster_whisper.utils import download_model
    path = download_model("{model_size}")
    print("MODEL_PATH:" + path)
except Exception as e:
    print("MODEL_ERROR:" + str(e), file=sys.stderr)
    sys.exit(1)
"""
    python_exe = sys.executable
    log.info(f"Running model download subprocess: {python_exe}")

    try:
        result = subprocess.run(
            [python_exe, "-c", script],
            capture_output=True,
            text=True,
            timeout=600,
            cwd=os.path.dirname(os.path.abspath(__file__)),
        )

        stdout = result.stdout.strip()
        stderr = result.stderr.strip()

        if result.returncode == 0:
            for line in stdout.split("\n"):
                if line.startswith("MODEL_PATH:"):
                    model_path = line.split("MODEL_PATH:", 1)[1]
                    log.info(f"Model downloaded/cached at: {model_path}")
                    report("Model downloaded!")
                    return model_path
            log.info("Model download subprocess completed successfully")
            report("Model downloaded!")
        else:
            log.warning(f"Model download subprocess failed (rc={result.returncode})")
            if stderr:
                log.warning(f"Subprocess stderr: {stderr[:500]}")
            log.info("Will attempt direct model loading anyway...")
            report("Download check done, loading...")

    except subprocess.TimeoutExpired:
        log.warning("Model download subprocess timed out (10 min)")
        report("Download timeout, trying direct load...")
    except FileNotFoundError:
        log.warning(f"Python executable not found: {python_exe}")
        report("Loading model directly...")
    except Exception as e:
        log.warning(f"Model download subprocess error: {e}")
        report("Loading model directly...")

    return None


# ============================================================
# PRE-FLIGHT CHECKS
# ============================================================

def check_microphone():
    """Open the input briefly so macOS requests permission on first launch."""
    pa = None
    stream = None
    try:
        pa = pyaudio.PyAudio()
        info = pa.get_default_input_device_info()
        mic_name = info.get("name", "Unknown")
        stream = pa.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=SAMPLE_RATE,
            input=True,
            frames_per_buffer=CHUNK_SIZE,
        )
        log.info(f"Microphone OK: {mic_name}")
        return True
    except Exception as e:
        log.error(f"Microphone error: {e}")
        log.error("Make sure a microphone is connected and you've granted microphone access.")
        if IS_MAC:
            log.error("System Settings -> Privacy & Security -> Microphone")
        else:
            log.error("Windows Settings -> Privacy -> Microphone -> Allow apps to access")
        return False
    finally:
        if stream is not None:
            try:
                stream.stop_stream()
                stream.close()
            except Exception:
                pass
        if pa is not None:
            try:
                pa.terminate()
            except Exception:
                pass


if IS_WIN:
    def check_admin():
        """Check if running with admin privileges."""
        try:
            is_admin = ctypes.windll.shell32.IsUserAnAdmin()
            if is_admin:
                log.info("Running as Administrator")
            else:
                log.warning("NOT running as Administrator!")
                log.warning("Keyboard hook may fail. Right-click run.bat -> Run as administrator")
            return bool(is_admin)
        except Exception:
            return False
# On macOS check_admin is imported from platform_macos (checks Accessibility permission).


# ============================================================
# EXCEPTION HANDLERS
# ============================================================

def global_exception_handler(exc_type, exc_value, exc_tb):
    """Catch any unhandled exceptions and log them."""
    log.error("=" * 40)
    log.error("UNHANDLED EXCEPTION!")
    log.error("".join(traceback.format_exception(exc_type, exc_value, exc_tb)))
    log.error("=" * 40)


def thread_exception_handler(args):
    """Catch unhandled exceptions in any thread (Python 3.8+)."""
    log.error("=" * 40)
    log.error(f"UNHANDLED THREAD EXCEPTION in {args.thread.name}!")
    if args.exc_value:
        log.error("".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)))
    else:
        log.error(f"Exception type: {args.exc_type}")
    log.error("=" * 40)


# ============================================================
# MAIN — PyQt6 imports happen HERE, AFTER model loading
# ============================================================

def main():
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    os.environ.setdefault("CT2_VERBOSE", "0")

    sys.excepthook = global_exception_handler
    threading.excepthook = thread_exception_handler

    log.info("=" * 50)
    log.info("Guya starting...")
    log.info(f"Python: {sys.version}")
    log.info(f"Model: {MODEL_SIZE} | Device: {DEVICE} | Compute: {COMPUTE_TYPE}")
    log.info(f"Language: {LANGUAGE}")
    log.info(f"Real-time chunk: {REALTIME_CHUNK_SEC}s")
    log.info(f"Log file: {LOG_FILE}")
    log.info("=" * 50)

    # Pre-flight checks
    check_admin()
    microphone_ok = check_microphone()

    # =========================================================
    # STEP 1: Prepare the model BEFORE importing PyQt6
    # CTranslate2 CUDA segfaults if Qt's OpenGL DLLs are loaded first.
    # Online backend: no local model to load — just hold the provider + key.
    # =========================================================
    cloud_model = None
    if MODEL_BACKEND == "cloud":
        provider = CFG["cloud"]["provider"] or cloud_engine.DEFAULT_PROVIDER
        api_key = CFG["cloud"]["api_key"]
        log.info(f"Online backend: {provider} (no local model loaded)")
        if not api_key:
            log.error("Cloud backend selected but no API key in config. "
                      "Re-run setup: python -m guya --setup")
        model = CloudModel(provider, api_key)
    else:
        log.info("Loading model BEFORE Qt (CUDA/Qt order fix)...")
        model = load_model_sync(progress_callback=lambda msg: None)
        # Hybrid: also prepare the cloud backend so the widget can switch.
        if HYBRID:
            provider = CFG["cloud"]["provider"] or cloud_engine.DEFAULT_PROVIDER
            cloud_model = CloudModel(provider, CFG["cloud"]["api_key"])
            log.info(f"Hybrid mode: offline + online ({provider}) both available")

    # =========================================================
    # STEP 2: NOW import PyQt6 (safe because CUDA is initialized)
    # =========================================================
    log.info("Importing PyQt6...")
    from PyQt6.QtWidgets import (
        QApplication,
        QLabel,
        QMenu,
        QPushButton,
        QVBoxLayout,
        QWidget,
    )
    from PyQt6.QtCore import (
        Qt, QObject, QTimer, QPoint, QPointF, QRect, QRectF, pyqtSignal, QThread
    )
    from PyQt6.QtGui import (
        QPainter, QColor, QLinearGradient, QFont, QFontMetrics,
        QPen, QBrush, QRadialGradient, QPainterPath, QAction, QCursor
    )
    log.info("PyQt6 imported successfully")

    # =========================================================
    # STEP 3: Define Qt-dependent classes (need Qt symbols in scope)
    # =========================================================

    class SignalBridge(QObject):
        status_changed = pyqtSignal(str)
        text_ready = pyqtSignal(str)
        partial_text = pyqtSignal(str)
        error = pyqtSignal(str)
        hotkey_pressed = pyqtSignal(str)
        hotkey_released = pyqtSignal(str)

    class TranscriptionThread(QThread):
        """Runs final Whisper transcription in a background QThread."""
        finished = pyqtSignal(str)
        error = pyqtSignal(str)

        def __init__(self, model, audio_data, language):
            super().__init__()
            self.model = model
            self.audio_data = audio_data
            self.language = language

        def run(self):
            try:
                t0 = time.time()
                dur = len(self.audio_data) / SAMPLE_RATE
                text = transcribe_audio(self.model, self.audio_data, self.language, audio_duration=dur)
                elapsed = time.time() - t0
                log.info(f"Final transcription ({elapsed:.1f}s): {text[:80]}")
                self.finished.emit(text)
            except Exception as e:
                log.error(f"Transcription error: {e}")
                self.error.emit(str(e))

    class AssistantCommandThread(QThread):
        """Run filesystem search/launch work without blocking widget painting."""
        finished = pyqtSignal(object)
        error = pyqtSignal(str)

        def __init__(self, assistant, text):
            super().__init__()
            self.assistant = assistant
            self.text = text

        def run(self):
            try:
                self.finished.emit(self.assistant.handle(self.text))
            except Exception as e:
                log.error(f"Assistant command error: {e}")
                self.error.emit(str(e))

    class SearchResultsPopup(QWidget):
        """Non-activating, voice-first list of ambiguous file results."""

        option_selected = pyqtSignal(int)
        cancel_requested = pyqtSignal()

        def __init__(self):
            super().__init__()
            flags = (
                Qt.WindowType.FramelessWindowHint
                | Qt.WindowType.WindowStaysOnTopHint
                | Qt.WindowType.WindowDoesNotAcceptFocus
            )
            if not IS_MAC:
                flags |= Qt.WindowType.Tool
            self.setWindowFlags(flags)
            self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
            self.setObjectName("searchResultsPopup")
            self.setAccessibleName("Guya file choices")
            self.setStyleSheet(
                """
                QWidget#searchResultsPopup {
                    background: #15191f;
                    border: 1px solid #38414d;
                    border-radius: 14px;
                }
                QLabel {
                    color: #f1f5f9;
                    background: transparent;
                    border: none;
                }
                QLabel#choiceTitle {
                    color: #8fd3ff;
                    font-weight: 700;
                    font-size: 13px;
                }
                QPushButton#choiceItem {
                    color: #f1f5f9;
                    background: #20262e;
                    border: 1px solid #323b46;
                    border-radius: 9px;
                    padding: 8px 10px;
                    font-size: 12px;
                    text-align: left;
                }
                QPushButton#choiceItem:hover {
                    border-color: #2dd4bf;
                    background: #26333a;
                }
                QPushButton#choiceCancel {
                    color: #cbd5e1;
                    background: transparent;
                    border: 1px solid #38414d;
                    border-radius: 8px;
                    padding: 6px;
                }
                QLabel#choiceHint {
                    color: #aab4c0;
                    font-size: 11px;
                }
                """
            )
            self._layout = QVBoxLayout(self)
            self._layout.setContentsMargins(12, 12, 12, 12)
            self._layout.setSpacing(7)

        def show_results(self, paths, language, anchor):
            while self._layout.count():
                item = self._layout.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()

            title = QLabel(
                "یک فایل را انتخاب کنید"
                if language == "fa"
                else "Choose a file"
            )
            title.setObjectName("choiceTitle")
            title.setAccessibleName(title.text())
            self._layout.addWidget(title)

            for number, path in enumerate(paths[:3], 1):
                location = path.parent.name or str(path.parent)
                text = f"{number}.  {path.name}\n     {location}"
                button = QPushButton(text)
                button.setObjectName("choiceItem")
                button.setCursor(Qt.CursorShape.PointingHandCursor)
                button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                button.setAccessibleName(
                    f"Option {number}: {path.name}, in {location}"
                )
                button.clicked.connect(
                    lambda _checked=False, index=number - 1:
                    self.option_selected.emit(index)
                )
                self._layout.addWidget(button)

            hint = QLabel(
                "روی گزینه بزنید یا بگویید اول، دوم، سوم یا لغو"
                if language == "fa"
                else "Click an option, or say first, second, third, or cancel"
            )
            hint.setObjectName("choiceHint")
            hint.setWordWrap(True)
            hint.setAccessibleName(hint.text())
            self._layout.addWidget(hint)

            cancel = QPushButton("لغو" if language == "fa" else "Cancel")
            cancel.setObjectName("choiceCancel")
            cancel.setCursor(Qt.CursorShape.PointingHandCursor)
            cancel.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            cancel.setAccessibleName(cancel.text())
            cancel.clicked.connect(self.cancel_requested.emit)
            self._layout.addWidget(cancel)

            width = 420
            height = 116 + min(len(paths), 3) * 57
            self.setFixedSize(width, height)
            screen = QApplication.primaryScreen()
            available = screen.availableGeometry() if screen else anchor
            x = anchor.center().x() - width // 2
            y = anchor.bottom() + 10
            x = max(available.left() + 8, min(x, available.right() - width - 8))
            if y + height > available.bottom() - 8:
                y = anchor.top() - height - 10
            self.move(x, max(available.top() + 8, y))
            self.show()
            self.raise_()
            apply_nonactivating_style(self)

    class VoiceWidget(QWidget):
        """Minimal floating widget: collapses to a small circle, expands to a pill.

        Collapsed: small 40px circle showing only the status dot + language badge.
        Expanded: slim pill showing collapse btn, status text, toggle, and language badge.
        Auto-expands when listening/processing. Collapse is manual only (click ‹ button).
        Draggable in both collapsed and expanded modes.
        Click collapsed circle to expand. Click language badge to cycle language.
        """

        STATES = ("loading", "idle", "listening", "processing", "done")

        def __init__(self, model=None, cloud_model=None):
            super().__init__()
            # Backend setup: offline model and/or cloud model.
            self._offline_model = model if not isinstance(model, CloudModel) else None
            self._cloud_model = cloud_model or (model if isinstance(model, CloudModel) else None)
            self._hybrid = bool(self._offline_model and self._cloud_model)
            self._offline_language = OFFLINE_LANGUAGE
            if self._offline_model is not None:
                self._backend = "offline"
                self._model = self._offline_model
                self._language = self._offline_language
            else:
                self._backend = "online"
                self._model = self._cloud_model
                self._language = LANGUAGE
            self._recording_thread = None
            self._realtime_transcriber = None
            self._transcription_thread = None
            self._assistant_thread = None
            self._results_popup = SearchResultsPopup()
            self._results_popup.option_selected.connect(
                self._on_result_option_clicked
            )
            self._results_popup.cancel_requested.connect(
                lambda: self._submit_result_choice("cancel")
            )
            self._is_recording = False
            self._is_processing = False
            self._active_recording_mode = None
            self._processing_mode = "dictation"
            self._is_enabled = True         # ready to record as soon as it loads
            self._assistant_enabled = ASSISTANT_ENABLED
            self._last_audio_duration = 0.0
            self._transcription_started_at = None
            self._transcription_elapsed = 0.0
            self._assistant_command_started_at = None
            self._last_assistant_text = ""
            self._last_assistant_language = self._language
            self._last_cmd_seq = 0          # Control Panel command sync
            self._anim_tick = 0
            self._drag_pos = None
            self._press_pos = None
            self._was_dragged = False

            # Collapsed / expanded state. Hybrid needs more room for the switch.
            self._expanded = False
            self._expanded_width = 360 if self._hybrid else WIDGET_EXPANDED_WIDTH
            self._current_width = WIDGET_COLLAPSED_SIZE
            self._target_width = WIDGET_COLLAPSED_SIZE

            # Real-time state: partial text shown on widget only
            self._last_partial_text = ""

            # Target window: the window that had focus before recording started.
            # We type into this window. 0 = no target saved.
            self._target_hwnd = 0

            # Local deterministic assistant. Paths are constrained by config.
            self._assistant = AssistantService(
                roots=ASSISTANT_CFG.get("allowed_roots"),
                default_directory=ASSISTANT_CFG.get("default_directory"),
            )

            # Signal bridge
            self._bridge = SignalBridge()
            self._bridge.status_changed.connect(self._set_state)
            self._bridge.text_ready.connect(self._on_text_ready)
            self._bridge.partial_text.connect(self._on_partial_text)
            self._bridge.error.connect(self._on_error)
            self._bridge.hotkey_pressed.connect(self._handle_hotkey_press)
            self._bridge.hotkey_released.connect(self._handle_hotkey_release)

            if self._model is not None:
                self._state = "idle"
                self._label_text = self._idle_label()
                log.info(f"Model pre-loaded; backend={self._backend} hybrid={self._hybrid}")
            else:
                self._state = "loading"
                self._label_text = "Loading\u2026"

            self._setup_window()
            self._setup_animation_timer()
            self._start_keyboard_hook()

        # ---- Window Setup ----

        def _setup_window(self):
            # Qt.Tool on macOS = NSPanel; the panel hides whenever the app
            # isn't active, which kills our "always visible" UX. Skip it on
            # macOS; the Accessory activation policy already handles the
            # "no Dock icon" part.
            flags = (
                Qt.WindowType.FramelessWindowHint
                | Qt.WindowType.WindowStaysOnTopHint
                | Qt.WindowType.WindowDoesNotAcceptFocus  # Don't steal focus!
            )
            if not IS_MAC:
                flags |= Qt.WindowType.Tool
            self.setWindowFlags(flags)
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
            # Start collapsed
            self.setFixedSize(WIDGET_COLLAPSED_SIZE, WIDGET_COLLAPSED_SIZE)

            screen = QApplication.primaryScreen()
            if screen:
                geo = screen.geometry()
                x = geo.x() + (geo.width() - WIDGET_COLLAPSED_SIZE) // 2
                y = geo.y() + WIDGET_MARGIN_TOP
                self.move(x, y)

        def _expand(self):
            """Smoothly expand from circle to pill."""
            if self._expanded:
                return
            self._expanded = True
            self._target_width = self._expanded_width
            log.debug("Widget expanding")

        def _collapse(self):
            """Smoothly collapse from pill to circle."""
            if not self._expanded:
                return
            self._expanded = False
            self._target_width = WIDGET_COLLAPSED_SIZE
            log.debug("Widget collapsing")

        def _update_size(self):
            """Animate width towards target (called each animation tick)."""
            if abs(self._current_width - self._target_width) < 1.5:
                if self._current_width != self._target_width:
                    self._current_width = self._target_width
                else:
                    return  # nothing to do
            else:
                # Snappy lerp — 0.35 is quick but smooth
                self._current_width += (self._target_width - self._current_width) * 0.35

            w = int(self._current_width)
            h = WIDGET_EXPANDED_HEIGHT if w > WIDGET_COLLAPSED_SIZE + 5 else WIDGET_COLLAPSED_SIZE

            if w != self.width() or h != self.height():
                # Keep centered horizontally when resizing
                old_center_x = self.x() + self.width() // 2
                self.setFixedSize(w, h)
                new_x = old_center_x - w // 2
                self.move(new_x, self.y())
                self.update()

        def showEvent(self, event):
            """After widget is shown, apply platform-specific non-activating styling
            so the widget doesn't steal focus when clicked. On Windows that's
            WS_EX_NOACTIVATE; on macOS Qt's WindowDoesNotAcceptFocus flag handles it."""
            super().showEvent(event)
            apply_nonactivating_style(self)

        def _setup_animation_timer(self):
            self._anim_timer = QTimer(self)
            self._anim_timer.timeout.connect(self._on_animation_tick)
            self._anim_timer.start(1000 // ANIMATION_FPS)
            # Live two-way sync with the Control Panel.
            guya_runtime.clear()
            self._rt_timer = QTimer(self)
            self._rt_timer.timeout.connect(self._runtime_sync)
            self._rt_timer.start(400)

        def _runtime_sync(self):
            """Publish live state for the Control Panel, and apply its commands."""
            try:
                guya_runtime.write_state({
                    "pid": os.getpid(), "ts": time.time(),
                    "enabled": self._is_enabled, "backend": self._backend,
                    "language": self._language, "hybrid": self._hybrid,
                    "offline_language": self._offline_language,
                    "assistant_enabled": self._assistant_enabled,
                    "assistant_hotkey": ASSISTANT_HOTKEY_LABEL,
                    "microphone_ok": microphone_ok,
                    "state": self._state, "trusted": bool(is_accessibility_granted()),
                })
                cmd = guya_runtime.read_cmd()
                seq = cmd.get("seq", 0)
                if seq > self._last_cmd_seq:
                    self._last_cmd_seq = seq
                    if "enabled" in cmd and bool(cmd["enabled"]) != self._is_enabled:
                        self._toggle_enabled()
                    if "assistant_enabled" in cmd:
                        self._set_assistant_enabled(bool(cmd["assistant_enabled"]))
                    if "backend" in cmd and self._hybrid:
                        self._set_backend(cmd["backend"])
                    if "language" in cmd:
                        self._apply_language(cmd["language"])
            except Exception as e:
                log.debug(f"runtime sync: {e}")

        def _apply_language(self, lang):
            """Set a specific language live (respects the offline lock)."""
            if self._hybrid and self._backend == "offline":
                return
            if lang in ("fa", "en", "dual") and lang != self._language:
                self._language = lang
                log.info(f"Language set to {self._language_label()} (panel)")
                self.update()

        def _on_animation_tick(self):
            self._anim_tick += 1
            # Animate size changes (expand/collapse)
            self._update_size()
            if self._state in ("listening", "processing", "loading"):
                self.update()
            elif self._current_width != self._target_width:
                self.update()  # keep painting during size animation

        # ---- Keyboard Hook ----

        def _start_keyboard_hook(self):
            self._g_pressed = False
            self._assistant_pressed = False
            self._hook_thread = KeyboardHookThread(
                on_press=self._on_hotkey_press,
                on_release=self._on_hotkey_release,
                is_enabled_func=lambda: self._is_enabled,
                on_assistant_press=self._on_assistant_hotkey_press,
                on_assistant_release=self._on_assistant_hotkey_release,
                assistant_enabled_func=lambda: self._is_enabled and self._assistant_enabled,
            )
            self._hook_thread.start()

        def _on_hotkey_press(self):
            # pynput invokes this on its listener thread. A Qt signal safely
            # queues the work on the main UI thread, where recording may start.
            self._bridge.hotkey_pressed.emit("dictation")

        def _on_hotkey_release(self):
            self._bridge.hotkey_released.emit("dictation")

        def _on_assistant_hotkey_press(self):
            self._bridge.hotkey_pressed.emit("assistant")

        def _on_assistant_hotkey_release(self):
            self._bridge.hotkey_released.emit("assistant")

        def _handle_hotkey_press(self, mode):
            if mode == "assistant":
                if self._assistant_pressed:
                    return
                self._assistant_pressed = True
                # Pressing the assistant key acts like a natural "barge in":
                # stop current feedback and immediately listen for the next
                # command instead of making the user wait for the full reply.
                self._assistant.stop_speaking()
            else:
                if self._g_pressed:
                    return
                self._g_pressed = True
            self._start_recording(mode)

        def _on_result_option_clicked(self, index: int):
            words = ("first", "second", "third")
            if 0 <= index < len(words):
                self._submit_result_choice(words[index])

        def _submit_result_choice(self, choice: str):
            if self._is_recording or self._is_processing:
                return
            if not self._assistant.context.pending_options:
                self._results_popup.hide()
                return
            log.info("Assistant visual result choice: %s", choice)
            self._assistant.stop_speaking()
            self._results_popup.hide()
            self._is_processing = True
            self._set_state("processing")
            self._start_assistant_command(choice)

        def _handle_hotkey_release(self, mode):
            if mode == "assistant":
                if not self._assistant_pressed:
                    return
                self._assistant_pressed = False
            else:
                if not self._g_pressed:
                    return
                self._g_pressed = False
            self._stop_recording(mode)

        # ---- ON/OFF Toggle ----

        def _toggle_enabled(self):
            if self._state == "loading":
                return
            self._is_enabled = not self._is_enabled
            log.info(f"Toggle: {'ON' if self._is_enabled else 'OFF'}")
            if self._is_enabled:
                self._label_text = self._idle_label()
            else:
                if self._is_recording:
                    self._stop_recording()
                self._label_text = "OFF"
            self.update()

        def _set_assistant_enabled(self, enabled):
            if enabled == self._assistant_enabled:
                return
            self._assistant_enabled = enabled
            if not enabled and self._active_recording_mode == "assistant":
                self._stop_recording("assistant")
            if not enabled:
                self._results_popup.hide()
            if self._state == "idle":
                self._label_text = self._idle_label()
            log.info(f"Assistant: {'ON' if enabled else 'OFF'}")
            self.update()

        # Right-side cluster, laid out right→left:
        #   [language badge]  [backend pill (hybrid)]  [enable toggle]

        def _get_badge_rect(self):
            """Clickable rect for the language badge (rightmost)."""
            w = self.width(); h = self.height()
            badge_text = self._language_label()
            f = QFont(UI_FONT, 9); f.setWeight(QFont.Weight.DemiBold)
            badge_w = QFontMetrics(f).horizontalAdvance(badge_text) + 14
            badge_h = 18
            return QRect(w - badge_w - 8, (h - badge_h) // 2, badge_w, badge_h)

        def _get_backend_rect(self):
            """Clickable rect for the OFFLINE/ONLINE switch (hybrid only)."""
            if not self._hybrid:
                return QRect(0, 0, 0, 0)
            h = self.height()
            txt = self._backend_label()
            f = QFont(UI_FONT, 8); f.setWeight(QFont.Weight.Bold)
            bw = QFontMetrics(f).horizontalAdvance(txt) + 18
            bh = 20
            badge = self._get_badge_rect()
            return QRect(badge.x() - bw - 8, (h - bh) // 2, bw, bh)

        def _get_toggle_rect(self):
            w = self.width(); h = self.height()
            btn_w = 32; btn_h = 18
            ref = self._get_backend_rect() if self._hybrid else self._get_badge_rect()
            btn_x = ref.x() - btn_w - 10
            return QRect(btn_x, (h - btn_h) // 2, btn_w, btn_h)

        def _backend_label(self) -> str:
            return "ONLINE" if self._backend == "online" else "OFFLINE"

        def _set_backend(self, backend: str):
            if backend == self._backend:
                return
            if backend == "online" and not self._cloud_model:
                return
            if backend == "offline" and not self._offline_model:
                return
            self._backend = backend
            self._model = self._cloud_model if backend == "online" else self._offline_model
            if backend == "offline":
                # Offline is limited to the language it was set up for (e.g. EN).
                self._language = self._offline_language
            else:
                # Online (cloud large-v3) handles Persian well — default to it,
                # and the badge can cycle FA/EN/DUAL from here.
                if self._language == self._offline_language and self._offline_language == "en":
                    self._language = "fa"
            log.info(f"Backend switched to {backend} | language={self._language}")
            self.update()

        def _toggle_backend(self):
            self._set_backend("online" if self._backend == "offline" else "offline")

        # ---- Recording ----

        def _start_recording(self, mode="dictation"):
            if not self._is_enabled:
                return
            if mode == "assistant" and not self._assistant_enabled:
                return
            if self._state not in ("idle", "done"):
                return
            if self._is_processing:
                return

            log.info(f"Recording started ({mode})")
            self._is_recording = True
            self._active_recording_mode = mode
            self._last_partial_text = ""
            self._recording_start_time = time.time()

            # Use the target captured by the hook thread BEFORE Qt event loop ran.
            # On Windows: an HWND int. On macOS: an app bundle-id string (or None).
            hook_hwnd = self._hook_thread.captured_hwnd
            fallback_hwnd = get_foreground_window()
            widget_hwnd = int(self.winId()) if IS_WIN else None

            # If hook didn't capture (None/0) or it's our own widget, use fallback.
            no_hook = (hook_hwnd in (0, None)) or (IS_WIN and hook_hwnd == widget_hwnd)
            if no_hook:
                self._target_hwnd = fallback_hwnd
                log.info(f"Target (fallback): {self._target_hwnd}")
            else:
                self._target_hwnd = hook_hwnd
                log.info(f"Target (from hook): {self._target_hwnd}")

            # Drill down to the actual text control (Windows only — no-op on macOS).
            self._target_control = get_focused_control(self._target_hwnd)
            if self._target_control != self._target_hwnd:
                log.info(f"Target control: {self._target_control} (child of {self._target_hwnd})")

            # Sanity check: don't accidentally type into our own widget (Windows only).
            if IS_WIN and self._target_hwnd == widget_hwnd:
                log.warning("Target is our own widget! No external window detected.")
                self._target_hwnd = 0
                self._target_control = 0

            self._recording_thread = RecordingThread()
            self._recording_thread.start()

            # Real-time partial transcription only for the OFFLINE backend.
            # For cloud we don't fire an API request every 2s — we transcribe
            # once on release (saves requests, rate limit, and latency).
            if (
                mode != "assistant"
                and self._model is not None
                and not isinstance(self._model, CloudModel)
            ):
                transcribe_language = self._language
                self._realtime_transcriber = RealtimeTranscriber(
                    model=self._model,
                    recording_thread=self._recording_thread,
                    language=transcribe_language,
                    on_partial=lambda text: self._bridge.partial_text.emit(text),
                    on_error=lambda err: log.warning(f"RT error: {err}"),
                )
                self._realtime_transcriber.start()

            self._set_state("listening")

        def _stop_recording(self, expected_mode=None):
            if not self._is_recording:
                return
            if expected_mode and expected_mode != self._active_recording_mode:
                return
            mode = self._active_recording_mode or "dictation"
            log.info(f"Recording stopped ({mode})")
            self._is_recording = False
            self._active_recording_mode = None

            if self._realtime_transcriber:
                self._realtime_transcriber.stop()
                self._realtime_transcriber = None

            if self._recording_thread:
                self._recording_thread.stop_recording()
                self._recording_thread.join(timeout=2)
                audio_data = self._recording_thread.get_audio_data()
                self._recording_thread = None

                if audio_data is None:
                    log.info("Recording too short, ignoring")
                    self._set_state("idle")
                    return

                duration = len(audio_data) / SAMPLE_RATE
                self._last_audio_duration = duration
                log.info(f"Audio captured: {duration:.1f}s")

                self._start_transcription(audio_data, mode=mode)

        # ---- Real-time partial text ----

        def _on_partial_text(self, text: str):
            if not self._is_recording:
                return

            # Show partial text ONLY on the widget (not in target window).
            # Final text will be pasted to the target after recording stops.
            self._last_partial_text = text
            display = text[:30] + "\u2026" if len(text) > 30 else text
            self._label_text = f"\u25cf {display}"
            self.update()

        # ---- Final Transcription ----

        def _start_transcription(self, audio_data, mode="dictation"):
            if self._model is None:
                self._set_state("idle")
                return

            self._is_processing = True
            self._processing_mode = mode
            self._set_state("processing")

            # Assistant recognition follows the language badge. FA and EN force
            # Whisper to the chosen language; DUAL keeps automatic detection.
            lang = self._language
            self._last_assistant_language = lang
            self._transcription_started_at = time.time()
            self._transcription_thread = TranscriptionThread(self._model, audio_data, lang)
            self._transcription_thread.finished.connect(self._on_transcription_done)
            self._transcription_thread.error.connect(self._on_transcription_error)
            self._transcription_thread.start()

        def _on_transcription_done(self, text: str):
            if self._transcription_started_at is not None:
                self._transcription_elapsed = time.time() - self._transcription_started_at
                self._transcription_started_at = None
            if not text:
                self._is_processing = False
                log.info("No text from final transcription")
                self._set_state("idle")
                return

            log.info(f"Final text: {text[:80]}")
            if self._processing_mode == "assistant":
                self._start_assistant_command(text)
                return

            self._is_processing = False
            self._set_state("done")
            # Small delay to let the "Done" state show, then paste final text
            QTimer.singleShot(TYPE_DELAY, lambda: self._type_final_text(text))

        def _on_transcription_error(self, error_msg: str):
            self._is_processing = False
            log.error(f"Transcription error: {error_msg}")
            self._label_text = f"Error: {error_msg[:35]}"
            self._set_state("idle")

        def _start_assistant_command(self, text: str):
            log.info(f"Assistant heard: {text[:120]}")
            self._last_assistant_text = text
            self._assistant_command_started_at = time.time()
            self._assistant.set_target_app(self._target_hwnd)
            self._label_text = "Understanding command…"
            self.update()
            self._assistant_thread = AssistantCommandThread(self._assistant, text)
            self._assistant_thread.finished.connect(self._on_assistant_done)
            self._assistant_thread.error.connect(self._on_assistant_error)
            self._assistant_thread.start()

        def _on_assistant_done(self, response):
            self._is_processing = False
            self._state = "done"
            self._label_text = response.message
            self._expand()
            self.update()
            if response.options:
                self._results_popup.show_results(
                    response.options,
                    response.language,
                    self.geometry(),
                )
            else:
                self._results_popup.hide()
            log.info(
                f"Assistant result: status={response.status} "
                f"message={response.message}"
            )
            command_elapsed = (
                time.time() - self._assistant_command_started_at
                if self._assistant_command_started_at is not None
                else 0.0
            )
            self._assistant_command_started_at = None
            command = response.command
            trace = {
                "transcript": self._last_assistant_text,
                "stt_language": self._last_assistant_language,
                "response_language": response.language,
                "intent": command.intent if command else None,
                "slots": command.slots if command else {},
                "steps": [
                    {"intent": step.intent, "slots": step.slots}
                    for step in (command.steps if command else [])
                ],
                "status": response.status,
                "message": response.message,
                "path": str(response.path) if response.path else None,
                "options": [str(path) for path in response.options],
                "target_app": self._target_hwnd,
                "audio_seconds": round(self._last_audio_duration, 3),
                "transcription_ms": round(self._transcription_elapsed * 1000),
                "command_ms": round(command_elapsed * 1000),
            }
            log.info(
                "Assistant evaluation: %s",
                json.dumps(trace, ensure_ascii=False),
            )
            if ASSISTANT_SPEAK_FEEDBACK:
                self._assistant.speak(response.message, response.language)
            QTimer.singleShot(max(DONE_STATE_DURATION, 3000), self._return_to_idle)

        def _on_assistant_error(self, error_msg: str):
            self._is_processing = False
            log.error(f"Assistant error: {error_msg}")
            self._results_popup.hide()
            self._state = "done"
            self._label_text = "Assistant error"
            self.update()
            QTimer.singleShot(DONE_STATE_DURATION, self._return_to_idle)

        def _type_final_text(self, text: str):
            target = self._target_hwnd
            try:
                ok = paste_text_to_window(target, text)
                if ok:
                    log.info(f"Final text pasted ({len(text)} chars) to hwnd={target}")
                else:
                    log.warning(f"paste_text_to_window failed for hwnd={target}")
                    self._label_text = "Copied! Ctrl+V to paste"
                    self.update()
            except Exception as e:
                log.error(f"Final paste failed: {e}")
                try:
                    pyperclip.copy(text)
                except Exception:
                    pass
                self._label_text = "Copied! Ctrl+V to paste"
                self.update()

        def _on_text_ready(self, text: str):
            self._on_transcription_done(text)

        def _on_error(self, msg: str):
            self._on_transcription_error(msg)

        # ---- State Management ----

        def _set_state(self, state: str):
            old = self._state
            self._state = state
            log.debug(f"State: {old} -> {state}")
            if state == "loading":
                self._label_text = "Loading\u2026"
                self._expand()
            elif state == "idle":
                if self._is_enabled:
                    self._label_text = self._idle_label()
                else:
                    self._label_text = "OFF"
            elif state == "listening":
                self._label_text = (
                    "\u25cf Assistant listening\u2026"
                    if self._active_recording_mode == "assistant"
                    else "\u25cf Dictation listening\u2026"
                )
                self._expand()
            elif state == "processing":
                self._label_text = "Processing\u2026"
            elif state == "done":
                self._label_text = "\u2713 Done"
                QTimer.singleShot(DONE_STATE_DURATION, self._return_to_idle)
            self.update()

        def _return_to_idle(self):
            if self._state == "done":
                self._set_state("idle")

        def _idle_label(self):
            if self._assistant_enabled:
                return (
                    f"{HOTKEY_LABEL} Dictate  ·  "
                    f"{ASSISTANT_HOTKEY_LABEL} Assist"
                )
            return f"Hold {HOTKEY_LABEL} to speak"

        # ---- Language ----

        def _language_label(self) -> str:
            if self._language == "fa":
                return "FA"
            elif self._language == "en":
                return "EN"
            elif self._language == "dual":
                return "DUAL"
            return "FA"

        def _cycle_language(self):
            """Cycle FA → EN → DUAL → FA.

            In hybrid OFFLINE mode the language is locked to the offline
            language (e.g. EN); cycling only works ONLINE (or non-hybrid)."""
            if self._hybrid and self._backend == "offline":
                return  # offline is locked to its configured language
            if self._language == "fa":
                self._language = "en"
            elif self._language == "en":
                self._language = "dual"
            else:
                self._language = "fa"
            log.info(f"Language: {self._language_label()}")
            self.update()

        # ---- Context Menu ----

        def contextMenuEvent(self, event):
            menu = QMenu(self)
            menu.setStyleSheet("""
                QMenu {
                    background-color: #1a1a1a;
                    color: #cccccc;
                    border: 1px solid #333;
                    border-radius: 6px;
                    padding: 4px;
                }
                QMenu::item {
                    padding: 6px 20px;
                    border-radius: 4px;
                }
                QMenu::item:selected {
                    background-color: #333;
                }
            """)

            lang_action = QAction(f"Switch Language ({self._language_label()})", self)
            lang_action.triggered.connect(self._cycle_language)
            menu.addAction(lang_action)

            menu.addSeparator()

            quit_action = QAction("Quit", self)
            quit_action.triggered.connect(self._quit)
            menu.addAction(quit_action)

            menu.exec(event.globalPos())

        def _quit(self):
            log.info("Quitting...")
            if hasattr(self, '_hook_thread'):
                self._hook_thread.stop()
            self._results_popup.close()
            self.close()
            QApplication.quit()

        def closeEvent(self, event):
            log.info("Widget close event received")
            if hasattr(self, '_hook_thread'):
                self._hook_thread.stop()
            self._results_popup.close()
            event.accept()
            QApplication.quit()

        # ---- Mouse Events ----
        # Uses click-vs-drag detection: press stores position, release checks
        # if mouse moved more than 5px. If not, it's a click; otherwise drag.

        def _get_collapse_btn_rect(self):
            """Small collapse/minimize button at the left edge of expanded pill."""
            h = self.height()
            btn_size = 18
            return QRect(4, (h - btn_size) // 2, btn_size, btn_size)

        def mousePressEvent(self, event):
            if event.button() == Qt.MouseButton.LeftButton:
                self._drag_pos = event.globalPosition().toPoint() - self.pos()
                self._press_pos = event.globalPosition().toPoint()
                self._was_dragged = False
                event.accept()

        def mouseMoveEvent(self, event):
            if self._drag_pos is not None and event.buttons() & Qt.MouseButton.LeftButton:
                delta = event.globalPosition().toPoint() - self._press_pos
                if abs(delta.x()) > 5 or abs(delta.y()) > 5:
                    self._was_dragged = True
                if self._was_dragged:
                    self.move(event.globalPosition().toPoint() - self._drag_pos)
                event.accept()

        def mouseReleaseEvent(self, event):
            if event.button() == Qt.MouseButton.LeftButton and not self._was_dragged:
                # It was a click, not a drag — handle click actions
                pos = event.position().toPoint()
                self._handle_click(pos)
            self._drag_pos = None
            self._was_dragged = False

        def _handle_click(self, pos):
            """Process a click (not drag) at the given widget position."""
            if not self._expanded:
                # Collapsed circle: click = expand
                self._expand()
                return

            # Expanded pill: check specific areas
            # 1. Collapse button (left edge «)
            collapse_rect = self._get_collapse_btn_rect()
            if collapse_rect.contains(pos):
                self._collapse()
                return

            # 2. Toggle switch
            toggle_rect = self._get_toggle_rect()
            if toggle_rect.contains(pos):
                self._toggle_enabled()
                return

            # 3. Backend switch (hybrid only)
            if self._hybrid and self._get_backend_rect().contains(pos):
                self._toggle_backend()
                return

            # 4. Language badge
            badge_rect = self._get_badge_rect()
            if badge_rect.contains(pos):
                self._cycle_language()
                return

        # ---- Painting ----

        def paintEvent(self, event):
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)

            w = self.width()
            h = self.height()
            is_collapsed = w <= WIDGET_COLLAPSED_SIZE + 10

            if is_collapsed:
                self._paint_collapsed(painter, w, h)
            else:
                self._paint_expanded(painter, w, h)

            painter.end()

        def _paint_collapsed(self, painter, w, h):
            """Paint collapsed circle: 6-layer glass effect."""
            cx, cy = w / 2, h / 2
            r = min(w, h) / 2 - 1
            circle = QRectF(cx - r, cy - r, r * 2, r * 2)

            # Clip to circle
            clip_path = QPainterPath()
            clip_path.addEllipse(circle)
            painter.setClipPath(clip_path)

            # Layer 1: Glass base (semi-transparent dark)
            base, tint = self._get_background_colors()
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(base))
            painter.drawEllipse(circle)

            # Layer 2: State tint overlay
            painter.setBrush(QBrush(tint))
            painter.drawEllipse(circle)

            # Layer 3: Bottom inner shadow gradient (depth)
            shadow_grad = QLinearGradient(cx, cy + r * 0.3, cx, cy + r)
            shadow_grad.setColorAt(0, QColor(0, 0, 0, 0))
            shadow_grad.setColorAt(1, QColor(0, 0, 0, 60))
            painter.setBrush(QBrush(shadow_grad))
            painter.drawEllipse(circle)

            # Layer 4: Top highlight gradient (light refraction)
            highlight_grad = QLinearGradient(cx, cy - r, cx, cy - r * 0.2)
            highlight_grad.setColorAt(0, QColor(255, 255, 255, 25))
            highlight_grad.setColorAt(1, QColor(255, 255, 255, 0))
            painter.setBrush(QBrush(highlight_grad))
            painter.drawEllipse(circle)

            painter.setClipping(False)

            # Layer 5: Glass edge border (thin white, 1px)
            border_color, _ = self._get_border_color()
            pen = QPen(border_color)
            pen.setWidthF(1.0)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QRectF(cx - r + 0.5, cy - r + 0.5, r * 2 - 1, r * 2 - 1))

            # Layer 6: Status dot + glow
            dot_color = self._get_dot_color()
            dot_r = 6.0
            if self._state == "listening":
                pulse = 1.0 + 0.3 * abs(math.sin(self._anim_tick * 0.10))
                dot_r = 6.0 * pulse
            elif self._state == "loading":
                pulse = 0.5 + 0.5 * abs(math.sin(self._anim_tick * 0.06))
                dot_color = QColor(dot_color)
                dot_color.setAlphaF(pulse)

            # Glow (wider radius 3.5x)
            if self._state in ("listening", "processing", "done"):
                glow_alpha = self._get_glow_alpha()
                gc = QColor(dot_color)
                gc.setAlpha(glow_alpha)
                glow_r = dot_r * 3.5
                glow = QRadialGradient(cx, cy, glow_r)
                glow.setColorAt(0, gc)
                glow.setColorAt(1, QColor(0, 0, 0, 0))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(glow))
                painter.drawEllipse(QRectF(cx - glow_r, cy - glow_r, glow_r * 2, glow_r * 2))

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(dot_color))
            painter.drawEllipse(QRectF(cx - dot_r, cy - dot_r, dot_r * 2, dot_r * 2))

            # Language label (brighter alpha)
            lang = self._language_label()
            font = QFont(UI_FONT, 7, QFont.Weight.Bold)
            painter.setFont(font)
            painter.setPen(QColor(255, 255, 255, 110))
            painter.drawText(QRectF(0, h - 14, w, 12), Qt.AlignmentFlag.AlignCenter, lang)

        def _paint_expanded(self, painter, w, h):
            """Paint expanded pill: 8-layer glass effect."""
            radius = h / 2

            path = QPainterPath()
            path.addRoundedRect(QRectF(0, 0, w, h), radius, radius)
            painter.setClipPath(path)

            # Layer 1: Glass base
            base, tint = self._get_background_colors()
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(base))
            painter.drawPath(path)

            # Layer 2: State tint overlay
            painter.setBrush(QBrush(tint))
            painter.drawPath(path)

            # Layer 3: Horizontal glass depth gradient (subtle white at edges)
            edge_grad = QLinearGradient(0, 0, w, 0)
            edge_grad.setColorAt(0, QColor(255, 255, 255, 8))
            edge_grad.setColorAt(0.15, QColor(255, 255, 255, 0))
            edge_grad.setColorAt(0.85, QColor(255, 255, 255, 0))
            edge_grad.setColorAt(1, QColor(255, 255, 255, 8))
            painter.setBrush(QBrush(edge_grad))
            painter.drawPath(path)

            # Layer 4: Bottom inner shadow
            shadow_grad = QLinearGradient(0, h * 0.5, 0, h)
            shadow_grad.setColorAt(0, QColor(0, 0, 0, 0))
            shadow_grad.setColorAt(1, QColor(0, 0, 0, 50))
            painter.setBrush(QBrush(shadow_grad))
            painter.drawPath(path)

            # Layer 5: Top highlight line
            highlight_grad = QLinearGradient(0, 0, 0, h * 0.35)
            highlight_grad.setColorAt(0, QColor(255, 255, 255, 22))
            highlight_grad.setColorAt(1, QColor(255, 255, 255, 0))
            painter.setBrush(QBrush(highlight_grad))
            painter.drawPath(path)

            painter.setClipping(False)

            # Layer 6: Glass border (white edge + state accent)
            border_color, _ = self._get_border_color()
            pen = QPen(border_color)
            pen.setWidthF(1.0)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), radius, radius)

            # Layer 7: Collapse button (glass mini-panel with subtle border)
            cb = self._get_collapse_btn_rect()
            cb_path = QPainterPath()
            cb_path.addRoundedRect(QRectF(cb.x(), cb.y(), cb.width(), cb.height()), 4, 4)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(255, 255, 255, 10)))
            painter.drawPath(cb_path)
            # Subtle border on collapse button
            pen_cb = QPen(QColor(255, 255, 255, 18))
            pen_cb.setWidthF(0.5)
            painter.setPen(pen_cb)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(QRectF(cb.x(), cb.y(), cb.width(), cb.height()), 4, 4)
            chevron_font = QFont(UI_FONT, 11, QFont.Weight.Bold)
            painter.setFont(chevron_font)
            painter.setPen(QColor(255, 255, 255, 120))
            painter.drawText(QRect(cb.x(), cb.y(), cb.width(), cb.height()),
                             Qt.AlignmentFlag.AlignCenter, "\u2039")

            # Layer 8: Status dot, text, toggle, badge — updated colors
            # Toggle switch
            self._draw_toggle(painter, w, h)

            # Status dot
            dot_x = 28
            dot_y = h // 2
            dot_r = 4.0
            dot_color = self._get_dot_color()

            if self._state == "listening":
                pulse = 1.0 + 0.3 * abs(math.sin(self._anim_tick * 0.10))
                dot_r = 4.0 * pulse

                # Glow (wider 3.5x)
                glow_alpha = self._get_glow_alpha()
                gc = QColor(dot_color)
                gc.setAlpha(glow_alpha)
                glow_r = dot_r * 3.5
                glow = QRadialGradient(float(dot_x), float(dot_y), glow_r)
                glow.setColorAt(0, gc)
                glow.setColorAt(1, QColor(0, 0, 0, 0))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(glow))
                painter.drawEllipse(QPointF(dot_x, dot_y), glow_r, glow_r)

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(dot_color))
            painter.drawEllipse(QPointF(dot_x, dot_y), dot_r, dot_r)

            # Label text
            text_color = self._get_text_color()
            font = QFont(UI_FONT, 11)
            font.setWeight(QFont.Weight.Medium)
            painter.setFont(font)
            painter.setPen(text_color)
            text_x = int(dot_x + dot_r + 10)
            text_right_limit = self._get_toggle_rect().x() - 4
            text_rect = QRect(text_x, 0, text_right_limit - text_x, h)
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self._label_text)

            # Language badge
            badge_text = self._language_label()
            badge_font = QFont(UI_FONT, 9)
            badge_font.setWeight(QFont.Weight.DemiBold)
            painter.setFont(badge_font)
            fm = QFontMetrics(badge_font)
            badge_w = fm.horizontalAdvance(badge_text) + 12
            badge_h = 18
            badge_x = w - badge_w - 8
            badge_y = (h - badge_h) // 2

            badge_path = QPainterPath()
            badge_path.addRoundedRect(QRectF(badge_x, badge_y, badge_w, badge_h), 4, 4)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(255, 255, 255, 14)))
            painter.drawPath(badge_path)
            # Badge border
            pen_badge = QPen(QColor(255, 255, 255, 20))
            pen_badge.setWidthF(0.5)
            painter.setPen(pen_badge)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(QRectF(badge_x, badge_y, badge_w, badge_h), 4, 4)

            painter.setPen(QColor(180, 180, 200))
            painter.drawText(
                QRect(badge_x, badge_y, badge_w, badge_h),
                Qt.AlignmentFlag.AlignCenter,
                badge_text,
            )

            # Backend switch pill (hybrid only): OFFLINE (green) / ONLINE (violet)
            if self._hybrid:
                self._draw_backend_pill(painter)

        def _draw_backend_pill(self, painter):
            r = self._get_backend_rect()
            online = self._backend == "online"
            # violet for online, green for offline
            accent = QColor(124, 108, 255) if online else QColor(52, 211, 153)
            bg = QColor(accent.red(), accent.green(), accent.blue(), 38)
            rr = r.height() / 2
            path = QPainterPath()
            path.addRoundedRect(QRectF(r.x(), r.y(), r.width(), r.height()), rr, rr)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(bg))
            painter.drawPath(path)
            pen = QPen(QColor(accent.red(), accent.green(), accent.blue(), 150))
            pen.setWidthF(1.0)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(QRectF(r.x() + 0.5, r.y() + 0.5,
                                           r.width() - 1, r.height() - 1), rr, rr)
            f = QFont(UI_FONT, 8); f.setWeight(QFont.Weight.Bold)
            painter.setFont(f)
            painter.setPen(accent)
            painter.drawText(r, Qt.AlignmentFlag.AlignCenter, self._backend_label())

        def _draw_toggle(self, painter, w, h):
            """iOS-style glass toggle: green/grey track, white knob."""
            rect = self._get_toggle_rect()
            tx, ty, tw, th = rect.x(), rect.y(), rect.width(), rect.height()
            tr = th / 2

            # Track: green glass (on) / neutral grey glass (off)
            if self._state == "loading":
                track_color = QColor(35, 35, 45, 160)
            elif self._is_enabled:
                track_color = QColor(52, 199, 89, 180)  # iOS green
            else:
                track_color = QColor(90, 90, 100, 160)   # Neutral grey

            track_path = QPainterPath()
            track_path.addRoundedRect(QRectF(tx, ty, tw, th), tr, tr)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(track_color))
            painter.drawPath(track_path)

            # Glass border on track (thin white, 0.5px)
            pen_track = QPen(QColor(255, 255, 255, 30))
            pen_track.setWidthF(0.5)
            painter.setPen(pen_track)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(QRectF(tx, ty, tw, th), tr, tr)

            # Knob: clean white circle
            knob_r = (th - 4) / 2
            if self._is_enabled:
                knob_cx = tx + tw - knob_r - 3
            else:
                knob_cx = tx + knob_r + 3
            knob_cy = ty + th / 2

            # Tiny knob shadow
            shadow_c = QColor(0, 0, 0, 40)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(shadow_c))
            painter.drawEllipse(QPointF(knob_cx, knob_cy + 0.5), knob_r, knob_r)

            # White knob
            painter.setBrush(QBrush(QColor(255, 255, 255, 240)))
            painter.drawEllipse(QPointF(knob_cx, knob_cy), knob_r, knob_r)

            # Top glint on knob
            glint_grad = QRadialGradient(knob_cx, knob_cy - knob_r * 0.3, knob_r * 0.6)
            glint_grad.setColorAt(0, QColor(255, 255, 255, 80))
            glint_grad.setColorAt(1, QColor(255, 255, 255, 0))
            painter.setBrush(QBrush(glint_grad))
            painter.drawEllipse(QPointF(knob_cx, knob_cy), knob_r, knob_r)

        # ---- Color Helpers ----

        def _get_background_colors(self):
            """Return (base_layer, tint_overlay) — two semi-transparent QColors.
            Base: dark glass (alpha ~180-190). Tint: state-specific (alpha ~15-30).
            """
            base = QColor(18, 18, 24, 185)
            tints = {
                "loading": QColor(100, 80, 180, 18),
                "idle":    QColor(140, 140, 160, 12),
                "listening":  QColor(255, 60, 60, 28),
                "processing": QColor(60, 120, 255, 22),
                "done":       QColor(60, 220, 100, 25),
            }
            return base, tints.get(self._state, tints["idle"])

        def _get_border_color(self):
            """Glass white edge + state accent overlay."""
            glass_edge = QColor(255, 255, 255, 30)
            if self._state == "loading":
                accent = QColor(120, 100, 200, 50)
            elif self._state == "idle":
                accent = QColor(180, 180, 200, 25)
            elif self._state == "listening":
                breath = abs(math.sin(self._anim_tick * 0.10))
                accent = QColor(255, 80, 80, int(50 + 80 * breath))
            elif self._state == "processing":
                accent = QColor(80, 150, 255, 70)
            elif self._state == "done":
                accent = QColor(80, 230, 120, 65)
            else:
                accent = QColor(180, 180, 200, 25)
            # Blend: white edge + accent
            r = min(255, glass_edge.red() + accent.red())
            g = min(255, glass_edge.green() + accent.green())
            b = min(255, glass_edge.blue() + accent.blue())
            a = min(255, glass_edge.alpha() + accent.alpha())
            return QColor(r, g, b, a), a

        def _get_dot_color(self):
            """Softer, more saturated QColor objects."""
            colors = {
                "loading":    QColor(255, 180, 50),
                "idle":       QColor(120, 120, 140),
                "listening":  QColor(255, 75, 75),
                "processing": QColor(80, 160, 255),
                "done":       QColor(75, 230, 120),
            }
            return colors.get(self._state, QColor(120, 120, 140))

        def _get_glow_alpha(self):
            """Softer glow with slower breathing."""
            if self._state == "listening":
                return int(45 + 30 * abs(math.sin(self._anim_tick * 0.10)))
            elif self._state == "processing":
                return int(30 + 18 * abs(math.sin(self._anim_tick * 0.08)))
            elif self._state == "done":
                return 45
            return 0

        def _get_text_color(self):
            """Brighter text for readability on glass backgrounds."""
            colors = {
                "loading":    QColor(170, 170, 190),
                "idle":       QColor(200, 200, 215),
                "listening":  QColor(255, 130, 130),
                "processing": QColor(140, 195, 255),
                "done":       QColor(130, 255, 170),
            }
            return colors.get(self._state, QColor(200, 200, 215))

    # =========================================================
    # STEP 4: Create Qt app and widget
    # =========================================================

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    # macOS: a Python process launched from a terminal starts with activation
    # policy "Prohibited" — windows never appear on screen, even though Qt
    # thinks it drew them. Setting "Accessory" gives the process a UI session
    # (windows show) without adding a Dock icon or menu bar.
    if IS_MAC:
        try:
            from AppKit import NSApplication, NSApplicationActivationPolicyAccessory
            NSApplication.sharedApplication().setActivationPolicy_(
                NSApplicationActivationPolicyAccessory
            )
            log.info("macOS activation policy set to Accessory")
        except Exception as e:
            log.warning(f"Could not set activation policy: {e}")

    widget = VoiceWidget(model=model, cloud_model=cloud_model)
    widget.show()
    if IS_MAC:
        widget.raise_()  # ensure widget is on top of stacking order

    log.info("Widget displayed, entering event loop...")

    exit_code = app.exec()
    log.info(f"Event loop ended with code {exit_code}")
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
