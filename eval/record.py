"""
Record a real test set for the accuracy evaluation.

Shows each sentence, you read it aloud, and it saves a 16 kHz wav + appends to a
manifest the harness can score. This is the most thesis-relevant data — real
human Persian/English speech, ideally including the target user (your brother).

Usage:
    python eval/record.py            # uses the built-in sentences
    python eval/record.py --speaker brother --out eval/data/brother

Then:
    python eval/accuracy.py --manifest eval/data/<...>/manifest.jsonl \
        --models small,large-v3-turbo --cloud
"""

import argparse
import json
import os
import threading
import wave

import pyaudio

RATE = 16000
CHUNK = 1024

SENTENCES = [
    ("سلام، حال شما چطور است؟", "fa"),
    ("لطفاً این پیام را برای من تایپ کن.", "fa"),
    ("هوش مصنوعی دارد دنیای ما را تغییر می‌دهد.", "fa"),
    ("من امروز ساعت سه یک جلسه‌ی مهم دارم.", "fa"),
    ("می‌خواهم یک قهوه با کمی شیر سفارش بدهم.", "fa"),
    ("نوشتن متن‌های طولانی با کیبورد برای من سخت است.", "fa"),
    ("ممنون که در این پروژه به من کمک کردی.", "fa"),
    ("دوازده کتاب و سه دفتر از کتاب‌فروشی خریدم.", "fa"),
    ("Please send me the report by tomorrow morning.", "en"),
    ("Thank you very much for your help with this project.", "en"),
]


def record_clip(pa, path):
    frames = []
    flag = {"on": True}
    stream = pa.open(format=pyaudio.paInt16, channels=1, rate=RATE,
                     input=True, frames_per_buffer=CHUNK)

    def loop():
        while flag["on"]:
            frames.append(stream.read(CHUNK, exception_on_overflow=False))

    t = threading.Thread(target=loop, daemon=True); t.start()
    input("   …recording — press Enter to STOP. ")
    flag["on"] = False; t.join(); stream.stop_stream(); stream.close()
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(RATE)
        w.writeframes(b"".join(frames))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="eval/data/recorded")
    ap.add_argument("--speaker", default="me")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    manifest = os.path.join(args.out, "manifest.jsonl")

    # Re-running for the same speaker replaces only the rows whose wav files
    # are actually re-recorded this session; everything else is kept, so a
    # Ctrl+C after two clips loses nothing.
    existing = []
    if os.path.exists(manifest):
        with open(manifest, encoding="utf-8") as mf:
            existing = [json.loads(line) for line in mf if line.strip()]

    pa = pyaudio.PyAudio()
    print(f"\nRecording {len(SENTENCES)} clips (speaker: {args.speaker}).")
    print("Read each sentence clearly. Ctrl+C to stop early.")
    print("Privacy: the recordings stay on this computer unless you later score them with --cloud.\n")
    rows = []
    try:
        for i, (text, lang) in enumerate(SENTENCES):
            print(f"[{i+1}/{len(SENTENCES)}] ({lang})  {text}")
            input("   Press Enter to START… ")
            fn = f"{args.speaker}_{i:02d}.wav"
            record_clip(pa, os.path.join(args.out, fn))
            rows.append({"audio": fn, "text": text, "lang": lang, "speaker": args.speaker})
            print("   ✓ saved\n")
    except KeyboardInterrupt:
        print("\nStopped early; keeping the clips recorded so far.")
    finally:
        pa.terminate()
    recorded = {row["audio"] for row in rows}
    kept = [row for row in existing if row.get("audio") not in recorded]
    with open(manifest, "w", encoding="utf-8") as mf:
        for row in kept + rows:
            mf.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"✓ wrote {len(rows)} clips + {manifest} ({len(kept) + len(rows)} rows)")


if __name__ == "__main__":
    main()
