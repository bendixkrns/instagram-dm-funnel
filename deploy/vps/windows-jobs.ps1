# Example for Windows Task Scheduler. Run this file manually for one job;
# creating scheduled tasks remains a separate user decision.
param(
    [ValidateSet('kommentare','dms','keyword_dm','kennzahlen','warteschlange')]
    [string]$Job = 'kommentare'
)
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$pythonExe = (Get-Command python).Source
& $pythonExe -X utf8 (Join-Path $projectRoot 'tools\automation\run.py') $Job
exit $LASTEXITCODE
