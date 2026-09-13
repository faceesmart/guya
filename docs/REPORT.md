# Guya (گویا): Persian–English voice dictation and a limited desktop assistant for people who find typing hard

**B.Sc. Final-Year Project Report — Computer Engineering**

| | |
|---|---|
| Student | MohammadReza Ganji (220701091) |
| Supervisor | Dr. Hossein Aghababa |
| Institution | University of Tehran, Farabi Campus, Faculty of Engineering |
| Term | Eighth semester, 2026 |
| Code | `git@github.com:faceesmart/guya.git` |

## Contents

1. Introduction: problem, motivation, objectives, approach, deliverables, contributions
2. Background and related work: Whisper, faster-whisper, metrics, Persian, VAD, command understanding, accessibility, existing tools, Persian ASR research
3. Requirements analysis: users, use cases, a walkthrough of everyday use, functional, non-functional and safety requirements, constraints, scope
4. System design: architecture, processes, dictation path, speech pipeline, command understanding, model choice, safety model, feedback, platform abstraction, configuration, logging
5. Implementation: technology, code organisation, threads, speech module, filenames, parser, service, actions, widget, wizard, control panel, installer, tests, history, course concepts
6. User guide
7. Evaluation: data, model size, pipeline ablation, benchmark calibration, parser generalisation, real use, review, manual sessions, limits, objectives
8. Discussion
9. Conclusion and future work
References
Appendix A. Reproducing the results · B. The command set · C. Configuration · D. Evaluation instruments · E. Project history · F. Glossary

**Figures.** 4.1 Layered architecture · 4.2 The three processes · 4.3 Dictation sequence · 4.4 The transcription pipeline · 4.5 The assistant path · 4.6 Pending-question states · 4.7 Pill states and tones · 5.1 Settings tab · 5.2 Help tab · 6.1 Wizard welcome · 6.2 Wizard language choice · 6.3 Control panel

**Tables.** 1.1 Objectives · 1.2 Deliverables · 2.1 Whisper model sizes · 2.2 Existing tools · 3.1 Use cases · 3.2 Functional requirements · 3.3 Non-functional requirements · 3.4 Safety requirements · 4.1 Module responsibilities · 4.2 Response statuses · 4.3 Safety enforcement · 4.4 Pill states · 4.5 Platform interface · 4.6 Log record · 5.1 Dependencies · 5.2 Module sizes · 5.3 Threads and timers · 5.4 Decoding settings · 5.5 Filename match scale · 5.6 Parser rules · 5.7 Benchmark constants · 5.8 Test suite · 5.9 Development timeline · 5.10 Curriculum concepts · 6.1 Spoken commands · 7.1 Accuracy per model · 7.2 Ablation on small · 7.3 Ablation on large-v3-turbo · 7.4 Cost ratios · 7.5 Held-out intent accuracy · 7.6 Usage outcomes · 7.7 Review defects · 7.8 Manual sessions · 7.9 Objectives status · B.1 Command set · C.1 Configuration · F.1 Glossary

---

## Abstract

Guya is a desktop application for people who can speak but find sustained typing and repeated mouse and keyboard work difficult. It has two push-to-talk modes on two separate keys: dictation, which types what the user says into whatever application is in front, and a small assistant, which carries out a fixed set of safe desktop actions such as creating, finding, opening and renaming files, opening applications, saving and closing, and simple browser navigation. Both modes work in Persian and English, run entirely on the user's own computer with free software, and cost nothing to use. A setup wizard measures the computer's speed and recommends a speech model that will run at usable speed on that machine, with a free online model as the fallback for weak hardware. The application is installed with one double-click, is 11,894 lines of Python in 24 modules, has a safety boundary that cannot delete or overwrite anything, and is covered by 136 automated tests.

This report describes the requirements, the architecture and the implementation, and evaluates the system with reproducible measurements: word error rate of six Whisper model tiers on a fixed Persian and English test set, an ablation of Guya's own decoding settings, a calibration of the device benchmark, a held-out test of the command parser, and the assistant's real-use log. The main findings are that Persian needs a model at least the size of `large-v3-turbo` to be usable while English is already good with `small`; that one hand-tuned decoding setting inherited from earlier prototypes reduced accuracy and was measured, explained and removed; that the rule-based parser generalises well to unseen phrasings once filler words are handled (69% → 100% on a held-out set); and that almost all of the latency the user feels is the speech model itself, not the assistant.

چکیده: گویا یک برنامهٔ رومیزی برای افرادی است که می‌توانند صحبت کنند اما تایپ طولانی و کار مکرر با موس و کیبورد برایشان دشوار است. دو حالت «نگه‌دار و صحبت کن» (push-to-talk) روی دو کلید جداگانه دارد: دیکته، که گفتار کاربر را در هر برنامه‌ای که جلو باشد می‌نویسد، و یک دستیار کوچک که مجموعهٔ ثابتی از کارهای امن رومیزی را انجام می‌دهد: ساختن، پیدا کردن، باز کردن و تغییر نام فایل‌ها، باز کردن برنامه‌ها، ذخیره و بستن پنجره، و پیمایش ساده در مرورگر. هر دو حالت به فارسی و انگلیسی کار می‌کنند، به‌طور کامل روی رایانهٔ خود کاربر و با نرم‌افزار آزاد اجرا می‌شوند و هزینه‌ای ندارند. یک ویزارد نصب، سرعت رایانه را اندازه می‌گیرد و مدل گفتاری‌ای را پیشنهاد می‌کند که روی همان دستگاه با سرعت قابل استفاده اجرا شود؛ برای دستگاه‌های ضعیف، یک مدل آنلاین رایگان به‌عنوان جایگزین در نظر گرفته شده است. برنامه با یک دوبار کلیک نصب می‌شود، ۱۱٬۸۹۴ خط کد Python در ۲۴ ماژول دارد، مرز ایمنی‌ای دارد که هیچ‌چیز را حذف یا بازنویسی نمی‌کند، و ۱۳۶ آزمون خودکار آن را پوشش می‌دهند. این گزارش نیازمندی‌ها، معماری و پیاده‌سازی سیستم را شرح می‌دهد و آن را با اندازه‌گیری‌های قابل تکرار ارزیابی می‌کند: نرخ خطای واژه (WER) برای شش اندازهٔ مدل Whisper روی یک مجموعهٔ آزمون ثابت فارسی و انگلیسی، یک مطالعهٔ حذفی (ablation) روی تنظیمات رمزگشایی خود گویا، کالیبراسیون بنچمارک دستگاه، یک آزمون تعمیم‌پذیری تحلیل‌گر فرمان‌ها روی جمله‌های دیده‌نشده، و گزارش استفادهٔ واقعی از دستیار. یافته‌های اصلی این‌هاست: فارسی برای قابل استفاده بودن به مدلی دست‌کم به بزرگی `large-v3-turbo` نیاز دارد، در حالی که انگلیسی با مدل `small` هم خوب است؛ یک تنظیم دستی که از نمونه‌های اولیه به ارث رسیده بود دقت را کم می‌کرد و اندازه‌گیری، توضیح و حذف شد؛ تحلیل‌گر قاعده‌محور فرمان‌ها، پس از رسیدگی به واژه‌های اضافی گفتار، به جمله‌های دیده‌نشده خوب تعمیم می‌یابد (از ۶۹٪ به ۱۰۰٪ روی مجموعهٔ آزمون)؛ و تقریباً تمام تأخیری که کاربر حس می‌کند مربوط به خود مدل گفتار است، نه دستیار.

---
## 1. Introduction

### 1.1 Problem statement

Writing on a computer is mostly typing, and typing is a physical activity. For a person with a motor impairment, one paragraph can take several minutes and can hurt. The small tasks around writing cost as much again: opening the right document, finding it after it has been closed, renaming it, moving a web page down to read the rest of it. Each of these is a sequence of precise mouse and keyboard operations.

Dictation software has existed for a long time, and operating systems now include voice control. In practice none of it fits a Persian speaker on an ordinary home computer. The built-in dictation of macOS and Windows does not list Persian. The commercial products that do support Persian are Windows-only and licensed. The cloud services that recognise Persian well send every sentence to a server and need an account, and they do not help with the tasks around the text at all. A survey of these tools is given in Section 2.8.

There was also a technical question at the start of the project. Open speech models such as Whisper recognise Persian, but the large models that do it well are slow on a laptop processor, and the small models that are fast do not do it well. Whether a usable Persian dictation tool could run entirely on a normal computer, at no cost, was not known when the project began. Part of this report answers that question with measurements.

### 1.2 Motivation and target user

The project has one concrete user in mind: the author's brother. He speaks clearly, but long typing is difficult for him, and a good part of his daily computer use is writing in Persian with some English mixed in. This fixed three constraints before any code was written. The software had to run on the kind of computer a family already owns, with no graphics card and no subscription. It had to work in Persian as well as English. And it had to be something a family member could install and set up for him without technical help.

The user is described more formally in Section 3.1. The important point is that the project was built for a real person, and the design decisions in Chapter 4 were tested against what he would actually do with it.

### 1.3 Objectives

The approved proposal (Appendix E summarises its history) states five objectives. They are repeated here because the evaluation in Chapter 7 is organised around them.

| ID | Objective |
|---|---|
| O1 | Reliable Persian and English push-to-talk dictation into the active application. |
| O2 | A separate bilingual assistant for a limited set of desktop actions: creating, finding, opening and renaming files and folders, opening applications, saving or closing the active window, and safe web search and browser navigation. |
| O3 | Predictable and safe behaviour through rule-based command understanding, confirmation before renaming, visible choices for ambiguous results, and restricted filesystem access. |
| O4 | Offline, online and dual recognition modes, with device profiling and a measured model recommendation during setup. |
| O5 | Evaluation of recognition accuracy, response time, command-task success, safety and usability. |

*Table 1.1. Project objectives, from the proposal.*

### 1.4 Approach

Guya is a desktop application written in Python. Speech recognition is done locally by OpenAI's Whisper model, run through the faster-whisper library on the CTranslate2 inference engine with 8-bit weights, so that even the large model runs on a laptop CPU. The user holds one key to dictate and another key to give a command. Dictated text is pasted into whatever application is in front. Commands go to a small assistant whose understanding is rule-based: a fixed set of intents, each recognised by keywords and regular expressions written for Persian and for English, with a phrase list as a fallback. The assistant carries out actions through a thin platform layer for macOS and Windows, behind a safety boundary that cannot delete or overwrite anything and cannot leave three user folders.

Because the model Persian needs is heavy, a setup wizard measures the computer's speed on first run and recommends the most accurate model that will keep up with speech on that machine. If nothing does, it offers a free online model instead, and a dual mode lets one language run offline and the other online.

The whole system was built and evaluated on the author's laptop (Apple M1 Pro, 16 GB) between June and September 2026, and it is used daily on that machine.

### 1.5 What was delivered

The project delivered a working, installable application together with the material needed to evaluate and reproduce it. Table 1.2 lists the deliverables. Sizes are from the repository at the time of writing.

| Deliverable | Content | Size |
|---|---|---|
| Application | dictation widget, assistant, setup wizard, control panel, platform adapters for macOS and Windows | 24 Python modules, 11,894 lines |
| Installers and launchers | one-double-click installers for macOS and Windows, a generated `Guya.app` bundle, an uninstaller inside the control panel | 6 scripts |
| Evaluation harness | speech accuracy and speed scorer, FLEURS importer, ablation switches, held-out intent evaluator, usage-log analyser, table generator | 8 modules, 1,240 lines |
| Test suite | unit and regression tests that run without a microphone, model or network | 136 tests, 10 files, 1,598 lines |
| Data and results | 120-clip bilingual speech test set (manifest), 267 command phrasings, all result files | 60 result files |
| Documentation | user guide (Chapter 6), demonstration script, user-study protocol, spoken evaluation checklist, this report in English and Persian | |

*Table 1.2. Deliverables.*

The repository holds 52 commits between 5 June and 13 September 2026, with the assistant added in August and the evaluation in September (Section 5.14 gives the history).

### 1.6 Contributions

Beyond the software, the project produced evidence that did not exist before it, all of it reproducible from the repository (Appendix A):

1. A measurement of six Whisper model sizes on Persian and English read speech on consumer hardware, giving accuracy and speed for each. This is the data behind the wizard's recommendation and the per-language model floor (Section 7.2).
2. An ablation of Guya's own decoding settings, one setting at a time. It showed that one setting inherited from early prototypes, the repetition penalty, was cutting sentences short, and it was removed (Section 7.3).
3. A calibration of the device benchmark against measured cost ratios, replacing estimates that were wrong by a factor of two to three (Section 7.4).
4. A held-out test set of 267 natural Persian and English command phrasings and an evaluator for the parser. Intent accuracy on the 221 unseen phrasings went from 69.2% to 100% after the parser was changed to handle filler words and keyword navigation (Section 7.5).
5. A structured log record for every assistant command, which turns daily use into an evaluation dataset (Section 7.6).

### 1.7 Structure of the report

Chapter 2 gives the background on speech recognition with Whisper, on Persian as a low-resource language, on command understanding, and on the existing tools. Chapter 3 states the requirements and the scope. Chapter 4 describes the architecture and the design decisions. Chapter 5 describes the implementation module by module, the testing strategy and the development history. Chapter 6 is the user guide. Chapter 7 presents the evaluation. Chapter 8 discusses the results and their limits, and Chapter 9 concludes with future work. The appendices give the reproduction commands, the command set, the configuration keys, the evaluation instruments, the project history and a glossary.

---
## 2. Background and related work

### 2.1 Automatic speech recognition and Whisper

Automatic speech recognition (ASR) turns an audio signal into text. Until a few years ago a competitive recogniser was assembled from separate acoustic, pronunciation and language models, each trained on data prepared for that language. Persian systems of that kind exist (Section 2.8), but building one is a multi-year effort for a company. What changed the picture for a student project is the arrival of large end-to-end models trained on many languages at once.

Whisper (Radford et al., 2023) [1] is such a model. It is an encoder–decoder Transformer trained by OpenAI on 680,000 hours of audio collected from the web, paired with the transcripts that accompanied it. The audio is cut into 30-second windows, converted to a log-mel spectrogram, and passed through the encoder; the decoder then generates text tokens one at a time, conditioned on the encoder output and on the tokens already produced. Special tokens at the start of the decoder sequence tell the model which language to expect and whether to transcribe or translate. The same weights therefore handle Persian and English, and a language token is all that switches between them. That is the property that made this project possible at zero cost: no Persian-specific training was needed to get a usable Persian recogniser.

Whisper is released in several sizes, listed in Table 2.1. The `large-v3-turbo` variant keeps the full encoder of `large-v3` but reduces the decoder from 32 layers to 4, which makes it several times faster with only a small loss of accuracy [1]. Chapter 7 measures how much of that claim holds for Persian on a laptop.

| Model | Parameters | Download size (int8, MB) | Notes |
|---|---:|---:|---|
| tiny | 39 M | 75 | used by the wizard as a speed probe |
| base | 74 M | 145 | |
| small | 244 M | 484 | the English floor in Guya |
| medium | 769 M | 1,530 | |
| large-v3-turbo | 809 M | 1,620 | the Persian floor and the default |
| large-v3 | 1,550 M | 3,090 | |

*Table 2.1. Whisper model sizes. Parameter counts from the model card [1]; download sizes are the CTranslate2 int8 conversions the wizard reports.*

Decoding matters as much as the model. Whisper's decoder is run with beam search (Guya uses a beam of 5) and has a set of built-in quality checks: if the generated text compresses too well (a sign of repetition) or its average log-probability is too low, the library retries the window at a higher sampling temperature. It also estimates a "no speech" probability for each window, which is used to drop segments that are probably silence. These mechanisms are the source of two well-known Whisper failure modes that Guya has to handle: hallucinated text on silence or noise, typically sentences such as "thanks for watching" that were common in the training subtitles, and repetition loops where the decoder emits the same phrase again and again. Section 5.4 describes the filters Guya applies, and Section 7.3 measures what each of them costs.

### 2.2 faster-whisper and CTranslate2

Running the original PyTorch implementation of Whisper on a CPU is slow. Guya uses faster-whisper [2], a re-implementation of the inference on CTranslate2 [3], an engine written in C++ for Transformer models. CTranslate2 quantises the weights to 8-bit integers on the CPU, which cuts memory by about four times and speeds up the matrix operations, at a cost in accuracy that the authors put at a fraction of a percent of word error rate. The library also bundles the Silero voice activity detector (Section 2.5) and exposes all of Whisper's decoding options as keyword arguments. faster-whisper 1.2.1 and CTranslate2 4.8.1 were used throughout the project.

With 8-bit weights the largest turbo model transcribes at about a third of real time on the development machine (Section 7.2), which is what makes a fully local Persian system practical. The same measurement shows that the speed varies by an order of magnitude across model sizes and, on other machines, will vary again. That variation is why Guya measures the machine instead of assuming (Section 4.6).

### 2.3 Measuring a recogniser

Three figures are used throughout this report.

The **word error rate** (WER) of a transcript against a reference is the minimum number of word substitutions, deletions and insertions needed to turn one into the other, divided by the number of words in the reference:

WER = (S + D + I) / N

The **character error rate** (CER) is the same quantity computed over characters, with spaces removed. It is reported next to WER for Persian because a large share of Persian word errors are spacing differences that a reader barely notices (Section 7.2); CER shows how much of the text is actually right.

The **real-time factor** (RTF) is the time spent transcribing divided by the duration of the audio. An RTF of 0.5 means ten seconds of speech take five seconds to transcribe. Below 1.0 the recogniser keeps up with speech.

All error rates in this report are corpus-level: the edit counts of all clips are summed before dividing, so long clips weigh more than short ones. Both reference and hypothesis go through the same normalisation before scoring (lower case, punctuation removed, digits and spelled-out numbers unified, Arabic letter forms folded into Persian ones, diacritics and the zero-width non-joiner removed). The scorer is in `eval/wer.py` and has its own tests, because every number in Chapter 7 depends on it.

### 2.4 Why Persian is harder

Persian is a low-resource language for Whisper. The training data is dominated by English, and Persian is one of the languages with a small share of it. The writing system adds difficulties of its own. Persian uses the Arabic script with several letters that have two Unicode forms (ي and ی, ك and ک), so the same word can be written two ways. Short vowels are usually not written. Compound words and verb prefixes are joined with a zero-width non-joiner (ZWNJ) that many writers replace with a space or omit («می‌کند», «می کند», «میکند»), and Whisper's output is inconsistent about it. Finally, the spoken language differs from the written one: a speaker says «میخوام» and the model, trained on written text, writes «می‌خواهم». Guya reverses the most common of these (Section 5.4), and the evaluation reports CER next to WER so that spacing variation does not hide the real picture.

### 2.5 Voice activity detection

A voice activity detector (VAD) labels each short frame of audio as speech or not. Whisper transcribes fixed 30-second windows and tends to hallucinate on silence, so removing silent stretches before decoding reduces both wasted computation and invented text. faster-whisper includes the Silero VAD [6], a small recurrent network shipped as an ONNX file, and trims the audio according to four parameters: the speech probability threshold, the minimum silence that ends a speech region, the minimum length of a speech region, and the padding kept around each region. Guya lowers the threshold and shortens the silence gap relative to the library defaults, because its users speak quietly and pause inside sentences; the exact values and their measured effect are in Sections 5.4 and 7.3.

### 2.6 Command understanding: rules or a language model

A voice assistant must map a transcript to an intent and its arguments, for example "rename it to final report" to *rename* with the new name *final report*. The common way to do this today is to send the text to a large language model. Guya uses a deterministic parser instead: keyword sets, regular expressions written for each command in each language, and a list of example phrases used as a fallback. Three reasons decided this.

First, cost and locality. A language model API is paid or rate-limited and needs a connection; a local language model would compete with Whisper for the same CPU.

Second, explainability. Every decision of a rule-based parser can be printed and traced to a line of code. When the action is renaming someone's file, that matters.

Third, safety. The parser can only produce intents from a fixed list, and the action layer only implements those intents. There is no path from spoken text to an arbitrary action, and no prompt injection to defend against. Section 4.7 builds the safety argument on this.

The cost of the choice is coverage: a rule-based parser understands only phrasings someone thought of. Section 7.5 measures this cost on phrasings the parser had never seen and shows how it was reduced.

### 2.7 Accessibility considerations

Several design choices follow from the intended user rather than from the technology. Push-to-talk was chosen over a wake word: it needs no always-on microphone, it gives the user explicit control over when the computer listens, and the key pressed says which mode is meant. Feedback is always visible on screen, and in English it is also spoken. The floating status widget pairs every colour with a text label, so colour is never the only carrier of state, and its clickable targets are large; both are criteria of the Web Content Accessibility Guidelines 2.2 [9] that the widget was checked against. Ambiguous results are shown as large buttons that can equally be chosen by voice. Anything that changes a file asks first. These are ordinary accessibility principles; the interesting part is where the platform constrained them, for example the decision to show Persian feedback rather than read it with an Arabic voice (Section 4.9).

### 2.8 Existing tools

None of the mainstream dictation and voice-control products covers the case this project is built for: a Persian speaker on an ordinary computer with no budget. Table 2.2 summarises the state in September 2026, taken from the vendors' own documentation [10–15].

| Tool | Persian dictation | Voice commands for the desktop | Runs offline | Cost | Platform |
|---|---|---|---|---|---|
| Apple Dictation / Voice Control | no (Persian is not in the dictation language list; Voice Control supports English, Spanish, French, German, Chinese, Japanese) | yes, English and a few others | partly | free | macOS, iOS |
| Windows Voice Access / voice typing | no (15 variants of English, Spanish, German, French, Chinese, Japanese, Italian) | yes | yes | free | Windows 11 |
| Nuance Dragon Professional v16 | no (eight languages, none Persian) | yes | yes | about US $700 | Windows only; the Mac version was discontinued |
| Google Docs voice typing | yes (Farsi is listed) | inside Google Docs only | no, the browser's cloud service | free | any browser |
| Talon Voice | no (the main model is English only) | yes, very deep, aimed at programmers with RSI | yes | free tier, paid beta | macOS, Windows, Linux |
| Nevisa (Asr Gooyesh Pardaz) | yes, Persian since 2003, medical and legal editions | a separate product, Kara | yes | commercial licence | Windows |
| **Guya** | **yes, Persian and English** | **yes, a fixed safe set, bilingual** | **yes** | **free** | **macOS; Windows code present, unvalidated** |

*Table 2.2. Existing tools against the project's requirements.*

Two of these are the nearest neighbours and deserve a closer look.

Nevisa is the serious Persian dictation product. It was built by an Iranian company over two decades on a classical recogniser tuned for Persian, and it exists because the international vendors never covered the language. It is commercial, Windows-only, and its command product is separate. Guya does not compete with it. Guya is what becomes possible once an open multilingual model such as Whisper exists: a free, cross-platform tool that one student can build and a family can install, with dictation and commands in one program.

Talon is the closest in spirit on the accessibility side. It is designed for people who cannot use their hands at all, it is precise, and it has a large community of command grammars. It is also English-only and a power-user tool with a learning curve. Guya's user is meant to learn two keys and a dozen sentences.

The gap Guya fills is therefore narrow and real: Persian plus English, dictation plus a few safe commands, local and free, on a normal laptop.

### 2.9 Research on Persian speech recognition

Persian was, for a long time, a language with little public speech data. Two developments changed that. Public read-speech corpora that include Persian appeared, Mozilla Common Voice (Ardila et al., 2020) [5] and Google FLEURS (Conneau et al., 2022) [4]. And Whisper (Radford et al., 2023) [1] was trained on web audio in 97 languages and recognises Persian without any Persian-specific work. The `large-v3` release added one million hours of weakly labelled and four million hours of pseudo-labelled audio, and OpenAI reports 10 to 20% fewer errors than `large-v2` on Common Voice 15 and FLEURS for the languages it handles well.

Two facts from this work shaped the project's expectations. First, Whisper's Persian error rate is several times its English error rate at every model size; Section 7.2 measures this on the project's own test set. Second, fine-tuning Whisper on Persian data helps a great deal: a `large-v3` fine-tuned on Common Voice Persian reports about 13% WER on FLEURS [7], less than half the error of the stock model measured here. Fine-tuning needs a GPU and time that this project did not have; it is the most promising item of future work (Section 9.2).

### 2.10 What Guya takes from this

From the products: the two-key design (Talon and Dragon both separate dictation from commands), confirmation before destructive actions (Voice Control confirms), and the observation that no one has solved Persian on the desktop for free. From the research: Whisper through faster-whisper as the recogniser, the expectation that Persian needs the largest practical model, FLEURS as the test set so that the numbers can be reproduced and compared with published work, and fine-tuning as future work.

---
## 3. Requirements analysis

### 3.1 Stakeholders and primary user

There are three roles around the system. The **primary user** can speak clearly enough for speech recognition but finds sustained typing and repeated mouse and keyboard operation difficult. He writes mostly in Persian, sometimes in English, in a word processor and in the browser. He is not a technical user and should not have to read a manual. A **helper**, a family member, installs the software and runs the first-time setup; the installer and wizard must be usable by a non-technical person. The **developer** (the author) needs to diagnose problems from a log after the fact, because he is not present when the user hits them.

The user's computer is an ordinary laptop or desktop without a discrete graphics card, running macOS or Windows. Internet may be slow or absent, and no paid service can be assumed.

### 3.2 Use cases

Table 3.1 lists the use cases the system supports. Each was written before the corresponding feature and is exercised by the demonstration script (`docs/DEMO.md`) and the user-study task list (`docs/USER_STUDY.md`).

| ID | Use case | Actor | Main flow | Result |
|---|---|---|---|---|
| UC-1 | Dictate text | user | places the cursor in any application, holds the dictation key, speaks a sentence, releases | the sentence appears at the cursor in the language the badge shows |
| UC-2 | Create a document | user | holds the assistant key, says "create a Word file named report" | the file is created in Documents; Guya asks whether to open it; a spoken or clicked yes opens it |
| UC-3 | Find and open a file | user | says "open test six docs" or «فایل گزارش رو پیدا کن» | a unique match opens; several close matches are shown as up to three buttons to click or name |
| UC-4 | Rename a file safely | user | says "rename it to final report" | Guya shows the old and new names and asks; only "yes" renames; an existing name is never overwritten |
| UC-5 | Control the active window | user | says "save it", "close it" | the keystroke is sent to the application the command was spoken to |
| UC-6 | Use the browser | user | says "go to YouTube", "scroll down", "go back", "search for the weather on Chrome" | the browser navigates; searches open in the browser in front or the one named |
| UC-7 | Switch language | user | clicks the badge or says "switch to Persian" / «برو انگلیسی» | recognition language changes for both modes |
| UC-8 | First-time setup | helper | double-clicks the installer, answers three questions in the wizard | the model is downloaded, a launcher is created, Guya starts |
| UC-9 | Everyday start and stop | user or helper | double-clicks Guya, later closes it from the control panel | the widget appears on screen; all processes end together |
| UC-10 | Diagnose a problem | developer | opens the log from the control panel | every command is one structured record with what was heard and what happened |

*Table 3.1. Use cases.*

### 3.3 A walkthrough of everyday use

The use cases above are easier to judge as one continuous day. What follows is the intended journey of the primary user after the helper has installed Guya; every screen text quoted is the one the software shows.

**Morning.** He double-clicks Guya. The control panel opens, its power button turns teal, the status line reads "Guya is on", and a small grey circle appears at the top centre of the screen. He does not touch the panel again; it can be minimised. He opens Word, places the cursor, holds the Right Option key and starts a Persian sentence. The circle expands into a pill, turns red, and shows "● Dictation listening…" followed by the first words as they are recognised. When he releases the key the pill turns blue ("Processing…"), then green ("✓ Done"), and the sentence appears at the cursor with Persian spacing and colloquial forms as he spoke them. He continues sentence by sentence. Nothing has left the computer; the model is running on the laptop.

**An English email.** He needs to reply in English. He says, on the assistant key, "switch to English"; the pill answers "Switched to English." in a spoken voice and the badge changes from FA to EN. He dictates the reply the same way, then says «برو فارسی» to switch back. Persian replies are not spoken, so this one appears on the pill and in the bubble beneath it.

**A new document.** He holds the Right Command key and says «یه فایل ورد به اسم گزارش هفتگی بساز». The pill turns amber and the bubble shows «گزارش هفتگی.docx ساخته شد. الان بازش کنم؟ بگویید بله یا نه.» with two buttons, بله and نه. He says «بله» (or clicks) and the document opens in Word. Had he said nothing, the question would have expired after two minutes and the file would have stayed closed.

**Finding a file from last week.** Later he says «فایل گزارش رو باز کن». There are two candidates, so the pill asks and a popup lists them: "1. گزارش هفتگی.docx in Documents" and "2. گزارش.docx in Desktop", with the hint «روی گزینه بزنید یا بگویید اول، دوم، سوم یا لغو». He says «دومی»; it opens. He decides the name is wrong and says «اسمش رو بذار گزارش قدیمی». The bubble asks «نام گزارش.docx به گزارش قدیمی.docx تغییر کند؟ بگویید بله یا نه.» Only after his «بله» is the file renamed, and if a file of that name had existed the assistant would have refused.

**The browser.** He clicks inside Chrome and says "go to YouTube". The page opens in the current tab. He says "let's scroll down a bit", then "go back". Each command is answered on the pill ("Scrolled down.", "Went back one page."). If he had said "scroll down" while Word was in front, the reply would have been "Focus a supported browser, then try the command again."

**When something goes wrong.** He clicks the pill by mistake and then dictates a sentence: the pill shows "Copied! Press ⌘V to paste", because Guya itself is now the application in front and the text has been left on the clipboard. He pastes it. Another time the pill says "Too short — hold the key while you speak", because he released the key before the first word. If he asked for something outside the list, "delete the old report", the bubble would explain that Guya never deletes or removes files.

**Evening.** He closes Word and the browser as usual, then clicks the power button on the panel or closes the panel window. The pill disappears with it; no process is left holding the microphone.

The walkthrough is the basis of the demonstration script in `docs/DEMO.md` and of the task list used in the user study (Appendix D).

### 3.4 Functional requirements

Table 3.2 lists the functional requirements as implemented in version 1. The last column names where each is verified: an automated test file, an evaluation section, or the manual test sessions of Section 7.8.

| ID | Requirement | Verified by |
|---|---|---|
| FR-1 | Push-to-talk dictation in Persian and English, with the recording bounded by the key press and release. | daily use; Section 7.2 |
| FR-2 | While the key is held, the words recognised so far are shown on the status widget. | daily use |
| FR-3 | On release, the full recording is transcribed once and the text is pasted into the application in front; if pasting is impossible the text stays on the clipboard and the widget says so. | daily use; Section 7.8 |
| FR-4 | A second key, distinct from the dictation key, starts a command; a dictated sentence can never be executed as a command. | `test_platform_macos.py` |
| FR-5 | Create a Word document, a text file or a folder from a spoken name, then ask whether to open it. | `test_assistant_service.py` |
| FR-6 | Open an application from a fixed list (word processor, text editor, calculator, file manager, browsers). | `test_assistant_parser.py` |
| FR-7 | Find and open files and folders by spoken name, including spoken numbers and spoken extensions ("test six docs"). | `test_assistant_normalizer.py`, `test_assistant_actions.py` |
| FR-8 | When several files match, show at most three choices that can be clicked or chosen by voice ("first", «دوم»). | `test_assistant_service.py` |
| FR-9 | Remember recently used files so that "open it again" and "rename it" work without a name. | `test_assistant_service.py` |
| FR-10 | Rename a file or folder only after confirmation and never over an existing name. | `test_assistant_actions.py`, `test_review_regressions.py` |
| FR-11 | Save or close the window the command was spoken to. | `test_assistant_actions.py` |
| FR-12 | Open a website by a known name or a spoken domain, always over HTTPS. | `test_assistant_actions.py` |
| FR-13 | Search the web in the browser in front or in a named browser. | `test_assistant_parser_robustness.py`, `test_review_regressions.py` |
| FR-14 | Scroll, go to top or bottom, go back and forward in the browser in front. | `test_assistant_service.py`, Section 7.5 |
| FR-15 | Carry out two or three commands spoken in one sentence ("open Chrome, then search for YouTube"). | `test_assistant_parser.py`, `test_assistant_service_pending.py` |
| FR-16 | Switch the recognition language by voice or by clicking the badge. | `test_review_regressions.py` |
| FR-17 | Answer a pending question by voice or by clicking a button; a question left unanswered expires. | `test_assistant_service_pending.py` |
| FR-18 | Refuse deletion and Save As with an explanation. | `test_assistant_service_pending.py` |
| FR-19 | A setup wizard measures the computer, recommends a model, downloads it and creates a launcher. | `test_benchmark.py`; Section 7.4 |
| FR-20 | Offline, online and dual recognition modes, switchable from the control panel. | manual |
| FR-21 | A control panel turns Guya on and off, changes settings, shows the log, and can update, re-run setup or uninstall. | manual |
| FR-22 | Every process writes to one log, and every assistant command produces one structured record. | Section 7.6 |

*Table 3.2. Functional requirements.*

### 3.5 Non-functional requirements

| ID | Requirement | How it is met |
|---|---|---|
| NFR-1 | Zero cost: only free software and services. | faster-whisper, PyQt6 and Python; the optional online model uses Groq's free tier. |
| NFR-2 | Local operation: after the one-time model download, dictation and commands work with no internet connection. | offline mode; no telemetry; the only network call is the optional cloud transcription. |
| NFR-3 | Responsiveness: the recommended model must transcribe faster than real time on the user's machine. | the wizard measures the machine and applies a real-time factor threshold of 1.0 (Section 4.6). |
| NFR-4 | Installability by a non-technical helper. | one-double-click installers, a wizard in Persian or English with an easy mode. |
| NFR-5 | Bilingual interface and replies. | every reply exists in Persian and English; the wizard and panel are translated. |
| NFR-6 | Feedback is never colour alone and never silent: every state has a text label, and every question is shown in full. | pill labels, reply bubble, spoken English. |
| NFR-7 | Privacy: audio never leaves the machine unless the user chose the online mode explicitly. | the wizard states this on the mode page; the configuration file holding a key is owner-readable only. |
| NFR-8 | Diagnosability: a problem reported after the fact can be understood from the log alone. | one rotating log, structured command records (Section 4.11). |
| NFR-9 | Testability: the logic can be tested without a microphone, a model or a network. | the parser, service and action layers are separated from the UI; 136 tests run in a quarter of a second. |
| NFR-10 | Portability: the same code base runs on macOS and Windows. | platform adapters for hotkeys, window targeting, keystrokes and speech. |

*Table 3.3. Non-functional requirements.*

### 3.6 Safety requirements

The safety requirements were fixed early and are enforced in code rather than by convention. Section 4.7 explains where each is implemented.

| ID | Requirement |
|---|---|
| SR-1 | No delete action exists. A spoken request to delete is refused with an explanation. |
| SR-2 | Nothing is ever overwritten: creating a file with an existing name fails, and renaming onto an existing name fails. |
| SR-3 | The assistant touches only paths inside the configured folders (Desktop, Documents, Downloads by default); every path is resolved, symbolic links included, before the check. |
| SR-4 | Applications are launched only from a fixed table, never from a spoken string. |
| SR-5 | Websites are opened only as an HTTPS host, either a known name or a domain the user spoke as a domain; no path, query, port or script. |
| SR-6 | Keystrokes are addressed to the process the command was spoken to, never broadcast, and never to Guya's own process. |
| SR-7 | No subprocess is started through a shell, and spoken text is never part of a command line. |
| SR-8 | Renaming, and opening a file that was just created, happen only after the user confirms. |
| SR-9 | A pending question expires after two minutes, so a late "yes" cannot act on something forgotten. |
| SR-10 | A multi-step command is validated as a whole before its first step runs, and may only open applications or websites, search, save or close. |

*Table 3.4. Safety requirements.*

### 3.7 Constraints

The project was carried out by one student in one term, alongside other courses, with no budget. Development and all measurements were done on one machine, an Apple M1 Pro laptop with 16 GB of memory and no CUDA GPU. The target Windows machine belongs to the user's family and was not available for testing during the term. Persian text-to-speech is not available on macOS at all, which constrains how Persian replies can be delivered (Section 4.9).

### 3.8 Out of scope

The following were excluded from version 1 in the proposal and remain excluded: a general conversational assistant; arbitrary shell commands or unrestricted control of the computer; deleting or overwriting files or bypassing confirmation; reading or understanding arbitrary web pages, clicking results, or downloading; application-specific workflows such as Save As in every editor; wake-word listening; support for every accent, filename and application; and app-store distribution. These limits are deliberate. They keep the safety argument of Section 4.7 small enough to be read in full.

---
## 4. System design

### 4.1 Architecture overview

Guya is organised in six layers, shown in Figure 4.1. The proposal described five of them; the sixth, infrastructure, grew out of the installation and diagnosis problems met during the term. Every layer is a Python package or module inside `guya/`, and the dependencies point downward only: the interaction layer knows about the speech and command layers, the command layer knows about the action layer, and nothing below knows about the user interface. This is what allows the command and action layers to be tested without a screen, a microphone or a model (Section 5.13).

```mermaid
flowchart TB
    subgraph L1["Interaction layer"]
        PILL["Floating pill<br/>(widget.py)"]
        BUB["Reply bubble and<br/>choice popup"]
        PANEL["Control panel<br/>(control_panel.py)"]
        WIZ["Setup wizard<br/>(wizard.py)"]
    end
    subgraph L2["Speech layer"]
        REC["Recorder and<br/>partial transcriber"]
        STT["Transcription pipeline<br/>(stt.py)"]
        CLOUD["Online backend<br/>(cloud_engine.py)"]
    end
    subgraph L3["Command layer"]
        NORM["Normaliser<br/>(assistant/normalizer.py)"]
        PARSE["Rule-based parser<br/>(assistant/parser.py)"]
        SVC["Service: context, questions,<br/>dispatch (assistant/service.py)"]
    end
    subgraph L4["Action layer"]
        SAFE["Safe desktop actions<br/>(actions/common.py)"]
        MAC["macOS adapter<br/>(actions/macos.py)"]
        WIN["Windows adapter<br/>(actions/windows.py)"]
    end
    subgraph L5["Platform layer"]
        HOT["Hotkeys, frontmost app,<br/>paste, permissions<br/>(platform_macos.py)"]
    end
    subgraph L6["Infrastructure"]
        CFG["Configuration<br/>(config.py)"]
        RT["Panel-widget IPC<br/>(runtime.py)"]
        LOG["Logging<br/>(logsetup.py)"]
        BENCH["Profiler and benchmark<br/>(profiler.py, benchmark.py)"]
        LAUNCH["Installer and launcher<br/>(launcher_gen.py)"]
    end
    PILL --> REC --> STT
    STT --> CLOUD
    PILL --> SVC
    SVC --> PARSE --> NORM
    SVC --> SAFE
    SAFE --> MAC
    SAFE --> WIN
    PILL --> HOT
    WIZ --> BENCH
    PANEL --> RT
    PILL --> RT
```

*Figure 4.1. Layered architecture. Arrows show the direction of calls.*

Table 4.1 gives each module's responsibility in one line. Sizes are discussed in Section 5.2.

| Module | Responsibility |
|---|---|
| `widget.py` | the pill process: hotkeys, recording, live and final transcription, pasting, assistant glue, bubble and popup, state publication |
| `stt.py` | the transcription pipeline shared by the widget and the evaluation harness |
| `cloud_engine.py` | the optional online transcription through Groq |
| `assistant/normalizer.py` | Unicode and spoken-number normalisation; spoken filename normalisation; filename match scoring |
| `assistant/parser.py` | transcript to intent and slots, Persian and English |
| `assistant/service.py` | context memory, pending questions, sequence validation, dispatch to actions, bilingual replies |
| `assistant/context.py`, `models.py` | the data classes: parsed command, response, action outcome, context |
| `assistant/actions/common.py` | the safety boundary and filesystem actions; abstract platform operations |
| `assistant/actions/macos.py`, `windows.py` | the platform adapters: open, keystrokes, browser, speech |
| `platform_macos.py` | hotkey listener, frontmost application, paste, Accessibility permission |
| `wizard.py`, `profiler.py`, `benchmark.py` | first-run setup, device profile, measured model recommendation |
| `control_panel.py` | the everyday window: power, live controls, settings, help, logs, maintenance |
| `config.py`, `runtime.py`, `logsetup.py`, `launcher_gen.py`, `__main__.py` | configuration, IPC files, logging, launcher generation, entry point |

*Table 4.1. Module responsibilities.*

### 4.2 Process model

At run time Guya is three cooperating processes, all Python (Figure 4.2). The **wizard** runs once, on first launch or on request. The **control panel** is the window the user double-clicks; it starts the **widget** as a child process and mirrors its state. The widget is the program that listens and acts.

```mermaid
flowchart LR
    subgraph first_run["First run"]
        W[Setup wizard<br/>profile device, run benchmark,<br/>recommend model, write config]
    end
    subgraph daily["Every day"]
        P[Control panel<br/>power button, settings, help, logs] -- "spawns python -m guya --widget" --> D
        D[Dictation widget<br/>hotkeys, microphone, Whisper,<br/>assistant, floating pill]
        D <-- "rt_state.json / rt_cmd.json<br/>(400 ms)" --> P
    end
    C[(~/.guya/config.json)]
    L[(~/.guya/logs/guya.log)]
    W --> C
    C --> P
    C --> D
    D --> L
    P --> L
```

*Figure 4.2. The three processes and the files they share.*

Two reasons forced the split between panel and widget. The first is import order. The Whisper model must be loaded before the Qt library is imported, because on Windows the CUDA backend of CTranslate2 crashes if Qt has initialised its OpenGL libraries first. A child process that loads the model and only then imports Qt gives that ordering for free, and the entry point relaunches itself after the first-run wizard for the same reason. The second is robustness. If the widget process dies, the panel notices within half a second and shows the power button as off; the user restarts with one click instead of losing the window.

The two processes talk through two small JSON files written atomically (a temporary file renamed over the target). The widget publishes its state every 400 ms: process id, timestamp, enabled flag, backend, language, hybrid flag, microphone status, current state, and whether the Accessibility permission is granted. The panel polls at the same interval, treats a state older than two seconds as stale, and sends commands (turn on or off, switch language, switch backend, enable the assistant) with a monotonically increasing sequence number so that a command is never applied twice. This is not elegant, but it needs no sockets, no permissions and no library, and it survives either process restarting.

Three guards keep the process model tidy. The widget compares its parent process id with the one recorded at start-up on every tick and exits if the panel has gone, so a closed panel never leaves an orphan holding the hotkeys and the microphone. Each process takes a lock file (`widget.lock`, `control-panel.lock`, stale after ten seconds) so that a double launch cannot start two widgets that would both open the microphone and both fail. And all three processes write to the same log (Section 4.11).

### 4.3 The dictation path

Figure 4.3 shows what happens between the key press and the pasted text.

```mermaid
sequenceDiagram
    participant U as User
    participant H as Hotkey hook (pynput)
    participant Wg as Widget (Qt thread)
    participant R as Recorder (PyAudio)
    participant S as stt.py (faster-whisper)
    participant A as Active app
    U->>H: hold Right Option
    H->>Wg: pressed(dictation), frontmost app captured
    Wg->>R: start 16 kHz capture
    loop every 2 s (offline only)
        Wg->>S: partial transcript of the last 8 s
        S-->>Wg: text shown on the pill
    end
    U->>H: release
    H->>Wg: released
    Wg->>R: stop, join
    Wg->>S: transcribe(audio, language)
    S-->>Wg: final text
    Wg->>A: clipboard + Cmd+V (100 ms later)
```

*Figure 4.3. Dictation from key press to pasted text.*

The hotkey listener runs in its own thread and records which application is in front at the moment of the press, before any window of Guya can take focus. The microphone is recorded at 16 kHz mono while the key is held. While recording, a background pass re-transcribes the last eight seconds every two seconds and shows the partial text on the pill, so the user can see that they are being heard; this text is display-only and is never merged into the result. On release, the whole recording is transcribed once and the result is pasted into the frontmost application through the clipboard.

Pasting was chosen over synthesised keystrokes for two reasons. One paste is Unicode-safe and instant, while typing Persian character by character through a keyboard simulator was unreliable in early prototypes. And the paste goes to whatever is frontmost at that moment: the widget never takes focus, so the user's text field is still in front. The one case where this fails is when the user has just clicked on Guya itself; the paste is then refused, the text stays on the clipboard, and the pill says so (Section 5.9).

### 4.4 The speech pipeline

The model call is wrapped in a pipeline, shown in Figure 4.4, that was tuned during daily use and then measured (Section 7.3).

```mermaid
flowchart LR
    A[16 kHz float audio] --> B[Loudness<br/>normalisation<br/>target RMS 0.1]
    B --> C[Silero VAD<br/>threshold 0.3,<br/>250 ms silence]
    C --> D[Whisper decode<br/>beam 5, per-language<br/>vocabulary prompt]
    D --> E[Hallucination filter<br/>per segment]
    E --> F{Persian?}
    F -- yes --> G[Letter forms,<br/>corrections table,<br/>colloquial forms]
    F -- no --> H[Join segments]
    G --> H
```

*Figure 4.4. The transcription pipeline in `stt.py`.*

The pipeline has one entry point, `transcribe_audio`, with a `mode` argument that selects the vocabulary prompt: the dictation prompt lists the user's usual words, the assistant prompt lists the command vocabulary, and the answer prompt, used only while a question is pending, lists nothing but the possible answers. The last two were added after the first manual test session, when short Persian answers such as «بله» and «بازش کن» were heard as unrelated words (Section 7.8). The function also takes an `overrides` dictionary that the evaluation harness uses to switch each setting back to the library default one at a time. Extracting the pipeline into its own module, so that the harness runs the very code the widget runs, was a change made for this report, and it is what made the ablation of Section 7.3 possible.

### 4.5 Command understanding

Figure 4.5 shows the path of a spoken command.

```mermaid
flowchart TD
    T[transcript] --> N[normalise<br/>digits, letter forms, punctuation]
    N --> Pn{pending question?}
    Pn -- yes/no/first.. --> X[execute or cancel the pending action]
    Pn -- a new command --> Pr
    Pn -- no --> Pr[parser: ordered chain of keyword rules<br/>+ phrase-list fallback]
    Pr --> I[intent + slots]
    I --> Sv[service: context, confirmation,<br/>selection, safety checks]
    Sv --> Ac[platform actions<br/>macOS / Windows]
    Ac --> F[reply: on-screen bubble,<br/>spoken in English, log record]
```

*Figure 4.5. The assistant path.*

**The parser** is an ordered chain of rules, and the order is the semantics. Deletion is checked first so that it can be refused before any other rule sees the sentence. Creation is checked before rename, because "make a file and name it X" contains "name it". Save and close come before browser movement. Website comes before application, and application before file, so that "go to youtube" is a website and "open word file" opens Word rather than searching for a file called "word". Each rule extracts its arguments with regular expressions written for that command in each language. If no rule fires, the utterance is compared with a list of 193 example phrases and the closest intent is taken if the similarity ratio is at least 0.82. The rules are described one by one in Section 5.6.

Two additions were made for this report, both driven by the held-out evaluation. Filler words at the edges of an utterance ("let's", "please", "again", «یه کم», «لطفاً») are stripped before the strict grammars run. And browser movement has a looser keyword fallback that requires a movement word and a direction word and refuses to fire when the sentence names a file, folder, application, window or tab. The reason for the second rule's strictness is recorded in Section 7.5: its first version scrolled the page on "shut down the computer".

**The service** keeps a small context: the current path and the five most recent ones, so that "open it again" and "rename it" work without a name, and one pending question at a time. A pending question is one of three kinds: a confirmation (rename, or "open it now?" after a file was created), a request for a missing name, or a choice among up to three search results. Figure 4.6 shows how the service moves between these states.

```mermaid
stateDiagram-v2
    [*] --> Idle
    Idle --> Idle : command executed / refused
    Idle --> AwaitYesNo : rename parsed, or file created
    Idle --> AwaitName : "rename it" without a name
    Idle --> AwaitChoice : several close matches
    AwaitYesNo --> Idle : yes → act / no → cancel
    AwaitYesNo --> Idle : fresh command → drop question, run it
    AwaitName --> AwaitYesNo : name heard → ask to confirm
    AwaitName --> Idle : clearly different command
    AwaitChoice --> Idle : first/second/third, click, or file name → open
    AwaitChoice --> Idle : cancel, or fresh command
    AwaitYesNo --> Idle : 120 s without an answer
    AwaitName --> Idle : 120 s without an answer
    AwaitChoice --> Idle : 120 s without an answer
```

*Figure 4.6. Pending-question states of the assistant service.*

Three properties of this state machine were decided deliberately. A "yes" or "no" answers the question, and a fresh command replaces it: the assistant used to insist on an answer first, which made every file creation cost an extra utterance, and the log showed users simply moving on. A question that is not answered within two minutes expires, so a "yes" spoken later can never rename something the user has forgotten. And answers to a question are interpreted in the language of the question, so "yes" spoken in English to a Persian question gets a Persian reply.

Every response from the service carries one of six statuses (Table 4.2). The widget uses the status to choose the tone of the pill and whether to show buttons.

| Status | Meaning | Widget behaviour |
|---|---|---|
| `success` | the action was carried out | green pill, reply shown for 3 s |
| `error` | not understood, refused, or failed | red pill, reply shown for 6 s |
| `needs_confirmation` | a yes/no question is pending | amber pill, bubble with Yes/No buttons |
| `needs_selection` | up to three matches are pending | amber pill, popup with clickable choices |
| `needs_input` | a name is missing | amber pill, bubble with the question |
| `cancelled` | the user said no or cancel | amber pill, reply shown for 6 s |

*Table 4.2. Response statuses.*

**Spoken filenames** need their own normaliser. Whisper hears "test six docks" for `test6.docx` and «گزارش شش ورد» for `گزارش ۶.docx`. The normaliser folds digits and number words, drops leading words such as "the" and "my", and rewrites the suffixes speech recognition produces (docs, docks, "doc x", «دکس», «ورد») into the extension. Matching is scored rather than exact, with a fixed scale (Section 5.5). A single confident match opens directly; a close race shows the choices. The rule that a partial match needs at least three characters exists because of a real bug: "open the system folder" once opened a folder named `m`.

### 4.6 Device-aware model choice

Guessing the right model from the machine's specification is unreliable: a 16 GB Mac and a 16 GB PC without a graphics card behave very differently. So the wizard measures. The algorithm is:

```
rtf_base   = time to transcribe the bundled 7 s clip with `tiny` / clip length
             (one warm-up pass, then the best of two timed passes, temperature fallback off)
for each model m:
    predicted_rtf[m] = rtf_base × RELATIVE_COST[m]
candidates = offline models the profiler allows for this RAM,
             with accuracy rank ≥ FLOOR[language]
choose the most accurate candidate with predicted_rtf ≤ 1.0
if none: recommend the online model
```

`RELATIVE_COST` is the measured real-time factor of each model on the reference machine divided by the reference probe value 0.040 (Table 7.4). The per-language floor encodes the accuracy measurement of Section 7.2: English is acceptable from `small` upward, Persian and dual need at least `large-v3-turbo`. The threshold of 1.0 means the recommended model keeps up with speech; the wizard also shows the predicted time for ten seconds of speech on each model card, so a user who prefers accuracy over speed can choose a slower one knowingly.

Two things about the earlier design were found wrong during the evaluation and fixed. The benchmark used to time the model on synthetic noise; on noise Whisper fails its own quality checks and retries at rising temperatures, so it was measuring decoder retries rather than the device, and on the development machine it recommended the online model for every language even though the same machine runs `large-v3-turbo` every day. The recommendation rule also had two latency tiers, which made it non-monotonic: a slightly slower machine could be told to run a bigger, slower model. Both are covered by tests now (`tests/test_benchmark.py`).

### 4.7 The safety model

The assistant's safety does not rest on the parser being right. Table 4.3 maps each safety requirement of Section 3.6 to the mechanism that enforces it and the module that implements it.

| Requirement | Mechanism | Where |
|---|---|---|
| SR-1 no delete | no delete method exists in the action layer; the parser recognises delete words only to refuse them, before any other rule | `parser.py`, `actions/common.py` |
| SR-2 no overwrite | `exists()` is checked before create and before rename; a text file is created with `exist_ok=False` | `actions/common.py` |
| SR-3 allowed roots | every path is `resolve()`d (symbolic links followed) and must be relative to one of the roots; search does not descend into symbolic links, hidden folders, application bundles or a fixed list of tool folders, and stops at depth 6 | `actions/common.py` |
| SR-4 app allow-list | applications are looked up in a table of eight names with fixed executables; the spoken string is never launched | `actions/macos.py`, `actions/windows.py` |
| SR-5 HTTPS host only | `safe_website_url` accepts a known name or a domain with a valid label structure and a top-level domain from a list, and returns `https://host` with nothing after it | `actions/common.py` |
| SR-6 addressed keystrokes | macOS posts key events with `CGEventPostToPid` to the process captured at key press; Windows refocuses the captured window and verifies it before sending; Guya's own bundle ids are refused as targets | `actions/macos.py`, `actions/windows.py` |
| SR-7 no shell | every `subprocess` call is a fixed argument list (`open -a`, `say`, a fixed PowerShell script); spoken text goes through stdin or a URL encoder, never a command line | both adapters |
| SR-8 confirmation | rename and "open it now?" set a pending confirmation; the action runs only from the confirmation path | `service.py` |
| SR-9 expiry | `PENDING_TIMEOUT_SEC = 120`; an expired question is cleared before any answer is interpreted | `context.py`, `service.py` |
| SR-10 sequences | every step is checked against an allow-list of five intents before the first step runs | `service.py` |

*Table 4.3. Safety requirements and their enforcement.*

The boundary is small enough to be read in full: `actions/common.py` is 513 lines. Several unit tests assert the absence of side effects, for example that nothing was opened before "yes", that nothing was renamed after "no", and that a delete request touched nothing (Section 5.13).

### 4.8 Feedback and interaction

The floating pill is Guya's face. It has five states (loading, idle, listening, processing, done) and the done state carries one of three tones, ok, warn or error. Figure 4.7 shows the transitions; Table 4.4 gives the colours and labels.

```mermaid
stateDiagram-v2
    [*] --> Loading
    Loading --> Idle : model loaded
    Idle --> Listening : hotkey pressed
    Listening --> Processing : hotkey released
    Listening --> Done_warn : too short / nothing heard
    Processing --> Done_ok : text pasted / action done
    Processing --> Done_warn : question, cancel, copied-only
    Processing --> Done_error : refused, failed, mic error
    Done_ok --> Idle : 1.5 s (dictation) or 3 s (reply)
    Done_warn --> Idle : 2.5 s to 6 s
    Done_error --> Idle : 4.5 s to 6 s
    Done_warn --> Listening : user answers by voice or click
```

*Figure 4.7. Pill states and tones.*

| State / tone | Dot colour | Label | Meaning |
|---|---|---|---|
| loading | amber | "Loading…" | model is being loaded |
| idle | grey | "⌥ Dictate · ⌘ Assist" | ready; the badge shows the language |
| listening | red, pulsing | "● Dictation listening…" / "● Assistant listening…" then the partial text | key held |
| processing | blue, breathing | "Processing…" / "Understanding command…" | transcribing or acting |
| done, ok | green | "✓ Done" or the reply | success |
| done, warn | amber | the question or notice | a question is pending, or a notice |
| done, error | red | the error | refused or failed |

*Table 4.4. Pill states, tones and labels.*

Every state pairs its colour with a text label, and every label change is mirrored into the pill's accessible description so that a screen reader can read it. A single reusable idle timer returns the pill to idle after a delay that depends on what was shown: 1.5 s for a plain "Done", 2.5 s for a notice, 4.5 s for an error, 3 s for a successful reply and 6 s for a question. The timer is re-armed on every change, because an earlier design with one fire-and-forget timer per reply let an old timer wipe a new reply early.

The pill's label holds about thirty characters and cannot wrap. Any reply longer than 28 characters, and any reply that is not a plain success, is therefore repeated in full in a **reply bubble** under the pill: a 420-pixel wrapped panel that follows the text direction (right-to-left for Persian), coloured by tone, with Yes and No buttons when a confirmation is pending. The buttons emit the literal words "yes" and "no" into the same path a spoken answer takes, so a click and a voice answer are handled by one piece of code. Search results that need a choice appear in a similar popup with up to three buttons and a Cancel. Neither window ever takes keyboard focus, so the user's document keeps it.

English replies are also spoken with the system voice. Persian replies are shown only. macOS ships 184 voices and none for Persian; the only Arabic-script voice reads Persian with an Arabic accent, and after trying it we decided that silence is better than a voice that sounds wrong to every Persian speaker. This is the limit of a zero-cost design on this platform, and it is the reason the bubble exists: during the audit it turned out that a Persian confirmation question had been cut to its first three words on the pill, and the user was answering "yes" to a question they could not read. Pressing either hotkey while an English reply is being spoken interrupts it; the dictation key does so because Guya's own voice was once recorded as part of a dictation.

### 4.9 Platform abstraction

Everything that touches the operating system goes through two adapters with the same interface (Table 4.5). The service and the parser never import a platform module, which is why they run unchanged in the tests.

| Operation | macOS | Windows |
|---|---|---|
| detect the hotkeys | pynput listener over a system event tap; Right Option and Right Command matched by key and by hardware code | low-level keyboard hook (`WH_KEYBOARD_LL`) in a thread; G and F8 by default, configurable |
| capture the target | frontmost application's bundle identifier, read on the hook thread at key press | foreground window handle, plus the focused text control |
| paste dictated text | clipboard, then Cmd+V to whatever is frontmost; refused if that is Guya | clipboard, refocus the captured window, Ctrl+V |
| open a file or folder | `open <path>` | `os.startfile` |
| open an application | `open -a <name>` from a table of candidates | `os.startfile(<exe>)` from a table |
| save, close | Cmd+S / Cmd+W posted to the captured process id; close tries the window's Accessibility close button first | Ctrl+S / Ctrl+W after refocusing and verifying the captured window |
| browser navigation | Page Up/Down, Cmd+Up/Down, Cmd+[ and Cmd+] posted to the browser's process; refused unless the captured app is one of eight known browsers | Page Up/Down, Home/End, Browser Back/Forward keys to a Chrome- or Firefox-class window |
| open a URL | into the current tab of the captured browser (Cmd+L, paste, Return, clipboard restored) or `open -a <browser> <url>` | same, with Ctrl+L |
| speak a reply | `say` for English; nothing for Persian | PowerShell speech synthesiser, first `fa-*` voice if installed; text passed on stdin as UTF-8 |
| permissions | Accessibility prompt through `AXIsProcessTrustedWithOptions`; microphone prompt by opening the stream once | administrator check for the keyboard hook |

*Table 4.5. The platform interface and its two implementations.*

The Windows adapter was written against the API documentation and the one test that exercises it runs with the operating system calls patched out. It has not been executed on a Windows machine (Section 7.9).

### 4.10 Configuration, installation and runtime layout

All settings live in one JSON file, `~/.guya/config.json`, with 27 keys (Appendix C). On every load the file is merged over the built-in defaults, so an older file keeps working after an update and simply gains any new keys. The file is written with owner-only permissions because it may hold the online API key.

Everything Guya writes at run time lives under `~/.guya`:

```
~/.guya/
├── config.json          settings (chmod 600)
├── logs/guya.log        one rotating log for all processes (2 MiB × 5)
├── logs/launcher.log    stdout and stderr of the process tree started from Guya.app
├── runtime/guya/        a copy of the package (macOS)
├── runtime/venv/        a copy of the Python environment (macOS)
├── runtime/origin       path of the checkout, for Update and Uninstall
├── rt_state.json        widget → panel, every 400 ms
├── rt_cmd.json          panel → widget, numbered commands
├── widget.lock          single-instance locks
└── control-panel.lock
```

Models are not under `~/.guya`; they live in the Hugging Face cache (`~/.cache/huggingface/hub`), which the wizard and the uninstaller both know about.

The copy of the package and environment under `runtime/` is the result of a real failure recorded in the launcher log. An application launched from the Finder is denied access to a Python environment that lives on the Desktop or in Documents, because those folders are protected by macOS privacy controls; a Terminal launch hides the problem because Terminal already has permission. The installer therefore copies the code to `~/.guya/runtime` and generates a `Guya.app` bundle that runs the copy. The bundle is a four-line shell stub with an `Info.plist` that names Guya as the process asking for the microphone and the three folders, and it is signed ad hoc so that Gatekeeper accepts it without an Apple developer account. Because the bundle, not a terminal, is the process that asks for Accessibility, the permission belongs to Guya. The panel's Update button pulls the repository, reinstalls the requirements and regenerates the bundle, which re-copies the package; Uninstall removes the settings, logs, models, runtime copy and launchers, and keeps the project folder.

### 4.11 Logging and diagnosability

The developer is not present when the user has a problem, so the log has to be enough on its own. Every process writes to one rotating file with the date and the process id in every record, which is what makes a session reconstructible afterwards. The widget logs the mode, the captured target, the audio length and the transcription time of every recording. And every assistant command produces one JSON record (Table 4.6), which is what Section 7.6 and the usage-log analyser are built from. The control panel shows the last 400 lines of the log in a dialog that refreshes every 1.5 seconds without losing the reader's scroll position, which was itself a reported bug.

| Field | Content |
|---|---|
| `transcript` | what was heard |
| `stt_language` | the badge language at the time |
| `response_language` | the language of the reply |
| `intent`, `slots`, `steps` | what the parser produced |
| `status`, `message` | the service's response |
| `path`, `options` | the file acted on, or the choices offered |
| `target_app` | the application the command was addressed to |
| `audio_seconds`, `transcription_ms`, `command_ms` | the latency split |

*Table 4.6. The per-command log record.*

---
## 5. Implementation

### 5.1 Technology stack

Table 5.1 lists every runtime dependency with the version used and what it is for. There is no PyTorch, no paid service and no compiled code of our own. Python 3.10 to 3.12 is required because PyQt6 had no wheels for newer versions at the time; the development environment runs 3.11.15.

| Component | Version | Used for |
|---|---|---|
| Python | 3.11 | everything |
| faster-whisper | 1.2.1 | offline speech recognition; pulls CTranslate2 4.8.1, the tokenizer, ONNX Runtime for the VAD, and the Hugging Face hub client for downloads |
| CTranslate2 | 4.8.1 | the inference engine; 8-bit weights on the CPU |
| PyQt6 | 6.11.0 | every window, plus `QProcess`, `QThread`, `QTimer` and `QLockFile` |
| PyAudio (PortAudio) | 0.2.14 | microphone capture |
| NumPy | 2.4.6 | audio buffers |
| pyperclip | 1.11.0 | clipboard for pasting |
| psutil | 7.2.2 | device profile (cores, memory) |
| httpx | 0.28.1 | the optional online transcription request |
| pynput (macOS) | 1.8.2 | global hotkey listener; Cmd+V synthesis |
| PyObjC: Cocoa, ApplicationServices, Quartz (macOS) | 12.2.1 | frontmost application, Accessibility permission, window close button, addressed key events |
| Groq API (optional) | `whisper-large-v3` | online transcription on the free tier |

*Table 5.1. Runtime dependencies.*

### 5.2 Code organisation and size

The repository is laid out as follows.

```
guya/                         the application package (24 modules, 11,894 lines)
  widget.py                   pill process
  stt.py                      transcription pipeline
  wizard.py  profiler.py  benchmark.py
  control_panel.py  runtime.py  config.py  logsetup.py  launcher_gen.py
  platform_macos.py  cloud_engine.py  __main__.py
  assistant/                  parser.py  service.py  normalizer.py  context.py  models.py
    commands_en.json  commands_fa.json      phrase packs (93 + 100 examples)
    actions/                  common.py  macos.py  windows.py
  assets/                     bench_speech.wav (7 s probe clip), Vazirmatn fonts
eval/                         evaluation harness (8 modules, 1,240 lines)
tests/                        136 tests (10 files, 1,598 lines)
docs/                         this report, user guide material, demo script, user-study protocol
install.sh  install.bat  "Install Guya.command"  "Install Guya.bat"  run.sh  run.bat
```

Table 5.2 gives the size of each module. The whole project is 14,906 lines of Python in 45 modules. The two largest modules are the user interfaces, which is usual for Qt code; the logic that matters for correctness, the parser, service and actions, is about 3,300 lines and is the part covered by tests.

| Module | Lines | Role |
|---|---:|---|
| `widget.py` | 2,808 | recorder, hotkeys, floating pill, reply bubble, results popup, assistant glue |
| `wizard.py` | 2,121 | eleven-page bilingual setup wizard |
| `assistant/parser.py` | 1,121 | intents and slots, Persian and English |
| `control_panel.py` | 1,017 | launcher window, settings, help, logs, maintenance |
| `assistant/service.py` | 798 | context, confirmation, selection, dispatch |
| `stt.py` | 563 | the speech-to-text pipeline shared with the evaluation |
| `assistant/actions/macos.py` | 547 | macOS adapter |
| `assistant/actions/common.py` | 513 | the safety boundary and filesystem actions |
| `platform_macos.py` | 427 | hotkeys, frontmost application, paste, permissions |
| `assistant/actions/windows.py` | 315 | Windows adapter |
| `assistant/normalizer.py` | 287 | text and spoken-filename normalisation |
| `benchmark.py`, `profiler.py` | 498 | device profile, benchmark, recommendation |
| `launcher_gen.py`, `config.py`, `cloud_engine.py` | 498 | launcher generation, configuration, online backend |
| `__main__.py`, `runtime.py`, `logsetup.py`, `context.py`, `models.py`, `__init__` files | 385 | entry point, IPC, logging, data classes |
| `eval/` | 1,240 | accuracy, ablation, intent and log evaluators, table generator |
| `tests/` | 1,598 | 136 tests |

*Table 5.2. Module sizes.*

### 5.3 Start-up sequence and threads

The widget's `main()` runs a fixed sequence: enable the fault handler and route unhandled exceptions to the log; check the Accessibility permission and open the microphone once so that macOS asks for both permissions; load the Whisper model (or construct the online model object); only then import the Qt library; take the single-instance lock; build the window; set the macOS activation policy to *accessory*, so that the pill shows without a Dock icon or menu bar; and show the pill collapsed at the top centre of the screen.

Model loading chooses the device and precision at run time. On macOS there is no GPU backend for faster-whisper, so the model runs on the CPU with 8-bit weights and all cores. On Windows the code probes `nvcuda.dll` through `ctypes`; if a CUDA device is found the model runs there in 16-bit floating point, and if initialisation fails it falls back to the CPU. If the model files are not in the cache, they are downloaded in a subprocess with a ten-minute timeout.

At run time the widget has four threads and four timers (Table 5.3). The hotkey hook and the recorder are plain threads; transcription and assistant commands run in Qt threads so that their results arrive on the interface thread as signals. Nothing that can block runs on the interface thread, which is why the pill keeps animating while the model works.

| Thread or timer | What it does | Interval |
|---|---|---|
| hotkey hook thread | pynput listener (macOS) or low-level keyboard hook (Windows); captures the frontmost application at key press | event-driven |
| recording thread | reads 1,024-sample chunks (64 ms) from PortAudio into a buffer | while the key is held |
| partial transcriber thread | transcribes the last 8 s of the buffer and shows it on the pill; offline dictation only | every 2.0 s |
| transcription `QThread` | the final pass over the whole recording | once per release |
| assistant `QThread` | `service.handle(text)` | once per command |
| animation timer | the pill's width, glow and dot animation | 33 ms (30 fps) |
| runtime timer | publishes state to the panel, applies its commands, checks the parent process | 400 ms |
| idle timer | returns the pill to idle after a reply or notice | 1.5 to 6 s, single-shot |
| paste delay | between "Done" and the paste keystroke | 100 ms |

*Table 5.3. Threads and timers of the widget.*

### 5.4 The speech-to-text module

`stt.py` is 563 lines and has one public function, `transcribe_audio`. Its stages run in the order shown in Figure 4.4; Table 5.4 lists the decoding settings against the library defaults.

**Loudness normalisation.** The float audio is scaled so that its root-mean-square level becomes 0.1, with the gain capped at 30 and the result clipped to ±1. Silence (RMS below 10⁻⁶) is left untouched. The intended user speaks quietly and the microphone is a laptop's; without this stage the VAD dropped the ends of sentences.

**Voice activity detection.** faster-whisper's Silero VAD is enabled with a speech threshold of 0.3 instead of 0.5, a minimum silence of 250 ms instead of 2,000 ms, 500 ms of padding around each speech region, and a minimum speech region of 80 ms. The lower threshold and shorter gap keep the pauses inside a slow Persian sentence from splitting it; Section 7.3 shows that the splitting costs accuracy on the small model but not on the shipped one.

**Language and prompt.** For Persian and English the language token is fixed and the sampling temperature is 0 with no fallback. In dual mode the language is left to the model, per-segment detection is enabled, and a short temperature ladder (0, 0.2, 0.4, 0.6) is allowed, because mixed-language audio fails the quality checks more often. Each language has a vocabulary prompt: a comma-separated list of words the user says often (colloquial cue words such as «خب», «میخوام», «چجوری», technical terms, brand names, «فایل», «پوشه», «گزارش»). The prompt is a list rather than sentences because Whisper will happily transcribe a prompt sentence as if it had heard it. faster-whisper keeps only the last 223 prompt tokens, and an earlier 298-token Persian prompt was silently losing its first 75 words; the current one measures 214 tokens with the model's tokenizer and the code comment says so, so that nobody adds words without re-measuring.

**Decoding.** Beam search with 5 beams, `best_of` 5, a no-speech threshold of 0.5 instead of 0.6, and no repetition penalty. The penalty was 1.2 from the first prototype until September 2026, as the standard remedy for Whisper's repetition loops; the ablation of Section 7.3 showed that it made the decoder end sentences early and cost the small model 9.6 points of English WER, so it was removed. Loop protection is now the hallucination filter and the rule that recordings shorter than five seconds are decoded without conditioning on previous text.

| Setting | Guya | faster-whisper default |
|---|---|---|
| beam size / best of | 5 / 5 | 5 / 5 |
| temperature | 0 (fa, en); 0, 0.2, 0.4, 0.6 (dual) | 0 to 1.0 in six steps |
| VAD filter | on | off |
| VAD threshold / min silence / padding / min speech | 0.3 / 250 ms / 500 ms / 80 ms | 0.5 / 2,000 ms / 400 ms / 0 |
| no-speech threshold | 0.5 | 0.6 |
| repetition penalty | 1.0 (was 1.2 until September 2026) | 1.0 |
| condition on previous text | off for recordings under 5 s | on |
| initial prompt | per-language vocabulary list (fa 214 tokens, en 64, dual 97) | none |
| compression ratio / log-probability thresholds | 2.4 / −1.0 (default) | 2.4 / −1.0 |

*Table 5.4. Decoding settings.*

**Hallucination filter.** Each segment of the output is dropped if it is empty or shorter than two characters, consists only of punctuation, is a single repeated character, or has five or more words of which one makes up more than 60% (the Persian habit of doubling a word for emphasis, «خیلی خیلی خوب», stays under that limit). A list of sixteen phrases that Whisper produces on silence («ساب اسکرایب», "thanks for watching", «زیرنویس توسط», "www.") is also removed, but only when the segment is at most one word longer than the phrase, because an earlier version that removed single words such as «ترجمه» deleted real sentences.

**Persian post-processing.** Three stages run on Persian text (and on the Persian parts of dual-mode text). First, six Arabic letter forms are mapped to their Persian equivalents, diacritics are removed, and the spacing around Persian punctuation is fixed without touching times and version numbers («ساعت 10:30»). Second, a table of 64 corrections is applied with whole-word matching, longest key first. The entries come from months of use and fall into recognisable groups: names and places the user says («جاباما»), similar-sounding letter confusions (ب/پ, د/ت, ز/ذ), words the model splits or merges («پارامت های» → «پارامترهای», «محمد رضا» → «محمدرضا»), and technical and brand terms («اپ دیت» → «آپدیت», «واتس اپ» → «واتساپ»). Whole-word matching is essential: an earlier substring version turned «مدیریت» into «مدیرت». Third, 43 regular-expression rules turn the formal verb forms Whisper prefers back into the colloquial forms the speaker used: «می‌خواهم» → «میخوام», «می‌دانم» → «میدونم», «می‌توانم» → «میتونم», «اصلاً» → «اصن», «آنها» → «اونا», «چگونه» → «چجوری». English text is not post-processed.

**Modes and overrides.** The `mode` argument selects the prompt: `dictation` (default), `assistant` (the command vocabulary: yes, no, cancel, the ordinals, open, close, save, find, create, file, folder, rename, scroll, the site names, the browsers, the language names), or `answer` (only the words that can answer a question: «اول، دوم، سوم، یک، دو، سه، لغو، بله، نه»). The widget passes `assistant` for command recordings and `answer` when a question or a result list is pending. The `overrides` dictionary is merged over the decoding arguments and exists only for the evaluation harness; the widget never passes it.

**Online backend.** When the model object is the online one, the same function sends the audio as a 16-bit WAV to Groq's transcription endpoint (`whisper-large-v3`, 30-second timeout, the language field set for Persian or English and omitted for dual), and applies the same hallucination filter and post-processing to the result. Connection, timeout, authentication and rate-limit errors are mapped to short messages for the pill. No prompt or VAD settings are sent.

### 5.5 Spoken filenames

Filenames arrive from the recogniser as speech: "test six docks", «آزمون شیش دکس», "report doc x". `normalize_spoken_filename` turns them into something that can be compared with real names, in five steps: character normalisation (lower case, digits, Arabic letter forms, diacritics, punctuation and separators to spaces); spoken numbers from 0 to 99 in both languages, including colloquial Persian forms («یه», «شیش», «پونزده»); removal of leading words such as "the", "my", «فایل», «پوشه»; rewriting of the trailing type words ("word file", «سند ورد») and the spoken extensions ("docs", "docks", "doc x", «دکس», «ورد» → `docx`; "text", «تکست» → `txt`); and splitting into a stem and an extension.

`filename_match_score` then compares a spoken query with a candidate name and returns a score on a fixed scale (Table 5.5). The scale was tuned by hand against real mistakes, and the search keeps candidates scoring at least 0.58, shows at most three, and opens without asking only when the best is clearly ahead (a single match at 0.90 or above, or a best of 0.86 with a margin of 0.12 over the runner-up, or an exact match with no near-exact rival).

| Case | Score |
|---|---:|
| full name identical | 1.00 (exact) |
| stem identical, same or no extension | 0.98 (exact) |
| stem identical, different extension | 0.90 |
| otherwise, similarity ratio of the stems | ratio × 0.76 |
| the shorter stem (≥ 3 characters) is a prefix of the other | at least 0.86 |
| the shorter stem (≥ 3 characters) is contained in the other | at least 0.82 |
| share of the query's words present in the name | at least share × 0.80 |
| extension equal / different | +0.04 / −0.08 |
| cap for any non-exact match | 0.97 |

*Table 5.5. Filename match scale.*

### 5.6 The command parser

`parse(text)` first detects the language (any Persian character makes the utterance Persian), normalises the text, and checks whether the whole utterance, before or after filler stripping, is one of the confirmation or cancellation phrases (14 and 12 in English, 17 and 16 in Persian). Then it looks for a sequence: the text is split only on explicit connectors ("then", "and then", «بعد», «سپس», and a bare "and" or «و» only when followed by a verb such as save, close, search, go or visit), at most three parts, and each part is parsed on its own; if every part is understood the result is a sequence, otherwise the whole utterance is parsed as one command. A search step directly after "open Chrome" becomes a web search in Chrome, and a website or search step inherits the browser that the previous step opened; this rule came from the third manual test, where "open Chrome and search for the weather" opened Safari.

Filler stripping removes, from the edges of the utterance only, any of 30 English and 24 Persian words and phrases ("please", "just", "let's", "can you", "a bit", «لطفاً», «یه کم», «دوباره», «میشه», «بی زحمت»), longest first and repeatedly. It is applied at the edges only because a filler word in the middle of a name («گزارش دوباره») is part of the name.

The single-command parser is a chain of eighteen rules tried in order (Table 5.6). Each rule is a whole-word keyword test followed by slot extraction with a regular expression for each language.

| # | Rule | Fires on | Guard |
|---|---|---|---|
| 1 | delete refused | any of 9 delete words, unless another verb comes first | "open the trash folder" and "rename it to remove" stay ordinary commands |
| 2 | bare application name | the whole utterance is one of 32 application aliases | |
| 3 | language switch | at most six words matching a switch frame ("switch to Persian", «برو انگلیسی», "dual") | a bare language name alone is not a switch, so "english" while dictating a name does nothing |
| 4–7 | create Word document, folder, text file, plain file | a create verb (8 in the two languages) plus a type word | "new" and "build" are not create verbs, because "open the new folder" and "open the build folder" are open requests; creation is checked before rename because "make a file and name it X" contains "name it" |
| 8 | rename | 18 rename verbs or the frames "change … name", «اسمش رو بذار», «اسم جدیدش بشه» | «اسم» and «نام» must be whole words, so «نامه» (a letter) is never a rename; the contraction «اسمشو» is |
| 9 | save / save as | 7 save verbs; "save … as" or a folder name means Save As, which is refused with an explanation | |
| 10 | close | 7 close verbs | |
| 11 | browser navigation | 20 English and 21 Persian strict patterns, then the keyword fallback | the fallback needs a movement word and a direction, at most seven tokens, and no word that names a file, folder, application, window, tab or the computer |
| 12 | open website | "go to", "visit", «برو به سایت» with a known site name (56 spellings) or a spoken domain | a domain counts only if the raw transcript contains the dot or the word "dot"/«دات»; otherwise "open note app" would be a website |
| 13 | open application | an open verb and an application alias | "open the word file report" is a file, "open word file" is Word |
| 14 | find and open | "find X and open it", «X رو پیدا کن و بازش کن» | |
| 15 | web search / file search | 16 search verbs; a web search if the sentence names the web, Google or a browser, with five Persian verb-first patterns («توی گوگل سرچ کن X», «X رو گوگل کن») | |
| 16 | open file or folder | an open verb; "open it", «بازش کن» give no name and use the remembered path | |
| 17 | phrase-list fallback | the closest of 193 example phrases at similarity ≥ 0.82, then the slot extractor of that intent | a website from this path may omit the dot ("visit github com") |
| 18 | unknown | | |

*Table 5.6. Parser rules in order.*

Three helper functions serve the service while a question is pending. `leading_answer` accepts "yes" or "no" followed by more words ("no, don't rename it", «نه اسمش رو عوض نکن»), trying the cancel phrases first. `fuzzy_answer` accepts a single misheard word as an answer when it is at least 0.75 similar to a yes or no word, because Whisper writes «بیلی» for «بله». `fuzzy_selection_index` does the same for "first", "second", "third" at 0.5 with a margin of 0.1 over the runner-up, because it wrote «عوال» and «آبال» for «اول». All three are used only when a question is actually pending, so a misheard word can never start an action on its own.

### 5.7 The assistant service

`handle(text)` runs the flow of Figure 4.6. It first clears a pending question that is older than 120 seconds. If a result list is pending, the utterance is tried as a selection: an index word, a fuzzy index, a click, or the name of one of the options (scored with the filename scale, accepted at 0.86 with a 0.12 margin); a clearly different command drops the list. If a confirmation is pending, `leading_answer` and `fuzzy_answer` decide; a confirmation runs the stored action, a cancellation reports what was left unchanged ("Okay. report.docx was created and left closed."), and a fresh command from a list of sixteen intents replaces the question. If a name is pending, the utterance is taken as the name after eight English and twelve Persian prefixes ("the new name should be", «اسمش رو بذار») are removed, unless it is clearly a different command. Otherwise the utterance is parsed and dispatched.

`_dispatch` is a table from intent to handler. Creation calls the action and then asks whether to open the result. Opening with a name checks the remembered paths first and then searches. Search never opens anything; it remembers the best match and says how to open it. A sequence is validated in full before its first step: every step must be one of open application, open website, web search, save or close, and a sequence with any other step is refused as a whole. Rename finds the target (a spoken old name, or the remembered path), asks for the new name if it was not given, and then asks for confirmation with both names shown. Delete and Save As are answered with a fixed explanation.

Every message exists as an English and a Persian string written side by side in the code, and the service picks one by the language of the utterance, or, for an answer, by the language of the question. Ranking of search results adds a small recency bonus (0.03 minus 0.005 per position) to paths the user touched recently, so that "open the report" prefers the report opened a minute ago over an older one with the same name.

### 5.8 Desktop actions and platform adapters

`SafeDesktopActions` implements the filesystem actions once for both platforms. Its allowed roots default to Desktop, Documents and Downloads and are resolved at construction; the default directory for new files is Documents. Every path that reaches an action is resolved again and must be relative to one of the roots; a symbolic link pointing outside resolves outside and is rejected, and a link loop, which raises an exception on resolution, is treated as disallowed.

**Search** walks the roots with `os.walk` without following links, skipping hidden folders, application bundles and nine tool folders (`node_modules`, `venv`, `__pycache__`, `Library` and so on), to a depth of six and at most 20,000 candidates per root. Folder names a person might really use, such as `build`, `out` or `dist`, are deliberately not skipped: an earlier list that skipped them hid the user's own folders, and a skipped folder is still offered as a candidate even though its contents are not searched. Every name is scored with the filename scale, candidates below 0.58 are dropped, and the top twenty are ranked by score, exactness, name length and path. Queries that are too generic ("the file", «چیز») or shorter than two characters (unless they are a digit) are rejected before the walk. Each search writes one diagnostic record to the log with the query, the number of names inspected, the time taken and the top five candidates.

**Create** sanitises the spoken name (invalid characters removed, length capped at 180), appends `.docx` or `.txt` when missing, refuses an existing name, and writes the file. A Word document is produced without any Word library: it is an Office Open XML package, a zip with three parts (`[Content_Types].xml`, `_rels/.rels`, `word/document.xml` containing one empty paragraph), written with the standard `zipfile` module. Word, Pages and LibreOffice open it. This kept a dependency out of a project whose point is to run anywhere for free.

**Rename** keeps the old extension when the new name has none, refuses an existing destination, and calls `Path.rename`. Confirmation is the service's job, not the action's.

**Websites** go through `safe_website_url`: a known name is looked up in a table of 19 spellings for 7 sites; anything else must be at least two labels of letters, digits and hyphens with a top-level domain from a list of 14, with the usual length limits, and becomes `https://host`. Paths, queries, ports and schemes are not accepted.

**The macOS adapter** opens files with `open` and applications with `open -a` from a table (word → Microsoft Word, Pages, LibreOffice in that order; browser → Safari, Google Chrome; and so on). Keystrokes are Quartz keyboard events posted with `CGEventPostToPid` to the process id resolved from the bundle identifier captured at key press; the docstring records why a global keyboard controller was rejected: a global event can be delivered back to Guya if macOS changes focus at the wrong moment, and a process-addressed event cannot. Close first asks the Accessibility API for the focused window's close button and presses it, falling back to Cmd+W. Browser navigation is refused unless the captured application is one of eight known browsers, and then posts Page Up, Page Down, Cmd+Up, Cmd+Down, Cmd+[ or Cmd+] to it. A URL is opened in the current tab when the captured browser matches the requested one: the clipboard is saved, the URL copied, Cmd+L, Cmd+V and Return posted with short pauses, and the clipboard restored; otherwise the URL is handed to `open -a` with the requested or captured browser. English replies are spoken with `say`; Persian replies are not spoken at all.

**The Windows adapter** uses only the standard library `ctypes` bindings of `user32`: `os.startfile` for files and applications, a low-level keyboard event after refocusing the captured window and verifying that the refocus worked, Home, End, Page Up, Page Down and the browser back and forward keys for navigation, and the current-tab navigation with Ctrl+L. Speech uses the .NET speech synthesiser through PowerShell, choosing the first installed Persian voice if there is one; the text is written to the process's standard input as UTF-8 rather than placed on the command line, because the command line turned out to treat everything after the script as more script and nothing was ever spoken. This adapter has one unit test, which patches out the operating system calls, and has not been run on Windows.

### 5.9 The widget

The pill is a frameless, always-on-top window that never accepts focus, drawn entirely with `QPainter`: a 40-pixel circle when collapsed and a 280 by 42 pixel capsule when expanded (360 in dual mode), placed 18 pixels from the top of the screen and draggable. On macOS the usual `Tool` window type is deliberately not used, because a tool window there is a panel that hides whenever the application is not active, which would defeat an always-visible status. The expanded pill holds a status dot, the label, an on/off toggle, the language badge and a collapse chevron; the collapsed circle shows the dot and the badge. The width animates towards its target at 30 frames per second, and the listening state pulses its dot and glow.

The label is drawn without wrapping, which is what makes the reply bubble necessary (Section 4.8). The badge cycles Persian, English and dual on click and is locked to the offline language when the online backend is active in dual mode. A right-click menu offers the same language switch and Quit.

The bubble and the results popup are separate non-activating windows styled with Qt style sheets: a dark panel with a one-pixel border, 14-pixel text, and buttons that are at least 96 pixels wide with the teal accent of the wizard. Both position themselves under the pill, clamped to the screen, and move above it if there is no room. Both take no keyboard focus. A click on Yes, No, an option or Cancel first interrupts any speech and then feeds the corresponding word into the assistant exactly as if it had been spoken.

Every path that used to fail silently now shows a notice through one function: "Too short, hold the key while you speak" when the recording is under 0.4 s; "Microphone error, check that only one Guya is running" when PortAudio could not open the device, which is what a second running copy, a revoked permission or a device lost after sleep all look like; "Nothing heard, please try again" on an empty transcript; "Copied! Press ⌘V to paste" when the paste was refused. The error notices stay for 4.5 seconds because the first version overwrote them on the next line and they were never seen.

The widget also handles the self-target problem. After the user clicks the pill or a result button, Guya itself is the frontmost application, so the next command would be addressed to Guya and refused; six of the first 41 logged commands failed that way. The widget now remembers the last real target and falls back to it when the captured target is Guya. The paste routine still checks the frontmost application at paste time and leaves the text on the clipboard if it is Guya.

Every label change is mirrored into the pill's accessible description, and the bubble, its buttons and each result option have accessible names, so VoiceOver can read them; for Persian users the label is the only feedback channel.

### 5.10 Wizard, profiler and benchmark

The wizard is a `QStackedWidget` of eleven pages with a seven-step strip, translated into Persian and English with 170 strings each and mirrored right-to-left for Persian. It offers an easy path and an advanced path. In both, the language page comes first; then a loading page runs the device profile (processor, memory, GPU) and the benchmark as a subprocess with a 75-second safety timeout. The easy path then shows a single summary page with a "Change" button next to each choice; the advanced path walks through the device page (with editable specifications), the mode page (offline, online, dual, each with its pros and cons and a plain statement of where the audio goes), the setup page (model cards or the online-key panel with a Test button that sends one second of noise to the API), the key page, and a review page. Finishing writes the configuration, creates the launcher, and, if the chosen model is not in the cache, shows a download page that polls the cache folder's size every half second against the known model size, with pause, resume and retry.

The profiler decides which tiers a machine may run at all from its memory (the large tier from 8 GB or on Apple silicon, medium from 6 GB, small always) and marks the online model as an option. The benchmark runs as `python -m guya.benchmark` so that no Qt is loaded, times the `tiny` model on the bundled seven-second speech clip with temperature fallback off, takes the best of two runs after a warm-up, and prints the base real-time factor. The recommendation then follows the algorithm of Section 4.6 with the constants of Table 5.7.

| Constant | Value |
|---|---|
| probe model, clip | `tiny`, 7.0 s of English speech |
| reference probe RTF | 0.040 (three idle runs: 0.0398, 0.040, 0.040) |
| relative cost tiny / base / small / medium / large-v3-turbo / large-v3 | 2.0 / 1.5 / 5.5 / 10.0 / 8.25 / 16.5 |
| threshold | predicted RTF ≤ 1.0 |
| floor: English / Persian / dual | small / large-v3-turbo / large-v3-turbo |
| latency shown on cards | predicted RTF × 10 s |

*Table 5.7. Benchmark constants.*

### 5.11 Control panel

The control panel is the everyday window: a 540 by 780 pixel window with a circular power button, a status line with the uptime, a permission banner that appears when the widget reports a missing Accessibility or Microphone permission (with a button that opens the right pane of System Settings), and three tabs. The Controls tab is live: it shows the widget's state as reported every 400 ms and offers on/off switches for Guya and the assistant, the backend switch in dual mode, and the language, each sending a numbered command to the widget. The Settings tab shows the mode, the model, whether an online key is set and the two hotkeys, each with a Change button opening a modal; a change saves the configuration and restarts the widget. The Help tab is a bilingual card with the two keys, the common commands, the browser commands, choices and confirmations, and the safety limits. A maintenance row offers Re-run Setup (which runs the wizard as a subprocess while the panel hides), Update (a `git pull` and `pip install` in a console dialog, followed by regeneration of the launcher so that the runtime copy is refreshed), Open Logs (the last 400 lines of the log, refreshed every 1.5 seconds without disturbing the reader's scroll position) and Uninstall (a confirmation, then removal of the settings, logs, downloaded models, runtime copy and launchers, keeping the project folder).

![Settings tab of the control panel](img/panel-settings.png)

*Figure 5.1. The Settings tab: mode, model, online key and the two hotkeys, each with a Change button.*

![Help tab of the control panel](img/panel-help.png)

*Figure 5.2. The bilingual Help tab.*

### 5.12 Installer, launcher and logging

`Install Guya.command` is the macOS installer. It looks for Python 3.10 to 3.12 and, if Homebrew is present, installs Python 3.11 with it; otherwise it opens a short setup page and the python.org download. It installs PortAudio through Homebrew, creates the virtual environment under `~/.guya/runtime/venv`, installs the requirements, creates `Guya.app` through `launcher_gen`, and opens it. `install.sh` does the same without the guidance, for use from a terminal, and `run.sh` starts Guya from whichever environment exists. `Install Guya.bat` mirrors the flow on Windows with `py` launcher detection, `winget` installation of Python if needed, and a retry of PyAudio through `pipwin`; it has not been executed on Windows.

`launcher_gen.create_launcher()` copies the package to `~/.guya/runtime/guya` (ignoring caches), records the checkout path in `runtime/origin`, copies the environment if the runtime has none, and writes the bundle: a four-line shell stub that changes into the runtime directory and runs `python -m guya` with its output appended to `launcher.log`, and an `Info.plist` with the bundle identifier `com.guya.app`, the microphone and folder usage descriptions, and no `LSUIElement`, so that the application keeps a normal Dock icon and the user can see it is running. The bundle is signed ad hoc and registered with Launch Services. On Windows the launcher is a `Start Guya.vbs` that starts `pythonw.exe` without a console.

Logging is set up once per process by `logsetup.setup_logging()`: one rotating file, 2 MiB with five backups, the format `time [level] pid=N message`, the noisy HTTP and hub loggers raised to warning level. This module was added in September because until then only the widget configured logging and every line from the panel and the wizard was lost.

### 5.13 Testing strategy

The tests are organised by layer and run with the standard `unittest` runner in about a quarter of a second, with no microphone, model, network or display:

```
$ python -m unittest discover -s tests -t .
Ran 136 tests in 0.227s
OK
```

Table 5.8 lists the files. Three kinds of test are worth pointing out. **Fakes at the platform boundary**: the service tests run against a `FakeDesktopActions` that records what would have been opened or spoken, so a test can assert both that a file was created on disk (in a temporary directory) and that nothing was opened before "yes". **Absence assertions**: several tests assert that no side effect happened, which is where the safety requirements are pinned; for example that an unrecognised command runs no action, that a delete request changes nothing, and that a sequence with a disallowed step runs none of its steps. **Regression tests from real failures**: every defect found by the September code review and by the three manual test sessions became a test that reproduces the original phrasing, so that "open word file", «اسمشو بذار گزارش نهایی» and "shut down the computer" keep doing what they should.

| File | Tests | What it pins |
|---|---:|---|
| `test_assistant_parser.py` | 15 | word variants, bilingual names, rename forms, selection words, sequences, and that every phrase-pack example maps to its own intent |
| `test_assistant_parser_robustness.py` | 19 | filler words, "new", spoken domains, Persian rename false positives, delete refusal, web search forms |
| `test_review_regressions.py` | 26 | every regression found by the review and the manual test sessions |
| `test_assistant_normalizer.py` | 5 | number and extension homophones, compound numbers, one-character candidates |
| `test_assistant_service.py` | 23 | confirmation, selection, context, sequences ordered and limited, several assert that no action happened |
| `test_assistant_service_pending.py` | 8 | non-modal questions, expiry, refusals |
| `test_assistant_actions.py` | 18 | the filesystem boundary, no-overwrite rename, DOCX generation, addressed keystrokes with the OS mocked, no Arabic voice for Persian |
| `test_platform_macos.py` | 3 | hotkey recognition (run on macOS only) |
| `test_benchmark.py` | 6 | calibration on the reference machine, per-language floor, monotonic recommendation |
| `test_eval_wer.py` | 13 | the scorer behind every accuracy number |

*Table 5.8. The test suite.*

The evaluation scripts double as tests of a different kind: the held-out intent evaluator runs in under a second and could be run in continuous integration, and `report_tables.py` re-scores every stored hypothesis with the current scorer each time it runs, so the tables in Chapter 7 and the raw result files cannot disagree.

### 5.14 Development history

The project was developed in four phases between June and September 2026 (Table 5.9). The repository has 52 commits, concentrated on eight working days, because most of the work was done in long sessions and committed when a milestone was reached.

| Period | Milestone | Commits |
|---|---|---|
| 5–6 June | M1 dictation widget with configuration; M2 setup wizard and device profile; M3 benchmark-based recommendation; M4 online fallback through Groq; dual mode with a backend switch on the widget; first fix of the paste target (stale frontmost application) | 17 |
| 20 June | project proposal in English and Persian; one-double-click installers for both platforms; easy and advanced wizard paths; Calm Teal theme and Vazirmatn fonts; `Guya.app` bundle; control panel with live two-way sync, tabs and logs; accuracy harness (WER, CER, RTF) | 17 |
| July | proposal approved; the assistant designed and written offline (parser, service, actions for both platforms, phrase packs, first five test files, scope document, spoken evaluation checklist) | |
| 17 August | assistant version 1 committed: 31 files, 5,708 lines | 1 |
| 5 September | evaluation sprint: FLEURS test set, scorer rewrite, `stt.py` extraction, held-out intent set and evaluator, usage-log analyser; visible errors, reply bubble, safer targets, calibrated benchmark; filler-tolerant parser and non-modal questions; report chapters; systematic review of the day's changes with 27 defects fixed and pinned by tests; repetition penalty removed; final tables | 9 |
| 9–11 September | microphone error notice, orphan exit, single instance; three manual test sessions and their fixes (command-vocabulary prompt, Yes/No buttons, language switch by voice, Persian web search, colloquial numbers, browser inheritance, misheard choice words) | 5 |
| 13 September | report in the B.Sc. layout, HTML renderer, Persian report | 3 |

*Table 5.9. Development timeline.*

Three iterations changed the design rather than just fixing it. The first was the discovery, in June, that a Finder-launched application could not read a virtual environment on the Desktop, which produced the runtime copy and the bundle of Section 4.10. The second was the usage log of July and August, which showed that a good share of the failures were not misrecognition at all: six of 41 commands were refused because Guya itself was the frontmost application, and users moved on from unanswered questions instead of answering them. That led to the non-modal question design of Section 4.5 and the target fallback of Section 5.9. The third was the evaluation of September, which turned several beliefs into measurements and reversed two of them: the repetition penalty was hurting, and the benchmark was measuring the wrong thing. Chapter 7 gives the numbers.

### 5.15 Course concepts applied

Guya is an application project, but almost every part of it rests on material from the computer engineering curriculum. Table 5.10 lists the concepts that were actually used, with the section where each appears, so that the connection between the coursework and the code is explicit.

| Course area | Concept | Where it is used in Guya |
|---|---|---|
| Operating systems | processes and child processes; inter-process communication; threads and a lock-protected buffer; lock files for mutual exclusion; the platform permission model | the panel–widget split and its file-based IPC with sequence numbers (4.2); the recorder thread and the Qt worker threads (5.3); `widget.lock` and `control-panel.lock`; the macOS privacy controls that forced the runtime copy (4.10) |
| Computer architecture and performance | CPU-bound inference; 8-bit quantisation; using all cores; measuring with warm-up and best-of-n; real-time factor as a throughput measure | CTranslate2 int8 on the CPU (2.2); the benchmark's warm-up pass and best of two runs (5.10); the cost-ratio calibration (7.4) |
| Algorithms and data structures | edit distance by dynamic programming; sequence similarity; ranking with tie-breaks; bounded tree traversal | WER and CER (2.3, `eval/wer.py`); the filename match scale and the fuzzy fallbacks built on `SequenceMatcher` (5.5, 5.6); result ranking with a recency bonus (5.7); the depth- and count-bounded search walk (5.8) |
| Formal languages and automata | regular expressions as a grammar; tokenisation and normalisation; an ordered rule chain as a priority grammar; finite state machines | the parser's 18 rules and their slot extractors (5.6); the normaliser (5.5); the pending-question and pill state machines (4.5, 4.8) |
| Artificial intelligence and machine learning | encoder–decoder transformers; language and task tokens; beam search and temperature sampling; prompts as prior context; a small neural voice activity detector; evaluation with a held-out set, ablation and corpus-level metrics | Whisper through faster-whisper (2.1); the decoding settings (5.4); the Silero VAD (2.5); the whole of chapter 7 |
| Signal processing | sampling at 16 kHz, 16-bit mono PCM; RMS level and gain with clipping; the log-mel spectrogram front end | audio capture (5.3); loudness normalisation (5.4); Whisper's input (2.1) |
| Software engineering | requirements with identifiers and traceability; layered architecture with one-way dependencies; fakes at the boundary and absence assertions; regression tests from real failures; configuration merging; logging designed for diagnosis; version control history | chapter 3; 4.1; 5.13; 4.10; 4.11; 5.14 |
| Programming languages and systems programming | foreign-function calls into the Win32 API through `ctypes`; the Objective-C bridge for macOS APIs; writing a file format from its specification with the standard library | the Windows adapter (5.8); PyObjC and Quartz key events (5.8); the three-part DOCX package (5.8) |
| Computer networks | HTTP multipart upload; timeouts and error classes; API keys and their protection | the online backend (5.4); the owner-only configuration file (4.10) |
| Human–computer interaction | push-to-talk against wake words; feedback states that pair colour with text; target size; non-modal questions; the System Usability Scale | 2.7; 4.8; 4.5; Appendix D |
| Security | allow-lists over free text; path containment with symbolic-link resolution; no shell execution; least privilege | the safety model (4.7) |

*Table 5.10. Concepts from the curriculum and where they are applied.*

Two of these deserve a comment. The evaluation methodology of chapter 7 (a fixed held-out set, one variable changed at a time, corpus-level metrics with the same normalisation on both sides) was the part of the coursework that changed the project most, because it reversed two decisions that had been taken on intuition. And the operating-systems material turned out to matter in a desktop application more than expected: the two hardest bugs of the term, the orphaned widget holding the microphone and the Finder-launched application denied its own environment, were process-model and permission problems, not speech problems.

---
## 6. User guide

This chapter is written for the person who will use Guya, or the family member who installs it for them. It repeats nothing from the design chapters and can be read on its own.

### 6.1 Installing

Download or clone the project folder, then double-click the installer: `Install Guya.command` on macOS (the first time, right-click it and choose Open, because it is not from the App Store), or `Install Guya.bat` on Windows. The installer finds Python, or helps you install it, prepares everything, and opens the setup wizard. On macOS the first run asks for two permissions, Microphone and Accessibility; both are needed, the first to hear you and the second to press keys on your behalf. Nothing is sent anywhere: the speech model is downloaded once (about 1.5 GB for the recommended model) and after that Guya works without internet.

### 6.2 First run: the setup wizard

![Wizard welcome](img/wizard-welcome.png)

*Figure 6.1. Wizard welcome.*

The wizard asks three things. Which languages you speak (Persian, English, or both); this decides which speech model is acceptable. Then it measures your computer for a few seconds and recommends how to run: offline with a model that keeps up with your voice, online through a free service if the computer is too slow for the model Persian needs, or both. Then it shows what it chose and a button to install. Easy mode does all of this on one page with a Change button next to each choice; Advanced mode walks through the same choices one page at a time.

![Wizard language choice](img/wizard-language.png)

*Figure 6.2. Wizard language choice.*

At the end the wizard creates a `Guya` launcher (Guya.app on macOS, Start Guya on Windows). From then on you only ever double-click that.

### 6.3 Every day

![Control panel](img/panel-controls.png)

*Figure 6.3. Control panel.*

Double-click Guya. The control panel opens and turns Guya on; a small round pill appears at the top of the screen. The pill is Guya's face: grey when idle, red while listening, blue while thinking, green when done, amber when it has a question, red-tinted when something failed. The two-letter badge on it (FA, EN or DUAL) is the language it is listening for; click it to change, or say a language command (Section 6.7).

You can close the control panel window only by turning Guya off; while Guya is on, keep the panel open or minimised.

### 6.4 Dictation

Hold **Right Option (⌥)** on macOS, or **G** on Windows, speak, and release. While you speak, the pill shows the words it has heard so far; when you release, the whole sentence is written into whatever program is in front, wherever the cursor is. Speak naturally in whole sentences; the model is better on a full sentence than on single words. If the text does not appear, it is on the clipboard: press ⌘V (Ctrl+V on Windows). That happens when Guya's own window was in front, and the pill says so.

### 6.5 Commands

Hold **Right Command (⌘)** on macOS, or **F8** on Windows, say one command, release. Guya answers on the pill and, if the answer is long or a question, in a bubble under it. English answers are also spoken; Persian answers are shown only, because the Mac has no Persian voice.

| You want to | Say (English) | بگویید (فارسی) |
|---|---|---|
| create a Word file | Create a Word file named report | یه فایل ورد به اسم گزارش بساز |
| create a text file or folder | Make a text file called notes · Create a folder named photos | یه فایل متنی به اسم یادداشت بساز · یه پوشه به اسم عکس‌ها بساز |
| open a program | Open the calculator · Open Chrome | ماشین حساب رو باز کن · کروم رو باز کن |
| find a file or folder | Find my report file · Where is the photos folder | فایل گزارش رو پیدا کن · پوشه عکس‌ها کجاست |
| open a file by name | Open test six docs | فایل تست شش ورد رو باز کن |
| open the last thing again | Open it again | دوباره بازش کن |
| rename (Guya asks first) | Rename it to final report | اسمش رو بذار گزارش نهایی |
| save or close the current window | Save it · Close it | ذخیره کن · پنجره رو ببند |
| open a website | Go to YouTube · Visit github.com | برو به سایت یوتیوب |
| search the web | Search for the weather on Chrome | توی گوگل سرچ کن هوای تهران |
| two steps at once | Open Chrome, then search for YouTube | کروم رو باز کن بعد یوتیوب رو جستجو کن |
| move in the browser | Scroll down · Go back · Go to the top | یه کم برو پایین · برگرد · برو اول صفحه |
| change the language | Switch to Persian · Switch to dual | برو انگلیسی · دو زبانه |

*Table 6.1. Quick reference of spoken commands.*

Filler words are fine ("let's scroll down a bit", «لطفاً یه کم برو پایین»). Numbers in names may be spoken («تست شش», "test six") and the file's real extension does not need to be said correctly; "docs" and «دکس» both mean `.docx`.

### 6.6 Questions and choices

After creating something, Guya asks whether to open it. Answer by voice (yes / no, بله / نه) or click the Yes / No buttons in the bubble. Before renaming, it asks the same way and shows the exact new name; nothing is renamed until you say yes. If a name matches several files, up to three choices appear on screen: click one, or say first / second / third (اول / دوم / سوم), or cancel (لغو). You can also just give a different command; the question goes away. A question that is not answered within two minutes expires by itself.

### 6.7 Languages and modes

The badge decides which language Guya listens for. FA and EN are precise; DUAL lets the model detect the language sentence by sentence and is a little slower. To switch by voice, say the command in the language currently set: *switch to Persian* while on EN, «برو انگلیسی» while on FA, and *dual* or «دو زبانه» for both. The control panel's Settings tab changes the model and the running mode (offline, online, both); those changes restart Guya.

### 6.8 What Guya will not do

It only looks inside Desktop, Documents and Downloads. It never deletes, never overwrites, never runs commands, never clicks inside web pages or downloads anything, and does not automate Save As. If you ask for one of those it says so. Browser commands only work when the browser is the program in front.

### 6.9 If something goes wrong

- *"Too short"*: hold the key while you speak, release after the last word.
- *"Nothing heard"*: the microphone heard silence; check the input device in System Settings.
- *"Microphone error"*: usually a second copy of Guya is running; quit both and start once. It also happens after sleep on some Macs; restarting Guya fixes it.
- *"Focus a supported browser"*: click inside the browser page first.
- *A command is misunderstood*: the pill shows the words Guya heard. Say the sentence again in one breath; short single words are the hardest for the model.
- *Everything else*: the control panel's Open Logs button shows `~/.guya/logs/guya.log`; every command is one line there with what was heard and what happened. Sending that file with a bug report is the fastest way to get it fixed.

### 6.10 Removing Guya

The Uninstall button in Settings removes the settings, the logs, the downloaded models and the launcher, and leaves the project folder. Re-run Setup starts the wizard again without removing anything.

---
## 7. Evaluation

Every number in this chapter was produced by a script in `eval/` from data that is either in the repository or downloadable by anyone; Appendix A gives the exact commands, and `report_tables.py` regenerates every table from the stored per-clip results with the current scorer, so the tables and the raw files cannot drift apart. Speech results are corpus-level word error rate (WER) and character error rate (CER); the real-time factor (RTF) is transcription time divided by audio length. All timing was done on an otherwise idle Apple M1 Pro (10 cores, 16 GB) with 8-bit weights on the CPU, which is the machine Guya is used on every day.

### 7.1 Data and method

**Speech.** Google FLEURS [4] is read speech of Wikipedia sentences recorded by native speakers, with human transcripts, and it is the only Persian speech corpus that can be downloaded without an account, so anyone assessing this report can rerun the evaluation. `eval/import_fleurs.py` samples 60 Persian and 60 English clips from the development split with a fixed seed (7), one clip per sentence so that no sentence is counted twice: 14.8 minutes of Persian (1,355 words after normalisation) and 9.4 minutes of English (1,211 words). The Persian sentences are long (median 23 words, 14.7 s), formal, and full of numbers and proper names; this is harder than the short colloquial commands Guya is built for, and the absolute Persian error rates should be read with that in mind. Ten clean English sentences from the macOS speech synthesiser were also kept as a smoke test of the pipeline; they are too easy to rank models and are not used below.

**Commands.** `eval/data/intents.jsonl` holds 267 Persian and English command phrasings (139 English, 128 Persian), written to be natural rather than to match the parser, each labelled with the intended intent and arguments. The last ten are taken verbatim from the manual test sessions of Section 7.8. The evaluator computes which rows coincide with one of the parser's own example phrases (46, after the yes/no vocabulary was widened) and reports them separately, so the headline number is on the 221 phrasings the parser had never seen (120 English, 101 Persian).

**Real use.** Every assistant command Guya processes writes one JSON record to the log (Table 4.6). At the time of the audit the log held 41 commands from four sessions of the author's own use in July and August; that snapshot is analysed in Section 7.6. By the time of writing the log holds 165 records.

**Machine and settings.** All speech measurements use faster-whisper 1.2.1 with int8 weights on the CPU. "Stock" means the library defaults with a beam of 5; "Guya pipeline" means the exact code of `stt.py` as the widget runs it.

### 7.2 Which model size does Persian need?

| Model | FA WER | FA CER | EN WER | EN CER | FA RTF | EN RTF |
|---|---:|---:|---:|---:|---:|---:|
| tiny | 92.5% | 37.7% | 13.4% | 6.1% | 0.11 | 0.03 |
| base | 84.1% | 30.8% | 7.8% | 3.7% | 0.07 | 0.05 |
| small | 56.6% | 16.7% | 6.0% | 2.6% | 0.18 | 0.14 |
| medium | 39.6% | 9.8% | 5.0% | 2.2% | 0.42 | 0.36 |
| large-v3-turbo | 28.9% | 6.0% | 4.0% | 1.9% | 0.29 | 0.35 |
| large-v3 | 28.2% | 5.8% | 4.8% | 2.2% | 0.72 | 0.57 |

*Table 7.1. Stock faster-whisper decoding (beam 5), FLEURS dev, 60 + 60 clips. RTF from a separate pass on the idle machine over 12 + 12 clips.*

Three results follow from Table 7.1.

**English is easy; Persian is not.** English at `small` is already a solved problem for this purpose: 6% WER on read Wikipedia sentences, and 32 of the 60 clips are transcribed with no error at all. Persian is different. The three smaller models are unusable for Persian (more than one word in two wrong), `medium` is marginal, and only the two large models bring Persian under 30% WER. The gap between the languages is seven times at the large end and nine times at `small`. This is the measurement behind the per-language accuracy floor in the wizard: English may run on `small`, Persian must not be offered anything below `large-v3-turbo`. That rule was a constant in the code from the first prototype; it is now a measured rule with a test.

**`large-v3-turbo` is the right default.** It matches `large-v3` on Persian (28.9% against 28.2%, a difference of nine words in 1,355), beats it on English, and runs in less than half the time (RTF 0.32 against 0.66). There is no reason to ship `large-v3` on a CPU.

**Persian CER is much lower than Persian WER**, 6% against 29% for the shipped model, because a large share of the word errors are spacing conventions rather than misheard words: «می‌کند» written as «می کند», «کنترل کننده‌های» written as «کنترل کننده های». The scorer deliberately does not unify these, because the user has to correct them by hand; but they are a different kind of error from the substitutions in the worst clips (technical vocabulary such as «ردیابی» heard as «رجابی», numbers, foreign names), and a Persian reader sees the text as mostly right. The spread across clips is wide. With `large-v3-turbo`, the median Persian clip has 25.7% WER; six of the sixty clips are at or under 10%, one is perfect, five are at or over 50%, and the worst is 71%. English is tighter: 40 of the 60 clips are perfect and 52 are at or under 10%.

### 7.3 Does Guya's own pipeline help or hurt?

The widget does not call the model with stock settings. Over months of use it had accumulated loudness normalisation, a VAD tuned for quiet speech, a vocabulary prompt per language, a repetition penalty of 1.2 against Whisper's habit of looping, a stricter no-speech threshold, and three Persian post-processing stages (Section 5.4). None of these had ever been measured. Extracting the pipeline into `stt.py` made it possible to run exactly the production code over the test set and then switch each setting back to the library default one at a time.

| `small` | FA WER | FA CER | EN WER | EN CER |
|---|---:|---:|---:|---:|
| stock faster-whisper | 56.6% | 16.7% | 6.0% | 2.6% |
| Guya pipeline, all settings | 63.2% | 21.6% | 15.6% | 11.0% |
| minus the repetition penalty | 57.3% | 17.5% | 6.0% | 2.5% |
| minus the VAD | 62.3% | 21.3% | 12.2% | 7.0% |
| minus the vocabulary prompt | 63.7% | 20.6% | 16.9% | 12.7% |
| minus Persian post-processing | 62.4% | 20.6% | 15.6% | 11.0% |
| minus the stricter no-speech threshold | 62.6% | 20.7% | 15.6% | 11.0% |
| minus loudness normalisation | 64.3% | 22.1% | 16.4% | 12.2% |
| minus the no-conditioning rule for short clips | 62.6% | 20.7% | 15.6% | 11.0% |

*Table 7.2. The production pipeline on `small`, and each setting switched back to stock in turn.*

The production pipeline made `small` two and a half times worse on English (6.0% to 15.6%) and noticeably worse on Persian, and Table 7.2 says why: almost all of it is the repetition penalty. Removing that one setting restores stock accuracy on English exactly and recovers nearly all of the Persian loss. The worst clips show the mechanism. The penalty, which lowers the score of every token already generated, pushes the decoder to end the sentence early rather than repeat a common word such as "the" or "of":

- *reference:* Next, some saddles, particularly English saddles, have safety bars that allow a stirrup leather to fall off the saddle if pulled backwards by a falling rider.
- *with the penalty:* Next, some saddles particularly English saddles have safety bars that allow a stirrup leather
- *without it:* Next, some saddles, particularly English saddles, have safety bars that allow a stirrup leather to fall off the saddle if pulled backwards by a falling rider.

The VAD costs another three to four points of English on `small`, because splitting a sentence into segments loses context at every cut; the prompt, the post-processing and the no-speech threshold are within noise of each other. Persian post-processing is expected to add errors on this set, because it deliberately rewrites formal verb forms into the colloquial forms a speaker uses («می‌خواهم» to «میخوام») and FLEURS is formal text; the cost is under one point.

| `large-v3-turbo` | FA WER | FA CER | EN WER | EN CER |
|---|---:|---:|---:|---:|
| stock faster-whisper | 28.9% | 6.0% | 4.0% | 1.9% |
| Guya pipeline, all settings | 29.2% | 6.3% | 4.1% | 2.0% |
| minus the repetition penalty | 27.1% | 6.6% | 3.9% | 1.8% |
| minus the VAD | 29.7% | 7.2% | 4.4% | 2.0% |
| minus the vocabulary prompt | 29.7% | 6.8% | 4.0% | 1.9% |
| minus Persian post-processing | 28.3% | 6.4% | 4.1% | 2.0% |

*Table 7.3. The same on the shipped model.*

On the shipped model the whole pipeline is within a few words of stock, so the damage from the penalty is specific to the smaller model, which is less certain about each token and gives up sooner; and even there the row without the penalty is the best row of the table (27.1% Persian, 3.9% English), better than stock decoding. The change made as a result: the repetition penalty is now off (1.0). Protection against Whisper's repetition loops falls to the hallucination filter, which drops a segment dominated by one repeated word, and to the rule that short recordings are decoded without conditioning on previous text; both are kept. The other settings stay, because they cost nothing measurable on the shipped model and exist for situations this test set does not contain (weak microphones, specialised vocabulary, colloquial Persian).

### 7.4 Calibrating the device benchmark

The wizard predicts each model's speed from one measurement of `tiny`. Table 7.4 gives the measured cost of every model relative to `tiny` on the idle machine; these ratios replaced the estimated table in `benchmark.py`.

| Model | RTF (idle) | ratio to `tiny` | previous estimate |
|---|---:|---:|---:|
| tiny | 0.08 | 1.0 | 1.0 |
| base | 0.06 | 0.8 | 2.0 |
| small | 0.16 | 2.1 | 5.2 |
| medium | 0.40 | 5.0 | 14.0 |
| large-v3-turbo | 0.32 | 4.0 | 8.0 |
| large-v3 | 0.66 | 8.4 | 28.0 |

*Table 7.4. Measured cost ratios. `base` is slightly faster than `tiny` because `tiny` fails Whisper's quality checks more often and retries at higher temperatures. The wizard's table now holds these measured values (Guya's own pipeline for `small` and `large-v3-turbo`, stock decoding for the rest) divided by the reference probe measurement of 0.040, so a machine whose probe comes out twice the reference is predicted to run every model twice as slowly.*

The estimates were pessimistic by a factor of two to three, and the benchmark itself was worse: it timed `tiny` on synthetic noise, on which Whisper fails its own compression-ratio check and retries at every temperature, so three runs on the same idle machine gave RTF 0.34, 0.48 and 0.69, and all three told this machine, which runs `large-v3-turbo` at 0.32, to use the online model for every language. The benchmark now times a bundled seven-second speech clip with temperature fallback off, takes the best of two runs, and gives 0.040 on this machine (three runs: 0.0398, 0.040, 0.040); with the ratios of Table 7.4 it predicts `large-v3-turbo` at 0.33 and recommends it, which is right. The recommendation rule also changed from two latency tiers, which were non-monotonic (a slightly slower machine could be told to run a bigger model), to a single threshold of 1.0.

### 7.5 Does the command parser generalise?

| Parser | phrasings | intent correct | intent and arguments | English | Persian | browser navigation |
|---|---:|---:|---:|---:|---:|---:|
| before this work | 221 | 69.2% | 66.1% | 65.8% | 73.3% | 42.3% |
| after | 221 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |

*Table 7.5. Unseen phrasings, `eval/intent_accuracy.py`. The 46 phrasings that coincide with the parser's own examples are excluded from both rows.*

The unit tests had always said the parser was fine, because they tested its example phrases against themselves. The unseen set said otherwise. Of the 75 failures before the change, 46 were browser navigation: "let's scroll down", "again, scroll down", «یه کم برو پایین» all failed outright, because navigation was matched with a regular expression over the whole sentence. The rest were spread over search (5), web search (5), open file (3), rename (3), open website (3) and a few others. Browser navigation went from 42% to 100% after filler words were stripped from the edges of the sentence and a keyword fallback was added. That fallback needed a second round of its own: its first version fired on any short sentence with a direction word, so "shut down the computer" scrolled the page and "back up my thesis" went back a page; it now requires a movement word as well as a direction and refuses anything that names a file, folder, application, window or tab. The remaining fixes were individually small and each came from one failing row: "new" was a create verb, so "open the new folder" *created* a folder; "note app" looked like the domain `note.app`; the word «نامه» contains «نام», so «سند پایان نامه رو باز کن» was a rename; «ماشین حساب» on its own was nothing; "delete the report" fuzzy-matched to a file search, and now is refused with a sentence that says so.

A perfect score on a set written by the person who wrote the parser is not a proof of generality, only coverage of the phrasings one person could think of. The real-use log is the check on that (Section 7.6), and the code review of Section 7.7 found five further regressions that this set had not caught.

Re-running the 13 real misunderstood transcripts from the usage log through the new parser, 9 now parse to the intended action. Of the other four, two are Persian transcripts that are misheard beyond repair («برگیار داکات»), and two are "Let's cool down", which is what Whisper made of "let's scroll down": the parser is deliberately not so lenient as to scroll on "cool down", because the same leniency is what made "shut down the computer" scroll.

### 7.6 Real use

The 41 logged commands are a small and biased sample: the author's own commands, almost all in English (39 of 41), and mostly browser commands because that feature was being tested at the time. They still say two things clearly.

| Outcome (41 commands) | Share |
|---|---:|
| action completed | 51% |
| not understood | 27% |
| understood but failed (wrong window in front, nothing found) | 15% |
| the assistant asked a question | 5% |
| cancelled | 2% |

*Table 7.6. Outcomes in the usage log.*

Half of the failures were the parser, and Section 7.5 removes almost all of them. The other half was one specific interaction bug: after a click on the pill or a result button, Guya itself was the frontmost application, so the next command was addressed to Guya and refused; six of the 41 commands hit this, and the widget now falls back to the last real target.

Latency is entirely the speech model. The median utterance was 1.9 s; median recognition 2,762 ms; median parse and act 30 ms; 97% of the time between key release and reply is Whisper. The real-time factor in use was 1.44, worse than the 0.32 measured in isolation, because the widget was re-transcribing the whole buffer every two seconds for the partial text and the final pass had to wait behind it; the partial pass is now limited to the last eight seconds. A device-based recommender that suggests a model which then falls behind real time in use is the most useful negative result the project produced, and it is why the recommendation threshold is 1.0 rather than 2.0.

### 7.7 Review of the September changes

The parser and widget changes of 5 September were reviewed line by line the same day, with every suspected defect reproduced before it was counted. The review confirmed 27 defects in that day's work; Table 7.7 groups them by kind.

| Group | Examples |
|---|---|
| rule precedence | "open word file" opened the last remembered folder instead of Word; "Okay, new folder" was not a creation |
| whole-word guards | the guard that stopped «نامه» from being a rename also stopped the spoken contraction «اسمشو» |
| navigation fallback firing too widely | "shut down the computer", "back up my thesis", "look up the weather" scrolled or went back |
| search pruning | a list meant to hide `node_modules` also hid any folder the user had named `build` or `out` |
| evaluation harness | the ablation switch for one setting flipped it the wrong way; eight rows of the held-out set coincided with pack phrases without being flagged |
| pending questions | a fresh command while a name was awaited was taken as the name; extra words after a spoken "no" («نه اسمش رو عوض نکن») were not recognised as a refusal |

*Table 7.7. Defects confirmed by the review, by group.*

Every one of them was reproduced, fixed and pinned by a test in `tests/test_review_regressions.py` before the numbers above were regenerated. The held-out set had been written by the same person who wrote the parser, so it shared his blind spots; the review did not, and that is the main argument for keeping both kinds of check.

### 7.8 Manual test sessions

After the evaluation sprint, manual testing was done on the development machine: a first run on 9 September and three task sessions on 11 September, each with a short list of spoken tasks in both languages. Each session produced observations that became code changes the same day (Table 7.8). The sessions are the reason for several details of Chapter 5 that would otherwise look arbitrary.

| Session | Observation | Cause found in the log | Change |
|---|---|---|---|
| 9 Sept | nothing happened on the hotkey; the pill said "I did not understand" | two widget processes were running (one left over from a screenshot script); both had opened the microphone and PortAudio failed for both with error −9986 | single-instance lock; widget exits when the panel dies; a "Microphone error" notice instead of "too short" |
| 1 | «بازش کن» after a file was created did nothing; «بله» was refused | Whisper transcribed the two-word command as «بازشگو» and the answer as «بیلی»; the dictation vocabulary prompt does not help on short commands | a command-vocabulary prompt for assistant recordings and an answer-only prompt while a question is pending; fuzzy acceptance of one-word answers at similarity 0.75; Yes/No buttons in the bubble |
| 1 | the user asked to switch languages by voice | (feature request) | `set_language` intent in both languages; the reply is given in the new language |
| 2 | Persian web search worked worse than English | Persian puts the query after the verb («توی گوگل سرچ کن مدل مو») and the grammar expected it before; «سرچ» was heard as «سیرچ» and «سیچ» | five verb-first Persian search patterns; the misheard forms added to the search verbs; «X رو گوگل کن» |
| 2 | «آزمون شیش» did not find `آزمون شیش.docx` and «ورد پنج» found nothing | the colloquial numbers were not in the spoken-number table; a query consisting of one digit was rejected as too short | colloquial Persian numbers added; single-digit queries allowed |
| 3 | "open Chrome and search for the weather" searched in Safari | the second step of the sequence carried no browser | a search step inherits the browser opened by the previous step |
| 3 | «اول» did not choose the first result; «یک» did | Whisper wrote «عوال» and «آبال» | fuzzy choice words at similarity 0.5 with a 0.1 margin, used only while a list is pending |

*Table 7.8. Manual test sessions and the changes they produced.*

Each change is pinned by a test, and the ten phrasings from these sessions were added to the held-out set. The pattern across the sessions is the same as in Section 7.6: most failures were not the recogniser's accuracy on long speech but short Persian words at the edges of the interaction, answers and choice words, and the fix was to tell the recogniser what to expect at those moments.

### 7.9 What was not measured

Nobody but the author has used Guya yet. The task list and questionnaire for the session with the target user are ready (Appendix D), and `eval/record.py` records his voice for the accuracy set, but the session had not taken place when this report was written, so there is no usability score and no accuracy figure on the target user's speech. The Windows adapter has not been run on Windows. The dual mode (offline English plus online Persian) and the online model were not measured, because scoring them means uploading the test audio to a third party.

### 7.10 Summary against the objectives

| Objective | Status | Evidence |
|---|---|---|
| O1 Persian and English dictation | met on macOS | Table 7.1; daily use since June |
| O2 bilingual assistant with the listed actions | met | Appendix B; Tables 7.5 and 7.8 |
| O3 predictable, safe behaviour | met | Table 4.3; absence tests in Section 5.13 |
| O4 offline, online and dual modes with a measured recommendation | met; online and dual modes unmeasured | Section 7.4 |
| O5 evaluation of accuracy, response time, task success, safety and usability | accuracy, response time and safety measured; task success on the author's use only; usability study pending | Sections 7.2 to 7.8 |

*Table 7.9. Objectives and their status.*

---
## 8. Discussion

### 8.1 What the measurements say about the design

The central design bet was that a fully local, zero-cost Persian dictation tool is possible on a normal laptop. Table 7.1 says yes, with a condition. It needs the large turbo model and a machine that runs it at about a third of real time, and it delivers Persian text that is right in nine characters out of ten and needs spacing corrections. English is far easier and would run on any machine. That asymmetry is the reason the wizard exists at all, and Section 7.4 is the first time the wizard's recommendation has been driven by measurement instead of assumption.

The second bet was a rule-based assistant. Section 7.5 gives the full picture. Tested against its own examples it looked perfect. Against phrasings someone else would actually say, it understood two commands in three. After a day of work driven by a held-out test set, it understands almost all of them, and the safety argument of Section 4.7 still holds, because nothing in the parser can produce an action that is not on the list. A language model would have handled the filler words on the first day, but it could not have given the same guarantee, and it would not have been free.

The third bet, that the tool could be made installable by a family member, cannot be judged from measurements. What can be said is that the installer, the wizard and the launcher each exist because of a specific failure met during the term (a Finder-launched application denied access to its own Python environment, a benchmark that told a fast machine to go online, a Persian question cut to three words), and that each failure is now covered by code and, where possible, by a test.

### 8.2 The effect of tuning without measurement

The most instructive result of the project is Table 7.2. Every setting in the speech pipeline had a reason, and each had been added after a real problem in daily use. Together they made the small model markedly worse, and one of them, the repetition penalty, was silently truncating sentences. None of this was visible in use, because the shipped model happens to be insensitive to it and because a truncated dictation looks like a mumbled ending. It only became visible when the exact production code was run on a fixed test set with each setting switched off in turn. The conclusion is not that the tuning was wrong in intent. It is that tuning without a measurement is guessing, and that the harness which makes the measurement cheap was worth more than any single setting.

The same applies to the parser work. After the changes had reached 100% on the held-out set, the review of Section 7.7 found 27 defects in the same day's work, including phrasings that had worked before the changes and no longer did. Every one of them was reproduced and pinned by a test before the numbers were regenerated. The held-out set and the review found different things, which is the reason both are kept.

### 8.3 The Persian voice

Guya speaks its English replies and shows its Persian ones. This is a constraint of the platform rather than a choice: macOS has no Persian voice, and reading Persian with the one Arabic voice was, to a Persian ear, worse than nothing. The consequence was found during the audit rather than during use. The pill's label holds about thirty characters, so a Persian confirmation question was cut to its first three words, and the user was answering "yes" to a question they could not read. The reply bubble fixes the display. A free offline Persian voice (Piper's `fa_IR-amir-medium` model through sherpa-onnx [17], tested on this machine at 0.06 RTF) is the natural next step, and a decision for the person who will listen to it.

### 8.4 Limitations and threats to validity

FLEURS is read, formal speech from one microphone setup; Guya's real input is short, colloquial, and from whatever microphone the user has. The absolute error rates in Table 7.1 are therefore not the error rates a user will see, in either direction: commands are shorter and easier, but home microphones and colloquial Persian are harder. What the table supports is the ranking of the models and the size of the gap between the languages.

The held-out intent set was written by the author, after reading the parser. It was written to contain what people say rather than what the parser accepts, and the 69.2% starting point suggests it was not simply written to the code, but it is not an independent sample of real users' phrasings. The real-use log is that sample, and it is small and mostly English.

All timing figures are from one machine. The cost ratios in Table 7.4 will differ on a Windows laptop without a fast memory system, which is exactly why the wizard measures rather than assumes; but the measurement itself has only been validated on the one machine.

The safety boundary has been checked by unit tests and by reading, not by an adversary. It is a small enough surface that reading is credible, but it remains a claim about a prototype.

Finally, the Windows adapter is untested on Windows, and the target user has not yet used the system. Both are stated in Section 7.9 and both are the first items of future work.

---

## 9. Conclusion and future work

### 9.1 Conclusion

Guya set out to give one person a way to write and to do small things on a computer by voice, in Persian and English, for free. The software does that on macOS, and it is installed with one double-click, set up by a wizard that measures the machine, and used every day. It is 11,894 lines of Python in 24 modules, with a safety boundary that cannot delete or overwrite anything, 136 automated tests, and an evaluation harness that reproduces every number in this report.

The report has replaced most of what was believed about the system with what was measured: which model Persian needs (`large-v3-turbo`, at 28.9% WER and 6.0% CER on read speech, against 4.0% WER for English), what the machine can run (the benchmark now calibrated within a few percent on the reference machine), what the tuning does (one setting was hurting and was removed), what the parser understands (100% of 221 unseen phrasings, from 69.2%), and where the time goes (97% in the speech model).

Three findings would carry over to anyone building a similar tool. Persian needs the large turbo model and English does not, so a bilingual tool must choose per language. A repetition penalty, the standard remedy for Whisper's loops, truncates sentences on smaller models and should be measured before it is used. And a rule-based command parser is adequate for a fixed command set provided it is tested on phrasings it was not written from, and provided filler words are handled before the grammar runs.

### 9.2 Future work

The items below are ordered by how much they would change what the user gets.

1. **The session with the target user.** The protocol is written (Appendix D): twelve tasks, timed, with the ten-item System Usability Scale in Persian and a recording of his voice for the accuracy set. It will produce the only accuracy number that matters, on his own speech, and the usability score.
2. **A run on Windows.** The adapter, installer and launcher exist; they need one afternoon on the family's machine and will certainly need fixes, because nothing that has not been run works the first time.
3. **A Persian voice.** Piper through sherpa-onnx runs at 0.06 RTF on this machine and sounds acceptable; wiring it into the `speak` method of the macOS adapter is a small change, and the decision whether the voice is good enough belongs to the user.
4. **Fine-tuning on Persian.** A `large-v3` fine-tuned on Common Voice Persian reports about 13% WER on FLEURS [7], less than half the stock model's error. Fine-tuning needs a GPU for a few hours; a fine-tuned model converted to CTranslate2 would drop into Guya without any other change, and the harness of Chapter 7 would measure the gain.
5. **A per-user correction table.** The 64 corrections of Section 5.4 were collected by hand. Guya could learn them from the user's own edits: when a dictated word is replaced within a few seconds, the pair is a candidate correction.
6. **The vocabulary prompt on colloquial speech.** Table 7.2 only shows the prompt does not hurt on formal speech; whether it helps on the user's own colloquial Persian needs the recorded set of item 1.
7. **More commands, within the same safety model.** Save As already has a refusal message because it came up in use; a Save As that names the folder, and moving a file with confirmation, are the natural next commands, and each fits the confirmation pattern of Section 4.5.
8. **A faster backend on Apple silicon.** faster-whisper has no Metal backend; whisper.cpp does. On the development machine that could bring `large-v3-turbo` well under 0.2 RTF and make the partial transcription smoother.

---
## References

1. A. Radford, J. W. Kim, T. Xu, G. Brockman, C. McLeavey and I. Sutskever, "Robust Speech Recognition via Large-Scale Weak Supervision," *Proceedings of the 40th International Conference on Machine Learning (ICML)*, 2023. Model card and `large-v3` release notes: https://github.com/openai/whisper and https://github.com/openai/whisper/discussions/1762.
2. SYSTRAN, *faster-whisper: Whisper transcription with CTranslate2*, https://github.com/SYSTRAN/faster-whisper (version 1.2.1 used).
3. OpenNMT, *CTranslate2: fast inference engine for Transformer models*, https://github.com/OpenNMT/CTranslate2 (version 4.8.1 used).
4. A. Conneau, M. Ma, S. Khanuja, Y. Zhang, V. Axelrod, S. Dalmia, J. Riesa, C. Rivera and A. Bapna, "FLEURS: Few-shot Learning Evaluation of Universal Representations of Speech," *IEEE Spoken Language Technology Workshop (SLT)*, 2022. Data: https://huggingface.co/datasets/google/fleurs (CC-BY-4.0).
5. R. Ardila, M. Branson, K. Davis, M. Henretty, M. Kohler, J. Meyer, R. Morais, L. Saunders, F. M. Tyers and G. Weber, "Common Voice: A Massively-Multilingual Speech Corpus," *Proceedings of LREC*, 2020.
6. Silero Team, *Silero VAD: pre-trained enterprise-grade voice activity detector*, https://github.com/snakers4/silero-vad (used through faster-whisper).
7. M. Gholizadeh, *whisper-large-v3-persian-common-voice-17*, Hugging Face model card, 2024, https://huggingface.co/MohammadGholizadeh/whisper-large-v3-persian-common-voice-17 (a Persian fine-tune reporting about 13% WER on FLEURS).
8. J. Brooke, "SUS: a 'quick and dirty' usability scale," in *Usability Evaluation in Industry*, Taylor & Francis, 1996.
9. W3C, *Web Content Accessibility Guidelines (WCAG) 2.2*, W3C Recommendation, October 2023, https://www.w3.org/TR/WCAG22/.
10. Apple, "Use Voice Control on your Mac," Apple Support, and "Dictation in Farsi/Persian," Apple Community discussion 253735978, accessed September 2026.
11. Microsoft, "Voice access frequently asked questions," Microsoft Support, accessed September 2026, https://support.microsoft.com/en-US/accessibility/windows/voice-access/voice-access-frequently-asked-questions-faqs.
12. Nuance, *Dragon Professional v16 data sheet*, 2023, https://dragon.nuance.com/shared/data-sheets/ds-dragon-professional-v16-en-us.pdf.
13. Google, "Type & edit with your voice," Google Docs Editors Help, accessed September 2026, https://support.google.com/docs/answer/4492226.
14. Talon Community, "Speech engines," Talon Community Wiki, accessed September 2026, https://talon.wiki/Resource%20Hub/Speech%20Recognition/speech%20engines/.
15. Asr Gooyesh Pardaz, *Nevisa: Persian speech to text*, https://asr-gooyesh.com/en/, accessed September 2026.
16. Riverbank Computing, *PyQt6*, https://www.riverbankcomputing.com/software/pyqt/ (version 6.11 used); PortAudio and PyAudio for capture; pynput and PyObjC for the macOS hotkey and window layer.
17. M. Hansen, *Piper: a fast, local neural text-to-speech system*, https://github.com/rhasspy/piper, and k2-fsa, *sherpa-onnx*, https://github.com/k2-fsa/sherpa-onnx, accessed August 2026 (the Persian voice `fa_IR-amir-medium`).
18. Groq, *Speech to text API reference*, https://console.groq.com/docs/speech-to-text, accessed September 2026 (the optional online model, `whisper-large-v3`).
19. Ecma International, *ECMA-376: Office Open XML File Formats*, Part 1, 2006 and later editions (the package structure used to write `.docx` files).
20. V. I. Levenshtein, "Binary codes capable of correcting deletions, insertions, and reversals," *Soviet Physics Doklady*, vol. 10, no. 8, pp. 707–710, 1966 (the edit distance behind WER and CER).

---

## Appendix A. Reproducing the results

All commands are run from the repository root. The FLEURS audio (about 430 MB) is downloaded once by the importer and is not committed; the manifests and every result file are.

```bash
./install.sh && ./venv/bin/python -m unittest discover -s tests -t .      # 136 tests, about 0.25 s
python eval/import_fleurs.py                                              # 60 + 60 clips, seed 7 (once)
python eval/accuracy.py --manifest eval/data/fleurs/manifest.jsonl \
    --models tiny,base,small,medium,large-v3-turbo,large-v3 --pipeline raw --out eval/results/fleurs_raw
python eval/accuracy.py --manifest eval/data/fleurs/manifest.jsonl \
    --models small,large-v3-turbo --pipeline guya --out eval/results/fleurs_guya
# Tables 7.2 and 7.3 were measured while production still had repetition_penalty=1.2;
# with the current code, "all settings" is `--ablate penalty_1_2` and "minus the
# penalty" is the plain `--pipeline guya` row.
for a in penalty_1_2 no_vad no_prompt no_postprocess no_speech_thr no_rms no_cond; do
  python eval/accuracy.py --manifest eval/data/fleurs/manifest.jsonl --models small --pipeline guya --ablate $a \
      --out eval/results/ablate_small_$a; done
python eval/intent_accuracy.py --failures                                 # Table 7.5
python eval/assistant_report.py --replay                                  # Table 7.6
python eval/report_tables.py --write                                      # regenerates every table
```

The full accuracy run over six models takes about two hours on the reference machine. The real-time factors of Tables 7.1 and 7.4 come from a separate run over 12 + 12 clips on the idle machine, because timing is disturbed by anything else running.

## Appendix B. The command set

| Intent | Examples (EN / FA) | Arguments |
|---|---|---|
| create_word_document | Create a Word file named report / یه فایل ورد به اسم گزارش بساز | name |
| create_text_file | Make a text file called notes / یه فایل متنی به اسم یادداشت بساز | name |
| create_folder | Create a folder named photos / یه پوشه به اسم عکس‌ها بساز | name |
| open_app | Open the calculator / ماشین حساب رو باز کن | app (word, text editor, calculator, file manager, browser, chrome, safari, pages) |
| open_file, open_folder | Open test six docs / فایل تست شش ورد رو باز کن; Open it again / دوباره بازش کن | query (optional; "it" uses the remembered path) |
| search | Find my report file / گزارش رو پیدا کن; Where is my budget file / پوشه پروژه کجاست | query |
| rename | Rename it to final report / اسمش رو بذار گزارش نهایی | old_name (optional), new_name; always confirmed |
| save_current, close_current | Save it / ذخیره کن; Close the window / پنجره رو ببند | — |
| open_website | Go to YouTube / برو به سایت یوتیوب; Visit github.com | target (known name or spoken domain) |
| web_search | Search for GitHub on Chrome / تو گوگل دنبال هوا بگرد | query, app |
| browser_navigation | Scroll down, Go to the top, Go back / یه کم برو پایین، برو اول صفحه، برگرد | action (scroll_down, scroll_up, top, bottom, back, forward) |
| sequence | Open Chrome, then search for YouTube / کروم رو باز کن بعد یوتیوب رو جستجو کن | 2–3 steps from open_app, open_website, web_search, save, close |
| set_language | Switch to Persian / برو انگلیسی; dual / دو زبانه | language (fa, en, dual) |
| confirm, cancel | Yes, sure, go ahead / بله، باشه; No, cancel / نه، لغو کن | — |
| delete_unsupported | Delete the report / فایل گزارش رو پاک کن | refused with an explanation |
| save_as_unsupported | Save this file as report on the Desktop | explained as unsupported |

*Table B.1. Intents, examples and arguments.*

The parser also recognises 32 application aliases, 56 website names, 16 search verbs, 18 rename verbs and 54 selection phrases; the full lists are in `guya/assistant/parser.py`, and the example phrases used by the fallback are in `guya/assistant/commands_en.json` and `commands_fa.json`.

## Appendix C. Configuration

`~/.guya/config.json`, merged over the defaults on every load so that an old file keeps working.

| Key | Default | Meaning |
|---|---|---|
| `model.backend` | `faster-whisper` | `faster-whisper` (offline) or `cloud` |
| `model.size` | `large-v3-turbo` | tiny, base, small, medium, large-v3-turbo, large-v3 |
| `model.device`, `model.compute_type` | `auto`, `auto` | CPU int8 or CUDA float16, chosen at start |
| `language` | `fa` | `fa`, `en` or `dual`; the badge's starting value |
| `cloud.provider`, `cloud.api_key`, `cloud.enabled` | groq, empty, false | the optional online model; `enabled` means dual mode |
| `hotkey.vk`, `hotkey.name`, `hotkey.label` | 71, G, G | the Windows dictation key; macOS uses Right Option regardless |
| `assistant.enabled` | true | whether the assistant key is active |
| `assistant.hotkey.*` | 119, F8, F8 | the Windows assistant key; macOS uses Right Command |
| `assistant.allowed_roots` | Desktop, Documents, Downloads | the only folders the assistant may touch |
| `assistant.default_directory` | Documents | where new files are created |
| `assistant.speak_feedback` | true | speak English replies |
| `ui.style` | `pill` | the widget style (a second style is reserved) |
| `audio.sample_rate`, `audio.chunk_size`, `audio.realtime_chunk_sec` | 16000, 1024, 2.0 | capture and partial-transcription settings |
| `behavior.min_recording_duration` | 0.4 s | shorter recordings are ignored |
| `behavior.done_state_duration_ms` | 1500 | how long "Done" stays on the pill |
| `behavior.type_delay_ms` | 100 | delay before the paste keystroke |
| `behavior.animation_fps` | 30 | pill animation rate |

*Table C.1. Configuration keys.*

## Appendix D. Evaluation instruments

**Spoken evaluation checklist.** `docs/ASSISTANT_EVALUATION.md` is the checklist used for the spoken tests of version 1. Each item is graded on four points, recognition, intent, action and feedback, as pass, partial or fail. It has 75 items in six groups: 15 English commands, 13 Persian commands, 8 phrasing variations, 7 safety checks (delete, overwrite, outside folders, unsupported actions), 23 save, close and browser checks, and 9 spoken-filename checks. The result summary at its end records the totals, the median response time, the best and worst commands per language, and any crash.

**User-study protocol.** `docs/USER_STUDY.md` is the protocol for the session with the target user (and, if possible, two or three other people); one session takes about forty minutes. It measures task success (done, done with help, not done), time on task, recognition quality (the tester writes what Guya heard), a typing comparison (two tasks are also done by typing, timed), usability with the ten-item System Usability Scale [8] in Persian, and three open questions. The twelve tasks are:

1. Dictate «امروز هوا خوب است و من می‌خواهم بیرون بروم.»
2. Dictate two sentences of the participant's own choice.
3. Type the sentence of task 1 by hand, for comparison.
4. Create a Word file called «تمرین».
5. Do not open it (answer the question).
6. Find the file «نامه» and choose the older of the two.
7. Rename it to «نامه اول» and confirm.
8. Open the calculator.
9. Close it.
10. In Chrome: go to YouTube, scroll down, go back.
11. Open the «عکس» folder by typing the path or clicking, for comparison.
12. Open the «عکس» folder by voice.

The SUS items, in Persian, are (1 = کاملاً مخالفم … 5 = کاملاً موافقم):

1. فکر می‌کنم دوست دارم از گویا مرتب استفاده کنم.
2. گویا را بی‌جهت پیچیده یافتم.
3. استفاده از گویا آسان بود.
4. فکر می‌کنم برای استفاده از گویا به کمک یک فرد فنی نیاز دارم.
5. بخش‌های مختلف گویا به‌خوبی با هم هماهنگ بودند.
6. در گویا ناسازگاری‌های زیادی دیدم.
7. فکر می‌کنم بیشتر افراد خیلی سریع یاد می‌گیرند از گویا استفاده کنند.
8. استفاده از گویا دست‌وپاگیر بود.
9. هنگام استفاده از گویا احساس اطمینان داشتم.
10. قبل از اینکه بتوانم از گویا استفاده کنم باید چیزهای زیادی یاد می‌گرفتم.

Scoring follows Brooke: for odd items use (answer − 1), for even items (5 − answer); the sum is multiplied by 2.5. A score around 68 is average for software in general. After the session the log is copied to `eval/results/user_study/`, `eval/assistant_report.py` is run on it, and the participant's ten recorded sentences are scored with `eval/accuracy.py`.

## Appendix E. Project history

**The proposal.** The first draft, written in June 2026 and kept in `docs/archive/`, described a dictation-only project with a four-week timeline. The proposal approved in July 2026 (`docs/PROPOSAL.md`) added the assistant and the five objectives of Table 1.1, and listed as excluded everything in Section 3.8. Its expected outputs were a runnable application with installers for macOS and Windows, both modes on separate keys, the wizard, control panel, widget, spoken feedback, help and logs, automated tests, structured user-evaluation results, documented limitations, this report, and a repeatable demonstration.

**The commits.** The repository holds the following commits (hash, date, message), in order.

```
26f327d  2026-06-05  Guya M1: config-driven widget + project scaffold
ba24a5d  2026-06-05  Guya M2: setup wizard
d7b859f  2026-06-05  Guya M2 fixes: CPU-appropriate model tier + readable wizard fonts
c2abaab  2026-06-05  Guya M3: on-device benchmark-based model recommendation
a2b18df  2026-06-05  Fix '&' rendering as Qt mnemonic in model card subtitle
c91de91  2026-06-05  Guya M4: free online fallback (cloud STT via Groq)
a46230d  2026-06-06  Guya polish: modern UI, download progress bar, double-click launcher
2bab75e  2026-06-06  Fix download progress bar stuck at 0% (disable xet backend)
8de1f84  2026-06-06  Guya: bilingual wizard, language-aware selection, editable specs, richer cards
d3f8658  2026-06-06  Guya UI fixes: scrollable model page, richer cards, better cloud guide, download controls, modern review
4a04412  2026-06-06  Guya wizard: faster benchmark, download cancel, clickable cloud guide, installed-model indicator
a73c621  2026-06-06  Guya: hybrid offline+online mode with a widget ONLINE/OFFLINE switch
c670aaa  2026-06-06  Fix wizard horizontal overflow + make hybrid checkbox usable
8beecb6  2026-06-06  Fix: move 'Also enable Online' box + cloud panel out of the scroll area
2c224e0  2026-06-06  Redesign wizard: separate Mode step (Offline/Online/Dual) from model setup
599bf81  2026-06-06  Fix macOS paste going to the wrong app (stale frontmost capture)
468a41f  2026-06-06  Clearer Mode page copy + friendlier Dual setup design
1efab35  2026-06-20  Add B.Sc. final-project proposal (docs/PROPOSAL.md)
3d55f33  2026-06-20  Proposal: fill student/supervisor details + add styled HTML and PDF
6da260b  2026-06-20  Proposal: shorten timeline (mark done phases) + add Persian version
7803e56  2026-06-20  Add one-double-click installers (macOS + Windows) + Python-setup guide
5fafa48  2026-06-20  Harden Windows installer: handle winget PATH-refresh + paren-safe batch
1d8e3da  2026-06-20  Wizard: Easy/Advanced choice, "How to use" final screen, clearer API guide
9e8eb02  2026-06-20  Easy Mode: single review page with changeable settings + Install
a63c9c8  2026-06-20  Wizard UX/visual overhaul: bigger resizable window, modal pickers, merged analysis, Apple/Airbnb-style polish
157e521  2026-06-20  Apply Calm Teal theme to the wizard (accessible, soothing)
c4e725b  2026-06-20  Vazirmatn font, analyze loading screen, device-config modal
86d90a2  2026-06-20  Launcher: clean macOS .app bundle + Windows windowless launcher
6429ee8  2026-06-20  Add Guya Control Panel (the real 'launcher'): on/off + settings + maintenance
3fd7a9d  2026-06-20  Control Panel: real circular power button + uptime + in-place settings
6ec2318  2026-06-20  Live two-way sync: panel mirrors the widget (active/backend/language) + logs modal
75b2330  2026-06-20  Fix not-recording + redesign panel into tabs (Controls | Settings)
55ab378  2026-06-20  Add accuracy evaluation harness (WER/CER/RTF) — the thesis results tool
8149040  2026-06-20  eval: add --examples (worst ref-vs-hyp clips per model) for error analysis
d93ebad  2026-08-17  feat: add accessible bilingual assistant V1
881de3c  2026-09-05  eval: real Persian data, honest scorer, held-out intent set, log report
2f72328  2026-09-05  widget, panel, wizard: visible errors, reply bubble, safer targets, calibrated benchmark
f67a38c  2026-09-05  assistant: filler-tolerant parser, safer intents, non-modal questions
2858a26  2026-09-05  docs: archive June proposals, fix workbook and checklist contradictions, screenshots
5af94d5  2026-09-05  docs: report draft (ch. 1-5), demo script, user-study protocol, README rewrite, status updates
e73ec00  2026-09-05  report: evaluation, discussion and conclusion chapters; FLEURS, RTF and ablation results
2c6278d  2026-09-05  fix the regressions found by the adversarial review of today's changes
9a8a345  2026-09-05  benchmark calibrated from measurements; repetition penalty off; report tables filled
2ebc3f0  2026-09-05  results: corrected conditioning ablation, final report tables
6d6b8a2  2026-09-09  widget: name microphone errors, exit when the panel dies, one widget at a time
69c1acc  2026-09-11  from the first manual test: command-vocabulary prompt, yes/no buttons, language switch by voice
5f67d9f  2026-09-11  tests: keep the main guard at the end of the regression file
679daff  2026-09-11  from the second manual test: Persian web search, colloquial numbers, number queries
5e8a0bc  2026-09-11  from the third manual test: search in the browser just opened; misheard choice words
5b38dbc  2026-09-13  report: B.Sc. layout — related work with a tool comparison, user guide, references, appendices
66112fc  2026-09-13  docs: script that renders the report markdown to a self-contained page (LTR and RTL)
d445219  2026-09-13  report: Persian version of the full report, and small fixes to the English one
```

## Appendix F. Glossary

| Term | Persian | Meaning in this report |
|---|---|---|
| ASR, automatic speech recognition | تشخیص خودکار گفتار | turning audio into text |
| push-to-talk | نگه‌دار و صحبت کن | recording only while a key is held |
| dictation mode | حالت دیکته | speech typed into the active application |
| assistant mode, command mode | حالت دستیار، حالت فرمان | speech interpreted as a command |
| intent | قصد | the action a command asks for |
| slot, argument | آرگومان | a value inside a command, such as a file name |
| phrase pack | بستهٔ عبارت‌ها | the list of example phrasings per intent |
| held-out set | مجموعهٔ دیده‌نشده | test phrasings the parser was not written from |
| WER, word error rate | نرخ خطای واژه | edits per reference word |
| CER, character error rate | نرخ خطای نویسه | edits per reference character |
| RTF, real-time factor | ضریب زمان واقعی | transcription time divided by audio length |
| VAD, voice activity detection | تشخیص فعالیت صوتی | labelling frames as speech or silence |
| beam search | جستجوی پرتویی | decoding that keeps several candidate sequences |
| temperature fallback | بازگشت دمایی | retrying a window with more randomness |
| repetition penalty | جریمهٔ تکرار | lowering the score of tokens already produced |
| hallucination | توهم | text the model produces without matching audio |
| vocabulary prompt | prompt واژگانی | words given to the decoder as prior context |
| ablation | مطالعهٔ حذفی | switching settings off one at a time to measure each |
| quantisation, int8 | کوانتیزاسیون، ۸ بیتی | storing weights as 8-bit integers |
| ZWNJ, zero-width non-joiner | نیم‌فاصله | the invisible character joining Persian compounds |
| pill | پیل | the floating status widget |
| reply bubble | حباب پاسخ | the wrapped panel under the pill |
| badge | نشان | the FA / EN / DUAL label on the pill |
| pending question | پرسش در انتظار | a confirmation, name or choice the assistant is waiting for |
| allowed roots | پوشه‌های مجاز | the folders the assistant may touch |
| barge-in | قطع گفتار | interrupting a spoken reply by pressing a key |
| wizard | ویزارد | the first-run setup program |
| control panel | پنل کنترل | the everyday window with the power button |
| launcher | اجراکننده | `Guya.app` or `Start Guya` |
| runtime copy | نسخهٔ اجرایی | the copy of the code under `~/.guya/runtime` |
| SUS, System Usability Scale | مقیاس کاربردپذیری سیستم | the ten-item usability questionnaire |

*Table F.1. Terms used in the report and their Persian equivalents.*
