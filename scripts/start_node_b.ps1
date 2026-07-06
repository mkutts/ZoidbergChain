$ErrorActionPreference = "Stop"
$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $ProjectRoot

$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    $Python = "python"
}

$env:NODE_ID = "node-b"
$env:NODE_HOST = "127.0.0.1"
$env:NODE_PORT = "8001"
$env:PUBLIC_NODE_URL = "http://127.0.0.1:8001"
$env:NETWORK_NAME = "zoidberg-testnet"
$env:DATA_DIR = "data/node-b"
$env:NODE_DATA_DIR = "data/node-b"
$env:STORAGE_BACKEND = "json"

New-Item -ItemType Directory -Force -Path (Join-Path $ProjectRoot $env:NODE_DATA_DIR) | Out-Null
if (-not (Test-Path (Join-Path $ProjectRoot "$($env:NODE_DATA_DIR)/blockchain.json"))) {
    Write-Warning "No node-b blockchain found. Run .\scripts\init_two_node_data.ps1 first for matching genesis hashes."
}

& $Python -m uvicorn api:app --host $env:NODE_HOST --port $env:NODE_PORT
