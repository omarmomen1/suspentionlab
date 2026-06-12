# Run this script to start the application
Write-Host "Ensuring Docker Desktop is running..."
$process = Get-Process -Name "Docker Desktop" -ErrorAction SilentlyContinue
if (-not $process) {
    Write-Host "Starting Docker Desktop..."
    Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe"
    Write-Host "Waiting for Docker Engine to start (this might take a minute)..."
    Start-Sleep -Seconds 20
}

Write-Host "Stopping any running containers..."
docker-compose down

Write-Host "Rebuilding and starting SuspensionLab PRO..."
docker-compose up --build -d

Write-Host ""
Write-Host "========================================="
Write-Host "Application is booting in the background!"
Write-Host "Next.js UI will be available at: http://localhost:3000"
Write-Host "API Gateway will be available at: http://localhost:8000"
Write-Host "To view logs, run: docker-compose logs -f"
Write-Host "========================================="
