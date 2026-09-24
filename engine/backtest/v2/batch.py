"""Bounded in-process batch job state; no distributed or live execution."""
from __future__ import annotations

from dataclasses import dataclass, replace
from hashlib import sha256


class BatchError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class BatchJob:
    job_id: str
    run_fingerprint: str
    priority: int
    status: str = "PENDING"
    attempts: int = 0


class LocalBatch:
    def __init__(self, *, max_workers: int, max_pending: int) -> None:
        if any(isinstance(x, bool) or not isinstance(x, int) or x <= 0 for x in (max_workers, max_pending)):
            raise BatchError("positive worker and queue limits required")
        self.max_workers = max_workers
        self.max_pending = max_pending
        self._jobs: dict[str, BatchJob] = {}

    def submit(self, run_fingerprint: str, *, priority: int = 0) -> BatchJob:
        if not isinstance(run_fingerprint, str) or not run_fingerprint or isinstance(priority, bool) or not isinstance(priority, int):
            raise BatchError("run identity and integer priority required")
        job_id = sha256(("algofortis-local-batch/v1\0" + run_fingerprint).encode()).hexdigest()
        if job_id in self._jobs:
            job = self._jobs[job_id]
            if job.priority != priority:
                raise BatchError("conflicting duplicate job")
            return job
        if sum(job.status == "PENDING" for job in self._jobs.values()) >= self.max_pending:
            raise BatchError("pending queue full")
        job = BatchJob(job_id, run_fingerprint, priority)
        self._jobs[job_id] = job
        return job

    def next_job(self) -> BatchJob | None:
        if sum(job.status == "RUNNING" for job in self._jobs.values()) >= self.max_workers:
            return None
        pending = sorted((j for j in self._jobs.values() if j.status == "PENDING"),
                         key=lambda j: (j.priority, j.job_id))
        if not pending:
            return None
        job = replace(pending[0], status="RUNNING", attempts=pending[0].attempts + 1)
        self._jobs[job.job_id] = job
        return job

    def finish(self, job_id: str, *, success: bool) -> BatchJob:
        job = self._jobs.get(job_id)
        if job is None or job.status != "RUNNING":
            raise BatchError("only running jobs may finish")
        updated = replace(job, status="COMPLETED" if success else "FAILED")
        self._jobs[job_id] = updated
        return updated

    def cancel(self, job_id: str) -> BatchJob:
        job = self._jobs.get(job_id)
        if job is None or job.status not in ("PENDING", "RUNNING"):
            raise BatchError("only pending or running jobs may cancel")
        updated = replace(job, status="CANCELLED")
        self._jobs[job_id] = updated
        return updated

    def retry(self, job_id: str) -> BatchJob:
        job = self._jobs.get(job_id)
        if job is None or job.status != "FAILED":
            raise BatchError("only failed jobs may retry")
        updated = replace(job, status="PENDING")
        self._jobs[job_id] = updated
        return updated

    def resume(self, job_id: str) -> BatchJob:
        job = self._jobs.get(job_id)
        if job is None or job.status != "FAILED":
            raise BatchError("only failed jobs may resume")
        return self.retry(job_id)

    def health(self) -> dict[str, int]:
        return {status: sum(job.status == status for job in self._jobs.values())
                for status in ("PENDING", "RUNNING", "COMPLETED", "FAILED", "CANCELLED")}
