# Guya — Evaluation

Everything in the report's results chapter is produced by the scripts in this
folder, from data that anyone can re-download. Nothing here needs a paid
service; the optional `--cloud` flag is the only thing that leaves the machine.

## What is measured

| Question | Script | Output |
|---|---|---|
| How accurate is each Whisper model tier on Persian and English speech, and how fast is it on this machine? | `accuracy.py` | WER / CER / real-time factor per model, language and pipeline |
| Does Guya's own tuning (prompt, VAD, penalties, Persian post-processing) help or hurt compared with stock faster-whisper? | `accuracy.py --pipeline guya`, `--ablate` | one row per setting switched back to stock |
| How well does the rule-based command parser generalise to phrasings it was not written for? | `intent_accuracy.py` | intent and slot accuracy on a held-out set |
| What happened in real daily use? | `assistant_report.py` | task outcome, latency split, misunderstood transcripts, from Guya's own log |

## Files

- `accuracy.py` — the speech harness (manifest → models → WER/CER/RTF table → `.md`, `.csv`, `.json`).
- `wer.py` — bilingual text normalisation + WER/CER. No external dependencies. Tested by `tests/test_eval_wer.py`.
- `import_fleurs.py` — downloads Google FLEURS (CC-BY-4.0) and samples a fixed Persian + English set.
- `record.py` — record your own test set with the microphone (the target user's voice is the most relevant data).
- `make_say_samples.py` — ten clean English TTS clips; a smoke test of the pipeline only.
- `intent_accuracy.py` + `data/intents.jsonl` — held-out command phrasings (257 rows, 38 of which coincide with the phrase packs and are reported separately).
- `assistant_report.py` — turns the `Assistant evaluation: {...}` lines in `~/.guya/logs/guya.log` into tables.
- `results/` — every table the report cites. `*.json` files hold the per-clip references and hypotheses.

## Reproduce the speech results

```bash
# 1. Data: 60 Persian + 60 English FLEURS dev clips (~24 min, ~430 MB download, audio is not committed)
python eval/import_fleurs.py

# 2. Stock faster-whisper, every tier (about two hours on an M1 Pro, CPU int8)
python eval/accuracy.py --manifest eval/data/fleurs/manifest.jsonl \
    --models tiny,base,small,medium,large-v3-turbo,large-v3 --pipeline raw --out eval/results/fleurs_raw

# 3. The pipeline the widget actually runs
python eval/accuracy.py --manifest eval/data/fleurs/manifest.jsonl \
    --models small,large-v3-turbo --pipeline guya --out eval/results/fleurs_guya

# 4. One setting at a time back to stock (which knob costs accuracy?)
python eval/accuracy.py --manifest eval/data/fleurs/manifest.jsonl \
    --models small --pipeline guya --ablate no_vad --out eval/results/ablate_small_no_vad

# 5. Merge any set of .json results into one table, re-scored with the current normaliser
python eval/accuracy.py --report eval/results/fleurs_raw.json,eval/results/fleurs_guya.json \
    --out eval/results/all --examples 5
```

Real-time factor (RTF) is transcription wall time divided by audio seconds;
below 1.0 is faster than real time. Run the RTF rows on an idle machine; WER
does not depend on load but RTF does.

## Your own recordings

```bash
python eval/record.py --speaker reza
python eval/record.py --speaker brother      # the target user
python eval/accuracy.py --manifest eval/data/recorded/manifest.jsonl --models small,large-v3-turbo --pipeline guya
```

Privacy: recordings stay on the computer. `--cloud` sends every clip to the
Groq API; do not use it on someone's voice without asking them.

## Reproduce the assistant results

```bash
python eval/intent_accuracy.py --failures              # held-out parser accuracy, in under a second
python eval/assistant_report.py --replay               # real-use log + what the current parser now understands
```

## Notes on scoring

- WER/CER are corpus-level (total edits ÷ total reference units).
- The same normalisation is applied to reference and hypothesis: case,
  punctuation, Persian/Arabic-Indic digits, spelled-out numbers 0–99, Arabic
  letter forms (ي/ك/ة), diacritics and the zero-width non-joiner. Genuine
  Persian letters (آ, ئ) are **not** folded, so writing «اب» for «آب» counts.
- Compound-word spacing («کتاب ها» / «کتابها») is not normalised. It costs a
  word error and no character error, which is why CER is reported next to WER
  for Persian.
- FLEURS is read speech from Wikipedia sentences, recorded by native speakers.
  It measures the recogniser, not Guya's target situation (short colloquial
  commands and dictation), which is why the report also uses the real-use log.
