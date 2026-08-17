# Guya (گویا)

**Device-aware Persian & English speech-to-text and simple computer assistance
for accessibility.**

Guya is a push-to-talk speech-to-text tool: hold a key, speak in Persian or
English, release — the text is typed into whatever app you're using. It is
aimed at users for whom typing is difficult.

Guya also includes a limited local voice assistant for common desktop tasks:
creating Word/text files and folders, opening applications/files/folders,
finding items, renaming them with confirmation, saving or closing the current
window, and running limited safe browser navigation. The assistant is
rule-based, works in Persian and English, and does not require a paid AI API.

On first run, Guya **analyzes your computer** and lets you choose how to run:
a large accurate offline model (if your machine can handle it), a lighter/faster
offline model, or an online cloud model (for weak machines). It then walks you
through picking a push-to-talk key and language, and creates a launcher you
double-click to start.

> Final-year Computer Engineering capstone, University of Tehran.
> Built on [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (OpenAI Whisper).

---

## Status

Early development. Milestones:

- [x] **M1** — Config-driven widget (reads `~/.guya/config.json`)
- [x] **M2** — Setup wizard (analyze device → choose model → configure)
- [x] **M3** — Benchmark-based model recommendation
- [x] **M4** — Cloud fallback engine (free online option via Groq)
- [x] **M5** — Bilingual local assistant MVP with safe desktop actions
- [x] **M6** — Spoken filename normalization and accessible result selection
- [ ] **M7** — Cross-platform/user evaluation and final report

## Install (easiest — no typing)

Just **double-click the installer** for your system:

- **Windows:** `Install Guya.bat`
- **macOS:** `Install Guya.command`  *(first time: right-click → Open)*

It checks for Python (and helps you install it if missing — automatically on
Windows via winget, or with a simple guide), sets everything up, and opens the
setup wizard. No commands to type.

After setup it creates a **Start Guya** launcher you double-click to run daily.

<details>
<summary>Manual install (advanced)</summary>

```bash
# Windows
install.bat
# macOS / Linux
./install.sh
```
Then `python -m guya` (or `run.bat` / `./run.sh`).
</details>

## How it works

```
python -m guya
   │
   ├─ no ~/.guya/config.json  → run setup wizard → save config → launch widget
   └─ config present          → launch widget with saved settings
```

- **Config**: `~/.guya/config.json` — model, device, language, push-to-talk key, UI.
- **Logs**: `~/.guya/logs/guya.log`.
- **Model cache**: `~/.cache/huggingface` (shared, downloaded once).

## Dictation and assistant keys

- **macOS:** hold Right Option (⌥) for dictation; hold Right Command (⌘) for
  assistant commands.
- **Windows:** hold the configured dictation key (G by default); hold the
  assistant key (F8 by default). Both can be changed in Settings.

Assistant recognition follows the language badge: choose FA, EN, or DUAL before
speaking. Examples:

- `Create a Word file named Guya`
- `Find my project folder`
- `Open test six docs` → can match `test6.docx`
- `Find and open the report file`
- `Rename it to final report` → Guya asks for confirmation
- `Save the current file`
- `Open Chrome, then search for YouTube`
- `Scroll down` / `Page down` / `Go back` / `Go forward`
- `Go to YouTube` / `Visit github.com`

After creating an item, Guya asks whether to open it. Similar filename results
can be selected by clicking or by saying first, second, third, or cancel. While
English feedback is speaking, press the assistant key again to interrupt it and
continue. The control panel's **Help** tab contains a bilingual quick guide.
- `برام یه فایل ورد به اسم گویا بساز`
- `پوشه پروژه رو پیدا کن`
- `فایل تست شش رو پیدا کن و باز کن`
- `اسمش رو عوض کن` → گویا نام جدید و سپس تأیید را می‌پرسد
- `فایل فعلی رو ذخیره کن و پنجره فعلی رو ببند`
- `صفحه رو پایین ببر` / `برو عقب` / `برو جلو`
- `برو به سایت یوتیوب`

For safety, the MVP only works inside Desktop, Documents, and Downloads. It
does not delete files, overwrite existing items, run arbitrary commands, click
unknown web results, read arbitrary web pages, download files, or automate
application-specific Save As dialogs. Scroll/back/forward commands require the
browser to be the active application. Website opening accepts known names or a
complete domain, always uses HTTPS, and reuses the active tab so browser history
continues to work.

The final-year-project feature boundary and remaining work are documented in
[`docs/V1_SCOPE_AND_ROADMAP.md`](docs/V1_SCOPE_AND_ROADMAP.md).

## Project layout

```
guya/
├── guya/                  # the package
│   ├── __main__.py        # entry point (wizard vs widget)
│   ├── config.py          # config schema + load/save
│   ├── widget.py          # the floating push-to-talk widget
│   ├── platform_macos.py  # macOS hotkey / paste / permissions adapter
│   ├── assistant/         # bilingual parser + safe OS/file actions
│   └── wizard.py          # setup wizard (M2)
├── tests/                 # parser, context, and file-safety tests
├── docs/                  # capstone material (proposal, evaluation)
├── requirements.txt
├── install.sh / install.bat
└── run.sh / run.bat
```

## Reconfigure

```bash
python -m guya --setup    # re-run the wizard
python -m guya --reset    # wipe config and start fresh
```
