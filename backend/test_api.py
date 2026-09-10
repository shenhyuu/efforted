from __future__ import annotations

from datetime import timedelta

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
    with database.connect() as connection:
        connection.execute(
            "INSERT INTO purge_requests(user_id,requested_at,execute_at) VALUES(1,?,?)",
            (iso(), iso(utc_now() - timedelta(seconds=1))),
        )
        connection.commit()
    assert main.execute_all_due_purges() == 1
    with database.connect() as connection:
        assert connection.execute("SELECT count(*) FROM records").fetchone()[0] == 0
