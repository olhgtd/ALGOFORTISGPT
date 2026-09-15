"""R-05: manual Walk-Forward / OOS productization around the existing engine.

No engine/** changes. Each IS/OOS window executes as an exact registered
paper historical-replay session (same strategy/version/hash, same approved
dataset via the NF-06 pin, RiskGate, SimulatedPaperBroker) — the proven
stable multi-day execution path. Manual RUN only: jobs are created
explicitly and run once in a single worker with cooperative cancellation
between windows. No schedulers, no auto-runs, no fabricated metrics —
overall aggregates are sums/counts over real windows.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import copy
from datetime import date
from threading import RLock
from typing import Any
from uuid import uuid4


class WalkForwardError(Exception):
    """Fail-closed walk-forward product error."""


WALKFORWARD_MAX_WINDOWS = 12
WALKFORWARD_MAX_SPAN_DAYS = 120


def compute_walkforward_windows(
    coverage_start: str, coverage_end: str, *, is_days: int, oos_days: int,
    max_windows: int = WALKFORWARD_MAX_WINDOWS,
) -> list[dict[str, str]]:
    """Split approved coverage into sequential non-overlapping IS/OOS blocks.

    Deterministic and fully inside [coverage_start, coverage_end]. Raises
    WalkForwardError when no complete IS+OOS block fits.
    """
    try:
        cov_start = date.fromisoformat(coverage_start)
        cov_end = date.fromisoformat(coverage_end)
    except ValueError as exc:
        raise WalkForwardError(f"Invalid dataset coverage dates: {exc}") from exc
    if cov_start > cov_end:
        raise WalkForwardError("Dataset coverage is empty")
    windows: list[dict[str, str]] = []
    cursor = cov_start
    while len(windows) // 2 < max_windows:
        is_start = cursor
        is_end = _add_days(is_start, is_days - 1)
        oos_start = _add_days(is_end, 1)
        oos_end = _add_days(oos_start, oos_days - 1)
        if oos_end > cov_end:
            break
        windows.append({"kind": "IN_SAMPLE", "start_date": is_start.isoformat(), "end_date": is_end.isoformat()})
        windows.append({"kind": "OUT_OF_SAMPLE", "start_date": oos_start.isoformat(), "end_date": oos_end.isoformat()})
        cursor = _add_days(oos_end, 1)
    if not windows:
        raise WalkForwardError(
            "No complete IS/OOS block fits approved coverage: "
            f"need {is_days + oos_days} days inside {coverage_start}/{coverage_end}")
    return windows


def _add_days(value: date, days: int):
    from datetime import timedelta
    return value + timedelta(days=days)


class WalkForwardService:
    """Manual walk-forward jobs over paper historical replay (single worker)."""

    def __init__(self, *, security_store, backtest_service, paper_service=None) -> None:
        if security_store is None or backtest_service is None:
            raise WalkForwardError("Walk-forward requires security and backtest authorities")
        self._security = security_store
        self._backtests = backtest_service
        self._paper = paper_service
        self._lock = RLock()
        self._pool: ThreadPoolExecutor | None = None
        self._futures: dict[str, Any] = {}
        self._closed = False

    def start(self) -> None:
        with self._lock:
            if self._closed:
                raise WalkForwardError("WALKFORWARD_RUNTIME_STOPPED")
            if self._pool is None:
                try:
                    self._security.interrupt_walkforward_jobs("RUNTIME_RESTART_INTERRUPTED")
                except Exception:
                    pass
                self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="sentinelx-walkforward")

    def shutdown(self) -> None:
        with self._lock:
            self._closed = True
            for job_id in tuple(self._futures):
                try:
                    self._security.cancel_walkforward_job(job_id=job_id, user_id=None)
                except Exception:
                    pass
            pool, self._pool = self._pool, None
        if pool is not None:
            pool.shutdown(wait=True)

    # ── manual RUN ──

    def create_and_run(
        self, *, user_id: str, strategy_id: str, version_id: str | None = None,
        dataset_id: str | None = None, instrument: str = "NIFTY", timeframe: str = "1m",
        is_days: int = 20, oos_days: int = 5, initial_capital: float = 500000.0,
        policy: dict[str, Any] | None = None, max_windows: int = WALKFORWARD_MAX_WINDOWS,
    ) -> dict[str, Any]:
        uid = str(user_id)
        try:
            is_n, oos_n = int(is_days), int(oos_days)
        except (TypeError, ValueError) as exc:
            raise WalkForwardError(f"Invalid walk-forward window configuration: {exc}") from exc
        if not 1 <= is_n <= WALKFORWARD_MAX_SPAN_DAYS or not 1 <= oos_n <= WALKFORWARD_MAX_SPAN_DAYS:
            raise WalkForwardError("IS/OOS days must each be within 1..120")
        try:
            max_w = int(max_windows)
        except (TypeError, ValueError) as exc:
            raise WalkForwardError(f"Invalid max_windows: {exc}") from exc
        max_w = max(1, min(max_w, WALKFORWARD_MAX_WINDOWS))
        inst = (instrument or "").upper().strip()
        tf = (timeframe or "").strip()
        if not inst or not tf:
            raise WalkForwardError("Instrument and timeframe are required")
        if not math_is_finite(initial_capital) or initial_capital <= 0:
            raise WalkForwardError("Initial capital must be finite and positive")

        user = self._security.get_user(uid)
        if user is None:
            raise WalkForwardError("Active authenticated User required")
        try:
            role = user["role"] or ""
        except (KeyError, TypeError, IndexError):
            role = ""
        if role != "OWNER":
            access = self._security.check_user_strategy_access(uid, strategy_id)
            if not access.get("permitted"):
                raise WalkForwardError(f"Strategy '{strategy_id}' not available to user: {access.get('reason')}")

        resolved = self._resolve_exact_version(strategy_id, version_id)
        ds_id = str(dataset_id or "nse-tick-primary")
        gate = self._security.check_backtest_gate(
            strategy_id, ds_id, user_id=uid, instrument=inst, timeframe=tf)
        if not gate.get("permitted"):
            raise WalkForwardError(str(gate.get("code")) + ": " + str(gate.get("reason")))
        dataset = gate["dataset"]
        windows = compute_walkforward_windows(
            str(dataset["startDate"]), str(dataset["endDate"]),
            is_days=is_n, oos_days=oos_n, max_windows=max_w)

        job = self._security.create_walkforward_job(
            user_id=uid, strategy_id=strategy_id,
            strategy_version_id=resolved["version_id"], source_sha256=resolved["source_sha256"],
            dataset_id=ds_id, instrument=inst, timeframe=tf,
            is_days=is_n, oos_days=oos_n, initial_capital=float(initial_capital),
            policy=dict(policy or {"mode": "OTM", "distance": 1}), windows=windows)
        self._security.update_walkforward_job(job_id=job["jobId"], user_id=uid, status="RUNNING")
        self.start()
        with self._lock:
            future = self._pool.submit(self._work, job["jobId"], uid, {
                "strategy_id": strategy_id, "version_id": resolved["version_id"],
                "dataset_id": ds_id, "instrument": inst, "timeframe": tf,
                "initial_capital": float(initial_capital),
                "policy": dict(policy or {"mode": "OTM", "distance": 1}),
            })
            self._futures[job["jobId"]] = future
            future.add_done_callback(lambda _f, jid=job["jobId"]: self._retire(jid))
        return self.get_job(job["jobId"], user_id=uid)

    def _retire(self, job_id: str) -> None:
        with self._lock:
            self._futures.pop(job_id, None)

    def _resolve_exact_version(self, strategy_id: str, version_id: str | None) -> dict[str, Any]:
        registered = self._security.get_owner_strategy(strategy_id)
        if registered is None:
            raise WalkForwardError("Strategy is not registered")
        canonical = str(registered.get("version") or "").strip()
        if not canonical:
            raise WalkForwardError("Canonical strategy version is unavailable")
        if version_id is not None and str(version_id) != canonical:
            raise WalkForwardError("Strategy version does not match the canonical current version")
        gov = getattr(self._backtests, "_governance_store", None)
        if gov is None:
            raise WalkForwardError("Governance authority unavailable")
        row = gov.get_version(strategy_id, canonical)
        if row is None:
            raise WalkForwardError("Exact registered strategy version required")
        if row["archived"]:
            raise WalkForwardError("Strategy version is archived")
        return {"version_id": row["version_id"], "source_sha256": row["source_sha256"]}

    # ── worker ──

    def _work(self, job_id: str, user_id: str, request: dict[str, Any]) -> None:
        security = governance = None
        try:
            security = self._security.worker_copy()
            governance = self._backtests._governance_store.worker_copy()
            paper = copy(self._paper) if self._paper is not None else None
            if paper is None:
                raise WalkForwardError("Paper replay authority unavailable")
            paper._security_store = security
            paper._governance_store = governance
            job = security.get_walkforward_job(job_id, user_id=user_id)
            if job is None:
                return
            for window in job["windows"]:
                current = security.get_walkforward_job(job_id, user_id=user_id)
                if current is None or current.get("cancelRequested"):
                    self._cancel_remaining(security, job_id, user_id)
                    security.update_walkforward_job(
                        job_id=job_id, user_id=user_id, status="CANCELLED",
                        error="CANCELLED_BY_OPERATOR")
                    return
                self._run_window(security, paper, job_id, user_id, request, window)
                refreshed = security.get_walkforward_job(job_id, user_id=user_id)
                security.update_walkforward_job(
                    job_id=job_id, user_id=user_id, overall=self._overall(refreshed))
            final = security.get_walkforward_job(job_id, user_id=user_id)
            if final is not None and not final.get("cancelRequested"):
                completed = [w for w in final["windows"] if w["status"] == "COMPLETED"]
                failed = [w for w in final["windows"] if w["status"] == "FAILED"]
                if not completed:
                    security.update_walkforward_job(
                        job_id=job_id, user_id=user_id, status="FAILED",
                        error="All walk-forward windows failed",
                        overall=self._overall(final))
                else:
                    security.update_walkforward_job(
                        job_id=job_id, user_id=user_id, status="COMPLETED",
                        error="Some windows failed" if failed else None,
                        overall=self._overall(final))
        except Exception as exc:
            try:
                (security or self._security).update_walkforward_job(
                    job_id=job_id, user_id=user_id, status="FAILED",
                    error=f"WALKFORWARD_WORKER_FAILED: {exc}")
            except Exception:
                pass
        finally:
            if governance is not None:
                try:
                    governance.close()
                except Exception:
                    pass
            if security is not None:
                try:
                    security.close()
                except Exception:
                    pass

    def _run_window(self, security, paper, job_id, user_id, request, window) -> None:
        window_id = window["windowId"]
        security.update_walkforward_window(window_id=window_id, status="RUNNING")
        date_range = f"{window['startDate']}/{window['endDate']}"
        try:
            ses = paper.create_session(
                user_id=user_id, strategy_id=request["strategy_id"],
                instrument=request["instrument"], timeframe=request["timeframe"],
                initial_capital=request["initial_capital"], policy=request["policy"],
                data_source_mode="HISTORICAL_REPLAY",
                date_range=date_range, dataset_id=request["dataset_id"])
            done = paper.start_session(ses["session_id"], user_id=user_id)
            orders = security.get_paper_orders(ses["session_id"], user_id=user_id)
            metrics = {
                "paperSessionId": ses["session_id"],
                "status": done.get("status"),
                "netProfit": done.get("total_pnl"),
                "realizedPnl": done.get("realized_pnl"),
                "unrealizedPnl": done.get("unrealized_pnl"),
                "totalTrades": len(orders),
                "barsConsumed": done.get("bars_consumed"),
            }
            security.update_walkforward_window(
                window_id=window_id, status="COMPLETED",
                paper_session_id=ses["session_id"], metrics=metrics)
        except Exception as exc:
            security.update_walkforward_window(
                window_id=window_id, status="FAILED", error=f"{type(exc).__name__}: {exc}")

    def _cancel_remaining(self, security, job_id, user_id) -> None:
        job = security.get_walkforward_job(job_id, user_id=user_id)
        if job is None:
            return
        for window in job["windows"]:
            if window["status"] in ("PENDING", "RUNNING"):
                security.update_walkforward_window(window_id=window["windowId"], status="CANCELLED")

    @staticmethod
    def _overall(job: dict[str, Any] | None) -> dict[str, Any]:
        if not job:
            return {}
        is_runs = [w for w in job["windows"] if w["kind"] == "IN_SAMPLE" and w["status"] == "COMPLETED"]
        oos_runs = [w for w in job["windows"] if w["kind"] == "OUT_OF_SAMPLE" and w["status"] == "COMPLETED"]
        failed = sum(1 for w in job["windows"] if w["status"] == "FAILED")

        def _total(rows, key):
            total = 0.0
            for w in rows:
                value = (w.get("metrics") or {}).get(key)
                if isinstance(value, (int, float)):
                    total += float(value)
            return round(total, 2)

        return {
            "windowsTotal": len(job["windows"]),
            "windowsCompleted": len(is_runs) + len(oos_runs),
            "windowsFailed": failed,
            "inSample": {
                "windows": len(is_runs),
                "netProfit": _total(is_runs, "netProfit"),
                "totalTrades": int(_total(is_runs, "totalTrades")),
            },
            "outOfSample": {
                "windows": len(oos_runs),
                "netProfit": _total(oos_runs, "netProfit"),
                "totalTrades": int(_total(oos_runs, "totalTrades")),
            },
        }

    # ── reads / cancel ──

    def get_job(self, job_id: str, user_id: str | None) -> dict[str, Any] | None:
        return self._security.get_walkforward_job(job_id, user_id=user_id)

    def list_jobs(self, user_id: str | None, *, status: str | None = None) -> list[dict[str, Any]]:
        return self._security.list_walkforward_jobs(user_id, status=status)

    def cancel_job(self, job_id: str, user_id: str | None) -> dict[str, Any] | None:
        return self._security.request_walkforward_cancel(job_id=job_id, user_id=user_id)


def math_is_finite(value: Any) -> bool:
    try:
        return float(value) == float(value) and abs(float(value)) != float("inf")
    except (TypeError, ValueError):
        return False
