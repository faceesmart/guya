"""
On-device speech-to-text benchmark + latency-aware model recommendation.

This is Guya's core research contribution: rather than guessing a model from
hardware specs (which are unreliable — a 16 GB Mac and a 16 GB GPU-less PC
behave very differently), we MEASURE the device.

Method:
  1. Run a small proxy model (`base`) on a fixed synthetic audio clip on the
     device's real backend (CUDA or CPU) and measure its real-time factor
        RTF = processing_time / audio_duration       (lower = faster).
  2. Predict the RTF of each candidate model by scaling the proxy RTF with a
     calibrated per-model compute-cost factor.
  3. Recommend the largest (most accurate) model whose PREDICTED RTF stays
     under a latency budget — so the user gets the best accuracy that still
     feels responsive on *their* machine.

Run as a subprocess (`python -m guya.benchmark ...`) so it loads the model in a
clean, Qt-free process — required on Windows where importing Qt before the
CTranslate2 CUDA backend can segfault.
"""

import os
import sys
import json
import time
import logging

log = logging.getLogger("Guya")

# ============================================================
# CALIBRATION
# ============================================================
# Compute cost of each model RELATIVE TO `base` (= 1.0). These are calibrated
# estimates from public faster-whisper benchmarks; a strength of this approach
# (and a good capstone evaluation task) is refining them with real measurements
# on the target machines. Roughly tracks parameter count, with `turbo` cheaper
# than its size suggests because it has only 4 decoder layers.
RELATIVE_COST = {
    "tiny": 0.5,
    "base": 1.0,
    "small": 2.6,
    "medium": 7.0,
    "large-v3": 14.0,
    # turbo has the full large encoder but only 4 decoder layers, so it is far
    # cheaper than large-v3 and roughly between small and medium in total cost.
    "large-v3-turbo": 4.0,
}

# Quality ordering (higher = more accurate). NOT the same as cost: large-v3-turbo
# is more accurate than `medium` despite costing less, so we must rank by quality
# explicitly when choosing "the most accurate model that fits the latency budget".
ACCURACY_RANK = {
    "tiny": 1,
    "base": 2,
    "small": 3,
    "medium": 4,
    "large-v3-turbo": 5,
    "large-v3": 6,
}

PROXY_MODEL = "tiny"          # smallest model (~75 MB) — fastest to fetch + run
PROXY_AUDIO_SEC = 5.0         # length of the synthetic benchmark clip

# Latency budget, expressed as real-time factor for a typical utterance.
#   <= COMFORTABLE  → feels responsive (transcription ≤ utterance length)
#   <= ACCEPTABLE   → usable, noticeably slower
COMFORTABLE_RTF = 1.0
ACCEPTABLE_RTF = 2.0

# Per-language quality floor: the minimum model (by ACCURACY_RANK) that gives
# acceptable accuracy for that language. English is good even on `small`;
# Persian degrades badly below `large-v3-turbo`, so Persian/bilingual users
# must not be recommended anything weaker than turbo.
LANGUAGE_FLOOR_RANK = {
    "en": ACCURACY_RANK["small"],            # 3
    "fa": ACCURACY_RANK["large-v3-turbo"],   # 5
    "dual": ACCURACY_RANK["large-v3-turbo"], # 5 (Persian is the binding constraint)
}


# ============================================================
# THE BENCHMARK (runs in a subprocess)
# ============================================================

BENCH_CLIP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "bench_speech.wav")


def _benchmark_audio(audio_sec: float):
    """The clip the proxy model is timed on.

    Real speech (a bundled 7 s English sentence) is used, not noise: on noise
    Whisper fails its own quality checks and retries at rising temperatures,
    so the measured time reflects decoder retries rather than device speed
    (measured on an M1 Pro: 2x spread between runs, and every run slower than
    the machine's real large-v3-turbo RTF). Noise is kept only as a fallback
    when the asset is missing.
    """
    import numpy as np
    if os.path.exists(BENCH_CLIP):
        from faster_whisper.audio import decode_audio
        return decode_audio(BENCH_CLIP, sampling_rate=16000), "speech"
    rng = np.random.default_rng(0)
    return (rng.standard_normal(int(16000 * audio_sec)).astype("float32")) * 0.05, "noise"


def run_proxy_benchmark(device: str, compute_type: str,
                        proxy: str = PROXY_MODEL,
                        audio_sec: float = PROXY_AUDIO_SEC,
                        repeats: int = 2) -> dict:
    """Load the proxy model, transcribe a fixed clip, return the RTF."""
    from faster_whisper import WhisperModel

    audio, clip_kind = _benchmark_audio(audio_sec)
    audio_sec = len(audio) / 16000.0

    kwargs = {"device": device, "compute_type": compute_type}
    if device == "cpu":
        kwargs["cpu_threads"] = 0  # use all cores
    model = WhisperModel(proxy, **kwargs)

    # Same decoding settings the widget uses for a single-language pass, with
    # temperature fallback off so the time is the device's, not the decoder's.
    decode = dict(language="en", beam_size=5, temperature=0.0, vad_filter=False,
                  condition_on_previous_text=False)

    # Warm-up: the first transcribe pays one-time init costs we don't want to
    # measure. Run a short throwaway pass first.
    list(model.transcribe(audio[:16000], **decode)[0])

    timings = []
    for _ in range(max(1, repeats)):
        t0 = time.perf_counter()
        segments, _ = model.transcribe(audio, **decode)
        list(segments)  # force the lazy generator to actually run
        timings.append(time.perf_counter() - t0)
    elapsed = min(timings)  # the best run is the least disturbed one

    return {
        "proxy": proxy,
        "device": device,
        "compute_type": compute_type,
        "clip": clip_kind,
        "audio_sec": round(audio_sec, 2),
        "elapsed": round(elapsed, 3),
        "runs": [round(t, 3) for t in timings],
        "rtf_base": round(elapsed / audio_sec, 4),
    }


# ============================================================
# PREDICTION + RECOMMENDATION
# ============================================================

def predict_rtf(rtf_base: float, model_size: str) -> float:
    """Predict a model's RTF on this device from the proxy RTF."""
    factor = RELATIVE_COST.get(model_size, RELATIVE_COST["medium"]) / RELATIVE_COST[PROXY_MODEL]
    return rtf_base * factor


def annotate_and_recommend(options: list, rtf_base: float,
                           language: str = "fa",
                           utterance_sec: float = 10.0) -> list:
    """Given the wizard's model options, the measured proxy RTF, and the user's
    language preference:

      * add predicted_rtf and predicted_latency_sec to every offline option, and
      * mark `recommended` = the most accurate OFFLINE model that (a) meets the
        language's quality floor, (b) fits the latency budget, and (c) is
        enabled for this hardware. If none qualifies, recommend CLOUD — full
        accuracy with no local compute (exactly the weak-device + Persian case).

    Returns the same list, mutated.
    """
    for o in options:
        if o["backend"] == "cloud":
            o["predicted_rtf"] = None
            o["predicted_latency_sec"] = None
        else:
            rtf = predict_rtf(rtf_base, o["model_size"])
            o["predicted_rtf"] = round(rtf, 2)
            o["predicted_latency_sec"] = round(rtf * utterance_sec, 1)

    floor = LANGUAGE_FLOOR_RANK.get(language, LANGUAGE_FLOOR_RANK["fa"])

    # Offline candidates that are enabled AND meet the language quality floor.
    candidates = [
        o for o in options
        if o["backend"] != "cloud" and o["enabled"]
        and ACCURACY_RANK.get(o["model_size"], 0) >= floor
    ]
    for o in options:
        o["recommended"] = False

    # Most accurate first.
    by_accuracy = sorted(candidates,
                         key=lambda o: ACCURACY_RANK.get(o["model_size"], 0),
                         reverse=True)

    # One budget, applied once: the most accurate model predicted to run at or
    # under real time. A two-tier budget (comfortable, then acceptable) was
    # non-monotonic — a slightly slower machine could be told to run a bigger,
    # slower model — so it was replaced by a single threshold.
    chosen = None
    for o in by_accuracy:
        if o["predicted_rtf"] is not None and o["predicted_rtf"] <= COMFORTABLE_RTF:
            chosen = o
            break
    for o in options:
        if o["backend"] != "cloud" and o.get("predicted_rtf") is not None:
            o["latency_label"] = (
                "comfortable" if o["predicted_rtf"] <= COMFORTABLE_RTF
                else "slow" if o["predicted_rtf"] <= ACCEPTABLE_RTF
                else "too slow"
            )

    # Nothing offline is both accurate-enough AND fast-enough → go online.
    if chosen is not None:
        chosen["recommended"] = True
    else:
        for o in options:
            if o["backend"] == "cloud":
                o["recommended"] = True

    return options


# ============================================================
# SUBPROCESS ENTRY POINT
# ============================================================

def _main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--compute", default="int8")
    ap.add_argument("--proxy", default=PROXY_MODEL)
    args = ap.parse_args()

    try:
        result = run_proxy_benchmark(args.device, args.compute, args.proxy)
        # Single machine-readable line the wizard parses.
        print("BENCH_JSON:" + json.dumps(result))
    except Exception as e:
        print("BENCH_ERROR:" + str(e), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    _main()
