# Guya — user study protocol

For the session with the target user (and, if possible, two or three other
people). One session takes about 40 minutes. Everything is on paper or in this
file; nothing is uploaded anywhere.

## What is being measured

| Measure | How |
|---|---|
| Task success | each task marked done / done with help / not done |
| Time on task | stopwatch, from the first key press to the visible result |
| Recognition quality | the tester writes what Guya heard (the pill shows it; it is also in the log) |
| Typing comparison | two of the tasks are also done by typing, timed |
| Usability | the 10-item System Usability Scale (SUS), in Persian below |
| Open feedback | three questions, written down verbatim |

## Setup

1. Guya installed and on; badge set to the participant's language.
2. TextEdit (or Word) open with an empty document; Chrome open.
3. A folder `Documents/آزمایش` containing `نامه.docx`, `نامه قدیمی.docx`, `عکس` (folder).
4. Start `~/.guya/logs/guya.log` fresh: note the time; every command is logged with its
   transcript, intent and outcome, so the tester only needs to note *what happened*.
5. Explain: "Hold the first key to write, the second key to give a command. Say things
   the way you would to a person. There is no wrong way; if it does not work, that is
   information for me, not a mistake by you."

## Tasks (in this order)

| # | Task (say it your own way) | Done | Help | Time | What Guya heard |
|---|---|---|---|---|---|
| 1 | Dictate: «امروز هوا خوب است و من می‌خواهم بیرون بروم.» | | | | |
| 2 | Dictate two sentences of your own choice. | | | | |
| 3 | Type task 1 by hand (for comparison). | | | | |
| 4 | Create a Word file called «تمرین». | | | | |
| 5 | Do not open it (answer the question). | | | | |
| 6 | Find the file «نامه». Choose the older one. | | | | |
| 7 | Rename it to «نامه اول». Confirm. | | | | |
| 8 | Open the calculator. | | | | |
| 9 | Close it. | | | | |
| 10 | In Chrome: go to YouTube, scroll down, go back. | | | | |
| 11 | Open the «عکس» folder by typing the path or clicking (comparison). | | | | |
| 12 | Open the «عکس» folder by voice. | | | | |

Record every misrecognition and every time the participant had to repeat.

## SUS — پرسش‌نامهٔ کاربردپذیری (۱ = کاملاً مخالفم … ۵ = کاملاً موافقم)

| | سؤال | ۱ | ۲ | ۳ | ۴ | ۵ |
|---|---|---|---|---|---|---|
| ۱ | فکر می‌کنم دوست دارم از گویا مرتب استفاده کنم. | | | | | |
| ۲ | گویا را بی‌جهت پیچیده یافتم. | | | | | |
| ۳ | استفاده از گویا آسان بود. | | | | | |
| ۴ | فکر می‌کنم برای استفاده از گویا به کمک یک فرد فنی نیاز دارم. | | | | | |
| ۵ | بخش‌های مختلف گویا به‌خوبی با هم هماهنگ بودند. | | | | | |
| ۶ | در گویا ناسازگاری‌های زیادی دیدم. | | | | | |
| ۷ | فکر می‌کنم بیشتر افراد خیلی سریع یاد می‌گیرند از گویا استفاده کنند. | | | | | |
| ۸ | استفاده از گویا دست‌وپاگیر بود. | | | | | |
| ۹ | هنگام استفاده از گویا احساس اطمینان داشتم. | | | | | |
| ۱۰ | قبل از اینکه بتوانم از گویا استفاده کنم باید چیزهای زیادی یاد می‌گرفتم. | | | | | |

Scoring: for odd items use (answer − 1), for even items use (5 − answer); add
the ten values and multiply by 2.5. A score around 68 is average for software
in general.

## Three questions (write the answers word for word)

1. چه چیزی بیشتر از همه به شما کمک کرد؟
2. چه چیزی بیشتر از همه اذیت‌کننده بود؟
3. اگر یک چیز را می‌توانستید تغییر دهید، چه بود؟

## After the session

- Copy `~/.guya/logs/guya.log` to `eval/results/user_study/<name>-<date>.log`.
- Run `python eval/assistant_report.py --log eval/results/user_study/<name>-<date>.log --out eval/results/user_study/<name>-<date>`.
- If the participant agreed to it, also record the ten sentences of `eval/record.py`
  with `--speaker <name>` and score them with `eval/accuracy.py`; this is the only
  Persian accuracy number that reflects the real user's voice.
