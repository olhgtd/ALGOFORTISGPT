"""Slice 13 public-safe canonical reporting and export boundary."""

from engine.reporting.model import (
    CATEGORY_A,
    CATEGORY_B,
    CATEGORY_C,
    INVALID_FINALIZED,
    SUCCESS,
    CategoryAPayload,
    CategoryBPayload,
    CategoryCPayload,
    InvalidFinalizationPayload,
    RandomizedAnalysisCollectionEvidence,
    RandomizedAnalysisEvidence,
    ReportProvenance,
    ResultKind,
    StructuredBacktestResult,
    SuccessPayload,
    success_payload_v2,
    success_payload_with_cost_evidence,
)
from engine.reporting.serializer import ReportSerializationError, ReportSerializer
from engine.reporting.writer import (
    PublicationOutcome,
    PublicationResult,
    ReportPublicationError,
    ReportWriter,
)

__all__ = [
    "CATEGORY_A", "CATEGORY_B", "CATEGORY_C", "INVALID_FINALIZED", "SUCCESS", "CategoryAPayload",
    "CategoryBPayload", "CategoryCPayload", "InvalidFinalizationPayload", "PublicationOutcome",
    "PublicationResult", "RandomizedAnalysisCollectionEvidence", "RandomizedAnalysisEvidence", "ReportProvenance",
    "ReportPublicationError", "ReportSerializationError", "ReportSerializer",
    "ReportWriter", "ResultKind", "StructuredBacktestResult", "SuccessPayload",
    "success_payload_v2", "success_payload_with_cost_evidence",
]
