"""Private, Instagram-scoped email addresses for requested resource flows.

An address saved here is not a newsletter subscription or marketing consent.
"""
import datetime
import re
import sqlite3
from contextlib import closing

from kanal import ROOT

DB = ROOT / ".secrets" / "automation" / "instagram_contacts.sqlite3"
EMAIL = re.compile(r"^[A-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?(?:\.[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?)+$", re.I)


def normalize_email(value):
    address = (value or "").strip()
    if len(address) > 254 or not EMAIL.fullmatch(address):
        return None
    return address.lower()


def _connect():
    DB.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB, timeout=10)
    db.execute("CREATE TABLE IF NOT EXISTS contacts (business TEXT NOT NULL, user_id TEXT NOT NULL, "
               "email TEXT NOT NULL, saved_at TEXT NOT NULL, PRIMARY KEY (business, user_id))")
    return db


def email_for(business, user_id):
    if not DB.exists():
        return None
    with closing(_connect()) as db:
        row = db.execute("SELECT email FROM contacts WHERE business = ? AND user_id = ?",
                         (str(business), str(user_id))).fetchone()
    return row[0] if row else None


def save_email(business, user_id, value):
    address = normalize_email(value)
    if not address:
        raise ValueError("Ungültige E-Mail-Adresse")
    with closing(_connect()) as db:
        with db:
            db.execute("INSERT INTO contacts (business, user_id, email, saved_at) VALUES (?, ?, ?, ?) "
                       "ON CONFLICT(business, user_id) DO UPDATE SET email=excluded.email, saved_at=excluded.saved_at",
                       (str(business), str(user_id), address, datetime.datetime.now(datetime.timezone.utc).isoformat()))
    return address


def delete_email(business, user_id):
    if not DB.exists():
        return
    with closing(_connect()) as db:
        with db:
            db.execute("DELETE FROM contacts WHERE business = ? AND user_id = ?", (str(business), str(user_id)))
