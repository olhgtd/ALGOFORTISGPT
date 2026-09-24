"""SQLite-backed append-only trial authority with a durable OOS latch."""
from __future__ import annotations

from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Mapping

from .experiments import ExperimentSpec
from .trials import TrialRecord, TrialStatus, TrialsLedger, TrialsLedgerError


class DurableLedgerError(TrialsLedgerError):
    pass


def _encode(value: object) -> object:
    if isinstance(value, Decimal):
        return {"$decimal": str(value)}
    if isinstance(value, Mapping):
        return {"$map": [[key, _encode(item)] for key, item in sorted(value.items())]}
    if isinstance(value, tuple):
        return {"$tuple": [_encode(item) for item in value]}
    if value is None or isinstance(value, (bool, int, str)):
        return value
    raise DurableLedgerError("unsupported trial parameter")


def _decode(value: object) -> object:
    if isinstance(value, dict):
        if len(value) != 1:
            raise DurableLedgerError("invalid encoded parameter")
        key, payload = next(iter(value.items()))
        if key == "$decimal":
            return Decimal(payload)
        if key == "$tuple":
            return tuple(_decode(x) for x in payload)
        if key == "$map":
            return {name: _decode(item) for name, item in payload}
        raise DurableLedgerError("unknown encoded parameter")
    return value


class DurableTrialsLedger(TrialsLedger):
    def __init__(self, path: str | Path, experiment: ExperimentSpec) -> None:
        super().__init__(experiment)
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS experiment (identity TEXT PRIMARY KEY, budget INTEGER NOT NULL, oos INTEGER NOT NULL CHECK(oos IN (0, 1)))")
            db.execute("CREATE TABLE IF NOT EXISTS trials (ordinal INTEGER PRIMARY KEY, parameters TEXT NOT NULL, status TEXT NOT NULL, result TEXT, reason TEXT NOT NULL, fingerprint TEXT NOT NULL, chain TEXT NOT NULL)")
            db.execute("CREATE TRIGGER IF NOT EXISTS trials_no_update BEFORE UPDATE ON trials BEGIN SELECT RAISE(ABORT, 'append-only'); END")
            db.execute("CREATE TRIGGER IF NOT EXISTS trials_no_delete BEFORE DELETE ON trials BEGIN SELECT RAISE(ABORT, 'append-only'); END")
            row = db.execute("SELECT identity, budget FROM experiment").fetchone()
            if row is None:
                db.execute("INSERT INTO experiment VALUES (?, ?, 0)", (experiment.experiment_id, experiment.max_trials))
            elif row != (experiment.experiment_id, experiment.max_trials):
                raise DurableLedgerError("experiment identity/budget changed")
        self._refresh()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=10)

    def _refresh(self) -> None:
        with self._connect() as db:
            rows = db.execute("SELECT ordinal, parameters, status, result, reason, fingerprint, chain FROM trials ORDER BY ordinal").fetchall()
        records = []
        previous = "0" * 64
        for ordinal, parameters, status, result, reason, fingerprint, chain in rows:
            try:
                decoded = _decode(json.loads(parameters))
                record = TrialRecord.create(experiment=self.experiment, ordinal=ordinal,
                                            parameters=decoded, status=TrialStatus(status),
                                            result_fingerprint=result, reason=reason)
            except (ValueError, TypeError, KeyError) as exc:
                raise DurableLedgerError("trial evidence is invalid") from exc
            expected = hashlib.sha256((previous + record.fingerprint).encode("ascii")).hexdigest()
            if ordinal != len(records) + 1 or fingerprint != record.fingerprint or chain != expected:
                raise DurableLedgerError("trial ledger was tampered with")
            records.append(record)
            previous = chain
        self._records = records
        self._trial_ids = {record.trial_id for record in records}

    @property
    def trial_count(self) -> int:
        self._refresh()
        return len(self._records)

    @property
    def remaining_budget(self) -> int:
        return self.experiment.max_trials - self.trial_count

    @property
    def oos_viewed(self) -> bool:
        with self._connect() as db:
            return bool(db.execute("SELECT oos FROM experiment").fetchone()[0])

    def mark_oos_viewed(self) -> None:
        with self._connect() as db:
            db.execute("UPDATE experiment SET oos = 1 WHERE identity = ?", (self.experiment.experiment_id,))

    def append(self, record: TrialRecord) -> TrialRecord:
        if not isinstance(record, TrialRecord) or record.experiment_id != self.experiment.experiment_id:
            raise DurableLedgerError("trial belongs to a different experiment")
        try:
            with self._connect() as db:
                db.execute("BEGIN IMMEDIATE")
                if db.execute("SELECT oos FROM experiment").fetchone()[0]:
                    raise DurableLedgerError("OOS viewed: experiment is closed")
                count, previous = db.execute("SELECT COUNT(*), COALESCE((SELECT chain FROM trials ORDER BY ordinal DESC LIMIT 1), ? ) FROM trials LIMIT 1", ("0" * 64,)).fetchone()
                if count >= self.experiment.max_trials or record.ordinal != count + 1:
                    raise DurableLedgerError("trial budget or ordinal invalid")
                parameters = json.dumps(_encode(record.parameters), sort_keys=True, separators=(",", ":"))
                chain = hashlib.sha256((previous + record.fingerprint).encode("ascii")).hexdigest()
                db.execute("INSERT INTO trials VALUES (?, ?, ?, ?, ?, ?, ?)",
                           (record.ordinal, parameters, record.status.value, record.result_fingerprint,
                            record.reason, record.fingerprint, chain))
        except sqlite3.DatabaseError as exc:
            raise DurableLedgerError("durable trial append failed") from exc
        self._refresh()
        return record

    def records(self) -> tuple[TrialRecord, ...]:
        self._refresh()
        return tuple(self._records)
