"""Run one background job on Windows or Linux.

Usage: python -X utf8 tools/automation/run.py <job> [--modus probelauf] [--trocken] [--backend groq|claude]
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from kanal import kanal  # noqa: E402

STATE = ROOT / ".secrets" / "automation"
JOBS = {"kommentare", "dms", "keyword_dm", "kennzahlen", "warteschlange"}


def commands(job, mode, dry):
    active = set(((kanal().get("plattformen") or {}).get("aktiv") or []))
    if job == "kommentare":
        flags = ["--modus", mode] + (["--trocken"] if dry else [])
        result = []
        if "instagram" in active:
            result.append(["tools/instagram/kommentare.py", "--alle", *flags])
        if active & {"youtube", "tiktok"}:
            result.append(["tools/kommentare_zernio.py", "--alle", *flags])
        return result
    if job == "keyword_dm":
        return [["tools/instagram/kommentare.py", "--alle", "--nur-keyword", "--modus", mode,
                 *(["--trocken"] if dry else [])]] if "instagram" in active else []
    if job == "dms":
        return [["tools/instagram/dms.py", "--alle", *(["--trocken"] if dry else [])]] if "instagram" in active else []
    if job == "kennzahlen":
        result = []
        if "instagram" in active:
            result.append(["tools/instagram/kennzahlen.py", "--alle", *(["--trocken"] if dry else [])])
        if not dry:
            if "youtube" in active:
                result.append(["tools/youtube/youtube.py", "kennzahlen"])
            if "tiktok" in active:
                result.append(["tools/tiktok/tiktok.py", "kennzahlen"])
        return result
    return [["tools/instagram/warteschlange.py", *(["--trocken"] if dry else [])]]


def run(job, mode, dry, backend):
    lock = STATE / ("kommentare.lock" if job in {"kommentare", "keyword_dm"} else f"{job}.lock")
    if not dry:
        STATE.mkdir(parents=True, exist_ok=True)
        if lock.exists() and datetime.datetime.now().timestamp() - lock.stat().st_mtime > 3600:
            lock.unlink(missing_ok=True)
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            print(f"{job}: läuft bereits ({lock.name})", file=sys.stderr)
            return 2
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(json.dumps({"pid": os.getpid(), "start": datetime.datetime.now().isoformat()}))
    try:
        env = os.environ.copy()
        env["BOT_LLM_BACKEND"] = backend
        failures = []
        for command in commands(job, mode, dry):
            proc = subprocess.run([sys.executable, "-X", "utf8", *command], cwd=ROOT, env=env,
                                  capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900)
            output = ((proc.stdout or "") + (proc.stderr or "")).strip()
            if output:
                print(output)
            if proc.returncode:
                failures.append(f"{command[0]}: Exit {proc.returncode}")
        code = 1 if failures else 0
        if not dry:
            with (STATE / "jobs.log").open("a", encoding="utf-8") as log:
                log.write(f"{datetime.datetime.now().isoformat(timespec='seconds')} {job} exit={code} {', '.join(failures)}\n")
        return code
    except subprocess.TimeoutExpired as exc:
        print(f"{job}: Zeitüberschreitung ({exc.cmd})", file=sys.stderr)
        if not dry:
            with (STATE / "jobs.log").open("a", encoding="utf-8") as log:
                log.write(f"{datetime.datetime.now().isoformat(timespec='seconds')} {job} exit=1 timeout\n")
        return 1
    finally:
        if not dry:
            lock.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("job", choices=sorted(JOBS))
    parser.add_argument("--modus", choices=["aus", "probelauf", "live"])
    parser.add_argument("--trocken", action="store_true")
    parser.add_argument("--backend", choices=["groq", "claude"], default=os.environ.get("BOT_LLM_BACKEND", "groq"))
    args = parser.parse_args()
    mode = args.modus or (kanal().get("kommentar_bot") or {}).get("modus", "aus")
    return run(args.job, mode, args.trocken, args.backend)


if __name__ == "__main__":
    raise SystemExit(main())
