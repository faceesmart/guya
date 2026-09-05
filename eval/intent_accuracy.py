"""
Held-out intent accuracy for the rule-based assistant parser.

The unit tests prove that the phrase packs have no intent collisions, which is
useful but circular — they test the packs against themselves. This script
measures how the parser generalises to phrasings it has never seen:
eval/data/intents.jsonl holds natural Persian and English commands written
independently of the packs (rows that happen to coincide with a pack phrase
are flagged "in_pack" and reported separately).

Each row: {"lang", "text", "intent", "slots"?, "steps"?, "note"?, "in_pack"?}
  intent  a string, or a list of acceptable strings (e.g. an out-of-scope
          request may be "unknown" or a harmless intent, but never a click)
  slots   only the listed slots are checked; a value may be a list of
          acceptable alternatives. Comparison is on normalised text.
  steps   for "sequence": the expected intent of each step, in order.

Usage:
    python eval/intent_accuracy.py                       # prints the table
    python eval/intent_accuracy.py --tag after --out eval/results/intents_after
    python eval/intent_accuracy.py --failures            # list every miss

No audio, no model: this is text in, intent out, so it runs in well under a
second and is safe to put in CI.
"""

import argparse
import json
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from guya.assistant.normalizer import normalize  # noqa: E402
from guya.assistant.parser import CommandParser  # noqa: E402


def load(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def as_list(value):
    return value if isinstance(value, list) else [value]


def judge(parser, row):
    """Return (intent_ok, slots_ok, parsed) for one row."""
    parsed = parser.parse(row["text"])
    intent_ok = parsed.intent in as_list(row["intent"])
    slots_ok = True
    if intent_ok and row.get("steps"):
        got = [s.intent for s in parsed.steps]
        slots_ok = got == row["steps"]
    if intent_ok and row.get("slots"):
        for key, expected in row["slots"].items():
            got = normalize(parsed.slots.get(key, ""))
            if got not in {normalize(v) for v in as_list(expected)}:
                slots_ok = False
    return intent_ok, slots_ok, parsed


def summarise(rows, results):
    """Aggregate by language and by expected intent."""
    by = defaultdict(lambda: {"n": 0, "intent": 0, "full": 0})

    def bump(key, intent_ok, full_ok):
        b = by[key]; b["n"] += 1; b["intent"] += intent_ok; b["full"] += full_ok

    for row, (intent_ok, slots_ok, _p) in zip(rows, results):
        full_ok = intent_ok and slots_ok
        bump(("lang", row["lang"]), intent_ok, full_ok)
        bump(("intent", as_list(row["intent"])[0]), intent_ok, full_ok)
        bump(("all", "all"), intent_ok, full_ok)
    return by


def pct(a, b):
    return f"{100.0 * a / b:.1f}%" if b else "—"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="eval/data/intents.jsonl")
    ap.add_argument("--tag", default="")
    ap.add_argument("--out", default=None, help="write <out>.md and <out>.json")
    ap.add_argument("--failures", action="store_true")
    ap.add_argument("--include-pack", action="store_true",
                    help="also count rows that coincide with a phrase-pack entry")
    args = ap.parse_args()

    rows = load(args.data)
    parser = CommandParser()
    # The partition is computed, not trusted: any row whose normalised text
    # equals a phrase-pack entry is a pack row, whatever the file says.
    pack_phrases = set()
    for phrases in parser.phrases.values():
        for examples in phrases.values():
            pack_phrases.update(normalize(x) for x in examples)
    for r in rows:
        r["in_pack"] = bool(r.get("in_pack")) or normalize(r["text"]) in pack_phrases
    results = [judge(parser, r) for r in rows]

    held = [(r, x) for r, x in zip(rows, results) if not r.get("in_pack")]
    pack = [(r, x) for r, x in zip(rows, results) if r.get("in_pack")]
    scored = held + pack if args.include_pack else held

    by = summarise([r for r, _ in scored], [x for _, x in scored])
    lines = []
    title = f"Intent accuracy{(' — ' + args.tag) if args.tag else ''} ({len(scored)} held-out rows"
    title += f", {len(pack)} pack rows {'included' if args.include_pack else 'excluded'})"
    lines.append(title)
    lines.append("")
    lines.append("| Group | n | Intent correct | Intent + slots correct |")
    lines.append("|---|---:|---:|---:|")
    order = [("all", "all"), ("lang", "en"), ("lang", "fa")]
    for key in order:
        b = by[key]
        label = {"all": "All", "en": "English", "fa": "Persian"}[key[1]]
        lines.append(f"| {label} | {b['n']} | {pct(b['intent'], b['n'])} | {pct(b['full'], b['n'])} |")
    lines.append("")
    lines.append("| Intent | n | Intent correct | Intent + slots correct |")
    lines.append("|---|---:|---:|---:|")
    for key in sorted(k for k in by if k[0] == "intent"):
        b = by[key]
        lines.append(f"| {key[1]} | {b['n']} | {pct(b['intent'], b['n'])} | {pct(b['full'], b['n'])} |")
    if pack:
        bp = summarise([r for r, _ in pack], [x for _, x in pack])[("all", "all")]
        lines.append("")
        lines.append(f"Phrase-pack rows (sanity, not generalisation): {bp['n']} rows, "
                     f"{pct(bp['intent'], bp['n'])} intent, {pct(bp['full'], bp['n'])} intent+slots.")
    report = "\n".join(lines)
    print(report)

    failures = []
    for row, (intent_ok, slots_ok, parsed) in scored:
        if not (intent_ok and slots_ok):
            failures.append({
                "lang": row["lang"], "text": row["text"],
                "expected": row["intent"], "expected_slots": row.get("slots"), "expected_steps": row.get("steps"),
                "got": parsed.intent, "got_slots": parsed.slots,
                "got_steps": [s.intent for s in parsed.steps] or None,
                "kind": "intent" if not intent_ok else "slots",
                "note": row.get("note"),
            })
    if args.failures:
        print(f"\n{len(failures)} failures:")
        for f in failures:
            exp = f["expected"] if not f["expected_slots"] else f"{f['expected']} {f['expected_slots']}"
            got = f["got"] if not f["got_slots"] else f"{f['got']} {f['got_slots']}"
            print(f"  [{f['lang']}] {f['text']!r}\n      expected {exp}\n      got      {got}" + (f"  ({f['note']})" if f["note"] else ""))

    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out + ".md", "w", encoding="utf-8") as f:
            f.write(report + "\n")
        with open(args.out + ".json", "w", encoding="utf-8") as f:
            json.dump({"tag": args.tag, "n": len(scored),
                       "summary": {f"{k[0]}:{k[1]}": v for k, v in by.items()},
                       "failures": failures}, f, ensure_ascii=False, indent=1)
        print(f"\n✓ wrote {args.out}.md and {args.out}.json")


if __name__ == "__main__":
    main()
