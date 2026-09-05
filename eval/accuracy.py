"""
Guya accuracy evaluation harness.

Runs each offline model tier (and optionally the free cloud model) over a test
manifest and reports corpus-level WER + CER per language, plus the real-time
factor (RTF) — the headline results table for the report.

Two pipelines can be measured:

  --pipeline raw   stock faster-whisper: model.transcribe(audio, language, beam_size=5)
  --pipeline guya  the pipeline the desktop widget actually runs (guya/stt.py):
                   RMS normalisation, VAD, per-language vocabulary prompt,
                   beam 5, hallucination filter and Persian post-processing
                   (the repetition penalty was removed after --ablate measured it).

Manifest: a .jsonl file, one object per line:
    {"audio": "fa_ir/clip1.wav", "text": "the reference transcript", "lang": "fa"}
(audio paths are relative to the manifest's folder; lang is "fa" or "en".)

Usage:
    python eval/accuracy.py --manifest eval/data/fleurs/manifest.jsonl \
        --models tiny,base,small,medium,large-v3-turbo --pipeline raw
    python eval/accuracy.py --manifest ... --models small,large-v3-turbo --pipeline guya
    python eval/accuracy.py --report eval/results/a.json,eval/results/b.json --out eval/results/all

Outputs <out>.md, <out>.csv (the table) and <out>.json (every clip: reference,
hypothesis, per-clip WER, seconds of audio, seconds of compute) so the error
analysis in the report can be reproduced. --report re-scores the stored
hypotheses with the current normaliser, so a scorer fix never needs the
transcriptions to be run again. The "Clips" column shows how many clips per
language actually contributed (a clip that fails to decode is skipped and
would otherwise silently shrink the denominator).

Privacy: --cloud sends every clip to the Groq API. Do not use it on
recordings of a person who has not agreed to that.
"""

import argparse
import json
import os
import statistics
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from wer import wer_counts, cer_counts, rate  # noqa: E402


def load_manifest(path):
    base = os.path.dirname(os.path.abspath(path))
    items = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            d["audio"] = os.path.join(base, d["audio"])
            items.append(d)
    return items


# ---------------------------------------------------------------- transcribers

def make_raw(model):
    def run(audio, lang):
        segments, _info = model.transcribe(audio, language=lang, beam_size=5)
        return " ".join(s.text for s in segments).strip()
    return run


# Each ablation switches ONE production setting back to the stock value, so
# the difference to the full "guya" row is that setting's contribution.
ABLATIONS = {
    "no_prompt":     {"overrides": {"initial_prompt": None}},
    "no_vad":        {"overrides": {"vad_filter": False}},
    # production was 1.2 until the ablation below showed the cost; it is now
    # 1.0, so this ablation is a no-op kept for reproducibility of Table 2/3
    "no_penalty":    {"overrides": {"repetition_penalty": 1.0}},
    "penalty_1_2":   {"overrides": {"repetition_penalty": 1.2}},
    "no_speech_thr": {"overrides": {"no_speech_threshold": 0.6}},
    "no_postprocess": {"postprocess": False},
    "no_rms":        {"rms": False},
    # stock is True; Guya turns it off for recordings under 5 s
    "no_cond":       {"overrides": {"condition_on_previous_text": True}},
}


def make_guya(model, ablation=None):
    from guya import stt
    extra = ABLATIONS.get(ablation, {}) if ablation else {}

    def run(audio, lang):
        return stt.transcribe_audio(model, audio, lang, audio_duration=len(audio) / 16000.0, **extra)
    return run


def make_cloud(api_key, pipeline):
    from guya import cloud_engine, stt
    if pipeline == "guya":
        model = stt.CloudModel("groq", api_key)
        return lambda audio, lang: stt.transcribe_audio(model, audio, lang, audio_duration=len(audio) / 16000.0)
    return lambda audio, lang: cloud_engine.transcribe(audio, lang, api_key).strip()


# ---------------------------------------------------------------- evaluation

def evaluate(name, pipeline, transcribe_fn, items, decode_audio, quiet=False):
    """Return a result row: aggregates per language + per-clip details."""
    agg = {}
    details = []
    for k, it in enumerate(items, 1):
        lang = it["lang"]
        try:
            audio = decode_audio(it["audio"], sampling_rate=16000)
            seconds = len(audio) / 16000.0
            t0 = time.perf_counter()
            hyp = transcribe_fn(audio, lang)
            compute = time.perf_counter() - t0
        except Exception as e:  # noqa: BLE001 — one bad clip must not kill a 2-hour run
            print(f"   ! {os.path.basename(it['audio'])}: {e}")
            continue
        we, wn = wer_counts(it["text"], hyp, lang)
        ce, cn = cer_counts(it["text"], hyp, lang)
        a = agg.setdefault(lang, {"we": 0, "wn": 0, "ce": 0, "cn": 0, "n": 0, "audio": 0.0, "compute": 0.0})
        a["we"] += we; a["wn"] += wn; a["ce"] += ce; a["cn"] += cn; a["n"] += 1
        a["audio"] += seconds; a["compute"] += compute
        details.append({"audio": os.path.basename(it["audio"]), "lang": lang,
                        "ref": it["text"], "hyp": hyp,
                        "wer": round(100.0 * rate(we, wn), 1),
                        "seconds": round(seconds, 2), "compute": round(compute, 3)})
        if not quiet and (k % 10 == 0 or k == len(items)):
            print(f"   {k}/{len(items)}", flush=True)
    return {"model": name, "pipeline": pipeline, "agg": agg, "details": details}


def rescore(result):
    """Recompute the aggregates of a stored result from its per-clip details
    with the CURRENT normaliser, so a scorer fix never requires re-running
    hours of transcription."""
    agg = {}
    for d in result["details"]:
        lang = d["lang"]
        we, wn = wer_counts(d["ref"], d["hyp"], lang)
        ce, cn = cer_counts(d["ref"], d["hyp"], lang)
        a = agg.setdefault(lang, {"we": 0, "wn": 0, "ce": 0, "cn": 0, "n": 0, "audio": 0.0, "compute": 0.0})
        a["we"] += we; a["wn"] += wn; a["ce"] += ce; a["cn"] += cn; a["n"] += 1
        a["audio"] += d.get("seconds", 0.0); a["compute"] += d.get("compute", 0.0)
        d["wer"] = round(100.0 * rate(we, wn), 1)
    result["agg"] = agg
    return result


def table_rows(results, langs):
    header = (["Model", "Pipeline", "Clips"]
              + [f"{l.upper()}-WER" for l in langs]
              + [f"{l.upper()}-CER" for l in langs]
              + [f"{l.upper()}-RTF" for l in langs]
              + ["RTF"])
    rows = [header]
    for r in results:
        agg = r["agg"]
        n_clips = "+".join(str(agg.get(l, {}).get("n", 0)) for l in langs)
        row = [r["model"], r["pipeline"], n_clips]
        for l in langs:
            a = agg.get(l, {})
            row.append(fmt_pct(a.get("we", 0), a.get("wn", 0)))
        for l in langs:
            a = agg.get(l, {})
            row.append(fmt_pct(a.get("ce", 0), a.get("cn", 0)))
        for l in langs:
            a = agg.get(l, {})
            row.append(fmt_rtf(a.get("compute", 0.0), a.get("audio", 0.0)))
        tot_c = sum(a.get("compute", 0.0) for a in agg.values())
        tot_a = sum(a.get("audio", 0.0) for a in agg.values())
        row.append(fmt_rtf(tot_c, tot_a))
        rows.append(row)
    return rows


def fmt_pct(e, n):
    return f"{100.0 * e / n:.1f}%" if n else "—"


def fmt_rtf(compute, audio):
    return f"{compute / audio:.2f}x" if audio else "—"


def write_outputs(results, langs, out):
    rows = table_rows(results, langs)
    widths = [max(len(row[i]) for row in rows) for i in range(len(rows[0]))]
    print("\n" + "=" * (sum(widths) + 3 * len(widths)))
    for ri, row in enumerate(rows):
        print("  ".join(c.ljust(widths[i]) for i, c in enumerate(row)))
        if ri == 0:
            print("-" * (sum(widths) + 3 * len(widths)))

    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out + ".md", "w", encoding="utf-8") as f:
        f.write("| " + " | ".join(rows[0]) + " |\n")
        f.write("|" + "|".join(["---"] * len(rows[0])) + "|\n")
        for row in rows[1:]:
            f.write("| " + " | ".join(row) + " |\n")
    with open(out + ".csv", "w", encoding="utf-8") as f:
        for row in rows:
            f.write(",".join(row) + "\n")
    with open(out + ".json", "w", encoding="utf-8") as f:
        json.dump({"langs": langs, "results": results}, f, ensure_ascii=False, indent=1)
    print(f"\n✓ wrote {out}.md, {out}.csv and {out}.json")


def print_examples(results, n):
    for r in results:
        worst = sorted(r["details"], key=lambda d: -d["wer"])[:n]
        print(f"\n── {r['model']} / {r['pipeline']}: {n} worst clips ──")
        for d in worst:
            print(f"  WER {d['wer']:.0f}%  [{d['lang']}] {d['audio']}")
            print(f"    ref: {d['ref']}")
            print(f"    hyp: {d['hyp']}")
        med = statistics.median(d["compute"] for d in r["details"]) if r["details"] else 0
        print(f"  median compute per clip: {med:.2f}s")


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest")
    ap.add_argument("--models", default="tiny,base,small,large-v3-turbo")
    ap.add_argument("--pipeline", default="raw", choices=["raw", "guya"])
    ap.add_argument("--ablate", default=None, choices=sorted(ABLATIONS),
                    help="with --pipeline guya: switch one production setting back to stock")
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--compute", default="int8")
    ap.add_argument("--cloud", action="store_true")
    ap.add_argument("--limit", type=int, default=0, help="first N clips overall")
    ap.add_argument("--per-lang-limit", type=int, default=0, help="first N clips of each language")
    ap.add_argument("--examples", type=int, default=0, help="print the N worst clips per model")
    ap.add_argument("--report", default=None, help="comma-separated .json results to merge into one table (no models run)")
    ap.add_argument("--out", default="eval/results/results")
    args = ap.parse_args()

    if args.report:
        merged, langs = [], set()
        for path in [p.strip() for p in args.report.split(",") if p.strip()]:
            with open(path, encoding="utf-8") as f:
                d = json.load(f)
            merged.extend(rescore(r) for r in d["results"]); langs.update(d["langs"])
        write_outputs(merged, sorted(langs), args.out)
        if args.examples:
            print_examples(merged, args.examples)
        return

    if not args.manifest:
        ap.error("--manifest is required unless --report is given")

    from faster_whisper import WhisperModel
    from faster_whisper.audio import decode_audio

    items = load_manifest(args.manifest)
    if args.per_lang_limit:
        kept, seen = [], {}
        for it in items:
            if seen.get(it["lang"], 0) < args.per_lang_limit:
                kept.append(it); seen[it["lang"]] = seen.get(it["lang"], 0) + 1
        items = kept
    if args.limit:
        items = items[:args.limit]
    # Drop clips that cannot be decoded up front, so one bad file never aborts
    # a two-hour run and the Clips column stays honest.
    readable, total_audio = [], 0.0
    for it in items:
        try:
            total_audio += len(decode_audio(it["audio"], sampling_rate=16000)) / 16000.0
            readable.append(it)
        except Exception as e:  # noqa: BLE001
            print(f"   ! skipping {os.path.basename(it['audio'])}: {e}")
    items = readable
    langs = sorted({it["lang"] for it in items})
    counts = ", ".join(f"{l}:{sum(1 for i in items if i['lang'] == l)}" for l in langs)
    print(f"Loaded {len(items)} clips ({counts}), {total_audio/60:.1f} min of audio, pipeline={args.pipeline}\n")

    results = []
    for size in [m.strip() for m in args.models.split(",") if m.strip()]:
        print(f"▶ {size} ({args.device}/{args.compute}, {args.pipeline}) …", flush=True)
        model = WhisperModel(size, device=args.device, compute_type=args.compute)
        fn = make_guya(model, args.ablate) if args.pipeline == "guya" else make_raw(model)
        label = args.pipeline + (f"-{args.ablate}" if args.ablate else "")
        results.append(evaluate(size, label, fn, items, decode_audio))
        del model
        write_outputs(results, langs, args.out)   # checkpoint after every model

    if args.cloud:
        from guya import config as gc
        key = (gc.load_config().get("cloud", {}) or {}).get("api_key")
        if key:
            print("▶ cloud (groq whisper-large-v3) …")
            results.append(evaluate("cloud", args.pipeline, make_cloud(key, args.pipeline), items, decode_audio))
            write_outputs(results, langs, args.out)
        else:
            print("   (skipping cloud: no API key in ~/.guya/config.json)")

    if args.examples:
        print_examples(results, args.examples)


if __name__ == "__main__":
    main()
