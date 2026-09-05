## Speech accuracy per model (FLEURS dev, 60 fa + 60 en clips, CPU int8, stock decoding)

| Model | FA WER | FA CER | EN WER | EN CER | FA RTF | EN RTF |
|---|---:|---:|---:|---:|---:|---:|
| tiny | 92.5% | 37.7% | 13.4% | 6.1% | 0.11x | 0.03x |
| base | 84.1% | 30.8% | 7.8% | 3.7% | 0.07x | 0.05x |
| small | 56.6% | 16.7% | 6.0% | 2.6% | 0.18x | 0.14x |
| medium | 39.6% | 9.8% | 5.0% | 2.2% | 0.42x | 0.36x |
| large-v3-turbo | 28.9% | 6.0% | 4.0% | 1.9% | 0.29x | 0.35x |
| large-v3 | 28.2% | 5.8% | 4.8% | 2.2% | 0.72x | 0.57x |

## Measured cost ratios used by the wizard (idle machine, 12 + 12 clips)

| Model | measured RTF (idle machine) | ratio to tiny |
|---|---:|---:|
| tiny | 0.08x | 1.0 |
| base | 0.06x | 0.8 |
| small | 0.16x | 2.1 |
| medium | 0.40x | 5.0 |
| large-v3-turbo | 0.32x | 4.0 |
| large-v3 | 0.66x | 8.4 |

## Guya pipeline vs stock, and one setting at a time — small

| small: pipeline | FA WER | FA CER | EN WER | EN CER |
|---|---:|---:|---:|---:|
| stock faster-whisper | 56.6% | 16.7% | 6.0% | 2.6% |
| Guya pipeline (all settings) | 63.2% | 21.6% | 15.6% | 11.0% |
| Guya minus `no_cond` | 62.6% | 20.7% | 15.6% | 11.0% |
| Guya minus `no_penalty` | 57.3% | 17.5% | 6.0% | 2.5% |
| Guya minus `no_postprocess` | 62.4% | 20.6% | 15.6% | 11.0% |
| Guya minus `no_prompt` | 63.7% | 20.6% | 16.9% | 12.7% |
| Guya minus `no_rms` | 64.3% | 22.1% | 16.4% | 12.2% |
| Guya minus `no_speech_thr` | 62.6% | 20.7% | 15.6% | 11.0% |
| Guya minus `no_vad` | 62.3% | 21.3% | 12.2% | 7.0% |

## Guya pipeline vs stock, and one setting at a time — large-v3-turbo

| large-v3-turbo: pipeline | FA WER | FA CER | EN WER | EN CER |
|---|---:|---:|---:|---:|
| stock faster-whisper | 28.9% | 6.0% | 4.0% | 1.9% |
| Guya pipeline (all settings) | 29.2% | 6.3% | 4.1% | 2.0% |
| Guya minus `no_penalty` | 27.1% | 6.6% | 3.9% | 1.8% |
| Guya minus `no_postprocess` | 28.3% | 6.4% | 4.1% | 2.0% |
| Guya minus `no_prompt` | 29.7% | 6.8% | 4.0% | 1.9% |
| Guya minus `no_vad` | 29.7% | 7.2% | 4.4% | 2.0% |

## Held-out intent accuracy (eval/data/intents.jsonl)

| Parser | rows | intent | intent + slots | English | Persian | browser navigation |
|---|---:|---:|---:|---:|---:|---:|
| before | 211 | 71.1% | 67.8% | 66.9% | 76.3% | 42.3% |
| after | 211 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |

## Worst Persian clips, large-v3-turbo, stock

- WER 71%
  - ref: از فناوری مبتنی بر ماهواره در مقابل فناوری مبتنی بر رادار زمینی استفاده می‌کند که به کنترل کننده‌های ترافیک هوایی امکان می‌دهد هواپیما را با دقت بیشتری ردیابی کند و به خلبانان اطلاعات دقیق‌تری می‌دهد.
  - hyp: از فناوری مبتدی بر ماهواره در مقابل فناوری مبتدی  از فناوری مبتنی بر ماهواره در مقابل فناوری مبتنی بر رادار زمینی استفاده می کند  که به کنترول کننده های ترافیک هوایی امکان می داد  هواه ما را با دقیقت بیشتری رجابی کند و به خلبان اطلاعات دقیق تری می داد
- WER 58%
  - ref: این پارک 19،500 کیلومتر مربع مساحت دارد و به 14 قلمرو مختلف زیست‌جغرافیایی تقسیم می‌شود، که هر یک از آنها حیات‌وحش متفاوتی را پشتیبانی می‌کنند.
  - hyp: این پارک 19500 کلومتر مربع مساحت دارد و به 14 قلم روی مختلف زیست جغرافی های تقسیم می شود  که هر یکی از آنها حیات وحش متفاوتی را پشتیبانی می کند
- WER 56%
  - ref: در سراسر ایالات متحده آمریکا، تقریباً 400،000 مورد شناخته شده از بیماری گرفتگی بافت‌های گوناگون (MS) وجود دارد، که یک بیماری عصبی مهم در بزرگسالان جوان‌تر و مسن به حساب می‌آید.
  - hyp: در سر و سر ایالت متحده امریکا تقیباً 400 هزار مورد شناخته شده از بیماری گرفتگی بافت های گناگون  ام ایس وجود دارد که ایک بیماری عصبی مهم در بزرگ سالان جوانتر و موسن به حساب می آید
- WER 52%
  - ref: این نظریه‌ها مطرح می‌کنند که افراد نیازها و/یا تمایلاتی مشخص دارند که طی رشد و رسیدن به بزرگسالی این نیازها و تمایلات درون‌سازی شده‌اند.
  - hyp: این نظریه ها مطرح می کنند که افراد نیازها و یا تمایولاتی مشخص دارند که تیه رشد و رسیدن به بزرگ سالی این نیازها و تمایولات در اون سازی شدند.

## Worst English clips, small, Guya pipeline

- WER 54%
  - ref: The Tibetan Buddhism is based on the teachings of Buddha, but were extended by the mahayana path of love and by a lot of techniques from Indian Yoga.
  - hyp: The Tibetan Buddhism is based on the teachings of Buddha, but we're extended by Mahayana.
- WER 47%
  - ref: When the fighting ceased after the wounded were transported to the hospital, about 40 of the other remaining inmates stayed in the yard and refused to return to their cells.
  - hyp: When the fighting ceased after The Wounded were transported to hospital, about 40 of the other
- WER 46%
  - ref: Next, some saddles, particularly English saddles, have safety bars that allow a stirrup leather to fall off the saddle if pulled backwards by a falling rider.
  - hyp: Next, some saddles particularly English saddles have safety bars that allow a stirrup leather
- WER 40%
  - ref: Science’s main goal is to figure out the way the world works through the scientific method. This method in fact guides most scientific research.
  - hyp: Science's main goal is to figure out the way that world works through scientific method.
