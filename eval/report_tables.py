"""
Assemble the tables cited in docs/REPORT.md from eval/results/*.json.

    python eval/report_tables.py            # prints markdown
    python eval/report_tables.py --write    # also writes eval/results/REPORT_TABLES.md

Every table is re-scored from the stored per-clip hypotheses with the current
eval/wer.py, so the report and the raw results can never disagree.
"""

import argparse
import glob
import json
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from accuracy import rescore, fmt_pct, fmt_rtf  # noqa: E402

RESULTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
ORDER = ["tiny", "base", "small", "medium", "large-v3-turbo", "large-v3", "cloud"]


def load(pattern):
    rows = []
    for path in sorted(glob.glob(os.path.join(RESULTS, pattern))):
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        for r in d["results"]:
            rows.append(rescore(r))
    return rows


def pick(rows, model, pipeline):
    for r in rows:
        if r["model"] == model and r["pipeline"] == pipeline:
            return r
    return None


def cell(r, lang, key):
    a = r["agg"].get(lang, {})
    if key == "wer":
        return fmt_pct(a.get("we", 0), a.get("wn", 0))
    if key == "cer":
        return fmt_pct(a.get("ce", 0), a.get("cn", 0))
    if key == "rtf":
        return fmt_rtf(a.get("compute", 0.0), a.get("audio", 0.0))
    return "—"


def table_models(acc_rows, rtf_rows):
    lines = ["| Model | FA WER | FA CER | EN WER | EN CER | FA RTF | EN RTF |", "|---|---:|---:|---:|---:|---:|---:|"]
    for m in ORDER:
        acc = pick(acc_rows, m, "raw")
        if not acc:
            continue
        rtf = pick(rtf_rows, m, "raw") or acc
        lines.append(f"| {m} | {cell(acc,'fa','wer')} | {cell(acc,'fa','cer')} | {cell(acc,'en','wer')} | {cell(acc,'en','cer')} | {cell(rtf,'fa','rtf')} | {cell(rtf,'en','rtf')} |")
    return "\n".join(lines)


def table_pipeline(raw_rows, guya_rows, ablate_rows, model):
    lines = [f"| {model}: pipeline | FA WER | FA CER | EN WER | EN CER |", "|---|---:|---:|---:|---:|"]
    raw = pick(raw_rows, model, "raw")
    guya = pick(guya_rows, model, "guya")
    if raw:
        lines.append(f"| stock faster-whisper | {cell(raw,'fa','wer')} | {cell(raw,'fa','cer')} | {cell(raw,'en','wer')} | {cell(raw,'en','cer')} |")
    if guya:
        lines.append(f"| Guya pipeline (all settings) | {cell(guya,'fa','wer')} | {cell(guya,'fa','cer')} | {cell(guya,'en','wer')} | {cell(guya,'en','cer')} |")
    for r in ablate_rows:
        if r["model"] == model and r["pipeline"].startswith("guya-"):
            name = r["pipeline"].replace("guya-", "")
            lines.append(f"| Guya minus `{name}` | {cell(r,'fa','wer')} | {cell(r,'fa','cer')} | {cell(r,'en','wer')} | {cell(r,'en','cer')} |")
    return "\n".join(lines)


def table_rtf_calibration(rtf_rows):
    tiny = pick(rtf_rows, "tiny", "raw")
    if not tiny:
        return ""
    def overall(r):
        c = sum(a.get("compute", 0.0) for a in r["agg"].values())
        s = sum(a.get("audio", 0.0) for a in r["agg"].values())
        return c / s if s else 0.0
    base = overall(tiny)
    lines = ["| Model | measured RTF (idle machine) | ratio to tiny |", "|---|---:|---:|"]
    for m in ORDER:
        r = pick(rtf_rows, m, "raw")
        if r:
            lines.append(f"| {m} | {overall(r):.2f}x | {overall(r)/base:.1f} |")
    return "\n".join(lines)


def table_intents():
    out = []
    for tag in ("before", "after"):
        path = os.path.join(RESULTS, f"intents_{tag}.json")
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        s = d["summary"]
        row = lambda k: (s[k]["n"], 100.0 * s[k]["intent"] / s[k]["n"], 100.0 * s[k]["full"] / s[k]["n"])
        out.append((tag, row("all:all"), row("lang:en"), row("lang:fa"), row("intent:browser_navigation")))
    lines = ["| Parser | rows | intent | intent + slots | English | Persian | browser navigation |", "|---|---:|---:|---:|---:|---:|---:|"]
    for tag, a, en, fa, nav in out:
        lines.append(f"| {tag} | {a[0]} | {a[1]:.1f}% | {a[2]:.1f}% | {en[1]:.1f}% | {fa[1]:.1f}% | {nav[1]:.1f}% |")
    return "\n".join(lines)


def worst_examples(rows, model, pipeline, lang, n=4):
    r = pick(rows, model, pipeline)
    if not r:
        return ""
    det = sorted((d for d in r["details"] if d["lang"] == lang), key=lambda d: -d["wer"])[:n]
    lines = []
    for d in det:
        lines.append(f"- WER {d['wer']:.0f}%\n  - ref: {d['ref']}\n  - hyp: {d['hyp']}")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    raw = load("fleurs_raw_*.json")
    guya = load("fleurs_guya_*.json")
    rtf = load("fleurs_rtf_raw.json") or raw
    rtf_guya = load("fleurs_rtf_guya.json")
    ablate = load("ablate_*.json")

    parts = []
    parts.append("## Speech accuracy per model (FLEURS dev, 60 fa + 60 en clips, CPU int8, stock decoding)\n\n" + table_models(raw, rtf))
    parts.append("## Measured cost ratios used by the wizard (idle machine, 12 + 12 clips)\n\n" + table_rtf_calibration(rtf))
    for m in ("small", "large-v3-turbo"):
        t = table_pipeline(raw, guya, ablate, m)
        if t.count("\n") > 1:
            parts.append(f"## Guya pipeline vs stock, and one setting at a time — {m}\n\n" + t)
    parts.append("## Held-out intent accuracy (eval/data/intents.jsonl)\n\n" + table_intents())
    parts.append("## Worst Persian clips, large-v3-turbo, stock\n\n" + worst_examples(raw, "large-v3-turbo", "raw", "fa"))
    parts.append("## Worst English clips, small, Guya pipeline\n\n" + worst_examples(guya, "small", "guya", "en"))
    text = "\n\n".join(p for p in parts if p.strip())
    print(text)
    if args.write:
        with open(os.path.join(RESULTS, "REPORT_TABLES.md"), "w", encoding="utf-8") as f:
            f.write(text + "\n")
        print("\n✓ wrote eval/results/REPORT_TABLES.md")


if __name__ == "__main__":
    main()
