# Clean Reset Runbook

This runbook defines how to safely reset local ZoidbergChain development or testnet-prep state before MetaMask identity becomes the standard account model.

## Why Reset Is Allowed At This Stage

- Current backend wallets, submissions, votes, mint queue records, and related chain state are still development or test artifacts.
- Task 7 moves the project toward MetaMask-signed identity using `0x` addresses as the native user account format.
- Before that identity model becomes standard, a clean reset is allowed so old dev-era data does not become a long-term architectural constraint.
- This reset flow is for development and testnet preparation only.

## What Gets Reset

Depending on backend and flags, a reset may delete or reinitialize:

- blockchain data
- submissions
- votes
- originality certificates
- content metadata
- content binaries when explicitly requested
- mint queue records
- old backend or dev wallets
- peer state when explicitly requested
- local JSON or SQLite state for Node A or Node B test data

## What Should Not Be Reset Unless Explicitly Chosen

- source code
- config files
- `.env` secrets
- docs
- frontend source
- unrelated workspace files

The reset tool is intentionally limited to known node-state files and directories under a selected node data directory.

## Back Up First

Before any destructive reset:

1. Stop local nodes that use the target data directory.
2. Create a backup snapshot.
3. Confirm the backup file exists before deleting anything.

Example:

```powershell
.\.venv\Scripts\python.exe .\scripts\dev_reset_state.py --node-data-dir data\node-a --backend json --backup-first --yes-i-understand-this-deletes-test-data
```

The reset tool writes backup snapshots under `DATA_DIR/backups/reset-preflight/` when `--backup-first` is used.

## Resetting JSON Backend Data

JSON backend reset reinitializes the selected node data directory by clearing JSON-backed chain state and optionally peer state and content files.

Example:

```powershell
$env:ENVIRONMENT = "development"
$env:PUBLIC_API_MODE = "false"
.\.venv\Scripts\python.exe .\scripts\dev_reset_state.py --node-data-dir data\node-a --backend json --yes-i-understand-this-deletes-test-data
```

Optional flags:

- `--backup-first`
- `--include-content-files`
- `--include-peers`

By default:

- chain state is reset
- peer state is preserved
- content binaries are preserved

## Resetting SQLite Backend Data

SQLite backend reset deletes and recreates the selected SQLite node state safely.

Example:

```powershell
$env:ENVIRONMENT = "development"
$env:PUBLIC_API_MODE = "false"
.\.venv\Scripts\python.exe .\scripts\dev_reset_state.py --node-data-dir data\node-a --backend sqlite --yes-i-understand-this-deletes-test-data
```

Optional flags:

- `--backup-first`
- `--include-content-files`
- `--include-peers`

By default:

- chain state is reset
- peer state is preserved
- content binaries are preserved

## Resetting Node A / Node B Local Test Data

Node A example:

```powershell
.\.venv\Scripts\python.exe .\scripts\dev_reset_state.py --node-data-dir data\node-a --backend json --backup-first --include-content-files --include-peers --yes-i-understand-this-deletes-test-data
```

Node B example:

```powershell
.\.venv\Scripts\python.exe .\scripts\dev_reset_state.py --node-data-dir data\node-b --backend sqlite --backup-first --yes-i-understand-this-deletes-test-data
```

For local two-node work:

- reset Node A and Node B separately
- verify each node uses its own `DATA_DIR`
- re-run any bootstrap or migration steps needed for the backend you are testing

## How To Verify Reset Succeeded

After reset:

1. Confirm the tool output shows only expected node-data files were deleted or reinitialized.
2. Confirm source files, docs, and `.env` files were not touched.
3. Check that the selected backend storage file was recreated in an empty state.
4. Start the backend again and confirm it boots cleanly.
5. If `--include-content-files` was used, confirm content binaries are gone only from the selected node content directory.
6. If `--include-peers` was used, confirm peer state is empty. Otherwise confirm peers were preserved.

Useful follow-up checks:

```powershell
.\.venv\Scripts\python.exe -c "from storage import create_storage_backend, check_storage_integrity; backend = create_storage_backend(); print(check_storage_integrity(backend))"
```

## Warning

- This reset process is for development and testnet preparation only.
- Never run it against production data.
- Never expose reset tooling through public API mode.
