# Run this script with PowerShell to create a Desktop shortcut for Keyboard & Mouse Switch on this computer.
# It automatically detects the project folder wherever you placed it.

$ErrorActionPreference = 'Stop'

# Project directory dynamically resolved based on this script's location
$projectDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# Locate windowless pythonw.exe inside local virtualenv or uv cache
$pythonw = Join-Path $projectDir ".venv\Scripts\pythonw.exe"
$python = Join-Path $projectDir ".venv\Scripts\python.exe"

if (-not (Test-Path $pythonw)) {
    # If .venv does not exist yet, try creating it with uv
    $uv = Get-Command "uv" -ErrorAction SilentlyContinue
    if ($uv) {
        Write-Host "Local virtual environment not found. Running 'uv sync'..." -ForegroundColor Cyan
        Start-Process -FilePath "uv" -ArgumentList "sync" -WorkingDirectory $projectDir -Wait -NoNewWindow
    }
}

if (-not (Test-Path $pythonw)) {
    Write-Warning "Could not find '.venv\Scripts\pythonw.exe'. Please run 'uv sync' in this folder first."
    exit 1
}

# Determine Desktop path dynamically for current user
$desktop = [System.Environment]::GetFolderPath('Desktop')
$shortcutPath = Join-Path $desktop "Keyboard & Mouse Switch.lnk"

# Create Desktop Shortcut via WScript.Shell
$wsh = New-Object -ComObject WScript.Shell
$shortcut = $wsh.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $pythonw
$shortcut.Arguments = "main.py"
$shortcut.WorkingDirectory = $projectDir
$shortcut.Description = "Keyboard & Mouse Switch"

# Use python.exe icon if available, otherwise fallback to shell icon
if (Test-Path $python) {
    $shortcut.IconLocation = "$python, 0"
} else {
    $shortcut.IconLocation = "$pythonw, 0"
}

$shortcut.Save()

Write-Host "Success! Created shortcut at: $shortcutPath" -ForegroundColor Green
Write-Host "Target: $pythonw main.py (runs silently with no terminal)" -ForegroundColor Gray

