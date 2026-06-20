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
)
from PyQt6.QtCore import Qt, QProcess, QTimer, pyqtSignal, QRectF
from PyQt6.QtGui import QFont, QColor, QPainter, QPen

from . import config as guya_config
from . import profiler
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
        self._load_state()
        self.setWindowTitle("Guya")
        self.resize(540, 780)
        self.setMinimumSize(460, 660)
        self.setStyleSheet(
            f"ControlPanel {{ background: {_grad(BG, BG2)}; }}"
            f"QWidget {{ color: {TEXT}; }}")
        self._build()
        # live sync with the actual widget process
        self._sync = QTimer(self); self._sync.timeout.connect(self._tick); self._sync.start(1000)
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
            c["language"] = "en"     # offline does English; online handles the rest
        else:  # offline
            c["model"]["backend"] = "faster-whisper"; c["model"]["size"] = self.model_size
            c["model"]["device"] = self.device; c["model"]["compute_type"] = "auto"
            c["cloud"]["enabled"] = False
            c["language"] = self.lang
        c["hotkey"]["vk"] = self.vk; c["hotkey"]["name"] = self.label
        c["hotkey"]["label"] = self.label
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
        root.setContentsMargins(26, 22, 26, 20)
        root.setSpacing(12)

        title = QLabel("گویا  ·  Guya")
        title.setFont(QFont(UI_FONT, 17, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {TEXT2};")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(title)

        # Power button + status + uptime
        self.power = PowerButton(132)
        self.power.clicked.connect(self._toggle_widget)
        prow = QHBoxLayout(); prow.addStretch(); prow.addWidget(self.power); prow.addStretch()
        root.addSpacing(6); root.addLayout(prow)

        self.status_lbl = QLabel("…"); self.status_lbl.setFont(QFont(UI_FONT, 15, QFont.Weight.Bold))
        self.status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.status_lbl)
        self.uptime_lbl = QLabel(""); self.uptime_lbl.setFont(QFont(UI_FONT, 22, QFont.Weight.DemiBold))
        self.uptime_lbl.setStyleSheet(f"color: {ACCENT};")
        self.uptime_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.uptime_lbl)
        root.addSpacing(6)

        # Settings
        head = QLabel("SETTINGS"); head.setFont(QFont(UI_FONT, 10, QFont.Weight.Bold))
        head.setStyleSheet(f"color: {DIM}; letter-spacing: 1px;")
        root.addWidget(head)
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
        root.addWidget(area, 1)
        self._fill_settings()

        # Maintenance
        mhead = QLabel("MAINTENANCE"); mhead.setFont(QFont(UI_FONT, 10, QFont.Weight.Bold))
        mhead.setStyleSheet(f"color: {DIM}; letter-spacing: 1px;")
        root.addWidget(mhead)
        m1 = QHBoxLayout(); m1.setSpacing(9)
        for txt, fn in (("Re-run Setup", self._rerun_setup), ("Update", self._update)):
            b = self._ghost(txt); b.clicked.connect(fn); m1.addWidget(b)
        root.addLayout(m1)
        m2 = QHBoxLayout(); m2.setSpacing(9)
        for txt, fn in (("Open Logs", self._open_logs), ("Uninstall", self._uninstall)):
            b = self._ghost(txt); b.clicked.connect(fn); m2.addWidget(b)
        root.addLayout(m2)

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
        disp_lang = "Persian + English" if self.mode == "dual" else LANG_NAME.get(self.lang, self.lang)
        rows.append(("🌐", "Language", disp_lang, None if self.mode == "dual" else self._open_lang_modal))
        rows.append(("⌨️", "Push-to-talk key", "Right Option (⌥)" if IS_MAC else self.label,
                     None if IS_MAC else self._open_key_modal))
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
        dlg = PickerDialog(self, "Push-to-talk key", build); dlg.resize(480, 240)
        if dlg.exec() and dlg.value:
            self.vk, self.label = dlg.value; self._apply()

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
        root = _project_root()
        pip = os.path.join(root, "venv", "Scripts" if sys.platform == "win32" else "bin", "pip")
        if sys.platform == "win32":
            argv = ["cmd", "/c", f'cd /d "{root}" & git pull & "{pip}" install -r requirements.txt']
        else:
            argv = ["bash", "-lc", f'cd "{root}" && git pull && "{pip}" install -r requirements.txt']
        self._run_console("Updating Guya…", argv)

    def _open_logs(self):
        logdir = os.path.join(os.path.expanduser("~"), ".guya", "logs")
        os.makedirs(logdir, exist_ok=True)
        opener = "open" if sys.platform == "darwin" else ("explorer" if sys.platform == "win32" else "xdg-open")
        QProcess.startDetached(opener, [logdir])

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
        root = _project_root()
        targets = [os.path.join(os.path.expanduser("~"), ".guya"),
                   os.path.join(root, "Guya.app"),
                   os.path.join(root, "Start Guya.command"),
                   os.path.join(root, "Start Guya.vbs")]
        targets += glob.glob(os.path.join(os.path.expanduser("~"), ".cache", "huggingface",
                                          "hub", "models--*faster-whisper*"))
        for t in targets:
            try:
                shutil.rmtree(t, ignore_errors=True) if os.path.isdir(t) else (
                    os.remove(t) if os.path.exists(t) else None)
            except Exception as e:
                log.warning(f"uninstall: {t}: {e}")
        QMessageBox.information(self, "Guya", "Guya has been removed. Goodbye! 👋")
        QApplication.quit()

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
    app.setStyle("Fusion")
    wz._load_fonts()
    app.setFont(QFont(UI_FONT, 11))
    app.setQuitOnLastWindowClosed(True)
    panel = ControlPanel()
    panel.show(); panel.raise_(); panel.activateWindow()
    app.exec()
