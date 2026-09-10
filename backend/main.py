from __future__ import annotations

import json
import sqlite3
from contextlib import asynccontextmanager, closing
from datetime import datetime, time, timedelta, timezone
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Response, status
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
    connection.execute("DELETE FROM purge_requests WHERE user_id=?", (user_id,))
    connection.commit()
    return True


def current_user(authorization: Annotated[str | None, Header()] = None) -> int:
    if not authorization or not authorization.startswith("Bearer "):
        raise friendly(401, "UNAUTHORIZED", "这次访问需要先确认是你。")
    digest = token_digest(authorization[7:])
    with closing(connect()) as connection:
        session = connection.execute(
            "SELECT user_id,expires_at FROM sessions WHERE token_hash=?", (digest,)
        ).fetchone()
        if not session or parse_iso(session["expires_at"]) <= utc_now():
            raise friendly(401, "UNAUTHORIZED", "这次访问已经安静地结束了，可以重新进入。")
        execute_due_purge(connection, session["user_id"])
        return int(session["user_id"])


AuthUser = Annotated[int, Depends(current_user)]


def insert_record(
    connection: sqlite3.Connection, user_id: int, *, kind: str, occurred_at: str | None,
    time_scope: str, energy: str | None, content: str | None, day_slot: str | None = None,
    client_uuid: str | None = None, duration_seconds: int | None = None,
    timer_id: int | None = None,
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
            duration_seconds,timer_id,created_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
        (user_id, client_uuid, kind, occurred_at, time_scope, day_slot, energy,
         content or None, duration_seconds, timer_id, iso()),
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
    yield


app = FastAPI(title="织痕 API", description="记录出现过的时刻，不评价它们。", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=False, allow_methods=["GET", "POST", "PATCH", "DELETE"], allow_headers=["*"],
)


@app.get("/")
async def root() -> dict[str, str]:
    return {"name": "织痕", "version": app.version, "docs": "/docs"}


@app.get("/health")
async def health() -> dict[str, str]:
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
async def login(payload: PasswordInput) -> dict[str, str]:
    with closing(connect()) as connection:
        user = connection.execute("SELECT * FROM users WHERE username='me'").fetchone()
        if not user or not verify_password(payload.password, user["password_hash"], user["password_salt"]):
            raise friendly(401, "WRONG_PASSWORD", "这个密码没对上，可以再试一次，也可以先休息一会儿。")
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
        )
        connection.commit()
        return record


@app.post("/api/v1/checkins/batch")
async def batch_checkins(payload: BatchCheckinCreate, user_id: AuthUser) -> dict[str, int]:
    accepted = duplicates = 0
    with closing(connect()) as connection:
        for item in payload.items:
            occurred = item.client_created_at or iso()
            _, created = insert_record(
                connection, user_id, kind="checkin", occurred_at=occurred, time_scope="exact",
                energy=item.energy, content=item.note, client_uuid=item.client_uuid,
            )
            accepted += int(created)
            duplicates += int(not created)
        connection.commit()
    return {"accepted": accepted, "duplicates_ignored": duplicates}


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
        )
        connection.commit()
        return record


@app.get("/api/v1/records")
async def list_records(user_id: AuthUser, limit: Annotated[int, Query(ge=1, le=200)] = 100) -> dict[str, object]:
    with closing(connect()) as connection:
        rows = connection.execute(
            """SELECT * FROM records WHERE user_id=?
               ORDER BY CASE WHEN time_scope='exact' THEN 0 ELSE 1 END,
                        occurred_at DESC,created_at DESC LIMIT ?""", (user_id, limit)
        ).fetchall()
    return {"items": [row_record(row) for row in rows], "next_cursor": None}


@app.patch("/api/v1/records/{record_id}")
async def update_record(record_id: int, payload: RecordUpdate, user_id: AuthUser) -> dict[str, object]:
    fields: dict[str, object] = {}
    if "day" in payload.model_fields_set:
        fields["occurred_at"] = (
            datetime.combine(payload.day, time(hour=12), tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
            if payload.day else None
        )
        fields["time_scope"] = "exact" if payload.day else "past"
    for api_name, db_name in (("day_slot", "day_slot"), ("energy", "energy"), ("content", "content")):
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
async def weave(user_id: AuthUser) -> dict[str, object]:
    with closing(connect()) as connection:
        rows = connection.execute(
            """SELECT substr(occurred_at,1,10) day,energy,count(*) count FROM records
               WHERE user_id=? AND time_scope='exact' GROUP BY day,energy ORDER BY day""", (user_id,)
        ).fetchall()
        past = connection.execute(
            "SELECT energy,count(*) count FROM records WHERE user_id=? AND time_scope='past' GROUP BY energy", (user_id,)
        ).fetchall()
        last = connection.execute(
            "SELECT occurred_at FROM records WHERE user_id=? AND occurred_at IS NOT NULL ORDER BY occurred_at DESC LIMIT 1", (user_id,)
        ).fetchone()
    grouped: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        grouped.setdefault(row["day"], []).append({"energy": row["energy"], "count": row["count"]})
    temperature = 1.0
    if last:
        days = max(0, (utc_now() - parse_iso(last["occurred_at"])).days)
        temperature = max(0.15, 1 - days / 90)
    return {
        "days": [{"day": day, "threads": threads} for day, threads in grouped.items()],
        "past": {"label": "过去", "threads": [{"energy": r["energy"], "count": r["count"]} for r in past]},
        "ember": {"temperature": round(temperature, 3)},
    }


@app.get("/api/v1/comeback")
async def comeback(user_id: AuthUser) -> dict[str, object]:
    with closing(connect()) as connection:
        rows = connection.execute(
            "SELECT occurred_at,content FROM records WHERE user_id=? AND occurred_at IS NOT NULL ORDER BY occurred_at", (user_id,)
        ).fetchall()
    if not rows:
        return {"is_comeback": False}
    last_time = parse_iso(rows[-1]["occurred_at"])
    gap_days = (utc_now() - last_time).days
    restart_count = 0
    previous = None
    for row in rows:
        current = parse_iso(row["occurred_at"])
        if previous and (current - previous).days >= 7:
            restart_count += 1
        previous = current
    if gap_days < 7:
        return {"is_comeback": False}
    return {"is_comeback": True, "card": {
        "last_left_at": rows[-1]["occurred_at"], "last_left_hint": rows[-1]["content"],
        "restart_count": restart_count + 1, "message": "你回来了。过去的痕迹还在这里。",
    }}


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
    return {key: bool(row[key]) for key in ("low_energy_mode", "hide_all_numbers", "nothing_mode", "privacy_mode")}


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
        connection.execute("UPDATE records SET content=NULL,energy=NULL,ash=1 WHERE user_id=?", (user_id,))
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
