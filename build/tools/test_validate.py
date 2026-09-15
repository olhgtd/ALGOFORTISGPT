import os
import subprocess
from pathlib import Path
from dashboard.runtime.paths import RuntimePaths, RuntimeMode

paths = RuntimePaths.resolve(RuntimeMode.PRODUCTION)
print("Root:", paths.root)
print("Root exists:", paths.root.exists())

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
}
$items = @(Get-Item -LiteralPath $target) + @(Get-ChildItem -LiteralPath $target -Recurse -Force)
foreach ($item in $items) {
  if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { Write-Host "REPARSE: $($item.FullName)"; exit 1 }
  $acl = Get-Acl -LiteralPath $item.FullName
  $owner = $acl.GetOwner([Security.Principal.SecurityIdentifier]).Value
  if ($owner -notin @($sid.Value, 'S-1-5-18', 'S-1-5-32-544')) { Write-Host "BAD_OWNER: $owner on $($item.FullName)"; exit 1 }
  $hasUser = $false
  foreach ($rule in $acl.GetAccessRules($true, $true, [Security.Principal.SecurityIdentifier])) {
    if ($rule.AccessControlType -eq 'Allow') {
      if ($rule.IdentityReference.Value -notin @($sid.Value, 'S-1-5-18', 'S-1-5-32-544', 'S-1-3-4')) { Write-Host "BAD_ACE: $($rule.IdentityReference.Value) on $($item.FullName)"; exit 1 }
      if ($rule.IdentityReference.Value -in @($sid.Value, 'S-1-3-4')) { $hasUser = $true }
    }
  }
  if (-not $hasUser) { Write-Host "NO_USER: $($item.FullName)"; exit 1 }
}
Write-Host "ALL_PASSED_SUCCESSFULLY"
'''

win_modules = str(Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "WindowsPowerShell" / "v1.0" / "Modules")
env = {**os.environ, "SENTINELX_ACL_TARGET": str(paths.root), "SENTINELX_ACL_CREATE": "0", "PSModulePath": win_modules}
res = subprocess.run(
    ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
    env=env,
    capture_output=True,
    text=True,
    timeout=30
)
print("Returncode:", res.returncode)
print("Stdout:", res.stdout.strip())
print("Stderr:", res.stderr.strip())

try:
    paths.prepare()
    print("paths.prepare() SUCCEEDED!")
except Exception as ex:
    print("paths.prepare() FAILED:", type(ex), ex)
