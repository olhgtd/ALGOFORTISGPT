"""AlgoFortis V2 migration facade including additive Phase-5 V8 and Live V9 schema."""

from __future__ import annotations

from engine.persistence.live_execution_schema_v9 import (
    LIVE_EXECUTION_CREATE_TABLES_SQL,
    LIVE_EXECUTION_DROP_TABLES_SQL,
)
from engine.persistence.migrations_base_v7 import (
    Migration,
    MigrationError,
    MigrationResult,
    RollbackResult,
    SQLiteMigrationRunner,
)
from engine.persistence.phase5_schema_v8 import (
    PHASE5_CREATE_TABLES_SQL,
    PHASE5_DROP_TABLES_SQL,
)

PHASE5_V8_MIGRATION = Migration(
    migration_id="phase5-paper-recovery-v8",
    from_version=7,
    to_version=8,
    apply_sql=PHASE5_CREATE_TABLES_SQL,
    rollback_sql=PHASE5_DROP_TABLES_SQL,
)

LIVE_EXECUTION_V9_MIGRATION = Migration(
    migration_id="live-execution-v9",
    from_version=8,
    to_version=9,
    apply_sql=LIVE_EXECUTION_CREATE_TABLES_SQL,
    rollback_sql=LIVE_EXECUTION_DROP_TABLES_SQL,
)

__all__ = [
    "MigrationError",
    "Migration",
    "MigrationResult",
    "RollbackResult",
    "SQLiteMigrationRunner",
    "PHASE5_V8_MIGRATION",
    "LIVE_EXECUTION_V9_MIGRATION",
]
