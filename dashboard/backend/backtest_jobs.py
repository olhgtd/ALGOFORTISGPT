"""Application-owned, single-worker historical jobs with cooperative shutdown."""
from concurrent.futures import ThreadPoolExecutor
from threading import RLock
from uuid import uuid4
from engine.strategy.base import StrategySignalGenerator


class BacktestCancelled(BaseException):
    """Control flow must escape the engine's Exception-to-HOLD strategy guard."""


class CancellableStrategy(StrategySignalGenerator):
    interface_version = "1.0"

    def __init__(self, strategy, check):
        self.strategy, self.check = strategy, check
        self.interface_version = strategy.interface_version
        self.state_schema = strategy.state_schema

    def __getattr__(self, name):
        return getattr(self.strategy, name)

    def initial_state(self):
        self.check()
        return self.strategy.initial_state()

    def generate_signal(self, data, state):
        self.check()
        return self.strategy.generate_signal(data, state)


class BacktestJobs:
    def __init__(self, service):
        self.service = service
        self.instance_id = uuid4().hex
        self.lock = RLock()
        self.pool = None
        self.closed = False
        self.futures = {}

    def start(self):
        with self.lock:
            if self.closed:
                raise RuntimeError("BACKTEST_RUNTIME_STOPPED")
            if self.pool is None:
                self.service._security_store.interrupt_backtest_jobs("RUNTIME_RESTART_INTERRUPTED")
                self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="algofortis-backtest")

    def submit(self, prepared):
        with self.lock:
            self.start()
            # Bound queued in-memory datasets as well as worker count.
            if len(self.futures) >= 8:
                raise RuntimeError("BACKTEST_QUEUE_FULL")
            record, frame, artifact, generator = prepared
            record["status"] = "PENDING"
            record["execution_metadata"]["runtime_instance"] = self.instance_id
            saved = self.service._security_store.save_backtest_run(record)
            run_id = saved["run_id"]
            try:
                future = self.pool.submit(self._work, prepared)
                self.futures[run_id] = future
                future.add_done_callback(lambda _: self._retire(run_id))
            except Exception:
                self.service._security_store.interrupt_backtest_jobs("BACKTEST_ENQUEUE_FAILED", run_id=run_id)
                raise
            return saved

    def _retire(self, run_id):
        with self.lock:
            self.futures.pop(run_id, None)

    def _work(self, prepared):
        # Each worker owns its connections. Never share a request transaction.
        from copy import copy
        service = copy(self.service)
        security = governance = None
        try:
            security = self.service._security_store.worker_copy()
            service._security_store = security
            governance = self.service._governance_store.worker_copy()
            service._governance_store = governance
            record = prepared[0]
            if not service._security_store.claim_backtest_job(record["run_id"]):
                return  # duplicate dispatch or queued cancellation
            record["status"] = "RUNNING"
            service._run_prepared(prepared)
        except Exception:
            service._security_store.interrupt_backtest_jobs("BACKTEST_WORKER_FAILED", run_id=prepared[0]["run_id"])
        finally:
            if governance is not None:
                governance.close()
            if security is not None:
                security.close()

    def shutdown(self):
        with self.lock:
            self.closed = True
            for run_id in tuple(self.futures):
                self.service._security_store.cancel_backtest_run(run_id)
            pool = self.pool
        if pool is not None:
            pool.shutdown(wait=True)
