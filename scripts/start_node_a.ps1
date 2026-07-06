$ErrorActionPreference = "Stop"
$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $ProjectRoot

$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    $Python = "python"
}

$env:NODE_ID = "node-a"
$env:NODE_HOST = "127.0.0.1"
$env:NODE_PORT = "8000"
$env:PUBLIC_NODE_URL = "http://127.0.0.1:8000"
$env:NETWORK_NAME = "zoidberg-testnet"
$env:DATA_DIR = "data/node-a"
$env:NODE_DATA_DIR = "data/node-a"
$env:STORAGE_BACKEND = "json"

New-Item -ItemType Directory -Force -Path (Join-Path $ProjectRoot $env:NODE_DATA_DIR) | Out-Null
if (-not (Test-Path (Join-Path $ProjectRoot "$($env:NODE_DATA_DIR)/blockchain.json"))) {
    Write-Warning "No node-a blockchain found. Run .\scripts\init_two_node_data.ps1 first for matching genesis hashes."
}

& $Python -m uvicorn api:app --host $env:NODE_HOST --port $env:NODE_PORT
