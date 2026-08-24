$ErrorActionPreference = "Stop"
$skillRoot = Split-Path -Parent $PSScriptRoot
$targetRoot = "C:\Users\Administrator\.codex\skills\translate-scan-pdf-professionally"
New-Item -ItemType Directory -Force -Path $targetRoot | Out-Null
robocopy $skillRoot $targetRoot /E /PURGE /XD __pycache__ /XF *.pyc | Out-Null
if ($LASTEXITCODE -gt 7) { throw "robocopy failed with exit code $LASTEXITCODE" }

$sourceFiles = Get-ChildItem $skillRoot -Recurse -File | Where-Object { $_.Extension -ne ".pyc" }
foreach ($sourceFile in $sourceFiles) {
    $relative = $sourceFile.FullName.Substring($skillRoot.Length + 1)
    $target = Join-Path $targetRoot $relative
    if (!(Test-Path $target)) { throw "Missing installed file: $relative" }
    if ((Get-FileHash $sourceFile.FullName -Algorithm SHA256).Hash -ne (Get-FileHash $target -Algorithm SHA256).Hash) {
        throw "Installed file hash mismatch: $relative"
    }
}
Write-Output "Installed and hash-verified: $targetRoot"
