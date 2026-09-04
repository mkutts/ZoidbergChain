# Testing

This project uses `pytest` for automated tests.

## Dependency installation groups

`requirements-core.txt` is the node's core runtime group.
`requirements-originality.txt` is the media/OCR group. `requirements.txt`
combines both and is required for a runnable node because FastAPI imports the
originality path at startup. `requirements-test.txt` adds HTTP/test tooling to
that complete node install. `requirements-dev.txt` includes the complete test
group for local repository validation.

## Install test dependencies

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-test.txt
```

This includes the complete node dependencies and pytest tooling. The current test suite imports the FastAPI application, which imports the originality/OCR path; do not use `requirements-core.txt` alone for backend testing.

For local development validation, install:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

## Run all tests

```powershell
.\.venv\Scripts\python.exe -m pytest
```

## Continuous integration

GitHub Actions partitions backend and integration tests, verifies frontend installation/test/build, blocks tracked runtime artifacts and current-tree secrets, and audits Python and frontend dependencies. See [docs/continuous-integration.md](docs/continuous-integration.md) for the exact jobs, local-equivalent commands, dependency-audit thresholds, and the documented Windows frontend-lock limitation. Lint and formatting gates are intentionally not enabled yet.

## Run tests with coverage

```powershell
.\.venv\Scripts\python.exe -m pytest --cov=. --cov-report=term-missing
```

Coverage reporting is configured for local visibility only. There is no minimum coverage threshold yet.

## Clean frontend verification

Do not run a clean frontend install in the repository's potentially locked
`node_modules`. Copy `zoidbergcoin-ui` to a new temporary directory and point
`npm_config_cache` at a second temporary directory, then run `npm ci`, `npm test`,
`npm run build`, and `npm audit --audit-level=high` from that copy. This
is the local equivalent of the CI frontend gate and leaves frontend source,
lockfile, and repository dependency state untouched.

FastAPI/Starlette `TestClient` currently emits its known upstream deprecation
warning during parts of the suite. It is recorded as a warning rather than
suppressed; tests must still pass without changing the compatibility path.

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
