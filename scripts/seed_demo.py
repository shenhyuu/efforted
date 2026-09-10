"""Create a representative, disposable database for visual acceptance testing."""

from __future__ import annotations

import argparse
import sys
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import database  # noqa: E402
from security import hash_password, iso, utc_now  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database",
        type=Path,
        default=ROOT / "backend" / "data" / "demo.db",
        help="Output database. Defaults to backend/data/demo.db; the live database is never selected implicitly.",
    )
    parser.add_argument("--password", default="demo-only", help="Demo login password (minimum 6 characters).")
    parser.add_argument("--force", action="store_true", help="Replace an existing output database.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    target = args.database.resolve()
    live = (ROOT / "backend" / "data" / "zhihen.db").resolve()
    if len(args.password) < 6:
        raise SystemExit("--password must contain at least 6 characters")
    if target == live:
        raise SystemExit("Refusing to replace the default live database; choose a separate --database path.")
    if target.exists():
        if not args.force:
            raise SystemExit(f"{target} already exists; pass --force to replace this disposable database.")
        target.unlink()
    for suffix in ("-wal", "-shm"):
        sidecar = Path(f"{target}{suffix}")
        if sidecar.exists():
            sidecar.unlink()

    database.DATABASE_PATH = target
    database.initialize_database()
    password_hash, salt = hash_password(args.password)
    now = utc_now()
    energies = ("low", "mid", "enough", None)
    notes = ("打开了文档", "晒了一会儿太阳", "把水杯接满", None)
    units = ("读一页", "走到门口", "写一句", None)
    with database.connect() as connection:
        cursor = connection.execute(
            """INSERT INTO users(username,password_hash,password_salt,created_at,last_seen_at)
               VALUES('me',?,?,?,?)""",
            (password_hash, salt, iso(now - timedelta(days=70)), iso(now)),
        )
        user_id = int(cursor.lastrowid)
        connection.execute(
            "INSERT INTO user_settings(user_id,updated_at) VALUES(?,?)", (user_id, iso(now))
        )
        for index, days_ago in enumerate((0, 0, 1, 2, 4, 7, 11, 18, 29, 45, 63)):
            occurred = now - timedelta(days=days_ago, hours=index % 7)
            connection.execute(
                """INSERT INTO records
                   (user_id,kind,occurred_at,time_scope,day_slot,energy,content,effort_unit,created_at)
                   VALUES(?,'checkin',?,'exact',?,?,?,?,?)""",
                (
                    user_id,
                    iso(occurred),
                    ("morning", "afternoon", "evening", "night")[index % 4],
                    energies[index % len(energies)],
                    notes[index % len(notes)],
                    units[index % len(units)],
                    iso(occurred),
                ),
            )
        connection.execute(
            """INSERT INTO records
               (user_id,kind,occurred_at,time_scope,energy,content,effort_unit,created_at)
               VALUES(?,'backfill',NULL,'past','mid','想起曾经也有慢慢走过','做了一点',?)""",
            (user_id, iso(now - timedelta(days=5))),
        )
        connection.execute(
            """INSERT INTO records
               (user_id,kind,occurred_at,time_scope,energy,duration_seconds,created_at)
               VALUES(?,'timer_close',?,'exact','enough',840,?)""",
            (user_id, iso(now - timedelta(days=3)), iso(now - timedelta(days=3))),
        )
        connection.execute(
            "INSERT INTO lamps(user_id,message,energy_at_write,created_at) VALUES(?,?,?,?)",
            (user_id, "你已经走过一些路了。", "low", iso(now - timedelta(days=20))),
        )
        connection.commit()
    print(f"Created demo database: {target}")
    print(f"Login password: {args.password}")


if __name__ == "__main__":
    main()
