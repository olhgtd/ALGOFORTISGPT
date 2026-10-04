$target = "$env:LOCALAPPDATA\AlgoFortis"
if (-not (Test-Path $target)) {
    $target = "$env:LOCALAPPDATA\AlgoFortis"
}
$sid = [Security.Principal.WindowsIdentity]::GetCurrent().User
$items = @(Get-Item -LiteralPath $target) + @(Get-ChildItem -LiteralPath $target -Recurse -Force)
$fails = 0
foreach ($item in $items) {
    if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
        Write-Host "ReparsePoint on: $($item.FullName)"
        $fails++
    }
    $acl = Get-Acl -LiteralPath $item.FullName
    $owner = $acl.GetOwner([Security.Principal.SecurityIdentifier]).Value
    if ($owner -notin @($sid.Value, 'S-1-5-18', 'S-1-5-32-544')) {
        Write-Host "Bad owner: $owner on $($item.FullName)"
        $fails++
    }
    $hasUser = $false
    foreach ($rule in $acl.GetAccessRules($true, $true, [Security.Principal.SecurityIdentifier])) {
        if ($rule.AccessControlType -eq 'Allow') {
            if ($rule.IdentityReference.Value -notin @($sid.Value, 'S-1-5-18', 'S-1-5-32-544', 'S-1-3-4')) {
                Write-Host "Bad ACE: $($rule.IdentityReference.Value) on $($item.FullName)"
                $fails++
            }
            if ($rule.IdentityReference.Value -in @($sid.Value, 'S-1-3-4')) { $hasUser = $true }
        }
    }
    if (-not $hasUser) {
        Write-Host "No user rule on: $($item.FullName)"
        $fails++
    }
}
Write-Host "Scan complete. Total failure points: $fails"
