"""
Build a Persian + English evaluation set from Google FLEURS (CC-BY-4.0).

FLEURS is read speech recorded by native speakers, with human transcripts. It
is the only openly downloadable Persian speech corpus that needs no account or
licence acceptance, so the numbers it produces are reproducible by anyone who
runs this script.

    python eval/import_fleurs.py                      # 60 fa + 60 en clips, dev split
    python eval/import_fleurs.py --per-lang 100 --split test

Output (default eval/data/fleurs/):
    manifest.jsonl          {"audio", "text", "lang", "id", "seconds"} per clip
    fa_ir/<id>.wav          the sampled 16 kHz mono clips
    en_us/<id>.wav
    _raw/                   the downloaded tar.gz + tsv (delete to reclaim space)

Sampling is deterministic (--seed). One clip per sentence, so no sentence is
counted twice even though FLEURS records each sentence by several speakers.

The audio is not committed to git (see .gitignore); re-run this script to
recreate the exact same set.
"""

import argparse
import csv
import json
import os
import random
import shutil
import sys
import tarfile
import urllib.request

HF = "https://huggingface.co/datasets/google/fleurs/resolve/main/data"
LANG_CODE = {"fa_ir": "fa", "en_us": "en"}


def fetch(url, dest):
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        return
    print(f"  downloading {os.path.basename(dest)} …")
    tmp = dest + ".part"
    with urllib.request.urlopen(url, timeout=60) as r, open(tmp, "wb") as f:
        shutil.copyfileobj(r, f, length=1 << 20)
    os.replace(tmp, dest)


def read_tsv(path):
    """FLEURS tsv: id, file, raw_transcription, transcription, chars, num_samples, gender."""
    rows = []
    with open(path, encoding="utf-8") as f:
        for r in csv.reader(f, delimiter="\t", quoting=csv.QUOTE_NONE):
            if len(r) < 6:
                continue
            rows.append({
                "sid": r[0], "file": r[1], "raw": r[2], "norm": r[3],
                "seconds": int(r[5]) / 16000.0,
                "gender": r[6] if len(r) > 6 else "",
            })
    return rows


def sample(rows, n, seed):
    by_sentence = {}
    for r in rows:
        by_sentence.setdefault(r["sid"], []).append(r)
    rng = random.Random(seed)
    sids = sorted(by_sentence)
    rng.shuffle(sids)
    chosen = []
    for sid in sids[:n]:
        clips = by_sentence[sid]
        chosen.append(clips[rng.randrange(len(clips))])
    return chosen


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--langs", default="fa_ir,en_us")
    ap.add_argument("--split", default="dev", choices=["dev", "test"])
    ap.add_argument("--per-lang", type=int, default=60)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default="eval/data/fleurs")
    ap.add_argument("--raw", default=None, help="where to keep downloads (default <out>/_raw)")
    args = ap.parse_args()

    raw_dir = args.raw or os.path.join(args.out, "_raw")
    os.makedirs(raw_dir, exist_ok=True)
    manifest_path = os.path.join(args.out, "manifest.jsonl")
    entries = []

    for lang in [l.strip() for l in args.langs.split(",") if l.strip()]:
        code = LANG_CODE[lang]
        print(f"▶ {lang} ({args.split})")
        tsv = os.path.join(raw_dir, f"{lang}.{args.split}.tsv")
        tgz = os.path.join(raw_dir, f"{lang}.{args.split}.tar.gz")
        fetch(f"{HF}/{lang}/{args.split}.tsv", tsv)
        fetch(f"{HF}/{lang}/audio/{args.split}.tar.gz", tgz)

        rows = read_tsv(tsv)
        chosen = sample(rows, args.per_lang, args.seed)
        wanted = {r["file"] for r in chosen}
        print(f"  {len(rows)} clips / {len({r['sid'] for r in rows})} sentences → sampling {len(chosen)}")

        out_dir = os.path.join(args.out, lang)
        os.makedirs(out_dir, exist_ok=True)
        missing = {f for f in wanted if not os.path.exists(os.path.join(out_dir, f))}
        if missing:
            with tarfile.open(tgz, "r:gz") as tar:
                for member in tar:
                    base = os.path.basename(member.name)
                    if base in missing and member.isfile():
                        with tar.extractfile(member) as src, open(os.path.join(out_dir, base), "wb") as dst:
                            shutil.copyfileobj(src, dst)
                        missing.discard(base)
                        if not missing:
                            break
        if missing:
            print(f"  ! {len(missing)} clips not found in the archive", file=sys.stderr)

        for r in chosen:
            if r["file"] in missing:
                continue
            entries.append({
                "audio": f"{lang}/{r['file']}",
                "text": r["raw"],
                "lang": code,
                "id": r["sid"],
                "seconds": round(r["seconds"], 2),
                "source": f"fleurs/{lang}/{args.split}",
            })

    with open(manifest_path, "w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    total = sum(e["seconds"] for e in entries)
    print(f"\n✓ wrote {manifest_path}: {len(entries)} clips, {total/60:.1f} min of audio")
    print("  next: python eval/accuracy.py --manifest", manifest_path,
          "--models tiny,base,small,medium,large-v3-turbo --pipeline raw")


if __name__ == "__main__":
    main()
