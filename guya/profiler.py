"""
Device profiling + model recommendation for the Guya setup wizard.

Two jobs:
  1. get_device_profile()  — inspect the machine (CPU, RAM, GPU/CUDA).
  2. recommend_models()    — turn that profile into a short list of options
                             the wizard shows the user, with one marked as
                             recommended.

NOTE: M2 uses a spec-based heuristic. Milestone 3 replaces the recommendation
with an on-device micro-benchmark (transcribe a sample, measure real-time
factor) — the capstone's research contribution. The interface stays the same.
"""

import sys
import platform
import subprocess
import logging

log = logging.getLogger("Guya")

IS_WIN = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"


# ============================================================
# DEVICE PROFILE
# ============================================================

def _cpu_name() -> str:
    """Human-readable CPU name, best effort per OS."""
    try:
        if IS_MAC:
            out = subprocess.run(
                ["sysctl", "-n", "machdep.cpu.brand_string"],
                capture_output=True, text=True, timeout=2,
            )
            if out.stdout.strip():
                return out.stdout.strip()
        elif IS_WIN:
            name = platform.processor()
            if name:
                return name
        else:  # Linux
            try:
                with open("/proc/cpuinfo") as f:
                    for line in f:
                        if "model name" in line:
                            return line.split(":", 1)[1].strip()
            except Exception:
                pass
    except Exception:
        pass
    return platform.processor() or platform.machine() or "Unknown CPU"


def _probe_cuda():
    """Probe for an NVIDIA CUDA GPU (usable by faster-whisper).

    Returns (has_cuda, gpu_name, vram_gb). Only Windows/Linux with NVIDIA can
    use CUDA here — macOS has no CUDA and faster-whisper has no Metal backend.
    """
    if IS_MAC:
        return (False, None, 0.0)
    try:
        import ctypes
        lib = "nvcuda.dll" if IS_WIN else "libcuda.so"
        cuda = ctypes.CDLL(lib)
        if cuda.cuInit(0) != 0:
            return (False, None, 0.0)
        count = ctypes.c_int(0)
        cuda.cuDeviceGetCount(ctypes.byref(count))
        if count.value == 0:
            return (False, None, 0.0)
        name_buf = ctypes.create_string_buffer(256)
        cuda.cuDeviceGetName(name_buf, 256, 0)
        gpu_name = name_buf.value.decode("utf-8", errors="replace")
        mem = ctypes.c_size_t(0)
        cuda.cuDeviceTotalMem_v2(ctypes.byref(mem), 0)
        return (True, gpu_name, mem.value / (1024 ** 3))
    except (OSError, AttributeError):
        return (False, None, 0.0)


def get_device_profile() -> dict:
    """Inspect the machine and return a profile dict."""
    prof = {
        "os": platform.system(),
        "machine": platform.machine(),
        "cpu_name": _cpu_name(),
        "cpu_cores": None,
        "cpu_threads": None,
        "ram_gb": None,
        "has_cuda": False,
        "gpu_name": None,
        "vram_gb": 0.0,
        "apple_silicon": IS_MAC and platform.machine() == "arm64",
    }

    try:
        import psutil
        prof["cpu_cores"] = psutil.cpu_count(logical=False) or psutil.cpu_count()
        prof["cpu_threads"] = psutil.cpu_count(logical=True)
        prof["ram_gb"] = round(psutil.virtual_memory().total / (1024 ** 3), 1)
    except Exception as e:
        log.warning(f"psutil unavailable: {e}")

    has_cuda, gpu_name, vram = _probe_cuda()
    prof["has_cuda"] = has_cuda
    prof["gpu_name"] = gpu_name
    prof["vram_gb"] = round(vram, 1)

    log.info(f"Device profile: {prof}")
    return prof


# ============================================================
# MODEL RECOMMENDATION (spec-based heuristic for M2)
# ============================================================
#
# Tiers map to faster-whisper model sizes. Quality (esp. Persian) increases
# with size; speed decreases. The "recommended" flag is the wizard's default.

def recommend_models(profile: dict) -> list:
    """Return a list of option dicts for the wizard, one marked recommended.

    Each option:
        id, title, subtitle, model_size, backend, device, recommended,
        enabled, note
    """
    ram = profile.get("ram_gb") or 0
    has_cuda = profile.get("has_cuda")
    vram = profile.get("vram_gb") or 0
    apple = profile.get("apple_silicon")

    options = []

    # ---- Offline: Accurate (large-v3) ----
    if has_cuda and vram >= 4:
        accurate_note = f"Uses your GPU ({profile.get('gpu_name','GPU')})"
        accurate_device = "cuda"
        accurate_enabled = True
        accurate_rec = True
    elif apple or ram >= 16:
        accurate_note = "Runs on CPU — most accurate but slower"
        accurate_device = "cpu"
        accurate_enabled = True
        accurate_rec = apple  # on Apple Silicon, large is the quality pick
    else:
        accurate_note = "Needs a strong GPU or 16 GB+ RAM"
        accurate_device = "cpu"
        accurate_enabled = ram >= 8
        accurate_rec = False
    options.append({
        "id": "accurate",
        "title": "Accurate",
        "subtitle": "large-v3 · best quality (Persian & English)",
        "model_size": "large-v3",
        "backend": "faster-whisper",
        "device": accurate_device,
        "recommended": accurate_rec,
        "enabled": accurate_enabled,
        "note": accurate_note,
    })

    # ---- Offline: Balanced (medium) ----
    bal_device = "cuda" if has_cuda else "cpu"
    options.append({
        "id": "balanced",
        "title": "Balanced",
        "subtitle": "medium · good quality, faster",
        "model_size": "medium",
        "backend": "faster-whisper",
        "device": bal_device,
        "recommended": (not has_cuda) and ram >= 8 and not apple,
        "enabled": ram >= 6,
        "note": "Uses your GPU" if has_cuda else "Runs on CPU",
    })

    # ---- Offline: Fast (small) ----
    fast_device = "cuda" if has_cuda else "cpu"
    options.append({
        "id": "fast",
        "title": "Fast",
        "subtitle": "small · quickest offline, lower accuracy",
        "model_size": "small",
        "backend": "faster-whisper",
        "device": fast_device,
        "recommended": (not has_cuda) and ram < 8,
        "enabled": True,
        "note": "Good for weaker machines",
    })

    # ---- Online: Cloud ----
    options.append({
        "id": "cloud",
        "title": "Cloud (Online)",
        "subtitle": "runs on a server · needs internet",
        "model_size": "large-v3",
        "backend": "cloud",
        "device": "cloud",
        "recommended": False,
        "enabled": True,
        "note": "Best when your computer is too weak for offline models",
    })

    # Guarantee exactly one recommended option.
    if not any(o["recommended"] for o in options):
        for o in options:
            if o["enabled"]:
                o["recommended"] = True
                break

    return options
