"""
Record a short clip from the microphone into a 16 kHz mono WAV file.
Used to test the cloud STT path before building M4.

    python tools/record_sample.py [seconds] [outfile]

Defaults: 5 seconds -> /tmp/guya_test.wav
"""
import sys
import wave
import pyaudio

SECONDS = float(sys.argv[1]) if len(sys.argv) > 1 else 5.0
OUT = sys.argv[2] if len(sys.argv) > 2 else "/tmp/guya_test.wav"

RATE = 16000
CHUNK = 1024

pa = pyaudio.PyAudio()
stream = pa.open(format=pyaudio.paInt16, channels=1, rate=RATE,
                 input=True, frames_per_buffer=CHUNK)

print(f"🎙  Recording {SECONDS:g}s — speak now (Persian or English)…")
frames = []
for _ in range(int(RATE / CHUNK * SECONDS)):
    frames.append(stream.read(CHUNK, exception_on_overflow=False))
print("✓ done recording.")

stream.stop_stream()
stream.close()
pa.terminate()

with wave.open(OUT, "wb") as wf:
    wf.setnchannels(1)
    wf.setsampwidth(pa.get_sample_size(pyaudio.paInt16))
    wf.setframerate(RATE)
    wf.writeframes(b"".join(frames))

print(f"✓ saved WAV -> {OUT}")
