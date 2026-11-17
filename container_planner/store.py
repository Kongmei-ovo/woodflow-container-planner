from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


def now():
    return datetime.now(timezone.utc).isoformat()


def uid():
    return uuid.uuid4().hex


class Conflict(ValueError):
    pass


class Store:
    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        for sub in ("originals", "exports"):
            (self.root / sub).mkdir(exist_ok=True)
        self.path = self.root / "planner.sqlite3"
        with self.connection() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS records (
                    kind TEXT NOT NULL, id TEXT NOT NULL, data TEXT NOT NULL,
                    revision INTEGER NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    PRIMARY KEY(kind,id));
                CREATE TABLE IF NOT EXISTS audit (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT, time TEXT NOT NULL,
                    kind TEXT NOT NULL, id TEXT NOT NULL, action TEXT NOT NULL,
                    before_data TEXT, after_data TEXT);
                PRAGMA user_version=1;
            """)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def decode(row):
        if row is None:
            return None
        return {**json.loads(row["data"]), "id": row["id"], "revision": row["revision"],
                "created_at": row["created_at"], "updated_at": row["updated_at"]}

    def get(self, kind, id):
        with self.connection() as db:
            row = db.execute("SELECT * FROM records WHERE kind=? AND id=?", (kind, id)).fetchone()
        if row is None:
            raise KeyError(f"找不到记录：{kind}/{id}")
        return self.decode(row)

    def list(self, kind):
        with self.connection() as db:
            rows = db.execute("SELECT * FROM records WHERE kind=? ORDER BY created_at,id", (kind,)).fetchall()
        return [self.decode(r) for r in rows]

    def put(self, kind, data, id=None, expected=None, action="保存"):
        return self.put_many([(kind, data, id, expected, action)])[0]

    def put_many(self, items):
        """Commit business records and their audit entries atomically."""
        result = []
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            for kind, data, id, expected, action in items:
                id = id or uid()
                old = db.execute("SELECT * FROM records WHERE kind=? AND id=?", (kind, id)).fetchone()
                if expected is not None and (old is None or old["revision"] != expected):
                    raise Conflict("记录已更新，请刷新后再保存，避免覆盖其他修改。")
                clean = {k: v for k, v in data.items() if k not in ("id", "revision", "created_at", "updated_at")}
                raw = json.dumps(clean, ensure_ascii=False, allow_nan=False)
                stamp = now()
                rev = old["revision"] + 1 if old else 1
                created = old["created_at"] if old else stamp
                db.execute("INSERT OR REPLACE INTO records VALUES(?,?,?,?,?,?)",
                           (kind, id, raw, rev, created, stamp))
                before = json.loads(old["data"]) if old else None
                after = clean
                if kind == "project" and before:
                    previous_lines = {line["id"]: line for line in before.get("lines", [])}
                    changed_lines = [line for line in clean.get("lines", []) if line != previous_lines.get(line["id"])]
                    fields = ("name", "customer", "notes", "deleted_at")
                    before = {**{k: before.get(k) for k in fields}, "lines": [previous_lines[l["id"]] for l in changed_lines if l["id"] in previous_lines]}
                    after = {**{k: clean.get(k) for k in fields}, "lines": changed_lines}
                elif kind in {"job", "plan"}:
                    # Inputs are already preserved in immutable plan/job records.
                    before = {k: v for k, v in before.items() if k not in {"snapshot", "locked", "containers"}} if before else None
                    after = {k: v for k, v in clean.items() if k not in {"snapshot", "locked", "containers"}}
                db.execute("INSERT INTO audit(time,kind,id,action,before_data,after_data) VALUES(?,?,?,?,?,?)",
                           (stamp, kind, id, action, json.dumps(before, ensure_ascii=False) if before else None,
                            json.dumps(after, ensure_ascii=False)))
                result.append({**clean, "id": id, "revision": rev, "created_at": created, "updated_at": stamp})
        return result

    def history(self, kind=None, id=None):
        with self.connection() as db:
            rows = db.execute("SELECT seq,time,kind,id,action,before_data,after_data FROM audit "
                              "WHERE (? IS NULL OR kind=?) AND (? IS NULL OR id=?) ORDER BY seq DESC LIMIT 300",
                              (kind, kind, id, id)).fetchall()
        return [dict(r) for r in rows]
