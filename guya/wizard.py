"""
Guya setup wizard (Milestone 2).

A multi-page Qt wizard shown on first run:

    Welcome → Analyze PC → Choose model → Configure (key/language/UI) → Finish

On Finish it writes ~/.guya/config.json, and the entry point then launches the
widget in a fresh process (so the model loads cleanly before Qt).

The wizard only imports lightweight things (psutil, ctypes CUDA probe) — it does
NOT load a Whisper model, so it stays fast and never creates a CUDA context.
"""

import sys
import logging

try:
    from . import config as guya_config
    from . import profiler
except ImportError:
    import config as guya_config
    import profiler

log = logging.getLogger("Guya")

IS_WIN = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"
# Use a concrete, always-present font per OS. An empty family makes Qt fall
# back to a poor default ("Sans Serif"), which rendered messy/unreadable.
if IS_WIN:
    UI_FONT = "Segoe UI"
elif IS_MAC:
    UI_FONT = "Helvetica Neue"   # clean, always present on macOS
else:
    UI_FONT = "DejaVu Sans"

# ---- palette (matches the rest of Guya) ----
BG_PRIMARY = "#0a0a0f"
BG_CARD = "#12121a"
BG_CARD_SEL = "#1b2233"
BORDER = "#1e1e2e"
BORDER_SEL = "#3b82f6"
GREEN = "#4ade80"
BLUE = "#60a5fa"
RED = "#f87171"
PURPLE = "#a78bfa"
TEXT = "#e2e8f0"
TEXT2 = "#94a3b8"
DIM = "#475569"


def run() -> bool:
    """Show the wizard. Returns True if the user completed setup (config saved)."""
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtGui import QFont as _QFont
    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyle("Fusion")
    # Set a clean default font for the whole wizard so nothing falls back to
    # an ugly substitute.
    app.setFont(_QFont(UI_FONT, 11))
    win = WizardWindow()
    win.show()
    win.raise_()
    win.activateWindow()
    app.exec()
    return win.completed


# Imports that need Qt are done lazily inside run()/classes so that importing
# this module doesn't pull in Qt unless the wizard actually runs.
from PyQt6.QtWidgets import (  # noqa: E402
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QStackedWidget, QButtonGroup, QRadioButton, QComboBox, QApplication,
)
from PyQt6.QtCore import Qt, pyqtSignal  # noqa: E402
from PyQt6.QtGui import QFont  # noqa: E402


# ============================================================
# HOTKEY CAPTURE
# ============================================================

class HotkeyCapture(QPushButton):
    """Button that captures the next key press and reports (vk, label).

    For letters/digits, Qt's key code equals the Windows virtual-key code,
    so storing e.key() is correct for the Windows keyboard hook.
    """
    captured = pyqtSignal(int, str)

    def __init__(self, parent=None):
        super().__init__("Click here, then press a key", parent)
        self._capturing = False
        self.clicked.connect(self._start)
        self.setMinimumHeight(40)

    def _start(self):
        self._capturing = True
        self.setText("Press any key now…")
        self.grabKeyboard()

    def keyPressEvent(self, e):
        if self._capturing:
            vk = e.key()
            label = (e.text().upper().strip() or e.text().strip())
            if not label:
                # Fallback name for non-printable keys
                label = e.text() or "Key"
            self._capturing = False
            self.releaseKeyboard()
            self.setText(f"Key:  {label or vk}")
            self.captured.emit(vk, label or str(vk))
        else:
            super().keyPressEvent(e)


# ============================================================
# SELECTABLE MODEL CARD
# ============================================================

class ModelCard(QRadioButton):
    """A radio-styled card for a model option."""

    def __init__(self, opt: dict, parent=None):
        super().__init__(parent)
        self.opt = opt
        self.setEnabled(opt["enabled"])
        self.setCursor(Qt.CursorShape.PointingHandCursor if opt["enabled"]
                       else Qt.CursorShape.ForbiddenCursor)
        self._build()

    def _build(self):
        o = self.opt
        title = o["title"]
        if o["recommended"]:
            title += "   ★ Recommended"
        badge = "ONLINE" if o["backend"] == "cloud" else "OFFLINE"
        disabled = "" if o["enabled"] else "   (not suitable for this PC)"
        self.setText(
            f"{title}\n{o['subtitle']}\n{badge} · {o['note']}{disabled}"
        )
        self.setStyleSheet(f"""
            QRadioButton {{
                color: {TEXT};
                background: {BG_CARD};
                border: 1px solid {BORDER};
                border-radius: 10px;
                padding: 12px 14px;
                font-size: 12px;
            }}
            QRadioButton:checked {{
                background: {BG_CARD_SEL};
                border: 1px solid {BORDER_SEL};
            }}
            QRadioButton:disabled {{ color: {DIM}; }}
            QRadioButton::indicator {{ width: 0px; height: 0px; }}
        """)
        f = QFont(UI_FONT, 11)
        self.setFont(f)


# ============================================================
# WIZARD WINDOW
# ============================================================

class WizardWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.completed = False
        self.profile = None
        self.model_options = []
        self.choices = {
            "model_opt": None,           # selected option dict
            "language": "fa",
            "hotkey_vk": 71,
            "hotkey_label": "G",
            "ui_style": "pill",
        }

        self.setWindowTitle("Guya — Setup")
        self.setFixedSize(560, 600)
        self.setStyleSheet(f"background: {BG_PRIMARY}; color: {TEXT};")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        self.stack = QStackedWidget()
        root.addWidget(self.stack, 1)

        # Build pages
        self.stack.addWidget(self._page_welcome())     # 0
        self.stack.addWidget(self._page_analyze())      # 1
        self.stack.addWidget(self._page_model())        # 2
        self.stack.addWidget(self._page_configure())    # 3
        self.stack.addWidget(self._page_finish())       # 4

        # Nav bar
        nav = QHBoxLayout()
        nav.setContentsMargins(24, 12, 24, 20)
        self.back_btn = self._btn("Back", BORDER, TEXT)
        self.back_btn.clicked.connect(self._go_back)
        self.next_btn = self._btn("Next", BLUE, "#0a0a0f")
        self.next_btn.clicked.connect(self._go_next)
        nav.addWidget(self.back_btn)
        nav.addStretch()
        nav.addWidget(self.next_btn)
        root.addLayout(nav)

        self._update_nav()

    # ---- helpers ----

    def _btn(self, text, bg, fg):
        b = QPushButton(text)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setMinimumSize(110, 40)
        b.setFont(QFont(UI_FONT, 11, QFont.Weight.DemiBold))
        b.setStyleSheet(f"""
            QPushButton {{ background: {bg}; color: {fg}; border: none;
                           border-radius: 10px; padding: 0 22px; }}
            QPushButton:disabled {{ background: #1a1a25; color: {DIM}; }}
        """)
        return b

    def _title(self, text, sub=""):
        box = QVBoxLayout()
        t = QLabel(text)
        t.setFont(QFont(UI_FONT, 20, QFont.Weight.Bold))
        t.setStyleSheet(f"color: {TEXT};")
        box.addWidget(t)
        if sub:
            s = QLabel(sub)
            s.setFont(QFont(UI_FONT, 11))
            s.setStyleSheet(f"color: {TEXT2};")
            s.setWordWrap(True)
            box.addWidget(s)
        return box

    def _page(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(32, 32, 32, 8)
        lay.setSpacing(14)
        return w, lay

    # ---- Page 0: Welcome ----

    def _page_welcome(self):
        w, lay = self._page()
        lay.addStretch()
        logo = QLabel("گویا  ·  Guya")
        logo.setFont(QFont(UI_FONT, 30, QFont.Weight.Bold))
        logo.setStyleSheet(f"color: {TEXT};")
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(logo)

        sub = QLabel("Speech-to-Text for Persian & English\nHold a key, speak, and your words are typed for you.")
        sub.setFont(QFont(UI_FONT, 12))
        sub.setStyleSheet(f"color: {TEXT2};")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(sub)

        note = QLabel("This quick setup will check your computer and help you\nchoose the best option. Takes about a minute.")
        note.setFont(QFont(UI_FONT, 10))
        note.setStyleSheet(f"color: {DIM};")
        note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(note)
        lay.addStretch()
        return w

    # ---- Page 1: Analyze ----

    def _page_analyze(self):
        w, lay = self._page()
        lay.addLayout(self._title("Step 1 — Your computer",
                                  "Guya will check your hardware to recommend the best model."))
        self.analyze_btn = self._btn("Analyze my PC", GREEN, "#0a0a0f")
        self.analyze_btn.setMinimumHeight(44)
        self.analyze_btn.clicked.connect(self._do_analyze)
        lay.addWidget(self.analyze_btn)

        self.profile_box = QLabel("")
        self.profile_box.setFont(QFont(UI_FONT, 11))
        self.profile_box.setStyleSheet(
            f"color: {TEXT}; background: {BG_CARD}; border: 1px solid {BORDER};"
            f"border-radius: 10px; padding: 16px;")
        self.profile_box.setWordWrap(True)
        self.profile_box.setVisible(False)
        lay.addWidget(self.profile_box)
        lay.addStretch()
        return w

    def _do_analyze(self):
        self.analyze_btn.setText("Analyzing…")
        self.analyze_btn.setEnabled(False)
        QApplication.processEvents()
        self.profile = profiler.get_device_profile()
        p = self.profile
        gpu_line = (f"GPU:  {p['gpu_name']}  ({p['vram_gb']:.1f} GB)"
                    if p["has_cuda"] else
                    ("GPU:  Apple Silicon (CPU mode for STT)" if p["apple_silicon"]
                     else "GPU:  none detected (CPU mode)"))
        ram = f"{p['ram_gb']:.0f} GB" if p["ram_gb"] else "unknown"
        cores = p["cpu_cores"] or "?"
        self.profile_box.setText(
            f"OS:    {p['os']} ({p['machine']})\n"
            f"CPU:   {p['cpu_name']}  ·  {cores} cores\n"
            f"RAM:   {ram}\n"
            f"{gpu_line}"
        )
        self.profile_box.setVisible(True)
        self.analyze_btn.setText("Re-analyze")
        self.analyze_btn.setEnabled(True)
        # Build model options now
        self.model_options = profiler.recommend_models(self.profile)
        self._populate_models()
        self._update_nav()

    # ---- Page 2: Model ----

    def _page_model(self):
        w, lay = self._page()
        lay.addLayout(self._title("Step 2 — Choose a model",
                                  "How should Guya recognize your speech?"))
        self.model_group = QButtonGroup(self)
        self.model_container = QVBoxLayout()
        self.model_container.setSpacing(10)
        lay.addLayout(self.model_container)
        lay.addStretch()
        return w

    def _populate_models(self):
        # Clear old
        while self.model_container.count():
            item = self.model_container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for btn in list(self.model_group.buttons()):
            self.model_group.removeButton(btn)

        for opt in self.model_options:
            card = ModelCard(opt)
            self.model_group.addButton(card)
            self.model_container.addWidget(card)
            if opt["recommended"] and opt["enabled"]:
                card.setChecked(True)
                self.choices["model_opt"] = opt
            card.toggled.connect(lambda checked, o=opt: self._pick_model(checked, o))

    def _pick_model(self, checked, opt):
        if checked:
            self.choices["model_opt"] = opt

    # ---- Page 3: Configure ----

    def _page_configure(self):
        w, lay = self._page()
        lay.addLayout(self._title("Step 3 — Configure",
                                  "Set your push-to-talk key and language."))

        # Language
        lang_lbl = QLabel("Default language")
        lang_lbl.setFont(QFont(UI_FONT, 11, QFont.Weight.DemiBold))
        lang_lbl.setStyleSheet(f"color: {TEXT2};")
        lay.addWidget(lang_lbl)
        self.lang_combo = QComboBox()
        self.lang_combo.addItem("Persian (فارسی)", "fa")
        self.lang_combo.addItem("English", "en")
        self.lang_combo.addItem("Both / bilingual", "dual")
        self.lang_combo.setMinimumHeight(38)
        self.lang_combo.setStyleSheet(f"""
            QComboBox {{ background: {BG_CARD}; color: {TEXT};
                border: 1px solid {BORDER}; border-radius: 8px; padding: 6px 12px; }}
            QComboBox QAbstractItemView {{ background: {BG_CARD}; color: {TEXT};
                selection-background-color: {BG_CARD_SEL}; }}
        """)
        self.lang_combo.currentIndexChanged.connect(
            lambda _: self.choices.update(language=self.lang_combo.currentData()))
        lay.addWidget(self.lang_combo)

        # Hotkey
        key_lbl = QLabel("Push-to-talk key (hold to speak)")
        key_lbl.setFont(QFont(UI_FONT, 11, QFont.Weight.DemiBold))
        key_lbl.setStyleSheet(f"color: {TEXT2};")
        lay.addWidget(key_lbl)

        if IS_MAC:
            mac_lbl = QLabel("On macOS the push-to-talk key is Right Option (⌥).")
            mac_lbl.setFont(QFont(UI_FONT, 11))
            mac_lbl.setStyleSheet(
                f"color: {TEXT}; background: {BG_CARD}; border: 1px solid {BORDER};"
                f"border-radius: 8px; padding: 12px;")
            mac_lbl.setWordWrap(True)
            lay.addWidget(mac_lbl)
            self.choices["hotkey_vk"] = 0xA4   # not used on mac
            self.choices["hotkey_label"] = "⌥"
        else:
            self.key_capture = HotkeyCapture()
            self.key_capture.setStyleSheet(f"""
                QPushButton {{ background: {BG_CARD}; color: {TEXT};
                    border: 1px solid {BORDER}; border-radius: 8px; padding: 8px; }}
            """)
            self.key_capture.captured.connect(self._on_key)
            lay.addWidget(self.key_capture)
            hint = QLabel("Tip: pick a letter you rarely press mid-sentence (default: G).")
            hint.setFont(QFont(UI_FONT, 9))
            hint.setStyleSheet(f"color: {DIM};")
            lay.addWidget(hint)

        lay.addStretch()
        return w

    def _on_key(self, vk, label):
        self.choices["hotkey_vk"] = vk
        self.choices["hotkey_label"] = label

    # ---- Page 4: Finish ----

    def _page_finish(self):
        w, lay = self._page()
        lay.addLayout(self._title("All set!", "Review your choices, then finish."))
        self.summary = QLabel("")
        self.summary.setFont(QFont(UI_FONT, 12))
        self.summary.setStyleSheet(
            f"color: {TEXT}; background: {BG_CARD}; border: 1px solid {BORDER};"
            f"border-radius: 10px; padding: 18px;")
        self.summary.setWordWrap(True)
        lay.addWidget(self.summary)

        tip = QLabel("")
        tip.setObjectName("finishtip")
        tip.setFont(QFont(UI_FONT, 10))
        tip.setStyleSheet(f"color: {TEXT2};")
        tip.setWordWrap(True)
        self.finish_tip = tip
        lay.addWidget(tip)
        lay.addStretch()
        return w

    def _refresh_summary(self):
        opt = self.choices["model_opt"] or {}
        lang = {"fa": "Persian", "en": "English", "dual": "Bilingual"}.get(
            self.choices["language"], self.choices["language"])
        backend = "Online (cloud)" if opt.get("backend") == "cloud" else "Offline (on your PC)"
        self.summary.setText(
            f"Model:     {opt.get('title','?')}  ({opt.get('model_size','?')})\n"
            f"Runs:      {backend}\n"
            f"Language:  {lang}\n"
            f"Hotkey:    {self.choices['hotkey_label']}"
        )
        if opt.get("backend") == "cloud":
            self.finish_tip.setText(
                "You chose the cloud option. After finishing, you'll be guided to "
                "connect an online provider (set up in a later step).")
        else:
            self.finish_tip.setText(
                "After finishing, Guya will download the model if needed (one time) "
                "and the widget will appear at the top of your screen.")

    # ---- Navigation ----

    def _go_next(self):
        idx = self.stack.currentIndex()
        if idx == self.stack.count() - 1:
            self._finish()
            return
        if idx == 4 - 1:  # leaving configure → refresh summary
            self._refresh_summary()
        self.stack.setCurrentIndex(idx + 1)
        if self.stack.currentIndex() == 4:
            self._refresh_summary()
        self._update_nav()

    def _go_back(self):
        idx = self.stack.currentIndex()
        if idx > 0:
            self.stack.setCurrentIndex(idx - 1)
        self._update_nav()

    def _update_nav(self):
        idx = self.stack.currentIndex()
        self.back_btn.setEnabled(idx > 0)
        # Gate: can't pass Analyze until profiled; can't pass Model until one picked.
        can_next = True
        if idx == 1 and self.profile is None:
            can_next = False
        if idx == 2 and not self.choices["model_opt"]:
            can_next = False
        self.next_btn.setEnabled(can_next)
        self.next_btn.setText("Finish" if idx == self.stack.count() - 1 else "Next")

    # ---- Finish: write config ----

    def _finish(self):
        opt = self.choices["model_opt"]
        cfg = guya_config.load_config()
        cfg["model"]["backend"] = opt["backend"]
        cfg["model"]["size"] = opt["model_size"]
        cfg["model"]["device"] = opt["device"]
        cfg["model"]["compute_type"] = "auto"
        cfg["language"] = self.choices["language"]
        cfg["hotkey"]["vk"] = self.choices["hotkey_vk"]
        cfg["hotkey"]["label"] = self.choices["hotkey_label"]
        cfg["hotkey"]["name"] = self.choices["hotkey_label"]
        cfg["ui"]["style"] = self.choices["ui_style"]
        if guya_config.save_config(cfg):
            self.completed = True
            log.info("Setup complete; config saved.")
            self.close()
