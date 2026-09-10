from __future__ import annotations

import asyncio
import json
import sqlite3
from contextlib import asynccontextmanager, closing
from datetime import date, datetime, time, timedelta, timezone
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import database
from database import connect, initialize_database
from schemas import (
    BackfillCreate, BatchCheckinCreate, CheckinCreate, ExportInput, LampCreate,
    PasswordInput, PurgeInput, RecordUpdate, SettingsUpdate,
)
from security import create_token, hash_password, iso, parse_iso, token_digest, utc_now, verify_password

UserId = Annotated[int, Depends(lambda: None)]


def friendly(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


def row_record(row: sqlite3.Row) -> dict[str, object]:
    scope = row["time_scope"]
    return {
        "id": row["id"], "occurred_at": row["occurred_at"], "time_scope": scope,
        "time_label": "过去" if scope == "past" else None, "day_slot": row["day_slot"],
        "energy": row["energy"], "content": row["content"],
        "effort_unit": row["effort_unit"],
        "duration_seconds": row["duration_seconds"], "ash": bool(row["ash"]),
        "created_at": row["created_at"],
    }


def issue_session(connection: sqlite3.Connection, user_id: int) -> dict[str, str]:
    token, digest, expires_at = create_token()
    connection.execute(
        "INSERT INTO sessions(token_hash,user_id,expires_at,created_at) VALUES(?,?,?,?)",
        (digest, user_id, expires_at, iso()),
    )
    return {"token": token, "expires_at": expires_at}


def execute_due_purge(connection: sqlite3.Connection, user_id: int) -> bool:
    pending = connection.execute(
        "SELECT execute_at FROM purge_requests WHERE user_id=?", (user_id,)
    ).fetchone()
    if not pending or parse_iso(pending["execute_at"]) > utc_now():
        return False
    for table in ("timer_segments", "timers", "lamps", "records"):
        if table == "timer_segments":
            connection.execute(
                "DELETE FROM timer_segments WHERE timer_id IN (SELECT id FROM timers WHERE user_id=?)",
                (user_id,),
            )
        else:
            connection.execute(f"DELETE FROM {table} WHERE user_id=?", (user_id,))
    connection.execute(
        """UPDATE user_settings SET low_energy_mode=0,auto_low_energy_mode=0,
           hide_all_numbers=0,nothing_mode=0,notify_enabled=0,
           weekly_report_opt_out=0,privacy_mode=0,updated_at=? WHERE user_id=?""",
        (iso(), user_id),
    )
    connection.execute("DELETE FROM purge_requests WHERE user_id=?", (user_id,))
    connection.commit()
    return True


def execute_all_due_purges() -> int:
    """Physically remove data whose grace period elapsed, even without a user request."""
    with closing(connect()) as connection:
        user_ids = [
            int(row["user_id"])
            for row in connection.execute(
                "SELECT user_id FROM purge_requests WHERE execute_at<=?", (iso(),)
            ).fetchall()
        ]
        return sum(execute_due_purge(connection, user_id) for user_id in user_ids)


async def purge_worker(stop: asyncio.Event) -> None:
    while not stop.is_set():
        try:
            await asyncio.to_thread(execute_all_due_purges)
        except sqlite3.Error:
            # A transient database lock must not permanently stop expiry processing.
            pass
        try:
            await asyncio.wait_for(stop.wait(), timeout=30)
        except TimeoutError:
            pass


def current_user(authorization: Annotated[str | None, Header()] = None) -> int:
    if not authorization or not authorization.startswith("Bearer "):
        raise friendly(401, "UNAUTHORIZED", "这次访问需要先确认是你。")
    digest = token_digest(authorization[7:])
    with closing(connect()) as connection:
        session = connection.execute(
            "SELECT user_id,expires_at FROM sessions WHERE token_hash=?", (digest,)
        ).fetchone()
        if not session:
            raise friendly(401, "UNAUTHORIZED", "这次访问已经安静地结束了，可以重新进入。")
        if parse_iso(session["expires_at"]) <= utc_now():
            connection.execute("DELETE FROM sessions WHERE token_hash=?", (digest,))
            connection.commit()
            raise friendly(401, "UNAUTHORIZED", "这次访问已经安静地结束了，可以重新进入。")
        execute_due_purge(connection, session["user_id"])
        return int(session["user_id"])


AuthUser = Annotated[int, Depends(current_user)]


def insert_record(
    connection: sqlite3.Connection, user_id: int, *, kind: str, occurred_at: str | None,
    time_scope: str, energy: str | None, content: str | None, day_slot: str | None = None,
    client_uuid: str | None = None, duration_seconds: int | None = None,
    timer_id: int | None = None, effort_unit: str | None = None,
) -> tuple[dict[str, object], bool]:
    if client_uuid:
        existing = connection.execute(
            "SELECT * FROM records WHERE user_id=? AND client_uuid=?", (user_id, client_uuid)
        ).fetchone()
        if existing:
            return row_record(existing), False
    cursor = connection.execute(
        """INSERT INTO records
           (user_id,client_uuid,kind,occurred_at,time_scope,day_slot,energy,content,
            effort_unit,duration_seconds,timer_id,created_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
        (user_id, client_uuid, kind, occurred_at, time_scope, day_slot, energy,
         content or None, effort_unit or None, duration_seconds, timer_id, iso()),
    )
    row = connection.execute("SELECT * FROM records WHERE id=?", (cursor.lastrowid,)).fetchone()
    if row is None:
        raise RuntimeError("record insert did not return a row")
    return row_record(row), True


def timer_payload(row: sqlite3.Row) -> dict[str, object]:
    accumulated = int(row["accumulated_seconds"])
    elapsed = accumulated
    if row["status"] == "running" and row["last_resumed_at"]:
        elapsed += max(0, int((utc_now() - parse_iso(row["last_resumed_at"])).total_seconds()))
    return {
        "id": row["id"], "status": row["status"], "accumulated_seconds": accumulated,
        "elapsed_seconds": elapsed, "created_at": row["created_at"], "closed_at": row["closed_at"],
    }


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database()
    stop = asyncio.Event()
    task = asyncio.create_task(purge_worker(stop))
    try:
        yield
    finally:
        stop.set()
        await task


app = FastAPI(title="织痕 API", description="记录出现过的时刻，不评价它们。", version="1.2.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=False, allow_methods=["GET", "POST", "PATCH", "DELETE"], allow_headers=["*"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(self), geolocation=()"
    if request.url.scheme == "https":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


@app.get("/")
async def root() -> dict[str, str]:
    return {"name": "织痕", "version": app.version, "docs": "/docs"}


@app.get("/health")
@app.get("/api/v1/health")
async def health() -> dict[str, str]:
    try:
        with closing(connect()) as connection:
            connection.execute("SELECT 1").fetchone()
    except sqlite3.Error as error:
        raise friendly(503, "DATABASE_UNAVAILABLE", "数据存储暂时没有回应。") from error
    return {"status": "ok"}


@app.get("/api/v1/auth/status")
async def auth_status() -> dict[str, bool]:
    with closing(connect()) as connection:
        return {"initialized": connection.execute("SELECT 1 FROM users LIMIT 1").fetchone() is not None}


@app.post("/api/v1/auth/setup", status_code=201)
async def setup(payload: PasswordInput) -> dict[str, str]:
    with closing(connect()) as connection:
        if connection.execute("SELECT 1 FROM users LIMIT 1").fetchone():
            raise friendly(409, "ALREADY_SETUP", "这里已经有一把钥匙了。")
        password_hash, salt = hash_password(payload.password)
        cursor = connection.execute(
            "INSERT INTO users(username,password_hash,password_salt,created_at) VALUES('me',?,?,?)",
            (password_hash, salt, iso()),
        )
        user_id = int(cursor.lastrowid)
        connection.execute(
            "INSERT INTO user_settings(user_id,updated_at) VALUES(?,?)", (user_id, iso())
        )
        legacy = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='records_legacy_v01'"
        ).fetchone()
        if legacy:
            connection.execute(
                """INSERT INTO records(user_id,client_uuid,kind,occurred_at,time_scope,day_slot,
                   energy,content,created_at,ash)
                   SELECT ?,client_uuid,kind,occurred_at,time_scope,day_slot,energy,content,created_at,0
                   FROM records_legacy_v01""", (user_id,)
            )
            connection.execute("DROP TABLE records_legacy_v01")
        result = issue_session(connection, user_id)
        connection.commit()
        return result


@app.post("/api/v1/auth/login")
async def login(payload: PasswordInput, request: Request) -> dict[str, str]:
    address = request.client.host if request.client else "unknown"
    cutoff = iso(utc_now() - timedelta(minutes=15))
    with closing(connect()) as connection:
        connection.execute("DELETE FROM login_attempts WHERE attempted_at<?", (cutoff,))
        failures = connection.execute(
            "SELECT count(*) count FROM login_attempts WHERE address=? AND attempted_at>=?",
            (address, cutoff),
        ).fetchone()["count"]
        if failures >= 8:
            connection.commit()
            raise friendly(429, "TOO_MANY_ATTEMPTS", "这里暂时锁了一会儿，可以稍后再试。")
        user = connection.execute("SELECT * FROM users WHERE username='me'").fetchone()
        if not user or not verify_password(payload.password, user["password_hash"], user["password_salt"]):
            connection.execute(
                "INSERT INTO login_attempts(address,attempted_at) VALUES(?,?)", (address, iso())
            )
            connection.commit()
            raise friendly(401, "WRONG_PASSWORD", "这个密码没对上，可以再试一次，也可以先休息一会儿。")
        connection.execute("DELETE FROM login_attempts WHERE address=?", (address,))
        result = issue_session(connection, user["id"])
        connection.commit()
        return result


@app.post("/api/v1/auth/logout", status_code=204)
async def logout(user_id: AuthUser, authorization: Annotated[str | None, Header()] = None) -> None:
    del user_id
    with closing(connect()) as connection:
        connection.execute("DELETE FROM sessions WHERE token_hash=?", (token_digest(authorization[7:]),))
        connection.commit()


@app.post("/api/v1/checkins", status_code=201)
async def create_checkin(user_id: AuthUser, payload: CheckinCreate | None = None) -> dict[str, object]:
    data = payload or CheckinCreate()
    with closing(connect()) as connection:
        record, _ = insert_record(
            connection, user_id, kind="checkin", occurred_at=iso(), time_scope="exact",
            energy=data.energy, content=data.note, client_uuid=data.client_uuid,
            effort_unit=data.effort_unit,
        )
        connection.commit()
        return record


@app.post("/api/v1/checkins/batch")
async def batch_checkins(payload: BatchCheckinCreate, user_id: AuthUser) -> dict[str, int]:
    accepted = duplicates = invalid = 0
    with closing(connect()) as connection:
        for item in payload.items:
            if (
                item.client_created_at is not None
                and (
                    item.client_created_at.tzinfo is None
                    or item.client_created_at.astimezone(timezone.utc) > utc_now() + timedelta(minutes=5)
                )
            ):
                invalid += 1
                continue
            occurred = iso(item.client_created_at) if item.client_created_at else iso()
            _, created = insert_record(
                connection, user_id, kind="checkin", occurred_at=occurred, time_scope="exact",
                energy=item.energy, content=item.note, client_uuid=item.client_uuid,
                effort_unit=item.effort_unit,
            )
            accepted += int(created)
            duplicates += int(not created)
        connection.commit()
    return {
        "accepted": accepted,
        "duplicates_ignored": duplicates,
        "invalid_ignored": invalid,
    }


@app.post("/api/v1/records/backfill", status_code=201)
async def create_backfill(payload: BackfillCreate, user_id: AuthUser) -> dict[str, object]:
    occurred_at = None
    scope = "past"
    if payload.day is not None:
        occurred_at = datetime.combine(payload.day, time(hour=12), tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
        scope = "exact"
    with closing(connect()) as connection:
        record, _ = insert_record(
            connection, user_id, kind="backfill", occurred_at=occurred_at, time_scope=scope,
            day_slot=payload.day_slot, energy=payload.energy, content=payload.note,
            effort_unit=payload.effort_unit,
        )
        connection.commit()
        return record


@app.get("/api/v1/records")
async def list_records(
    user_id: AuthUser,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
    day: date | None = None,
) -> dict[str, object]:
    with closing(connect()) as connection:
        where = "user_id=?"
        parameters: list[object] = [user_id]
        if day is not None:
            where += " AND time_scope='exact' AND substr(occurred_at,1,10)=?"
            parameters.append(day.isoformat())
        parameters.extend((limit, offset))
        rows = connection.execute(
            f"""SELECT * FROM records WHERE {where}
               ORDER BY CASE WHEN time_scope='exact' THEN 0 ELSE 1 END,
                         occurred_at DESC,created_at DESC LIMIT ? OFFSET ?""", parameters
        ).fetchall()
    next_cursor = offset + len(rows) if len(rows) == limit else None
    return {"items": [row_record(row) for row in rows], "next_cursor": next_cursor}


@app.patch("/api/v1/records/{record_id}")
async def update_record(record_id: int, payload: RecordUpdate, user_id: AuthUser) -> dict[str, object]:
    fields: dict[str, object] = {}
    if "day" in payload.model_fields_set:
        fields["occurred_at"] = (
            datetime.combine(payload.day, time(hour=12), tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
            if payload.day else None
        )
        fields["time_scope"] = "exact" if payload.day else "past"
    for api_name, db_name in (
        ("day_slot", "day_slot"), ("energy", "energy"), ("content", "content"),
        ("effort_unit", "effort_unit"),
    ):
        if api_name in payload.model_fields_set:
            fields[db_name] = getattr(payload, api_name)
    if not fields:
        raise friendly(422, "VALIDATION", "这里没有需要改动的内容。")
    with closing(connect()) as connection:
        values = list(fields.values()) + [record_id, user_id]
        cursor = connection.execute(
            f"UPDATE records SET {','.join(f'{key}=?' for key in fields)} WHERE id=? AND user_id=?", values
        )
        if cursor.rowcount == 0:
            raise friendly(404, "NOT_FOUND", "没找到这段记录，它可能已经收好了。")
        connection.commit()
        return row_record(connection.execute("SELECT * FROM records WHERE id=?", (record_id,)).fetchone())


@app.delete("/api/v1/records/{record_id}", status_code=204)
async def delete_record(record_id: int, user_id: AuthUser) -> None:
    with closing(connect()) as connection:
        cursor = connection.execute("DELETE FROM records WHERE id=? AND user_id=?", (record_id, user_id))
        connection.commit()
    if cursor.rowcount == 0:
        raise friendly(404, "NOT_FOUND", "没找到这段记录，它可能已经收好了。")


@app.get("/api/v1/weave")
async def weave(
    user_id: AuthUser,
    days: Annotated[int, Query(ge=7, le=730)] = 180,
) -> dict[str, object]:
    cutoff = (utc_now() - timedelta(days=days - 1)).date().isoformat()
    with closing(connect()) as connection:
        rows = connection.execute(
            """SELECT substr(occurred_at,1,10) day,energy,count(*) count FROM records
               WHERE user_id=? AND time_scope='exact' AND substr(occurred_at,1,10)>=?
               GROUP BY day,energy ORDER BY day""", (user_id, cutoff)
        ).fetchall()
        past = connection.execute(
            "SELECT energy,count(*) count FROM records WHERE user_id=? AND time_scope='past' GROUP BY energy", (user_id,)
        ).fetchall()
        last = connection.execute(
            """SELECT COALESCE(occurred_at,created_at) activity_at FROM records
               WHERE user_id=? ORDER BY activity_at DESC LIMIT 1""", (user_id,)
        ).fetchone()
    grouped: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        grouped.setdefault(row["day"], []).append({"energy": row["energy"], "count": row["count"]})
    temperature = 1.0
    if last:
        elapsed_days = max(0, (utc_now() - parse_iso(last["activity_at"])).days)
        temperature = max(0.15, 1 - elapsed_days / 90)
    return {
        "days": [{"day": day, "threads": threads} for day, threads in grouped.items()],
        "past": {"label": "过去", "threads": [{"energy": r["energy"], "count": r["count"]} for r in past]},
        "ember": {"temperature": round(temperature, 3)},
    }


@app.get("/api/v1/comeback")
async def comeback(user_id: AuthUser) -> dict[str, object]:
    with closing(connect()) as connection:
        rows = connection.execute(
            """SELECT COALESCE(occurred_at,created_at) activity_at,content FROM records
               WHERE user_id=? ORDER BY activity_at""", (user_id,)
        ).fetchall()
    if not rows:
        return {"is_comeback": False}
    last_time = parse_iso(rows[-1]["activity_at"])
    gap_days = (utc_now() - last_time).days
    restart_count = 0
    previous = None
    for row in rows:
        current = parse_iso(row["activity_at"])
        if previous and (current - previous).days >= 7:
            restart_count += 1
        previous = current
    if gap_days < 7:
        return {"is_comeback": False}
    hint = rows[-1]["content"]
    return {"is_comeback": True, "card": {
        "last_left_at": rows[-1]["activity_at"],
        "last_left_hint": f"你上一次离开前，记下的是「{hint}」。" if hint else "你上一次留下的痕迹还在这里。",
        "restart_count": restart_count + 1, "message": "你回来了。过去的痕迹还在这里。",
    }, "options": [
        {"id": "backfill", "label": "补记那段时间"},
        {"id": "fresh", "label": "直接开始新的"},
    ]}


@app.post("/api/v1/timers", status_code=201)
async def start_timer(user_id: AuthUser) -> dict[str, object]:
    now = iso()
    with closing(connect()) as connection:
        active = connection.execute("SELECT * FROM timers WHERE user_id=? AND status!='closed'", (user_id,)).fetchone()
        if active:
            return timer_payload(active)
        cursor = connection.execute(
            "INSERT INTO timers(user_id,status,last_resumed_at,created_at) VALUES(?,'running',?,?)", (user_id, now, now)
        )
        connection.execute("INSERT INTO timer_segments(timer_id,started_at) VALUES(?,?)", (cursor.lastrowid, now))
        connection.commit()
        return timer_payload(connection.execute("SELECT * FROM timers WHERE id=?", (cursor.lastrowid,)).fetchone())


@app.get("/api/v1/timers/active")
async def active_timer(user_id: AuthUser) -> dict[str, object] | None:
    with closing(connect()) as connection:
        row = connection.execute("SELECT * FROM timers WHERE user_id=? AND status!='closed'", (user_id,)).fetchone()
    return timer_payload(row) if row else None


@app.get("/api/v1/timers/{timer_id}")
async def get_timer(timer_id: int, user_id: AuthUser) -> dict[str, object]:
    with closing(connect()) as connection:
        row = connection.execute("SELECT * FROM timers WHERE id=? AND user_id=?", (timer_id, user_id)).fetchone()
    if not row:
        raise friendly(404, "NOT_FOUND", "没找到这段计时，它可能已经收好了。")
    return timer_payload(row)


@app.post("/api/v1/timers/{timer_id}/pause")
async def pause_timer(timer_id: int, user_id: AuthUser) -> dict[str, object]:
    now = utc_now()
    with closing(connect()) as connection:
        row = connection.execute("SELECT * FROM timers WHERE id=? AND user_id=?", (timer_id, user_id)).fetchone()
        if not row or row["status"] == "closed":
            raise friendly(404, "NOT_FOUND", "没找到这段计时，它可能已经收好了。")
        if row["status"] == "running":
            total = int(row["accumulated_seconds"]) + max(0, int((now - parse_iso(row["last_resumed_at"])).total_seconds()))
            connection.execute("UPDATE timers SET status='paused',accumulated_seconds=?,last_resumed_at=NULL WHERE id=?", (total, timer_id))
            connection.execute("UPDATE timer_segments SET ended_at=? WHERE timer_id=? AND ended_at IS NULL", (iso(now), timer_id))
            connection.commit()
        fresh = connection.execute("SELECT * FROM timers WHERE id=?", (timer_id,)).fetchone()
    result = timer_payload(fresh)
    result["break_card"] = {"message": f"你在这里停下了，那时已经走了 {max(1, int(result['elapsed_seconds']) // 60)} 分钟。"}
    return result


@app.post("/api/v1/timers/{timer_id}/resume")
async def resume_timer(timer_id: int, user_id: AuthUser) -> dict[str, object]:
    now = iso()
    with closing(connect()) as connection:
        row = connection.execute("SELECT * FROM timers WHERE id=? AND user_id=?", (timer_id, user_id)).fetchone()
        if not row or row["status"] == "closed":
            raise friendly(404, "NOT_FOUND", "没找到这段计时，它可能已经收好了。")
        if row["status"] == "paused":
            connection.execute("UPDATE timers SET status='running',last_resumed_at=? WHERE id=?", (now, timer_id))
            connection.execute("INSERT INTO timer_segments(timer_id,started_at) VALUES(?,?)", (timer_id, now))
            connection.commit()
        return timer_payload(connection.execute("SELECT * FROM timers WHERE id=?", (timer_id,)).fetchone())


@app.post("/api/v1/timers/{timer_id}/close")
async def close_timer(timer_id: int, user_id: AuthUser) -> dict[str, object]:
    with closing(connect()) as connection:
        row = connection.execute("SELECT * FROM timers WHERE id=? AND user_id=?", (timer_id, user_id)).fetchone()
        if not row or row["status"] == "closed":
            raise friendly(404, "NOT_FOUND", "没找到这段计时，它可能已经收好了。")
        payload = timer_payload(row)
        total = int(payload["elapsed_seconds"])
        now = iso()
        connection.execute(
            "UPDATE timers SET status='closed',accumulated_seconds=?,last_resumed_at=NULL,closed_at=? WHERE id=?", (total, now, timer_id)
        )
        connection.execute("UPDATE timer_segments SET ended_at=? WHERE timer_id=? AND ended_at IS NULL", (now, timer_id))
        record, _ = insert_record(
            connection, user_id, kind="timer_close", occurred_at=now, time_scope="exact",
            energy=None, content=None, duration_seconds=total, timer_id=timer_id,
        )
        connection.commit()
        return {"total_seconds": total, "record_id": record["id"]}


@app.post("/api/v1/lamps", status_code=201)
async def create_lamp(payload: LampCreate, user_id: AuthUser) -> dict[str, object]:
    now = iso()
    with closing(connect()) as connection:
        cursor = connection.execute(
            "INSERT INTO lamps(user_id,message,energy_at_write,created_at) VALUES(?,?,?,?)",
            (user_id, payload.message, payload.energy_at_write, now),
        )
        connection.commit()
        return {"id": cursor.lastrowid, "message": payload.message, "energy_at_write": payload.energy_at_write, "created_at": now, "opened_at": None}


@app.get("/api/v1/lamps")
async def list_lamps(user_id: AuthUser) -> dict[str, object]:
    with closing(connect()) as connection:
        rows = connection.execute("SELECT * FROM lamps WHERE user_id=? ORDER BY created_at DESC", (user_id,)).fetchall()
    return {"lamps": [dict(row) for row in rows], "context_note": "这些话一直在这里，只在你主动打开时出现。"}


@app.post("/api/v1/lamps/{lamp_id}/open")
async def open_lamp(lamp_id: int, user_id: AuthUser) -> dict[str, object]:
    now = iso()
    with closing(connect()) as connection:
        row = connection.execute("SELECT * FROM lamps WHERE id=? AND user_id=?", (lamp_id, user_id)).fetchone()
        if not row:
            raise friendly(404, "NOT_FOUND", "这盏灯不在这里了。")
        connection.execute("UPDATE lamps SET opened_at=? WHERE id=?", (now, lamp_id))
        connection.commit()
        return {"id": lamp_id, "message": row["message"], "energy_at_write": row["energy_at_write"], "created_at": row["created_at"], "opened_at": now}


@app.delete("/api/v1/lamps/{lamp_id}", status_code=204)
async def delete_lamp(lamp_id: int, user_id: AuthUser) -> None:
    with closing(connect()) as connection:
        cursor = connection.execute("DELETE FROM lamps WHERE id=? AND user_id=?", (lamp_id, user_id))
        connection.commit()
    if cursor.rowcount == 0:
        raise friendly(404, "NOT_FOUND", "这盏灯不在这里了。")


@app.get("/api/v1/settings")
async def get_settings(user_id: AuthUser) -> dict[str, bool]:
    with closing(connect()) as connection:
        row = connection.execute("SELECT * FROM user_settings WHERE user_id=?", (user_id,)).fetchone()
        latest_record = connection.execute(
            "SELECT created_at FROM records WHERE user_id=? ORDER BY created_at DESC LIMIT 1",
            (user_id,),
        ).fetchone()
        user = connection.execute("SELECT created_at FROM users WHERE id=?", (user_id,)).fetchone()
    preferences = {
        key: bool(row[key])
        for key in (
            "low_energy_mode", "auto_low_energy_mode", "hide_all_numbers",
            "nothing_mode", "notify_enabled", "weekly_report_opt_out", "privacy_mode",
        )
    }
    auto_active = bool(
        preferences["auto_low_energy_mode"]
        and parse_iso(latest_record["created_at"] if latest_record else user["created_at"])
        <= utc_now() - timedelta(days=3)
    )
    return {**preferences, "auto_low_energy_active": auto_active}


@app.post("/api/v1/reflections/weekly")
async def weekly_reflection(user_id: AuthUser) -> dict[str, object]:
    cutoff = iso(utc_now() - timedelta(days=7))
    with closing(connect()) as connection:
        settings = connection.execute(
            "SELECT weekly_report_opt_out,nothing_mode FROM user_settings WHERE user_id=?", (user_id,)
        ).fetchone()
        if settings["weekly_report_opt_out"] or settings["nothing_mode"]:
            raise friendly(409, "REFLECTION_DISABLED", "回看已经按你的选择保持安静。")
        rows = connection.execute(
            """SELECT occurred_at,day_slot,content,effort_unit FROM records
               WHERE user_id=? AND COALESCE(occurred_at,created_at)>=?""",
            (user_id, cutoff),
        ).fetchall()

    if not rows:
        return {"period": "past_7_days", "lines": ["过去七天的织痕保持着原来的样子。"]}
    exact_days = {row["occurred_at"][:10] for row in rows if row["occurred_at"]}
    lines = [f"过去七天，织痕里新增了 {len(rows)} 根线。"]
    if exact_days:
        lines.append(f"这些痕迹分布在 {len(exact_days)} 个日期里。")
    slot_labels = {"morning": "早上", "afternoon": "下午", "evening": "晚上", "night": "深夜"}
    slot_counts = {
        slot: sum(row["day_slot"] == slot for row in rows) for slot in slot_labels
    }
    for slot, label in slot_labels.items():
        if slot_counts[slot]:
            lines.append(f"其中有 {slot_counts[slot]} 根记录在{label}。")
    note_count = sum(bool(row["content"]) for row in rows)
    if note_count:
        lines.append(f"有 {note_count} 根线带着当时留下的话。")
    unit_counts: dict[str, int] = {}
    for row in rows:
        if row["effort_unit"]:
            unit_counts[row["effort_unit"]] = unit_counts.get(row["effort_unit"], 0) + 1
    for unit, count in sorted(unit_counts.items(), key=lambda item: (-item[1], item[0]))[:3]:
        lines.append(f"“{unit}”被记下了 {count} 次。")
    return {"period": "past_7_days", "lines": lines}


@app.post("/api/v1/echo")
async def deliver_echo(user_id: AuthUser) -> dict[str, object]:
    with closing(connect()) as connection:
        settings = connection.execute(
            "SELECT notify_enabled,nothing_mode,privacy_mode FROM user_settings WHERE user_id=?", (user_id,)
        ).fetchone()
        if not settings["notify_enabled"] or settings["nothing_mode"]:
            return {"echo": None}
        latest = connection.execute(
            "SELECT id,created_at FROM records WHERE user_id=? ORDER BY created_at DESC LIMIT 1",
            (user_id,),
        ).fetchone()
        if not latest or parse_iso(latest["created_at"]) > utc_now() - timedelta(days=14):
            return {"echo": None}
        delivered = connection.execute(
            "SELECT 1 FROM echo_deliveries WHERE user_id=? AND anchor_record_id=?",
            (user_id, latest["id"]),
        ).fetchone()
        if delivered:
            return {"echo": None}
        connection.execute(
            "INSERT INTO echo_deliveries(user_id,anchor_record_id,delivered_at) VALUES(?,?,?)",
            (user_id, latest["id"], iso()),
        )
        connection.commit()
    if settings["privacy_mode"]:
        return {"echo": {"title": "提醒", "message": "有一条留给你的消息。"}}
    return {"echo": {"title": "织痕", "message": "有一段痕迹仍在这里。"}}


@app.patch("/api/v1/settings")
async def update_settings(payload: SettingsUpdate, user_id: AuthUser) -> dict[str, bool]:
    fields = {name: int(getattr(payload, name)) for name in payload.model_fields_set}
    if fields:
        with closing(connect()) as connection:
            connection.execute(
                f"UPDATE user_settings SET {','.join(f'{key}=?' for key in fields)},updated_at=? WHERE user_id=?",
                list(fields.values()) + [iso(), user_id],
            )
            connection.commit()
    return await get_settings(user_id)


@app.post("/api/v1/data/export")
async def export_data(payload: ExportInput, user_id: AuthUser) -> Response:
    if payload.format == "png":
        raise friendly(422, "CLIENT_EXPORT", "织痕长卷由当前设备直接生成，不上传图案。")
    with closing(connect()) as connection:
        data = {
            "exported_at": iso(),
            "records": [dict(row) for row in connection.execute("SELECT * FROM records WHERE user_id=?", (user_id,))],
            "timers": [dict(row) for row in connection.execute("SELECT * FROM timers WHERE user_id=?", (user_id,))],
            "timer_segments": [dict(row) for row in connection.execute(
                "SELECT s.* FROM timer_segments s JOIN timers t ON t.id=s.timer_id WHERE t.user_id=?",
                (user_id,),
            )],
            "lamps": [dict(row) for row in connection.execute("SELECT * FROM lamps WHERE user_id=?", (user_id,))],
            "settings": dict(connection.execute("SELECT * FROM user_settings WHERE user_id=?", (user_id,)).fetchone()),
        }
    return Response(
        content=json.dumps(data, ensure_ascii=False, indent=2), media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="zhihen-export.json"'},
    )


@app.post("/api/v1/data/ash")
async def ash_data(user_id: AuthUser) -> dict[str, str]:
    with closing(connect()) as connection:
        connection.execute(
            "UPDATE records SET content=NULL,effort_unit=NULL,ash=1 WHERE user_id=?",
            (user_id,),
        )
        connection.execute("DELETE FROM lamps WHERE user_id=?", (user_id,))
        connection.commit()
    return {"result": "视觉图案保留，文字已经收走。"}


@app.get("/api/v1/data/purge")
async def purge_status(user_id: AuthUser) -> dict[str, object]:
    with closing(connect()) as connection:
        row = connection.execute("SELECT * FROM purge_requests WHERE user_id=?", (user_id,)).fetchone()
    return {"pending": bool(row), "grace_until": row["execute_at"] if row else None}


@app.post("/api/v1/data/purge", status_code=202)
async def request_purge(payload: PurgeInput, user_id: AuthUser) -> dict[str, str]:
    if not payload.confirm:
        raise friendly(422, "VALIDATION", "需要由你确认这次清空。")
    requested = utc_now()
    execute_at = requested + timedelta(hours=48)
    with closing(connect()) as connection:
        connection.execute(
            """INSERT INTO purge_requests(user_id,requested_at,execute_at) VALUES(?,?,?)
               ON CONFLICT(user_id) DO UPDATE SET requested_at=excluded.requested_at,execute_at=excluded.execute_at""",
            (user_id, iso(requested), iso(execute_at)),
        )
        connection.commit()
    return {"grace_until": iso(execute_at)}


@app.post("/api/v1/data/purge/cancel", status_code=204)
async def cancel_purge(user_id: AuthUser) -> None:
    with closing(connect()) as connection:
        connection.execute("DELETE FROM purge_requests WHERE user_id=?", (user_id,))
        connection.commit()


@app.get("/api/v1/help/resources")
async def help_resources() -> dict[str, object]:
    return {
        "note": "如果你需要真正的帮助，我无法替代专业支持，他们可以陪你一起处理此刻。",
        "resources": [
            {"name": "全国统一心理援助热线", "phone": "12356"},
            {"name": "紧急医疗帮助", "phone": "120"},
        ],
    }


@app.exception_handler(HTTPException)
async def http_exception_handler(_, exc: HTTPException) -> JSONResponse:
    if isinstance(exc.detail, dict) and "code" in exc.detail:
        return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})
    return JSONResponse(status_code=exc.status_code, content={"error": {"code": "REQUEST", "message": str(exc.detail)}})
