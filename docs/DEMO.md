# Guya — demonstration script (about 6 minutes)

A fixed sequence that shows every part of V1 once, in an order that never
depends on luck. Rehearse it twice; the timings below are from the development
Mac (M1 Pro, `large-v3-turbo`, offline).

## Before you start (2 minutes, off camera)

1. Open Guya.app. Wait until the control panel says **Guya is on** and the pill
   shows `⌥ Dictate · ⌘ Assist`.
2. Set the language badge to **EN** for the English half, **FA** for the Persian half.
3. Open TextEdit with an empty document, and Chrome on any page. Put a file
   named `report beta.docx` and one named `report alpha.docx` in Documents
   (this is what makes the "choose one" step happen on purpose).
4. Delete any old `test6.docx` / `آزمون شش.docx` from Documents.
5. Quit anything that talks (music, notifications).

## Part 1 — dictation (1 minute)

| Say (hold ⌥) | What the audience sees |
|---|---|
| *Hello, this is Guya. It types what I say into any application.* | the pill shows the partial text while you speak, then the sentence appears in TextEdit |
| (switch badge to FA) *سلام، این گویاست. هر چیزی که بگویم را در برنامهٔ فعال می‌نویسد.* | Persian text appears, right-to-left, in the same document |

Point out: nothing left the computer; the model runs locally.

## Part 2 — the assistant, English (2 minutes)

Hold ⌘ for each line. Wait for the reply before the next one.

| Say | Expected reply / action |
|---|---|
| *Create a Word file named test six* | "Created test6.docx. Open it now?" — **shows the ask-before-open rule** |
| *Yes* | Word opens `test6.docx` |
| *Close it* | the Word window closes; Guya stays open |
| *Open test six docks* | `test6.docx` opens again — **spoken filename normalisation** ("docks" → .docx) |
| *Rename it to demo report* | "Rename test6.docx to demo report? Say yes or no." |
| *No* | "Cancelled. Nothing was changed." — **confirmation before a change** |
| *Open report docs* | the pill and a popup show `report alpha.docx` / `report beta.docx` — **ambiguity shown, not guessed** |
| *Second* (or click it) | `report beta.docx` opens |
| *Delete the report file* | "Guya never deletes or removes files." — **safety boundary** |

## Part 3 — browser (1 minute)

Click inside the Chrome page first.

| Say | Action |
|---|---|
| *Go to YouTube* | YouTube opens in the current tab over HTTPS |
| *Let's scroll down a bit* | the page scrolls — **filler words are fine** |
| *Go back* | previous page |
| *Open Chrome and search for University of Tehran* | a Google search opens — a two-step command |

## Part 4 — the assistant, Persian (1 minute)

Switch the badge to FA.

| Say | Expected |
|---|---|
| *یه فایل ورد به اسم گزارش بساز* | «گزارش.docx ساخته شد. الان بازش کنم؟» shown in the bubble (Persian is shown, not spoken — say why: macOS has no Persian voice) |
| *نه* | «باشه. گزارش.docx ساخته شد و بسته ماند.» |
| *فایل گزارش رو پیدا کن* | «گزارش.docx پیدا شد...» |
| *یه کم برو پایین* (Chrome in front) | the page scrolls |

## Part 5 — what makes it device-aware (30 seconds)

Open the control panel's **Settings** tab and show the chosen model, then say:
"On first run the wizard timed a small model on this machine, predicted how the
larger ones would run, and picked the most accurate one that stays under real
time. On a weaker laptop it would have recommended the free online model."

## If something goes wrong

- A command is not understood: repeat it slowly; the pill shows what was heard.
- Nothing pastes: the text is on the clipboard; press ⌘V in the document.
- The browser command says "focus a supported browser": click in the page first.
- Guya's own window was in front: the pill now falls back to the last real target, but if a
  command fails, click in the target application and repeat.
