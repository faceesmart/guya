"""
Summarise real assistant usage from Guya's own log.

Every assistant command the widget handles is logged as one structured line:

    HH:MM:SS [INFO   ] Assistant evaluation: {"transcript": ..., "intent": ...,
        "status": ..., "audio_seconds": ..., "transcription_ms": ..., "command_ms": ...}

That makes the daily-use log a ready-made evaluation dataset: task outcome per
command, where the time goes (speech recognition vs. parsing and acting), and
which utterances the parser failed on. This script turns it into the tables
the report needs.

Usage:
    python eval/assistant_report.py                          # ~/.guya/logs/guya.log
    python eval/assistant_report.py --log some/guya.log --out eval/results/assistant_log
    python eval/assistant_report.py --replay                 # re-parse failed transcripts with the CURRENT parser
"""

import argparse
import glob
import json
import os
import re
import statistics
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

LINE = re.compile(r"Assistant evaluation: (\{.*\})\s*$")


def load_records(paths):
    records = []
    for path in paths:
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                for line in f:
                    m = LINE.search(line)
                    if m:
                        try:
                            records.append(json.loads(m.group(1)))
                        except json.JSONDecodeError:
                            pass
        except OSError:
            continue
    return records


def pct(a, b):
    return f"{100.0 * a / b:.0f}%" if b else "—"


def median(xs):
    return statistics.median(xs) if xs else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", default=os.path.expanduser("~/.guya/logs/guya.log"))
    ap.add_argument("--out", default=None)
    ap.add_argument("--replay", action="store_true",
                    help="re-run every transcript through the current parser and count how many failures it now understands")
    args = ap.parse_args()

    paths = [args.log] + sorted(glob.glob(args.log + ".*"))
    recs = load_records(paths)
    if not recs:
        print("no 'Assistant evaluation' records found in", paths)
        return

    lines = []
    n = len(recs)
    status = Counter(r.get("status") for r in recs)
    intents = Counter(r.get("intent") for r in recs)
    langs = Counter(r.get("stt_language") for r in recs)
    success = status.get("success", 0)
    # "needs_selection" / "needs_confirmation" are the assistant asking a question, not failures.
    asked = status.get("needs_selection", 0) + status.get("needs_confirmation", 0)
    cancelled = status.get("cancelled", 0)
    errors = status.get("error", 0)
    unknown = sum(1 for r in recs if r.get("intent") == "unknown")

    lines.append(f"Assistant usage log — {n} commands from {len(paths)} log file(s)")
    lines.append("")
    lines.append("| Outcome | Count | Share |")
    lines.append("|---|---:|---:|")
    lines.append(f"| Action completed (success) | {success} | {pct(success, n)} |")
    lines.append(f"| Assistant asked a question (selection / confirmation) | {asked} | {pct(asked, n)} |")
    lines.append(f"| Cancelled by the user | {cancelled} | {pct(cancelled, n)} |")
    lines.append(f"| Not understood (intent = unknown) | {unknown} | {pct(unknown, n)} |")
    lines.append(f"| Understood but failed (wrong app focused, nothing found, …) | {errors - unknown} | {pct(errors - unknown, n)} |")
    lines.append("")
    lines.append("| Language (as recognised) | Commands |")
    lines.append("|---|---:|")
    for k, v in langs.most_common():
        lines.append(f"| {k} | {v} |")
    lines.append("")
    lines.append("| Intent | Commands | Succeeded |")
    lines.append("|---|---:|---:|")
    for k, v in intents.most_common():
        ok = sum(1 for r in recs if r.get("intent") == k and r.get("status") == "success")
        lines.append(f"| {k} | {v} | {ok} |")

    tr = [r["transcription_ms"] for r in recs if isinstance(r.get("transcription_ms"), (int, float))]
    cm = [r["command_ms"] for r in recs if isinstance(r.get("command_ms"), (int, float))]
    au = [r["audio_seconds"] for r in recs if isinstance(r.get("audio_seconds"), (int, float))]
    lines.append("")
    lines.append("| Timing (median) | Value |")
    lines.append("|---|---:|")
    lines.append(f"| Utterance length | {median(au):.2f} s |")
    lines.append(f"| Speech recognition | {median(tr):.0f} ms |")
    lines.append(f"| Parse + act | {median(cm):.0f} ms |")
    if tr and cm:
        share = 100.0 * sum(tr) / (sum(tr) + sum(cm))
        lines.append(f"| Share of latency spent in speech recognition | {share:.0f}% |")
    if tr and au:
        rtfs = [t / 1000.0 / a for t, a in zip(tr, au) if a]
        lines.append(f"| Real-time factor in use (median) | {median(rtfs):.2f}x |")

    misses = [r for r in recs if r.get("intent") == "unknown" or
              (r.get("intent") == "browser_navigation" and not (r.get("slots") or {}).get("action"))]
    lines.append("")
    lines.append(f"Transcripts the parser did not understand ({len(misses)}):")
    for r in misses:
        lines.append(f"- «{r.get('transcript')}»")

    if args.replay:
        from guya.assistant.parser import CommandParser
        parser = CommandParser()
        fixed = []
        for r in misses:
            p = parser.parse(r.get("transcript") or "")
            if p.intent not in ("unknown",) and not (p.intent == "browser_navigation" and not p.slots.get("action")):
                fixed.append((r.get("transcript"), p.intent, p.slots))
        lines.append("")
        lines.append(f"Re-parsed with the current parser: {len(fixed)} of {len(misses)} are now understood.")
        for t, i, s in fixed:
            lines.append(f"- «{t}» → {i} {s}")

    report = "\n".join(lines)
    print(report)
    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out + ".md", "w", encoding="utf-8") as f:
            f.write(report + "\n")
        with open(args.out + ".json", "w", encoding="utf-8") as f:
            json.dump(recs, f, ensure_ascii=False, indent=1)
        print(f"\n✓ wrote {args.out}.md and {args.out}.json")


if __name__ == "__main__":
    main()
