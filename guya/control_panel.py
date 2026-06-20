"""
Guya Control Panel — the app you double-click to manage Guya.

Opening it turns Guya ON (starts the dictation widget as a child process) and
shows one window to:
  * turn Guya on / off
  * see + change settings (mode, model, online API key, language, key)
  * re-run setup, update, open logs, uninstall

The dictation widget runs as a separate process (`python -m guya --widget`), so
model loading stays isolated from this window's Qt — and Accessibility is granted
once to Guya itself.
"""

import os
import sys

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QApplication, QScrollArea, QMessageBox, QDialog, QPlainTextEdit,
)
from PyQt6.QtCore import Qt, QProcess, QTimer
from PyQt6.QtGui import QFont

from . import config as guya_config
from . import wizard as wz
from .wizard import (
    BG, BG2, CARD, BORDER, ACCENT, ACCENT2, ACCENT_TEXT, GREEN, RED,
    TEXT, TEXT2, DIM, UI_FONT, _grad, _shadow,
)

import logging
log = logging.getLogger("Guya")


def _project_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# Human-readable summary of the current config.
def _summary():
    c = guya_config.load_config()
    backend = c.get("model", {}).get("backend", "faster-whisper")
    cloud_on = c.get("cloud", {}).get("enabled", False)
    if backend == "cloud":
        mode = "online"
    elif cloud_on:
        mode = "dual"
    else:
        mode = "offline"
    lang = c.get("language", "en")
    return {
        "mode": mode,
        "model": c.get("model", {}).get("size", "—"),
        "api": bool(c.get("cloud", {}).get("api_key")),
        "language": {"en": "English", "fa": "Persian", "dual": "Persian + English"}.get(lang, lang),
        "key": c.get("hotkey", {}).get("label", "—"),
    }


class ControlPanel(QWidget):
    def __init__(self):
        super().__init__()
        self.widget_proc = None
        self.setWindowTitle("Guya")
        self.resize(560, 760)
        self.setMinimumSize(480, 620)
        self.setStyleSheet(
            f"ControlPanel {{ background: {_grad(BG, BG2)}; }}"
            f"QWidget {{ color: {TEXT}; }}")
        self._build()
        # "Turn on + open panel": start the widget right away.
        QTimer.singleShot(150, self.start_widget)

    # ---------- UI ----------

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(26, 22, 26, 22)
        root.setSpacing(16)

        # Title
        title = QLabel("گویا  ·  Guya")
        title.setFont(QFont(UI_FONT, 20, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {TEXT};")
        root.addWidget(title)

        # Status + on/off
        sbox = QFrame()
        sbox.setStyleSheet(f"QFrame {{ background: {_grad('#1a1e24', '#15181d')};"
                           f"border: 1px solid {BORDER}; border-radius: 18px; }}"
                           f"QLabel {{ border: none; background: transparent; }}")
        _shadow(sbox, blur=22, dy=6, alpha=110)
        sl = QHBoxLayout(sbox); sl.setContentsMargins(20, 16, 20, 16); sl.setSpacing(12)
        self.dot = QLabel("●"); self.dot.setFont(QFont(UI_FONT, 16))
        sl.addWidget(self.dot)
        self.status_lbl = QLabel("…"); self.status_lbl.setFont(QFont(UI_FONT, 14, QFont.Weight.DemiBold))
        sl.addWidget(self.status_lbl); sl.addStretch()
        self.toggle_btn = self._btn("Stop", "danger"); self.toggle_btn.setMinimumWidth(120)
        self.toggle_btn.clicked.connect(self._toggle_widget)
        sl.addWidget(self.toggle_btn)
        root.addWidget(sbox)

        # Settings
        head = QLabel("Settings"); head.setFont(QFont(UI_FONT, 12, QFont.Weight.DemiBold))
        head.setStyleSheet(f"color: {TEXT2};")
        root.addWidget(head)

        area = QScrollArea(); area.setWidgetResizable(True); area.setFrameShape(QFrame.Shape.NoFrame)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        area.setStyleSheet("QScrollArea{background:transparent;border:none;}"
                           "QScrollBar:vertical{background:transparent;width:8px;}"
                           f"QScrollBar::handle:vertical{{background:{BORDER};border-radius:4px;}}"
                           "QScrollBar::add-line,QScrollBar::sub-line{height:0;}")
        inner = QWidget(); inner.setStyleSheet("background:transparent;")
        self.settings_col = QVBoxLayout(inner)
        self.settings_col.setContentsMargins(0, 0, 8, 0); self.settings_col.setSpacing(10)
        area.setWidget(inner)
        root.addWidget(area, 1)
        self._fill_settings()

        # Maintenance
        mhead = QLabel("Maintenance"); mhead.setFont(QFont(UI_FONT, 12, QFont.Weight.DemiBold))
        mhead.setStyleSheet(f"color: {TEXT2};")
        root.addWidget(mhead)
        m1 = QHBoxLayout(); m1.setSpacing(10)
        b_setup = self._btn("Re-run Setup", "ghost"); b_setup.clicked.connect(self._change_settings)
        b_update = self._btn("Update", "ghost"); b_update.clicked.connect(self._update)
        m1.addWidget(b_setup); m1.addWidget(b_update)
        root.addLayout(m1)
        m2 = QHBoxLayout(); m2.setSpacing(10)
        b_logs = self._btn("Open Logs", "ghost"); b_logs.clicked.connect(self._open_logs)
        b_uninstall = self._btn("Uninstall", "ghost"); b_uninstall.clicked.connect(self._uninstall)
        m2.addWidget(b_logs); m2.addWidget(b_uninstall)
        root.addLayout(m2)

    def _btn(self, text, kind="primary"):
        b = QPushButton(text); b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setMinimumHeight(44); b.setFont(QFont(UI_FONT, 12, QFont.Weight.DemiBold))
        if kind == "primary":
            b.setStyleSheet(
                f"QPushButton {{ background: {_grad('#3ee0cb', ACCENT2)}; color: {ACCENT_TEXT};"
                f"border: none; border-radius: 13px; padding: 0 22px; font-weight: 700; }}"
                f"QPushButton:hover {{ background: {_grad('#4fe9d5', '#10a89a')}; }}")
            _shadow(b, blur=18, dy=4, alpha=100)
        elif kind == "danger":
            b.setStyleSheet(
                f"QPushButton {{ background: {_grad('#fb7185', '#e11d48')}; color: #fff;"
                f"border: none; border-radius: 13px; padding: 0 22px; font-weight: 700; }}"
                f"QPushButton:hover {{ background: {_grad('#fda4b0', '#be123c')}; }}")
            _shadow(b, blur=18, dy=4, alpha=100)
        else:  # ghost
            b.setStyleSheet(
                f"QPushButton {{ background: rgba(255,255,255,0.04); color: {TEXT};"
                f"border: 1px solid {BORDER}; border-radius: 13px; padding: 0 18px; }}"
                f"QPushButton:hover {{ border-color: {ACCENT}; color: {TEXT};"
                f"background: rgba(45,212,191,0.08); }}")
        return b

    def _fill_settings(self):
        while self.settings_col.count():
            it = self.settings_col.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        s = _summary()
        modes = {"offline": "💻  Offline", "online": "☁️  Online", "dual": "🔀  Dual (offline + online)"}
        rows = [
            ("🧩", "How it runs", modes.get(s["mode"], s["mode"])),
            ("🧠", "Model", s["model"]),
            ("☁️", "Online API key", "Set ✓" if s["api"] else "Not set"),
            ("🌐", "Language", s["language"]),
            ("⌨️", "Push-to-talk key", s["key"]),
        ]
        for icon, label, value in rows:
            self.settings_col.addWidget(self._setting_row(icon, label, value))
        self.settings_col.addStretch()

    def _setting_row(self, icon, label, value):
        f = QFrame()
        f.setStyleSheet(f"QFrame {{ background: {_grad('#1a1a23', '#15151d')};"
                        f"border: 1px solid {BORDER}; border-radius: 16px; }}"
                        f"QLabel {{ border: none; background: transparent; }}")
        _shadow(f, blur=16, dy=4, alpha=70)
        h = QHBoxLayout(f); h.setContentsMargins(18, 13, 18, 13); h.setSpacing(12)
        ic = QLabel(icon); ic.setFont(QFont(UI_FONT, 16)); ic.setFixedWidth(30); h.addWidget(ic)
        tx = QVBoxLayout(); tx.setSpacing(2)
        lb = QLabel(label); lb.setFont(QFont(UI_FONT, 10)); lb.setStyleSheet(f"color: {TEXT2};")
        vl = QLabel(str(value)); vl.setFont(QFont(UI_FONT, 13, QFont.Weight.DemiBold))
        vl.setStyleSheet(f"color: {TEXT};"); vl.setWordWrap(True)
        tx.addWidget(lb); tx.addWidget(vl); h.addLayout(tx, 1)
        cb = QPushButton("Change"); cb.setCursor(Qt.CursorShape.PointingHandCursor)
        cb.setMinimumSize(92, 36); cb.setFont(QFont(UI_FONT, 10, QFont.Weight.DemiBold))
        cb.setStyleSheet(f"QPushButton {{ background: rgba(45,212,191,0.12); color: {ACCENT};"
                         f"border: 1px solid {ACCENT}; border-radius: 11px; padding: 0 14px; }}"
                         f"QPushButton:hover {{ background: rgba(45,212,191,0.22); }}")
        cb.clicked.connect(self._change_settings)
        h.addWidget(cb)
        return f

    # ---------- widget on/off ----------

    def start_widget(self):
        if self.widget_proc and self.widget_proc.state() != QProcess.ProcessState.NotRunning:
            self._refresh_status(); return
        self.widget_proc = QProcess(self)
        self.widget_proc.setProgram(sys.executable)
        self.widget_proc.setArguments(["-m", "guya", "--widget"])
        self.widget_proc.setWorkingDirectory(_project_root())
        self.widget_proc.finished.connect(self._refresh_status)
        self.widget_proc.started.connect(self._refresh_status)
        self.widget_proc.start()
        self.status_lbl.setText("Starting…")
        self.dot.setStyleSheet(f"color: {ACCENT};")
        QTimer.singleShot(1500, self._refresh_status)

    def stop_widget(self):
        if self.widget_proc and self.widget_proc.state() != QProcess.ProcessState.NotRunning:
            self.widget_proc.terminate()
            if not self.widget_proc.waitForFinished(2000):
                self.widget_proc.kill()
        self._refresh_status()

    def _toggle_widget(self):
        if self._running():
            self.stop_widget()
        else:
            self.start_widget()

    def _running(self):
        return bool(self.widget_proc and
                    self.widget_proc.state() != QProcess.ProcessState.NotRunning)

    def _refresh_status(self, *_):
        if self._running():
            self.dot.setStyleSheet(f"color: {GREEN};")
            self.status_lbl.setText("Guya is running")
            self.toggle_btn.setText("Stop")
            self.toggle_btn.setStyleSheet(self._btn("Stop", "danger").styleSheet())
        else:
            self.dot.setStyleSheet(f"color: {DIM};")
            self.status_lbl.setText("Guya is off")
            self.toggle_btn.setText("Start")
            self.toggle_btn.setStyleSheet(self._btn("Start", "primary").styleSheet())

    # ---------- settings / maintenance ----------

    def _change_settings(self):
        """Open the setup wizard in a child process; on exit, reload + restart."""
        was_running = self._running()
        self.stop_widget()
        self.setup_proc = QProcess(self)
        self.setup_proc.setProgram(sys.executable)
        self.setup_proc.setArguments(["-m", "guya", "--setup-only"])
        self.setup_proc.setWorkingDirectory(_project_root())
        self.setup_proc.finished.connect(lambda *_: self._after_settings(was_running))
        self.setup_proc.start()
        self.hide()

    def _after_settings(self, was_running):
        self.show(); self.raise_(); self.activateWindow()
        self._fill_settings()
        if was_running:
            self.start_widget()
        else:
            self._refresh_status()

    def _update(self):
        root = _project_root()
        pip = os.path.join(root, "venv",
                           "Scripts" if sys.platform == "win32" else "bin",
                           "pip")
        cmd = (f'cd "{root}" && git pull && "{pip}" install -r requirements.txt')
        self._run_console("Updating Guya…", ["bash", "-lc", cmd] if sys.platform != "win32"
                          else ["cmd", "/c", cmd.replace(" && ", " & ")])

    def _open_logs(self):
        logdir = os.path.join(os.path.expanduser("~"), ".guya", "logs")
        os.makedirs(logdir, exist_ok=True)
        if sys.platform == "darwin":
            QProcess.startDetached("open", [logdir])
        elif sys.platform == "win32":
            QProcess.startDetached("explorer", [logdir])
        else:
            QProcess.startDetached("xdg-open", [logdir])

    def _uninstall(self):
        box = QMessageBox(self)
        box.setWindowTitle("Uninstall Guya")
        box.setText("Remove Guya's settings, downloaded models, and launchers?")
        box.setInformativeText("Your project folder is kept. This frees up disk space "
                               "and resets Guya. You can set it up again anytime.")
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
                if os.path.isdir(t):
                    shutil.rmtree(t, ignore_errors=True)
                elif os.path.exists(t):
                    os.remove(t)
            except Exception as e:
                log.warning(f"uninstall: could not remove {t}: {e}")
        QMessageBox.information(self, "Guya", "Guya has been removed. Goodbye! 👋")
        QApplication.quit()

    def _run_console(self, title, argv):
        dlg = QDialog(self); dlg.setWindowTitle(title); dlg.resize(640, 420)
        dlg.setStyleSheet(f"background: {BG};")
        v = QVBoxLayout(dlg)
        out = QPlainTextEdit(); out.setReadOnly(True)
        out.setStyleSheet(f"background: #0a0d10; color: {TEXT}; border: 1px solid {BORDER};"
                          f"border-radius: 10px; font-family: monospace; font-size: 11px;")
        v.addWidget(QLabel(title)); v.addWidget(out)
        proc = QProcess(dlg)
        proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        proc.readyRead.connect(
            lambda: out.appendPlainText(bytes(proc.readAll()).decode("utf-8", "replace").rstrip()))
        proc.finished.connect(lambda *_: out.appendPlainText("\n✓ Done. You can close this window."))
        proc.setProgram(argv[0]); proc.setArguments(argv[1:]); proc.start()
        dlg.exec()

    def closeEvent(self, e):
        self.stop_widget()
        e.accept()
        QApplication.quit()


def run():
    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyle("Fusion")
    wz._load_fonts()
    app.setFont(QFont(UI_FONT, 11))
    app.setQuitOnLastWindowClosed(True)
    panel = ControlPanel()
    panel.show(); panel.raise_(); panel.activateWindow()
    app.exec()
