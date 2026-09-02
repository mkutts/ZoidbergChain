# Milestone 2 Tasks 3, 4A, and 4B: Dependency Audit

Audit date: 2026-09-01. Scope: dependency declarations and installation documentation only. No application, protocol, API, storage-format, signature, consensus, or frontend dependency behavior was changed.

## Task 4A: Python Security Remediation

Task 4A reproduced the CI command in a new external Python 3.13 environment after
installing `requirements-test.txt` and `pip-audit==2.9.0`:

```powershell
python -m pip_audit -r requirements-test.txt --strict
```

The baseline was 47 advisories in eight packages. There are no pip-audit
suppression flags, ignore lists, or advisory exclusions. The table maps every
baseline advisory to its resolver origin and records the smallest version that
clears all fixable findings for that package.

| Package | Origin and declaration | Before -> after | Baseline advisories | Resolution |
|---|---|---|---|---|
| `cryptography` | Direct core, `requirements-core.txt` | `45.0.6` -> `50.0.0` | `PYSEC-2026-36`, `PYSEC-2026-35`, `PYSEC-2026-2141`, `PYSEC-2026-3552`, `PYSEC-2026-3553`, `PYSEC-2026-3554`, `GHSA-537c-gmf6-5ccf` | Fixed; `50.0.0` is the maximum listed fixed version. |
| `ecdsa` | Direct core, `requirements-core.txt` | `0.19.0` -> `0.19.2` | `PYSEC-2026-1325`, `PYSEC-2026-2467` | `PYSEC-2026-2467` fixed by `0.19.2`; `PYSEC-2026-1325` has no listed fix. |
| `python-multipart` | Direct core, `requirements-core.txt` | `0.0.20` -> `0.0.31` | `PYSEC-2026-1852`, `PYSEC-2026-3038`, `PYSEC-2026-3037`, `PYSEC-2026-3036`, `PYSEC-2026-3040`, `PYSEC-2026-3039` | Fixed; `0.0.31` is the maximum listed fixed version. |
| `requests` | Direct core, `requirements-core.txt` | `2.32.3` -> `2.33.0` | `PYSEC-2026-1872`, `PYSEC-2026-2275` | Fixed; `2.33.0` is the maximum listed fixed version. |
| `pillow` | Direct originality, `requirements-originality.txt` | `11.0.0` -> `12.3.0` | `PYSEC-2026-165`, `PYSEC-2026-2250`, `PYSEC-2026-2253`, `PYSEC-2026-2255`, `PYSEC-2026-2257`, `PYSEC-2026-2256`, `PYSEC-2026-2254`, `PYSEC-2026-2252`, `PYSEC-2026-2249`, `PYSEC-2026-2874`, `PYSEC-2026-3453`, `PYSEC-2026-3451`, `PYSEC-2026-3454`, `PYSEC-2026-3495`, `PYSEC-2026-3496`, `PYSEC-2026-3494`, `PYSEC-2026-3493` | Fixed; `12.3.0` is the maximum listed fixed version. |
| `pytest` | Direct test, `requirements-test.txt` | `8.4.1` -> `9.0.3` | `PYSEC-2026-1845` | Fixed by `9.0.3`; compatible with retained `pytest-cov==6.2.1`. |
| `starlette` | Transitive through FastAPI; security pin in `requirements-core.txt` | `0.41.3` -> `1.3.1` | `PYSEC-2026-161`, `PYSEC-2026-249`, `PYSEC-2026-248`, `PYSEC-2026-1942`, `PYSEC-2026-1941`, `PYSEC-2026-2281`, `PYSEC-2026-2280` | Fixed; a direct pin is necessary to keep the resolved FastAPI dependency at the audited fixed version. |
| `transformers` | Transitive through direct originality dependency `sentence-transformers==3.3.1` | `4.57.6` -> unchanged | `PYSEC-2025-217`, `PYSEC-2026-2290`, `PYSEC-2026-2288`, `PYSEC-2026-2289`, `GHSA-xrqw-3rrv-vx5w` | Not fixed in the compatible `<5` parent range. The audit lists no fix for the first two and requires `5.0.0`, `5.3.0`, and yanked `5.10.0` for the others. |

### Compatibility Decisions

- Every selected fixed release has a Python 3.13 wheel or was successfully resolved
  by the fresh Python 3.13 environment. `pip check` confirms compatible parent
  constraints after installation.
- `fastapi==0.133.0` is the minimum release tested that accepts
  `starlette==1.3.1`; `0.132.0` and earlier reject Starlette 1.x. It retains the
  pinned `pydantic==2.10.5`. FastAPI and Starlette are exercised by the complete
  API suite, including uploads, multipart parsing, CORS, middleware, rate limits,
  TestClient, routing, and lifespan behavior.
- `cryptography==50.0.0` preserves the RSA APIs used by `wallet.py`; the
  repository's Protocol v1 vectors, wallet-auth/MetaMask recovery, native-transfer
  signing, peer-auth/replay, and signature-verification tests protect message and
  signature compatibility. `ecdsa==0.19.2` keeps the same SECP256k1 API used for
  legacy wallet signing and verification.
- `pillow==12.3.0` remains compatible with ImageHash and pytesseract. Content
  hashing, canonical genesis validation, media validation, content storage, and
  certificate tests protect image decoding and originality-facing behavior.
- `sentence-transformers==3.3.1` remains intentionally unchanged because
  `zoidbergCoin.py` is a tracked executable entry point that imports it. Moving to
  a Transformers 5 fixed release requires a sentence-transformers major upgrade,
  pulls new model-stack dependencies, and selects the yanked `transformers==5.10.0`
  release. That is a separately scoped ML compatibility migration, not a safe
  dependency-only remediation.

### Remaining Blockers

- `ecdsa==0.19.2` remains reachable through legacy wallet SECP256k1 signing and
  verification. `PYSEC-2026-1325` has no listed patched release. Replacing that
  library would change cryptographic implementation scope and requires explicit
  protocol-compatible security review; it has not been suppressed.
- `transformers==4.57.6` remains reachable when the retained legacy
  `zoidbergCoin.py` entry point is used. Its five advisory IDs above cannot be
  cleared within sentence-transformers 3.3.1's `<5` constraint. No model names,
  preprocessing, thresholds, scoring, or originality interfaces were changed.
- Consequently the exact audit command remains red for these six unsuppressed
  advisories after all behavior-preserving fixed-version upgrades. Owner/security
  review is required for the `ecdsa` finding and a separately scoped ML-stack
  compatibility migration is required for Transformers.

### Task 4A Verification Results

The second fresh external Python 3.13 environment installed the complete test
requirements plus `pip-audit==2.9.0` successfully. `python -m pip check` passed.
The exact audit command reported the six remaining advisories listed above in two
packages; it did not report the 41 remediated advisories. `python -m pytest
--collect-only -q` collected 900 tests. The focused API, Protocol v1, signing,
content/media, certificate, and storage suite passed with 659 tests; `python -m
pytest tests/integration -q` passed with 21 tests; and the full backend suite
passed with 900 tests. `python scripts/check_repository_hygiene.py` and `git diff
--check` passed.

The FastAPI/Starlette test run emits Starlette's upstream warning that its
`TestClient` compatibility path for `httpx` is deprecated in favor of `httpx2`.
The existing TestClient tests pass, and no compatibility source change was made.

## Task 4B: Frontend Security Remediation

Task 4B reproduced the frontend CI audit in an isolated Windows temporary copy
of `zoidbergcoin-ui`, using Node `24.13.0`, npm `11.6.2`, and a separate npm
cache. The copy included only the source, public assets, scripts, manifest,
lockfile, Vite configuration, and `index.html`; it excluded `node_modules`,
`dist`, coverage, caches, logs, and all environment files. This avoided the
repository-local `esbuild.exe` and PyCharm-managed npm-cache `EPERM` locks
without killing processes or deleting shared state.

### Baseline Findings and Dependency Chains

The exact CI command, `npm audit --audit-level=high`, initially failed with
eight advisories: one critical, five high, and two moderate. The affected
installed packages, chains, and minimum safe versions were:

| Package | Installed | Severity | Origin and chain | Advisory identifiers | Minimum fixed version |
| --- | ---: | --- | --- | --- | ---: |
| `axios` | 1.7.9 | high | Direct dependency | `GHSA-jr5f-v2jv-69x6`, `GHSA-4hjh-wcwx-xvwj`, `GHSA-pmwg-cvhr-8vh7`, `GHSA-pf86-5x62-jrwf`, `GHSA-6chq-wfr3-2hj9`, `GHSA-43fc-jf86-j433`, `GHSA-q8qp-cvcw-x6jj`, `GHSA-hfxv-24rg-xrqf`, `GHSA-777c-7fjr-54vf`, `GHSA-p92q-9vqr-4j8v`, `GHSA-j5f8-grm9-p9fc`, `GHSA-3g43-6gmg-66jw`, `GHSA-35jp-ww65-95wh` | 1.18.0 |
| `form-data` | 4.0.1 | critical/high | Transitive: `axios@1.7.9 -> form-data` | `GHSA-fjxv-7rqg-78g4`, `GHSA-hmw2-7cc7-3qxx` | 4.0.6 |
| `follow-redirects` | 1.15.9 | moderate | Transitive: `axios@1.7.9 -> follow-redirects` | `GHSA-r4q5-vmmm-2653` | 1.15.12 |
| `vite` / `esbuild` | 6.0.11 / 0.24.2 | high/moderate | Direct `vite`; Vite resolves esbuild | `GHSA-p9ff-h696-f583`, `GHSA-fx2h-pf6j-xcff`; `GHSA-67mh-4wv8-2f99` | Vite 6.4.3 / esbuild 0.25.0 |
| `rollup` | 4.34.0 | high | Transitive: `vite@6.0.11 -> rollup` | `GHSA-mw96-cpmx-2vgc` | 4.59.0 |
| `postcss` / `nanoid` | 8.5.1 / 3.3.8 | high | Transitive: `vite@6.0.11 -> postcss -> nanoid` | `GHSA-6g55-p6wh-862q`, `GHSA-r28c-9q8g-f849`; `GHSA-28wg-ghj8-5hjv`, `GHSA-2v37-7h3g-55p8`, `GHSA-xwg4-73v4-xw9w` | PostCSS 8.5.23 / Nano ID 3.3.18 |

`npm audit` offered a normal fix for every finding and did not require a
semver-major change. Task 4's earlier documentation described a lockfile-only
audit; the clean isolated audit confirmed the same count and affected families
against the complete project copy.

### Remediation and Compatibility

Only the controlling direct dependencies changed:

| Direct dependency | Before | After | Reason |
| --- | ---: | ---: | --- |
| `axios` | `^1.7.9` | `^1.18.0` | Minimum current stable Axios version above every reported vulnerable range; resolves safe supported `form-data` and `follow-redirects` releases. |
| `vite` | `^6.0.5` | `^6.4.3` | Minimum Vite 6 release above the reported direct high-severity range; its supported ranges resolve fixed esbuild, Rollup, PostCSS, and Nano ID releases. |

`@vitejs/plugin-vue@5.2.1`, Vue `3.5.13`, and Vue Router `4.5.0` are unchanged.
Plugin Vue 5 accepts Vite 6 and Vue 3.2+, and Vite 6.4.3 supports Node 24.
The regenerated npm lockfile resolves Axios 1.18.0, form-data 4.0.6,
follow-redirects 1.16.0, Vite 6.4.3, esbuild 0.25.12, Rollup 4.63.1, PostCSS
8.5.26, and Nano ID 3.3.18. No override, suppression, prerelease, forced audit
fix, source change, Vite-configuration migration, or CI-threshold change was
used.

### Task 4B Verification Results

After npm regenerated the manifest and lockfile, a fresh isolated frontend
copy with its own npm cache passed `npm ci`, `npm test`, `npm run build`, and
`npm audit --audit-level=high`. `npm ci` did not rewrite the lockfile. The test
command covers 21 named frontend test files and passed 130 tests, including API-base/runtime-config,
API authorization and error handling, MetaMask wallet behavior, native ZOID
transfers, submissions, voting, certificates, and explorer/dashboard behavior.
The production build completed and generated only expected ignored `dist`
assets; it copied no runtime `.env` file and generated no source maps. The
audit JSON reports zero critical, high, moderate, low, and informational
findings, so there are no remaining moderate/low findings to document and the
configured high/critical CI gate passes.

The repository-local `esbuild.exe` process and managed npm-cache lock were not
modified and may still block direct repository `npm ci`; the isolated method is
the verified Windows workaround. Python remains unchanged: the six unresolved
advisories are the existing `ecdsa` and `transformers` blockers described
above.

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
| cryptography | 50.0.0 | core | `wallet.py` RSA key/signature operations. |
| ecdsa | 0.19.2 | core | `wallet.py`, `blockchain.py`, and legacy entry point signing. |
| eth-account | 0.13.7 | core | MetaMask personal-sign recovery in `wallet_auth.py` and native-transfer paths. |
| fastapi | 0.133.0 | core | Current `api.py` application and route entry point. |
| starlette | 1.3.1 | core, transitive security pin | FastAPI ASGI dependency pinned to the audited fixed line. |
| pydantic | 2.10.5 | core | API request/response models. |
| python-multipart | 0.0.31 | core | FastAPI file/form upload handling. |
| requests | 2.33.0 | core | Peer synchronization and `sync.py`. |
| slowapi | 0.1.9 | core | API rate limiting. |
| uvicorn | 0.34.0 | core | Documented FastAPI server and systemd entry point. |
| ImageHash | 4.3.1 | originality | Perceptual hashes in `blockchain.py` and `utils.py`. |
| pillow | 12.3.0 | originality | Image decoding in originality/OCR paths. |
| pytesseract | 0.3.13 | originality | OCR in `blockchain.py`, `utils.py`, and `tessTest.py`; requires external Tesseract. |
| sentence-transformers | 3.3.1 | originality | Legacy executable `zoidbergCoin.py` embedding model. Retained as uncertain/legacy support. |
| httpx | 0.28.1 | test | FastAPI/Starlette TestClient compatibility and test collection. |
| pytest | 9.0.3 | test | Backend and integration test runner. |
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
