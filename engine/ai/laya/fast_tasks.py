"""Bounded fast-task service for Laya analysis outputs."""

from __future__ import annotations

from engine.ai.laya.contracts import FastTaskRequest, FastTaskResult


class LayaFastTaskError(ValueError):
    """Raised when a fast-task result is not bound to its request."""


class FastTaskService:
    def __init__(self, router: object) -> None:
        if not hasattr(router, "route_fast_task"):
            raise TypeError("router must provide route_fast_task")
        self._router = router

    def run(self, request: FastTaskRequest) -> FastTaskResult:
        if not isinstance(request, FastTaskRequest):
            raise TypeError("request must be FastTaskRequest")
        result = self._router.route_fast_task(request)
        if not isinstance(result, FastTaskResult):
            raise LayaFastTaskError("fast-task result type is invalid")
        if result.request_fingerprint != request.fingerprint:
            raise LayaFastTaskError("fast-task result is not bound to request")
        if result.task_kind != request.task_kind:
            raise LayaFastTaskError("fast-task result task kind mismatch")
        return result


__all__ = ["LayaFastTaskError", "FastTaskService"]
