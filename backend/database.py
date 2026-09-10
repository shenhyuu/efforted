from __future__ import annotations

import os
import sqlite3
from contextlib import closing
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = Path(os.getenv("ZHIHEN_DB_PATH", BASE_DIR / "data" / "zhihen.db"))


def connect() -> sqlite3.Connection:
    connection = sqlite3.connect(DATABASE_PATH, timeout=5)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    return connection


def initialize_database() -> None:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with closing(connect()) as connection:
        connection.execute("PRAGMA journal_mode = WAL")
        existing = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='records'"
        ).fetchone()
        if existing:
            columns = {row["name"] for row in connection.execute("PRAGMA table_info(records)")}
            if "user_id" not in columns:
                connection.execute("ALTER TABLE records RENAME TO records_legacy_v01")

        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL DEFAULT 'me',
                password_hash TEXT NOT NULL,
                password_salt TEXT NOT NULL,
                created_at TEXT NOT NULL,
                last_seen_at TEXT
            );

            CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                client_uuid TEXT,
                kind TEXT NOT NULL CHECK (kind IN ('checkin', 'backfill', 'timer_close')),
                occurred_at TEXT,
                time_scope TEXT NOT NULL CHECK (time_scope IN ('exact', 'past')),
                day_slot TEXT CHECK (day_slot IN ('morning','afternoon','evening','night') OR day_slot IS NULL),
                energy TEXT CHECK (energy IN ('low','mid','enough') OR energy IS NULL),
                content TEXT,
                duration_seconds INTEGER,
                timer_id INTEGER,
                created_at TEXT NOT NULL,
                ash INTEGER NOT NULL DEFAULT 0,
                CHECK ((time_scope='exact' AND occurred_at IS NOT NULL) OR
                       (time_scope='past' AND occurred_at IS NULL)),
                UNIQUE(user_id, client_uuid)
            );
            CREATE INDEX IF NOT EXISTS idx_records_time ON records(user_id, time_scope, occurred_at);

            CREATE TABLE IF NOT EXISTS timers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                status TEXT NOT NULL CHECK (status IN ('running','paused','closed')),
                accumulated_seconds INTEGER NOT NULL DEFAULT 0,
                last_resumed_at TEXT,
                created_at TEXT NOT NULL,
                closed_at TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_timers_user ON timers(user_id, status);

            CREATE TABLE IF NOT EXISTS timer_segments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timer_id INTEGER NOT NULL REFERENCES timers(id) ON DELETE CASCADE,
                started_at TEXT NOT NULL,
                ended_at TEXT
            );

            CREATE TABLE IF NOT EXISTS lamps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                message TEXT NOT NULL,
                energy_at_write TEXT CHECK (energy_at_write IN ('low','mid','enough') OR energy_at_write IS NULL),
                created_at TEXT NOT NULL,
                opened_at TEXT
            );

            CREATE TABLE IF NOT EXISTS user_settings (
                user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                low_energy_mode INTEGER NOT NULL DEFAULT 0,
                hide_all_numbers INTEGER NOT NULL DEFAULT 0,
                nothing_mode INTEGER NOT NULL DEFAULT 0,
                privacy_mode INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS purge_requests (
                user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                requested_at TEXT NOT NULL,
                execute_at TEXT NOT NULL
            );
            """
        )
        connection.commit()
