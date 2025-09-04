from __future__ import annotations

import threading
import time
import uuid
from typing import Dict, List, Optional

from .contracts import IngestionEvent, IngestionJob, IngestionStatus


class InMemoryIngestionRepo:
    """
    Per-tenant in-memory store for jobs + events.
    Not thread-safe across processes; adequate for tests + first iteration.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._jobs: Dict[str, IngestionJob] = {}

    def _now(self) -> float:
        return time.time()

    def create_job(self, tenant_id: str) -> IngestionJob:
        with self._lock:
            job_id = str(uuid.uuid4())
            ts = self._now()
            job = IngestionJob(
                id=job_id,
                tenant_id=tenant_id,
                status=IngestionStatus.PENDING,
                created_at=ts,
                updated_at=ts,
                items=[],
                events=[],
            )
            self._jobs[job_id] = job
            return job

    def get_job(self, tenant_id: str, job_id: str) -> Optional[IngestionJob]:
        with self._lock:
            job = self._jobs.get(job_id)
            if job and job.tenant_id == tenant_id:
                return job
            return None

    def save_job(self, job: IngestionJob) -> None:
        with self._lock:
            job.updated_at = self._now()
            self._jobs[job.id] = job

    def append_event(self, job: IngestionJob, event: IngestionEvent) -> None:
        with self._lock:
            job.events.append(event)
            job.updated_at = self._now()
            self._jobs[job.id] = job

    def list_events(self, tenant_id: str, job_id: str) -> List[IngestionEvent]:
        job = self.get_job(tenant_id, job_id)
        return list(job.events) if job else []


