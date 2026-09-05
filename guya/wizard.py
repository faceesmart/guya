"""
Guya setup wizard — bilingual (English / فارسی), device-aware.

Flow:
    Welcome → Language (which you speak) → Device (analyze + editable specs)
            → Mode (Offline / Online / Dual, with pros & cons)
            → Setup (per mode: pick offline model / connect online / set up both)
            → Key → Review → Download → launch

The wizard UI itself can be shown in English or Persian (toggle top-right),
right-to-left for Persian.
"""

import os
import sys
import glob
import json
import logging

try:
    from . import config as guya_config
    from . import profiler
    from . import benchmark
    from . import cloud_engine
    from . import launcher_gen
except ImportError:
    import config as guya_config
    import profiler
    import benchmark
    import cloud_engine
    import launcher_gen

log = logging.getLogger("Guya")

IS_WIN = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"
if IS_WIN:
    UI_FONT = "Segoe UI"
elif IS_MAC:
    UI_FONT = "Helvetica Neue"
else:
    UI_FONT = "DejaVu Sans"

# ---- palette: Calm Teal (dark, accessible — gentle for sensory sensitivity) ----
BG = "#0c1014"           # deep slate
BG2 = "#0f141a"          # subtle gradient partner for the window
CARD = "#16191f"
CARD_SEL = "#16302e"     # teal-tinted selection
BORDER = "#283038"
ACCENT = "#2dd4bf"       # teal
ACCENT2 = "#14b8a6"      # gradient end for buttons
ACCENT_RGB = "45,212,191"
ACCENT_TEXT = "#04211d"  # dark text reads well on teal
GREEN = "#34d399"
GREEN2 = "#22c55e"
RED = "#fb7185"
TEXT = "#eef2f4"
TEXT2 = "#9fb0b3"
DIM = "#5d6b70"

def _grad(c1, c2):
    return f"qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 {c1}, stop:1 {c2})"

MODEL_SIZE_MB = {
    "tiny": 75, "base": 145, "small": 484, "medium": 1530,
    "large-v3": 3090, "large-v3-turbo": 1620,
}

# Per-model performance ratings (0–4). Accuracy is per-language; speed is the
# model's inherent speed (cloud = fast server, needs internet).
MODEL_PERF = {
    "accurate": {"fa_acc": 4, "en_acc": 4, "speed": 2},
    "balanced": {"fa_acc": 2, "en_acc": 4, "speed": 2},
    "fast":     {"fa_acc": 1, "en_acc": 3, "speed": 4},
    "cloud":    {"fa_acc": 4, "en_acc": 4, "speed": 4},
}


def _dots(n, total=4):
    n = max(0, min(total, int(n)))
    return "●" * n + "○" * (total - n)


# Mode metadata (id, icon, title key, how-it-works key, pros keys, cons keys)
MODE_META = [
    ("offline", "💻", "mode_offline", "mode_off_how", ["mode_off_p1", "mode_off_p2"], ["mode_off_c1"]),
    ("online", "☁️", "mode_online", "mode_on_how", ["mode_on_p1", "mode_on_p2"], ["mode_on_c1", "mode_on_c2"]),
    ("dual", "🔀", "mode_dual", "mode_du_how", ["mode_du_p1", "mode_du_p2"], ["mode_du_c1"]),
]


# ============================================================
# TRANSLATIONS
# ============================================================

LANG = {
    "en": {
        "win_title": "Guya — Setup",
        "step_welcome": "Welcome", "step_language": "Language", "step_device": "Device",
        "step_mode": "Mode", "step_setup": "Setup", "step_key": "Key", "step_finish": "Finish",
        "back": "Back", "next": "Next", "finish": "Finish",

        "w_tagline": "Speech-to-Text for Persian and English",
        "w_sub": "Hold a key, speak, and your words are typed for you.",
        "w_note": "This quick setup takes about a minute.",
        "w_easy": "⚡  Easy setup",
        "w_easy_sub": "Recommended — we guide you and pick the best option for your computer",
        "w_adv": "Advanced setup",
        "w_adv_sub": "Choose everything yourself",
        "easy_hint": "✓ We picked the best option for your computer. Just tap Next — or change it if you like.",

        "done_title": "You're all set!",
        "done_how": "How to use Guya:",
        "done_s1": "Click where you want to type — a chat box, a document, anywhere.",
        "done_s2": "Hold the  {k}  key and speak.",
        "done_s3": "Let go — your words appear.",
        "done_s4": "For assistant commands, hold {k}, speak, then release.",
        "done_more": "A “Start Guya” shortcut was created so you can open it anytime.",
        "done_start": "Start Guya",

        "es_title": "Here's your setup",
        "es_sub": "We picked the best options for your computer. Change anything you like, then install.",
        "es_mode": "How it runs", "es_model": "Model", "es_key": "Dictation key",
        "es_assistant_key": "Assistant key",
        "es_change": "Change", "es_pick": "Choose this", "es_install": "Install Guya",
        "es_mac_key": "Right Option (⌥)",

        "lang_title": "Which languages will you speak?",
        "lang_sub": "Persian needs a stronger model than English, so this changes "
                    "what Guya recommends.",
        "lang_fa": "Persian only", "lang_fa_desc": "Best Persian accuracy.",
        "lang_en": "English only", "lang_en_desc": "Works well even on light, fast models.",
        "lang_both": "Both — Persian and English",
        "lang_both_desc": "Bilingual — great for Dual mode (offline + online).",

        "dev_title": "Your computer",
        "dev_sub": "This is what we found. Tap Edit to correct anything, then continue.",
        "dev_analyze": "Analyze my PC", "dev_analyzing": "Analyzing…",
        "dev_reanalyze": "Re-analyze",
        "dev_edit_hint": "Detected automatically. Click any value to correct it.",
        "dev_edit": "Edit",
        "load_title": "Analyzing your device",
        "load_sub": "Checking your hardware and measuring its real speed.\nThis takes a few seconds…",
        "spec_os": "Operating system", "spec_cpu": "Processor",
        "spec_ram": "Memory (GB)", "spec_gpu": "Graphics (GPU)",
        "gpu_none": "None / not usable",
        "bench_measuring": "⏱  Measuring your computer's speed…",
        "bench_done": "✓  Speed measured — the recommendation is tuned to your machine.",
        "bench_failed": "Could not run the speed test; using a specs-based guess.",

        "mode_title": "How should it run?",
        "mode_sub": "Choose where your speech becomes text. You can change this "
                    "anytime by running setup again.",
        "mode_offline": "Offline", "mode_offline_sub": "Runs on your computer",
        "mode_online": "Online", "mode_online_sub": "Runs on a free cloud server",
        "mode_dual": "Dual", "mode_dual_sub": "Both — switch with one tap",
        "mode_off_how": "A speech model runs on your own computer. Your voice is "
                        "never sent anywhere.",
        "mode_on_how": "Your voice is sent to a free server (Groq) running a "
                       "powerful model; the text comes back in a couple of seconds.",
        "mode_du_how": "Use offline for one language and online for the other, and "
                       "switch between them with one tap on the widget.",
        "mode_off_p1": "Completely private — nothing leaves your computer",
        "mode_off_p2": "Free, and works with no internet",
        "mode_off_c1": "Accuracy is limited by your computer (good Persian needs a "
                       "powerful machine or GPU)",
        "mode_on_p1": "Top accuracy on ANY computer — even old or weak ones",
        "mode_on_p2": "Nothing to download; barely uses memory",
        "mode_on_c1": "Needs internet and a free account (about a minute to set up)",
        "mode_on_c2": "Your voice is sent to the provider's server",
        "mode_du_p1": "Best of both: fast private English offline + accurate Persian online",
        "mode_du_p2": "One tap to switch, right on the widget",
        "mode_du_c1": "Sets up both — an offline model and a free online key",
        "mode_best": "Best model for your computer:  {m}  (about {n}s to type 10s of speech)",
        "mode_online_model": "Always uses large-v3 — the most accurate model",
        "mode_dual_note": "e.g. English offline (instant, private) + Persian online (most accurate)",

        "setup_off_title": "Choose your offline model",
        "setup_off_sub": "All of these run on your computer. Pick the balance of "
                         "accuracy and speed you want.",
        "setup_on_title": "Connect to the free server",
        "setup_on_sub": "Create a free Groq key — it takes about a minute. No card needed.",
        "setup_du_title": "Set up both",
        "setup_du_sub": "Pick the offline model for one language, then connect online "
                        "for the other. You'll switch between them on the widget.",
        "setup_du_offline": "Offline model",
        "setup_du_off_sub": "Runs on your computer — best for the language you use most "
                            "(e.g. English).",
        "setup_du_online": "Online connection",
        "setup_du_on_sub": "A free cloud model for your other language (e.g. Persian).",

        "recommended": "Recommended", "offline": "OFFLINE", "online": "ONLINE",
        "not_suitable": "not suitable for this PC",
        "title_accurate": "Accurate", "title_balanced": "Balanced",
        "title_fast": "Fast", "title_cloud": "Cloud (Online)",
        "lat_est": "≈ {n}s for 10s of speech (estimated on your machine)",
        "model_name": "Model", "perf_acc": "accuracy", "perf_speed": "speed",
        "installed": "✓ Installed", "not_installed": "↓ will download",
        "pro_best_persian": "Best Persian accuracy",
        "pro_accents": "Handles accents and colloquial speech",
        "con_slower_cpu": "Slower on a CPU-only machine",
        "pro_good_balance": "Good balance of speed and quality",
        "con_weaker_persian": "Weaker Persian than the Accurate model",
        "pro_very_fast": "Very fast", "pro_light": "Light on memory",
        "con_low_persian": "Lower accuracy, weak for Persian",
        "pro_full_accuracy": "Full accuracy on any computer",
        "pro_no_download": "No model download",
        "con_needs_internet": "Needs an internet connection",
        "con_privacy": "Sends your voice to the provider's servers",

        "cloud_guide_title": "Connect a free Groq account",
        "cloud_intro": "This is a free online account that does the speech recognition on a "
                       "powerful server — so you get top accuracy even on a weak computer. "
                       "It's free, needs no payment card, and takes about a minute. Just "
                       "follow these 3 steps:",
        "cloud_step1": '1.  Open <a href="https://console.groq.com/keys" '
                       'style="color:#7c6cff;text-decoration:none;">console.groq.com/keys</a>'
                       ' and sign in (free, no card needed)',
        "cloud_step2": '2.  Click <b>Create API Key</b>, name it “guya”, and copy the key',
        "cloud_step3": "3.  Paste the key below and press Test",
        "cloud_key_ph": "Paste your API key (gsk_…)",
        "cloud_example": "Example: gsk_AbC12dEf34GhIj…",
        "cloud_test": "Test", "cloud_testing": "Checking your key…",
        "cloud_paste_first": "Paste a key first.",
        "cloud_privacy": "Note: the online option sends your voice to the provider's "
                         "servers. Offline keeps everything on your device.",

        "key_title": "Push-to-talk key", "key_sub": "Choose the key you hold to speak.",
        "key_mac": "On macOS the push-to-talk key is Right Option (⌥).",
        "key_capture": "Click here, then press a key", "key_capturing": "Press any key now…",
        "key_chosen": "Key:  {k}",
        "key_hint": "Tip: pick a letter you rarely press mid-sentence (default: G).",
        "assistant_key_note": "Assistant commands use a separate key: {k}.",

        "review_title": "Review", "review_sub": "Check your choices, then finish.",
        "sum_mode": "Mode", "sum_model": "Model", "sum_runs": "Runs",
        "sum_language": "Language", "sum_key": "Dictation key",
        "sum_assistant_key": "Assistant key",
        "sum_offline": "Offline (on your PC)", "sum_online": "Online (cloud)",
        "sum_dual": "Dual (switch on the widget)",
        "tip_cloud": "Online chosen — no download. Guya will create a launcher and start.",
        "tip_offline": "Guya will download the model if needed (with a progress bar), "
                       "create a launcher, and start.",
        "tip_dual": "Guya will prepare the offline model and the online connection, "
                    "create a launcher, and start.",
        "dl_title": "Downloading the “{m}” model", "dl_wait": "This happens once. Keep this window open.",
        "dl_of": "{a} MB of ~{b} MB", "dl_done": "Done.",
        "dl_downloading": "Downloading…", "dl_paused": "Paused",
        "dl_error": "Download failed — check your internet and try again.",
        "dl_pause": "Pause", "dl_resume": "Resume", "dl_retry": "Try again",
        "dl_connecting": "Connecting…", "cancel": "Cancel",
        "lbl_fa": "Persian", "lbl_en": "English", "lbl_dual": "Bilingual",
    },
    "fa": {
        "win_title": "گویا — راه‌اندازی",
        "step_welcome": "خوش‌آمد", "step_language": "زبان", "step_device": "دستگاه",
        "step_mode": "حالت", "step_setup": "تنظیم", "step_key": "کلید", "step_finish": "پایان",
        "back": "بازگشت", "next": "بعدی", "finish": "پایان",

        "w_tagline": "تبدیل گفتار به متن برای فارسی و انگلیسی",
        "w_sub": "یک کلید را نگه دارید، صحبت کنید، و کلماتتان تایپ می‌شود.",
        "w_note": "این راه‌اندازی سریع حدود یک دقیقه طول می‌کشد.",
        "w_easy": "⚡  راه‌اندازی ساده",
        "w_easy_sub": "پیشنهادی — راهنمایی‌تان می‌کنیم و بهترین گزینه را برای کامپیوترتان انتخاب می‌کنیم",
        "w_adv": "راه‌اندازی پیشرفته",
        "w_adv_sub": "همه‌چیز را خودتان انتخاب کنید",
        "easy_hint": "✓ بهترین گزینه را برای کامپیوتر شما انتخاب کردیم. فقط «بعدی» را بزنید — یا اگر خواستید تغییرش دهید.",

        "done_title": "همه‌چیز آماده است!",
        "done_how": "نحوهٔ استفاده از گویا:",
        "done_s1": "روی جایی که می‌خواهید تایپ کنید کلیک کنید — یک چت‌باکس، یک سند، هرجا.",
        "done_s2": "کلید  {k}  را نگه دارید و صحبت کنید.",
        "done_s3": "رها کنید — کلماتتان ظاهر می‌شوند.",
        "done_s4": "برای فرمان‌های دستیار، کلید {k} را نگه دارید، صحبت کنید و رها کنید.",
        "done_more": "یک میان‌بر «Start Guya» ساخته شد تا هر وقت خواستید بازش کنید.",
        "done_start": "شروع گویا",

        "es_title": "این هم تنظیمات شما",
        "es_sub": "بهترین گزینه‌ها را برای کامپیوتر شما انتخاب کردیم. هرچه خواستید تغییر دهید، سپس نصب کنید.",
        "es_mode": "نحوهٔ اجرا", "es_model": "مدل", "es_key": "کلید دیکته",
        "es_assistant_key": "کلید دستیار",
        "es_change": "تغییر", "es_pick": "همین را انتخاب کن", "es_install": "نصب گویا",
        "es_mac_key": "Right Option (⌥)",

        "lang_title": "به چه زبان‌هایی صحبت می‌کنید؟",
        "lang_sub": "فارسی به مدلی قوی‌تر از انگلیسی نیاز دارد، پس این انتخاب روی "
                    "پیشنهاد گویا اثر می‌گذارد.",
        "lang_fa": "فقط فارسی", "lang_fa_desc": "بهترین دقت فارسی.",
        "lang_en": "فقط انگلیسی", "lang_en_desc": "حتی روی مدل‌های سبک و سریع هم خوب کار می‌کند.",
        "lang_both": "هر دو — فارسی و انگلیسی",
        "lang_both_desc": "دوزبانه — عالی برای حالت دوگانه (آفلاین + آنلاین).",

        "dev_title": "کامپیوتر شما",
        "dev_sub": "این چیزی است که پیدا کردیم. برای اصلاح روی «ویرایش» بزنید، سپس ادامه دهید.",
        "dev_analyze": "بررسی کامپیوتر", "dev_analyzing": "در حال بررسی…",
        "dev_reanalyze": "بررسی دوباره",
        "dev_edit_hint": "خودکار شناسایی شد. برای اصلاح روی هر مقدار کلیک کنید.",
        "dev_edit": "ویرایش",
        "load_title": "در حال بررسی دستگاه شما",
        "load_sub": "بررسی سخت‌افزار و اندازه‌گیری سرعت واقعی آن.\nچند ثانیه طول می‌کشد…",
        "spec_os": "سیستم‌عامل", "spec_cpu": "پردازنده",
        "spec_ram": "حافظه (گیگابایت)", "spec_gpu": "کارت گرافیک",
        "gpu_none": "ندارد / غیرقابل‌استفاده",
        "bench_measuring": "⏱  در حال اندازه‌گیری سرعت کامپیوتر…",
        "bench_done": "✓  سرعت اندازه‌گیری شد — پیشنهاد متناسب با دستگاه شما تنظیم شد.",
        "bench_failed": "آزمایش سرعت انجام نشد؛ از حدس مبتنی بر مشخصات استفاده می‌شود.",

        "mode_title": "چطور اجرا شود؟",
        "mode_sub": "انتخاب کنید گفتار شما کجا به متن تبدیل شود. هر وقت خواستید "
                    "می‌توانید با اجرای دوبارهٔ راه‌اندازی تغییرش دهید.",
        "mode_offline": "آفلاین", "mode_offline_sub": "روی کامپیوتر شما اجرا می‌شود",
        "mode_online": "آنلاین", "mode_online_sub": "روی سرور ابری رایگان اجرا می‌شود",
        "mode_dual": "دوگانه", "mode_dual_sub": "هر دو — با یک ضربه جابه‌جا شو",
        "mode_off_how": "یک مدل گفتار روی کامپیوتر خودتان اجرا می‌شود. صدای شما به "
                        "هیچ‌جا فرستاده نمی‌شود.",
        "mode_on_how": "صدای شما به یک سرور رایگان (Groq) با مدلی قدرتمند فرستاده "
                       "می‌شود و متن در چند ثانیه برمی‌گردد.",
        "mode_du_how": "برای یک زبان آفلاین و برای زبان دیگر آنلاین استفاده کنید و "
                       "با یک ضربه روی ویجت بینشان جابه‌جا شوید.",
        "mode_off_p1": "کاملاً خصوصی — هیچ‌چیز از کامپیوتر شما خارج نمی‌شود",
        "mode_off_p2": "رایگان، و بدون اینترنت کار می‌کند",
        "mode_off_c1": "دقت محدود به کامپیوتر شماست (فارسی خوب به دستگاه قوی یا کارت گرافیک نیاز دارد)",
        "mode_on_p1": "بالاترین دقت روی هر کامپیوتری — حتی قدیمی یا ضعیف",
        "mode_on_p2": "بدون دانلود؛ تقریباً بدون مصرف حافظه",
        "mode_on_c1": "به اینترنت و یک حساب رایگان نیاز دارد (حدود یک دقیقه)",
        "mode_on_c2": "صدای شما به سرور سرویس‌دهنده فرستاده می‌شود",
        "mode_du_p1": "بهترینِ هر دو: انگلیسی آفلاین سریع و خصوصی + فارسی آنلاین دقیق",
        "mode_du_p2": "یک ضربه برای جابه‌جایی، درست روی ویجت",
        "mode_du_c1": "هر دو را تنظیم می‌کند — یک مدل آفلاین و یک کلید آنلاین رایگان",
        "mode_best": "بهترین مدل برای کامپیوتر شما:  {m}  (حدود {n} ثانیه برای ۱۰ ثانیه گفتار)",
        "mode_online_model": "همیشه از large-v3 استفاده می‌کند — دقیق‌ترین مدل",
        "mode_dual_note": "مثلاً انگلیسی آفلاین (فوری، خصوصی) + فارسی آنلاین (دقیق‌ترین)",

        "setup_off_title": "مدل آفلاین را انتخاب کنید",
        "setup_off_sub": "همهٔ این‌ها روی کامپیوتر شما اجرا می‌شوند. تعادل دقت و سرعت "
                         "دلخواهتان را انتخاب کنید.",
        "setup_on_title": "اتصال به سرور رایگان",
        "setup_on_sub": "یک کلید رایگان Groq بسازید — حدود یک دقیقه. بدون نیاز به کارت.",
        "setup_du_title": "هر دو را تنظیم کنید",
        "setup_du_sub": "مدل آفلاین را برای یک زبان انتخاب کنید، سپس برای زبان دیگر "
                        "آنلاین متصل شوید. روی ویجت بینشان جابه‌جا می‌شوید.",
        "setup_du_offline": "مدل آفلاین",
        "setup_du_off_sub": "روی کامپیوتر شما اجرا می‌شود — برای زبانی که بیشتر استفاده "
                            "می‌کنید (مثلاً انگلیسی).",
        "setup_du_online": "اتصال آنلاین",
        "setup_du_on_sub": "یک مدل ابری رایگان برای زبان دیگرتان (مثلاً فارسی).",

        "recommended": "پیشنهادی", "offline": "آفلاین", "online": "آنلاین",
        "not_suitable": "برای این کامپیوتر مناسب نیست",
        "title_accurate": "دقیق", "title_balanced": "متعادل",
        "title_fast": "سریع", "title_cloud": "ابری (آنلاین)",
        "lat_est": "حدود {n} ثانیه برای ۱۰ ثانیه گفتار (تخمینی روی دستگاه شما)",
        "model_name": "مدل", "perf_acc": "دقت", "perf_speed": "سرعت",
        "installed": "✓ نصب‌شده", "not_installed": "↓ دانلود می‌شود",
        "pro_best_persian": "بهترین دقت فارسی",
        "pro_accents": "پشتیبانی از لهجه و گفتار محاوره‌ای",
        "con_slower_cpu": "روی دستگاه بدون کارت گرافیک کندتر است",
        "pro_good_balance": "تعادل خوب بین سرعت و کیفیت",
        "con_weaker_persian": "فارسی ضعیف‌تر از مدل دقیق",
        "pro_very_fast": "بسیار سریع", "pro_light": "مصرف حافظه کم",
        "con_low_persian": "دقت پایین‌تر، ضعیف برای فارسی",
        "pro_full_accuracy": "دقت کامل روی هر کامپیوتری",
        "pro_no_download": "بدون دانلود مدل",
        "con_needs_internet": "به اینترنت نیاز دارد",
        "con_privacy": "صدای شما به سرور سرویس‌دهنده ارسال می‌شود",

        "cloud_guide_title": "اتصال به یک حساب رایگان Groq",
        "cloud_intro": "این یک حساب آنلاین رایگان است که تشخیص گفتار را روی یک سرور قدرتمند "
                       "انجام می‌دهد — پس حتی روی کامپیوتر ضعیف هم بالاترین دقت را می‌گیرید. "
                       "رایگان است، به کارت بانکی نیاز ندارد، و حدود یک دقیقه طول می‌کشد. "
                       "فقط این ۳ گام را دنبال کنید:",
        "cloud_step1": '۱.  به <a href="https://console.groq.com/keys" '
                       'style="color:#7c6cff;text-decoration:none;">console.groq.com/keys</a>'
                       ' بروید و وارد شوید (رایگان، بدون کارت)',
        "cloud_step2": '۲.  روی <b>Create API Key</b> بزنید، نامش را «guya» بگذارید و کپی کنید',
        "cloud_step3": "۳.  کلید را پایین بچسبانید و «آزمایش» را بزنید",
        "cloud_key_ph": "کلید API خود را بچسبانید (gsk_…)",
        "cloud_example": "نمونه: gsk_AbC12dEf34GhIj…",
        "cloud_test": "آزمایش", "cloud_testing": "در حال بررسی کلید…",
        "cloud_paste_first": "ابتدا یک کلید بچسبانید.",
        "cloud_privacy": "توجه: گزینهٔ آنلاین صدای شما را به سرور سرویس‌دهنده می‌فرستد. "
                         "آفلاین همه‌چیز را روی دستگاه شما نگه می‌دارد.",

        "key_title": "کلید فشار-برای-صحبت", "key_sub": "کلیدی را که برای صحبت نگه می‌دارید انتخاب کنید.",
        "key_mac": "در مک‌اواس کلید فشار-برای-صحبت، Right Option (⌥) است.",
        "key_capture": "اینجا کلیک کنید، سپس یک کلید را فشار دهید", "key_capturing": "حالا یک کلید را فشار دهید…",
        "key_chosen": "کلید:  {k}",
        "key_hint": "نکته: حرفی را انتخاب کنید که وسط جمله کم فشار می‌دهید (پیش‌فرض: G).",
        "assistant_key_note": "فرمان‌های دستیار کلید جداگانه دارند: {k}.",

        "review_title": "مرور", "review_sub": "انتخاب‌هایتان را بررسی و سپس تمام کنید.",
        "sum_mode": "حالت", "sum_model": "مدل", "sum_runs": "اجرا",
        "sum_language": "زبان", "sum_key": "کلید دیکته",
        "sum_assistant_key": "کلید دستیار",
        "sum_offline": "آفلاین (روی کامپیوتر شما)", "sum_online": "آنلاین (ابری)",
        "sum_dual": "دوگانه (روی ویجت جابه‌جا شو)",
        "tip_cloud": "آنلاین انتخاب شد — بدون دانلود. گویا یک فایل اجرا می‌سازد و شروع می‌کند.",
        "tip_offline": "گویا در صورت نیاز مدل را دانلود می‌کند (با نوار پیشرفت)، یک فایل "
                       "اجرا می‌سازد و شروع می‌کند.",
        "tip_dual": "گویا مدل آفلاین و اتصال آنلاین را آماده می‌کند، یک فایل اجرا می‌سازد و شروع می‌کند.",
        "dl_title": "در حال دانلود مدل «{m}»", "dl_wait": "این فقط یک‌بار اتفاق می‌افتد. این پنجره را باز نگه دارید.",
        "dl_of": "{a} مگابایت از ~{b} مگابایت", "dl_done": "انجام شد.",
        "dl_downloading": "در حال دانلود…", "dl_paused": "متوقف شد",
        "dl_error": "دانلود ناموفق بود — اینترنت را بررسی و دوباره تلاش کنید.",
        "dl_pause": "توقف", "dl_resume": "ادامه", "dl_retry": "تلاش دوباره",
        "dl_connecting": "در حال اتصال…", "cancel": "لغو",
        "lbl_fa": "فارسی", "lbl_en": "انگلیسی", "lbl_dual": "دوزبانه",
    },
}


def _load_fonts():
    """Load the bundled Vazirmatn font (clean modern Persian + Latin). Returns
    the family name to use, or the platform default if loading fails."""
    global UI_FONT
    try:
        from PyQt6.QtGui import QFontDatabase
        fonts_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "fonts")
        loaded = False
        for fn in ("Vazirmatn-Regular.ttf", "Vazirmatn-Medium.ttf",
                   "Vazirmatn-SemiBold.ttf", "Vazirmatn-Bold.ttf"):
            p = os.path.join(fonts_dir, fn)
            if os.path.isfile(p) and QFontDatabase.addApplicationFont(p) != -1:
                loaded = True
        if loaded and "Vazirmatn" in QFontDatabase.families():
            UI_FONT = "Vazirmatn"
    except Exception as e:
        log.warning(f"Could not load Vazirmatn: {e}")
    return UI_FONT


def run() -> bool:
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtGui import QFont as _QFont
    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyle("Fusion")
    _load_fonts()
    app.setFont(_QFont(UI_FONT, 11))
    win = WizardWindow()
    win.show()
    win.raise_()
    win.activateWindow()
    app.exec()
    return win.completed


from PyQt6.QtWidgets import (  # noqa: E402
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QStackedWidget, QApplication, QLineEdit, QProgressBar, QScrollArea,
    QDialog, QGraphicsDropShadowEffect,
)
from PyQt6.QtCore import (  # noqa: E402
    Qt, QProcess, QProcessEnvironment, QTimer, pyqtSignal,
)
from PyQt6.QtGui import QFont, QColor, QPainter, QPen, QKeySequence  # noqa: E402


def _shadow(widget, blur=24, dy=6, alpha=120):
    """Soft drop shadow for depth (Apple-like)."""
    eff = QGraphicsDropShadowEffect(widget)
    eff.setBlurRadius(blur)
    eff.setOffset(0, dy)
    eff.setColor(QColor(0, 0, 0, alpha))
    widget.setGraphicsEffect(eff)
    return widget


class Spinner(QWidget):
    """A smooth rotating-arc loading indicator (Apple-style)."""

    def __init__(self, size=72, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._angle = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

    def start(self):
        self._timer.start(16)

    def stop(self):
        self._timer.stop()

    def _tick(self):
        self._angle = (self._angle + 5) % 360
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.rect().adjusted(7, 7, -7, -7)
        track = QPen(QColor(45, 212, 191, 40)); track.setWidth(6)
        track.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(track); p.drawArc(r, 0, 360 * 16)
        arc = QPen(QColor(45, 212, 191)); arc.setWidth(6)
        arc.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(arc); p.drawArc(r, -self._angle * 16, 100 * 16)
        p.end()


def _hub_root():
    return os.environ.get(
        "HUGGINGFACE_HUB_CACHE",
        os.path.join(os.path.expanduser("~"), ".cache", "huggingface", "hub"))


def model_is_cached(size: str) -> bool:
    for d in glob.glob(os.path.join(_hub_root(), f"models--*--faster-whisper-{size}",
                                    "snapshots", "*")):
        if os.path.isfile(os.path.join(d, "model.bin")):
            return True
    return False


def model_downloaded_mb(size: str) -> float:
    total = 0
    for d in glob.glob(os.path.join(_hub_root(), f"models--*--faster-whisper-{size}")):
        for dp, _dn, files in os.walk(d):
            for fn in files:
                try:
                    total += os.path.getsize(os.path.join(dp, fn))
                except OSError:
                    pass
    return total / (1024 * 1024)


# Pages:  0 Welcome  1 Language  2 Device  3 Mode  4 Setup  5 Key  6 Review  7 Download
STEPS_KEYS = ["step_welcome", "step_language", "step_device", "step_mode",
              "step_setup", "step_key", "step_finish"]
# pages: 0 Welcome 1 Lang 2 Device 3 Mode 4 Setup 5 Key 6 Review 7 Download
#        8 Done 9 EasySummary 10 Loading
PAGE_TO_STEP = [0, 1, 2, 3, 4, 5, 6, 6, 6, 4, 2]


class Card(QFrame):
    """A clickable card with a stacked body, used for choices."""

    def __init__(self, on_click, payload, enabled=True):
        super().__init__()
        self.payload = payload
        self.on_click = on_click
        self.enabled_ = enabled
        self.selected = False
        self.setObjectName("card")
        self._body = QVBoxLayout(self)
        self._body.setContentsMargins(18, 14, 18, 14)
        self._body.setSpacing(6)
        if enabled:
            self.setCursor(Qt.CursorShape.PointingHandCursor)

    def style_self(self):
        if not self.enabled_:
            border, bg = BORDER, "#0f1316"
        elif self.selected:
            border, bg = ACCENT, _grad("#16302e", "#102420")
        else:
            border, bg = BORDER, _grad("#181c22", "#13161b")
        self.setStyleSheet(
            f"QFrame#card {{ background: {bg}; border: 1.5px solid {border};"
            f"border-radius: 18px; }} QLabel {{ background: transparent; border: none; }}")

    def set_selected(self, s):
        self.selected = s
        self.style_self()

    def mousePressEvent(self, e):
        if self.enabled_:
            self.on_click(self)


class PickerDialog(QDialog):
    """A modern modal that floats over the wizard to pick an option.
    `build(content_layout, choose)` populates the body; cards call choose(value)."""

    def __init__(self, parent, title, build):
        super().__init__(parent)
        self.value = None
        self.setModal(True)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setLayoutDirection(parent.layoutDirection())
        outer = QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0)
        panel = QFrame(); panel.setObjectName("panel")
        panel.setStyleSheet(
            f"QFrame#panel {{ background: {_grad('#181c22', '#13161b')};"
            f"border: 1px solid {BORDER}; border-radius: 22px; }}"
            f"QLabel {{ background: transparent; border: none; }}")
        _shadow(panel, blur=48, dy=14, alpha=180)
        outer.addWidget(panel)
        v = QVBoxLayout(panel); v.setContentsMargins(22, 20, 22, 20); v.setSpacing(12)
        head = QHBoxLayout()
        t = QLabel(title); t.setFont(QFont(UI_FONT, 17, QFont.Weight.Bold))
        t.setStyleSheet(f"color: {TEXT};"); head.addWidget(t); head.addStretch()
        x = QPushButton("✕"); x.setCursor(Qt.CursorShape.PointingHandCursor)
        x.setFixedSize(34, 34)
        x.setStyleSheet(f"QPushButton {{ background: rgba(255,255,255,0.05); color: {TEXT2};"
                        f"border: none; border-radius: 17px; font-size: 14px; }}"
                        f"QPushButton:hover {{ background: rgba(255,255,255,0.12); color: {TEXT}; }}")
        x.clicked.connect(self.reject); head.addWidget(x)
        v.addLayout(head)
        area = QScrollArea(); area.setWidgetResizable(True)
        area.setFrameShape(QFrame.Shape.NoFrame)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        area.setStyleSheet("QScrollArea{background:transparent;border:none;}"
                           "QScrollBar:vertical{background:transparent;width:8px;}"
                           f"QScrollBar::handle:vertical{{background:{BORDER};border-radius:4px;}}"
                           "QScrollBar::add-line,QScrollBar::sub-line{height:0;}")
        inner = QWidget(); inner.setStyleSheet("background:transparent;")
        col = QVBoxLayout(inner); col.setContentsMargins(2, 2, 12, 2); col.setSpacing(11)
        build(col, self._choose)
        col.addStretch()
        area.setWidget(inner)
        v.addWidget(area)

    def _choose(self, value):
        self.value = value
        self.accept()

    def sizeHint(self):
        from PyQt6.QtCore import QSize
        p = self.parent()
        if p:
            return QSize(int(p.width() * 0.82), int(p.height() * 0.74))
        return QSize(560, 600)


# ============================================================
# WIZARD
# ============================================================

class WizardWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.ui_lang = "en"
        self.completed = False
        self.profile = None
        self.model_options = []
        self.rtf_base = None
        self.bench_proc = None
        self.dl_proc = None
        self.dl_timer = None
        self.dl_paused = False
        self.mode = None                 # "offline" | "online" | "dual"
        self.recommended_mode = "offline"
        self.easy = True                 # Easy (guided) vs Advanced setup
        self.model_cards = []
        self.lang_cards = []
        self.mode_cards = []
        self.selected_model_id = None
        self.choices = {
            "model_opt": None, "language": "fa",
            "hotkey_vk": 71, "hotkey_label": "G",
            "ui_style": "pill", "cloud_api_key": "",
        }
        self.spec_edits = {}

        # Resizable + bigger, with a subtle vertical gradient background.
        self.resize(880, 900)
        self.setMinimumSize(720, 760)
        self.setStyleSheet(
            f"WizardWindow {{ background: {_grad(BG, BG2)}; }}"
            f"QWidget {{ color: {TEXT}; }}")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QWidget()
        hlay = QHBoxLayout(header)
        hlay.setContentsMargins(20, 14, 20, 10)
        self.step_labels = []
        steprow = QHBoxLayout(); steprow.setSpacing(7)
        for i, k in enumerate(STEPS_KEYS):
            lbl = QLabel(f"{i+1}")
            lbl.setFont(QFont(UI_FONT, 10, QFont.Weight.DemiBold))
            self.step_labels.append(lbl)
            steprow.addWidget(lbl)
            if i < len(STEPS_KEYS) - 1:
                s = QLabel("—"); s.setStyleSheet(f"color: {DIM};")
                steprow.addWidget(s)
        hlay.addLayout(steprow)
        hlay.addStretch()
        hlay.addWidget(self._lang_toggle())
        root.addWidget(header)

        self.stack = QStackedWidget()
        root.addWidget(self.stack, 1)
        self.stack.addWidget(self._page_welcome())      # 0
        self.stack.addWidget(self._page_language())      # 1
        self.stack.addWidget(self._page_device())        # 2
        self.stack.addWidget(self._page_mode())          # 3
        self.stack.addWidget(self._page_setup())         # 4
        self.stack.addWidget(self._page_key())           # 5
        self.stack.addWidget(self._page_review())        # 6
        self.stack.addWidget(self._page_download())      # 7
        self.stack.addWidget(self._page_done())          # 8
        self.stack.addWidget(self._page_easy_summary())  # 9
        self.stack.addWidget(self._page_loading())       # 10

        navw = QWidget()
        nav = QHBoxLayout(navw)
        nav.setContentsMargins(24, 8, 24, 18)
        self.back_btn = self._btn("back", "ghost"); self.back_btn.clicked.connect(self._go_back)
        self.next_btn = self._btn("next", "primary"); self.next_btn.clicked.connect(self._go_next)
        nav.addWidget(self.back_btn); nav.addStretch(); nav.addWidget(self.next_btn)
        root.addWidget(navw)

        self.retranslate()
        self._update_nav()
        self._prewarm_proxy()

    def _prewarm_proxy(self):
        if model_is_cached(benchmark.PROXY_MODEL):
            return
        self._prewarm_proc = QProcess(self)
        self._prewarm_proc.setProgram(sys.executable)
        self._prewarm_proc.setArguments([
            "-c", "from faster_whisper.utils import download_model; "
                  f"download_model('{benchmark.PROXY_MODEL}')"])
        env = QProcessEnvironment.systemEnvironment()
        env.insert("HF_HUB_DISABLE_XET", "1")
        self._prewarm_proc.setProcessEnvironment(env)
        self._prewarm_proc.start()

    # ---- i18n ----

    def tr(self, key, **fmt):
        s = LANG.get(self.ui_lang, LANG["en"]).get(key, LANG["en"].get(key, key))
        return s.format(**fmt) if fmt else s

    def _t(self, widget, key, placeholder=False):
        widget.setProperty("i18nPh" if placeholder else "i18nKey", key)
        if placeholder:
            widget.setPlaceholderText(self.tr(key))
        else:
            widget.setText(self.tr(key))
        return widget

    def _lang_toggle(self):
        box = QWidget()
        lay = QHBoxLayout(box); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(0)
        self.btn_en = QPushButton("EN"); self.btn_fa = QPushButton("فا")
        for b in (self.btn_en, self.btn_fa):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFixedSize(42, 28)
            b.setFont(QFont(UI_FONT, 10, QFont.Weight.DemiBold))
        self.btn_en.clicked.connect(lambda: self._set_ui_lang("en"))
        self.btn_fa.clicked.connect(lambda: self._set_ui_lang("fa"))
        lay.addWidget(self.btn_en); lay.addWidget(self.btn_fa)
        self._style_lang_toggle()
        return box

    def _style_lang_toggle(self):
        on = f"background: {ACCENT}; color: {ACCENT_TEXT}; border: none;"
        off = f"background: {CARD}; color: {TEXT2}; border: 1px solid {BORDER};"
        self.btn_en.setStyleSheet(f"QPushButton {{ {on if self.ui_lang=='en' else off}"
                                  f"border-top-left-radius: 9px; border-bottom-left-radius: 9px; }}")
        self.btn_fa.setStyleSheet(f"QPushButton {{ {on if self.ui_lang=='fa' else off}"
                                  f"border-top-right-radius: 9px; border-bottom-right-radius: 9px; }}")

    def _set_ui_lang(self, lang):
        self.ui_lang = lang
        self._style_lang_toggle()
        self.setLayoutDirection(
            Qt.LayoutDirection.RightToLeft if lang == "fa" else Qt.LayoutDirection.LeftToRight)
        self.retranslate()

    def retranslate(self):
        self.setWindowTitle(self.tr("win_title"))
        for w in self.findChildren(QWidget):
            k = w.property("i18nKey")
            if k:
                try:
                    w.setText(self.tr(k))
                except Exception:
                    pass
            ph = w.property("i18nPh")
            if ph:
                try:
                    w.setPlaceholderText(self.tr(ph))
                except Exception:
                    pass
            k2 = w.property("i18nKey2")   # two-line buttons (title + subtitle)
            if k2:
                try:
                    w.setText(f"{self.tr(k2[0])}\n{self.tr(k2[1])}")
                except Exception:
                    pass
        self._sync_step()
        # Rebuild whichever choice page is current so dynamic text re-translates.
        idx = self.stack.currentIndex()
        if idx == 2:
            self._build_device_page()
        elif idx == 3:
            self._build_mode_cards()
        elif idx == 4:
            self._build_setup()
        elif idx == 6:
            self._refresh_summary()
        elif idx == 8:
            self._fill_done()
        elif idx == 9:
            self._build_easy_summary()

    # ---- styled widgets ----

    def _btn(self, key, kind="primary"):
        b = QPushButton(); b.setProperty("i18nKey", key); b.setText(self.tr(key))
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setMinimumSize(120, 46)
        b.setFont(QFont(UI_FONT, 12, QFont.Weight.DemiBold))
        if kind == "primary":
            b.setStyleSheet(
                f"QPushButton {{ background: {_grad('#3ee0cb', ACCENT2)}; color: {ACCENT_TEXT};"
                f"border: none; border-radius: 14px; padding: 0 26px; font-weight: 700; }}"
                f"QPushButton:hover {{ background: {_grad('#4fe9d5', '#10a89a')}; }}"
                f"QPushButton:pressed {{ background: {_grad(ACCENT2, ACCENT2)}; }}"
                f"QPushButton:disabled {{ background: #1c232a; color: {DIM}; }}")
            _shadow(b, blur=22, dy=5, alpha=110)
        elif kind == "green":
            b.setStyleSheet(
                f"QPushButton {{ background: {_grad('#4ade80', GREEN2)}; color: #06210f;"
                f"border: none; border-radius: 14px; padding: 0 26px; }}"
                f"QPushButton:hover {{ background: {_grad('#5cee92', '#26cf63')}; }}"
                f"QPushButton:disabled {{ background: #23232f; color: {DIM}; }}")
            _shadow(b, blur=22, dy=5, alpha=110)
        else:
            b.setStyleSheet(
                f"QPushButton {{ background: rgba(255,255,255,0.04); color: {TEXT2};"
                f"border: 1px solid {BORDER}; border-radius: 14px; padding: 0 26px; }}"
                f"QPushButton:hover {{ border-color: {ACCENT}; color: {TEXT};"
                f"background: rgba(45,212,191,0.08); }}"
                f"QPushButton:disabled {{ color: {DIM}; }}")
        return b

    def _heading(self, lay, title_key, sub_key):
        t = QLabel(); t.setFont(QFont(UI_FONT, 22, QFont.Weight.Bold))
        t.setStyleSheet(f"color: {TEXT};"); self._t(t, title_key); lay.addWidget(t)
        s = QLabel(); s.setFont(QFont(UI_FONT, 11)); s.setWordWrap(True)
        s.setStyleSheet(f"color: {TEXT2};"); self._t(s, sub_key); lay.addWidget(s)

    def _page(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(34, 18, 34, 8)
        lay.setSpacing(12)
        return w, lay

    def _scroll_area(self):
        area = QScrollArea(); area.setWidgetResizable(True)
        area.setFrameShape(QFrame.Shape.NoFrame)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        area.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollBar:vertical { background: transparent; width: 8px; margin: 2px; }"
            f"QScrollBar::handle:vertical {{ background: {BORDER}; border-radius: 4px; min-height: 30px; }}"
            "QScrollBar::add-line, QScrollBar::sub-line { height: 0; }")
        inner = QWidget(); inner.setStyleSheet("background: transparent;")
        col = QVBoxLayout(inner)
        col.setContentsMargins(2, 2, 16, 2); col.setSpacing(12)
        area.setWidget(inner)
        return area, col

    def _info_card(self):
        lbl = QLabel(); lbl.setFont(QFont(UI_FONT, 11))
        lbl.setStyleSheet(f"color: {TEXT}; background: {CARD}; border: 1px solid {BORDER};"
                          f"border-radius: 12px; padding: 16px;")
        lbl.setWordWrap(True)
        return lbl

    # ---- Page 0: Welcome ----

    def _page_welcome(self):
        w, lay = self._page()
        lay.addStretch()
        logo = QLabel("گویا"); logo.setFont(QFont(UI_FONT, 46, QFont.Weight.Bold))
        logo.setStyleSheet(f"color: {TEXT};"); logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(logo)
        nm = QLabel("Guya"); nm.setFont(QFont(UI_FONT, 16, QFont.Weight.DemiBold))
        nm.setStyleSheet(f"color: {ACCENT};"); nm.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(nm)
        for key, sz, col in (("w_tagline", 13, TEXT2), ("w_sub", 11, TEXT2)):
            l = QLabel(); l.setFont(QFont(UI_FONT, sz)); l.setStyleSheet(f"color: {col};")
            l.setAlignment(Qt.AlignmentFlag.AlignCenter); self._t(l, key); lay.addWidget(l)
        lay.addSpacing(18)

        # Easy vs Advanced choice — two big buttons.
        ez = self._choice_button("w_easy", "w_easy_sub", primary=True)
        ez.clicked.connect(lambda: self._start_setup(True))
        lay.addWidget(ez)
        adv = self._choice_button("w_adv", "w_adv_sub", primary=False)
        adv.clicked.connect(lambda: self._start_setup(False))
        lay.addWidget(adv)
        lay.addStretch()
        return w

    def _choice_button(self, title_key, sub_key, primary):
        b = QPushButton(); b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setMinimumHeight(62)
        if primary:
            bg, fg, border, subcol = ACCENT, ACCENT_TEXT, ACCENT, "#2a2350"
        else:
            bg, fg, border, subcol = CARD, TEXT, BORDER, TEXT2
        b.setText(f"{self.tr(title_key)}\n{self.tr(sub_key)}")
        b.setProperty("i18nKey2", (title_key, sub_key))
        b.setStyleSheet(
            f"QPushButton {{ background: {bg}; color: {fg}; border: 1.5px solid {border};"
            f"border-radius: 13px; padding: 10px 20px; text-align: left; font-size: 13pt;"
            f"font-weight: 700; }}"
            f"QPushButton:hover {{ border-color: {ACCENT}; }}")
        return b

    def _start_setup(self, easy):
        self.easy = easy
        self.stack.setCurrentIndex(1)   # → Language
        self._sync_step(); self._update_nav()

    # ---- Page 1: Language ----

    def _page_language(self):
        w, lay = self._page()
        self._heading(lay, "lang_title", "lang_sub")
        self.lang_container = QVBoxLayout(); self.lang_container.setSpacing(10)
        lay.addLayout(self.lang_container)
        lay.addStretch()
        self._build_lang_cards()
        return w

    def _build_lang_cards(self):
        while self.lang_container.count():
            it = self.lang_container.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        self.lang_cards = []
        for code, tk, dk in [("fa", "lang_fa", "lang_fa_desc"),
                             ("en", "lang_en", "lang_en_desc"),
                             ("dual", "lang_both", "lang_both_desc")]:
            c = Card(self._select_lang, code)
            t = QLabel(); t.setFont(QFont(UI_FONT, 14, QFont.Weight.Bold))
            t.setStyleSheet(f"color: {TEXT};"); self._t(t, tk)
            d = QLabel(); d.setFont(QFont(UI_FONT, 10)); d.setWordWrap(True)
            d.setStyleSheet(f"color: {TEXT2};"); self._t(d, dk)
            c._body.addWidget(t); c._body.addWidget(d)
            c.set_selected(self.choices["language"] == code)
            self.lang_cards.append(c); self.lang_container.addWidget(c)

    def _select_lang(self, card):
        self.choices["language"] = card.payload
        for c in self.lang_cards:
            c.set_selected(c is card)
        if self.rtf_base is not None and self.model_options:
            benchmark.annotate_and_recommend(self.model_options, self.rtf_base,
                                             language=self.choices["language"])
        self._update_nav()

    # ---- Page 10: Loading (analyzing the device) ----

    def _page_loading(self):
        w, lay = self._page()
        lay.addStretch()
        self.loading_spinner = Spinner(78)
        row = QHBoxLayout(); row.addStretch(); row.addWidget(self.loading_spinner); row.addStretch()
        lay.addLayout(row)
        lay.addSpacing(26)
        self.load_title = QLabel(); self.load_title.setFont(QFont(UI_FONT, 21, QFont.Weight.Bold))
        self.load_title.setStyleSheet(f"color: {TEXT};")
        self.load_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._t(self.load_title, "load_title"); lay.addWidget(self.load_title)
        self.load_sub = QLabel(); self.load_sub.setFont(QFont(UI_FONT, 12))
        self.load_sub.setStyleSheet(f"color: {TEXT2};"); self.load_sub.setWordWrap(True)
        self.load_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._t(self.load_sub, "load_sub"); lay.addWidget(self.load_sub)
        lay.addStretch()
        return w

    def _start_loading(self):
        self.stack.setCurrentIndex(10); self._sync_step(); self._update_nav()
        self.loading_spinner.start()
        if self.profile is None:
            self._run_analysis()
        else:
            QTimer.singleShot(450, self._after_analysis)
        # Safety net: proceed even if the benchmark hangs.
        self._loading_timer = QTimer(self); self._loading_timer.setSingleShot(True)
        self._loading_timer.timeout.connect(self._after_analysis)
        self._loading_timer.start(75000)

    def _run_analysis(self):
        self.profile = profiler.get_device_profile()
        self.model_options = profiler.recommend_models(self.profile)
        self._start_benchmark()

    def _after_analysis(self):
        idx = self.stack.currentIndex()
        if idx == 10:                       # leaving the loading screen
            if getattr(self, "_loading_timer", None):
                self._loading_timer.stop()
            if self.loading_spinner:
                self.loading_spinner.stop()
            if self.easy:
                self.stack.setCurrentIndex(9); self._build_easy_summary()
            else:
                self.stack.setCurrentIndex(2); self._build_device_page()
            self._sync_step(); self._update_nav()
        elif idx == 9:
            self._build_easy_summary()
        elif idx == 2:
            self._build_device_page()

    # ---- Page 2: Device (config display; analysis runs on the Loading page) ----

    def _page_device(self):
        w, lay = self._page()
        self._heading(lay, "dev_title", "dev_sub")
        area, col = self._scroll_area()
        self.device_col = col
        lay.addWidget(area, 1)
        return w

    def _build_device_page(self):
        while self.device_col.count():
            it = self.device_col.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        self.device_col.addWidget(self._device_card())
        st = QLabel(); st.setFont(QFont(UI_FONT, 10, QFont.Weight.DemiBold)); st.setWordWrap(True)
        if self.rtf_base is None:
            st.setStyleSheet(f"color: {ACCENT};"); st.setText(self.tr("bench_measuring"))
        else:
            st.setStyleSheet(f"color: {GREEN};"); st.setText(self.tr("bench_done"))
        self.device_col.addWidget(st)
        self.device_col.addStretch()

    def _device_card(self):
        p = self.profile or {}
        f = QFrame()
        f.setStyleSheet(f"QFrame {{ background: {_grad('#1a1e24', '#15181d')};"
                        f"border: 1px solid {BORDER}; border-radius: 18px; }}"
                        f"QLabel {{ border: none; background: transparent; }}")
        _shadow(f, blur=20, dy=5, alpha=90)
        h = QHBoxLayout(f); h.setContentsMargins(20, 18, 20, 18); h.setSpacing(14)
        ic = QLabel("💻"); ic.setFont(QFont(UI_FONT, 30)); ic.setFixedWidth(46)
        h.addWidget(ic)
        col = QVBoxLayout(); col.setSpacing(3)
        name = QLabel(p.get("cpu_name", "—")); name.setFont(QFont(UI_FONT, 15, QFont.Weight.Bold))
        name.setStyleSheet(f"color: {TEXT};"); name.setWordWrap(True)
        col.addWidget(name)
        ram = f"{p.get('ram_gb', 0):.0f} GB" if p.get("ram_gb") else "8 GB"
        gpu = p.get("gpu_name") or ("Apple Silicon" if p.get("apple_silicon")
                                    else ("GPU" if p.get("has_cuda") else "CPU mode"))
        sub = QLabel(f"{ram}  ·  {gpu}  ·  {p.get('os', '')}")
        sub.setFont(QFont(UI_FONT, 11)); sub.setStyleSheet(f"color: {TEXT2};"); sub.setWordWrap(True)
        col.addWidget(sub)
        h.addLayout(col, 1)
        edit = QPushButton(self.tr("dev_edit")); edit.setCursor(Qt.CursorShape.PointingHandCursor)
        edit.setMinimumSize(88, 38); edit.setFont(QFont(UI_FONT, 10, QFont.Weight.DemiBold))
        edit.setStyleSheet(
            f"QPushButton {{ background: rgba(45,212,191,0.12); color: {ACCENT};"
            f"border: 1px solid {ACCENT}; border-radius: 12px; padding: 0 14px; }}"
            f"QPushButton:hover {{ background: rgba(45,212,191,0.22); }}")
        edit.clicked.connect(self._open_device_editor)
        h.addWidget(edit)
        return f

    def _open_device_editor(self):
        def build(col, choose):
            self._render_specs(col)
            done = self._btn("done_start", "primary"); done.setText("✓")
            done.setProperty("i18nKey", None); done.setMinimumHeight(42)
            done.clicked.connect(lambda: choose(True))
            col.addWidget(done)
        dlg = PickerDialog(self, self.tr("dev_title"), build)
        dlg.resize(560, 460)
        dlg.exec()
        self.model_options = profiler.recommend_models(self.profile)
        if self.rtf_base is not None:
            benchmark.annotate_and_recommend(self.model_options, self.rtf_base,
                                             language=self.choices["language"])
        idx = self.stack.currentIndex()
        if idx == 2:
            self._build_device_page()
        elif idx == 9:
            self._build_easy_summary()

    def _render_specs(self, target):
        while target.count():
            it = target.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        self.spec_edits = {}
        p = self.profile
        from PyQt6.QtWidgets import QCheckBox

        def add_row(icon, label_key, value, key, editable=True):
            r = QHBoxLayout(); r.setSpacing(10)
            ic = QLabel(icon); ic.setFont(QFont(UI_FONT, 14)); ic.setFixedWidth(26)
            lb = QLabel(); lb.setFont(QFont(UI_FONT, 11)); lb.setStyleSheet(f"color: {TEXT2};")
            self._t(lb, label_key); lb.setFixedWidth(150)
            r.addWidget(ic); r.addWidget(lb)
            if editable:
                ed = QLineEdit(str(value)); ed.setFont(QFont(UI_FONT, 11, QFont.Weight.DemiBold))
                ed.setStyleSheet(
                    f"QLineEdit {{ background: {CARD}; color: {TEXT}; border: 1px solid {BORDER};"
                    f"border-radius: 8px; padding: 6px 8px; }}"
                    f"QLineEdit:focus {{ border: 1px solid {ACCENT}; }}")
                ed.editingFinished.connect(self._on_spec_edited)
                self.spec_edits[key] = ed; r.addWidget(ed, 1)
            else:
                vl = QLabel(str(value)); vl.setFont(QFont(UI_FONT, 11, QFont.Weight.DemiBold))
                vl.setStyleSheet(f"color: {TEXT};"); r.addWidget(vl, 1)
            cont = QWidget(); cont.setLayout(r); target.addWidget(cont)

        add_row("🖥", "spec_os", f"{p['os']} ({p['machine']})", "os", editable=False)
        add_row("⚙️", "spec_cpu", p["cpu_name"], "cpu")
        add_row("🧠", "spec_ram", f"{p['ram_gb']:.0f}" if p["ram_gb"] else "8", "ram")

        gr = QHBoxLayout(); gr.setSpacing(10)
        ic = QLabel("🎮"); ic.setFont(QFont(UI_FONT, 14)); ic.setFixedWidth(26)
        lb = QLabel(); lb.setFont(QFont(UI_FONT, 11)); lb.setStyleSheet(f"color: {TEXT2};")
        self._t(lb, "spec_gpu"); lb.setFixedWidth(150)
        gr.addWidget(ic); gr.addWidget(lb)
        self.gpu_check = QCheckBox(); self.gpu_check.setChecked(bool(p["has_cuda"]))
        self.gpu_check.stateChanged.connect(self._on_spec_edited); gr.addWidget(self.gpu_check)
        gpu_val = p["gpu_name"] or ("Apple Silicon" if p["apple_silicon"] else self.tr("gpu_none"))
        self.gpu_name_edit = QLineEdit(str(gpu_val))
        self.gpu_name_edit.setFont(QFont(UI_FONT, 11, QFont.Weight.DemiBold))
        self.gpu_name_edit.setStyleSheet(
            f"QLineEdit {{ background: {CARD}; color: {TEXT}; border: 1px solid {BORDER};"
            f"border-radius: 8px; padding: 6px 8px; }}"
            f"QLineEdit:focus {{ border: 1px solid {ACCENT}; }}")
        self.gpu_name_edit.editingFinished.connect(self._on_spec_edited)
        gr.addWidget(self.gpu_name_edit, 1)
        gcont = QWidget(); gcont.setLayout(gr); target.addWidget(gcont)

        hint = QLabel(); hint.setFont(QFont(UI_FONT, 9)); hint.setStyleSheet(f"color: {DIM};")
        self._t(hint, "dev_edit_hint"); target.addWidget(hint)

    def _on_spec_edited(self):
        if not self.profile:
            return
        try:
            if "ram" in self.spec_edits:
                self.profile["ram_gb"] = float(self.spec_edits["ram"].text() or 0)
        except ValueError:
            pass
        if "cpu" in self.spec_edits:
            self.profile["cpu_name"] = self.spec_edits["cpu"].text()
        if hasattr(self, "gpu_check"):
            self.profile["has_cuda"] = self.gpu_check.isChecked()
            self.profile["gpu_name"] = self.gpu_name_edit.text()
        self.model_options = profiler.recommend_models(self.profile)
        if self.rtf_base is not None:
            benchmark.annotate_and_recommend(self.model_options, self.rtf_base,
                                             language=self.choices["language"])

    def _start_benchmark(self):
        device = "cuda" if self.profile["has_cuda"] else "cpu"
        compute = "float16" if self.profile["has_cuda"] else "int8"
        self.bench_proc = QProcess(self)
        self.bench_proc.finished.connect(self._on_benchmark_done)
        self.bench_proc.setProgram(sys.executable)
        self.bench_proc.setArguments(["-m", "guya.benchmark", "--device", device, "--compute", compute])
        self.bench_proc.start()

    def _on_benchmark_done(self, code, _s):
        out = ""
        try:
            out = bytes(self.bench_proc.readAllStandardOutput()).decode("utf-8", "replace")
        except Exception:
            pass
        rtf = None
        for line in out.splitlines():
            if line.startswith("BENCH_JSON:"):
                try:
                    rtf = json.loads(line[len("BENCH_JSON:"):]).get("rtf_base")
                except Exception:
                    pass
        if rtf is not None:
            self.rtf_base = rtf
            benchmark.annotate_and_recommend(self.model_options, rtf,
                                             language=self.choices["language"])
        self._after_analysis()

    # ---- helpers for recommendations ----

    def _offline_options(self):
        return [o for o in self.model_options if o["backend"] != "cloud"]

    def _recommended_offline(self):
        offs = [o for o in self._offline_options() if o["enabled"]]
        if not offs:
            return None
        rec = [o for o in offs if o["recommended"]]
        if rec:
            return rec[0]
        # else most accurate enabled
        return max(offs, key=lambda o: benchmark.ACCURACY_RANK.get(o["model_size"], 0))

    def _compute_recommended_mode(self):
        if self.choices["language"] == "dual":
            self.recommended_mode = "dual"
            return
        rec = [o for o in self.model_options if o["recommended"]]
        if rec and rec[0]["backend"] == "cloud":
            self.recommended_mode = "online"
        else:
            self.recommended_mode = "offline"

    # ---- Page 3: Mode ----

    def _page_mode(self):
        w, lay = self._page()
        self._heading(lay, "mode_title", "mode_sub")
        area, col = self._scroll_area()
        self.mode_container = QVBoxLayout(); self.mode_container.setSpacing(12)
        col.addLayout(self.mode_container)
        col.addStretch()
        lay.addWidget(area, 1)
        return w

    def _easy_hint_widget(self):
        h = QLabel(self.tr("easy_hint")); h.setFont(QFont(UI_FONT, 10, QFont.Weight.DemiBold))
        h.setWordWrap(True)
        h.setStyleSheet(f"color: {ACCENT}; background: rgba(45,212,191,0.10);"
                        f"border-radius: 9px; padding: 9px 12px;")
        return h

    def _build_mode_cards(self):
        while self.mode_container.count():
            it = self.mode_container.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        self.mode_cards = []
        if self.easy:
            self.mode_container.addWidget(self._easy_hint_widget())
        self._compute_recommended_mode()
        best = self._recommended_offline()
        best_line = ""
        if best:
            lat = best.get("predicted_latency_sec")
            tk = {"accurate": "title_accurate", "balanced": "title_balanced",
                  "fast": "title_fast"}.get(best["id"], "title_fast")
            best_line = self.tr("mode_best", m=self.tr(tk),
                                n=f"{lat:g}" if lat is not None else "?")

        specs = [
            ("offline", "💻", "mode_offline", "mode_off_how", best_line,
             ["mode_off_p1", "mode_off_p2"], ["mode_off_c1"]),
            ("online", "☁️", "mode_online", "mode_on_how", self.tr("mode_online_model"),
             ["mode_on_p1", "mode_on_p2"], ["mode_on_c1", "mode_on_c2"]),
            ("dual", "🔀", "mode_dual", "mode_du_how", self.tr("mode_dual_note"),
             ["mode_du_p1", "mode_du_p2"], ["mode_du_c1"]),
        ]
        for mid, icon, tk, how_k, detail, pros, cons in specs:
            c = Card(self._select_mode, mid)
            c.setMinimumHeight(176)
            c._body.setContentsMargins(18, 15, 18, 15)
            c._body.setSpacing(7)
            # Title row: icon + name + recommended badge
            top = QHBoxLayout(); top.setSpacing(10)
            ic = QLabel(icon); ic.setFont(QFont(UI_FONT, 17)); top.addWidget(ic)
            t = QLabel(); t.setFont(QFont(UI_FONT, 18, QFont.Weight.Bold))
            t.setStyleSheet(f"color: {TEXT};"); self._t(t, tk); top.addWidget(t)
            if mid == self.recommended_mode:
                badge = QLabel("★ " + self.tr("recommended"))
                badge.setFont(QFont(UI_FONT, 10, QFont.Weight.DemiBold))
                badge.setStyleSheet(f"color: {ACCENT}; background: rgba(45,212,191,0.14);"
                                    f"border-radius: 9px; padding: 3px 11px;")
                top.addWidget(badge)
            top.addStretch()
            c._body.addLayout(top)
            # How it works (plain language)
            how = QLabel(); how.setFont(QFont(UI_FONT, 11)); how.setWordWrap(True)
            how.setStyleSheet(f"color: {TEXT};"); self._t(how, how_k); c._body.addWidget(how)
            # Key fact (best model / model used / example)
            if detail:
                d = QLabel(detail); d.setFont(QFont(UI_FONT, 10, QFont.Weight.DemiBold))
                d.setStyleSheet(f"color: {ACCENT};"); d.setWordWrap(True); c._body.addWidget(d)
            # Pros / cons, each on its own line for clarity
            for k in pros:
                l = QLabel("✓  " + self.tr(k)); l.setFont(QFont(UI_FONT, 10)); l.setWordWrap(True)
                l.setStyleSheet(f"color: {GREEN};"); c._body.addWidget(l)
            for k in cons:
                l = QLabel("✕  " + self.tr(k)); l.setFont(QFont(UI_FONT, 10)); l.setWordWrap(True)
                l.setStyleSheet(f"color: {RED};"); c._body.addWidget(l)
            c.set_selected(self.mode == mid)
            c.style_self()
            self.mode_cards.append(c); self.mode_container.addWidget(c)
        # default selection
        if self.mode is None:
            self.mode = self.recommended_mode
            for c in self.mode_cards:
                c.set_selected(c.payload == self.mode)

    def _select_mode(self, card):
        self.mode = card.payload
        for c in self.mode_cards:
            c.set_selected(c is card)
        self._update_nav()

    # ---- Page 4: Setup (dynamic per mode) ----

    def _page_setup(self):
        w, lay = self._page()
        self.setup_head = QLabel(); self.setup_head.setFont(QFont(UI_FONT, 22, QFont.Weight.Bold))
        self.setup_head.setStyleSheet(f"color: {TEXT};")
        lay.addWidget(self.setup_head)
        self.setup_sub = QLabel(); self.setup_sub.setFont(QFont(UI_FONT, 11))
        self.setup_sub.setWordWrap(True); self.setup_sub.setStyleSheet(f"color: {TEXT2};")
        lay.addWidget(self.setup_sub)
        area, col = self._scroll_area()
        self.setup_col = col
        lay.addWidget(area, 1)
        return w

    def _section_header(self, number, title, subtitle):
        """A numbered step header: ① Title  /  subtitle — for the Dual setup."""
        box = QWidget()
        h = QHBoxLayout(box); h.setContentsMargins(0, 4, 0, 0); h.setSpacing(12)
        num = QLabel(str(number))
        num.setFont(QFont(UI_FONT, 13, QFont.Weight.Bold))
        num.setFixedSize(30, 30)
        num.setAlignment(Qt.AlignmentFlag.AlignCenter)
        num.setStyleSheet(f"color: {ACCENT_TEXT}; background: {ACCENT}; border-radius: 15px;")
        h.addWidget(num)
        txt = QVBoxLayout(); txt.setSpacing(1)
        t = QLabel(title); t.setFont(QFont(UI_FONT, 14, QFont.Weight.Bold))
        t.setStyleSheet(f"color: {TEXT};")
        s = QLabel(subtitle); s.setFont(QFont(UI_FONT, 10)); s.setWordWrap(True)
        s.setStyleSheet(f"color: {TEXT2};")
        txt.addWidget(t); txt.addWidget(s)
        h.addLayout(txt, 1)
        return box

    def _build_setup(self):
        # Clear
        while self.setup_col.count():
            it = self.setup_col.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        self.model_cards = []
        if self.easy:
            self.setup_col.addWidget(self._easy_hint_widget())

        if self.mode == "offline":
            self.setup_head.setText(self.tr("setup_off_title"))
            self.setup_sub.setText(self.tr("setup_off_sub"))
            self._add_model_cards(self.setup_col)
        elif self.mode == "online":
            self.setup_head.setText(self.tr("setup_on_title"))
            self.setup_sub.setText(self.tr("setup_on_sub"))
            self.setup_col.addWidget(self._build_cloud_panel())
        else:  # dual — two clearly numbered steps
            self.setup_head.setText(self.tr("setup_du_title"))
            self.setup_sub.setText(self.tr("setup_du_sub"))
            self.setup_col.addWidget(self._section_header(
                "1", self.tr("setup_du_offline"), self.tr("setup_du_off_sub")))
            self._add_model_cards(self.setup_col)
            self.setup_col.addSpacing(6)
            self.setup_col.addWidget(self._section_header(
                "2", self.tr("setup_du_online"), self.tr("setup_du_on_sub")))
            self.setup_col.addWidget(self._build_cloud_panel())
        self.setup_col.addStretch()
        self._update_nav()

    def _add_model_cards(self, col):
        prev = self.selected_model_id
        to_sel = None
        for opt in self._offline_options():
            card = Card(self._select_model, opt, enabled=opt["enabled"])
            self._fill_model_card(card, opt)
            self.model_cards.append(card)
            col.addWidget(card)
            if (prev and opt["id"] == prev) or (not prev and opt["recommended"] and opt["enabled"]):
                to_sel = card
        if to_sel is None:
            rec = self._recommended_offline()
            for c in self.model_cards:
                if rec and c.payload["id"] == rec["id"]:
                    to_sel = c
        if to_sel:
            self._select_model(to_sel)

    def _pill(self, key, color):
        p = QLabel(); p.setFont(QFont(UI_FONT, 9, QFont.Weight.Bold))
        rgba = "rgba(52,211,153,0.16)" if color == GREEN else "rgba(45,212,191,0.18)"
        p.setStyleSheet(f"color: {color}; background: {rgba}; border-radius: 9px; padding: 3px 11px;")
        self._t(p, key)
        return p

    def _fill_model_card(self, card, opt):
        card.setMinimumHeight(150)
        perf = MODEL_PERF.get(opt["id"], {"fa_acc": 2, "en_acc": 3, "speed": 3})
        tk = {"accurate": "title_accurate", "balanced": "title_balanced",
              "fast": "title_fast"}.get(opt["id"], "title_fast")
        top = QHBoxLayout(); top.setSpacing(10)
        t = QLabel(); t.setFont(QFont(UI_FONT, 18, QFont.Weight.Bold))
        t.setStyleSheet(f"color: {TEXT};"); self._t(t, tk); top.addWidget(t)
        if opt["recommended"]:
            badge = QLabel("★ " + self.tr("recommended"))
            badge.setFont(QFont(UI_FONT, 10, QFont.Weight.DemiBold))
            badge.setStyleSheet(f"color: {ACCENT}; background: rgba(45,212,191,0.14);"
                                f"border-radius: 9px; padding: 3px 11px;")
            top.addWidget(badge)
        top.addStretch()
        cached = model_is_cached(opt["model_size"])
        ind = QLabel(self.tr("installed" if cached else "not_installed"))
        ind.setFont(QFont(UI_FONT, 9, QFont.Weight.DemiBold))
        ind.setStyleSheet(f"color: {GREEN if cached else TEXT2};"); top.addWidget(ind)
        top.addWidget(self._pill("offline", GREEN))
        card._body.addLayout(top)

        meta_bits = [f"{self.tr('model_name')}: {opt['model_size']}"]
        lat = opt.get("predicted_latency_sec")
        if lat is not None:
            meta_bits.append(self.tr("lat_est", n=f"{lat:g}"))
        meta = QLabel("   ·   ".join(meta_bits)); meta.setFont(QFont(UI_FONT, 11))
        meta.setWordWrap(True); meta.setStyleSheet(f"color: {ACCENT if lat is not None else TEXT2};")
        card._body.addWidget(meta)

        for lk, acc in (("lbl_fa", perf["fa_acc"]), ("lbl_en", perf["en_acc"])):
            line = QLabel(f"{self.tr(lk)}   {self.tr('perf_acc')} {_dots(acc)}    "
                          f"{self.tr('perf_speed')} {_dots(perf['speed'])}")
            line.setFont(QFont(UI_FONT, 11)); line.setWordWrap(True)
            line.setStyleSheet(f"color: {TEXT2};"); card._body.addWidget(line)

        if opt.get("pros"):
            pl = QLabel("✓  " + "   ·   ".join(self.tr(k) for k in opt["pros"]))
            pl.setFont(QFont(UI_FONT, 10)); pl.setWordWrap(True)
            pl.setStyleSheet(f"color: {GREEN};"); card._body.addWidget(pl)
        if opt.get("cons"):
            cl = QLabel("✕  " + "   ·   ".join(self.tr(k) for k in opt["cons"]))
            cl.setFont(QFont(UI_FONT, 10)); cl.setWordWrap(True)
            cl.setStyleSheet(f"color: {RED};"); card._body.addWidget(cl)
        if not opt["enabled"]:
            ns = QLabel("· " + self.tr("not_suitable")); ns.setFont(QFont(UI_FONT, 10))
            ns.setStyleSheet(f"color: {DIM};"); card._body.addWidget(ns)
        card.style_self()

    def _select_model(self, card):
        for c in self.model_cards:
            c.set_selected(c is card)
        self.selected_model_id = card.payload["id"]
        self.choices["model_opt"] = card.payload
        self._update_nav()

    def _build_cloud_panel(self):
        f = QFrame(); f.setObjectName("cp")
        f.setStyleSheet(f"QFrame#cp {{ background: {CARD}; border: 1.5px solid {ACCENT};"
                        f"border-radius: 14px; }} QLabel {{ background: transparent; border: none; }}")
        v = QVBoxLayout(f); v.setContentsMargins(20, 18, 20, 18); v.setSpacing(11)
        title = QLabel(); title.setFont(QFont(UI_FONT, 15, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {TEXT};"); self._t(title, "cloud_guide_title"); v.addWidget(title)
        intro = QLabel(); intro.setFont(QFont(UI_FONT, 11)); intro.setWordWrap(True)
        intro.setStyleSheet(f"color: {TEXT2};"); self._t(intro, "cloud_intro"); v.addWidget(intro)
        for sk in ("cloud_step1", "cloud_step2", "cloud_step3"):
            s = QLabel(); s.setFont(QFont(UI_FONT, 12)); s.setStyleSheet(f"color: {TEXT};")
            s.setWordWrap(True); s.setTextFormat(Qt.TextFormat.RichText); s.setOpenExternalLinks(True)
            self._t(s, sk); v.addWidget(s)
        self.key_edit = QLineEdit(); self._t(self.key_edit, "cloud_key_ph", placeholder=True)
        self.key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_edit.setMinimumHeight(44); self.key_edit.setFont(QFont(UI_FONT, 12))
        self.key_edit.setText(self.choices.get("cloud_api_key", ""))
        self.key_edit.setStyleSheet(
            f"QLineEdit {{ background: {BG}; color: {TEXT}; border: 1px solid {BORDER};"
            f"border-radius: 10px; padding: 8px 14px; }}"
            f"QLineEdit:focus {{ border: 1px solid {ACCENT}; }}")
        self.key_edit.textChanged.connect(self._on_key_changed)
        v.addWidget(self.key_edit)
        ex = QLabel(); ex.setFont(QFont(UI_FONT, 10)); ex.setStyleSheet(f"color: {DIM};")
        self._t(ex, "cloud_example"); v.addWidget(ex)
        row = QHBoxLayout()
        self.test_btn = self._btn("cloud_test", "primary"); self.test_btn.setMinimumSize(110, 42)
        self.test_btn.clicked.connect(self._test_cloud); row.addWidget(self.test_btn)
        self.cloud_status = QLabel(); self.cloud_status.setFont(QFont(UI_FONT, 11))
        self.cloud_status.setStyleSheet(f"color: {TEXT2};"); self.cloud_status.setWordWrap(True)
        row.addWidget(self.cloud_status, 1)
        v.addLayout(row)
        priv = QLabel(); priv.setFont(QFont(UI_FONT, 10)); priv.setStyleSheet(f"color: {DIM};")
        priv.setWordWrap(True); self._t(priv, "cloud_privacy"); v.addWidget(priv)
        return f

    def _on_key_changed(self, text):
        self.choices["cloud_api_key"] = text.strip()
        self.cloud_status.setText("")
        self._update_nav()
        self._update_easy_install()

    def _test_cloud(self):
        key = self.key_edit.text().strip()
        if not key:
            self.cloud_status.setStyleSheet(f"color: {RED};")
            self.cloud_status.setText(self.tr("cloud_paste_first")); return
        self.test_btn.setEnabled(False)
        self.cloud_status.setStyleSheet(f"color: {ACCENT};")
        self.cloud_status.setText(self.tr("cloud_testing")); QApplication.processEvents()
        ok, msg = cloud_engine.test_connection(key, provider="groq")
        self.cloud_status.setStyleSheet(f"color: {GREEN if ok else RED};")
        self.cloud_status.setText(("✓ " if ok else "✗ ") + msg)
        self.test_btn.setEnabled(True); self._update_nav()

    # ---- Page 5: Key ----

    def _page_key(self):
        w, lay = self._page()
        self._heading(lay, "key_title", "key_sub")
        if IS_MAC:
            m = QLabel(); m.setFont(QFont(UI_FONT, 11)); m.setWordWrap(True)
            m.setStyleSheet(f"color: {TEXT}; background: {CARD}; border: 1px solid {BORDER};"
                            f"border-radius: 9px; padding: 12px;")
            self._t(m, "key_mac"); lay.addWidget(m)
            self.choices["hotkey_vk"] = 0xA4; self.choices["hotkey_label"] = "⌥"
        else:
            self.key_capture = HotkeyCapture(self.tr("key_capture"))
            self.key_capture.setStyleSheet(
                f"QPushButton {{ background: {CARD}; color: {TEXT};"
                f"border: 1px solid {BORDER}; border-radius: 9px; padding: 10px; }}")
            self.key_capture.captured.connect(self._on_key); lay.addWidget(self.key_capture)
            h = QLabel(); h.setFont(QFont(UI_FONT, 9)); h.setStyleSheet(f"color: {DIM};")
            self._t(h, "key_hint"); lay.addWidget(h)
        assistant_note = QLabel(
            self.tr("assistant_key_note", k=self._assistant_key_choice()[1])
        )
        assistant_note.setFont(QFont(UI_FONT, 10))
        assistant_note.setWordWrap(True)
        assistant_note.setStyleSheet(f"color: {ACCENT};")
        lay.addWidget(assistant_note)
        lay.addStretch()
        return w

    def _assistant_key_choice(self):
        if IS_MAC:
            return 0, "Right Command (⌘)"
        cfg = guya_config.load_config()
        hotkey = cfg.get("assistant", {}).get("hotkey", {})
        vk = hotkey.get("vk", 119)
        label = hotkey.get("label", "F8")
        if vk == self.choices.get("hotkey_vk"):
            return 120, "F9"
        return vk, label

    def _on_key(self, vk, label):
        self.choices["hotkey_vk"] = vk; self.choices["hotkey_label"] = label
        self.key_capture.setText(self.tr("key_chosen", k=label))

    # ---- Page 6: Review ----

    def _page_review(self):
        w, lay = self._page()
        self._heading(lay, "review_title", "review_sub")
        self.summary_box = QFrame()
        self.summary_box.setStyleSheet(
            f"QFrame {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 14px; }}"
            f"QLabel {{ border: none; background: transparent; }}")
        self.summary_layout = QVBoxLayout(self.summary_box)
        self.summary_layout.setContentsMargins(22, 18, 22, 18); self.summary_layout.setSpacing(14)
        lay.addWidget(self.summary_box)
        self.finish_tip = QLabel(); self.finish_tip.setFont(QFont(UI_FONT, 11))
        self.finish_tip.setStyleSheet(f"color: {TEXT2};"); self.finish_tip.setWordWrap(True)
        lay.addWidget(self.finish_tip)
        lay.addStretch()
        return w

    def _refresh_summary(self):
        if not hasattr(self, "summary_layout"):
            return
        while self.summary_layout.count():
            it = self.summary_layout.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        mode_lbl = {"offline": "sum_offline", "online": "sum_online", "dual": "sum_dual"}.get(
            self.mode, "sum_offline")
        lang = self.tr({"fa": "lbl_fa", "en": "lbl_en", "dual": "lbl_dual"}.get(
            self.choices["language"], "lbl_fa"))
        opt = self.choices["model_opt"] or {}
        rows = [("🧩", "sum_mode", self.tr(mode_lbl))]
        if self.mode in ("offline", "dual") and opt:
            tk = {"accurate": "title_accurate", "balanced": "title_balanced",
                  "fast": "title_fast"}.get(opt.get("id"), "title_fast")
            rows.append(("🧠", "sum_model", f"{self.tr(tk)}  ·  {opt.get('model_size','?')}"))
        if self.mode == "online":
            rows.append(("🧠", "sum_model", "large-v3 (cloud)"))
        rows.append(("🗣", "sum_language", lang))
        rows.append(("⌨️", "sum_key", self.choices["hotkey_label"]))
        rows.append(("✨", "sum_assistant_key", self._assistant_key_choice()[1]))
        for icon, lk, val in rows:
            r = QHBoxLayout(); r.setSpacing(12)
            ic = QLabel(icon); ic.setFont(QFont(UI_FONT, 15)); ic.setFixedWidth(28)
            lb = QLabel(self.tr(lk)); lb.setFont(QFont(UI_FONT, 12))
            lb.setStyleSheet(f"color: {TEXT2};"); lb.setFixedWidth(150)
            vl = QLabel(val); vl.setFont(QFont(UI_FONT, 13, QFont.Weight.DemiBold))
            vl.setStyleSheet(f"color: {TEXT};")
            r.addWidget(ic); r.addWidget(lb); r.addWidget(vl, 1)
            cont = QWidget(); cont.setLayout(r); self.summary_layout.addWidget(cont)
        tip = {"offline": "tip_offline", "online": "tip_cloud", "dual": "tip_dual"}.get(
            self.mode, "tip_offline")
        self.finish_tip.setText(self.tr(tip))

    # ---- Page 7: Download ----

    def _page_download(self):
        w, lay = self._page()
        lay.addStretch()
        self.dl_title = QLabel(); self.dl_title.setFont(QFont(UI_FONT, 20, QFont.Weight.Bold))
        self.dl_title.setStyleSheet(f"color: {TEXT};")
        self.dl_title.setAlignment(Qt.AlignmentFlag.AlignCenter); self.dl_title.setWordWrap(True)
        lay.addWidget(self.dl_title)
        self.dl_state = QLabel(); self.dl_state.setFont(QFont(UI_FONT, 12, QFont.Weight.DemiBold))
        self.dl_state.setAlignment(Qt.AlignmentFlag.AlignCenter); self.dl_state.setWordWrap(True)
        lay.addWidget(self.dl_state)
        self.dl_bar = QProgressBar(); self.dl_bar.setRange(0, 100); self.dl_bar.setValue(0)
        self.dl_bar.setMinimumHeight(26)
        self.dl_bar.setStyleSheet(
            f"QProgressBar {{ background: {CARD}; border: 1px solid {BORDER};"
            f"border-radius: 13px; text-align: center; color: {TEXT}; }}"
            f"QProgressBar::chunk {{ background: {ACCENT}; border-radius: 12px; }}")
        lay.addWidget(self.dl_bar)
        self.dl_status = QLabel(); self.dl_status.setFont(QFont(UI_FONT, 11))
        self.dl_status.setStyleSheet(f"color: {TEXT2};")
        self.dl_status.setAlignment(Qt.AlignmentFlag.AlignCenter); lay.addWidget(self.dl_status)
        ctl = QHBoxLayout(); ctl.addStretch()
        self.dl_cancel_btn = self._btn("cancel", "ghost"); self.dl_cancel_btn.setMinimumSize(130, 40)
        self.dl_cancel_btn.clicked.connect(self._cancel_download); ctl.addWidget(self.dl_cancel_btn)
        self.dl_pause_btn = self._btn("dl_pause", "primary"); self.dl_pause_btn.setMinimumSize(130, 40)
        self.dl_pause_btn.clicked.connect(self._toggle_pause); ctl.addWidget(self.dl_pause_btn)
        ctl.addStretch(); lay.addLayout(ctl)
        lay.addStretch()
        return w

    def _cancel_download(self):
        self.dl_paused = True
        if self.dl_timer:
            self.dl_timer.stop()
        if self.dl_proc and self.dl_proc.state() != QProcess.ProcessState.NotRunning:
            self.dl_proc.kill()
        self.stack.setCurrentIndex(6); self._sync_step(); self._update_nav()

    # ---- Page 8: Done / How to use ----

    def _page_done(self):
        w, lay = self._page()
        lay.addStretch()
        check = QLabel("✓"); check.setFont(QFont(UI_FONT, 40, QFont.Weight.Bold))
        check.setStyleSheet(f"color: {GREEN};"); check.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(check)
        self.done_title = QLabel(); self.done_title.setFont(QFont(UI_FONT, 22, QFont.Weight.Bold))
        self.done_title.setStyleSheet(f"color: {TEXT};")
        self.done_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.done_title)
        lay.addSpacing(10)

        self.done_box = QFrame()
        self.done_box.setStyleSheet(
            f"QFrame {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 14px; }}"
            f"QLabel {{ border: none; background: transparent; }}")
        self.done_layout = QVBoxLayout(self.done_box)
        self.done_layout.setContentsMargins(22, 18, 22, 18); self.done_layout.setSpacing(12)
        lay.addWidget(self.done_box)

        self.done_more = QLabel(); self.done_more.setFont(QFont(UI_FONT, 10))
        self.done_more.setStyleSheet(f"color: {DIM};"); self.done_more.setWordWrap(True)
        self.done_more.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.done_more)
        lay.addSpacing(8)

        row = QHBoxLayout(); row.addStretch()
        self.done_btn = self._btn("done_start", "green"); self.done_btn.setMinimumSize(180, 46)
        self.done_btn.clicked.connect(self._complete)
        row.addWidget(self.done_btn); row.addStretch()
        lay.addLayout(row)
        lay.addStretch()
        return w

    def _fill_done(self):
        if not hasattr(self, "done_layout"):
            return
        self.done_title.setText(self.tr("done_title"))
        self.done_more.setText(self.tr("done_more"))
        while self.done_layout.count():
            it = self.done_layout.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        head = QLabel(self.tr("done_how")); head.setFont(QFont(UI_FONT, 13, QFont.Weight.DemiBold))
        head.setStyleSheet(f"color: {ACCENT};")
        self.done_layout.addWidget(head)
        key = self.choices["hotkey_label"]
        assistant_key = self._assistant_key_choice()[1]
        steps = [("👆", self.tr("done_s1")),
                 ("🎙", self.tr("done_s2", k=key)),
                 ("✨", self.tr("done_s3")),
                 ("🧭", self.tr("done_s4", k=assistant_key))]
        for icon, text in steps:
            r = QHBoxLayout(); r.setSpacing(12)
            ic = QLabel(icon); ic.setFont(QFont(UI_FONT, 16)); ic.setFixedWidth(30)
            tl = QLabel(text); tl.setFont(QFont(UI_FONT, 12)); tl.setWordWrap(True)
            tl.setStyleSheet(f"color: {TEXT};")
            r.addWidget(ic); r.addWidget(tl, 1)
            cont = QWidget(); cont.setLayout(r); self.done_layout.addWidget(cont)

    def _show_done(self):
        self._fill_done()
        self.stack.setCurrentIndex(8); self._sync_step(); self._update_nav()

    # ---- Page 9: Easy summary (everything on one page, each changeable) ----

    def _page_easy_summary(self):
        w, lay = self._page()
        self._heading(lay, "es_title", "es_sub")
        area, col = self._scroll_area()
        self.easy_col = col
        lay.addWidget(area, 1)
        row = QHBoxLayout(); row.addStretch()
        self.easy_install_btn = self._btn("es_install", "green")
        self.easy_install_btn.setMinimumSize(180, 46)
        self.easy_install_btn.clicked.connect(self._easy_install)
        row.addWidget(self.easy_install_btn); row.addStretch()
        lay.addLayout(row)
        return w

    def _build_easy_summary(self):
        self._compute_recommended_mode()
        if self.mode is None:
            self.mode = self.recommended_mode
        if self.mode in ("offline", "dual") and not self.choices.get("model_opt"):
            rec = self._recommended_offline()
            if rec:
                self.choices["model_opt"] = rec
                self.selected_model_id = rec["id"]

        while self.easy_col.count():
            it = self.easy_col.takeAt(0)
            if it.widget():
                it.widget().deleteLater()

        # Device config at the top (changeable via the same modal as Advanced).
        if self.profile is not None:
            self.easy_col.addWidget(self._device_card())

        # --- How it runs (mode) ---
        meta = next((m for m in MODE_META if m[0] == self.mode), MODE_META[0])
        self.easy_col.addWidget(self._easy_row("🧩", self.tr("es_mode"),
                                               self.tr(meta[2]), self._open_mode_picker))

        # --- Model (offline / dual) ---
        if self.mode in ("offline", "dual"):
            opt = self.choices.get("model_opt") or {}
            tkmap = {"accurate": "title_accurate", "balanced": "title_balanced", "fast": "title_fast"}
            self.easy_col.addWidget(self._easy_row(
                "🧠", self.tr("es_model"),
                f"{self.tr(tkmap.get(opt.get('id'),'title_fast'))} · {opt.get('model_size','?')}",
                self._open_model_picker))

        # --- Online key (online / dual) — the cloud guide + field ---
        if self.mode in ("online", "dual"):
            self.easy_col.addWidget(self._build_cloud_panel())

        # --- Push-to-talk key ---
        if IS_MAC:
            self.choices["hotkey_vk"] = 0xA4; self.choices["hotkey_label"] = "⌥"
            self.easy_col.addWidget(self._easy_row("⌨️", self.tr("es_key"),
                                                   self.tr("es_mac_key"), None))
        else:
            self.easy_col.addWidget(self._easy_row("⌨️", self.tr("es_key"),
                                                   self.choices["hotkey_label"], self._open_key_picker))
        self.easy_col.addWidget(self._easy_row(
            "✨",
            self.tr("es_assistant_key"),
            self._assistant_key_choice()[1],
            None,
        ))

        self.easy_col.addStretch()
        self._update_easy_install()

    def _easy_row(self, icon, label, value, on_change):
        f = QFrame()
        f.setStyleSheet(f"QFrame {{ background: {_grad('#1a1a23', '#15151d')};"
                        f"border: 1px solid {BORDER}; border-radius: 16px; }}"
                        f"QLabel {{ border: none; background: transparent; }}")
        _shadow(f, blur=18, dy=4, alpha=80)
        h = QHBoxLayout(f); h.setContentsMargins(18, 14, 18, 14); h.setSpacing(12)
        ic = QLabel(icon); ic.setFont(QFont(UI_FONT, 17)); ic.setFixedWidth(32)
        h.addWidget(ic)
        tx = QVBoxLayout(); tx.setSpacing(2)
        lb = QLabel(label); lb.setFont(QFont(UI_FONT, 10)); lb.setStyleSheet(f"color: {TEXT2};")
        vl = QLabel(value); vl.setFont(QFont(UI_FONT, 14, QFont.Weight.DemiBold))
        vl.setStyleSheet(f"color: {TEXT};"); vl.setWordWrap(True)
        tx.addWidget(lb); tx.addWidget(vl)
        h.addLayout(tx, 1)
        if on_change is not None:
            cb = QPushButton(self.tr("es_change")); cb.setCursor(Qt.CursorShape.PointingHandCursor)
            cb.setMinimumSize(92, 36); cb.setFont(QFont(UI_FONT, 10, QFont.Weight.DemiBold))
            cb.setStyleSheet(
                f"QPushButton {{ background: rgba(45,212,191,0.12); color: {ACCENT};"
                f"border: 1px solid {ACCENT}; border-radius: 11px; padding: 0 14px; }}"
                f"QPushButton:hover {{ background: rgba(45,212,191,0.22); }}")
            cb.clicked.connect(on_change)
            h.addWidget(cb)
        return f

    def _easy_option_card(self, icon, title, how, pros, cons, selected, on_pick):
        c = Card(lambda card: on_pick(), None)
        c.set_selected(selected)
        top = QHBoxLayout(); top.setSpacing(8)
        ic = QLabel(icon); ic.setFont(QFont(UI_FONT, 15)); top.addWidget(ic)
        t = QLabel(title); t.setFont(QFont(UI_FONT, 14, QFont.Weight.Bold))
        t.setStyleSheet(f"color: {TEXT};"); top.addWidget(t); top.addStretch()
        c._body.addLayout(top)
        hw = QLabel(how); hw.setFont(QFont(UI_FONT, 10)); hw.setWordWrap(True)
        hw.setStyleSheet(f"color: {TEXT2};"); c._body.addWidget(hw)
        for k in pros:
            l = QLabel("✓  " + self.tr(k)); l.setFont(QFont(UI_FONT, 9)); l.setWordWrap(True)
            l.setStyleSheet(f"color: {GREEN};"); c._body.addWidget(l)
        for k in cons:
            l = QLabel("✕  " + self.tr(k)); l.setFont(QFont(UI_FONT, 9)); l.setWordWrap(True)
            l.setStyleSheet(f"color: {RED};"); c._body.addWidget(l)
        c.style_self()
        return c

    # ---- Modal pickers (float over the page) ----

    def _open_mode_picker(self):
        def build(col, choose):
            for mid, icon, tk, how_k, pros, cons in MODE_META:
                col.addWidget(self._easy_option_card(
                    icon, self.tr(tk), self.tr(how_k), pros, cons,
                    selected=(mid == self.mode), on_pick=lambda m=mid: choose(m)))
        dlg = PickerDialog(self, self.tr("es_mode"), build)
        dlg.resize(dlg.sizeHint())
        if dlg.exec() and dlg.value:
            self.mode = dlg.value
            self.choices["model_opt"] = None
            self.selected_model_id = None
            self._build_easy_summary()

    def _open_model_picker(self):
        cur = (self.choices.get("model_opt") or {}).get("id")

        def build(col, choose):
            for o in self._offline_options():
                card = Card(lambda c, oo=o: (choose(oo) if oo["enabled"] else None),
                            o, enabled=o["enabled"])
                self._fill_model_card(card, o)
                card.set_selected(o["id"] == cur); card.style_self()
                col.addWidget(card)
        dlg = PickerDialog(self, self.tr("es_model"), build)
        dlg.resize(dlg.sizeHint())
        if dlg.exec() and dlg.value:
            self.choices["model_opt"] = dlg.value
            self.selected_model_id = dlg.value["id"]
            self._build_easy_summary()

    def _open_key_picker(self):
        def build(col, choose):
            cap = HotkeyCapture(self.tr("key_capture"))
            cap.setMinimumHeight(56)
            cap.setStyleSheet(f"QPushButton {{ background: {CARD}; color: {TEXT};"
                              f"border: 1px solid {BORDER}; border-radius: 12px; padding: 14px;"
                              f"font-size: 13pt; }}")
            cap.captured.connect(lambda vk, label: choose((vk, label)))
            col.addWidget(cap)
            hint = QLabel(self.tr("key_hint")); hint.setFont(QFont(UI_FONT, 10))
            hint.setStyleSheet(f"color: {DIM};"); hint.setWordWrap(True)
            col.addWidget(hint)
        dlg = PickerDialog(self, self.tr("es_key"), build)
        dlg.resize(560, 280)
        if dlg.exec() and dlg.value:
            self.choices["hotkey_vk"], self.choices["hotkey_label"] = dlg.value
            self._build_easy_summary()

    def _update_easy_install(self):
        if not hasattr(self, "easy_install_btn"):
            return
        ok = True
        if self.mode == "online":
            ok = bool(self.choices.get("cloud_api_key"))
        elif self.mode == "dual":
            ok = bool(self.choices.get("model_opt") and self.choices.get("cloud_api_key"))
        elif self.mode == "offline":
            ok = bool(self.choices.get("model_opt"))
        self.easy_install_btn.setEnabled(ok)

    def _easy_install(self):
        self._finish()

    # ---- Navigation ----

    def _go_next(self):
        idx = self.stack.currentIndex()
        if idx == 6:
            self._finish(); return
        # After Language → the Loading screen analyzes the device, then routes to
        # the Easy summary (easy) or the Device config page (advanced).
        if idx == 1:
            self._start_loading(); return
        new = idx + 1
        self.stack.setCurrentIndex(new)
        if new == 3:
            self._build_mode_cards()
        elif new == 4:
            self._build_setup()
        elif new == 6:
            self._refresh_summary()
        self._sync_step(); self._update_nav()

    def _go_back(self):
        idx = self.stack.currentIndex()
        if idx == 9:                    # Easy summary → back to Language
            self.stack.setCurrentIndex(1)
            self._sync_step(); self._update_nav(); return
        if 0 < idx <= 6:
            new = idx - 1
            self.stack.setCurrentIndex(new)
            if new == 3:
                self._build_mode_cards()
            elif new == 4:
                self._build_setup()
        self._sync_step(); self._update_nav()

    def _sync_step(self):
        cur = PAGE_TO_STEP[self.stack.currentIndex()]
        for i, lbl in enumerate(self.step_labels):
            name = self.tr(STEPS_KEYS[i])
            lbl.setText(f"{i+1}  {name}" if i == cur else f"{i+1}")
            lbl.setStyleSheet(f"color: {ACCENT if i==cur else (TEXT2 if i<cur else DIM)};")

    def _update_nav(self):
        idx = self.stack.currentIndex()
        # Welcome (0), Download (7), Done (8), Loading (10) use no nav bar.
        if idx in (0, 7, 8, 10):
            self.back_btn.setVisible(False); self.next_btn.setVisible(False); return
        # Easy summary (9): Back only (Install is in-page).
        if idx == 9:
            self.back_btn.setVisible(True); self.back_btn.setEnabled(True)
            self.next_btn.setVisible(False)
            return
        self.back_btn.setVisible(True); self.next_btn.setVisible(True)
        self.back_btn.setEnabled(idx > 0)
        can = True
        if idx == 2 and self.profile is None:
            can = False
        if idx == 3 and self.mode is None:
            can = False
        if idx == 4:
            if self.mode == "offline":
                can = bool(self.choices.get("model_opt"))
            elif self.mode == "online":
                can = bool(self.choices.get("cloud_api_key"))
            elif self.mode == "dual":
                can = bool(self.choices.get("model_opt") and self.choices.get("cloud_api_key"))
        self.next_btn.setEnabled(can)
        self._t(self.next_btn, "finish" if idx == 6 else "next")

    # ---- Finish ----

    def _finish(self):
        cfg = guya_config.load_config()
        if self.mode == "online":
            cfg["model"]["backend"] = "cloud"
            cfg["model"]["size"] = "large-v3"
            cfg["model"]["device"] = "cloud"
            cfg["cloud"]["provider"] = "groq"
            cfg["cloud"]["api_key"] = self.choices.get("cloud_api_key", "")
            cfg["cloud"]["enabled"] = False
            cfg["language"] = self.choices["language"]
            need_model = None
        else:
            opt = self.choices["model_opt"]
            cfg["model"]["backend"] = "faster-whisper"
            cfg["model"]["size"] = opt["model_size"]
            cfg["model"]["device"] = opt["device"]
            cfg["model"]["compute_type"] = "auto"
            need_model = opt["model_size"]
            if self.mode == "dual":
                cfg["cloud"]["provider"] = "groq"
                cfg["cloud"]["api_key"] = self.choices.get("cloud_api_key", "")
                cfg["cloud"]["enabled"] = True
                # The offline half keeps the language the user chose. It used to
                # be forced to English, which silently contradicted the Review
                # page and left a Persian-only user with an English-only offline model.
                chosen = self.choices.get("language")
                cfg["language"] = chosen if chosen in ("fa", "en") else "en"
            else:
                cfg["cloud"]["enabled"] = False
                cfg["language"] = self.choices["language"]
        cfg["hotkey"]["vk"] = self.choices["hotkey_vk"]
        cfg["hotkey"]["label"] = self.choices["hotkey_label"]
        cfg["hotkey"]["name"] = self.choices["hotkey_label"]
        assistant_vk, assistant_label = self._assistant_key_choice()
        if not IS_MAC:
            cfg["assistant"]["hotkey"]["vk"] = assistant_vk
            cfg["assistant"]["hotkey"]["label"] = assistant_label
            cfg["assistant"]["hotkey"]["name"] = assistant_label
        cfg["ui"]["style"] = self.choices["ui_style"]

        if self.bench_proc and self.bench_proc.state() != QProcess.ProcessState.NotRunning:
            self.bench_proc.kill()
        if not guya_config.save_config(cfg):
            return
        launcher_gen.create_launcher()

        if need_model is None or model_is_cached(need_model):
            self._show_done(); return
        self.stack.setCurrentIndex(7); self._sync_step(); self._update_nav()
        self._start_download(need_model)

    def _set_dl_state(self, key, color):
        self.dl_state.setStyleSheet(f"color: {color};")
        self.dl_state.setText(f"●  {self.tr(key)}")

    def _start_download(self, size):
        self.dl_title.setText(self.tr("dl_title", m=size))
        self.dl_status.setText(self.tr("dl_wait"))
        self.dl_expected = MODEL_SIZE_MB.get(size, 1000); self.dl_size = size
        self.dl_paused = False; self._t(self.dl_pause_btn, "dl_pause")
        self.dl_pause_btn.setEnabled(True); self.dl_bar.setValue(0)
        self._spawn_download()

    def _spawn_download(self):
        self._set_dl_state("dl_connecting", ACCENT)
        self.dl_proc = QProcess(self)
        self.dl_proc.finished.connect(self._on_download_done)
        self.dl_proc.setProgram(sys.executable)
        self.dl_proc.setArguments([
            "-c", "from faster_whisper.utils import download_model; "
                  f"download_model('{self.dl_size}')"])
        env = QProcessEnvironment.systemEnvironment()
        env.insert("HF_HUB_DISABLE_XET", "1"); env.insert("HF_HUB_ENABLE_HF_TRANSFER", "0")
        self.dl_proc.setProcessEnvironment(env)
        self.dl_proc.start()
        if self.dl_timer is None:
            self.dl_timer = QTimer(self); self.dl_timer.timeout.connect(self._poll_download)
        self.dl_timer.start(500)

    def _poll_download(self):
        mb = model_downloaded_mb(self.dl_size)
        pct = int(min(99, (mb / self.dl_expected) * 100)) if self.dl_expected else 0
        self.dl_bar.setValue(pct)
        self.dl_status.setText(self.tr("dl_of", a=f"{mb:.0f}", b=f"{self.dl_expected:.0f}"))
        if mb > 1:
            self._set_dl_state("dl_downloading", GREEN)

    def _toggle_pause(self):
        if self.dl_paused:
            self.dl_paused = False; self._t(self.dl_pause_btn, "dl_pause"); self._spawn_download()
        else:
            self.dl_paused = True
            if self.dl_timer:
                self.dl_timer.stop()
            if self.dl_proc and self.dl_proc.state() != QProcess.ProcessState.NotRunning:
                self.dl_proc.kill()
            self._set_dl_state("dl_paused", TEXT2); self._t(self.dl_pause_btn, "dl_resume")

    def _on_download_done(self, code, _s):
        if self.dl_paused:
            return
        if self.dl_timer:
            self.dl_timer.stop()
        if model_is_cached(self.dl_size):
            self.dl_bar.setValue(100); self._set_dl_state("dl_done", GREEN)
            self.dl_status.setText(self.tr("dl_done")); self._show_done()
        else:
            self._set_dl_state("dl_error", RED); self._t(self.dl_pause_btn, "dl_retry")
            self.dl_paused = True

    def _complete(self):
        self.completed = True
        log.info("Setup complete; config saved.")
        self.close()


class HotkeyCapture(QPushButton):
    captured = pyqtSignal(int, str)

    def __init__(self, label, parent=None):
        super().__init__(label, parent)
        self._capturing = False
        self.clicked.connect(self._start)
        self.setMinimumHeight(40)

    def _start(self):
        self._capturing = True; self.setText("…"); self.grabKeyboard()

    def keyPressEvent(self, e):
        if self._capturing:
            qt_key = e.key()
            vk = qt_key
            if IS_WIN:
                f1 = Qt.Key.Key_F1.value
                f24 = Qt.Key.Key_F24.value
                if f1 <= qt_key <= f24:
                    vk = 0x70 + (qt_key - f1)
                else:
                    special = {
                        Qt.Key.Key_Backspace.value: 0x08,
                        Qt.Key.Key_Tab.value: 0x09,
                        Qt.Key.Key_Return.value: 0x0D,
                        Qt.Key.Key_Enter.value: 0x0D,
                        Qt.Key.Key_Escape.value: 0x1B,
                        Qt.Key.Key_Space.value: 0x20,
                        Qt.Key.Key_PageUp.value: 0x21,
                        Qt.Key.Key_PageDown.value: 0x22,
                        Qt.Key.Key_End.value: 0x23,
                        Qt.Key.Key_Home.value: 0x24,
                        Qt.Key.Key_Left.value: 0x25,
                        Qt.Key.Key_Up.value: 0x26,
                        Qt.Key.Key_Right.value: 0x27,
                        Qt.Key.Key_Down.value: 0x28,
                        Qt.Key.Key_Insert.value: 0x2D,
                        Qt.Key.Key_Delete.value: 0x2E,
                    }
                    vk = special.get(qt_key, qt_key)
            label = (
                QKeySequence(qt_key).toString()
                or e.text().upper().strip()
                or str(vk)
            )
            self._capturing = False; self.releaseKeyboard()
            self.setText(f"{label}"); self.captured.emit(vk, label)
        else:
            super().keyPressEvent(e)
