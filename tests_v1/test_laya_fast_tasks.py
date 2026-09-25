from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from engine.ai.laya.contracts import FastTaskRequest, FastTaskResult, ModelProvenance
from engine.ai.laya.fast_tasks import FastTaskService, LayaFastTaskError


def _provenance() -> ModelProvenance:
    return ModelProvenance(
        model_id="laya-test",
        model_version="v1",
        model_hash="a" * 64,
        adapter_version="fake@v1",
        feature_schema_version="features@v1",
    )


def _request() -> FastTaskRequest:
    return FastTaskRequest.create(
        task_kind="FEATURE_SCORING",
        payload=(("symbol", "NIFTY"),),
        request_timestamp=datetime(2026, 1, 5, 9, 30, tzinfo=timezone.utc),
    )


class StubRouter:
    def __init__(self) -> None:
        self.calls = []
        self.request_override = None
        self.kind_override = None

    def route_fast_task(self, request):
        self.calls.append(request.fingerprint)
        return FastTaskResult.create(
            task_kind=self.kind_override or request.task_kind,
            request_fingerprint=self.request_override or request.fingerprint,
            ranked_items=(("atr", Decimal("0.8")),),
            provenance=_provenance(),
        )


def test_fast_task_service_returns_request_bound_result():
    request = _request()
    router = StubRouter()
    result = FastTaskService(router).run(request)
    assert result.request_fingerprint == request.fingerprint
    assert result.task_kind == request.task_kind
    assert router.calls == [request.fingerprint]


def test_fast_task_service_rejects_wrong_request_binding():
    request = _request()
    router = StubRouter()
    router.request_override = "b" * 64
    with pytest.raises(LayaFastTaskError, match="bound to request"):
        FastTaskService(router).run(request)


def test_fast_task_service_rejects_wrong_task_kind():
    request = _request()
    router = StubRouter()
    router.kind_override = "SIGNAL_FILTERING"
    with pytest.raises(LayaFastTaskError, match="task kind"):
        FastTaskService(router).run(request)


def test_fast_task_service_rejects_non_request_before_router_call():
    router = StubRouter()
    with pytest.raises(TypeError, match="FastTaskRequest"):
        FastTaskService(router).run(None)
    assert router.calls == []
