"""SQLite Store contract tests; all test state lives in temporary fixture directories."""
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest

from ninnin_core.store import Store

SCRATCH = Path(tempfile.gettempdir())
DIRECTOR = {"provider": "fixture", "model": "director"}
WORKER = {"provider": "fixture", "model": "worker"}


class StoreCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ninnin-store-", dir=SCRATCH)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "领域状态"
        self.store = Store(self.root)

    def make_room(self, **kwargs):
        return self.store.create_room("研究工作台", DIRECTOR, [WORKER], **kwargs)


class DatabaseTests(StoreCase):
    def test_schema_version_is_persisted_and_future_databases_are_not_modified(self):
        with closing(sqlite3.connect(self.root / "state.db")) as db:
            self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 1)
            db.execute("PRAGMA user_version=999")
            db.commit()
        with self.assertRaises(ValueError):
            Store(self.root)
        with closing(sqlite3.connect(self.root / "state.db")) as db:
            self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 999)
            self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")

    def test_constructor_creates_a_real_sqlite_database(self):
        self.assertTrue((self.root / "state.db").is_file(), "Store must create state.db")
        with closing(sqlite3.connect(self.root / "state.db")) as db:
            self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(db.execute("PRAGMA journal_mode").fetchone()[0], "wal")


class RoomTests(StoreCase):
    def test_invalid_room_authorizations_or_secret_routes_leave_no_room(self):
        cases = [
            {"authorization_id": ""}, {"authorization_id": None},
            {"token_limit": -1}, {"token_limit": True},
            {"director_route": {"provider": "fixture"}},
            {"worker_routes": [{**WORKER, "api_key": "test-only-not-a-secret"}]},
            {"worker_routes": [{**WORKER, "base_url": "https://user:password@example.invalid"}]},
            {"worker_routes": [{**WORKER, "key_env": "not an env name"}]},
            {"worker_routes": [{**WORKER, "api_mode": "invented"}]},
        ]
        for changes in cases:
            with self.subTest(changes=changes):
                values = dict(title="test", director_route=DIRECTOR, worker_routes=[WORKER])
                values.update(changes)
                with self.assertRaises(ValueError):
                    self.store.create_room(**values)
        self.assertEqual(self.store.rooms(), [])
        with self.assertRaises(ValueError):
            self.store.room("missing")

    def test_room_round_trip_survives_a_new_store_instance(self):
        self.assertTrue(callable(getattr(self.store, "create_room", None)), "Store must persist rooms")
        room = self.make_room(authorization_id="approved-test", token_limit=100)
        self.assertEqual(room["title"], "研究工作台")
        self.assertEqual(room["director_route"], DIRECTOR)
        self.assertEqual(room["worker_routes"], [WORKER])
        self.assertEqual(room["authorization_id"], "approved-test")
        self.assertEqual(room["token_limit"], 100)
        reopened = Store(self.root)
        self.assertEqual(reopened.room(room["id"]), room)
        self.assertEqual(reopened.rooms(), [room])
        room["director_route"]["model"] = "mutated"
        self.assertEqual(reopened.room(room["id"])["director_route"], DIRECTOR)


if __name__ == "__main__":
    unittest.main()
