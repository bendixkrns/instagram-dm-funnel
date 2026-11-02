"""Per-job status for the cockpit. No credentials or message bodies are stored here."""
from pathlib import Path
import os
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kanal import KANAL, jetzt, lies, schreib  # noqa: E402

FILE = KANAL / "bot_status.json"


def record(job, account, ok, error="", *, dry=False):
    if dry:
        return
    lock = FILE.with_suffix(".lock")
    for _ in range(100):
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(fd)
            break
        except FileExistsError:
            if lock.exists() and time.time() - lock.stat().st_mtime > 60:
                lock.unlink(missing_ok=True)
            time.sleep(0.05)
    else:
        raise RuntimeError("Bot-Statusdatei ist gesperrt")
    try:
        data = lies(FILE, {}) or {}
        key = f"{job}:{account}"
        previous = data.get(key, {})
        data[key] = {
            "ok": bool(ok), "stand": jetzt(), "letzter_erfolg": jetzt() if ok else previous.get("letzter_erfolg"),
            "fehler": "" if ok else str(error)[:300],
        }
        schreib(FILE, data)
    finally:
        lock.unlink(missing_ok=True)
