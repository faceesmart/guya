# Guya (گویا)

**Device-aware Persian & English speech-to-text for accessibility.**

Guya is a push-to-talk speech-to-text tool: hold a key, speak in Persian or
English, release — the text is typed into whatever app you're using. It is
aimed at users for whom typing is difficult.

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
- [ ] **M2** — Setup wizard (analyze device → choose model → configure)
- [ ] **M3** — Benchmark-based model recommendation
- [ ] **M4** — Cloud fallback engine

## Install

**Windows** (primary target — GPU acceleration via CUDA):
```bat
install.bat
run.bat
```

**macOS / Linux** (development):
```bash
./install.sh
./run.sh
```

First run launches the setup wizard. After that, `run` starts the widget directly.

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

## Project layout

```
guya/
├── guya/                  # the package
│   ├── __main__.py        # entry point (wizard vs widget)
│   ├── config.py          # config schema + load/save
│   ├── widget.py          # the floating push-to-talk widget
│   ├── platform_macos.py  # macOS hotkey / paste / permissions adapter
│   └── wizard.py          # setup wizard (M2)
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
