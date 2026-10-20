"""Checkpoints retain an explicit generation and consistent event cutoff."""
from tests.test_store import StoreCase, WORKER
from ninnin_core.store import Store


class CheckpointTests(StoreCase):
    def test_checkpoint_is_durable_and_cannot_be_overwritten_by_a_fenced_writer(self):
        room = self.make_room()
        task = self.store.create_task(room["id"], "交接", "核验", WORKER)
        run = self.store.start_run(task["id"])
        self.assertTrue(callable(getattr(self.store, "checkpoint", None)), "Checkpoint must survive worker exit")
        self.assertIsNone(self.store.get_checkpoint(task["id"]))
        event = self.store.add_event(room["id"], "tool_started", {"unknown_side_effects": ["待核对"]}, task_id=task["id"], run_id=run["id"])
        data = {"completed": ["已核验事实"], "unknown_side_effects": ["待核对"], "next_step": "查证"}
        point = self.store.checkpoint(task["id"], data, expected_generation=run["generation"])
        self.assertEqual(point["generation"], run["generation"])
        self.assertEqual(point["version"], 1)
        self.assertEqual(point["data"], data)
        self.assertGreaterEqual(point["events_cursor"], event["seq"])
        self.assertTrue(point["timestamp"])
        self.assertEqual(Store(self.root).get_checkpoint(task["id"]), point)
        self.store.stop_branch(task["id"])
        for expected in (run["generation"], None):
            with self.subTest(expected=expected), self.assertRaises((ValueError, PermissionError)):
                self.store.checkpoint(task["id"], {"result": "late"}, expected_generation=expected)
        self.assertEqual(self.store.get_checkpoint(task["id"]), point)
        self.store.update_run(run["id"], {"state": "interrupted"})
        self.store.resume_task(task["id"], user_confirmed=True)
        new_run = self.store.start_run(task["id"])
        fresh = self.store.checkpoint(task["id"], {"next_step": "继续"}, expected_generation=new_run["generation"])
        self.assertGreater(fresh["events_cursor"], point["events_cursor"])
        self.assertEqual(self.store.get_checkpoint(task["id"]), fresh)
