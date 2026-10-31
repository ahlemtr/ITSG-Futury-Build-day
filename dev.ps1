# Local dev in one command: Postgres + Neo4j (Docker), API on :8000 (own window), UI on :5173 (this window).
#   ./dev.ps1           start everything
#   ./dev.ps1 -Reset    reset Postgres and the graph to the VB 13.3 starting point first
param([switch]$Reset)
# not "Stop": in Windows PowerShell any stderr line of docker/uv/npm would abort the script; exit codes are checked instead
$ErrorActionPreference = "Continue"
Set-Location $PSScriptRoot

function Wait-Port([int]$Port, [string]$Name, [int]$Seconds = 120) {
    Write-Host "waiting for $Name on :$Port ..."
    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        $client = New-Object Net.Sockets.TcpClient
        try { $client.Connect("127.0.0.1", $Port); return } catch { Start-Sleep -Seconds 2 } finally { $client.Dispose() }
    }
    throw "$Name did not come up on :$Port within $Seconds s"
}

# Docker Desktop: start it when the engine is not reachable
docker info *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host "starting Docker Desktop ..."
    Start-Process "$env:ProgramFiles\Docker\Docker\Docker Desktop.exe"
    $deadline = (Get-Date).AddSeconds(180)
    do {
        if ((Get-Date) -gt $deadline) { throw "Docker engine did not start within 180 s" }
        Start-Sleep -Seconds 3
        docker info *> $null
    } while ($LASTEXITCODE -ne 0)
}

docker compose up -d postgres neo4j
if ($LASTEXITCODE -ne 0) { throw "docker compose up failed" }
Wait-Port 5432 "Postgres"
Wait-Port 7687 "Neo4j"

# set here so the API window inherits them; the shell's VIRTUAL_ENV would only make uv warn
$env:SPEC_BASELINE = "VB@13.3"
$env:SEED_ON_START = "0"
Remove-Item Env:VIRTUAL_ENV -ErrorAction SilentlyContinue
Remove-Item Env:PYTHON_DOTENV_DISABLED -ErrorAction SilentlyContinue  # left over from a no-Docker run, it would hide .env (OpenAI key, DB URLs)

if ($Reset) {
    uv run python -m tools.reset_baseline
    if ($LASTEXITCODE -ne 0) { throw "reset failed" }
}

Start-Process powershell -WorkingDirectory $PSScriptRoot -ArgumentList "-NoExit", "-Command", "uv run uvicorn api.main:app --port 8000"
Wait-Port 8000 "API"

if (-not (Test-Path ui/node_modules)) { npm --prefix ui install }
npm --prefix ui run dev
