# Guya V1 — Final-Year Project Scope and Roadmap

## Project definition

Guya is an accessibility-focused desktop application for people with physical
or motor disabilities who can speak but find sustained typing and basic
computer navigation difficult. It combines:

1. Persian/English push-to-talk dictation into the active application.
2. A small, deterministic voice assistant for a limited set of safe desktop
   actions.
3. Device-aware offline/online speech-model selection so the application can
   run on both strong and weak computers.

Guya V1 is a university capstone prototype. It is not intended to be a general
AI assistant or a production-ready commercial accessibility product.

## Primary user

The primary user can speak clearly enough for speech recognition but has
difficulty typing long text or repeatedly operating the keyboard and mouse. A
caregiver may help with installation and first-time configuration.

## V1 feature boundary

### Included

- Persian and English push-to-talk dictation.
- Separate hotkeys for dictation and assistant commands.
- Offline, online, and dual speech-recognition modes.
- Device profiling and model recommendation.
- Accessible installer, setup wizard, control panel, floating status widget,
  spoken feedback, and logs.
- Safe assistant actions:
  - create Word/text files and folders, then ask before opening them;
  - open supported applications, files, and folders;
  - find files and folders using bilingual number/extension normalization;
  - show up to three ambiguous results, then accept a click or voice choice;
  - remember recent files and understand references such as “open it again”;
  - rename with confirmation and without overwriting;
  - save or close the active window;
  - open a browser and perform a safe web search;
  - open a known website or complete HTTPS domain;
  - scroll an active browser page, move to its top/bottom, and go back/forward.
- Filesystem access limited to configured user folders.
- Automated command, safety, and regression tests plus spoken user evaluation.

### Explicitly excluded

- A general Gemini/ChatGPT-style assistant.
- Arbitrary shell commands or unrestricted computer control.
- Deleting files, overwriting files, or bypassing confirmation.
- Reading or understanding arbitrary websites, clicking search results or page
  controls, and starting downloads.
- Application-specific workflows such as Save As in every editor.
- Wake-word/background listening.
- Perfect support for every accent, filename, application, or macOS/Windows
  version.
- App-store distribution, enterprise security certification, or global-scale
  production support.

## Definition of done

Guya V1 is ready for the final-year project when:

- installation and first launch work on the selected demonstration machines;
- dictation works in Word/TextEdit or Notepad in Persian and English;
- every included assistant action completes without crashes or unsafe side
  effects in the documented evaluation set;
- ambiguous file results can be understood visually and selected by voice;
- automated regression tests pass;
- real spoken tests are completed on macOS and the target Windows PC;
- at least one target user completes the main tasks and provides usability
  feedback;
- accuracy, latency, task success, limitations, and user feedback are reported;
- the repository, report, and demo scenario are understandable and reproducible.

The objective is a stable, explainable academic prototype—not zero defects in
every possible environment.

## Priority roadmap

### P0 — Freeze and stabilize the V1 feature set

- Keep the feature boundary frozen after the limited browser navigation above.
- Run the full English/Persian spoken evaluation.
- Fix crashes, unsafe behavior, incorrect actions, and common recognition
  failures found in logs.

### P1 — Cross-platform and accessibility validation

- Test installation, dictation, and the assistant on one macOS device and the
  target Windows PC.
- Test with the primary target user.
- Fix only usability blockers: unclear feedback, inaccessible selection,
  confusing setup, or unreliable primary tasks.

### P2 — Academic evaluation

- Measure speech accuracy and latency for the selected models.
- Record assistant task-completion success and response time.
- Compare representative tasks with typing/manual operation.
- Collect short usability feedback (for example SUS plus interview notes).

### P3 — Final delivery

- Clean the repository and installation instructions.
- Write architecture, implementation, evaluation, limitations, and future-work
  sections.
- Prepare a short repeatable demo and video.
- Package the final source, report, test results, and logs.

## Current completion estimate

- V1 software implementation: approximately **85% complete**.
- Whole capstone including evaluation, Windows validation, report, and demo:
  approximately **65–70% complete**.

Most remaining value now comes from testing, evidence, and documentation rather
than adding more features.
