# Start Lantern on Windows: installs requirements on first run, starts the app on 127.0.0.1:8000
# and opens the inspector, contractor and resident pages.
#   powershell -ExecutionPolicy Bypass -File app\start.ps1            # app only
#   powershell -ExecutionPolicy Bypass -File app\start.ps1 -Bot       # app + Telegram bot (needs TELEGRAM_BOT_TOKEN in .env)
param([switch]$Bot, [switch]$NoBrowser, [int]$Port = 8000)

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

python -c "import fastapi, uvicorn, multipart, httpx" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Installing requirements..."
    python -m pip install -r requirements.txt
}
if (-not (Test-Path "mock\signals.json")) {
    Write-Host "Note: mock\ is missing - unzip lantern_mock.zip into $root to replay the demo day."
}

$app = Start-Process python -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", $Port -PassThru -NoNewWindow
$base = "http://127.0.0.1:$Port"
for ($i = 0; $i -lt 30; $i++) {
    try { Invoke-RestMethod "$base/health" -TimeoutSec 2 | Out-Null; break } catch { Start-Sleep -Milliseconds 500 }
}
if (-not $NoBrowser) {
    Start-Process "$base/inspector"
    Start-Process "$base/contractor?contractor=A"
    Start-Process "$base/report"
}

$botProc = $null
if ($Bot) {
    $env:LANTERN_API_URL = $base
    $botProc = Start-Process python -ArgumentList "-m", "app.bot.telegram_bot" -PassThru -NoNewWindow
}

Write-Host ""
Write-Host "Lantern is running at $base  (API docs: $base/docs)"
Write-Host "Replay the mock day:  python -m app.demo --auto-done"
Write-Host "Press Enter to stop."
[void][Console]::ReadLine()
if ($botProc) { Stop-Process -Id $botProc.Id -ErrorAction SilentlyContinue }
Stop-Process -Id $app.Id -ErrorAction SilentlyContinue
