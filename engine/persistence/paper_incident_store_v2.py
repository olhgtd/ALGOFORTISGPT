"""Append-only SQLite evidence repository for Phase-5 incidents/alerts."""

from __future__ import annotations

from pathlib import Path
import sqlite3

from engine.paper.contracts_v2 import AlertDeliveryRecord, FailureIncident
from engine.persistence.paper_codec_v2 import dumps_record, loads_record


class PaperIncidentStore:
    def __init__(self, database_path: Path | str) -> None:
        self.database_path = Path(database_path)
        if not self.database_path.is_file():
            raise FileNotFoundError(self.database_path)

    def _open(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.database_path))
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def save_incident(self, incident: FailureIncident) -> None:
        if not isinstance(incident, FailureIncident):
            raise TypeError("incident must be FailureIncident")
        with self._open() as connection:
            connection.execute(
                """
                INSERT INTO phase5_failure_incidents(
                    incident_id, affected_scope, detected_at, payload_json
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    incident.incident_id,
                    incident.affected_scope,
                    incident.detected_at.isoformat(),
                    dumps_record(incident),
                ),
            )

    def list_incidents(self, affected_scope: str) -> tuple[FailureIncident, ...]:
        with self._open() as connection:
            rows = connection.execute(
                """
                SELECT payload_json
                FROM phase5_failure_incidents
                WHERE affected_scope = ?
                ORDER BY detected_at, incident_id
                """,
                (affected_scope,),
            ).fetchall()
        return tuple(loads_record(str(row[0]), FailureIncident) for row in rows)

    def save_alert_delivery(self, record: AlertDeliveryRecord) -> None:
        if not isinstance(record, AlertDeliveryRecord):
            raise TypeError("record must be AlertDeliveryRecord")
        with self._open() as connection:
            connection.execute(
                """
                INSERT INTO phase5_alert_deliveries(
                    alert_id, incident_id, channel, attempt, attempted_at, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    record.alert_id,
                    record.incident_id,
                    record.channel,
                    record.attempt,
                    record.attempted_at.isoformat(),
                    dumps_record(record),
                ),
            )

    def list_alert_deliveries(self, incident_id: str) -> tuple[AlertDeliveryRecord, ...]:
        with self._open() as connection:
            rows = connection.execute(
                """
                SELECT payload_json
                FROM phase5_alert_deliveries
                WHERE incident_id = ?
                ORDER BY attempted_at, alert_id, channel, attempt
                """,
                (incident_id,),
            ).fetchall()
        return tuple(loads_record(str(row[0]), AlertDeliveryRecord) for row in rows)


__all__ = ["PaperIncidentStore"]
