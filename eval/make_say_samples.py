"""
Generate a small ENGLISH validation set with macOS `say` (text-to-speech) so the
accuracy harness can be exercised end-to-end immediately.

NOTE: TTS speech is unrealistically clean, so WER will be very low for every
model — this validates the *pipeline*, not the research result. The real
evaluation uses human speech (record clips, or fetch Common Voice / FLEURS); see
eval/README.md.
"""

import json
import os
import subprocess

SENTENCES = [
    "The quick brown fox jumps over the lazy dog.",
    "Please send me the report by tomorrow morning.",
    "Artificial intelligence is changing how we work and communicate.",
    "I would like a cup of coffee with a little bit of milk.",
    "She sells seashells by the seashore on a sunny afternoon.",
    "Our meeting is scheduled for three o'clock next Thursday.",
    "The weather today is cold, windy, and slightly rainy.",
    "Thank you very much for your help with this project.",
    "He bought twelve apples and three oranges at the market.",
    "Learning a new language takes patience, practice, and time.",
]


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    data = os.path.join(here, "data")
    os.makedirs(data, exist_ok=True)
    manifest = os.path.join(data, "say_manifest.jsonl")
    with open(manifest, "w", encoding="utf-8") as mf:
        for i, text in enumerate(SENTENCES):
            aiff = os.path.join(data, f"say_en_{i:02d}.aiff")
            subprocess.run(["say", "-v", "Samantha", "-o", aiff, text], check=True)
            mf.write(json.dumps({"audio": f"say_en_{i:02d}.aiff", "text": text,
                                 "lang": "en"}, ensure_ascii=False) + "\n")
            print(f"  ✓ {os.path.basename(aiff)}")
    print(f"\n✓ wrote {len(SENTENCES)} clips + {manifest}")


if __name__ == "__main__":
    main()
