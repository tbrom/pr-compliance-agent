"""
Persistent history store for Sentinel PR verdicts.

The Copilot chat endpoint needs to recall earlier verdicts so developers can
ask follow-up questions ("why was my PR blocked?"). The original implementation
kept an in-process dict which did not survive restarts and broke under
horizontal scaling.

This module provides a thin abstraction with a SQLite default implementation.
The backend is swappable via the `SENTINEL_HISTORY_BACKEND` env var. For GCP
production we can add a Firestore implementation behind the same interface
without touching the callers.

Design notes
------------
- The table uses (repo, pr_id) as a natural primary key with upsert semantics:
  re-running Sentinel on a PR update replaces the prior verdict rather than
  accumulating rows. `updated_at` is refreshed on every write.
- `get_latest(repo)` is used by the Copilot endpoint when the chat payload
  does not carry a specific PR reference.
- Schema is intentionally small; payload fields are stored as JSON in a single
  text column so evolving the verdict shape does not require migrations.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
from typing import Any, Optional, Protocol
from urllib.parse import quote

logger = logging.getLogger("sentinel")


class HistoryStore(Protocol):
    def put(self, repo: str, pr_id: int, payload: dict[str, Any]) -> None: ...
    def get(self, repo: str, pr_id: int) -> Optional[dict[str, Any]]: ...
    def get_latest(self, repo: str) -> Optional[dict[str, Any]]: ...


class SQLiteHistoryStore:
    """File-backed history store. Suitable for single-node deployments.

    On Cloud Run with multiple replicas the local filesystem is per-instance,
    so verdicts written by one replica are invisible to others. Swap to a
    Firestore/Cloud SQL backend for multi-replica production use.
    """

    _SCHEMA = """
        CREATE TABLE IF NOT EXISTS sentinel_history (
            repo        TEXT NOT NULL,
            pr_id       INTEGER NOT NULL,
            payload     TEXT NOT NULL,
            updated_at  REAL NOT NULL,
            PRIMARY KEY (repo, pr_id)
        );
        CREATE INDEX IF NOT EXISTS idx_repo_updated
            ON sentinel_history (repo, updated_at DESC);
    """

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._lock = threading.Lock()
        # `check_same_thread=False` so the single connection can serve the
        # FastAPI worker threads. The lock above serialises access.
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(self._SCHEMA)
            self._conn.commit()
        logger.info("📚 History store: SQLite at %s", db_path)

    def put(self, repo: str, pr_id: int, payload: dict[str, Any]) -> None:
        blob = json.dumps(payload, default=str)
        now = time.time()
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO sentinel_history (repo, pr_id, payload, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(repo, pr_id) DO UPDATE SET
                    payload = excluded.payload,
                    updated_at = excluded.updated_at
                """,
                (repo, pr_id, blob, now),
            )
            self._conn.commit()

    def get(self, repo: str, pr_id: int) -> Optional[dict[str, Any]]:
        with self._lock:
            row = self._conn.execute(
                "SELECT payload FROM sentinel_history WHERE repo = ? AND pr_id = ?",
                (repo, pr_id),
            ).fetchone()
        return json.loads(row["payload"]) if row else None

    def get_latest(self, repo: str) -> Optional[dict[str, Any]]:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT payload FROM sentinel_history
                WHERE repo = ?
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (repo,),
            ).fetchone()
        return json.loads(row["payload"]) if row else None

    def close(self) -> None:
        with self._lock:
            self._conn.close()


class FirestoreHistoryStore:
    """Firestore-backed history store for multi-replica Cloud Run deployments.

    Collection layout (flat):
        sentinel_history / {owner__repo__pr__NN}
            repo        : str   (indexed — used by get_latest)
            pr_id       : int
            payload     : map   (verdict blob, free-form)
            updated_at  : server timestamp (indexed DESCENDING)

    Requires a composite index on (repo ASC, updated_at DESC) for
    `get_latest`. The index is provisioned in terraform — Firestore will
    return FAILED_PRECONDITION until it is built.
    """

    def __init__(self, project: str, database: str, collection: str):
        # Imported lazily so SQLite users don't pay for a GCP-only dep.
        from google.cloud import firestore  # type: ignore

        self._firestore = firestore
        self.client = firestore.Client(project=project, database=database)
        self.collection_name = collection
        logger.info(
            "📚 History store: Firestore project=%s database=%s collection=%s",
            project, database, collection,
        )

    @staticmethod
    def _doc_id(repo: str, pr_id: int) -> str:
        # Firestore doc IDs cannot contain "/". Percent-encode the repo so the
        # slug is unambiguous even if repo names ever contain the separator
        # we'd otherwise pick (e.g. "__").
        return f"{quote(repo, safe='')}__pr__{pr_id}"

    def put(self, repo: str, pr_id: int, payload: dict[str, Any]) -> None:
        doc_id = self._doc_id(repo, pr_id)
        self.client.collection(self.collection_name).document(doc_id).set({
            "repo": repo,
            "pr_id": int(pr_id),
            "payload": payload,
            "updated_at": self._firestore.SERVER_TIMESTAMP,
        })

    def get(self, repo: str, pr_id: int) -> Optional[dict[str, Any]]:
        doc_id = self._doc_id(repo, pr_id)
        snap = self.client.collection(self.collection_name).document(doc_id).get()
        if not snap.exists:
            return None
        data = snap.to_dict() or {}
        return data.get("payload")

    def get_latest(self, repo: str) -> Optional[dict[str, Any]]:
        fs = self._firestore
        q = (
            self.client.collection(self.collection_name)
            .where(filter=fs.FieldFilter("repo", "==", repo))
            .order_by("updated_at", direction=fs.Query.DESCENDING)
            .limit(1)
        )
        for snap in q.stream():
            data = snap.to_dict() or {}
            return data.get("payload")
        return None

    def close(self) -> None:
        # google.cloud.firestore.Client manages its own gRPC channels; no
        # explicit shutdown is required and the library does not expose one.
        pass


def build_store() -> HistoryStore:
    """Factory honouring SENTINEL_HISTORY_BACKEND."""
    backend = os.environ.get("SENTINEL_HISTORY_BACKEND", "sqlite").lower()

    if backend == "sqlite":
        default_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "sentinel_history.db",
        )
        db_path = os.environ.get("SENTINEL_HISTORY_DB_PATH", default_path)
        return SQLiteHistoryStore(db_path)

    if backend == "firestore":
        project = os.environ.get("GOOGLE_CLOUD_PROJECT")
        if not project:
            raise RuntimeError(
                "SENTINEL_HISTORY_BACKEND=firestore requires GOOGLE_CLOUD_PROJECT to be set"
            )
        database = os.environ.get("SENTINEL_FIRESTORE_DATABASE", "sentinel")
        collection = os.environ.get("SENTINEL_FIRESTORE_COLLECTION", "sentinel_history")
        return FirestoreHistoryStore(project=project, database=database, collection=collection)

    raise ValueError(f"Unsupported SENTINEL_HISTORY_BACKEND: {backend}")
