"""Phase 7 NTFS ACL & Symlink/Junction/Reparse Certification for SentinelX."""
import os
import sys
import tempfile
import subprocess
from pathlib import Path

# Ensure we import strictly from the clean product tree
clean_root = Path(__file__).resolve().parents[2]
if str(clean_root) not in sys.path:
    sys.path.insert(0, str(clean_root))

from dashboard.runtime.paths import (
    RuntimePaths,
    RuntimeMode,
    CurrentUserAcl,
    check_no_symlink_or_reparse,
    is_symlink_or_reparse,
)

def log(msg):
    print(f"[PHASE 7 ACL] {msg}")


def _grant_everyone_access(target: Path, rights: str) -> None:
    """Inject a deliberate broad ACL rule using the well-known Everyone SID.

    Use the same SID-based, non-interactive PowerShell shape as CurrentUserAcl
    so certification is independent of localized account-name translation.
    """
    script = r'''
$ErrorActionPreference = 'Stop'
$target = $env:ALGOFORTIS_ACL_CERT_TARGET
$rightsName = $env:ALGOFORTIS_ACL_CERT_RIGHTS
$everyone = [Security.Principal.SecurityIdentifier]'S-1-1-0'
$rights = [Enum]::Parse([Security.AccessControl.FileSystemRights], $rightsName)
$inheritance = [Security.AccessControl.InheritanceFlags]'ContainerInherit,ObjectInherit'
$propagation = [Security.AccessControl.PropagationFlags]::None
$allow = [Security.AccessControl.AccessControlType]::Allow
$acl = Get-Acl -LiteralPath $target
$rule = New-Object Security.AccessControl.FileSystemAccessRule($everyone, $rights, $inheritance, $propagation, $allow)
$acl.AddAccessRule($rule)
Set-Acl -LiteralPath $target -AclObject $acl
'''
    env = {
        **os.environ,
        "ALGOFORTIS_ACL_CERT_TARGET": str(target),
        "ALGOFORTIS_ACL_CERT_RIGHTS": rights,
    }
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise AssertionError(
            "failed to inject broad Everyone ACL for certification "
            f"(exit={result.returncode}, stdout={result.stdout!r}, stderr={result.stderr!r})"
        )

def test_acl_clean_install_isolated():
    log("Test 1: Testing CurrentUserAcl creation and strict validation in isolated directory...")
    with tempfile.TemporaryDirectory(prefix="sentinelx_acl_test_") as tmp:
        target = Path(tmp) / "SentinelX_Data"
        acl = CurrentUserAcl()
        created = acl._run(target, create=True)
        assert created, "Failed to create directory with private ACL"
        assert target.exists(), "Target directory was not created"
        valid = acl.validate(target)
        assert valid, "Freshly created private directory failed ACL validation"
        log("  PASS: Created private ACL directory validated successfully.")

        # Test broad permissions fail-closed
        log("Test 2: Verifying broad permissions fail-closed (Everyone grant)...")
        _grant_everyone_access(target, "ReadAndExecute")
        assert not acl.validate(target), "ACL validator did not reject broad 'Everyone' grant!"
        log("  PASS: Broad permission (Everyone) rejected fail-closed.")

def test_test_override_cannot_weaken_production():
    log("Test 3: Verifying SENTINELX_TEST_ALLOW_INSECURE_ACL=1 CANNOT weaken PRODUCTION mode...")
    with tempfile.TemporaryDirectory(prefix="sentinelx_override_test_") as tmp:
        appdata = Path(tmp) / "AppData" / "Local"
        appdata.mkdir(parents=True)
        
        # Point to production mode
        env = {
            "LOCALAPPDATA": str(appdata),
            "SENTINELX_TEST_ALLOW_INSECURE_ACL": "1"
        }
        # In production mode, prepare must STILL validate or enforce ACL, and fail if ACL is corrupted
        paths = RuntimePaths.resolve(RuntimeMode.PRODUCTION, install_root=clean_root, environ=env)
        paths.prepare()
        assert paths.root.exists()
        
        # Now corrupt the ACL on paths.root with an unauthorized group
        _grant_everyone_access(paths.root, "FullControl")
        
        # Now attempt prepare() again with SENTINELX_TEST_ALLOW_INSECURE_ACL=1 still set
        failed = False
        try:
            paths.prepare()
        except PermissionError:
            failed = True
        assert failed, "PRODUCTION mode allowed corrupted ACL when SENTINELX_TEST_ALLOW_INSECURE_ACL=1 was set!"
        log("  PASS: SENTINELX_TEST_ALLOW_INSECURE_ACL=1 cannot bypass PRODUCTION ACL.")

def test_symlink_and_junction_rejection():
    log("Test 4: Verifying leaf symlink rejection...")
    with tempfile.TemporaryDirectory(prefix="sentinelx_symlink_test_") as tmp:
        real_dir = Path(tmp) / "real_dir"
        real_dir.mkdir()
        link_dir = Path(tmp) / "link_leaf"
        
        # Create directory symlink
        cmd = f'cmd.exe /c mklink /D "{link_dir}" "{real_dir}"'
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if res.returncode == 0:
            assert is_symlink_or_reparse(link_dir), "mklink directory was not recognized as symlink/reparse"
            failed = False
            try:
                check_no_symlink_or_reparse(link_dir)
            except ValueError:
                failed = True
            assert failed, "check_no_symlink_or_reparse failed to reject leaf symlink!"
            log("  PASS: Leaf symlink rejected.")
        else:
            log("  (mklink requires SeCreateSymbolicLinkPrivilege; checking junction instead)")

        log("Test 5: Verifying NTFS junction rejection...")
        junction_dir = Path(tmp) / "junction_leaf"
        cmd_j = f'cmd.exe /c mklink /J "{junction_dir}" "{real_dir}"'
        res_j = subprocess.run(cmd_j, shell=True, capture_output=True, text=True)
        assert res_j.returncode == 0, f"Failed to create junction: {res_j.stderr}"
        assert is_symlink_or_reparse(junction_dir), "NTFS junction was not recognized as reparse point"
        
        failed_j = False
        try:
            check_no_symlink_or_reparse(junction_dir)
        except ValueError:
            failed_j = True
        assert failed_j, "check_no_symlink_or_reparse failed to reject NTFS junction!"
        log("  PASS: NTFS junction rejected.")

        log("Test 6: Verifying ancestor junction rejection...")
        child_in_junction = junction_dir / "nested" / "target"
        failed_anc = False
        try:
            check_no_symlink_or_reparse(child_in_junction)
        except ValueError:
            failed_anc = True
        assert failed_anc, "check_no_symlink_or_reparse failed to reject child under junction ancestor!"
        log("  PASS: Ancestor junction rejected.")

def test_install_directory_cannot_be_data_root():
    log("Test 7: Verifying install directory cannot be production data root...")
    install = Path(r"C:\Program Files\SentinelX")
    env = {"LOCALAPPDATA": str(install)}
    failed = False
    try:
        RuntimePaths.resolve(RuntimeMode.PRODUCTION, install_root=install, environ=env)
    except ValueError as e:
        failed = True
        log(f"  Caught expected violation: {e}")
    assert failed, "RuntimePaths allowed production data root to reside in install directory!"
    log("  PASS: Install directory cannot be production data root.")

if __name__ == "__main__":
    print("=== STARTING PHASE 7 NTFS ACL & SYMLINK CERTIFICATION ===")
    test_acl_clean_install_isolated()
    test_test_override_cannot_weaken_production()
    test_symlink_and_junction_rejection()
    test_install_directory_cannot_be_data_root()
    print("=== PHASE 7 NTFS ACL & SYMLINK CERTIFICATION: ALL PASS ===")
