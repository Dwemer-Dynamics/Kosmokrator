# Launch the downloaded source without installing packages or changing agent configuration.
[CmdletBinding()]
param(
    [string]$Workspace = (Join-Path $PSScriptRoot 'work'),
    [string]$Catalog,
    [ValidateRange(1, 65535)][int]$Port = 8765,
    [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'
$candidates = @()
$localPython = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
if (Test-Path -LiteralPath $localPython -PathType Leaf) {
    $candidates += @{ Exe = $localPython; Prefix = @() }
}
foreach ($name in @('py', 'python')) {
    $command = Get-Command $name -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($command) { $candidates += @{ Exe = $command.Source; Prefix = $(if ($name -eq 'py') { @('-3') } else { @() }) } }
}
$chosen = $null
foreach ($candidate in $candidates) {
    try {
        $prefix = @($candidate.Prefix)
        & $candidate.Exe @prefix -c 'import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)' 2>$null
        if ($LASTEXITCODE -eq 0) { $chosen = $candidate; break }
    } catch { continue }
}
if (-not $chosen) { throw 'Python 3.11 or newer is required. Install Python, then run start.ps1 again.' }
if (-not (Test-Path -LiteralPath $Workspace)) { New-Item -ItemType Directory -Path $Workspace | Out-Null }
$workspacePath = (Resolve-Path -LiteralPath $Workspace).Path
$catalogPath = if ($Catalog) { (Resolve-Path -LiteralPath $Catalog).Path } else { $null }
$serveArgs = @('-m', 'kosmokrator', 'serve', '--workspace', $workspacePath, '--docs', (Join-Path $PSScriptRoot 'docs'), '--port', "$Port")
if ($catalogPath) { $serveArgs += @('--catalog', $catalogPath) }
if (-not $NoBrowser) { $serveArgs += '--open-browser' }
Push-Location -LiteralPath $PSScriptRoot
try {
    Write-Host "Projects: $workspacePath"
    Write-Host 'Keep this window open. Press Ctrl+C to stop Kosmokrator.'
    $prefix = @($chosen.Prefix)
    & $chosen.Exe @prefix @serveArgs
    $resultCode = $LASTEXITCODE
} finally { Pop-Location }
exit $resultCode
