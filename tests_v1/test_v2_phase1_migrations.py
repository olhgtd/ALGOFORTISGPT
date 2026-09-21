"""Phase 1 RED tests for AF2-ARC-004 migration safety foundation."""

from __future__ import annotations

import sqlite3

import pytest

from engine.persistence.migrations import (
    Migration,
    MigrationError,
    SQLiteMigrationRunner,
)


def _create_baseline(path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.execute("CREATE TABLE baseline (id INTEGER PRIMARY KEY, value TEXT NOT NULL)")
        connection.execute("INSERT INTO baseline(value) VALUES ('before')")
        connection.execute("PRAGMA user_version = 1")
        connection.commit()
    finally:
        connection.close()


def _migration_v1_to_v2() -> Migration:
    return Migration(
        migration_id="001_add_notes",
        from_version=1,
        to_version=2,
        apply_sql=(
            "CREATE TABLE notes (id INTEGER PRIMARY KEY, body TEXT NOT NULL)",
            "INSERT INTO notes(body) VALUES ('migrated')",
        ),
        rollback_sql=("DROP TABLE notes",),
    )


def _tables(path) -> set[str]:
    connection = sqlite3.connect(path)
    try:
        return {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ).fetchall()
        }
    finally:
        connection.close()


def _user_version(path) -> int:
    connection = sqlite3.connect(path)
    try:
        return int(connection.execute("PRAGMA user_version").fetchone()[0])
    finally:
        connection.close()


def test_migration_creates_verified_pre_backup_before_mutation(tmp_path) -> None:
    database = tmp_path / "state.db"
    backup_dir = tmp_path / "backups"
    _create_baseline(database)

    result = SQLiteMigrationRunner(database, backup_dir).migrate(
        (_migration_v1_to_v2(),),
        target_version=2,
    )

    assert result.from_version == 1
    assert result.to_version == 2
    assert result.applied_migration_ids == ("001_add_notes",)
    assert result.backup_path.is_file()
    assert result.backup_verified is True

    assert _user_version(database) == 2
    assert "notes" in _tables(database)

    # Backup must represent the exact pre-migration state.
    assert _user_version(result.backup_path) == 1
    assert "notes" not in _tables(result.backup_path)
    backup = sqlite3.connect(result.backup_path)
    try:
        assert backup.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert backup.execute("SELECT value FROM baseline").fetchone()[0] == "before"
    finally:
        backup.close()


def test_explicit_rollback_backs_up_then_reverses_latest_migration(tmp_path) -> None:
    database = tmp_path / "state.db"
    backup_dir = tmp_path / "backups"
    _create_baseline(database)
    runner = SQLiteMigrationRunner(database, backup_dir)
    migration = _migration_v1_to_v2()
    runner.migrate((migration,), target_version=2)

    result = runner.rollback_last((migration,))

    assert result.from_version == 2
    assert result.to_version == 1
    assert result.rolled_back_migration_id == "001_add_notes"
    assert result.backup_path.is_file()
    assert result.backup_verified is True
    assert _user_version(database) == 1
    assert "notes" not in _tables(database)

    # Rollback backup must preserve the successfully migrated state.
    assert _user_version(result.backup_path) == 2
    assert "notes" in _tables(result.backup_path)


def test_failed_migration_rolls_back_database_and_retains_verified_backup(tmp_path) -> None:
    database = tmp_path / "state.db"
    backup_dir = tmp_path / "backups"
    _create_baseline(database)
    broken = Migration(
        migration_id="001_broken",
        from_version=1,
        to_version=2,
        apply_sql=(
            "CREATE TABLE should_not_survive (id INTEGER PRIMARY KEY)",
            "INSERT INTO missing_table(value) VALUES ('boom')",
        ),
        rollback_sql=("DROP TABLE should_not_survive",),
    )

    runner = SQLiteMigrationRunner(database, backup_dir)
    with pytest.raises(MigrationError, match="migration failed") as captured:
        runner.migrate((broken,), target_version=2)

    assert _user_version(database) == 1
    assert "should_not_survive" not in _tables(database)
    assert captured.value.backup_path is not None
    assert captured.value.backup_path.is_file()
    assert _user_version(captured.value.backup_path) == 1


def test_migration_plan_rejects_duplicates_gaps_and_missing_rollback(tmp_path) -> None:
    database = tmp_path / "state.db"
    _create_baseline(database)
    runner = SQLiteMigrationRunner(database, tmp_path / "backups")
    first = _migration_v1_to_v2()

    duplicate = Migration(
        migration_id="001_add_notes",
        from_version=2,
        to_version=3,
        apply_sql=("CREATE TABLE extra (id INTEGER)",),
        rollback_sql=("DROP TABLE extra",),
    )
    with pytest.raises(MigrationError, match="duplicate"):
        runner.migrate((first, duplicate), target_version=3)

    gap = Migration(
        migration_id="002_gap",
        from_version=3,
        to_version=4,
        apply_sql=("CREATE TABLE gap_table (id INTEGER)",),
        rollback_sql=("DROP TABLE gap_table",),
    )
    with pytest.raises(MigrationError, match="contiguous"):
        runner.migrate((first, gap), target_version=4)

    irreversible = Migration(
        migration_id="001_irreversible",
        from_version=1,
        to_version=2,
        apply_sql=("CREATE TABLE irreversible (id INTEGER)",),
        rollback_sql=(),
    )
    with pytest.raises(MigrationError, match="rollback"):
        runner.migrate((irreversible,), target_version=2)


def test_migration_refuses_unknown_current_or_downgrade_target(tmp_path) -> None:
    database = tmp_path / "state.db"
    _create_baseline(database)
    runner = SQLiteMigrationRunner(database, tmp_path / "backups")
    migration = _migration_v1_to_v2()

    with pytest.raises(MigrationError, match="downgrade"):
        runner.migrate((migration,), target_version=0)

    connection = sqlite3.connect(database)
    try:
        connection.execute("PRAGMA user_version = 9")
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(MigrationError, match="current version"):
        runner.migrate((migration,), target_version=10)
