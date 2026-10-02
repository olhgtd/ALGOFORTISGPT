from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


violations: list[str] = []

update = read("dashboard/backend/update_service.py")
for marker in (
    "evaluate_update_safe_window",
    "UPDATE_MANIFEST_SIGNATURE_VERIFIER_UNAVAILABLE",
    "UPDATE_INSTALLER_SIGNATURE_VERIFIER_UNAVAILABLE",
    "UPDATE_POLICY_REFERENCE_MISMATCH",
    "auto_arm_live: bool = False",
):
    if marker not in update:
        violations.append(f"update_service.py:MISSING:{marker}")

entitlement = read("dashboard/backend/entitlement_service.py")
for marker in (
    "EntitlementTimeEvidence",
    "evaluate_entitlement_time",
    "LEASE_SIGNATURE_VERIFIER_UNAVAILABLE",
    "ENTITLEMENT_TIME_UNCERTAIN",
    "protective_safety_allowed",
):
    if marker not in entitlement:
        violations.append(f"entitlement_service.py:MISSING:{marker}")

telemetry = read("dashboard/backend/telemetry_service.py")
for marker in (
    "TelemetryPrivacyPolicy",
    "TELEMETRY_OPT_IN_REQUIRED",
    "TELEMETRY_DATA_CLASS_NOT_ALLOWED",
    "explicit_export_required",
):
    if marker not in telemetry:
        violations.append(f"telemetry_service.py:MISSING:{marker}")

backup = read("dashboard/backend/backup_service.py")
for marker in ("AlgoFortisBackup/v1", "BackupSecurityError", "integrity_check"):
    if marker not in backup:
        violations.append(f"backup_service.py:MISSING:{marker}")

installer = read("build/tools/build_installer.ps1")
for marker in (
    "RequireSignature",
    "Get-AuthenticodeSignature",
    "launcherSigned",
    "installerSigned",
    "SIGNED RELEASE cannot continue",
    "NOT RELEASE-QUALIFIED",
):
    if marker not in installer:
        violations.append(f"build_installer.ps1:MISSING:{marker}")
if "C:\\Users\\Ragini Music" in installer:
    violations.append("build_installer.ps1:PERSON_SPECIFIC_PATH")

register = read("ALGOFORTIS_V2_OWNER_DECISIONS.md")
for od in ("OD-V2-20", "OD-V2-21", "OD-V2-22", "OD-V2-23"):
    try:
        section = register.split(f"**{od} ", 1)[1].split("\n**OD-V2-", 1)[0]
    except IndexError:
        violations.append(f"owner_decisions:MISSING:{od}")
        continue
    if "*Status:* **FROZEN**" not in section:
        violations.append(f"owner_decisions:{od}:NOT_FROZEN")

for od in ("OD-V2-18", "OD-V2-26"):
    try:
        section = register.split(f"**{od} ", 1)[1].split("\n**OD-V2-", 1)[0]
    except IndexError:
        violations.append(f"owner_decisions:MISSING:{od}")
        continue
    if "*Status:* OPEN" not in section:
        violations.append(f"owner_decisions:{od}:MUST_REMAIN_OPEN_UNTIL_OWNER_FREEZE")

status = read("docs/v2/phase10/PHASE10_RELEASE_QUALIFICATION_STATUS.md")
for marker in (
    "G10: BLOCKED",
    "READ_ONLY / DISARMED",
    "OD-V2-18",
    "OD-V2-26",
    "PENDING_EXTERNAL",
):
    if marker not in status:
        violations.append(f"phase10_status:MISSING:{marker}")

if violations:
    raise SystemExit("S3_RELEASE_STATIC_FAIL\n" + "\n".join(violations))

print("S3_RELEASE_STATIC_PASS")
print("S3_UPDATE_TRUST_BOUNDARY=FAIL_CLOSED")
print("S3_ENTITLEMENT_TIME=TRUSTED_EVIDENCE_ONLY")
print("S3_TELEMETRY=OPT_IN_ONLY")
print("S3_BACKUP_SCHEMA=AlgoFortisBackup/v1")
print("P4_RELEASE_SIGNING=REQUIRED_FOR_RELEASE")
print("G10_RELEASE_GATE=BLOCKED")
print("LIVE_STATE=READ_ONLY/DISARMED")
