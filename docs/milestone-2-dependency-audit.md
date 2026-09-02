# Milestone 2 Task 3: Dependency Audit

Audit date: 2026-09-01. Scope: dependency declarations and installation documentation only. No application, protocol, API, storage-format, signature, consensus, or frontend dependency behavior was changed.

## Baseline and Mismatches

The previous `requirements.txt` was a flat 108-package pip-freeze-style list. It mixed direct dependencies with transitive packages, unreferenced Flask-era packages, forecasting, Spark, database, and ML stacks. `requirements-test.txt` added pytest and pytest-cov.

The Task 1 inventory records pre-Task-2 repository state and HEAD `5bd09cb`; Task 2 is now separately committed as `456e242` and the starting worktree for this task was clean. Its statements that runtime state, private-key-bearing state, backups, caches, patches, and a tracked virtual environment remain tracked are therefore historical and not current. The inventory correctly identifies FastAPI as current production code while the old requirements retained Flask-era dependencies. The inventory also calls `zoidbergCoin.py` a legacy candidate, but it remains a tracked executable Python entry point importing sentence-transformers; that dependency is retained pending a separately scoped decision.

## New Groups

| File | Responsibility |
|---|---|
| `requirements-core.txt` | Direct FastAPI node/API, signing, peer networking, upload, configuration, and rate-limit dependencies. |
| `requirements-originality.txt` | Direct media, image-hash, OCR, and legacy embedding dependencies. |
| `requirements.txt` | Complete supported node aggregate: core plus originality. It is the only documented runnable-node install. |
| `requirements-test.txt` | Complete node plus pytest, coverage, and the explicit HTTP test-client dependency. |
| `requirements-dev.txt` | Test installation for local development and repository validation. No new lint/audit package was introduced. |

`requirements-core.txt` alone is deliberately not advertised as runnable: importing `api:app` imports `blockchain.py`, which imports Pillow, ImageHash, and pytesseract. This task does not refactor that coupling.

## Direct Dependencies

| Dependency | Version | Group | Evidence and purpose |
|---|---:|---|---|
| cryptography | 45.0.6 | core | `wallet.py` RSA key/signature operations. |
| ecdsa | 0.19.0 | core | `wallet.py`, `blockchain.py`, and legacy entry point signing. |
| eth-account | 0.13.7 | core | MetaMask personal-sign recovery in `wallet_auth.py` and native-transfer paths. |
| fastapi | 0.115.6 | core | Current `api.py` application and route entry point. |
| pydantic | 2.10.5 | core | API request/response models. |
| python-multipart | 0.0.20 | core | FastAPI file/form upload handling. |
| requests | 2.32.3 | core | Peer synchronization and `sync.py`. |
| slowapi | 0.1.9 | core | API rate limiting. |
| uvicorn | 0.34.0 | core | Documented FastAPI server and systemd entry point. |
| ImageHash | 4.3.1 | originality | Perceptual hashes in `blockchain.py` and `utils.py`. |
| pillow | 11.0.0 | originality | Image decoding in originality/OCR paths. |
| pytesseract | 0.3.13 | originality | OCR in `blockchain.py`, `utils.py`, and `tessTest.py`; requires external Tesseract. |
| sentence-transformers | 3.3.1 | originality | Legacy executable `zoidbergCoin.py` embedding model. Retained as uncertain/legacy support. |
| httpx | 0.28.1 | test | FastAPI/Starlette TestClient compatibility and test collection. |
| pytest | 8.4.1 | test | Backend and integration test runner. |
| pytest-cov | 6.2.1 | test | Documented optional coverage command. |

## Removed Direct Declarations

Removed declarations are not removed packages from all resolved environments. They are no longer declared directly because static import, executable-entry-point, documentation, dynamic-import, subprocess, MIME/OCR, authentication, and deployment-command review found no direct project use, or because they are resolved transitively by retained dependencies.

| Classification | Removed declarations |
|---|---|
| Flask-era, unreferenced | Flask, Flask-Cors, Flask-JWT-Extended, Flask-SQLAlchemy, blinker, itsdangerous, Jinja2, MarkupSafe, PyJWT, Werkzeug. |
| Forecasting/data/Spark/Mongo, unreferenced | cmdstanpy, holidays, prophet, py4j, pyarrow, pymongo, pyspark, stanio, lightgbm, xgboost, pandas, matplotlib, Cython. |
| Unreferenced ML/data direct declarations | numpy, scipy, scikit-learn, torch, transformers, tokenizers, huggingface-hub, safetensors, fsspec, regex, joblib, threadpoolctl, sympy, networkx, mpmath, tqdm, PyWavelets. These remain transitive where required by ImageHash or sentence-transformers. |
| Runtime transitive declarations | annotated-types, anyio, certifi, charset-normalizer, click, colorama, Deprecated, dnspython, email_validator, filelock, greenlet, h11, httpcore, httptools, idna, importlib_resources, limits, orjson, packaging, pydantic-core, pydantic-extra-types, Pygments, python-dateutil, pytz, PyYAML, rich, rich-toolkit, shellingham, six, sniffio, SQLAlchemy, starlette, typer, typing-extensions, tzdata, ujson, urllib3, watchfiles, websockets, wrapt. |
| Packaging/tooling or apparently unused | fastapi-cli, pypi, python-dotenv, setuptools. `python-dotenv` has no current source import, dynamic use, or documented command. |
| Crypto transitive declaration | eth-keys is installed through eth-account and has no direct project import. |
| Plotting transitive declaration | contourpy, cycler, fonttools, kiwisolver, pyparsing, and mdurl. |

No direct code import, documented command, dynamic import, optional import, or subprocess invocation for the removed categories was found. They will be reinstalled when demanded transitively by a retained direct package. The clean-environment checks below validate the resulting resolution. All retained direct pins match the previous file except Pillow: it moved from 10.3.0 to 11.0.0 because 10.3.0 has no Python 3.13 wheel and its source build fails in the repository's documented Python 3.13.5 environment.

## Retained Uncertainty and Risks

- `sentence-transformers` is retained because `zoidbergCoin.py` is still present as an executable entry point and imports it at module load. The modern FastAPI node does not import it, but removal needs an explicit legacy-entry-point decision.
- ImageHash, Pillow, and pytesseract remain mandatory for the current full node because FastAPI import reaches `blockchain.py`; mocked tests are not evidence that production originality dependencies are removable.
- `pytesseract` needs the operating-system Tesseract executable. pip installs only its Python wrapper.
- Python 3.13.5 and Node 24.13.0 are the recorded tested environment. The frontend lockfile’s Vite engine accepts Node 18+; no broader compatibility claim is made.
- The old pip-freeze pins no longer constrain all transitive resolutions. Direct behavior-sensitive packages remain pinned; a future lock/constraints decision should be separately scoped.

## Installation and Verification

Complete node:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Tests and development:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-test.txt
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

Frontend:

```powershell
cd zoidbergcoin-ui
npm.cmd ci
npm.cmd test
npm.cmd run build
```

Install Tesseract OCR separately and expose `tesseract` on `PATH` before using image OCR. The deployment runbook continues to use `python -m uvicorn api:app`; the systemd unit uses the same module entry point.

## Clean-Environment Results

The temporary environment was created at `C:\Users\mattk\AppData\Local\Temp\zoidbergchain-task3-venv`, outside the repository; pip remained at 25.1.1 and was not upgraded. The initial installation was sandbox-network blocked (`WinError 10013`) and then retried with network permission. The original `pillow==10.3.0` failed because no Python 3.13 wheel was available and its source build raised `KeyError: '__version__'`; `pillow==11.0.0` installed successfully.

| Check | Result |
|---|---|
| `python -m pip install -r requirements.txt` | PASS after the Pillow compatibility correction. |
| `python -m pip check` | PASS: `No broken requirements found.` |
| Import `api`, `blockchain`, `storage`, `protocol_v1`, `protocol_v1_genesis` | PASS with `DATA_DIR` and `CONTENT_STORAGE_DIR` redirected to a temporary path. |
| `python -m pytest --collect-only -q` | PASS: 900 tests collected. |
| Targeted protocol/genesis/JSON-and-SQLite storage tests | PASS: 67 passed. |
| `python -m pytest tests/integration -q` | PASS: 21 passed. |
| `python -m pytest -q` | PASS: 900 passed in 93.14 seconds. |

The import check used temporary state paths. The full test suite passed using its isolation fixtures and did not create a tracked repository-root runtime-state file.

## Frontend Windows Blocker

Task 1 recorded `npm.cmd ci` failing with `EPERM` while unlinking `zoidbergcoin-ui/node_modules/@esbuild/win32-x64/esbuild.exe`. This audit confirmed that `esbuild.exe` is currently active from that exact generated path (PID 38536). The lockfile root dependencies exactly match `package.json`; no package or lockfile change is required. `npm.cmd cache verify` is also blocked by `EPERM` while unlinking a file under PyCharm's managed Node 24.13.0 npm cache, and cannot write its npm log there. Do not kill the process or alter that managed cache without its owner's approval. After the owner releases the esbuild/cache lock or permission boundary, remove only the resolved ignored `zoidbergcoin-ui/node_modules` directory and rerun `npm.cmd ci`, `npm.cmd test`, and `npm.cmd run build`.
