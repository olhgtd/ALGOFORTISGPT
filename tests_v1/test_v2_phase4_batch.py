import pytest

from engine.backtest.v2.batch import BatchError, LocalBatch


def test_batch_respects_limits_and_deterministic_ids():
    batch = LocalBatch(max_workers=1, max_pending=2)
    first = batch.submit("run-a", priority=2)
    assert first.job_id == batch.submit("run-a", priority=2).job_id
    second = batch.submit("run-b", priority=1)
    assert batch.next_job().job_id == second.job_id
    batch.cancel(first.job_id)
    with pytest.raises(BatchError):
        batch.resume(first.job_id)


def test_batch_retry_and_worker_limit_are_explicit():
    batch = LocalBatch(max_workers=1, max_pending=2)
    first = batch.submit("run-a")
    second = batch.submit("run-b")
    running = batch.next_job()
    assert running.job_id in (first.job_id, second.job_id)
    assert batch.next_job() is None
    assert batch.health()["RUNNING"] == 1
    batch.finish(running.job_id, success=False)
    batch.retry(running.job_id)
    assert batch.health()["PENDING"] == 2
