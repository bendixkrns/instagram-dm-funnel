"""Validated settings for Instagram keyword resource funnels."""
import re
from urllib.parse import urlsplit

from kanal import KANAL, lies, schreib

FILE = KANAL / "keyword_funnels.json"
MODES = {"adaptive", "follow", "email", "both"}
ORDERS = {"follow_first", "email_first"}
DEFAULT = {
    "mode": "adaptive",
    "order": "follow_first",
    "intro_text": "Thanks for commenting! 👏\nTap on the button and I will send you the link 🔥\nOn desktop? Reply SEND LINK.",
    "follow_text": "Sorry, this resource is only for my followers. Follow me, then tap I followed ✅ or reply I followed ✅ here, and I'll send you the link 🤝",
    "follow_again_text": "You're not following me yet.",
    "email_text": "Sorry, I need your email address for this resource. Reply with your email here, and I'll send you the link. 📩",
    "email_again_text": "Please reply with a valid email address.",
    "link_text": "Thanks! Here is your link: {link}",
    "start_button": "Send link",
    "follow_button": "I followed ✅",
    "follow_now_button": "Follow Now",
    "public_replies": ["Sent you a message. Check your DMs 📩", "Just sent it over. Check your DMs",
                       "It's in your DMs now 📩", "Sent! Take a look in your DMs",
                       "Your message is on its way 📩", "Check your DMs — it's there"],
}
TEXT_FIELDS = {"intro_text", "follow_text", "follow_again_text", "email_text", "email_again_text", "link_text"}
BUTTON_FIELDS = {"start_button", "follow_button", "follow_now_button"}


def load():
    data = lies(FILE, {}) or {}
    return {"default": {**DEFAULT, **(data.get("default") or {})}, "reels": data.get("reels") or {}}


def for_reel(reel_id):
    data = load()
    override = data["reels"].get(reel_id) or {}
    return {**data["default"], **override}


def _url(value):
    parsed = urlsplit(value)
    return parsed.scheme == "https" and bool(parsed.netloc) and not parsed.username and not parsed.password


def validate(settings, *, reel=False):
    if not isinstance(settings, dict):
        raise ValueError("Einstellungen müssen ein Objekt sein")
    allowed = {"mode", "order", "keywords", "link", *TEXT_FIELDS, *BUTTON_FIELDS, "public_replies"}
    if reel:
        allowed |= {"active", "keyword", "profile_link"}
    extra = set(settings) - allowed
    if extra:
        raise ValueError("Unbekannte Felder: " + ", ".join(sorted(extra)))
    result = {}
    for key, value in settings.items():
        if value is None and key in {"link", "keywords"} and not reel:
            result[key] = None                         # Standard-Wert entfernen
            continue
        if key == "mode":
            if value not in MODES:
                raise ValueError("Modus muss adaptive, follow, email oder both sein")
        elif key == "order":
            if value not in ORDERS:
                raise ValueError("Reihenfolge muss follow_first oder email_first sein")
        elif key == "active":
            if not isinstance(value, bool):
                raise ValueError("active muss wahr oder falsch sein")
        elif key == "keyword":
            if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9]{3,32}", value):
                raise ValueError("Keyword: 3–32 Buchstaben oder Ziffern")
            value = value.upper()
        elif key == "keywords":
            if not isinstance(value, list) or not (1 <= len(value) <= 10) or any(
                    not isinstance(item, str) or not re.fullmatch(r"[A-Za-z0-9]{3,32}", item) for item in value):
                raise ValueError("Keywords: 1–10 Einträge mit je 3–32 Buchstaben oder Ziffern")
            value = list(dict.fromkeys(item.upper() for item in value))
        elif key in {"link", "profile_link"}:
            if not isinstance(value, str) or not _url(value):
                raise ValueError(key + " muss eine HTTPS-URL sein")
        elif key in TEXT_FIELDS:
            if not isinstance(value, str) or not value.strip() or len(value) > 900:
                raise ValueError(key + ": Text muss 1–900 Zeichen enthalten")
            if key == "link_text" and "{link}" not in value:
                raise ValueError("Link-Nachricht muss {link} enthalten")
        elif key in BUTTON_FIELDS:
            if not isinstance(value, str) or not (1 <= len(value) <= 20):
                raise ValueError(key + ": Buttontext muss 1–20 Zeichen enthalten")
        elif key == "public_replies":
            if not isinstance(value, list) or not (1 <= len(value) <= 8) or any(
                    not isinstance(item, str) or not item.strip() or len(item) > 180 for item in value):
                raise ValueError("1–8 öffentliche Antworten mit höchstens 180 Zeichen nötig")
        result[key] = value
    return result


def save_default(settings):
    validated = validate(settings)
    data = load()
    data["default"] = {k: v for k, v in {**data["default"], **validated}.items() if v is not None}
    schreib(FILE, data)
    return data["default"]


def save_reel(reel_id, settings):
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,120}", reel_id):
        raise ValueError("Ungültige Reel-ID")
    validated = validate(settings, reel=True)
    data = load()
    data["reels"][reel_id] = validated
    schreib(FILE, data)
    return for_reel(reel_id)


def reset_reel(reel_id):
    data = load()
    data["reels"].pop(reel_id, None)
    schreib(FILE, data)
    return for_reel(reel_id)
