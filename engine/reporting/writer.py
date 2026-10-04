"""Atomic Slice 13 canonical report publication."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import json
import os
from pathlib import Path
import re
import time
from uuid import uuid4

from engine.reproducibility.codec import CanonicalCodec
from engine.reporting.model import ResultKind, StructuredBacktestResult
from engine.reporting.serializer import ReportSerializationError, ReportSerializer


class ReportPublicationError(RuntimeError):
    pass


class PublicationOutcome(str, Enum):
    PUBLISHED = "PUBLISHED"
    ALREADY_PUBLISHED = "ALREADY_PUBLISHED"


@dataclass(frozen=True)
class PublicationResult:
    outcome: PublicationOutcome
    destination: Path


_SAFE_ATTEMPT = re.compile(r"^[A-Za-z0-9_-]+$")


def _timestamp_token(value: datetime) -> str:
    return CanonicalCodec.timestamp_text(value).replace("-", "").replace(":", "").replace(".", "_")


def _short(identity: str) -> str:
    return identity[:12]


class ReportWriter:
    """Writes a complete validated report or leaves no canonical artifact."""

    @staticmethod
    def default_filename(result: StructuredBacktestResult) -> str:
        payload = result.payload
        if result.result_kind is ResultKind.SUCCESS:
            return f"algofortis-report-success-{_short(payload.manifest_fingerprint)}-{_short(payload.result_fingerprint)}.json"
        if result.result_kind is ResultKind.CATEGORY_A:
            return f"algofortis-report-category-a-{_short(payload.manifest_fingerprint)}-{_short(payload.failure_result_fingerprint)}.json"
        attempt = result.provenance.attempt_id
        suffix = attempt if attempt is not None and _SAFE_ATTEMPT.fullmatch(attempt) else _timestamp_token(result.report_generated_at)
        return f"algofortis-report-{result.result_kind.value.casefold()}-{suffix}.json"

    @classmethod
    def publish(cls, result: StructuredBacktestResult, destination: str | Path, *, create_parents: bool = False) -> PublicationResult:
        target = cls._destination(destination, create_parents=create_parents)
        raw = ReportSerializer.serialize(result)
        desired = ReportSerializer.validate_bytes(raw)
        with cls._exclusive_claim(target):
            if target.exists():
                return cls._existing(target, desired, result)
            staging = target.parent / f".{target.name}.algofortis-staging-{uuid4().hex}"
            if target.exists():
                return cls._existing(target, desired, result)
            try:
                with staging.open("xb") as stream:
                    stream.write(raw)
                    stream.flush()
                    os.fsync(stream.fileno())
                ReportSerializer.validate_bytes(staging.read_bytes())
                os.replace(staging, target)
                return PublicationResult(PublicationOutcome.PUBLISHED, target)
            except (OSError, ReportSerializationError) as error:
                if staging.exists():
                    staging.unlink()
                raise ReportPublicationError("canonical report publication failed") from error

    @staticmethod
    def _exclusive_claim(target: Path):
        """Claim one canonical target without deleting non-owned lock artifacts."""
        class _Claim:
            def __init__(self, lock: Path):
                self.lock = lock

            def __enter__(self):
                for _ in range(500):
                    try:
                        handle = os.open(self.lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                    except FileExistsError:
                        time.sleep(0.01)
                        continue
                    os.close(handle)
                    return self
                raise ReportPublicationError("canonical report destination remains locked")

            def __exit__(self, exc_type, exc, traceback):
                try:
                    self.lock.unlink()
                except FileNotFoundError:
                    pass
                return False

        return _Claim(target.parent / f".{target.name}.algofortis-lock")

    @staticmethod
    def _destination(destination: str | Path, *, create_parents: bool) -> Path:
        target = Path(destination)
        if not target.name or target.suffix != ".json" or any(part == ".." for part in target.parts):
            raise ReportPublicationError("unsafe reporting destination")
        parent = target.parent
        if not parent.exists():
            if not create_parents:
                raise ReportPublicationError("report destination parent is missing")
            parent.mkdir(parents=True, exist_ok=False)
        if not parent.is_dir():
            raise ReportPublicationError("report destination parent is not a directory")
        return target

    @classmethod
    def _existing(cls, target: Path, desired: dict[str, object], result: StructuredBacktestResult) -> PublicationResult:
        try:
            existing = ReportSerializer.validate_bytes(target.read_bytes())
        except (OSError, ReportSerializationError) as error:
            raise ReportPublicationError("existing target is not a valid canonical report") from error
        if result.result_kind in (ResultKind.CATEGORY_B, ResultKind.CATEGORY_C):
            raise ReportPublicationError("Category-B and Category-C publication collisions fail closed")
        identity_fields = ("manifest_fingerprint", "result_fingerprint") if result.result_kind is ResultKind.SUCCESS else ("manifest_fingerprint", "failure_result_fingerprint")
        if any(existing["payload"].get(field) != desired["payload"].get(field) for field in identity_fields):
            raise ReportPublicationError("report naming collision has distinct full identities")
        if cls._authoritative(existing) != cls._authoritative(desired):
            raise ReportPublicationError("same identities have inconsistent authoritative report content")
        return PublicationResult(PublicationOutcome.ALREADY_PUBLISHED, target)

    @staticmethod
    def _authoritative(document: dict[str, object]) -> dict[str, object]:
        return {"schema_version": document["schema_version"], "result_kind": document["result_kind"], "payload": document["payload"], "provenance": {key: value for key, value in document["provenance"].items() if key != "attempt_id"}}
