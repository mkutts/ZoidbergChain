param(
    [switch]$Reset
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $ProjectRoot

$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    $Python = "python"
}

$NodeAData = Join-Path $ProjectRoot "data\node-a"
$NodeBData = Join-Path $ProjectRoot "data\node-b"
$NodeAChain = Join-Path $NodeAData "blockchain.json"
$NodeBChain = Join-Path $NodeBData "blockchain.json"
$PreviousDataDir = $env:DATA_DIR
$PreviousNodeDataDir = $env:NODE_DATA_DIR
$PreviousStorageBackend = $env:STORAGE_BACKEND
$PreviousPythonIoEncoding = $env:PYTHONIOENCODING

try {
    if ($Reset) {
        foreach ($Path in @($NodeAData, $NodeBData)) {
            if (Test-Path $Path) {
                Remove-Item -LiteralPath $Path -Recurse -Force
            }
        }
    }

    New-Item -ItemType Directory -Force -Path $NodeAData, $NodeBData | Out-Null

    if (-not (Test-Path $NodeAChain)) {
        $env:DATA_DIR = "data/node-a"
        $env:NODE_DATA_DIR = "data/node-a"
        $env:STORAGE_BACKEND = "json"
        $env:PYTHONIOENCODING = "utf-8"
        & $Python -c "from wallet import Wallet; from blockchain import Blockchain; bc = Blockchain(Wallet(), Wallet(), Wallet()); bc.save_blockchain()"
    }

    if (-not (Test-Path $NodeBChain)) {
        Copy-Item -LiteralPath $NodeAChain -Destination $NodeBChain
    }

    Write-Host "Two-node data is ready:"
    Write-Host "  Node A: data/node-a"
    Write-Host "  Node B: data/node-b"
}
finally {
    if ($null -eq $PreviousDataDir) {
        Remove-Item Env:DATA_DIR -ErrorAction SilentlyContinue
    }
    else {
        $env:DATA_DIR = $PreviousDataDir
    }

    if ($null -eq $PreviousNodeDataDir) {
        Remove-Item Env:NODE_DATA_DIR -ErrorAction SilentlyContinue
    }
    else {
        $env:NODE_DATA_DIR = $PreviousNodeDataDir
    }

    if ($null -eq $PreviousStorageBackend) {
        Remove-Item Env:STORAGE_BACKEND -ErrorAction SilentlyContinue
    }
    else {
        $env:STORAGE_BACKEND = $PreviousStorageBackend
    }

    if ($null -eq $PreviousPythonIoEncoding) {
        Remove-Item Env:PYTHONIOENCODING -ErrorAction SilentlyContinue
    }
    else {
        $env:PYTHONIOENCODING = $PreviousPythonIoEncoding
    }
}
