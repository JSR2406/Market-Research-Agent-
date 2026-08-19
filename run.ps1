$ErrorActionPreference = "Stop"

# Get the script directory
$ProjectRoot = $PSScriptRoot

Write-Host "🚀 Starting Market Research Agent..." -ForegroundColor Cyan

# 1. Start Backend in a separate window
$BackendDir = Join-Path $ProjectRoot "backend"
$PythonExe = Join-Path $BackendDir ".venv\Scripts\python.exe"

if (-not (Test-Path $PythonExe)) {
    Write-Host "⚠️ Python virtual environment not found in backend/.venv!" -ForegroundColor Yellow
    Write-Host "Please run setup instructions in README.md first."
    exit 1
}

Write-Host "Starting FastAPI Backend (Port 8000)..." -ForegroundColor Green
Start-Process -FilePath $PythonExe -ArgumentList "-m uvicorn backend.main:app --reload --port 8000" -WorkingDirectory $ProjectRoot -WindowStyle Normal

# 2. Start Frontend in a separate window
$FrontendDir = Join-Path $ProjectRoot "frontend"

Write-Host "Starting Next.js Frontend (Port 3000, or next available)..." -ForegroundColor Green
Start-Process -FilePath "npm" -ArgumentList "run dev" -WorkingDirectory $FrontendDir -WindowStyle Normal

Write-Host "✅ Both servers are starting in separate windows." -ForegroundColor Cyan
Write-Host "Backend: http://localhost:8000/docs"
Write-Host "Frontend: http://localhost:3000"
