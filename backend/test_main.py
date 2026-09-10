import asyncio
import tempfile
import unittest
from pathlib import Path

import database
import main
from schemas import BackfillCreate, CheckinCreate, LampCreate, PasswordInput, PurgeInput


class ApiDomainTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        database.DATABASE_PATH = Path(self.temp_dir.name) / "test.db"
        database.initialize_database()
        asyncio.run(main.setup(PasswordInput(password="quiet-key")))
        self.user_id = 1

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_checkin_accepts_empty_input_and_is_idempotent(self) -> None:
        payload = CheckinCreate(client_uuid="same-client-record")
        first = asyncio.run(main.create_checkin(self.user_id, payload))
        second = asyncio.run(main.create_checkin(self.user_id, payload))
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(first["time_scope"], "exact")

    def test_backfill_without_day_is_past(self) -> None:
        record = asyncio.run(main.create_backfill(BackfillCreate(note="一段过去"), self.user_id))
        self.assertEqual(record["time_scope"], "past")
        self.assertEqual(record["time_label"], "过去")
        self.assertIsNone(record["occurred_at"])

    def test_timer_pause_resume_and_close_creates_record(self) -> None:
        timer = asyncio.run(main.start_timer(self.user_id))
        paused = asyncio.run(main.pause_timer(timer["id"], self.user_id))
        self.assertEqual(paused["status"], "paused")
        resumed = asyncio.run(main.resume_timer(timer["id"], self.user_id))
        self.assertEqual(resumed["status"], "running")
        closed = asyncio.run(main.close_timer(timer["id"], self.user_id))
        self.assertIn("record_id", closed)

    def test_lamp_only_opens_on_request(self) -> None:
        lamp = asyncio.run(main.create_lamp(LampCreate(message="给未来的话"), self.user_id))
        self.assertIsNone(lamp["opened_at"])
        opened = asyncio.run(main.open_lamp(lamp["id"], self.user_id))
        self.assertIsNotNone(opened["opened_at"])

    def test_delete_physically_removes_record(self) -> None:
        record = asyncio.run(main.create_checkin(self.user_id))
        asyncio.run(main.delete_record(record["id"], self.user_id))
        items = asyncio.run(main.list_records(self.user_id))["items"]
        self.assertEqual(items, [])

    def test_purge_has_a_48_hour_window(self) -> None:
        result = asyncio.run(main.request_purge(PurgeInput(confirm=True), self.user_id))
        pending = asyncio.run(main.purge_status(self.user_id))
        self.assertTrue(pending["pending"])
        self.assertEqual(result["grace_until"], pending["grace_until"])
        asyncio.run(main.cancel_purge(self.user_id))
        self.assertFalse(asyncio.run(main.purge_status(self.user_id))["pending"])


if __name__ == "__main__":
    unittest.main()
