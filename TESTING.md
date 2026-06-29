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

The test fixtures run blockchain operations from a temporary working directory and copy only the files needed for the test, so the production `blockchain.json` and `wallets.json` files in the project root are not modified.
