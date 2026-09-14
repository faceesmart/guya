# Guya - Persian-English Voice Dictation and Limited Desktop Assistance for Accessibility

**B.Sc. Final-Year Project Proposal - Computer Engineering**

| | |
|---|---|
| **Student** | MohammadReza Ganji |
| **Student ID** | 220701091 |
| **Institution** | University of Tehran, Farabi Campus, Faculty of Engineering |
| **Supervisor** | Dr. Hossein Aghababa |
| **Project term** | Eighth semester (second semester of the fourth year) |
| **Credits completed** | 133 |
| **Date** | July 2026 |

## 1. Overview

Guya is an accessibility-focused desktop application for people with physical
or motor disabilities who can speak but find sustained typing and some routine
computer actions difficult. It combines two independent push-to-talk modes:

1. Persian and English Voice-to-Text that writes into the active application.
2. A limited Persian and English Voice Assistant for a defined set of safe
   desktop actions.

The two modes use separate hotkeys so that dictation cannot be mistaken for a
computer command. Guya is a university MVP and is not intended to be a general
AI assistant or a production-ready commercial accessibility product.

## 2. Problem and motivation

For users with physical or motor disabilities, long-form typing and repeated
keyboard or mouse operations can be a daily barrier. Existing tools may provide
dictation, but Persian support, accessible setup, device requirements and simple
voice-driven desktop actions are not handled consistently in one application.

Guya is motivated by a real target user: the student's brother can speak but
finds long typing difficult. The project therefore focuses on reducing sustained
typing and a small number of repetitive desktop interactions rather than adding
open-ended automation.

## 3. Objectives

1. Provide reliable Persian and English push-to-talk dictation in the active
   application.
2. Provide a separate bilingual assistant for limited actions such as creating,
   finding, opening and renaming files or folders; opening applications; saving
   or closing the active window; and performing a safe web search.
3. Keep actions predictable through rule-based command detection, confirmation
   for renaming, visible choices for ambiguous results and restricted filesystem
   access.
4. Support offline, online and dual recognition modes, with device profiling and
   a model recommendation during setup.
5. Evaluate recognition quality, response time, command-task success, safety and
   usability with representative users, including a target user.

## 4. Proposed system

Guya is implemented in Python with a Qt desktop interface and Whisper-based
speech recognition. Its main components are:

- **Interaction layer:** separate dictation and assistant hotkeys, microphone
  capture, a floating state widget and spoken/visual feedback.
- **Speech-recognition layer:** Persian and English transcription using offline,
  online or dual modes selected according to the device and user preference.
- **Command-understanding layer:** bilingual normalization and a deterministic,
  rule-based parser for the supported command set.
- **Safety and action layer:** platform-specific actions, confirmation and
  disambiguation, remembered recent-file context, non-overwriting rename and
  filesystem access limited to configured user folders.
- **Accessible control layer:** setup wizard, control panel, help, permissions
  guidance and readable diagnostic logs.

## 5. Scope of the MVP

### Included

- Persian and English dictation with a dedicated hotkey.
- A separate assistant hotkey and a limited bilingual command set.
- Creation, search, opening and safe renaming of files and folders.
- Opening supported applications; saving or closing the active window.
- A limited sequence that opens a browser and performs a web search.
- Clickable or spoken selection when several file results match.
- Offline, online and dual recognition modes with device profiling.
- macOS and Windows launch/install paths, with validation on the selected demo
  machines.
- Automated tests, structured spoken evaluation and target-user feedback.

### Excluded

- General Gemini/ChatGPT-style conversation or reasoning.
- Arbitrary shell commands or unrestricted computer control.
- File deletion, silent overwrite or bypassing confirmation.
- Automatic clicking of unknown websites or arbitrary browser automation.
- Wake-word/background listening or support for every application and accent.
- App-store distribution or commercial production readiness.

## 6. Evaluation plan

- **Dictation:** representative Persian and English sentences, transcription
  accuracy, understandable output and response time.
- **Assistant:** first-attempt task-completion rate for every supported command,
  including ambiguous filenames, confirmation, save and close behavior.
- **Safety:** verify that Guya does not close itself, overwrite or delete files,
  act outside allowed folders or run unsupported actions.
- **Usability:** structured tasks and short feedback from several participants;
  when possible, include at least one person who genuinely finds sustained
  typing difficult.
- **Daily use:** a short bug diary recording the exact spoken phrase, expected
  result, actual result and matching log time.

## 7. Expected outputs

- A runnable Guya MVP and installer/launcher path for macOS and Windows.
- Bilingual Voice-to-Text and limited Voice Assistant modes with separate keys.
- Setup wizard, control panel, floating status widget, spoken feedback, help and
  diagnostic logs.
- Automated test results, structured user-evaluation results and documented
  limitations.
- Final technical report and a repeatable demonstration/video.

## 8. Current status and remaining work

*(updated September 2026; this proposal supersedes the June 2026 dictation-only
draft kept in `docs/archive/`)*

The V1 feature set is implemented and feature development is frozen. Since the
July version of this document the following evidence has been produced and is
in the repository:

1. Speech accuracy and speed of six Whisper model sizes measured on a fixed
   Persian and English test set (Google FLEURS, 60 + 60 clips), plus an
   ablation of Guya's own decoding settings — `eval/results/`.
2. A held-out test of the command parser on 221 unseen Persian and English
   phrasings, before and after fixes (69.2% → 100% intent accuracy).
3. The assistant's real-use log turned into task-outcome and latency tables.
4. 136 automated tests.
5. The final report, `docs/REPORT.md`.

Done since (September 2026): installation and the primary tasks validated on
the target Windows laptop, and the session with the target user (twelve of
twelve tasks completed, System Usability Scale 82.5; `docs/REPORT.md`,
Section 7.9). Remaining: recordings of the target user's voice for the
accuracy set, and the demonstration video.

The intended result is a stable, explainable and evaluated undergraduate
prototype that addresses a concrete accessibility need.
