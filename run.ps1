$ErrorActionPreference = "Stop"

# Get the script directory
$ProjectRoot = $PSScriptRoot

Write-Host "🚀 Starting Market Research Agent..." -ForegroundColor Cyan

# 1. Start Backend in a separate window
# Resolve a working Python: backend/.venv first, then root .venv, then PATH python.
# (backend/.venv can go stale — e.g. after moving machines/Anaconda — which left
#  the backend window dying instantly with "Cannot connect to backend".)
$Candidates = @(
    (Join-Path $ProjectRoot "backend\.venv\Scripts\python.exe"),
    (Join-Path $ProjectRoot ".venv\Scripts\python.exe"),
    "python"
)
$PythonExe = $Candidates | Where-Object { ($_ -eq "python") -or (Test-Path $_) } | Select-Object -First 1

if (-not $PythonExe) {
    Write-Host "Python virtual environment not found in backend/.venv or .venv!" -ForegroundColor Yellow
    Write-Host "Please run setup instructions in README.md first."
    exit 1
}
Write-Host "Using Python: $PythonExe" -ForegroundColor DarkGray

Write-Host "Starting FastAPI Backend (Port 8000)..." -ForegroundColor Green
Start-Process -FilePath $PythonExe -ArgumentList "-m uvicorn backend.main:app --reload --port 8000" -WorkingDirectory $ProjectRoot -WindowStyle Normal

# 2. Start Frontend in a separate window
$FrontendDir = Join-Path $ProjectRoot "frontend"

Write-Host "Starting Next.js Frontend (Port 3000, or next available)..." -ForegroundColor Green
Start-Process -FilePath "npm" -ArgumentList "run dev" -WorkingDirectory $FrontendDir -WindowStyle Normal

# 3. Start the LiveKit voice worker (only if LIVEKIT_URL is configured).
# Runs in its own window so it survives independently; the browser "Start Voice"
# button needs this process alive in order to hear the advisor.
$EnvFile = Join-Path $ProjectRoot "backend\.env"
$LivekitConfigured = $false
if (Test-Path $EnvFile) {
    $LivekitConfigured = (Get-Content $EnvFile | Where-Object { $_ -match '^\s*LIVEKIT_URL\s*=\s*\S+' }) -ne $null
}
if ($LivekitConfigured) {
    Write-Host "Starting LiveKit Voice Worker (advisory-room)..." -ForegroundColor Green
    Start-Process -FilePath $PythonExe -ArgumentList "-m backend.voice_agent.worker" -WorkingDirectory $ProjectRoot -WindowStyle Normal
} else {
    Write-Host "Skipping voice worker (LIVEKIT_URL not set in backend/.env)." -ForegroundColor DarkGray
}

Write-Host "✅ All servers are starting in separate windows." -ForegroundColor Cyan
Write-Host "Backend: http://localhost:8000/docs"
Write-Host "Frontend: http://localhost:3000"
