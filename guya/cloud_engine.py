"""
Cloud (online) speech-to-text engine for Guya.

The offline path runs Whisper locally. This module is the online fallback for
machines too weak to run a good offline model: it sends the recorded audio to a
hosted Whisper API and returns the text.

Default provider: Groq (free tier, runs whisper-large-v3 — same model family as
offline, so Persian quality is high). The request shape was validated by hand
against the live API before building this:

    POST https://api.groq.com/openai/v1/audio/transcriptions
    Authorization: Bearer <key>
    multipart: file=<wav>, model=whisper-large-v3, language=fa
    -> {"text": "..."}

Privacy: audio leaves the device and is sent to the provider. The offline path
stays fully private; this is the trade-off for running a big model on weak
hardware.
"""

import io
import wave
import logging

import numpy as np

log = logging.getLogger("Guya")

try:
    import httpx
except ImportError:  # httpx ships as a faster-whisper/huggingface dependency
    httpx = None


# ============================================================
# PROVIDERS
# ============================================================

PROVIDERS = {
    "groq": {
        "name": "Groq",
        "url": "https://api.groq.com/openai/v1/audio/transcriptions",
        "model": "whisper-large-v3",
        "signup": "https://console.groq.com/keys",
        "free": True,
    },
}
DEFAULT_PROVIDER = "groq"


# ============================================================
# AUDIO ENCODING
# ============================================================

def audio_to_wav_bytes(audio_float32: np.ndarray, sample_rate: int = 16000) -> bytes:
    """Encode float32 [-1,1] mono audio as 16-bit PCM WAV bytes (in memory)."""
    int16 = np.clip(audio_float32 * 32768.0, -32768, 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(int16.tobytes())
    return buf.getvalue()


# ============================================================
# TRANSCRIPTION
# ============================================================

class CloudError(Exception):
    """Raised when a cloud transcription request fails."""


def transcribe(audio_float32: np.ndarray, language: str, api_key: str,
               provider: str = DEFAULT_PROVIDER, sample_rate: int = 16000,
               timeout: float = 30.0) -> str:
    """Send audio to the cloud provider and return the raw transcription text.

    Raises CloudError on any failure (bad key, no internet, API error).
    """
    if httpx is None:
        raise CloudError("httpx is not installed")
    if not api_key:
        raise CloudError("No API key configured")
    prov = PROVIDERS.get(provider or DEFAULT_PROVIDER)
    if prov is None:
        raise CloudError(f"Unknown provider: {provider}")

    wav = audio_to_wav_bytes(audio_float32, sample_rate)
    files = {"file": ("audio.wav", wav, "audio/wav")}
    data = {"model": prov["model"], "response_format": "json"}
    # Persian / English are forced; "dual" lets the model auto-detect.
    if language in ("fa", "en"):
        data["language"] = language
    headers = {"Authorization": f"Bearer {api_key}"}

    try:
        resp = httpx.post(prov["url"], headers=headers, data=data, files=files,
                          timeout=timeout)
    except httpx.ConnectError:
        raise CloudError("No internet connection")
    except httpx.TimeoutException:
        raise CloudError("Request timed out")
    except Exception as e:
        raise CloudError(f"Network error: {e}")

    if resp.status_code == 401:
        raise CloudError("Invalid API key")
    if resp.status_code == 429:
        raise CloudError("Rate limit reached — try again shortly")
    if resp.status_code >= 400:
        raise CloudError(f"API error {resp.status_code}: {resp.text[:120]}")

    try:
        return resp.json().get("text", "").strip()
    except Exception:
        raise CloudError("Unexpected response from provider")


def test_connection(api_key: str, provider: str = DEFAULT_PROVIDER) -> tuple:
    """Verify the API key works by sending a tiny clip.

    Returns (ok: bool, message: str).
    """
    # 1 second of very low-amplitude noise = valid audio that confirms auth.
    rng = np.random.default_rng(0)
    audio = (rng.standard_normal(16000).astype("float32")) * 0.01
    try:
        transcribe(audio, "en", api_key, provider=provider, timeout=20.0)
        return True, "Connection OK — your key works."
    except CloudError as e:
        return False, str(e)
    except Exception as e:
        return False, str(e)
