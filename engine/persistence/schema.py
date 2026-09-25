"""AlgoFortis SQLite schema facade with additive Phase-5 V8 objects."""

from __future__ import annotations

from engine.persistence.phase5_schema_v8 import PHASE5_CREATE_TABLES_SQL
from engine.persistence.schema_legacy_v7 import (
    CREATE_TABLES_SQL as V7_CREATE_TABLES_SQL,
    PRAGMA_STATEMENTS,
)

SCHEMA_VERSION: int = 8
CREATE_TABLES_SQL: tuple[str, ...] = V7_CREATE_TABLES_SQL + PHASE5_CREATE_TABLES_SQL

__all__ = ["SCHEMA_VERSION", "PRAGMA_STATEMENTS", "CREATE_TABLES_SQL"]
