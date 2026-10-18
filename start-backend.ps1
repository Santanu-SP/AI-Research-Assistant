# This script activates the virtual environment and starts the backend server

# Ensure we are in the correct directory (the script's directory)
Set-Location $PSScriptRoot

Write-Host "Activating virtual environment..."
# Check if the virtual environment exists
if (-Not (Test-Path ".\backend\venv\Scripts\Activate.ps1")) {
    Write-Host "Virtual environment not found! Please run 'python -m venv backend\venv' first." -ForegroundColor Red
    exit 1
}

# Run the activation script
. ".\backend\venv\Scripts\Activate.ps1"

Write-Host "Starting FastAPI backend server..."
# Start the uvicorn server with hot-reload enabled
uvicorn app.main:app --app-dir backend --reload
