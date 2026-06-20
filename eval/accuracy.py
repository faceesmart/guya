"""
Guya accuracy evaluation harness.

Runs each offline model tier (and optionally the free cloud model) over a test
manifest, and reports corpus-level WER + CER per language, plus the real-time
factor (RTF) — the headline results table for the thesis.

Manifest: a .jsonl file, one object per line:
    {"audio": "data/clip1.wav", "text": "the reference transcript", "lang": "fa"}
    {"audio": "data/clip2.wav", "text": "another one", "lang": "en"}
(audio paths are relative to the manifest's folder; lang is "fa" or "en".)

Usage:
    python eval/accuracy.py --manifest eval/data/say_manifest.jsonl \
        --models tiny,base,small,large-v3-turbo --device cpu --compute int8
    # add --cloud to also score the free Groq model (uses the key in ~/.guya/config.json)
"""

import argparse
import json
import os
import sys
import time

from faster_whisper import WhisperModel
from faster_whisper.audio import decode_audio

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wer import wer_counts, cer_counts  # noqa: E402


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


def transcribe_offline(model, path, lang):
    segments, _info = model.transcribe(path, language=lang, beam_size=5)
    return " ".join(s.text for s in segments).strip()


def transcribe_cloud(path, lang, api_key):
    from guya import cloud_engine
    audio = decode_audio(path, sampling_rate=16000)
    return cloud_engine.transcribe(audio, lang, api_key).strip()


def evaluate(model_name, transcribe_fn, items):
    """Return (name, per-lang aggregates, rtf, per-clip details)."""
    agg = {}
    details = []
    audio_sec = 0.0
    t0 = time.time()
    for it in items:
        lang = it["lang"]
        try:
            audio = decode_audio(it["audio"], sampling_rate=16000)
            audio_sec += len(audio) / 16000.0
            hyp = transcribe_fn(it["audio"], lang)
        except Exception as e:
            print(f"   ! {os.path.basename(it['audio'])}: {e}")
            continue
        we, wn = wer_counts(it["text"], hyp, lang)
        ce, cn = cer_counts(it["text"], hyp, lang)
        a = agg.setdefault(lang, {"we": 0, "wn": 0, "ce": 0, "cn": 0, "n": 0})
        a["we"] += we; a["wn"] += wn; a["ce"] += ce; a["cn"] += cn; a["n"] += 1
        details.append({"audio": os.path.basename(it["audio"]), "lang": lang,
                        "ref": it["text"], "hyp": hyp,
                        "wer": (100.0 * we / wn if wn else 0.0)})
    elapsed = time.time() - t0
    rtf = (elapsed / audio_sec) if audio_sec else 0.0
    return model_name, agg, rtf, details


def fmt_pct(e, n):
    return f"{100.0 * e / n:.1f}%" if n else "—"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--models", default="tiny,base,small,large-v3-turbo")
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--compute", default="int8")
    ap.add_argument("--cloud", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--examples", type=int, default=0,
                    help="print the N worst clips per model (ref vs hyp)")
    ap.add_argument("--out", default="eval/results")
    args = ap.parse_args()

    items = load_manifest(args.manifest)
    if args.limit:
        items = items[:args.limit]
    langs = sorted({it["lang"] for it in items})
    counts = ", ".join(f"{l}:{sum(1 for i in items if i['lang'] == l)}" for l in langs)
    print(f"Loaded {len(items)} clips ({counts})\n")

    rows = []
    for size in [m.strip() for m in args.models.split(",") if m.strip()]:
        print(f"▶ {size} ({args.device}/{args.compute}) …")
        model = WhisperModel(size, device=args.device, compute_type=args.compute)
        rows.append(evaluate(size, lambda p, l: transcribe_offline(model, p, l), items))
        del model

    if args.cloud:
        from guya import config as gc
        key = (gc.load_config().get("cloud", {}) or {}).get("api_key")
        if key:
            print("▶ cloud (groq) …")
            rows.append(evaluate("cloud", lambda p, l: transcribe_cloud(p, l, key), items))
        else:
            print("   (skipping cloud: no API key in ~/.guya/config.json)")

    # ---- print + write table ----
    header = ["Model"] + [f"{l.upper()}-WER" for l in langs] + [f"{l.upper()}-CER" for l in langs] + ["RTF"]
    table = [header]
    for name, agg, rtf, _details in rows:
        r = [name]
        for l in langs:
            a = agg.get(l, {})
            r.append(fmt_pct(a.get("we", 0), a.get("wn", 0)))
        for l in langs:
            a = agg.get(l, {})
            r.append(fmt_pct(a.get("ce", 0), a.get("cn", 0)))
        r.append(f"{rtf:.2f}x")
        table.append(r)

    widths = [max(len(row[i]) for row in table) for i in range(len(header))]
    print("\n" + "=" * (sum(widths) + 3 * len(widths)))
    for ri, row in enumerate(table):
        print("  ".join(c.ljust(widths[i]) for i, c in enumerate(row)))
        if ri == 0:
            print("-" * (sum(widths) + 3 * len(widths)))

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out + ".md", "w", encoding="utf-8") as f:
        f.write("| " + " | ".join(header) + " |\n")
        f.write("|" + "|".join(["---"] * len(header)) + "|\n")
        for row in table[1:]:
            f.write("| " + " | ".join(row) + " |\n")
    with open(args.out + ".csv", "w", encoding="utf-8") as f:
        for row in table:
            f.write(",".join(row) + "\n")
    print(f"\n✓ wrote {args.out}.md and {args.out}.csv")

    # ---- error examples (qualitative analysis) ----
    if args.examples:
        for name, _agg, _rtf, details in rows:
            worst = sorted(details, key=lambda d: -d["wer"])[:args.examples]
            print(f"\n── {name}: {args.examples} worst clips ──")
            for d in worst:
                print(f"  WER {d['wer']:.0f}%  [{d['lang']}] {d['audio']}")
                print(f"    ref: {d['ref']}")
                print(f"    hyp: {d['hyp']}")


if __name__ == "__main__":
    main()
