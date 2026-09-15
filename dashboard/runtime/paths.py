"""One explicit runtime layout; immutable resources never hold mutable state."""
from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import tempfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class RuntimeMode(str, Enum):
    DEVELOPMENT = "DEVELOPMENT"
    TEST = "TEST"
    PRODUCTION = "PRODUCTION"


def atomic_json(path: Path, value: dict) -> None:
    fd, name = tempfile.mkstemp(prefix=".pending-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def is_symlink_or_reparse(path: Path | str) -> bool:
    try:
        p = Path(path)
        if p.is_symlink():
            return True
        if hasattr(p, "is_junction") and p.is_junction():
            return True
        if hasattr(os.path, "isjunction") and os.path.isjunction(p):
            return True
        if os.name == "nt":
            try:
                st = os.lstat(p)
                attrs = getattr(st, "st_file_attributes", 0)
                if attrs & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400):
                    return True
            except (OSError, ValueError):
                pass
    except (OSError, ValueError):
        pass
    return False


def check_no_symlink_or_reparse(path: Path | str) -> None:
    p = Path(path)
    for target in (p, *p.parents):
        if is_symlink_or_reparse(target):
            raise ValueError(f"Runtime root cannot traverse a symlink or junction: {target}")


class CurrentUserAcl:
    """Create/validate a private per-user Windows directory, without elevation."""
    def _run(self, root: Path, create: bool = False) -> bool:
        # Paths go through the environment, never through executable shell text.
        script = r'''
$ErrorActionPreference = 'Stop'
$target = $env:ALGOFORTIS_ACL_TARGET
if (-not $target) { $target = $env:SENTINELX_ACL_TARGET }
$sid = [Security.Principal.WindowsIdentity]::GetCurrent().User
if ($env:ALGOFORTIS_ACL_CREATE -eq '1' -or $env:SENTINELX_ACL_CREATE -eq '1') {
  [IO.Directory]::CreateDirectory($target) | Out-Null
  $acl = New-Object Security.AccessControl.DirectorySecurity
  $acl.SetAccessRuleProtection($true, $false)
  $acl.SetOwner($sid)
  foreach ($identity in @($sid, [Security.Principal.SecurityIdentifier]'S-1-5-18')) {
    $rule = New-Object Security.AccessControl.FileSystemAccessRule($identity, 'FullControl', 'ContainerInherit,ObjectInherit', 'None', 'Allow')
    $acl.AddAccessRule($rule)
  }
  Set-Acl -LiteralPath $target -AclObject $acl
  Get-ChildItem -LiteralPath $target -Recurse -Force -ErrorAction SilentlyContinue | ForEach-Object {
    Set-Acl -LiteralPath $_.FullName -AclObject $acl
  }
}
$items = @(Get-Item -LiteralPath $target) + @(Get-ChildItem -LiteralPath $target -Recurse -Force)
foreach ($item in $items) {
  if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { exit 1 }
  $acl = Get-Acl -LiteralPath $item.FullName
  $owner = $acl.GetOwner([Security.Principal.SecurityIdentifier]).Value
  if ($owner -notin @($sid.Value, 'S-1-5-18', 'S-1-5-32-544')) { exit 1 }
  $hasUser = $false
  foreach ($rule in $acl.GetAccessRules($true, $true, [Security.Principal.SecurityIdentifier])) {
    if ($rule.AccessControlType -eq 'Allow') {
      if ($rule.IdentityReference.Value -notin @($sid.Value, 'S-1-5-18', 'S-1-5-32-544', 'S-1-3-4')) { exit 1 }
      if ($rule.IdentityReference.Value -in @($sid.Value, 'S-1-3-4')) { $hasUser = $true }
    }
  }
  if (-not $hasUser) { exit 1 }
}
'''
        win_modules = str(Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "WindowsPowerShell" / "v1.0" / "Modules")
        env = {
            **os.environ,
            "ALGOFORTIS_ACL_TARGET": str(root),
            "SENTINELX_ACL_TARGET": str(root),
            "ALGOFORTIS_ACL_CREATE": "1" if create else "0",
            "SENTINELX_ACL_CREATE": "1" if create else "0",
            "PSModulePath": win_modules,
        }
        result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                                env=env, capture_output=True, timeout=30,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return result.returncode == 0

    def validate(self, data_root: Path) -> bool:
        return self._run(data_root)


@dataclass(frozen=True)
class RuntimePaths:
    mode: RuntimeMode
    install: Path
    root: Path
    unresolved_root: Path | None = None

    @classmethod
    def resolve(cls, mode: RuntimeMode | str, *, install_root: Path | None = None,
                data_root: Path | None = None, environ=None) -> "RuntimePaths":
        mode = RuntimeMode(mode)
        env = os.environ if environ is None else environ
        install = Path(install_root or Path(__file__).resolve().parents[2]).resolve()
        local = env.get("LOCALAPPDATA")
        raw_local = Path(local) if local else None

        if mode is RuntimeMode.PRODUCTION:
            if not local or not raw_local.is_absolute():
                raise ValueError("Production requires an absolute Windows LOCALAPPDATA location")
            check_no_symlink_or_reparse(raw_local)
            
            # Primary production root is %LOCALAPPDATA%\AlgoFortis
            raw_production = raw_local / "AlgoFortis"
            legacy_production = raw_local / "SentinelX"
            
            if data_root is not None:
                raw_data_root = Path(data_root)
                if not raw_data_root.is_absolute():
                    raise ValueError("Production requires an absolute Windows LOCALAPPDATA location")
                check_no_symlink_or_reparse(raw_data_root)
                unresolved_root = raw_data_root
            else:
                unresolved_root = raw_production
                
            check_no_symlink_or_reparse(unresolved_root)
            production = raw_local.resolve() / "AlgoFortis"
            legacy_resolved = raw_local.resolve() / "SentinelX"
            root = unresolved_root.resolve()
            
            # Accept either primary AlgoFortis or legacy SentinelX path during migration
            if root != production and root != legacy_resolved:
                raise ValueError("Production data root must be LOCALAPPDATA/AlgoFortis")
        elif mode is RuntimeMode.TEST:
            if data_root is None or not Path(data_root).is_absolute():
                raise ValueError("TEST requires an explicit isolated absolute data root")
            raw_data_root = Path(data_root)
            check_no_symlink_or_reparse(raw_data_root)
            unresolved_root = raw_data_root
            root = raw_data_root.resolve()
            if not root.is_relative_to(Path(tempfile.gettempdir()).resolve()):
                raise ValueError("TEST data must be isolated in the system temporary directory")
        else:
            raw_data_root = Path(data_root or install / ".algofortis-dev-data")
            if not raw_data_root.exists() and (install / ".sentinelx-dev-data").exists() and data_root is None:
                raw_data_root = install / ".sentinelx-dev-data"
            check_no_symlink_or_reparse(raw_data_root)
            unresolved_root = raw_data_root
            root = raw_data_root.resolve()

        production_resolved = raw_local.resolve() / "AlgoFortis" if raw_local else None
        legacy_resolved = raw_local.resolve() / "SentinelX" if raw_local else None
        
        for p_res in (production_resolved, legacy_resolved):
            if p_res is not None:
                if mode is not RuntimeMode.PRODUCTION and (
                    root == p_res or root.is_relative_to(p_res)
                    or unresolved_root == p_res or (unresolved_root and unresolved_root.is_relative_to(p_res))
                ):
                    raise ValueError("Non-production modes cannot use production data")
                    
        if mode is RuntimeMode.PRODUCTION and (
            root == install or root.is_relative_to(install)
            or unresolved_root == install or (unresolved_root and unresolved_root.is_relative_to(install))
        ):
            raise ValueError("Mutable production data cannot be in the installation")
        return cls(mode, install, root, unresolved_root=unresolved_root)

    @property
    def databases(self): return self.root / "databases"
    @property
    def config(self): return self.root / "config"
    @property
    def logs(self): return self.root / "logs"
    @property
    def cache(self): return self.root / "cache"
    @property
    def state(self): return self.root / "runtime"
    @property
    def imports(self): return self.root / "imports"
    @property
    def artifacts(self): return self.root / "users"
    @property
    def frontend(self): return self.install / "dashboard" / "web" / "dist"

    def prepare(self) -> None:
        # Reject redirected paths before creating children or writing secrets.
        paths_to_check = [self.root, *self.root.parents]
        if self.unresolved_root is not None:
            paths_to_check.extend([self.unresolved_root, *self.unresolved_root.parents])
        for path in paths_to_check:
            if is_symlink_or_reparse(path):
                raise ValueError(f"Runtime root cannot traverse a symlink or junction: {path}")
                
        # Deterministic legacy migration from %LOCALAPPDATA%\SentinelX if migrating
        if self.mode is RuntimeMode.PRODUCTION and not self.root.exists():
            local = os.environ.get("LOCALAPPDATA")
            if local:
                legacy_root = Path(local) / "SentinelX"
                if legacy_root.exists() and not is_symlink_or_reparse(legacy_root):
                    # Copy existing databases and configuration to %LOCALAPPDATA%\AlgoFortis
                    acl = CurrentUserAcl()
                    acl._run(self.root, create=True)
                    for item in legacy_root.iterdir():
                        dest = self.root / item.name
                        if not dest.exists():
                            if item.is_dir():
                                shutil.copytree(item, dest)
                            else:
                                shutil.copy2(item, dest)
                    acl._run(self.root, create=True)

        if os.name == "nt":
            acl = CurrentUserAcl()
            if not self.root.exists():
                if not acl._run(self.root, create=True):
                    if self.mode is RuntimeMode.TEST and (
                        os.environ.get("ALGOFORTIS_TEST_ALLOW_INSECURE_ACL") == "1" or
                        os.environ.get("SENTINELX_TEST_ALLOW_INSECURE_ACL") == "1"
                    ):
                        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
                    else:
                        raise PermissionError("Runtime data requires a private current-user ACL")

            if not acl.validate(self.root):
                if self.mode is RuntimeMode.TEST and (
                    os.environ.get("ALGOFORTIS_TEST_ALLOW_INSECURE_ACL") == "1" or
                    os.environ.get("SENTINELX_TEST_ALLOW_INSECURE_ACL") == "1"
                ):
                    pass
                else:
                    raise PermissionError("Runtime data requires a private current-user ACL")
        else:
            self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
            self.root.chmod(0o700)
        for directory in (self.databases, self.config, self.logs, self.cache, self.state, self.imports, self.artifacts):
            directory.mkdir(exist_ok=True, mode=0o700)
