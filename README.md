# Guya (گویا)

**Persian & English push-to-talk dictation and a small, safe desktop assistant, for people who find typing hard. Runs on your own computer, for free.**

Hold a key, speak in Persian or English, release: the words are typed into
whatever application you are using. Hold a second key and speak a command:
Guya creates, finds, opens or renames files, opens applications, saves or
closes the current window, opens a website or scrolls the page. It understands
many phrasings of each command in both languages, asks before doing anything
that changes a file, and never deletes.

On first run a setup wizard measures your computer, recommends a speech model
that will keep up with your voice on that machine, and creates a launcher you
double-click every day. Weak computers can use a free online model instead.

> Final-year Computer Engineering project, University of Tehran (Farabi Campus).
> Built on [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (OpenAI Whisper).
> Full report: [`docs/REPORT.md`](docs/REPORT.md) (English) · [`docs/REPORT-FA.md`](docs/REPORT-FA.md) (فارسی); as files: `docs/Guya-Report-EN.pdf`, `docs/Guya-Report-FA.pdf`, `docs/Guya-Report-EN.docx`, `docs/Guya-Report-FA.docx`. Proposal: [`docs/PROPOSAL.md`](docs/PROPOSAL.md).

![Control panel](docs/img/panel-controls.png)

## Status

| Part | State |
|---|---|
| Dictation (fa / en / both), offline, online and dual modes | done |
| Assistant: create, find, open, rename (with confirmation), save, close, websites, web search, browser navigation | done |
| Setup wizard with device benchmark, control panel, help, logs | done |
| Automated tests | 136, all passing, no microphone or model needed |
| Speech accuracy and speed measurements (Persian + English, six model sizes) | done, see [`eval/results/`](eval/results/) |
| Held-out command-parser evaluation | done, 100% intent accuracy on 221 unseen phrasings (69% before this work) |
| macOS | tested daily |
| Windows | tested on the family's laptop (ASUS ROG G513RM, Ryzen 7 6800H, RTX 3060): installer, wizard, dictation and assistant work as on macOS |
| User study with the target user | done: 12 of 12 tasks completed, SUS 82.5 (`docs/REPORT.md` §7.9, `eval/results/user_study/`) |
| Demonstration | given live from the script in `docs/DEMO.md` (about six minutes) |

## Install (easiest — no typing)

Double-click the installer for your system:

- **macOS:** `Install Guya.command` *(first time: right-click → Open)*
- **Windows:** `Install Guya.bat`

It checks for Python (and helps you install it if missing), sets everything up,
and opens the setup wizard. After setup it creates a **Guya** launcher you
double-click to run daily.

<details>
<summary>Manual install (developers)</summary>

```bash
./install.sh            # macOS / Linux   (Windows: install.bat)
./run.sh                # start Guya      (Windows: run.bat)
./venv/bin/python -m unittest discover -s tests -t .   # run the tests
```
</details>

## The two keys

| | macOS | Windows |
|---|---|---|
| Dictation | hold **Right Option (⌥)** | hold **G** (changeable) |
| Assistant | hold **Right Command (⌘)** | hold **F8** (changeable) |

The language badge on the floating pill (FA / EN / DUAL) decides how speech is
recognised. The control panel's **Help** tab lists the commands in both languages.

### Example commands

| English | فارسی |
|---|---|
| Create a Word file named report | یه فایل ورد به اسم گزارش بساز |
| Find my project folder | پوشه پروژه رو پیدا کن |
| Open test six docs → opens `test6.docx` | فایل تست شش ورد رو باز کن |
| Open it again | دوباره بازش کن |
| Rename it to final report → Guya asks yes/no | اسمش رو بذار گزارش نهایی |
| Save it · Close it | ذخیره کن · پنجره رو ببند |
| Open Chrome, then search for YouTube | کروم رو باز کن بعد یوتیوب رو جستجو کن |
| Go to YouTube · Visit github.com | برو به سایت یوتیوب |
| Scroll down · Go back · Go to the top | یه کم برو پایین · برگرد · برو اول صفحه |
| Switch to Persian · Switch to dual | برو انگلیسی · دو زبانه |

After creating something Guya asks whether to open it; answer by voice or click
Yes / No in the bubble. If several files match a spoken name, up to three
choices appear; click one or say *first / second / third / cancel*. A new command can be spoken at any time; it replaces the
question. English replies are spoken and shown; Persian replies are shown on
the pill and in a bubble (macOS has no Persian voice, and an Arabic accent
was judged worse than silence). Press the assistant key while Guya is speaking
to interrupt it.

## What Guya will not do

For safety the assistant only works inside Desktop, Documents and Downloads. It
does not delete files, overwrite files, run commands, click web results, read
web pages, download anything, or automate application-specific dialogs such as
Save As. Websites open only over HTTPS and only by known name or a spoken
domain. Browser commands need the browser to be the active application.

## How it works

```
Install → wizard (profile + benchmark → model → config) → Guya.app / Start Guya
Guya.app → control panel → dictation widget (hotkeys, microphone, Whisper, assistant)
```

- **Config:** `~/.guya/config.json` — model, device, language, keys, allowed folders.
- **Logs:** `~/.guya/logs/guya.log` — every assistant command is one JSON record.
- **Models:** `~/.cache/huggingface` (downloaded once).
- **Architecture, design decisions and results:** [`docs/REPORT.md`](docs/REPORT.md), in Persian [`docs/REPORT-FA.md`](docs/REPORT-FA.md).
- **Scope and definition of done:** [`docs/V1_SCOPE_AND_ROADMAP.md`](docs/V1_SCOPE_AND_ROADMAP.md).
- **Spoken test checklist:** [`docs/ASSISTANT_EVALUATION.md`](docs/ASSISTANT_EVALUATION.md).
- **Evaluation scripts and how to reproduce every number:** [`eval/README.md`](eval/README.md).
- **Building the report files:** `docs/tools/build_report_html.py` (web page), `build_report_pdf.py` (PDF through Chrome in the Farabi Campus report layout: title and بسم‌الله pages, chapters opening on odd pages, running headers, mirrored margins, B Nazanin / B Titr / Times New Roman type; `pip install markdown playwright pypdf`, `cd docs/tools && npm install`, and the B Nazanin and B Titr `.ttf` files copied into `docs/tools/assets/fonts/`, which is not committed because those fonts are proprietary) and `build_report_docx.js` (Word). The Word files carry a table-of-contents field: answer *Yes* when Word asks to update fields on opening.

## Project layout

```
guya/
├── guya/                    # the package
│   ├── __main__.py          # entry point: wizard → control panel → widget
│   ├── config.py            # config schema + load/save
│   ├── widget.py            # floating push-to-talk widget (recorder, hotkeys, pill, bubble)
│   ├── stt.py               # the speech-to-text pipeline (shared with eval/)
│   ├── control_panel.py     # daily launcher window
│   ├── wizard.py            # first-run setup wizard
│   ├── benchmark.py         # device benchmark + model recommendation
│   ├── platform_macos.py    # hotkeys, paste, permissions (macOS)
│   └── assistant/           # bilingual parser, context, safe actions (macOS / Windows)
├── eval/                    # accuracy, ablation, intent and log evaluators + results
├── tests/                   # 136 unit tests
└── docs/                    # report, proposal, scope, checklists, screenshots
```

## Reconfigure

```bash
python -m guya --setup    # re-run the wizard
python -m guya --reset    # wipe config and start fresh
```
