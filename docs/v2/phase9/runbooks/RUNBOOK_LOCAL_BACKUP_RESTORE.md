# Phase 9 Local Backup/Restore Runbook

Version: `RUNBOOK_LOCAL_BACKUP_RESTORE/v1`

Verify `AlgoFortisBackup/v1`, checksums and forbidden-secret exclusions. Restore only into an isolated target. Never overwrite active runtime state. Record deterministic step evidence and PASS/FAIL. Live state is not changed by this runbook.
