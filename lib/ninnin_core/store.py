"""Transactional SQLite domain Store for ninnin-workbench.

This is a trusted-service API, not a model-facing authorization boundary. The
service must authenticate user/root decisions, bind worker operations to the
current owned run, and confirm budget approval before calling create_room.
Caller-provided role fields never change persisted task authority or accounting.
Each operation opens/closes its own SQLite connection; writers use BEGIN
IMMEDIATE and snapshots use one read transaction. No process/API is launched.

Private attachments are inline ``{name: str, content: str}`` reviewable packages;
no local files are read here. Pattern blocking is conservative, not a security
sandbox or a promise to detect every secret. ``unknown`` in budget summaries is
unresolved reserved tokens, already included in ``reserved`` (do not add twice).
Direction receipts advance pending -> delivered -> incorporated, and result
promotion waits for incorporation. Receipt calls are trusted service evidence,
not claims inferred from merely enqueueing text.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import math
import re
import sqlite3
from urllib.parse import urlsplit
from uuid import uuid4


class Store:
    _TERMINAL_RUNS = {"interrupted", "exited", "failed", "cancelled", "stopped", "completed"}
    _FROZEN_TASKS = {"stopped", "waiting_dependency"}

    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "state.db"
        db = sqlite3.connect(self.path, timeout=30)
        try:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1):
                raise ValueError("Unsupported Store schema version; refusing to modify it")
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("BEGIN IMMEDIATE")
            db.execute("CREATE TABLE IF NOT EXISTS rooms (id TEXT PRIMARY KEY, data TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS tasks (id TEXT PRIMARY KEY, room_id TEXT NOT NULL REFERENCES rooms(id), data TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS roots (room_id TEXT PRIMARY KEY REFERENCES rooms(id), task_id TEXT UNIQUE NOT NULL REFERENCES tasks(id))")
            db.execute("CREATE TABLE IF NOT EXISTS events (seq INTEGER PRIMARY KEY AUTOINCREMENT, room_id TEXT NOT NULL REFERENCES rooms(id), dedupe_key TEXT, data TEXT NOT NULL, UNIQUE(room_id,dedupe_key))")
            db.execute("CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(id), room_id TEXT NOT NULL REFERENCES rooms(id), data TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS allowances (authorization_id TEXT NOT NULL, provider TEXT NOT NULL, model TEXT NOT NULL, unlimited INTEGER NOT NULL DEFAULT 0, token_limit INTEGER, PRIMARY KEY(authorization_id,provider,model,unlimited))")
            db.execute("CREATE TABLE IF NOT EXISTS calls (id TEXT PRIMARY KEY, data TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS checkpoints (id TEXT PRIMARY KEY REFERENCES tasks(id), data TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS messages (id TEXT PRIMARY KEY, room_id TEXT NOT NULL REFERENCES rooms(id), channel TEXT NOT NULL, data TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS private_messages (id TEXT PRIMARY KEY, room_id TEXT NOT NULL REFERENCES rooms(id), sender_id TEXT NOT NULL REFERENCES tasks(id), recipient_id TEXT NOT NULL REFERENCES tasks(id), data TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS directions (id TEXT PRIMARY KEY, room_id TEXT NOT NULL REFERENCES rooms(id), data TEXT NOT NULL)")
            db.execute("PRAGMA user_version=1")
            db.commit()
        finally:
            db.close()

    @contextmanager
    def _transaction(self, write=False):
        # No connection is shared, even between two methods on one Store.
        db = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        try:
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def _json(value):
        try:
            return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)
        except (TypeError, ValueError, OverflowError, RecursionError) as exc:
            raise ValueError("Domain data must be finite JSON-serializable values") from exc

    @staticmethod
    def _get(db, table, identifier):
        Store._text(identifier, f"{table} id")
        row = db.execute(f"SELECT data FROM {table} WHERE id=?", (identifier,)).fetchone()
        if row is None:
            raise ValueError(f"Unknown {table} id: {identifier}")
        return json.loads(row[0])

    @staticmethod
    def _now():
        return datetime.now(timezone.utc).isoformat()

    def _event(self, db, room_id, kind, payload, task_id=None, run_id=None, dedupe_key=None):
        self._text(kind, "event kind")
        if not isinstance(payload, dict):
            raise ValueError("event payload must be a dict")
        if dedupe_key is not None:
            self._text(dedupe_key, "dedupe_key")
            row = db.execute("SELECT seq,data FROM events WHERE room_id=? AND dedupe_key=?", (room_id, dedupe_key)).fetchone()
            if row:
                old = json.loads(row[1])
                if (old["kind"], old["payload"], old["task_id"], old["run_id"]) != (kind, payload, task_id, run_id):
                    raise ValueError("dedupe_key already refers to different event content")
                return dict(old, seq=row[0])
        event = dict(room_id=room_id, kind=kind, payload=payload, task_id=task_id,
                     run_id=run_id, dedupe_key=dedupe_key, timestamp=self._now())
        cur = db.execute("INSERT INTO events(room_id,dedupe_key,data) VALUES (?,?,?)", (room_id, dedupe_key, self._json(event)))
        return dict(json.loads(self._json(event)), seq=cur.lastrowid)

    def add_event(self, room_id, kind, payload, task_id=None, run_id=None, dedupe_key=None):
        with self._transaction(write=True) as db:
            self._get(db, "rooms", room_id)
            if run_id is not None:
                run = self._get(db, "runs", run_id)
                if run["room_id"] != room_id or (task_id is not None and run["task_id"] != task_id):
                    raise ValueError("Event run/task ownership mismatch")
                task_id = run["task_id"]
                task = self._get(db, "tasks", task_id)
                if task["generation"] != run["generation"] or run["state"] in self._TERMINAL_RUNS:
                    raise PermissionError("Fenced or terminal runs cannot append current output")
            if task_id is not None:
                task = self._get(db, "tasks", task_id)
                if task["room_id"] != room_id:
                    raise ValueError("Event task belongs to another room")
                if task["state"] in self._FROZEN_TASKS:
                    raise PermissionError("Frozen tasks cannot append output")
                if isinstance(payload, dict) and "generation" in payload:
                    self._generation(task, payload["generation"])
            return self._event(db, room_id, kind, payload, task_id, run_id, dedupe_key)

    def events(self, room_id, after=0):
        self._nonnegative(after, "after")
        with self._transaction() as db:
            self._get(db, "rooms", room_id)
            return [dict(json.loads(row[1]), seq=row[0]) for row in db.execute("SELECT seq,data FROM events WHERE room_id=? AND seq>? ORDER BY seq", (room_id, after))]

    @staticmethod
    def _text(value, name, allow_empty=False):
        if not isinstance(value, str) or (not allow_empty and not value.strip()):
            raise ValueError(f"{name} must be {'a string' if allow_empty else 'a nonempty string'}")
        return value

    @staticmethod
    def _nonnegative(value, name):
        if type(value) is not int or value < 0 or value > 9223372036854775807:
            raise ValueError(f"{name} must be a nonnegative 64-bit integer")
        return value

    @classmethod
    def _route(cls, route):
        allowed = {"provider", "model", "base_url", "api_mode", "key_env",
                   "timeout_seconds", "max_output_tokens"}
        if not isinstance(route, dict) or set(route) - allowed:
            raise ValueError("Route must contain only non-secret supported settings")
        cls._text(route.get("provider"), "provider")
        cls._text(route.get("model"), "model")
        if "base_url" in route:
            url = urlsplit(cls._text(route["base_url"], "base_url"))
            if url.scheme not in {"http", "https"} or not url.netloc or url.username or url.password or url.query or url.fragment:
                raise ValueError("base_url must be an explicit HTTP(S) endpoint without credentials")
        if "key_env" in route and not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", cls._text(route["key_env"], "key_env")):
            raise ValueError("key_env must be an environment-variable name, not a credential")
        if "api_mode" in route and route["api_mode"] not in ("openai", "anthropic"):
            raise ValueError("Unknown api_mode")
        if "timeout_seconds" in route:
            timeout = route["timeout_seconds"]
            if type(timeout) not in {int, float} or not math.isfinite(timeout) or timeout <= 0:
                raise ValueError("timeout_seconds must be finite and positive")
        if "max_output_tokens" in route and cls._nonnegative(route["max_output_tokens"], "max_output_tokens") == 0:
            raise ValueError("max_output_tokens must be positive")
        return json.loads(cls._json(route))

    def create_room(self, title, director_route, worker_routes,
                    authorization_id="test-20261017", token_limit=1500000):
        self._text(title, "title")
        self._text(authorization_id, "authorization_id")
        self._nonnegative(token_limit, "token_limit")
        director_route = self._route(director_route)
        if not isinstance(worker_routes, list):
            raise ValueError("worker_routes must be a list")
        worker_routes = [self._route(route) for route in worker_routes]
        room = dict(id=str(uuid4()), title=title, director_route=director_route,
                    worker_routes=worker_routes, authorization_id=authorization_id,
                    token_limit=token_limit)
        with self._transaction(write=True) as db:
            for route in worker_routes:
                prior = db.execute("SELECT token_limit FROM allowances WHERE authorization_id=? AND provider=? AND model=? AND unlimited=0", (authorization_id, route["provider"], route["model"])).fetchone()
                if prior is not None and prior[0] != token_limit:
                    raise PermissionError("An existing authorization limit is immutable; a new room cannot change it")
                db.execute("INSERT OR IGNORE INTO allowances(authorization_id,provider,model,unlimited,token_limit) VALUES (?,?,?,0,?)", (authorization_id, route["provider"], route["model"], token_limit))
            db.execute("INSERT OR IGNORE INTO allowances(authorization_id,provider,model,unlimited,token_limit) VALUES (?,?,?,1,NULL)", (authorization_id, director_route["provider"], director_route["model"]))
            db.execute("INSERT INTO rooms(id,data) VALUES (?,?)", (room["id"], self._json(room)))
            self._event(db, room["id"], "room_created", {"title": title})
        return json.loads(self._json(room))

    def rooms(self):
        with self._transaction() as db:
            return [json.loads(row[0]) for row in db.execute("SELECT data FROM rooms ORDER BY rowid")]

    def room(self, room_id):
        with self._transaction() as db:
            return self._get(db, "rooms", room_id)

    def create_task(self, room_id, title, instructions, route, role="worker", parents=None, parent_id=None):
        self._text(title, "title")
        self._text(instructions, "instructions", allow_empty=True)
        if role not in ("director", "worker", "reviewer", "subdirector"):
            raise ValueError("Unknown task role")
        if parents is None:
            parents = []
        if not isinstance(parents, list) or any(not isinstance(p, str) for p in parents) or len(set(parents)) != len(parents):
            raise ValueError("parents must be distinct task IDs")
        task = dict(id=str(uuid4()), room_id=room_id, title=title, instructions=instructions,
                    route=self._route(route), role=role, parents=list(parents),
                    parent_id=parent_id, state="ready", version=1, generation=0)
        with self._transaction(write=True) as db:
            room = self._get(db, "rooms", room_id)
            for identifier in parents + ([parent_id] if parent_id is not None else []):
                if self._get(db, "tasks", identifier)["room_id"] != room_id:
                    raise ValueError("Task dependencies and hierarchy must belong to this room")
            if role == "director":
                if parents or parent_id or task["route"] != room["director_route"] or db.execute("SELECT 1 FROM roots WHERE room_id=?", (room_id,)).fetchone():
                    raise PermissionError("Only one parentless root director on the room's director route is allowed")
            elif task["route"] not in room["worker_routes"]:
                raise PermissionError("Worker route is not authorized for this room")
            db.execute("INSERT INTO tasks(id,room_id,data) VALUES (?,?,?)", (task["id"], room_id, self._json(task)))
            if role == "director":
                db.execute("INSERT INTO roots(room_id,task_id) VALUES (?,?)", (room_id, task["id"]))
            self._event(db, room_id, "task_created", task, task_id=task["id"])
        return task

    def start_run(self, task_id):
        with self._transaction(write=True) as db:
            task = self._get(db, "tasks", task_id)
            if task["state"] != "ready":
                raise ValueError("Only ready tasks may start")
            for identifier in task["parents"]:
                parent = self._get(db, "tasks", identifier)
                if parent["state"] != "done":
                    raise ValueError("Task is waiting for a verified dependency")
            if task["role"] == "subdirector":
                if task["parent_id"] is None:
                    raise PermissionError("Subdirectors require the room's root director as parent")
                parent = self._get(db, "tasks", task["parent_id"])
                root = db.execute("SELECT task_id FROM roots WHERE room_id=?", (task["room_id"],)).fetchone()
                if root is None or parent["id"] != root[0]:
                    raise PermissionError("Only one subdirector level is permitted")
            active = [json.loads(row[0]) for row in db.execute("SELECT data FROM runs")]
            active = [run for run in active if run["state"] not in self._TERMINAL_RUNS]
            if any(run["task_id"] == task_id for run in active):
                raise ValueError("An owned run is still active; confirm its exit before restarting")
            root = db.execute("SELECT task_id FROM roots WHERE room_id=?", (task["room_id"],)).fetchone()
            is_root = root is not None and root[0] == task_id
            if not is_root and root is not None and not self._director_available(db, task["room_id"]):
                raise PermissionError("New dispatch is paused while the root director is stopped")
            root_ids = {row[0] for row in db.execute("SELECT task_id FROM roots")}
            if not is_root and sum(run["task_id"] not in root_ids for run in active) >= 3:
                raise ValueError("The Store permits at most three active work runs")
            task["generation"] += 1
            task["state"] = "running"
            now = self._now()
            run = dict(id=str(uuid4()), task_id=task_id, room_id=task["room_id"],
                       generation=task["generation"], route=task["route"], role=task["role"],
                       state="running", started_at=now, heartbeat_at=now)
            db.execute("INSERT INTO runs(id,task_id,room_id,data) VALUES (?,?,?,?)", (run["id"], task_id, task["room_id"], self._json(run)))
            self._save(db, "tasks", task)
            self._event(db, task["room_id"], "run_started", run, task_id, run["id"])
            return run

    def run(self, run_id):
        with self._transaction() as db:
            return self._get(db, "runs", run_id)

    def update_run(self, run_id, changes):
        allowed = {"state", "pid", "start_fingerprint", "heartbeat_at", "activity", "error"}
        states = {"running", "preparing", "waiting_model", "tool_running", "stopping", "interrupted", "exited", "failed", "cancelled", "stopped", "completed"}
        if not isinstance(changes, dict) or set(changes) - allowed:
            raise PermissionError("Run identity, generation, route and role are protected")
        if "state" in changes and (not isinstance(changes["state"], str) or changes["state"] not in states):
            raise ValueError("Unknown run state")
        with self._transaction(write=True) as db:
            run = self._get(db, "runs", run_id)
            task = self._get(db, "tasks", run["task_id"])
            if run["state"] in self._TERMINAL_RUNS and (set(changes) - {"state", "error"} or changes.get("state", run["state"]) not in self._TERMINAL_RUNS):
                raise PermissionError("A terminal run cannot be resurrected; start a fresh generation")
            fenced = task["generation"] != run["generation"] or task["state"] in self._FROZEN_TASKS
            if fenced and (set(changes) - {"state", "error"} or changes.get("state") not in self._TERMINAL_RUNS):
                raise PermissionError("A fenced run may record termination only")
            run.update(changes)
            self._save(db, "runs", run)
            self._event(db, run["room_id"], "run_updated", {"changes": changes, "generation": run["generation"]}, run["task_id"], run_id)
            return run

    def task(self, task_id):
        with self._transaction() as db:
            return self._get(db, "tasks", task_id)

    def stop_branch(self, task_id):
        with self._transaction(write=True) as db:
            selected = self._get(db, "tasks", task_id)
            tasks = [json.loads(row[0]) for row in db.execute("SELECT data FROM tasks WHERE room_id=? ORDER BY rowid", (selected["room_id"],))]
            affected = {task_id}
            while True:
                more = {task["id"] for task in tasks if affected.intersection(task["parents"])}
                if more <= affected:
                    break
                affected.update(more)
            result = []
            for task in tasks:
                if task["id"] not in affected:
                    continue
                result.append(task["id"])
                task["generation"] += 1
                task["state"] = "stopped" if task["id"] == task_id or task["state"] == "stopped" else "waiting_dependency"
                self._save(db, "tasks", task)
                for row in db.execute("SELECT data FROM runs WHERE task_id=?", (task["id"],)).fetchall():
                    run = json.loads(row[0])
                    if run["state"] not in self._TERMINAL_RUNS:
                        run["state"] = "stopping"
                        self._save(db, "runs", run)
                self._event(db, task["room_id"], "task_stopped" if task["id"] == task_id else "task_dependency_frozen", {"generation": task["generation"], "source_task_id": task_id}, task_id=task["id"])
            return result

    def _allowance(self, db, authorization_id, provider, model, unlimited=False):
        row = db.execute("SELECT token_limit FROM allowances WHERE authorization_id=? AND provider=? AND model=? AND unlimited=?", (authorization_id, provider, model, int(unlimited))).fetchone()
        if row is None:
            raise PermissionError("No allowance exists for this authorization/provider/model")
        return row[0]

    def _ledger_totals(self, db, authorization_id, provider, model, unlimited=False):
        calls = [json.loads(row[0]) for row in db.execute("SELECT data FROM calls")]
        calls = [call for call in calls if (call["authorization_id"], call["provider"], call["model"], call["unlimited"]) == (authorization_id, provider, model, unlimited)]
        spent = sum(call["total_tokens"] for call in calls if call["state"] == "settled")
        reserved = sum(call["tokens"] for call in calls if call["state"] != "settled")
        unknown = sum(call["tokens"] for call in calls if call["state"] == "unresolved")
        return dict(spent=spent, reserved=reserved, unknown=unknown)

    def reserve(self, call_id, task_id, tokens):
        self._text(call_id, "call_id")
        self._nonnegative(tokens, "tokens")
        with self._transaction(write=True) as db:
            task = self._get(db, "tasks", task_id)
            room = self._get(db, "rooms", task["room_id"])
            if task["state"] not in {"ready", "running"}:
                raise PermissionError("Only an authorized ready/running task may reserve tokens")
            if any(self._get(db, "tasks", identifier)["state"] != "done" for identifier in task["parents"]):
                raise PermissionError("Waiting dependencies cannot obtain provider-call reservations")
            root = db.execute("SELECT task_id FROM roots WHERE room_id=?", (task["room_id"],)).fetchone()
            if task["state"] == "ready" and root is not None and root[0] != task_id and not self._director_available(db, task["room_id"]):
                raise PermissionError("Ready reservations cannot bypass paused dispatch")
            prior = db.execute("SELECT data FROM calls WHERE id=?", (call_id,)).fetchone()
            if prior is not None:
                prior = json.loads(prior[0])
                if prior["generation"] != task["generation"]:
                    raise ValueError("Call ID belongs to a fenced task generation")
                if prior["task_id"] != task_id or prior["tokens"] != tokens:
                    raise ValueError("Call ID already belongs to a different reservation")
                return prior
            provider, model = task["route"]["provider"], task["route"]["model"]
            root = db.execute("SELECT task_id FROM roots WHERE room_id=?", (task["room_id"],)).fetchone()
            unlimited = root is not None and root[0] == task_id
            limit = self._allowance(db, room["authorization_id"], provider, model, unlimited)
            totals = self._ledger_totals(db, room["authorization_id"], provider, model, unlimited)
            if not unlimited and totals["spent"] + totals["reserved"] + tokens > limit:
                raise ValueError("Insufficient shared token allowance")
            call = dict(id=call_id, call_id=call_id, task_id=task_id, room_id=task["room_id"],
                        generation=task["generation"], authorization_id=room["authorization_id"],
                        provider=provider, model=model, unlimited=unlimited, tokens=tokens,
                        total_tokens=None, state="reserved", details=None, timestamp=self._now())
            db.execute("INSERT INTO calls(id,data) VALUES (?,?)", (call_id, self._json(call)))
            self._event(db, task["room_id"], "tokens_reserved", {"call_id": call_id, "tokens": tokens}, task_id=task_id)
            return call

    def settle(self, call_id, total_tokens, details=None):
        if total_tokens is not None:
            self._nonnegative(total_tokens, "total_tokens")
        if details is not None and not isinstance(details, dict):
            raise ValueError("details must be a dict")
        with self._transaction(write=True) as db:
            call = self._get(db, "calls", call_id)
            if call["state"] == "settled":
                if call["total_tokens"] != total_tokens:
                    raise ValueError("A settled call cannot be settled twice with different usage")
                return call
            if total_tokens is None:
                if call["state"] == "unresolved":
                    return call
                call.update(state="unresolved", details=details, unresolved_at=self._now())
            else:
                call.update(total_tokens=total_tokens, state="settled", details=details, settled_at=self._now())
            self._save(db, "calls", call)
            self._event(db, call["room_id"], "tokens_unresolved" if total_tokens is None else "tokens_settled", {"call_id": call_id, "total_tokens": total_tokens}, task_id=call["task_id"])
            return call

    def _budget_summary(self, db, room):
        result = []
        keys = {(route["provider"], route["model"], False) for route in room["worker_routes"]}
        keys.add((room["director_route"]["provider"], room["director_route"]["model"], True))
        for provider, model, unlimited in sorted(keys):
            limit = self._allowance(db, room["authorization_id"], provider, model, unlimited)
            result.append(dict(provider=provider, model=model, limit=limit, unlimited=unlimited,
                               authorization_id=room["authorization_id"],
                               **self._ledger_totals(db, room["authorization_id"], provider, model, unlimited)))
        return result

    def budget_summary(self, room_id):
        with self._transaction() as db:
            return self._budget_summary(db, self._get(db, "rooms", room_id))

    def checkpoint(self, task_id, data, expected_generation=None):
        if not isinstance(data, dict):
            raise ValueError("checkpoint data must be a dict")
        with self._transaction(write=True) as db:
            task = self._get(db, "tasks", task_id)
            self._generation(task, expected_generation)
            if task["state"] in self._FROZEN_TASKS:
                raise PermissionError("A stopped or dependency-frozen task cannot write a checkpoint")
            self._require_incorporated_direction(db, task)
            event = self._event(db, task["room_id"], "checkpoint_saved", {"generation": task["generation"], "version": task["version"]}, task_id=task_id)
            point = dict(task_id=task_id, room_id=task["room_id"], generation=task["generation"],
                         version=task["version"], data=data, events_cursor=event["seq"],
                         cutoff=event["seq"], timestamp=event["timestamp"])
            db.execute("INSERT INTO checkpoints(id,data) VALUES (?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data", (task_id, self._json(point)))
            return json.loads(self._json(point))

    def get_checkpoint(self, task_id):
        with self._transaction() as db:
            self._get(db, "tasks", task_id)
            row = db.execute("SELECT data FROM checkpoints WHERE id=?", (task_id,)).fetchone()
            return json.loads(row[0]) if row else None

    def post_message(self, room_id, channel, author, text, task_id=None):
        if channel not in ("group", "director"):
            raise ValueError("Public messages use group or director; private messages require approval")
        self._text(author, "author")
        self._text(text, "text")
        with self._transaction(write=True) as db:
            self._get(db, "rooms", room_id)
            task = self._get(db, "tasks", task_id) if task_id is not None else None
            if task is not None:
                if task["room_id"] != room_id:
                    raise ValueError("Message task belongs to another room")
                if task["state"] in self._FROZEN_TASKS:
                    raise PermissionError("Frozen task cannot post messages")
            message = dict(id=str(uuid4()), room_id=room_id, channel=channel, author=author,
                           text=text, task_id=task_id, timestamp=self._now(),
                           role=task["role"] if task else "user", version=task["version"] if task else None,
                           generation=task["generation"] if task else None)
            db.execute("INSERT INTO messages(id,room_id,channel,data) VALUES (?,?,?,?)", (message["id"], room_id, channel, self._json(message)))
            self._event(db, room_id, "message_posted", {"message_id": message["id"], "channel": channel}, task_id=task_id)
            return message

    def messages(self, room_id, channel="group"):
        if channel not in ("group", "director"):
            raise ValueError("Unknown public channel")
        with self._transaction() as db:
            self._get(db, "rooms", room_id)
            return [json.loads(row[0]) for row in db.execute("SELECT data FROM messages WHERE room_id=? AND channel=? ORDER BY rowid", (room_id, channel))]

    @classmethod
    def _private_digest(cls, message):
        content = {key: message[key] for key in ("room_id", "sender_id", "recipient_id", "text", "attachments", "task_version", "recipient_version")}
        return hashlib.sha256(cls._json(content).encode("utf-8")).hexdigest()

    def _private_current(self, db, message):
        sender = self._get(db, "tasks", message["sender_id"])
        recipient = self._get(db, "tasks", message["recipient_id"])
        if sender["state"] in self._FROZEN_TASKS or recipient["state"] in self._FROZEN_TASKS:
            return False
        if sender["version"] != message["task_version"] or recipient["version"] != message["recipient_version"]:
            return False
        digest = self._private_digest(message)
        return digest == message["content_digest"] and (message["state"] != "approved" or digest == message.get("approved_digest"))

    def _director_available(self, db, room_id):
        root = db.execute("SELECT task_id FROM roots WHERE room_id=?", (room_id,)).fetchone()
        return root is not None and self._get(db, "tasks", root[0])["state"] not in self._FROZEN_TASKS

    @classmethod
    def _screen_private(cls, value):
        # Conservative engineering guard, not a secret-detection/security sandbox.
        if isinstance(value, dict):
            for key, item in value.items():
                if re.search(r"(?i)(?:api[_-]?key|access[_-]?token|client[_-]?secret|password|private[_-]?key)", str(key)):
                    raise PermissionError("Private content contains a credential-like field; nothing was sanitized or sent")
                cls._screen_private(str(key))
                cls._screen_private(item)
        elif isinstance(value, list):
            for item in value:
                cls._screen_private(item)
        elif isinstance(value, str):
            patterns = (
                r"(?i)(?:^|[\s/\\\"'])\.env(?:[.\s/\\\"']|$)",
                r"(?i)\b(?:SOUL|USER|MEMORY|IDENTITY)\.md\b|private\s+identity|私有身份记忆|id_(?:rsa|ed25519)",
                r"(?i)(?:api[_-]?key|access[_-]?token|client[_-]?secret|password|secret[_-]?key)\s*[\"']?\s*[:=]\s*\S+",
                r"(?i)\bbearer\s+[A-Za-z0-9._-]{8,}|\b(?:sk|rk|pk)[-_][A-Za-z0-9_-]{12,}",
                r"-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----",
            )
            if any(re.search(pattern, value) for pattern in patterns):
                raise PermissionError("Private content contains blocked credential/identity material; nothing was sanitized or sent")

    def propose_private(self, room_id, sender_id, recipient_id, text, attachments=None):
        self._text(text, "text")
        if attachments is None:
            attachments = []
        if not isinstance(attachments, list):
            raise ValueError("attachments must be a list")
        for attachment in attachments:
            if not isinstance(attachment, dict) or not isinstance(attachment.get("name"), str) or not isinstance(attachment.get("content"), str):
                raise ValueError("Private attachments must include name and full inline text content for prior review")
        self._screen_private(text)
        self._screen_private(attachments)
        with self._transaction(write=True) as db:
            self._get(db, "rooms", room_id)
            sender = self._get(db, "tasks", sender_id)
            recipient = self._get(db, "tasks", recipient_id)
            if sender["room_id"] != room_id or recipient["room_id"] != room_id or sender_id == recipient_id:
                raise ValueError("Private sender and recipient must be distinct tasks in this room")
            if sender["state"] in self._FROZEN_TASKS or recipient["state"] in self._FROZEN_TASKS:
                raise PermissionError("Frozen participants cannot propose private exchanges")
            message = dict(id=str(uuid4()), room_id=room_id, sender_id=sender_id, recipient_id=recipient_id,
                           text=text, attachments=attachments, task_version=sender["version"],
                           recipient_version=recipient["version"], state="pending", status="pending",
                           created_at=self._now(), decided_at=None, received_at=None, actor=None, reason="", decisions=[])
            message["content_digest"] = self._private_digest(message)
            prior = [json.loads(row[0]) for row in db.execute("SELECT data FROM private_messages WHERE room_id=? AND sender_id=?", (room_id, sender_id))]
            for old in prior:
                if old["content_digest"] == message["content_digest"]:
                    return old
            now = datetime.fromisoformat(message["created_at"])
            if sum((now - datetime.fromisoformat(old["created_at"])).total_seconds() < 60 for old in prior) >= 20:
                raise ValueError("Private sender rate limit is 20 distinct content packages per minute")
            db.execute("INSERT INTO private_messages(id,room_id,sender_id,recipient_id,data) VALUES (?,?,?,?,?)", (message["id"], room_id, sender_id, recipient_id, self._json(message)))
            self._event(db, room_id, "private_proposed", {"message_id": message["id"], "content_digest": message["content_digest"]}, task_id=sender_id)
            return json.loads(self._json(message))

    def decide_private(self, message_id, decision, reason="", actor="director"):
        if decision not in ("approved", "rejected", "escalated"):
            raise ValueError("Unknown private decision")
        self._text(actor, "actor")
        self._text(reason, "reason", allow_empty=True)
        with self._transaction(write=True) as db:
            message = self._get(db, "private_messages", message_id)
            root = db.execute("SELECT task_id FROM roots WHERE room_id=?", (message["room_id"],)).fetchone()
            if actor != "user" and (root is None or actor not in {"director", root[0]}):
                raise PermissionError("Only user or the verified room root director can decide private messages")
            if actor != "user" and not self._director_available(db, message["room_id"]):
                raise PermissionError("Stopped root director cannot grant private approval")
            if message["state"] in {"approved", "rejected"}:
                if message["state"] == decision and message["actor"] == actor and message["reason"] == reason:
                    return message
                raise ValueError("Final approval/rejection is immutable; propose a new content package")
            if message["state"] == "escalated" and actor != "user":
                raise PermissionError("Only the user can resolve an escalated decision")
            if decision == "approved" and not self._private_current(db, message):
                raise ValueError("Private approval is bound to exact content and both current task versions")
            message.update(state=decision, status=decision, reason=reason, actor=actor, decided_at=self._now())
            message["decisions"].append(dict(decision=decision, reason=reason, actor=actor, timestamp=message["decided_at"]))
            if decision == "approved":
                message["approved_digest"] = message["content_digest"]
            self._save(db, "private_messages", message)
            self._event(db, message["room_id"], "private_decided", {"message_id": message_id, "decision": decision, "actor": actor, "reason": reason})
            return message

    def inbox(self, task_id, include_received=False):
        with self._transaction() as db:
            task = self._get(db, "tasks", task_id)
            if not self._director_available(db, task["room_id"]):
                return []
            messages = [json.loads(row[0]) for row in db.execute("SELECT data FROM private_messages WHERE recipient_id=? ORDER BY rowid", (task_id,))]
            return [message for message in messages if message["state"] == "approved" and (include_received or message["received_at"] is None) and self._private_current(db, message)]

    def private_messages(self, room_id):
        with self._transaction() as db:
            self._get(db, "rooms", room_id)
            return [json.loads(row[0]) for row in db.execute("SELECT data FROM private_messages WHERE room_id=? ORDER BY rowid", (room_id,))]

    def ack_private(self, message_id, recipient_id):
        with self._transaction(write=True) as db:
            message = self._get(db, "private_messages", message_id)
            if message["recipient_id"] != recipient_id:
                raise PermissionError("Only the addressed recipient may acknowledge receipt")
            if message["state"] != "approved":
                raise PermissionError("Unapproved private content cannot be delivered")
            if message["received_at"] is not None:
                return message
            if not self._director_available(db, message["room_id"]):
                raise PermissionError("Private delivery is paused while the root director is unavailable")
            if any(self._get(db, "tasks", identifier)["state"] in self._FROZEN_TASKS for identifier in (message["sender_id"], recipient_id)):
                raise PermissionError("Frozen private participants cannot confirm delivery")
            if not self._private_current(db, message):
                raise ValueError("Stale or changed private content cannot be acknowledged")
            message["received_at"] = self._now()
            self._save(db, "private_messages", message)
            self._event(db, message["room_id"], "private_received", {"message_id": message_id, "recipient_id": recipient_id}, task_id=recipient_id)
            return message

    def add_direction(self, room_id, text, mode="director"):
        self._text(text, "direction text")
        if mode not in ("director", "broadcast"):
            raise ValueError("Direction mode must be director or broadcast")
        with self._transaction(write=True) as db:
            self._get(db, "rooms", room_id)
            tasks = [json.loads(row[0]) for row in db.execute("SELECT data FROM tasks WHERE room_id=? ORDER BY rowid", (room_id,))]
            root = db.execute("SELECT task_id FROM roots WHERE room_id=?", (room_id,)).fetchone()
            if mode == "director":
                tasks = [task for task in tasks if root is not None and task["id"] == root[0]]
            acknowledgments = {}
            for task in tasks:
                self._archive_outcome(task)
                task["version"] += 1
                task["latest_direction"] = text
                self._save(db, "tasks", task)
                acknowledgments[task["id"]] = dict(status="pending", version=task["version"],
                    generation=task["generation"], delivered_at=None, incorporated_at=None)
            direction = dict(id=str(uuid4()), room_id=room_id, text=text, mode=mode,
                             status="pending", created_at=self._now(), acknowledgments=acknowledgments)
            db.execute("INSERT INTO directions(id,room_id,data) VALUES (?,?,?)", (direction["id"], room_id, self._json(direction)))
            self._event(db, room_id, "direction_enqueued", {"direction_id": direction["id"], "mode": mode, "recipients": list(acknowledgments)})
            return direction

    def pending_directions(self, task_id, include_delivered=False):
        with self._transaction() as db:
            task = self._get(db, "tasks", task_id)
            if task["state"] in self._FROZEN_TASKS:
                return []
            directions = [json.loads(row[0]) for row in db.execute("SELECT data FROM directions WHERE room_id=? ORDER BY rowid", (task["room_id"],))]
            statuses = {"pending", "delivered"} if include_delivered else {"pending"}
            return [direction for direction in directions if direction["acknowledgments"].get(task_id, {}).get("status") in statuses and direction["acknowledgments"][task_id]["version"] == task["version"]]

    def ack_direction(self, direction_id, task_id, status="delivered"):
        if status not in ("delivered", "incorporated"):
            raise ValueError("Direction receipt must be delivered or incorporated")
        with self._transaction(write=True) as db:
            direction = self._get(db, "directions", direction_id)
            task = self._get(db, "tasks", task_id)
            if task["room_id"] != direction["room_id"] or task_id not in direction["acknowledgments"]:
                raise PermissionError("Task is not an addressed direction recipient")
            if task["state"] in self._FROZEN_TASKS:
                raise PermissionError("Frozen tasks cannot acknowledge directions")
            ack = direction["acknowledgments"][task_id]
            if ack["version"] != task["version"]:
                raise ValueError("Receipt is for a superseded task direction version")
            if ack["status"] == status:
                return direction
            if (ack["status"], status) not in {("pending", "delivered"), ("delivered", "incorporated")}:
                raise ValueError("Receipts must advance pending -> delivered -> incorporated")
            ack["status"] = status
            ack["generation"] = task["generation"]
            now = self._now()
            if status == "delivered":
                ack["delivered_at"] = now
            else:
                ack["incorporated_at"] = now
            statuses = {item["status"] for item in direction["acknowledgments"].values()}
            direction["status"] = "incorporated" if statuses == {"incorporated"} else "delivered" if "pending" not in statuses else "pending"
            self._save(db, "directions", direction)
            self._event(db, task["room_id"], "direction_acknowledged", {"direction_id": direction_id, "status": status}, task_id=task_id)
            return direction

    def snapshot(self, room_id):
        # Read everything through one transaction: cursor and data describe the
        # same database state even when worker threads commit concurrently.
        with self._transaction() as db:
            room = self._get(db, "rooms", room_id)
            result = dict(room=room)
            for table in ("tasks", "runs", "messages", "private_messages", "directions"):
                result[table] = [json.loads(row[0]) for row in db.execute(f"SELECT data FROM {table} WHERE room_id=? ORDER BY rowid", (room_id,))]
            result["budgets"] = self._budget_summary(db, room)
            result["events_cursor"] = db.execute("SELECT COALESCE(MAX(seq),0) FROM events WHERE room_id=?", (room_id,)).fetchone()[0]
            return result

    @staticmethod
    def _archive_outcome(task):
        outcome = {key: task.pop(key) for key in ("result", "artifacts", "evidence") if key in task}
        if outcome:
            task.setdefault("historical_results", []).append(dict(version=task["version"], generation=task["generation"], **outcome))

    def _require_incorporated_direction(self, db, task):
        for row in db.execute("SELECT data FROM directions WHERE room_id=?", (task["room_id"],)):
            ack = json.loads(row[0])["acknowledgments"].get(task["id"])
            if ack and ack["version"] == task["version"] and ack["status"] != "incorporated":
                raise ValueError("Current direction has not been incorporated; older output cannot become a current result")

    def resume_task(self, task_id, instructions=None, route=None, user_confirmed=False):
        if user_confirmed is not True:
            raise PermissionError("Explicit user confirmation is required")
        if instructions is not None:
            self._text(instructions, "instructions", allow_empty=True)
        if route is not None:
            route = self._route(route)
        with self._transaction(write=True) as db:
            task = self._get(db, "tasks", task_id)
            if task["state"] == "running":
                raise ValueError("Stop the active task before resuming or changing its direction")
            room = self._get(db, "rooms", task["room_id"])
            if route is not None:
                choices = [room["director_route"]] if task["role"] == "director" else room["worker_routes"]
                if route not in choices:
                    raise PermissionError("Route is not authorized; resuming cannot create a new allowance")
            changed = (instructions is not None and instructions != task["instructions"]) or (route is not None and route != task["route"])
            if instructions is not None:
                task["instructions"] = instructions
                task["latest_direction"] = instructions
            if route is not None:
                task["route"] = route
            if changed:
                self._archive_outcome(task)
                task["version"] += 1
            task["generation"] += 1
            task["state"] = "ready"
            task["metadata"] = dict(task.get("metadata", {}), awaiting_user=False)
            self._save(db, "tasks", task)
            self._event(db, task["room_id"], "task_resumed", {"generation": task["generation"], "version": task["version"], "direction_changed": changed}, task_id=task_id)
            return task

    def _save(self, db, table, value):
        db.execute(f"UPDATE {table} SET data=? WHERE id=?", (self._json(value), value["id"]))

    @staticmethod
    def _generation(task, expected):
        if expected is not None and (type(expected) is not int or expected != task["generation"]):
            raise ValueError("Stale task generation")

    def update_task(self, task_id, changes, expected_generation=None):
        allowed = {"title", "state", "progress", "result", "artifacts", "evidence", "error", "health", "activity", "metadata"}
        if not isinstance(changes, dict) or set(changes) - allowed:
            raise PermissionError("Task identity, graph, role, route, instructions and generations are protected")
        if "state" in changes and changes["state"] not in ("ready", "waiting_user", "paused", "handoff_ready", "pending_review", "done", "failed", "unknown", "waiting_budget", "clarification"):
            raise ValueError("State must be a task state; use start_run or stop_branch for control")
        with self._transaction(write=True) as db:
            task = self._get(db, "tasks", task_id)
            self._generation(task, expected_generation)
            if task["state"] in self._FROZEN_TASKS:
                raise PermissionError("Frozen tasks require explicit confirmed resume")
            if set(changes).intersection({"result", "artifacts", "evidence"}) or changes.get("state") in ("done", "pending_review", "handoff_ready"):
                self._require_incorporated_direction(db, task)
            task.update(changes)
            self._save(db, "tasks", task)
            self._event(db, task["room_id"], "task_updated", {"changes": changes, "generation": task["generation"]}, task_id=task_id)
        return task
