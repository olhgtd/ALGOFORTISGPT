"""AlgoFortis V2 deterministic SQLite migration foundation.

The runner is deliberately additive and is not wired into the frozen V1 store by
this Phase-1 slice.  It provides the safe primitive required by AF2-ARC-004:
validate a contiguous migration plan, create and verify a WAL-safe SQLite backup
before mutation, apply schema changes transactionally, and support an explicit
backup-before-rollback path.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3
import time
from typing import Iterable, Sequence


class MigrationError(RuntimeError):
    """Fail-closed migration error with any verified recovery backup attached."""

    def __init__(self, message: str, *, backup_path: Path | None = None) -> None:
        super().__init__(message)
        self.backup_path = backup_path


def _non_empty_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MigrationError(f"{field} must be a non-empty string")
    return value.strip()


def _sql_tuple(values: object, field: str) -> tuple[str, ...]:
    if not isinstance(values, (tuple, list)):
        raise MigrationError(f"{field} must be a sequence of SQL statements")
    result: list[str] = []
    for index, value in enumerate(values):
        if not isinstance(value, str) or not value.strip():
            raise MigrationError(f"{field}[{index}] must be a non-empty SQL statement")
        result.append(value.strip())
    return tuple(result)


@dataclass(frozen=True, slots=True)
class Migration:
    """One reversible, single-version SQLite schema transition."""

    migration_id: str
    from_version: int
    to_version: int
    apply_sql: tuple[str, ...]
    rollback_sql: tuple[str, ...]

    def __post_init__(self) -> None:
        migration_id = _non_empty_text(self.migration_id, "migration_id")
        if isinstance(self.from_version, bool) or not isinstance(self.from_version, int) or self.from_version < 0:
            raise MigrationError("from_version must be a non-negative integer")
        if isinstance(self.to_version, bool) or not isinstance(self.to_version, int) or self.to_version < 1:
            raise MigrationError("to_version must be a positive integer")
        if self.to_version != self.from_version + 1:
            raise MigrationError("each migration must advance exactly one contiguous version")
        apply_sql = _sql_tuple(self.apply_sql, "apply_sql")
        rollback_sql = _sql_tuple(self.rollback_sql, "rollback_sql")
        if not apply_sql:
            raise MigrationError("migration apply_sql must not be empty")
        if not rollback_sql:
            raise MigrationError("migration rollback_sql must not be empty")
        object.__setattr__(self, "migration_id", migration_id)
        object.__setattr__(self, "apply_sql", apply_sql)
        object.__setattr__(self, "rollback_sql", rollback_sql)


@dataclass(frozen=True, slots=True)
class MigrationResult:
    from_version: int
    to_version: int
    applied_migration_ids: tuple[str, ...]
    backup_path: Path | None
    backup_verified: bool


@dataclass(frozen=True, slots=True)
class RollbackResult:
    from_version: int
    to_version: int
    rolled_back_migration_id: str
    backup_path: Path
    backup_verified: bool


def _validate_plan(migrations: Iterable[Migration]) -> tuple[Migration, ...]:
    plan = tuple(migrations)
    if not all(isinstance(item, Migration) for item in plan):
        raise MigrationError("migration plan contains a non-Migration entry")

    ids = tuple(item.migration_id for item in plan)
    if len(ids) != len(set(ids)):
        raise MigrationError("duplicate migration_id in migration plan")

    ordered = tuple(sorted(plan, key=lambda item: (item.from_version, item.to_version, item.migration_id)))
    for left, right in zip(ordered, ordered[1:]):
        if right.from_version != left.to_version:
            raise MigrationError("migration plan must be contiguous without version gaps")
    return ordered


def _database_user_version(connection: sqlite3.Connection) -> int:
    row = connection.execute("PRAGMA user_version").fetchone()
    if row is None:
        raise MigrationError("unable to read current database version")
    return int(row[0])


def _assert_integrity(connection: sqlite3.Connection, label: str) -> None:
    rows = connection.execute("PRAGMA integrity_check").fetchall()
    if not rows or any(str(row[0]).casefold() != "ok" for row in rows):
        raise MigrationError(f"{label} SQLite integrity check failed: {rows!r}")


class SQLiteMigrationRunner:
    """Backup-first, fail-closed SQLite schema migration runner."""

    def __init__(self, database_path: Path | str, backup_dir: Path | str) -> None:
        self.database_path = Path(database_path).resolve()
        self.backup_dir = Path(backup_dir).resolve()
        if not self.database_path.is_file():
            raise MigrationError(f"database file does not exist: {self.database_path}")

    def _open(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.database_path))
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def _verified_backup(
        self,
        source: sqlite3.Connection,
        *,
        operation: str,
        from_version: int,
        to_version: int,
    ) -> Path:
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = time.time_ns()
        destination = self.backup_dir / (
            f"{self.database_path.stem}.{operation}.v{from_version}-to-v{to_version}.{stamp}.sqlite3"
        )
        partial = destination.with_suffix(destination.suffix + ".part")

        try:
            target = sqlite3.connect(str(partial))
            try:
                source.backup(target)
            finally:
                target.close()

            verify = sqlite3.connect(str(partial))
            try:
                _assert_integrity(verify, "backup")
                backup_version = _database_user_version(verify)
                if backup_version != from_version:
                    raise MigrationError(
                        f"backup version mismatch: expected {from_version}, got {backup_version}"
                    )
            finally:
                verify.close()

            partial.replace(destination)
            return destination
        except Exception as exc:
            if partial.exists():
                try:
                    partial.unlink()
                except OSError:
                    pass
            if isinstance(exc, MigrationError):
                raise
            raise MigrationError(f"pre-migration backup failed: {exc}") from exc

    def migrate(
        self,
        migrations: Sequence[Migration],
        *,
        target_version: int,
    ) -> MigrationResult:
        plan = _validate_plan(migrations)
        if isinstance(target_version, bool) or not isinstance(target_version, int) or target_version < 0:
            raise MigrationError("target_version must be a non-negative integer")

        connection = self._open()
        backup_path: Path | None = None
        try:
            _assert_integrity(connection, "source")
            current = _database_user_version(connection)
            if target_version < current:
                raise MigrationError(
                    f"downgrade target {target_version} is below current version {current}; use rollback_last"
                )
            if target_version == current:
                return MigrationResult(current, current, (), None, False)

            by_from = {migration.from_version: migration for migration in plan}
            if current not in by_from:
                raise MigrationError(f"current version {current} has no migration path")

            selected: list[Migration] = []
            version = current
            while version < target_version:
                migration = by_from.get(version)
                if migration is None:
                    raise MigrationError(
                        f"migration plan is not contiguous from current version {version} to target {target_version}"
                    )
                selected.append(migration)
                version = migration.to_version
            if version != target_version:
                raise MigrationError(f"migration plan does not terminate at target version {target_version}")

            backup_path = self._verified_backup(
                connection,
                operation="before-migrate",
                from_version=current,
                to_version=target_version,
            )

            try:
                connection.execute("BEGIN IMMEDIATE")
                for migration in selected:
                    for statement in migration.apply_sql:
                        connection.execute(statement)
                    connection.execute(f"PRAGMA user_version = {migration.to_version}")
                _assert_integrity(connection, "migrated database")
                connection.commit()
            except Exception as exc:
                connection.rollback()
                if isinstance(exc, MigrationError):
                    raise MigrationError(
                        f"migration failed: {exc}", backup_path=backup_path
                    ) from exc
                raise MigrationError(
                    f"migration failed: {exc}", backup_path=backup_path
                ) from exc

            return MigrationResult(
                from_version=current,
                to_version=target_version,
                applied_migration_ids=tuple(item.migration_id for item in selected),
                backup_path=backup_path,
                backup_verified=True,
            )
        finally:
            connection.close()

    def rollback_last(self, migrations: Sequence[Migration]) -> RollbackResult:
        plan = _validate_plan(migrations)
        connection = self._open()
        backup_path: Path | None = None
        try:
            _assert_integrity(connection, "source")
            current = _database_user_version(connection)
            candidates = [item for item in plan if item.to_version == current]
            if len(candidates) != 1:
                raise MigrationError(
                    f"current version {current} does not identify exactly one rollback migration"
                )
            migration = candidates[0]
            backup_path = self._verified_backup(
                connection,
                operation="before-rollback",
                from_version=current,
                to_version=migration.from_version,
            )

            try:
                connection.execute("BEGIN IMMEDIATE")
                for statement in migration.rollback_sql:
                    connection.execute(statement)
                connection.execute(f"PRAGMA user_version = {migration.from_version}")
                _assert_integrity(connection, "rolled-back database")
                connection.commit()
            except Exception as exc:
                connection.rollback()
                if isinstance(exc, MigrationError):
                    raise MigrationError(
                        f"rollback failed: {exc}", backup_path=backup_path
                    ) from exc
                raise MigrationError(
                    f"rollback failed: {exc}", backup_path=backup_path
                ) from exc

            return RollbackResult(
                from_version=current,
                to_version=migration.from_version,
                rolled_back_migration_id=migration.migration_id,
                backup_path=backup_path,
                backup_verified=True,
            )
        finally:
            connection.close()


__all__ = [
    "MigrationError",
    "Migration",
    "MigrationResult",
    "RollbackResult",
    "SQLiteMigrationRunner",
]
