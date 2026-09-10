from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

import database
import main
from security import iso, utc_now


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATABASE_PATH", tmp_path / "api.db")
    database.initialize_database()
    with TestClient(main.app) as test_client:
        yield test_client


def setup_headers(client: TestClient) -> dict[str, str]:
    response = client.post("/api/v1/auth/setup", json={"password": "quiet-key"})
    assert response.status_code == 201
    return {"Authorization": f"Bearer {response.json()['token']}"}


def test_checkin_requires_authentication(client: TestClient):
    response = client.post("/api/v1/checkins", json={})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_batch_is_idempotent_and_rejects_future_time(client: TestClient):
    headers = setup_headers(client)
    item = {"client_uuid": "offline-1", "client_created_at": iso()}
    first = client.post("/api/v1/checkins/batch", headers=headers, json={"items": [item]})
    second = client.post("/api/v1/checkins/batch", headers=headers, json={"items": [item]})
    assert first.json() == {"accepted": 1, "duplicates_ignored": 0}
    assert second.json() == {"accepted": 0, "duplicates_ignored": 1}

    future = {**item, "client_uuid": "offline-2", "client_created_at": iso(utc_now() + timedelta(hours=1))}
    assert client.post("/api/v1/checkins/batch", headers=headers, json={"items": [future]}).status_code == 422


def test_due_purge_runs_without_a_followup_api_request(client: TestClient):
    headers = setup_headers(client)
    assert client.post("/api/v1/checkins", headers=headers, json={}).status_code == 201
    client.patch(
        "/api/v1/settings", headers=headers,
        json={"notify_enabled": True, "low_energy_mode": True},
    )
    with database.connect() as connection:
        connection.execute(
            "INSERT INTO purge_requests(user_id,requested_at,execute_at) VALUES(1,?,?)",
            (iso(), iso(utc_now() - timedelta(seconds=1))),
        )
        connection.commit()
    assert main.execute_all_due_purges() == 1
    with database.connect() as connection:
        assert connection.execute("SELECT count(*) FROM records").fetchone()[0] == 0
    settings = client.get("/api/v1/settings", headers=headers).json()
    assert settings["notify_enabled"] is False
    assert settings["low_energy_mode"] is False


def test_optional_low_energy_simplification_uses_recent_activity(client: TestClient):
    headers = setup_headers(client)
    settings = client.patch(
        "/api/v1/settings", headers=headers, json={"auto_low_energy_mode": True}
    ).json()
    assert settings["notify_enabled"] is False
    assert settings["auto_low_energy_mode"] is True
    assert settings["auto_low_energy_active"] is False

    with database.connect() as connection:
        old = iso(utc_now() - timedelta(days=4))
        connection.execute(
            """INSERT INTO records
               (user_id,kind,occurred_at,time_scope,created_at)
               VALUES(1,'checkin',?,'exact',?)""",
            (old, old),
        )
        connection.commit()

    assert client.get("/api/v1/settings", headers=headers).json()["auto_low_energy_active"] is True
    assert client.post("/api/v1/checkins", headers=headers, json={}).status_code == 201
    assert client.get("/api/v1/settings", headers=headers).json()["auto_low_energy_active"] is False


def test_weekly_reflection_is_generated_only_on_request_and_can_be_disabled(client: TestClient):
    headers = setup_headers(client)
    client.post(
        "/api/v1/checkins", headers=headers,
        json={"note": "读了一会儿", "effort_unit": "读一页"},
    )
    reflection = client.post("/api/v1/reflections/weekly", headers=headers)
    assert reflection.status_code == 200
    assert reflection.json()["lines"][0] == "过去七天，织痕里新增了 1 根线。"

    client.patch(
        "/api/v1/settings", headers=headers, json={"weekly_report_opt_out": True}
    )
    assert client.post("/api/v1/reflections/weekly", headers=headers).status_code == 409

    client.patch(
        "/api/v1/settings", headers=headers,
        json={"weekly_report_opt_out": False, "nothing_mode": True},
    )
    assert client.post("/api/v1/reflections/weekly", headers=headers).status_code == 409


def test_custom_effort_unit_is_stored_without_aggregation(client: TestClient):
    headers = setup_headers(client)
    record = client.post(
        "/api/v1/checkins", headers=headers, json={"effort_unit": "打开了文档"}
    ).json()
    assert record["effort_unit"] == "打开了文档"
    listed = client.get("/api/v1/records", headers=headers).json()["items"]
    assert listed[0]["effort_unit"] == "打开了文档"


def test_echo_is_opt_in_neutral_and_delivered_once_per_old_anchor(client: TestClient):
    headers = setup_headers(client)
    old = iso(utc_now() - timedelta(days=15))
    with database.connect() as connection:
        connection.execute(
            """INSERT INTO records
               (user_id,kind,occurred_at,time_scope,created_at)
               VALUES(1,'checkin',?,'exact',?)""",
            (old, old),
        )
        connection.commit()

    assert client.post("/api/v1/echo", headers=headers).json() == {"echo": None}
    client.patch("/api/v1/settings", headers=headers, json={"notify_enabled": True})
    first = client.post("/api/v1/echo", headers=headers).json()["echo"]
    assert first == {"title": "织痕", "message": "有一段痕迹仍在这里。"}
    assert client.post("/api/v1/echo", headers=headers).json() == {"echo": None}


def test_future_backfill_is_rejected_and_weave_honors_window(client: TestClient):
    headers = setup_headers(client)
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    assert client.post(
        "/api/v1/records/backfill", headers=headers, json={"day": tomorrow}
    ).status_code == 422

    with database.connect() as connection:
        old = iso(utc_now() - timedelta(days=200))
        connection.execute(
            """INSERT INTO records(user_id,kind,occurred_at,time_scope,energy,created_at)
               VALUES(1,'checkin',?,'exact','low',?)""",
            (old, old),
        )
        connection.commit()
    recent = client.get("/api/v1/weave?days=180", headers=headers).json()
    expanded = client.get("/api/v1/weave?days=365", headers=headers).json()
    assert recent["days"] == []
    assert len(expanded["days"]) == 1


def test_ash_keeps_visual_energy_and_removes_text(client: TestClient):
    headers = setup_headers(client)
    record = client.post(
        "/api/v1/checkins", headers=headers,
        json={"energy": "enough", "note": "一段文字", "effort_unit": "一次出门"},
    ).json()
    client.post("/api/v1/lamps", headers=headers, json={"message": "留在灯里的话"})
    assert client.post("/api/v1/data/ash", headers=headers).status_code == 200
    stored = client.get("/api/v1/records", headers=headers).json()["items"][0]
    assert stored["id"] == record["id"]
    assert stored["energy"] == "enough"
    assert stored["content"] is None
    assert stored["effort_unit"] is None
    assert stored["ash"] is True
    assert client.get("/api/v1/lamps", headers=headers).json()["lamps"] == []


def test_comeback_has_neutral_context_and_equal_options(client: TestClient):
    headers = setup_headers(client)
    old = iso(utc_now() - timedelta(days=9))
    with database.connect() as connection:
        connection.execute(
            """INSERT INTO records(user_id,kind,occurred_at,time_scope,content,created_at)
               VALUES(1,'checkin',?,'exact','读到第四章',?)""",
            (old, old),
        )
        connection.commit()
    result = client.get("/api/v1/comeback", headers=headers).json()
    assert result["is_comeback"] is True
    assert "读到第四章" in result["card"]["last_left_hint"]
    assert [option["id"] for option in result["options"]] == ["backfill", "fresh"]
