"""JSON-friendly user snapshots, read at one SQLite snapshot boundary."""
import json
from tests.test_store import StoreCase, DIRECTOR, WORKER
from ninnin_core.store import Store


class SnapshotTests(StoreCase):
    def test_snapshot_returns_owned_records_with_an_event_cutoff_and_private_audit(self):
        room = self.make_room()
        other = self.make_room()
        root = self.store.create_task(room["id"], "总指挥", "test", DIRECTOR, role="director")
        worker = self.store.create_task(room["id"], "工作者", "test", WORKER)
        foreign = self.store.create_task(other["id"], "不应混入", "test", WORKER)
        run = self.store.start_run(worker["id"])
        group = self.store.post_message(room["id"], "group", "user", "任务")
        director = self.store.post_message(room["id"], "director", "user", "目标")
        private = self.store.propose_private(room["id"], worker["id"], root["id"], "用户可见的待审原文")
        self.store.reserve("snapshot-call", worker["id"], 20)
        direction = self.store.add_direction(room["id"], "原始证据")
        cutoff = self.store.events(room["id"])[-1]["seq"]
        self.store.add_event(other["id"], "foreign_event", {}, task_id=foreign["id"])
        self.assertTrue(callable(getattr(self.store, "snapshot", None)), "UI and handoff need a consistent user snapshot")
        snapshot = Store(self.root).snapshot(room["id"])
        self.assertEqual(snapshot["room"], room)
        self.assertEqual({task["id"] for task in snapshot["tasks"]}, {root["id"], worker["id"]})
        self.assertEqual(snapshot["runs"], [run])
        self.assertEqual(snapshot["messages"], [group, director])
        self.assertEqual(snapshot["private_messages"], [private])
        self.assertEqual(snapshot["directions"], [direction])
        self.assertEqual(snapshot["events_cursor"], cutoff)
        self.assertEqual(snapshot["budgets"], self.store.budget_summary(room["id"]))
        self.assertEqual(json.loads(json.dumps(snapshot, ensure_ascii=False)), snapshot)
