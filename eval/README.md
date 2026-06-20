# Guya — Accuracy Evaluation

Measures **Word Error Rate (WER)** and **Character Error Rate (CER)** for each
offline model tier and the free cloud model, per language, plus the **real-time
factor (RTF)**. This produces the headline results table for the thesis:

> *Persian needs a larger model than English to reach usable accuracy; the free
> cloud model rescues weak devices that can't run a large offline model.*

## Files
- `accuracy.py` — the harness (manifest → models → WER/CER/RTF table → `.md` + `.csv`).
- `wer.py` — normalization (Persian ↔ Arabic chars, digits, punctuation) + WER/CER. No external deps.
- `record.py` — record a **real** Persian/English test set with your mic (recommended).
- `make_say_samples.py` — generate a clean English TTS set to smoke-test the pipeline.

## 1. Smoke-test the pipeline (clean English TTS)
```bash
python eval/make_say_samples.py
python eval/accuracy.py --manifest eval/data/say_manifest.jsonl --models tiny,base,small
```
TTS is unrealistically clean, so WER is tiny for every model — this only checks
that the harness runs.

## 2. The real evaluation — record human speech (recommended)
The most relevant data is real Persian speech, ideally including the **target
user (your brother)**:
```bash
python eval/record.py --speaker reza
python eval/record.py --speaker brother     # the target user!
```
Read each sentence aloud (edit the list in `record.py` to add more / colloquial
ones). Then score every model — including the free cloud model:
```bash
python eval/accuracy.py \
  --manifest eval/data/recorded/manifest.jsonl \
  --models tiny,base,small,medium,large-v3-turbo \
  --cloud
```

## 3. (Optional) Standard benchmark data
For numbers comparable to the literature, point the manifest at a public set:
- **Mozilla Common Voice (fa, en)** — download clips + the `.tsv`, then write a
  manifest of `{audio, text, lang}` rows (mp3 is fine; ffmpeg decodes it).
- **FLEURS (`fa_ir`, `en_us`)** — clean read speech via 🤗 `datasets`.

The manifest format is the same, so any source works.

## Output
A printed table plus `eval/results.md` (paste into the thesis) and
`eval/results.csv`. `--cloud` uses the Groq key from `~/.guya/config.json`.

## Notes
- WER/CER are corpus-level (total edits ÷ total reference units) — the standard.
- Normalization is applied equally to reference and hypothesis, so Arabic vs
  Persian character forms and digit styles don't unfairly inflate Persian WER.
- RTF < 1.0 means faster than real time on this machine.
