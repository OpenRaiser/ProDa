from __future__ import annotations

import threading
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional


class JobRegistry:
    """Thread-safe in-memory registry of long-running background jobs.

    Each job is a plain dict. Keys starting with underscore (e.g. `_cancel`)
    are internal and stripped from JSON responses via `public()`.
    """

    def __init__(self, max_jobs: int = 50) -> None:
        self._jobs: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._max = max_jobs

    # ---------- helpers ----------
    @staticmethod
    def public(job: Dict[str, Any]) -> Dict[str, Any]:
        return {k: v for k, v in job.items() if not k.startswith("_")}

    def _evict(self) -> None:
        with self._lock:
            if len(self._jobs) <= self._max:
                return
            finished = [
                jid
                for jid, j in self._jobs.items()
                if j.get("status") in ("done", "error", "cancelled")
            ]
            finished.sort(key=lambda jid: self._jobs[jid].get("updated_at", ""))
            while len(self._jobs) > self._max and finished:
                self._jobs.pop(finished.pop(0), None)

    # ---------- lifecycle ----------
    def create(
        self,
        project_id: str,
        extra: Optional[Dict[str, Any]] = None,
    ) -> str:
        self._evict()
        job_id = uuid.uuid4().hex[:16]
        now = datetime.utcnow().isoformat()
        job: Dict[str, Any] = {
            "id": job_id,
            "project_id": project_id,
            "status": "pending",
            "progress": 0,
            "message": "Queued",
            "total": 0,
            "done": 0,
            "result": None,
            "error": None,
            "created_at": now,
            "updated_at": now,
            "_cancel": threading.Event(),
        }
        if extra:
            job.update(extra)
        with self._lock:
            self._jobs[job_id] = job
        return job_id

    def get(self, job_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self._jobs.get(job_id)

    def get_public(self, job_id: str) -> Optional[Dict[str, Any]]:
        job = self.get(job_id)
        return self.public(job) if job else None

    def update(self, job_id: str, **patch: Any) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            job.update(patch)
            job["updated_at"] = datetime.utcnow().isoformat()

    # ---------- cancellation ----------
    def cancel_event(self, job_id: str) -> Optional[threading.Event]:
        job = self.get(job_id)
        if not job:
            return None
        ev = job.get("_cancel")
        return ev if isinstance(ev, threading.Event) else None

    def request_cancel(
        self,
        job_id: str,
        wait_ms: int = 1000,
    ) -> Optional[Dict[str, Any]]:
        job = self.get(job_id)
        if not job:
            return None
        if job.get("status") in ("done", "error", "cancelled"):
            return self.public(job)
        ev = job.get("_cancel")
        if isinstance(ev, threading.Event):
            ev.set()
        self.update(job_id, message="Cancel requested")
        slept = 0
        while slept < wait_ms:
            if job.get("status") in ("cancelled", "error", "done"):
                break
            time.sleep(0.05)
            slept += 50
        return self.public(job)

    # ---------- listing ----------
    def list_for_project(self, project_id: str) -> List[Dict[str, Any]]:
        with self._lock:
            items = [
                self.public(j)
                for j in self._jobs.values()
                if j.get("project_id") == project_id
            ]
        items.sort(key=lambda j: j.get("created_at", ""), reverse=True)
        return items
