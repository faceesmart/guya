"""
Guya Control Panel — the app you double-click to manage Guya.

A professional, self-contained control surface:
  * a big circular POWER button (top-center) turns Guya on/off, with a live
    uptime timer underneath;
  * settings (mode, model, online API key, language, key) are changed IN PLACE
    via clean modals — no setup wizard;
  * maintenance: re-run setup, update, open logs, uninstall.

The dictation widget runs as a separate `python -m guya --widget` process. The
panel polls it once a second so its state always reflects reality (and if the
widget dies on its own, the button flips to OFF). Any settings change saves the
config and restarts the widget so the change takes effect.
"""

import os
import sys
import time

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QApplication, QScrollArea, QMessageBox, QDialog, QPlainTextEdit, QLineEdit,
    QStackedWidget,
)
from PyQt6.QtCore import Qt, QLockFile, QProcess, QTimer, pyqtSignal, QRectF
from PyQt6.QtGui import QFont, QColor, QPainter, QPen

from . import config as guya_config
from . import profiler
from . import runtime
from . import wizard as wz
from .wizard import (
    BG, BG2, CARD, BORDER, ACCENT, ACCENT2, ACCENT_TEXT, GREEN, RED,
    TEXT, TEXT2, DIM, UI_FONT, IS_MAC, _grad, _shadow, _dots,
    PickerDialog, Card, HotkeyCapture, MODE_META, MODEL_PERF, LANG,
    model_is_cached,
)

import logging
log = logging.getLogger("Guya")

EN = LANG["en"]
MODEL_TITLE = {"accurate": "Accurate", "balanced": "Balanced", "fast": "Fast"}
LANG_NAME = {"en": "English", "fa": "Persian", "dual": "Persian + English"}


def _project_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _source_root() -> str:
    """The git checkout. Under Guya.app the running code is a copy in
    ~/.guya/runtime; the installer records the original folder in
    ~/.guya/runtime/origin so Update and Uninstall can reach it."""
    root = _project_root()
    origin = os.path.join(root, "origin")
    try:
        with open(origin, encoding="utf-8") as handle:
            recorded = handle.read().strip()
        if recorded and os.path.isdir(recorded):
            return recorded
    except OSError:
        pass
    return root


def _fmt_uptime(secs: float) -> str:
    s = int(secs)
    h, m, s = s // 3600, (s % 3600) // 60, s % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


# ============================================================
# Power button (custom-painted circle)
# ============================================================

class PowerButton(QWidget):
    clicked = pyqtSignal()

    def __init__(self, size=132, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._on = False

    def setOn(self, on):
        if on != self._on:
            self._on = on
            self.update()

    def mousePressEvent(self, _e):
        self.clicked.emit()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        s = min(self.width(), self.height())
        m = 8
        rect = QRectF(m, m, s - 2 * m, s - 2 * m)
        # disc
        if self._on:
            p.setBrush(QColor(45, 212, 191))
            glyph = QColor("#04211d")
        else:
            p.setBrush(QColor("#1b1f25"))
            glyph = QColor(TEXT2)
        p.setPen(QPen(QColor(255, 255, 255, 22), 1.5))
        p.drawEllipse(rect)
        # power glyph: arc with a gap at the top + a vertical stroke
        g = rect.adjusted(s * 0.30, s * 0.30, -s * 0.30, -s * 0.30)
        pen = QPen(glyph, max(4.0, s * 0.05))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawArc(g, 115 * 16, -310 * 16)        # leaves ~50° gap centred at top
        cx = rect.center().x()
        p.drawLine(int(cx), int(rect.center().y()),
                   int(cx), int(g.top() - s * 0.04))
        p.end()


# ============================================================
# Control Panel
# ============================================================

class ControlPanel(QWidget):
    def __init__(self):
        super().__init__()
        self.widget_proc = None
        self.setup_proc = None
        self._on_since = None
        self._cmd_seq = 0
        self._live = None          # latest runtime state from the widget
        self._live_sig = None      # signature to avoid rebuilding controls every tick
        self._pending_until = 0.0  # freeze optimistic control values briefly after a command
        self._load_state()
        self.setWindowTitle("Guya")
        self.resize(540, 780)
        self.setMinimumSize(460, 660)
        self.setStyleSheet(
            f"ControlPanel {{ background: {_grad(BG, BG2)}; }}"
            f"QWidget {{ color: {TEXT}; }}")
        self._build()
        # live sync with the actual widget process
        self._sync = QTimer(self); self._sync.timeout.connect(self._tick); self._sync.start(400)
        # "Turn on + open panel"
        QTimer.singleShot(150, self.start_widget)

    # ---------- config <-> state ----------

    def _load_state(self):
        c = guya_config.load_config()
        backend = c["model"]["backend"]; cloud_on = c["cloud"]["enabled"]
        self.mode = "online" if backend == "cloud" else ("dual" if cloud_on else "offline")
        self.model_size = c["model"]["size"]
        self.device = c["model"]["device"]
        self.api_key = c["cloud"].get("api_key") or ""
        self.lang = c.get("language", "en")
        self.vk = c["hotkey"]["vk"]
        self.label = c["hotkey"]["label"]
        assistant = c.get("assistant", {})
        assistant_hotkey = assistant.get("hotkey", {})
        self.assistant_enabled = bool(assistant.get("enabled", True))
        self.assistant_vk = assistant_hotkey.get("vk", 119)
        self.assistant_label = assistant_hotkey.get("label", "F8")

    def _write_config(self):
        c = guya_config.load_config()
        if self.mode == "online":
            c["model"]["backend"] = "cloud"; c["model"]["size"] = "large-v3"
            c["model"]["device"] = "cloud"
            c["cloud"]["provider"] = "groq"; c["cloud"]["api_key"] = self.api_key
            c["cloud"]["enabled"] = False
            c["language"] = self.lang
        elif self.mode == "dual":
            c["model"]["backend"] = "faster-whisper"; c["model"]["size"] = self.model_size
            c["model"]["device"] = self.device; c["model"]["compute_type"] = "auto"
            c["cloud"]["provider"] = "groq"; c["cloud"]["api_key"] = self.api_key
            c["cloud"]["enabled"] = True
            # The offline model runs in the chosen language, including "dual"
            # (stt.transcribe_audio detects the language per segment).
            c["language"] = self.lang if self.lang in ("fa", "en", "dual") else "en"
        else:  # offline
            c["model"]["backend"] = "faster-whisper"; c["model"]["size"] = self.model_size
            c["model"]["device"] = self.device; c["model"]["compute_type"] = "auto"
            c["cloud"]["enabled"] = False
            c["language"] = self.lang
        c["hotkey"]["vk"] = self.vk; c["hotkey"]["name"] = self.label
        c["hotkey"]["label"] = self.label
        c["assistant"]["enabled"] = self.assistant_enabled
        c["assistant"]["hotkey"]["vk"] = self.assistant_vk
        c["assistant"]["hotkey"]["name"] = self.assistant_label
        c["assistant"]["hotkey"]["label"] = self.assistant_label
        guya_config.save_config(c)

    def _apply(self):
        """Persist + reflect a settings change, restarting Guya if it's on."""
        self._write_config()
        self._fill_settings()
        if self._running():
            self.stop_widget()
            QTimer.singleShot(300, self.start_widget)

    # ---------- UI ----------

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 18, 24, 16)
        root.setSpacing(8)

        title = QLabel("گویا  ·  Guya")
        title.setFont(QFont(UI_FONT, 16, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {TEXT2};")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(title)

        # Power button + status + uptime (always visible)
        self.power = PowerButton(116)
        self.power.clicked.connect(self._toggle_widget)
        prow = QHBoxLayout(); prow.addStretch(); prow.addWidget(self.power); prow.addStretch()
        root.addLayout(prow)
        self.status_lbl = QLabel("…"); self.status_lbl.setFont(QFont(UI_FONT, 14, QFont.Weight.Bold))
        self.status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.status_lbl)
        self.uptime_lbl = QLabel(""); self.uptime_lbl.setFont(QFont(UI_FONT, 20, QFont.Weight.DemiBold))
        self.uptime_lbl.setStyleSheet(f"color: {ACCENT};")
        self.uptime_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.uptime_lbl)

        # Accessibility warning (shown only when the widget reports it's needed)
        self.access_banner = self._access_banner(); self.access_banner.setVisible(False)
        root.addWidget(self.access_banner)
        root.addSpacing(4)

        # Tab switcher: Controls | Settings
        root.addWidget(self._tabbar(), alignment=Qt.AlignmentFlag.AlignHCenter)
        self.tabs = QStackedWidget()

        # --- Controls tab (live, synced) ---
        cpage = QWidget(); cpage.setStyleSheet("background:transparent;")
        cl = QVBoxLayout(cpage); cl.setContentsMargins(0, 10, 0, 0); cl.setSpacing(9)
        self.controls_box = QFrame(); self.controls_box.setStyleSheet("background:transparent;")
        self.controls_col = QVBoxLayout(self.controls_box)
        self.controls_col.setContentsMargins(0, 0, 0, 0); self.controls_col.setSpacing(9)
        cl.addWidget(self.controls_box); cl.addStretch()
        self.tabs.addWidget(cpage)

        # --- Settings tab (scroll) + Maintenance (fixed below) ---
        spage = QWidget(); spage.setStyleSheet("background:transparent;")
        sl = QVBoxLayout(spage); sl.setContentsMargins(0, 10, 0, 0); sl.setSpacing(10)
        area = QScrollArea(); area.setWidgetResizable(True); area.setFrameShape(QFrame.Shape.NoFrame)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        area.setStyleSheet("QScrollArea{background:transparent;border:none;}"
                           "QScrollBar:vertical{background:transparent;width:8px;}"
                           f"QScrollBar::handle:vertical{{background:{BORDER};border-radius:4px;}}"
                           "QScrollBar::add-line,QScrollBar::sub-line{height:0;}")
        inner = QWidget(); inner.setStyleSheet("background:transparent;")
        self.settings_col = QVBoxLayout(inner)
        self.settings_col.setContentsMargins(0, 0, 8, 0); self.settings_col.setSpacing(9)
        area.setWidget(inner)
        sl.addWidget(area, 1)
        self._fill_settings()
        mhead = QLabel("MAINTENANCE"); mhead.setFont(QFont(UI_FONT, 10, QFont.Weight.Bold))
        mhead.setStyleSheet(f"color: {DIM}; letter-spacing: 1px;")
        sl.addWidget(mhead)
        m1 = QHBoxLayout(); m1.setSpacing(9)
        for txt, fn in (("Re-run Setup", self._rerun_setup), ("Update", self._update)):
            b = self._ghost(txt); b.clicked.connect(fn); m1.addWidget(b)
        sl.addLayout(m1)
        m2 = QHBoxLayout(); m2.setSpacing(9)
        for txt, fn in (("Open Logs", self._open_logs), ("Uninstall", self._uninstall)):
            b = self._ghost(txt); b.clicked.connect(fn); m2.addWidget(b)
        sl.addLayout(m2)
        self.tabs.addWidget(spage)

        # --- Help tab: short bilingual onboarding and supported command shapes ---
        hpage = QWidget(); hpage.setStyleSheet("background:transparent;")
        hl = QVBoxLayout(hpage); hl.setContentsMargins(0, 10, 0, 0)
        help_area = QScrollArea(); help_area.setWidgetResizable(True)
        help_area.setFrameShape(QFrame.Shape.NoFrame)
        help_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        help_area.setStyleSheet(
            "QScrollArea{background:transparent;border:none;}"
            "QScrollBar:vertical{background:transparent;width:8px;}"
            f"QScrollBar::handle:vertical{{background:{BORDER};border-radius:4px;}}"
            "QScrollBar::add-line,QScrollBar::sub-line{height:0;}"
        )
        help_inner = QWidget(); help_inner.setStyleSheet("background:transparent;")
        help_col = QVBoxLayout(help_inner)
        help_col.setContentsMargins(0, 0, 8, 0); help_col.setSpacing(9)

        intro = QLabel("How to use Guya  ·  راهنمای استفاده از گویا")
        intro.setFont(QFont(UI_FONT, 15, QFont.Weight.Bold))
        intro.setStyleSheet(f"color: {ACCENT};")
        intro.setAccessibleName("How to use Guya")
        help_col.addWidget(intro)
        summary = QLabel(
            "Hold the key, speak naturally, then release it. Guya only performs "
            "the limited actions shown below.\n"
            "کلید را نگه دارید، دستور را بگویید و سپس کلید را رها کنید."
        )
        summary.setWordWrap(True); summary.setFont(QFont(UI_FONT, 10))
        summary.setStyleSheet(f"color: {TEXT2}; padding: 0 2px 4px 2px;")
        help_col.addWidget(summary)

        if sys.platform == "darwin":
            keys_card = (
                "Right Option (⌥): dictation into the active document.\n"
                "Right Command (⌘): assistant commands. Press it while Guya is speaking "
                "to interrupt and continue.\n\n"
                "⌥ برای تبدیل صدا به متن  ·  ⌘ برای فرمان‌های دستیار"
            )
        else:
            keys_card = (
                f"{self.label}: dictation into the active document.\n"
                f"{self.assistant_label}: assistant commands. Press it while Guya is speaking "
                "to interrupt and continue.\n\n"
                f"{self.label} برای تبدیل صدا به متن  ·  {self.assistant_label} برای فرمان‌های دستیار"
            )
        help_col.addWidget(self._help_card("⌨️  Two keys / دو کلید", keys_card))
        help_col.addWidget(self._help_card(
            "✨  Common commands / فرمان‌های اصلی",
            "Open Calculator  ·  ماشین حساب رو باز کن\n"
            "Create a Word file named report  ·  یه فایل ورد به اسم گزارش بساز\n"
            "Open report docs  ·  فایل گزارش رو باز کن\n"
            "Rename it to final report  ·  اسمش رو بذار گزارش نهایی\n"
            "Save it  ·  فایل فعلی رو ذخیره کن\n"
            "Close it  ·  پنجره فعلی رو ببند\n"
            "Switch to Persian  ·  برو انگلیسی  ·  دو زبانه",
        ))
        help_col.addWidget(self._help_card(
            "🌐  Browser / مرورگر",
            "First focus Chrome or Safari, then say: Scroll down (or Page down), "
            "Scroll up (or Page up), "
            "Go back, Go forward, Go to the top, or Go to the bottom.\n"
            "Open a site in the current tab: Go to YouTube  ·  Visit github.com\n\n"
            "ابتدا مرورگر را فعال کنید، سپس بگویید: صفحه رو پایین ببر، "
            "صفحه رو ببر پایین، صفحه رو بالا ببر، برو عقب، برو جلو، "
            "برو اول صفحه یا برو آخر صفحه.\n"
            "باز کردن مستقیم سایت: برو به سایت یوتیوب",
        ))
        help_col.addWidget(self._help_card(
            "🧭  Choices and confirmations / انتخاب و تأیید",
            "After Create, say Yes or No when Guya asks whether to open it.\n"
            "For similar filenames, click a result or say first, second, third, or cancel.\n\n"
            "بعد از ساخت فایل، برای باز شدن بگویید بله یا نه. برای نتایج مشابه، "
            "روی گزینه بزنید یا بگویید اول، دوم، سوم یا لغو.",
        ))
        help_col.addWidget(self._help_card(
            "🛡️  V1 safety limit / محدودیت ایمنی",
            "Guya searches only Desktop, Documents and Downloads. Delete, shell "
            "commands, uploads, reading web pages, clicking results and downloads "
            "are not supported.\n"
            "گویا حذف فایل، اجرای دستور سیستمی، خواندن صفحه وب، کلیک روی نتیجه‌ها "
            "یا دانلود را انجام نمی‌دهد.",
        ))
        help_col.addStretch()
        help_area.setWidget(help_inner); hl.addWidget(help_area)
        self.tabs.addWidget(hpage)

        root.addWidget(self.tabs, 1)
        self._select_tab(0)

    def _tabbar(self):
        wrap = QFrame(); wrap.setFixedHeight(40)
        wrap.setStyleSheet(f"QFrame {{ background: rgba(0,0,0,0.28); border: 1px solid {BORDER};"
                           f"border-radius: 13px; }}")
        h = QHBoxLayout(wrap); h.setContentsMargins(4, 4, 4, 4); h.setSpacing(4)
        self._tab_buttons = []
        for i, name in enumerate(("Controls", "Settings", "Help")):
            b = QPushButton(name); b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFixedHeight(30); b.setMinimumWidth(124)
            b.setFont(QFont(UI_FONT, 11, QFont.Weight.DemiBold))
            b.clicked.connect(lambda _=False, idx=i: self._select_tab(idx))
            self._tab_buttons.append(b); h.addWidget(b)
        return wrap

    def _help_card(self, title, body):
        frame = QFrame()
        frame.setStyleSheet(
            f"QFrame {{ background: {_grad('#1a1a23', '#15151d')};"
            f"border: 1px solid {BORDER}; border-radius: 14px; }}"
            "QLabel { border: none; background: transparent; }"
        )
        col = QVBoxLayout(frame); col.setContentsMargins(15, 12, 15, 12)
        col.setSpacing(6)
        heading = QLabel(title); heading.setFont(QFont(UI_FONT, 11, QFont.Weight.Bold))
        heading.setStyleSheet(f"color: {TEXT};")
        text = QLabel(body); text.setWordWrap(True); text.setFont(QFont(UI_FONT, 10))
        text.setStyleSheet(f"color: {TEXT2};")
        text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        col.addWidget(heading); col.addWidget(text)
        return frame

    def _select_tab(self, i):
        self.tabs.setCurrentIndex(i)
        for j, b in enumerate(self._tab_buttons):
            if j == i:
                b.setStyleSheet(f"QPushButton {{ background: {ACCENT}; color: {ACCENT_TEXT};"
                                f"border: none; border-radius: 10px; }}")
            else:
                b.setStyleSheet(f"QPushButton {{ background: transparent; color: {TEXT2};"
                                f"border: none; border-radius: 10px; }}"
                                f"QPushButton:hover {{ color: {TEXT}; }}")

    def _access_banner(self):
        self._permission_target = "Accessibility"
        f = QFrame()
        f.setStyleSheet(f"QFrame {{ background: rgba(251,113,133,0.12); border: 1px solid {RED};"
                        f"border-radius: 13px; }} QLabel {{ border: none; background: transparent; }}")
        h = QHBoxLayout(f); h.setContentsMargins(14, 10, 12, 10); h.setSpacing(10)
        ic = QLabel("⚠"); ic.setFont(QFont(UI_FONT, 15)); h.addWidget(ic)
        self.permission_text = QLabel("Guya needs permission to detect your key.")
        self.permission_text.setFont(QFont(UI_FONT, 10))
        self.permission_text.setWordWrap(True)
        self.permission_text.setStyleSheet(f"color: {TEXT};")
        h.addWidget(self.permission_text, 1)
        btn = QPushButton("Open Settings"); btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setMinimumHeight(34); btn.setFont(QFont(UI_FONT, 10, QFont.Weight.DemiBold))
        btn.setStyleSheet(f"QPushButton {{ background: {RED}; color: #2a0a12; border: none;"
                          f"border-radius: 10px; padding: 0 12px; }}")
        btn.clicked.connect(self._open_permission_settings)
        h.addWidget(btn)
        return f

    def _open_permission_settings(self):
        pane = (
            "Privacy_Microphone"
            if self._permission_target == "Microphone"
            else "Privacy_Accessibility"
        )
        QProcess.startDetached(
            "open", [f"x-apple.systempreferences:com.apple.preference.security?{pane}"])

    def _ghost(self, text):
        b = QPushButton(text); b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setMinimumHeight(42); b.setFont(QFont(UI_FONT, 11, QFont.Weight.DemiBold))
        b.setStyleSheet(
            f"QPushButton {{ background: rgba(255,255,255,0.04); color: {TEXT};"
            f"border: 1px solid {BORDER}; border-radius: 13px; padding: 0 16px; }}"
            f"QPushButton:hover {{ border-color: {ACCENT}; background: rgba(45,212,191,0.08); }}")
        return b

    def _fill_settings(self):
        while self.settings_col.count():
            it = self.settings_col.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        modes = {"offline": "💻  Offline", "online": "☁️  Online", "dual": "🔀  Dual"}
        rows = [("🧩", "How it runs", modes.get(self.mode, self.mode), self._open_mode_modal)]
        if self.mode in ("offline", "dual"):
            rows.append(("🧠", "Model", self.model_size, self._open_model_modal))
        if self.mode in ("online", "dual"):
            rows.append(("☁️", "Online API key", "Set ✓" if self.api_key else "Not set",
                         self._open_api_modal))
        rows.append(("⌨️", "Dictation key", "Right Option (⌥)" if IS_MAC else self.label,
                     None if IS_MAC else self._open_key_modal))
        rows.append(("✨", "Assistant key", "Right Command (⌘)" if IS_MAC else self.assistant_label,
                     None if IS_MAC else self._open_assistant_key_modal))
        for icon, label, value, fn in rows:
            self.settings_col.addWidget(self._setting_row(icon, label, value, fn))
        self.settings_col.addStretch()

    def _setting_row(self, icon, label, value, on_change):
        f = QFrame()
        f.setStyleSheet(f"QFrame {{ background: {_grad('#1a1a23', '#15151d')};"
                        f"border: 1px solid {BORDER}; border-radius: 15px; }}"
                        f"QLabel {{ border: none; background: transparent; }}")
        _shadow(f, blur=14, dy=3, alpha=70)
        h = QHBoxLayout(f); h.setContentsMargins(16, 12, 16, 12); h.setSpacing(12)
        ic = QLabel(icon); ic.setFont(QFont(UI_FONT, 16)); ic.setFixedWidth(28); h.addWidget(ic)
        tx = QVBoxLayout(); tx.setSpacing(1)
        lb = QLabel(label); lb.setFont(QFont(UI_FONT, 9)); lb.setStyleSheet(f"color: {TEXT2};")
        vl = QLabel(str(value)); vl.setFont(QFont(UI_FONT, 13, QFont.Weight.DemiBold))
        vl.setStyleSheet(f"color: {TEXT};"); vl.setWordWrap(True)
        tx.addWidget(lb); tx.addWidget(vl); h.addLayout(tx, 1)
        if on_change is not None:
            cb = QPushButton("Change"); cb.setCursor(Qt.CursorShape.PointingHandCursor)
            cb.setMinimumSize(86, 34); cb.setFont(QFont(UI_FONT, 10, QFont.Weight.DemiBold))
            cb.setStyleSheet(f"QPushButton {{ background: rgba(45,212,191,0.12); color: {ACCENT};"
                             f"border: 1px solid {ACCENT}; border-radius: 11px; padding: 0 14px; }}"
                             f"QPushButton:hover {{ background: rgba(45,212,191,0.22); }}")
            cb.clicked.connect(on_change)
            h.addWidget(cb)
        return f

    # ---------- widget on/off + sync ----------

    def start_widget(self):
        if self._running():
            return
        runtime.clear(); self._cmd_seq = 0; self._live = None; self._live_sig = None
        self.widget_proc = QProcess(self)
        self.widget_proc.setProgram(sys.executable)
        self.widget_proc.setArguments(["-m", "guya", "--widget"])
        self.widget_proc.setWorkingDirectory(_project_root())
        self.widget_proc.start()
        self._on_since = time.monotonic()
        self._tick()

    def stop_widget(self):
        if self._running():
            self.widget_proc.terminate()
            if not self.widget_proc.waitForFinished(2000):
                self.widget_proc.kill()
        self._on_since = None
        self._tick()

    def _toggle_widget(self):
        self.stop_widget() if self._running() else self.start_widget()

    def _running(self):
        return bool(self.widget_proc and
                    self.widget_proc.state() != QProcess.ProcessState.NotRunning)

    def _tick(self):
        on = self._running()
        if not on:
            self._on_since = None
        self.power.setOn(on)
        if on:
            self.status_lbl.setText("Guya is on")
            self.status_lbl.setStyleSheet(f"color: {GREEN};")
            self.uptime_lbl.setText(_fmt_uptime(time.monotonic() - (self._on_since or time.monotonic())))
        else:
            self.status_lbl.setText("Guya is off")
            self.status_lbl.setStyleSheet(f"color: {TEXT2};")
            self.uptime_lbl.setText("")

        # Live state from the running widget (heartbeat within 2s). After a
        # command we freeze the optimistic values briefly so they don't flicker.
        st = runtime.read_state()
        fresh = bool(st) and (time.time() - st.get("ts", 0) < 2.0)
        if not (on and fresh):
            self._live = None
        elif time.monotonic() >= self._pending_until:
            self._live = st
        # Permission warning when the widget cannot see keys or hear audio.
        trusted = (self._live or {}).get("trusted", True)
        microphone_ok = (self._live or {}).get("microphone_ok", True)
        permission_missing = bool(self._live) and (not trusted or not microphone_ok)
        if permission_missing:
            if not trusted:
                self._permission_target = "Accessibility"
                self.permission_text.setText(
                    "Guya needs Accessibility permission to detect the two hotkeys. "
                    "Grant it, then restart Guya."
                )
            else:
                self._permission_target = "Microphone"
                self.permission_text.setText(
                    "Guya needs Microphone permission to hear your voice. "
                    "Grant it, then restart Guya."
                )
        self.access_banner.setVisible(permission_missing)
        live_sig = None
        if self._live:
            live_sig = (
                self._live.get("enabled"),
                self._live.get("backend"),
                self._live.get("language"),
                self._live.get("hybrid"),
                self._live.get("assistant_enabled"),
            )
        sig = (on, live_sig)
        if sig != self._live_sig:
            self._live_sig = sig
            self._rebuild_controls()

    # ---------- live controls (mirror the widget; two-way sync) ----------

    def _send_cmd(self, **fields):
        self._cmd_seq += 1
        runtime.write_cmd({"seq": self._cmd_seq, **fields})
        if self._live is not None:          # optimistic: reflect immediately
            self._live.update(fields)
            self._pending_until = time.monotonic() + 1.2
            self._live_sig = None
            self._rebuild_controls()

    def _rebuild_controls(self):
        while self.controls_col.count():
            it = self.controls_col.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        live = self._live
        if not live:
            hint = QLabel("Turn Guya on (tap the power button)\nto use the live controls.")
            hint.setFont(QFont(UI_FONT, 11)); hint.setWordWrap(True)
            hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
            hint.setStyleSheet(f"color: {DIM}; padding: 24px;")
            self.controls_col.addWidget(hint)
            return
        head = QLabel("LIVE  (synced with the widget)")
        head.setFont(QFont(UI_FONT, 10, QFont.Weight.Bold))
        head.setStyleSheet(f"color: {DIM}; letter-spacing: 1px;")
        self.controls_col.addWidget(head)

        # Active (on/off while the widget is up — pause/resume listening)
        enabled = bool(live.get("enabled"))
        pill = self._toggle_pill(enabled, lambda: self._send_cmd(enabled=not enabled))
        self.controls_col.addWidget(self._ctrl_row("⚡", "Active", pill))

        assistant_enabled = bool(live.get("assistant_enabled", True))
        assistant_pill = self._toggle_pill(
            assistant_enabled,
            lambda: self._send_cmd(assistant_enabled=not assistant_enabled),
        )
        self.controls_col.addWidget(
            self._ctrl_row(
                "✨",
                f"Assistant ({live.get('assistant_hotkey', 'F8')})",
                assistant_pill,
            )
        )

        # Backend switch (only when both offline+online are loaded = dual)
        if live.get("hybrid"):
            be = live.get("backend", "offline")
            seg = self._segmented([("offline", "OFFLINE"), ("online", "ONLINE")], be,
                                  lambda v: self._send_cmd(backend=v))
            self.controls_col.addWidget(self._ctrl_row("🔀", "Backend now", seg))

        # Language switch (locked while a hybrid widget is on OFFLINE)
        locked = bool(live.get("hybrid") and live.get("backend") == "offline")
        lang = live.get("language", "en")
        seg = self._segmented([("en", "EN"), ("fa", "FA"), ("dual", "Both")], lang,
                              lambda v: self._send_cmd(language=v), enabled=not locked)
        self.controls_col.addWidget(self._ctrl_row("🌐", "Language now", seg,
                                    note="locked on OFFLINE" if locked else ""))

    def _ctrl_row(self, icon, label, right, note=""):
        f = QFrame()
        f.setStyleSheet(f"QFrame {{ background: {_grad('#16241f', '#141b18')};"
                        f"border: 1px solid {ACCENT2}; border-radius: 15px; }}"
                        f"QLabel {{ border: none; background: transparent; }}")
        _shadow(f, blur=14, dy=3, alpha=70)
        h = QHBoxLayout(f); h.setContentsMargins(16, 11, 14, 11); h.setSpacing(12)
        ic = QLabel(icon); ic.setFont(QFont(UI_FONT, 15)); ic.setFixedWidth(26); h.addWidget(ic)
        lb = QLabel(label + (f"   ({note})" if note else ""))
        lb.setFont(QFont(UI_FONT, 12, QFont.Weight.DemiBold)); lb.setStyleSheet(f"color: {TEXT};")
        h.addWidget(lb); h.addStretch(); h.addWidget(right)
        return f

    def _toggle_pill(self, on, on_click):
        b = QPushButton("ON" if on else "OFF"); b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setFixedSize(66, 32); b.setFont(QFont(UI_FONT, 11, QFont.Weight.Bold))
        if on:
            b.setStyleSheet(f"QPushButton {{ background: {GREEN}; color: #06210f;"
                            f"border: none; border-radius: 16px; }}")
        else:
            b.setStyleSheet(f"QPushButton {{ background: #2a2f36; color: {TEXT2};"
                            f"border: none; border-radius: 16px; }}")
        b.clicked.connect(on_click)
        return b

    def _segmented(self, options, current, on_select, enabled=True):
        f = QFrame()
        f.setStyleSheet(f"QFrame {{ background: rgba(0,0,0,0.25); border: 1px solid {BORDER};"
                        f"border-radius: 13px; }}")
        h = QHBoxLayout(f); h.setContentsMargins(3, 3, 3, 3); h.setSpacing(3)
        for val, lab in options:
            seg = QPushButton(lab); seg.setCursor(Qt.CursorShape.PointingHandCursor)
            seg.setFixedHeight(26); seg.setMinimumWidth(46)
            seg.setFont(QFont(UI_FONT, 10, QFont.Weight.Bold))
            seg.setEnabled(enabled)
            if val == current:
                seg.setStyleSheet(f"QPushButton {{ background: {ACCENT}; color: {ACCENT_TEXT};"
                                  f"border: none; border-radius: 10px; padding: 0 10px; }}")
            else:
                seg.setStyleSheet(f"QPushButton {{ background: transparent; color: {TEXT2};"
                                  f"border: none; border-radius: 10px; padding: 0 10px; }}"
                                  f"QPushButton:hover {{ color: {TEXT}; }}")
            seg.clicked.connect(lambda _=False, v=val: on_select(v))
            h.addWidget(seg)
        return f

    # ---------- in-place setting modals ----------

    def _open_mode_modal(self):
        def build(col, choose):
            for mid, icon, tk, how_k, pros, cons in MODE_META:
                col.addWidget(self._opt_card(
                    icon, EN.get(tk, mid), EN.get(how_k, ""),
                    [EN.get(k, "") for k in pros], [EN.get(k, "") for k in cons],
                    selected=(mid == self.mode), on_pick=lambda m=mid: choose(m)))
        dlg = PickerDialog(self, "How Guya runs", build); dlg.resize(dlg.sizeHint())
        if dlg.exec() and dlg.value:
            self.mode = dlg.value
            # ensure prerequisites for the new mode
            if self.mode in ("online", "dual") and not self.api_key:
                if not self._ask_api_key():
                    self._fill_settings(); return
            self._apply()

    def _open_model_modal(self):
        profile = profiler.get_device_profile()
        opts = [o for o in profiler.recommend_models(profile) if o["backend"] != "cloud"]

        def build(col, choose):
            for o in opts:
                perf = MODEL_PERF.get(o["id"], {"fa_acc": 2, "en_acc": 3, "speed": 3})
                sub = (f"Persian {_dots(perf['fa_acc'])}   English {_dots(perf['en_acc'])}   "
                       f"Speed {_dots(perf['speed'])}\n{o.get('note', '')}"
                       + ("" if model_is_cached(o["model_size"]) else "  ·  downloads on start"))
                col.addWidget(self._opt_card(
                    "🧠", f"{MODEL_TITLE.get(o['id'], o['id'])}  ·  {o['model_size']}",
                    subtitle=sub,
                    selected=(o["model_size"] == self.model_size),
                    enabled=o["enabled"], badge=("Recommended" if o["recommended"] else ""),
                    on_pick=(lambda oo=o: choose(oo)) if o["enabled"] else None))
        dlg = PickerDialog(self, "Choose a model", build); dlg.resize(dlg.sizeHint())
        if dlg.exec() and dlg.value:
            self.model_size = dlg.value["model_size"]; self.device = dlg.value["device"]
            self._apply()

    def _open_lang_modal(self):
        def build(col, choose):
            for code, name, icon in (("en", "English", "🇬🇧"), ("fa", "Persian", "🇮🇷"),
                                     ("dual", "Persian + English", "🌐")):
                col.addWidget(self._opt_card(icon, name, "", [], [],
                              selected=(code == self.lang), on_pick=lambda c=code: choose(c)))
        dlg = PickerDialog(self, "Language", build); dlg.resize(460, 360)
        if dlg.exec() and dlg.value:
            self.lang = dlg.value; self._apply()

    def _open_key_modal(self):
        def build(col, choose):
            cap = HotkeyCapture(EN.get("key_capture", "Click, then press a key"))
            cap.setMinimumHeight(54)
            cap.setStyleSheet(f"QPushButton {{ background: {CARD}; color: {TEXT};"
                              f"border: 1px solid {BORDER}; border-radius: 12px; padding: 14px;"
                              f"font-size: 13pt; }}")
            cap.captured.connect(lambda vk, lab: choose((vk, lab)))
            col.addWidget(cap)
        dlg = PickerDialog(self, "Dictation key", build); dlg.resize(480, 240)
        if dlg.exec() and dlg.value:
            if dlg.value[0] == self.assistant_vk:
                QMessageBox.warning(
                    self,
                    "Guya",
                    "Dictation and assistant must use different keys.",
                )
                return
            self.vk, self.label = dlg.value; self._apply()

    def _open_assistant_key_modal(self):
        def build(col, choose):
            cap = HotkeyCapture(EN.get("key_capture", "Click, then press a key"))
            cap.setMinimumHeight(54)
            cap.setStyleSheet(f"QPushButton {{ background: {CARD}; color: {TEXT};"
                              f"border: 1px solid {BORDER}; border-radius: 12px; padding: 14px;"
                              f"font-size: 13pt; }}")
            cap.captured.connect(lambda vk, lab: choose((vk, lab)))
            col.addWidget(cap)
        dlg = PickerDialog(self, "Assistant key", build); dlg.resize(480, 240)
        if dlg.exec() and dlg.value:
            if dlg.value[0] == self.vk:
                QMessageBox.warning(
                    self,
                    "Guya",
                    "Dictation and assistant must use different keys.",
                )
                return
            self.assistant_vk, self.assistant_label = dlg.value
            self._apply()

    def _ask_api_key(self) -> bool:
        return self._open_api_modal(prereq=True)

    def _open_api_modal(self, prereq=False):
        holder = {}

        def build(col, choose):
            intro = QLabel(EN.get("cloud_intro", ""))
            intro.setWordWrap(True); intro.setFont(QFont(UI_FONT, 11))
            intro.setStyleSheet(f"color: {TEXT2};"); col.addWidget(intro)
            link = QLabel('<a href="https://console.groq.com/keys" '
                          f'style="color:{ACCENT};">console.groq.com/keys</a>')
            link.setOpenExternalLinks(True); link.setFont(QFont(UI_FONT, 11, QFont.Weight.DemiBold))
            col.addWidget(link)
            field = QLineEdit(self.api_key); field.setMinimumHeight(44)
            field.setPlaceholderText("Paste your key here (gsk_…)")
            field.setStyleSheet(f"QLineEdit {{ background: {CARD}; color: {TEXT};"
                                f"border: 1px solid {BORDER}; border-radius: 12px; padding: 0 14px;"
                                f"font-size: 12pt; }} QLineEdit:focus {{ border: 1px solid {ACCENT}; }}")
            holder["field"] = field; col.addWidget(field)
            save = QPushButton("Save"); save.setMinimumHeight(44)
            save.setCursor(Qt.CursorShape.PointingHandCursor)
            save.setStyleSheet(f"QPushButton {{ background: {_grad('#3ee0cb', ACCENT2)};"
                               f"color: {ACCENT_TEXT}; border: none; border-radius: 12px;"
                               f"font-weight: 700; font-size: 12pt; }}")
            save.clicked.connect(lambda: choose(field.text().strip()))
            col.addWidget(save)
        dlg = PickerDialog(self, "Online API key", build); dlg.resize(560, 360)
        ok = dlg.exec()
        if ok and dlg.value:
            self.api_key = dlg.value
            if not prereq:
                self._apply()
            return True
        return False

    def _opt_card(self, icon, title, subtitle="", pros=(), cons=(), *,
                  selected=False, on_pick=None, enabled=True, badge=""):
        c = Card(lambda card: (on_pick() if on_pick else None), None, enabled=enabled)
        c.set_selected(selected)
        top = QHBoxLayout(); top.setSpacing(8)
        ic = QLabel(icon); ic.setFont(QFont(UI_FONT, 15)); top.addWidget(ic)
        t = QLabel(title); t.setFont(QFont(UI_FONT, 14, QFont.Weight.Bold))
        t.setStyleSheet(f"color: {TEXT if enabled else DIM};"); top.addWidget(t); top.addStretch()
        if badge:
            bl = QLabel(badge); bl.setFont(QFont(UI_FONT, 9, QFont.Weight.Bold))
            bl.setStyleSheet(f"color: {ACCENT}; background: rgba(45,212,191,0.16);"
                             f"border-radius: 8px; padding: 2px 9px;")
            top.addWidget(bl)
        c._body.addLayout(top)
        if subtitle:
            sw = QLabel(subtitle); sw.setFont(QFont(UI_FONT, 10)); sw.setWordWrap(True)
            sw.setStyleSheet(f"color: {TEXT2};"); c._body.addWidget(sw)
        for k in pros:
            l = QLabel("✓  " + k); l.setFont(QFont(UI_FONT, 9)); l.setWordWrap(True)
            l.setStyleSheet(f"color: {GREEN};"); c._body.addWidget(l)
        for k in cons:
            l = QLabel("✕  " + k); l.setFont(QFont(UI_FONT, 9)); l.setWordWrap(True)
            l.setStyleSheet(f"color: {RED};"); c._body.addWidget(l)
        c.style_self()
        return c

    # ---------- maintenance ----------

    def _rerun_setup(self):
        was = self._running(); self.stop_widget()
        self.setup_proc = QProcess(self)
        self.setup_proc.setProgram(sys.executable)
        self.setup_proc.setArguments(["-m", "guya", "--setup-only"])
        self.setup_proc.setWorkingDirectory(_project_root())
        self.setup_proc.finished.connect(lambda *_: self._after_setup(was))
        self.setup_proc.start(); self.hide()

    def _after_setup(self, was):
        self.show(); self.raise_(); self.activateWindow()
        self._load_state(); self._fill_settings()
        if was:
            self.start_widget()

    def _update(self):
        root = _source_root()
        if not os.path.isdir(os.path.join(root, ".git")):
            QMessageBox.information(
                self, "Update Guya",
                "Automatic update needs the original project folder with git.\n\n"
                f"Run these in a terminal instead:\n  cd \"{root}\"\n  git pull\n  ./install.sh   "
                "(or double-click Install Guya)")
            return
        pip = os.path.join(root, "venv", "Scripts" if sys.platform == "win32" else "bin", "pip")
        if not os.path.exists(pip):
            pip = sys.executable.replace("python", "pip") if "python" in sys.executable else "pip"
        # Under Guya.app the code that runs is the copy in ~/.guya/runtime, so a
        # pull alone changes nothing; regenerate the launcher (which re-copies).
        # sys.executable is the runtime interpreter, which always exists; a
        # stock macOS install has no <checkout>/venv.
        relaunch = f'"{sys.executable}" -c "import sys; sys.path.insert(0, \\"{root}\\"); from guya import launcher_gen; launcher_gen.create_launcher()"'
        if sys.platform == "win32":
            argv = ["cmd", "/c", f'cd /d "{root}" & git pull & "{pip}" install -r requirements.txt']
        else:
            argv = ["bash", "-lc", f'cd "{root}" && git pull && "{pip}" install -r requirements.txt && {relaunch}']
        self._run_console("Updating Guya…", argv)

    def _open_logs(self):
        logpath = os.path.join(os.path.expanduser("~"), ".guya", "logs", "guya.log")
        dlg = QDialog(self); dlg.setWindowTitle("Guya — Logs"); dlg.resize(720, 480)
        dlg.setStyleSheet(f"background: {BG}; color: {TEXT};")
        v = QVBoxLayout(dlg)
        top = QHBoxLayout()
        top.addWidget(QLabel("Recent log")); top.addStretch()
        v.addLayout(top)
        out = QPlainTextEdit(); out.setReadOnly(True)
        out.setStyleSheet(f"background: #0a0d10; color: {TEXT2}; border: 1px solid {BORDER};"
                          f"border-radius: 10px; font-family: monospace; font-size: 11px;")
        v.addWidget(out)

        scroll_state = {"follow_tail": True, "programmatic": False}

        def remember_scroll(value):
            if scroll_state["programmatic"]:
                return
            bar = out.verticalScrollBar()
            scroll_state["follow_tail"] = value >= bar.maximum() - 2

        out.verticalScrollBar().valueChanged.connect(remember_scroll)

        def refresh():
            try:
                with open(logpath, "r", encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()[-400:]
                content = "".join(lines)
            except Exception as e:
                content = f"(no log yet: {e})"

            # Avoid replacing identical text every 1.5 seconds. Replacing it
            # resets QPlainTextEdit's scroll position even when no log changed.
            if content == out.toPlainText():
                return

            bar = out.verticalScrollBar()
            old_value = bar.value()
            follow_tail = scroll_state["follow_tail"]
            scroll_state["programmatic"] = True
            try:
                out.setPlainText(content)
                bar = out.verticalScrollBar()
                if follow_tail:
                    bar.setValue(bar.maximum())
                else:
                    # The user is reviewing older entries: keep their current
                    # position instead of forcing the view back to the bottom.
                    bar.setValue(min(old_value, bar.maximum()))
            finally:
                scroll_state["programmatic"] = False
                scroll_state["follow_tail"] = follow_tail

        def jump_to_latest():
            scroll_state["programmatic"] = True
            try:
                bar = out.verticalScrollBar()
                bar.setValue(bar.maximum())
            finally:
                scroll_state["programmatic"] = False
                scroll_state["follow_tail"] = True

        refresh()
        rbtn = QPushButton("Refresh"); rbtn.clicked.connect(refresh)
        rbtn.setStyleSheet(self._ghost("").styleSheet()); rbtn.setMinimumHeight(38)
        rbtn.setCursor(Qt.CursorShape.PointingHandCursor); rbtn.setText("Refresh")
        top.addWidget(rbtn)
        latest_btn = QPushButton("Latest"); latest_btn.clicked.connect(jump_to_latest)
        latest_btn.setStyleSheet(self._ghost("").styleSheet()); latest_btn.setMinimumHeight(38)
        latest_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        top.addWidget(latest_btn)
        # auto-refresh while open
        t = QTimer(dlg); t.timeout.connect(refresh); t.start(1500)
        dlg.exec(); t.stop()

    def _uninstall(self):
        box = QMessageBox(self); box.setWindowTitle("Uninstall Guya")
        box.setText("Remove Guya's settings, downloaded models, and launchers?")
        box.setInformativeText("Your project folder is kept. You can set it up again anytime.")
        box.setStandardButtons(QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Yes)
        box.setDefaultButton(QMessageBox.StandardButton.Cancel)
        if box.exec() != QMessageBox.StandardButton.Yes:
            return
        self.stop_widget()
        import shutil, glob
        root = _source_root()
        home = os.path.expanduser("~")
        guya_dir = os.path.join(home, ".guya")
        # Launchers first (they point at the runtime), then user data, then the
        # model cache. The runtime this process runs from is removed last and
        # the process exits immediately afterwards.
        targets = [os.path.join(root, "Guya.app"),
                   os.path.join(root, "Start Guya.command"),
                   os.path.join(root, "Start Guya.vbs"),
                   os.path.join(guya_dir, "config.json"),
                   os.path.join(guya_dir, "logs"),
                   os.path.join(guya_dir, "rt_state.json"),
                   os.path.join(guya_dir, "rt_cmd.json")]
        targets += glob.glob(os.path.join(home, ".cache", "huggingface", "hub", "models--*faster-whisper*"))
        targets.append(os.path.join(guya_dir, "runtime"))
        for t in targets:
            try:
                shutil.rmtree(t, ignore_errors=True) if os.path.isdir(t) else (
                    os.remove(t) if os.path.exists(t) else None)
            except Exception as e:
                log.warning(f"uninstall: {t}: {e}")
        QMessageBox.information(self, "Guya", "Guya has been removed. Goodbye! 👋")
        os._exit(0)

    def _run_console(self, title, argv):
        dlg = QDialog(self); dlg.setWindowTitle(title); dlg.resize(660, 440)
        dlg.setStyleSheet(f"background: {BG}; color: {TEXT};")
        v = QVBoxLayout(dlg); v.addWidget(QLabel(title))
        out = QPlainTextEdit(); out.setReadOnly(True)
        out.setStyleSheet(f"background: #0a0d10; color: {TEXT}; border: 1px solid {BORDER};"
                          f"border-radius: 10px; font-family: monospace; font-size: 11px;")
        v.addWidget(out)
        proc = QProcess(dlg); proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        proc.readyRead.connect(
            lambda: out.appendPlainText(bytes(proc.readAll()).decode("utf-8", "replace").rstrip()))
        proc.finished.connect(lambda *_: out.appendPlainText("\n✓ Done. You can close this window."))
        proc.setProgram(argv[0]); proc.setArguments(argv[1:]); proc.start()
        dlg.exec()

    def closeEvent(self, e):
        self.stop_widget(); e.accept(); QApplication.quit()


def run():
    app = QApplication.instance() or QApplication(sys.argv)
    os.makedirs(guya_config.CONFIG_DIR, exist_ok=True)
    instance_lock = QLockFile(
        os.path.join(guya_config.CONFIG_DIR, "control-panel.lock")
    )
    instance_lock.setStaleLockTime(10_000)
    if not instance_lock.tryLock(100):
        if not instance_lock.removeStaleLockFile() or not instance_lock.tryLock(100):
            log.info("Guya is already running; ignoring duplicate launch.")
            return
    # Keep the QLockFile alive for the lifetime of the application.
    app._guya_instance_lock = instance_lock
    app.setStyle("Fusion")
    wz._load_fonts()
    app.setFont(QFont(UI_FONT, 11))
    app.setQuitOnLastWindowClosed(True)
    panel = ControlPanel()
    panel.show(); panel.raise_(); panel.activateWindow()
    app.exec()
