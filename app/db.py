"""طبقة قاعدة البيانات (SQLite)."""
import sqlite3
from pathlib import Path

from flask import current_app, g

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schema.sql"


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DB"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys=ON")
    return g.db


def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def query(sql, args=(), one=False):
    rows = get_db().execute(sql, args).fetchall()
    if one:
        return rows[0] if rows else None
    return rows


def execute(sql, args=()):
    conn = get_db()
    cur = conn.execute(sql, args)
    conn.commit()
    return cur.lastrowid


def init_db(path):
    """ينشئ الجداول من schema.sql ويضيف الأعمدة الجديدة للقواعد القديمة."""
    conn = sqlite3.connect(path)
    try:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        cols = {row[1] for row in conn.execute("PRAGMA table_info(crops)")}
        if "harvest_days" not in cols:
            conn.execute("ALTER TABLE crops ADD COLUMN harvest_days INTEGER")
        conn.commit()
    finally:
        conn.close()
