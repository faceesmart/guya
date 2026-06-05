"""
Guya setup wizard.

Modern multi-page first-run flow:

    Welcome → Device (analyze + benchmark) → Model → Settings → Review
            → Download (progress) → launch

On finish it writes ~/.guya/config.json, downloads the chosen offline model
(with a progress bar), creates a double-click launcher, and the entry point
then relaunches into the widget.
"""

import os
import sys
import glob
import json
import logging

try:
    from . import config as guya_config
    from . import profiler
    from . import benchmark
    from . import cloud_engine
    from . import launcher_gen
except ImportError:
    import config as guya_config
    import profiler
    import benchmark
    import cloud_engine
    import launcher_gen

log = logging.getLogger("Guya")

IS_WIN = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"
if IS_WIN:
    UI_FONT = "Segoe UI"
elif IS_MAC:
    UI_FONT = "Helvetica Neue"
else:
    UI_FONT = "DejaVu Sans"

# ---- modern dark palette with a violet accent ----
BG = "#0b0b12"
CARD = "#16161f"
CARD_SEL = "#1d1b33"
BORDER = "#26263a"
ACCENT = "#7c6cff"
ACCENT_TEXT = "#0b0b12"
GREEN = "#34d399"
RED = "#f87171"
BLUE = "#7c6cff"
TEXT = "#ECECF1"
TEXT2 = "#9a9ab0"
DIM = "#5a5a72"

STEPS = ["Welcome", "Device", "Model", "Settings", "Finish"]
PAGE_TO_STEP = [0, 1, 2, 3, 4, 4]   # page index -> step index (download = Finish)

# Approximate on-disk size per model (MB) — for the download progress bar.
MODEL_SIZE_MB = {
    "tiny": 75, "base": 145, "small": 484, "medium": 1530,
    "large-v3": 3090, "large-v3-turbo": 1620,
}


def _hub_root():
    return os.environ.get(
        "HUGGINGFACE_HUB_CACHE",
        os.path.join(os.path.expanduser("~"), ".cache", "huggingface", "hub"))


def model_is_cached(size: str) -> bool:
    for d in glob.glob(os.path.join(_hub_root(), f"models--*--faster-whisper-{size}",
                                    "snapshots", "*")):
        if os.path.isfile(os.path.join(d, "model.bin")):
            return True
    return False


def model_downloaded_mb(size: str) -> float:
    total = 0
    for d in glob.glob(os.path.join(_hub_root(), f"models--*--faster-whisper-{size}")):
        for dp, _dn, files in os.walk(d):
            for fn in files:
                try:
                    total += os.path.getsize(os.path.join(dp, fn))
                except OSError:
                    pass
    return total / (1024 * 1024)


def run() -> bool:
    """Show the wizard. Returns True if setup completed (config saved)."""
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtGui import QFont as _QFont
    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setFont(_QFont(UI_FONT, 11))
    win = WizardWindow()
    win.show()
    win.raise_()
    win.activateWindow()
    app.exec()
    return win.completed


from PyQt6.QtWidgets import (  # noqa: E402
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QStackedWidget, QComboBox, QApplication, QLineEdit, QProgressBar,
)
from PyQt6.QtCore import Qt, QProcess, QTimer, pyqtSignal  # noqa: E402
from PyQt6.QtGui import QFont  # noqa: E402


# ============================================================
# STEP INDICATOR
# ============================================================

class StepIndicator(QWidget):
    """A slim row of numbered steps at the top of the wizard."""

    def __init__(self):
        super().__init__()
        self._current = 0
        self._labels = []
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        lay.addStretch()
        for i, name in enumerate(STEPS):
            lbl = QLabel(f"{i+1}. {name}")
            lbl.setFont(QFont(UI_FONT, 10, QFont.Weight.DemiBold))
            self._labels.append(lbl)
            lay.addWidget(lbl)
            if i < len(STEPS) - 1:
                sep = QLabel("—")
                sep.setStyleSheet(f"color: {DIM};")
                lay.addWidget(sep)
        lay.addStretch()
        self.set_step(0)

    def set_step(self, idx):
        self._current = idx
        for i, lbl in enumerate(self._labels):
            if i == idx:
                lbl.setStyleSheet(f"color: {ACCENT};")
            elif i < idx:
                lbl.setStyleSheet(f"color: {TEXT2};")
            else:
                lbl.setStyleSheet(f"color: {DIM};")


# ============================================================
# CUSTOM MODEL CARD (clickable, modern)
# ============================================================

class ModelCard(QFrame):
    def __init__(self, opt: dict, on_click):
        super().__init__()
        self.opt = opt
        self.on_click = on_click
        self.selected = False
        self.setObjectName("card")
        if opt["enabled"]:
            self.setCursor(Qt.CursorShape.PointingHandCursor)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 13, 16, 13)
        lay.setSpacing(3)

        top = QHBoxLayout()
        top.setSpacing(8)
        title = QLabel(opt["title"])
        title.setFont(QFont(UI_FONT, 13, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {TEXT}; background: transparent;")
        top.addWidget(title)
        top.addStretch()
        if opt["recommended"]:
            badge = QLabel("★ Recommended")
            badge.setFont(QFont(UI_FONT, 9, QFont.Weight.DemiBold))
            badge.setStyleSheet(
                f"color: {ACCENT}; background: rgba(124,108,255,0.12);"
                f"border-radius: 8px; padding: 2px 8px;")
            top.addWidget(badge)
        kind = QLabel("ONLINE" if opt["backend"] == "cloud" else "OFFLINE")
        kind.setFont(QFont(UI_FONT, 8, QFont.Weight.DemiBold))
        kind.setStyleSheet(f"color: {TEXT2}; background: transparent;")
        top.addWidget(kind)
        lay.addLayout(top)

        sub = QLabel(opt["subtitle"])
        sub.setFont(QFont(UI_FONT, 10))
        sub.setStyleSheet(f"color: {TEXT2}; background: transparent;")
        lay.addWidget(sub)

        note = opt["note"]
        if not opt["enabled"]:
            note += "   ·   not suitable for this PC"
        nlbl = QLabel(note)
        nlbl.setFont(QFont(UI_FONT, 9))
        nlbl.setStyleSheet(f"color: {DIM}; background: transparent;")
        lay.addWidget(nlbl)

        lat = opt.get("predicted_latency_sec")
        if lat is not None:
            lt = QLabel(f"⏱ ~{lat:g}s (estimated) for 10s of speech on your machine")
            lt.setFont(QFont(UI_FONT, 9, QFont.Weight.DemiBold))
            lt.setStyleSheet(f"color: {ACCENT}; background: transparent;")
            lay.addWidget(lt)

        self._apply_style()

    def _apply_style(self):
        if not self.opt["enabled"]:
            border, bg = BORDER, "#101018"
        elif self.selected:
            border, bg = ACCENT, CARD_SEL
        else:
            border, bg = BORDER, CARD
        self.setStyleSheet(
            f"QFrame#card {{ background: {bg}; border: 1.5px solid {border};"
            f"border-radius: 12px; }}")

    def set_selected(self, sel):
        self.selected = sel
        self._apply_style()

    def mousePressEvent(self, e):
        if self.opt["enabled"]:
            self.on_click(self)


# ============================================================
# WIZARD WINDOW
# ============================================================

class WizardWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.completed = False
        self.profile = None
        self.model_options = []
        self.rtf_base = None
        self.bench_proc = None
        self.bench_done = False
        self.dl_proc = None
        self.dl_timer = None
        self.cards = []
        self.selected_card = None
        self.cloud_tested_ok = False
        self.choices = {
            "model_opt": None,
            "language": "fa",
            "hotkey_vk": 71,
            "hotkey_label": "G",
            "ui_style": "pill",
            "cloud_api_key": "",
        }

        self.setWindowTitle("Guya — Setup")
        self.setFixedSize(600, 660)
        self.setStyleSheet(f"background: {BG}; color: {TEXT};")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Step indicator header
        header = QWidget()
        header.setStyleSheet(f"background: {BG};")
        hlay = QVBoxLayout(header)
        hlay.setContentsMargins(20, 16, 20, 12)
        self.steps = StepIndicator()
        hlay.addWidget(self.steps)
        root.addWidget(header)

        self.stack = QStackedWidget()
        root.addWidget(self.stack, 1)

        self.stack.addWidget(self._page_welcome())     # 0
        self.stack.addWidget(self._page_analyze())      # 1
        self.stack.addWidget(self._page_model())        # 2
        self.stack.addWidget(self._page_configure())    # 3
        self.stack.addWidget(self._page_finish())       # 4
        self.stack.addWidget(self._page_download())      # 5

        # Nav bar
        navw = QWidget()
        nav = QHBoxLayout(navw)
        nav.setContentsMargins(24, 10, 24, 20)
        self.back_btn = self._btn("Back", "ghost")
        self.back_btn.clicked.connect(self._go_back)
        self.next_btn = self._btn("Next", "primary")
        self.next_btn.clicked.connect(self._go_next)
        nav.addWidget(self.back_btn)
        nav.addStretch()
        nav.addWidget(self.next_btn)
        root.addWidget(navw)

        self._update_nav()

    # ---- styled widgets ----

    def _btn(self, text, kind="primary"):
        b = QPushButton(text)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setMinimumSize(120, 42)
        b.setFont(QFont(UI_FONT, 11, QFont.Weight.DemiBold))
        if kind == "primary":
            b.setStyleSheet(f"""
                QPushButton {{ background: {ACCENT}; color: {ACCENT_TEXT}; border: none;
                    border-radius: 11px; padding: 0 24px; }}
                QPushButton:hover {{ background: #8d7dff; }}
                QPushButton:disabled {{ background: #23233140; color: {DIM}; }}
            """)
        elif kind == "green":
            b.setStyleSheet(f"""
                QPushButton {{ background: {GREEN}; color: {ACCENT_TEXT}; border: none;
                    border-radius: 11px; padding: 0 24px; }}
                QPushButton:hover {{ background: #4ade80; }}
                QPushButton:disabled {{ background: #23233140; color: {DIM}; }}
            """)
        else:  # ghost
            b.setStyleSheet(f"""
                QPushButton {{ background: transparent; color: {TEXT2};
                    border: 1px solid {BORDER}; border-radius: 11px; padding: 0 24px; }}
                QPushButton:hover {{ border-color: {TEXT2}; color: {TEXT}; }}
                QPushButton:disabled {{ color: {DIM}; border-color: {BORDER}; }}
            """)
        return b

    def _title(self, text, sub=""):
        box = QVBoxLayout()
        box.setSpacing(4)
        t = QLabel(text)
        t.setFont(QFont(UI_FONT, 22, QFont.Weight.Bold))
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
        lay.setContentsMargins(34, 22, 34, 10)
        lay.setSpacing(14)
        return w, lay

    def _info_card(self):
        lbl = QLabel("")
        lbl.setFont(QFont(UI_FONT, 11))
        lbl.setStyleSheet(
            f"color: {TEXT}; background: {CARD}; border: 1px solid {BORDER};"
            f"border-radius: 12px; padding: 16px;")
        lbl.setWordWrap(True)
        return lbl

    # ---- Page 0: Welcome ----

    def _page_welcome(self):
        w, lay = self._page()
        lay.addStretch()
        logo = QLabel("گویا")
        logo.setFont(QFont(UI_FONT, 46, QFont.Weight.Bold))
        logo.setStyleSheet(f"color: {TEXT};")
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(logo)
        name = QLabel("Guya")
        name.setFont(QFont(UI_FONT, 16, QFont.Weight.DemiBold))
        name.setStyleSheet(f"color: {ACCENT};")
        name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(name)
        sub = QLabel("Speech-to-Text for Persian and English.\n"
                     "Hold a key, speak, and your words are typed for you.")
        sub.setFont(QFont(UI_FONT, 12))
        sub.setStyleSheet(f"color: {TEXT2};")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(sub)
        note = QLabel("This quick setup checks your computer and helps you choose\n"
                      "the best option. It takes about a minute.")
        note.setFont(QFont(UI_FONT, 10))
        note.setStyleSheet(f"color: {DIM};")
        note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(note)
        lay.addStretch()
        return w

    # ---- Page 1: Analyze ----

    def _page_analyze(self):
        w, lay = self._page()
        lay.addLayout(self._title("Your computer",
                                  "Guya checks your hardware AND measures its real speed, "
                                  "then recommends the best model for your machine."))
        self.analyze_btn = self._btn("Analyze my PC", "green")
        self.analyze_btn.clicked.connect(self._do_analyze)
        lay.addWidget(self.analyze_btn)
        self.profile_box = self._info_card()
        self.profile_box.setVisible(False)
        lay.addWidget(self.profile_box)
        self.bench_status = QLabel("")
        self.bench_status.setFont(QFont(UI_FONT, 11))
        self.bench_status.setStyleSheet(f"color: {ACCENT};")
        self.bench_status.setWordWrap(True)
        self.bench_status.setVisible(False)
        lay.addWidget(self.bench_status)
        lay.addStretch()
        return w

    def _do_analyze(self):
        self.analyze_btn.setText("Analyzing…")
        self.analyze_btn.setEnabled(False)
        QApplication.processEvents()

        self.profile = profiler.get_device_profile()
        p = self.profile
        gpu_line = (f"GPU      {p['gpu_name']}  ({p['vram_gb']:.1f} GB)"
                    if p["has_cuda"] else
                    ("GPU      Apple Silicon (CPU mode for speech)" if p["apple_silicon"]
                     else "GPU      none detected (CPU mode)"))
        ram = f"{p['ram_gb']:.0f} GB" if p["ram_gb"] else "unknown"
        cores = p["cpu_cores"] or "?"
        self.profile_box.setText(
            f"OS       {p['os']} ({p['machine']})\n"
            f"CPU      {p['cpu_name']}  ·  {cores} cores\n"
            f"RAM      {ram}\n"
            f"{gpu_line}")
        self.profile_box.setVisible(True)

        self.model_options = profiler.recommend_models(self.profile)
        self._populate_models()
        self._start_benchmark()

    # ---- benchmark (async) ----

    def _start_benchmark(self):
        device = "cuda" if self.profile["has_cuda"] else "cpu"
        compute = "float16" if self.profile["has_cuda"] else "int8"
        self.bench_status.setVisible(True)
        self.bench_status.setStyleSheet(f"color: {ACCENT};")
        self.bench_status.setText("⏱  Measuring your computer's speed… (downloads a small "
                                  "test model the first time — about 20–40s)")
        QApplication.processEvents()
        self.bench_proc = QProcess(self)
        self.bench_proc.finished.connect(self._on_benchmark_done)
        self.bench_proc.setProgram(sys.executable)
        self.bench_proc.setArguments(["-m", "guya.benchmark",
                                      "--device", device, "--compute", compute])
        self.bench_proc.start()
        self._update_nav()

    def _on_benchmark_done(self, exit_code, _status):
        out = ""
        try:
            out = bytes(self.bench_proc.readAllStandardOutput()).decode("utf-8", "replace")
            out += bytes(self.bench_proc.readAllStandardError()).decode("utf-8", "replace")
        except Exception:
            pass
        rtf = None
        for line in out.splitlines():
            if line.startswith("BENCH_JSON:"):
                try:
                    rtf = json.loads(line[len("BENCH_JSON:"):]).get("rtf_base")
                except Exception:
                    pass
        if rtf is not None:
            self.rtf_base = rtf
            benchmark.annotate_and_recommend(self.model_options, rtf)
            self._populate_models()
            self.bench_status.setStyleSheet(f"color: {GREEN};")
            self.bench_status.setText("✓  Speed measured. The recommendation is tuned to "
                                      "YOUR machine (each model shows its expected wait time).")
        else:
            self.bench_status.setStyleSheet(f"color: {DIM};")
            self.bench_status.setText("Could not run the speed test; using a specs-based "
                                      "recommendation instead.")
        self.bench_done = True
        self.analyze_btn.setText("Re-analyze")
        self.analyze_btn.setEnabled(True)
        self._update_nav()

    # ---- Page 2: Model ----

    def _page_model(self):
        w, lay = self._page()
        lay.addLayout(self._title("Choose a model", "How should Guya recognize your speech?"))
        self.model_container = QVBoxLayout()
        self.model_container.setSpacing(10)
        lay.addLayout(self.model_container)

        # Cloud connect panel (hidden unless Cloud is selected)
        self.cloud_panel = QFrame()
        self.cloud_panel.setObjectName("cloudpanel")
        self.cloud_panel.setStyleSheet(
            f"QFrame#cloudpanel {{ background: {CARD}; border: 1.5px solid {ACCENT};"
            f"border-radius: 12px; }} QLabel {{ background: transparent; border: none; }}")
        cp = QVBoxLayout(self.cloud_panel)
        cp.setContentsMargins(16, 13, 16, 13)
        cp.setSpacing(8)
        guide = QLabel("Connect a free online account (Groq):\n"
                       "1. Open  console.groq.com/keys  and sign in (free, no card)\n"
                       "2. Create an API key and copy it\n"
                       "3. Paste it below and press Test")
        guide.setFont(QFont(UI_FONT, 10))
        guide.setStyleSheet(f"color: {TEXT2};")
        guide.setWordWrap(True)
        cp.addWidget(guide)
        self.key_edit = QLineEdit()
        self.key_edit.setPlaceholderText("Paste your API key (gsk_…)")
        self.key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_edit.setMinimumHeight(38)
        self.key_edit.setStyleSheet(
            f"QLineEdit {{ background: {BG}; color: {TEXT}; border: 1px solid {BORDER};"
            f"border-radius: 9px; padding: 6px 12px; }}"
            f"QLineEdit:focus {{ border: 1px solid {ACCENT}; }}")
        self.key_edit.textChanged.connect(self._on_key_changed)
        cp.addWidget(self.key_edit)
        row = QHBoxLayout()
        self.test_btn = self._btn("Test", "primary")
        self.test_btn.setMinimumSize(96, 38)
        self.test_btn.clicked.connect(self._test_cloud)
        row.addWidget(self.test_btn)
        self.cloud_status = QLabel("")
        self.cloud_status.setFont(QFont(UI_FONT, 10))
        self.cloud_status.setStyleSheet(f"color: {TEXT2};")
        self.cloud_status.setWordWrap(True)
        row.addWidget(self.cloud_status, 1)
        cp.addLayout(row)
        priv = QLabel("Note: the online option sends your voice to the provider's servers. "
                      "Offline models keep everything on your device.")
        priv.setFont(QFont(UI_FONT, 9))
        priv.setStyleSheet(f"color: {DIM};")
        priv.setWordWrap(True)
        cp.addWidget(priv)
        self.cloud_panel.setVisible(False)
        lay.addWidget(self.cloud_panel)
        lay.addStretch()
        return w

    def _populate_models(self):
        while self.model_container.count():
            item = self.model_container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.cards = []
        self.selected_card = None
        for opt in self.model_options:
            card = ModelCard(opt, self._select_card)
            self.cards.append(card)
            self.model_container.addWidget(card)
            if opt["recommended"] and opt["enabled"]:
                self._select_card(card)

    def _select_card(self, card):
        for c in self.cards:
            c.set_selected(c is card)
        self.selected_card = card
        self.choices["model_opt"] = card.opt
        is_cloud = card.opt["backend"] == "cloud"
        self.cloud_panel.setVisible(is_cloud)
        self._update_nav()

    def _on_key_changed(self, text):
        self.choices["cloud_api_key"] = text.strip()
        self.cloud_tested_ok = False
        self.cloud_status.setText("")
        self._update_nav()

    def _test_cloud(self):
        key = self.key_edit.text().strip()
        if not key:
            self.cloud_status.setStyleSheet(f"color: {RED};")
            self.cloud_status.setText("Paste a key first.")
            return
        self.test_btn.setText("Testing…")
        self.test_btn.setEnabled(False)
        self.cloud_status.setStyleSheet(f"color: {ACCENT};")
        self.cloud_status.setText("Checking your key…")
        QApplication.processEvents()
        ok, msg = cloud_engine.test_connection(key, provider="groq")
        self.cloud_tested_ok = ok
        self.cloud_status.setStyleSheet(f"color: {GREEN if ok else RED};")
        self.cloud_status.setText(("✓ " if ok else "✗ ") + msg)
        self.test_btn.setText("Test")
        self.test_btn.setEnabled(True)
        self._update_nav()

    # ---- Page 3: Configure ----

    def _page_configure(self):
        w, lay = self._page()
        lay.addLayout(self._title("Settings", "Set your push-to-talk key and language."))

        lang_lbl = QLabel("Default language")
        lang_lbl.setFont(QFont(UI_FONT, 11, QFont.Weight.DemiBold))
        lang_lbl.setStyleSheet(f"color: {TEXT2};")
        lay.addWidget(lang_lbl)
        self.lang_combo = QComboBox()
        self.lang_combo.addItem("Persian (فارسی)", "fa")
        self.lang_combo.addItem("English", "en")
        self.lang_combo.addItem("Both / bilingual", "dual")
        self.lang_combo.setMinimumHeight(40)
        self.lang_combo.setStyleSheet(
            f"QComboBox {{ background: {CARD}; color: {TEXT}; border: 1px solid {BORDER};"
            f"border-radius: 9px; padding: 6px 12px; }}"
            f"QComboBox QAbstractItemView {{ background: {CARD}; color: {TEXT};"
            f"selection-background-color: {CARD_SEL}; }}")
        self.lang_combo.currentIndexChanged.connect(
            lambda _: self.choices.update(language=self.lang_combo.currentData()))
        lay.addWidget(self.lang_combo)

        key_lbl = QLabel("Push-to-talk key (hold to speak)")
        key_lbl.setFont(QFont(UI_FONT, 11, QFont.Weight.DemiBold))
        key_lbl.setStyleSheet(f"color: {TEXT2};")
        lay.addWidget(key_lbl)
        if IS_MAC:
            mac_lbl = QLabel("On macOS the push-to-talk key is Right Option (⌥).")
            mac_lbl.setFont(QFont(UI_FONT, 11))
            mac_lbl.setStyleSheet(
                f"color: {TEXT}; background: {CARD}; border: 1px solid {BORDER};"
                f"border-radius: 9px; padding: 12px;")
            mac_lbl.setWordWrap(True)
            lay.addWidget(mac_lbl)
            self.choices["hotkey_vk"] = 0xA4
            self.choices["hotkey_label"] = "⌥"
        else:
            self.key_capture = HotkeyCapture()
            self.key_capture.setStyleSheet(
                f"QPushButton {{ background: {CARD}; color: {TEXT};"
                f"border: 1px solid {BORDER}; border-radius: 9px; padding: 10px; }}")
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

    # ---- Page 4: Review ----

    def _page_finish(self):
        w, lay = self._page()
        lay.addLayout(self._title("Review", "Check your choices, then finish setup."))
        self.summary = self._info_card()
        self.summary.setFont(QFont(UI_FONT, 12))
        lay.addWidget(self.summary)
        self.finish_tip = QLabel("")
        self.finish_tip.setFont(QFont(UI_FONT, 10))
        self.finish_tip.setStyleSheet(f"color: {TEXT2};")
        self.finish_tip.setWordWrap(True)
        lay.addWidget(self.finish_tip)
        lay.addStretch()
        return w

    def _refresh_summary(self):
        opt = self.choices["model_opt"] or {}
        lang = {"fa": "Persian", "en": "English", "dual": "Bilingual"}.get(
            self.choices["language"], self.choices["language"])
        backend = "Online (cloud)" if opt.get("backend") == "cloud" else "Offline (on your PC)"
        self.summary.setText(
            f"Model       {opt.get('title','?')}  ({opt.get('model_size','?')})\n"
            f"Runs        {backend}\n"
            f"Language    {lang}\n"
            f"Hotkey      {self.choices['hotkey_label']}")
        if opt.get("backend") == "cloud":
            self.finish_tip.setText("Cloud chosen — no model download needed. After finishing, "
                                    "Guya creates a launcher and starts.")
        else:
            self.finish_tip.setText("After finishing, Guya downloads the model if needed (shown "
                                    "with a progress bar), creates a double-click launcher, "
                                    "and starts the widget.")

    # ---- Page 5: Download ----

    def _page_download(self):
        w, lay = self._page()
        lay.addStretch()
        self.dl_title = QLabel("Downloading model…")
        self.dl_title.setFont(QFont(UI_FONT, 18, QFont.Weight.Bold))
        self.dl_title.setStyleSheet(f"color: {TEXT};")
        self.dl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.dl_title)
        self.dl_bar = QProgressBar()
        self.dl_bar.setRange(0, 100)
        self.dl_bar.setValue(0)
        self.dl_bar.setTextVisible(True)
        self.dl_bar.setMinimumHeight(22)
        self.dl_bar.setStyleSheet(
            f"QProgressBar {{ background: {CARD}; border: 1px solid {BORDER};"
            f"border-radius: 11px; text-align: center; color: {TEXT}; }}"
            f"QProgressBar::chunk {{ background: {ACCENT}; border-radius: 10px; }}")
        lay.addWidget(self.dl_bar)
        self.dl_status = QLabel("")
        self.dl_status.setFont(QFont(UI_FONT, 10))
        self.dl_status.setStyleSheet(f"color: {TEXT2};")
        self.dl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.dl_status)
        lay.addStretch()
        return w

    # ---- Navigation ----

    def _go_next(self):
        idx = self.stack.currentIndex()
        if idx == 4:                       # Review → Finish
            self._finish()
            return
        if idx == 3:                       # leaving Settings → refresh review
            self._refresh_summary()
        self.stack.setCurrentIndex(idx + 1)
        if self.stack.currentIndex() == 4:
            self._refresh_summary()
        self._sync_step()
        self._update_nav()

    def _go_back(self):
        idx = self.stack.currentIndex()
        if 0 < idx <= 4:
            self.stack.setCurrentIndex(idx - 1)
        self._sync_step()
        self._update_nav()

    def _sync_step(self):
        self.steps.set_step(PAGE_TO_STEP[self.stack.currentIndex()])

    def _update_nav(self):
        idx = self.stack.currentIndex()
        # Download page: no nav.
        if idx == 5:
            self.back_btn.setVisible(False)
            self.next_btn.setVisible(False)
            return
        self.back_btn.setVisible(True)
        self.next_btn.setVisible(True)
        self.back_btn.setEnabled(idx > 0)
        can_next = True
        if idx == 1 and self.profile is None:
            can_next = False
        if idx == 2:
            opt = self.choices["model_opt"]
            if not opt:
                can_next = False
            elif opt["backend"] == "cloud" and not self.choices.get("cloud_api_key"):
                can_next = False
        self.next_btn.setEnabled(can_next)
        self.next_btn.setText("Finish" if idx == 4 else "Next")

    # ---- Finish → save config, create launcher, download, complete ----

    def _finish(self):
        opt = self.choices["model_opt"]
        cfg = guya_config.load_config()
        cfg["model"]["backend"] = opt["backend"]
        cfg["model"]["size"] = opt["model_size"]
        cfg["model"]["device"] = opt["device"]
        cfg["model"]["compute_type"] = "auto"
        if opt["backend"] == "cloud":
            cfg["cloud"]["provider"] = "groq"
            cfg["cloud"]["api_key"] = self.choices.get("cloud_api_key", "")
        cfg["language"] = self.choices["language"]
        cfg["hotkey"]["vk"] = self.choices["hotkey_vk"]
        cfg["hotkey"]["label"] = self.choices["hotkey_label"]
        cfg["hotkey"]["name"] = self.choices["hotkey_label"]
        cfg["ui"]["style"] = self.choices["ui_style"]

        if self.bench_proc and self.bench_proc.state() != QProcess.ProcessState.NotRunning:
            self.bench_proc.kill()

        if not guya_config.save_config(cfg):
            return
        launcher_gen.create_launcher()   # double-click launcher

        # Cloud or already-cached → done immediately.
        if opt["backend"] == "cloud" or model_is_cached(opt["model_size"]):
            self._complete()
            return

        # Offline + not cached → show the download page with progress.
        self.stack.setCurrentIndex(5)
        self._sync_step()
        self._update_nav()
        self._start_download(opt["model_size"])

    def _start_download(self, size):
        self.dl_title.setText(f"Downloading the “{size}” model…")
        self.dl_status.setText("This happens once. Please keep this window open.")
        self.dl_expected = MODEL_SIZE_MB.get(size, 1000)
        self.dl_size = size
        self.dl_bar.setValue(0)

        self.dl_proc = QProcess(self)
        self.dl_proc.finished.connect(self._on_download_done)
        self.dl_proc.setProgram(sys.executable)
        self.dl_proc.setArguments([
            "-c",
            f"from faster_whisper.utils import download_model; download_model('{size}')"])
        self.dl_proc.start()

        self.dl_timer = QTimer(self)
        self.dl_timer.timeout.connect(self._poll_download)
        self.dl_timer.start(500)

    def _poll_download(self):
        mb = model_downloaded_mb(self.dl_size)
        pct = int(min(99, (mb / self.dl_expected) * 100)) if self.dl_expected else 0
        self.dl_bar.setValue(pct)
        self.dl_status.setText(f"{mb:.0f} MB of ~{self.dl_expected:.0f} MB")

    def _on_download_done(self, exit_code, _status):
        if self.dl_timer:
            self.dl_timer.stop()
        self.dl_bar.setValue(100)
        self.dl_status.setText("Done.")
        self._complete()

    def _complete(self):
        self.completed = True
        log.info("Setup complete; config saved.")
        self.close()


# Hotkey capture (Windows). Defined after Qt imports so the class resolves.
class HotkeyCapture(QPushButton):
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
            label = (e.text().upper().strip() or e.text().strip() or str(vk))
            self._capturing = False
            self.releaseKeyboard()
            self.setText(f"Key:  {label}")
            self.captured.emit(vk, label)
        else:
            super().keyPressEvent(e)
