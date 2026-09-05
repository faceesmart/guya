"""
Guya configuration system.

A single JSON file at ~/.guya/config.json holds every user choice made in the
setup wizard: which model, which device/backend, default language, push-to-talk
key, and UI style. The widget reads this on startup instead of hardcoded
constants.

Rule that drives first-run vs. normal-run:
    config exists  -> launch the widget with these settings
    config missing -> launch the setup wizard

Config lives in the user's home (~/.guya), NOT next to the app, so it:
  * survives app updates / re-downloads,
  * is always writable (no admin / no TCC-protected folder issues),
  * is per-user.
"""

import os
import json
import copy
import logging

log = logging.getLogger("Guya")

# ============================================================
# LOCATION
# ============================================================

CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".guya")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")

CONFIG_VERSION = 1

# ============================================================
# DEFAULTS
# ============================================================
# These mirror the values the original widget used. The wizard overwrites the
# parts the user configures; anything the wizard doesn't touch falls back here.

DEFAULT_CONFIG = {
    "version": CONFIG_VERSION,

    # Speech-to-text model + how to run it.
    "model": {
        "backend": "faster-whisper",   # "faster-whisper" (offline) | "cloud" (online)
        "size": "large-v3-turbo",      # tiny|base|small|medium|large-v3|large-v3-turbo
        "device": "auto",              # "auto"|"cuda"|"cpu"  (auto = detect at load)
        "compute_type": "auto",        # "auto"|"float16"|"int8"|"int8_float16"
    },

    # Online provider. Used when model.backend == "cloud" (online-only) OR, in
    # hybrid mode, alongside an offline model when "enabled" is true — letting
    # the widget switch between offline and online while running.
    "cloud": {
        "provider": None,              # e.g. "openai" | "groq" | "deepgram"
        "api_key": None,
        "enabled": False,              # hybrid: offline + online both available
    },

    # Default transcription language. "fa"=Persian, "en"=English, "dual"=bilingual.
    "language": "fa",

    # Push-to-talk hotkey.
    #   Windows: vk is a virtual-key code (e.g. 0x47 'G' = 71, Right Ctrl = 162).
    #   macOS:   we use Right Option; vk is ignored, name drives behavior.
    "hotkey": {
        "vk": 71,                      # default 'G' on Windows
        "name": "G",
        "label": "G",
    },

    # Limited local assistant. It reuses speech-to-text but has its own key.
    # Commands are parsed locally and may only touch these user folders.
    "assistant": {
        "enabled": True,
        "hotkey": {
            "vk": 119,                 # F8 on Windows
            "name": "F8",
            "label": "F8",
        },
        # Recognition follows the live FA / EN / DUAL widget badge.
        "allowed_roots": ["~/Desktop", "~/Documents", "~/Downloads"],
        "default_directory": "~/Documents",
        "speak_feedback": True,
    },

    # Widget appearance.
    "ui": {
        "style": "pill",              # "pill" (expand/collapse) | "minimal" (future 2nd UI)
    },

    # Audio capture (rarely changed).
    "audio": {
        "sample_rate": 16000,
        "chunk_size": 1024,
        "realtime_chunk_sec": 2.0,
    },

    # Behavior timings (rarely changed).
    "behavior": {
        "min_recording_duration": 0.4,
        "done_state_duration_ms": 1500,
        "type_delay_ms": 100,
        "animation_fps": 30,
    },
}


# ============================================================
# LOAD / SAVE
# ============================================================

def config_exists() -> bool:
    """True if a saved config is present (i.e. setup has been completed)."""
    return os.path.isfile(CONFIG_PATH)


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into a copy of base (override wins).

    Used so that a config file written by an older version still gets any new
    default keys filled in, instead of crashing on a missing key.
    """
    result = copy.deepcopy(base)
    for key, val in (override or {}).items():
        if isinstance(val, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], val)
        else:
            result[key] = val
    return result


def load_config() -> dict:
    """Load config.json merged over defaults. Returns defaults if no file."""
    if not config_exists():
        log.info("No config found; using defaults (setup not completed).")
        return copy.deepcopy(DEFAULT_CONFIG)
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            user_cfg = json.load(f)
        merged = _deep_merge(DEFAULT_CONFIG, user_cfg)
        log.info(f"Loaded config from {CONFIG_PATH}")
        return merged
    except Exception as e:
        log.error(f"Failed to read {CONFIG_PATH}: {e}. Falling back to defaults.")
        return copy.deepcopy(DEFAULT_CONFIG)


def save_config(cfg: dict) -> bool:
    """Write config to ~/.guya/config.json. Creates the dir if needed."""
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        # Always stamp the current version on save.
        cfg = _deep_merge(DEFAULT_CONFIG, cfg)
        cfg["version"] = CONFIG_VERSION
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        try:
            # The file may hold a cloud API key: owner-only.
            os.chmod(CONFIG_PATH, 0o600)
        except OSError:
            pass
        log.info(f"Saved config to {CONFIG_PATH}")
        return True
    except Exception as e:
        log.error(f"Failed to write {CONFIG_PATH}: {e}")
        return False


def reset_config() -> None:
    """Delete the saved config (forces the wizard to run again next launch)."""
    try:
        if config_exists():
            os.remove(CONFIG_PATH)
            log.info("Config reset (deleted).")
    except Exception as e:
        log.error(f"Failed to reset config: {e}")
