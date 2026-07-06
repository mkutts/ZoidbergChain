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

Storage is still JSON-backed for Task 5.1. Set `STORAGE_BACKEND=json` to use the current backend explicitly. `DATA_DIR` (or `NODE_DATA_DIR`) scopes each node to its own storage directory. SQLite will be introduced in Task 5.2 without changing the existing JSON layout first.
