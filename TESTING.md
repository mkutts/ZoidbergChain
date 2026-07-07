# Testing

This project uses `pytest` for automated tests.

## Install test dependencies

```powershell
python -m pip install -r requirements-test.txt
```

## Run all tests

```powershell
python -m pytest
```

## Run tests with coverage

```powershell
python -m pytest --cov=. --cov-report=term-missing
```

Coverage reporting is configured for local visibility only. There is no minimum coverage threshold yet.

The test fixtures run blockchain operations from a temporary working directory and copy only the files needed for the test, so the production `blockchain.json` and `wallets.json` files in the project root are not modified.

Storage supports JSON and SQLite. `STORAGE_BACKEND=json` remains the default. `STORAGE_BACKEND=sqlite` uses a node-local database at `SQLITE_DB_PATH`, which defaults to `DATA_DIR/zoidbergchain.db`. `DATA_DIR` (or `NODE_DATA_DIR`) must stay unique per node. Task 5.3 handled JSON to SQLite migration separately, and Task 5.5 added storage query helpers so the app no longer has to scan raw persistence data in the hot paths.

The storage abstraction now includes lookups for common blockchain entities such as:

- blocks by hash or height
- wallets by public key
- submissions by id or content hash
- votes by submission and voter
- certificates by id or submission
- peers by node id and active-peer filtering
- mint-queue membership checks
- active-user counts over a time window

Task 5.6 added operator-facing backup/export/import helpers and restore guidance in [docs/storage-operations.md](/C:/Users/mattk/ZoidbergChain/docs/storage-operations.md).

Storage writes are now hardened:

- JSON saves use a temporary file and atomic replace.
- JSON and SQLite keep a latest-known-good `.bak` backup.
- Corrupt JSON loads fall back to the backup when possible.
- SQLite saves run inside a transaction and roll back on failure.
- The local integrity helper can be called with:

  ```powershell
  .\.venv\Scripts\python.exe -c "from storage import check_storage_integrity; print(check_storage_integrity())"
  ```

To migrate an existing JSON data directory into SQLite manually:

```powershell
.\.venv\Scripts\python.exe .\scripts\migrate_json_to_sqlite.py --data-dir data\node-a
```

Use `--overwrite` only when you want to replace an existing SQLite database after creating a backup copy.

Always make a separate copy of the data directory before switching storage backends.
