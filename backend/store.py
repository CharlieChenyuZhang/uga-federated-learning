"""Local SQLite storage. Every private record belongs to exactly one institution."""

import hashlib
import json
import os
import secrets
import sqlite3
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(os.environ.get("CAMPUS_DATA_DIR", ROOT / ".local"))
SCHOOLS = [
    {
        "id": "uga",
        "name": "University of Georgia",
        "short": "UG",
        "city": "Athens, Georgia",
        "color": "red",
        "focus": "Science argumentation",
    },
    {
        "id": "gatech",
        "name": "Georgia Tech",
        "short": "GT",
        "city": "Atlanta, Georgia",
        "color": "gold",
        "focus": "Engineering inquiry",
    },
    {
        "id": "emory",
        "name": "Emory University",
        "short": "EU",
        "city": "Atlanta, Georgia",
        "color": "blue",
        "focus": "Evidence & reasoning",
    },
]
ACCOUNTS = {
    "uga": ("UGA Researcher", "contributor", "uga"),
    "gatech": ("Georgia Tech Researcher", "contributor", "gatech"),
    "emory": ("Emory Researcher", "contributor", "emory"),
    "user": ("Research Guest", "user", None),
}


def connect():
    DATA.mkdir(parents=True, exist_ok=True, mode=0o700)
    db = sqlite3.connect(DATA / "campus.db", timeout=30)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA foreign_keys=ON")
    return db


def password_hash(password, salt):
    return hashlib.scrypt(
        password.encode(), salt=salt.encode(), n=16384, r=8, p=1
    ).hex()


def initialize():
    with connect() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS users (id TEXT PRIMARY KEY, name TEXT NOT NULL, role TEXT NOT NULL, school_id TEXT, salt TEXT NOT NULL, password TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sessions (token TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), expires REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS datasets (id TEXT PRIMARY KEY, school_id TEXT NOT NULL, name TEXT NOT NULL, rows TEXT NOT NULL, row_count INTEGER NOT NULL, created REAL NOT NULL, synthetic INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, school_id TEXT NOT NULL, dataset_id TEXT NOT NULL REFERENCES datasets(id), name TEXT NOT NULL, status TEXT NOT NULL, steps INTEGER NOT NULL, step INTEGER NOT NULL DEFAULT 0, phase TEXT NOT NULL, history TEXT NOT NULL DEFAULT '[]', metrics TEXT, error TEXT, shared INTEGER NOT NULL DEFAULT 0, created REAL NOT NULL, finished REAL);
        CREATE INDEX IF NOT EXISTS idx_datasets_school ON datasets(school_id);
        CREATE INDEX IF NOT EXISTS idx_runs_school ON runs(school_id);
        CREATE INDEX IF NOT EXISTS idx_sessions_expiry ON sessions(expires);
        """)
        for uid, (name, role, school) in ACCOUNTS.items():
            if not db.execute("SELECT 1 FROM users WHERE id=?", (uid,)).fetchone():
                salt = secrets.token_hex(16)
                db.execute(
                    "INSERT INTO users VALUES (?,?,?,?,?,?)",
                    (
                        uid,
                        name,
                        role,
                        school,
                        salt,
                        password_hash(
                            os.environ.get("CAMPUS_DEMO_PASSWORD", "local-lab"), salt
                        ),
                    ),
                )
        db.execute("DELETE FROM sessions WHERE expires < ?", (time.time(),))
        db.execute(
            "UPDATE runs SET status='failed',phase='Interrupted',error='The local worker stopped before this run finished. Start a new run.',finished=? WHERE status IN ('queued','running')",
            (time.time(),),
        )


def rows(sql, args=()):
    with connect() as db:
        return [dict(row) for row in db.execute(sql, args).fetchall()]


def one(sql, args=()):
    found = rows(sql, args)
    return found[0] if found else None


def execute(sql, args=()):
    with connect() as db:
        db.execute(sql, args)


def update_run(run_id, **values):
    allowed = {
        "status",
        "step",
        "phase",
        "history",
        "metrics",
        "error",
        "shared",
        "finished",
    }
    if not values or not set(values) <= allowed:
        raise ValueError("Invalid run update")
    cooked = {
        k: json.dumps(v, allow_nan=False) if k in {"history", "metrics"} else v
        for k, v in values.items()
    }
    execute(
        f"UPDATE runs SET {','.join(k + '=?' for k in cooked)} WHERE id=?",
        (*cooked.values(), run_id),
    )


def public_run(row, private=False):
    result = {
        k: row[k]
        for k in [
            "id",
            "school_id",
            "name",
            "status",
            "steps",
            "step",
            "phase",
            "shared",
            "created",
            "finished",
        ]
    }
    if private:
        result.update(
            dataset_id=row["dataset_id"],
            error=row["error"],
            history=json.loads(row["history"]),
        )
        result["metrics"] = json.loads(row["metrics"]) if row["metrics"] else None
    elif row["shared"] and row["metrics"]:
        # A shared model exposes numeric evaluation only, never held-out prompts or targets.
        metrics = json.loads(row["metrics"])
        result["metrics"] = {k: v for k, v in metrics.items() if k != "samples"}
    return result
