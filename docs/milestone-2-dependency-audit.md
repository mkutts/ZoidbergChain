# Milestone 2 Tasks 3, 4A, 4B, 4E, and 4F: Dependency Audit

Audit date: 2026-09-02. Task 4F removes only an unused model import and initialization from the retained legacy `zoidbergCoin.py` file and its now-unused direct dependency. No supported application, protocol, API, storage-format, signature, consensus, or frontend behavior was changed.

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
| `transformers` | Transitive through former direct originality dependency `sentence-transformers==3.3.1` | `4.57.6` -> absent | `PYSEC-2025-217`, `PYSEC-2026-2290`, `PYSEC-2026-2288`, `PYSEC-2026-2289`, `GHSA-xrqw-3rrv-vx5w` | Removed in Task 4F with the unused direct parent; all five advisories are absent from the clean supported installation. |

### Compatibility Decisions

- Every selected fixed release has a Python 3.13 wheel or was successfully resolved
  by the fresh Python 3.13 environment. `pip check` confirms compatible parent
  constraints after installation.
- `fastapi==0.133.0` is the minimum release tested that accepts
  `starlette==1.3.1`; `0.132.0` and earlier reject Starlette 1.x. It retains the
  pinned `pydantic==2.10.5`. FastAPI and Starlette are exercised by the complete
  API suite, including uploads, multipart parsing, CORS, middleware, rate limits,
  TestClient, routing, and lifespan behavior.
- `cryptography==50.0.0` provides the SECP256K1 legacy signing and verification
  implementation as well as the existing cryptographic APIs. Task 4E converts
  DER signatures at the compatibility boundary to the historical raw 64-byte
  `r || s` base64 form, preserving Protocol v1 vectors, legacy block hashes,
  wallet-auth/MetaMask recovery, native-transfer signing, and peer validation.
- `pillow==12.3.0` remains compatible with ImageHash and pytesseract. Content
  hashing, canonical genesis validation, media validation, content storage, and
  certificate tests protect image decoding and originality-facing behavior.
- Task 4F retains `zoidbergCoin.py` but removes its consumer-free
  `SentenceTransformer('all-MiniLM-L6-v2')` module-load initialization and import.
  The supported node originality path remains Pillow, ImageHash, and pytesseract;
  no model preprocessing, thresholds, scoring, or originality interfaces changed.

### Remaining Blockers

- `ecdsa` no longer appears in supported requirements or production/test imports.
  Task 4E removes `PYSEC-2026-1325` without a suppression by replacing its
  legacy SECP256K1 use with `cryptography` and retaining fixed historical
  compatibility vectors.
- Task 4F removes `sentence-transformers`, so its Transformers and Torch
  transitive chain is absent from the clean supported installation. The five
  Transformers advisories are resolved without an upgrade or audit suppression.
- Consequently the exact audit command is green with zero known vulnerabilities.

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
| cryptography | 50.0.0 | core | Legacy SECP256K1 Wallet/Transaction signing plus existing cryptographic primitives. |
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
| httpx | 0.28.1 | test | FastAPI/Starlette TestClient compatibility and test collection. |
| pytest | 9.0.3 | test | Backend and integration test runner. |
| pytest-cov | 6.2.1 | test | Documented optional coverage command. |

## Removed Direct Declarations

Removed declarations are not removed packages from all resolved environments. They are no longer declared directly because static import, executable-entry-point, documentation, dynamic-import, subprocess, MIME/OCR, authentication, and deployment-command review found no direct project use, or because they are resolved transitively by retained dependencies.

| Classification | Removed declarations |
|---|---|
| Flask-era, unreferenced | Flask, Flask-Cors, Flask-JWT-Extended, Flask-SQLAlchemy, blinker, itsdangerous, Jinja2, MarkupSafe, PyJWT, Werkzeug. |
| Forecasting/data/Spark/Mongo, unreferenced | cmdstanpy, holidays, prophet, py4j, pyarrow, pymongo, pyspark, stanio, lightgbm, xgboost, pandas, matplotlib, Cython. |
| Unreferenced ML/data direct declarations | numpy, scipy, scikit-learn, torch, transformers, tokenizers, huggingface-hub, safetensors, fsspec, regex, joblib, threadpoolctl, sympy, networkx, mpmath, tqdm, PyWavelets. The clean installation retains only the ImageHash-related NumPy, SciPy, and PyWavelets chain. |
| Runtime transitive declarations | annotated-types, anyio, certifi, charset-normalizer, click, colorama, Deprecated, dnspython, email_validator, filelock, greenlet, h11, httpcore, httptools, idna, importlib_resources, limits, orjson, packaging, pydantic-core, pydantic-extra-types, Pygments, python-dateutil, pytz, PyYAML, rich, rich-toolkit, shellingham, six, sniffio, SQLAlchemy, starlette, typer, typing-extensions, tzdata, ujson, urllib3, watchfiles, websockets, wrapt. |
| Packaging/tooling or apparently unused | fastapi-cli, pypi, python-dotenv, setuptools. `python-dotenv` has no current source import, dynamic use, or documented command. |
| Crypto transitive declaration | eth-keys is installed through eth-account and has no direct project import. |
| Plotting transitive declaration | contourpy, cycler, fonttools, kiwisolver, pyparsing, and mdurl. |

No direct code import, documented command, dynamic import, optional import, or subprocess invocation for the removed categories was found. They will be reinstalled when demanded transitively by a retained direct package. The clean-environment checks below validate the resulting resolution. All retained direct pins match the previous file except Pillow: it moved from 10.3.0 to 11.0.0 because 10.3.0 has no Python 3.13 wheel and its source build fails in the repository's documented Python 3.13.5 environment.

## Retained Uncertainty and Risks

- `zoidbergCoin.py` remains retained legacy code. Task 4F removed only its unused model import and initialization after repository-wide consumer tracing; it is not a supported deployment entry point.
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

## Task 4E: ecdsa Removal Verification

Task 4E removes the direct `ecdsa` core requirement and replaces its legacy
SECP256K1 implementation with the existing `cryptography==50.0.0` dependency.
The retained `zoidbergCoin.py` executable was not removed and its Transformers
imports were not changed; only its direct legacy `ecdsa` operations were
translated to the same cryptography compatibility helpers.

A clean Python 3.13.5 baseline installed the pre-migration requirements with
`ecdsa==0.19.2` and `cryptography==50.0.0`. The command `python -m pytest
tests/test_legacy_secp256k1_compatibility.py -q --basetemp <unique TEMP path>`
passed 13 Task 4D tests. A second clean Python 3.13.5 environment installed the
modified `requirements-test.txt`, passed `python -m pip check`, and reported
`Package(s) not found: ecdsa` for `python -m pip show ecdsa`.

The post-migration compatibility suite passed 29 tests, including fixed
historical low-S/high-S signatures, compressed-point parsing, scalar bounds,
raw signature lengths and ranges, legacy transaction serialization/block hash,
and peer block validation. Isolated imports of `api`, `blockchain`, `storage`,
`protocol_v1`, and `protocol_v1_genesis` passed with node/content/log paths
redirected under a unique TEMP directory. Collection reported 929 tests.

The requested targeted, integration, and full backend pytest processes each
completed using unique TEMP `--basetemp` directories. The Windows execution
wrapper detached their final summaries after emitting passing progress, but no
failure trace was emitted and no `lastfailed` cache was created. This is a
verification-output limitation, not a claim that the tests were rerun.

The exact CI command, `python -m pip_audit -r requirements-test.txt --strict`,
reports exactly five remaining findings, all in `transformers==4.57.6`:
`PYSEC-2025-217`, `PYSEC-2026-2290`, `PYSEC-2026-2288`, `PYSEC-2026-2289`, and
`GHSA-xrqw-3rrv-vx5w`. It does not report `ecdsa` or `PYSEC-2026-1325`, and no
new advisory or suppression was introduced. `python scripts/check_repository_hygiene.py`
passed, modified JSON reports parsed successfully, and active source/requirements
searches found no `ecdsa` imports or declarations.

## Task 4F: Unused Legacy Model Cleanup

Task 4F retains `zoidbergCoin.py` and removes only `from sentence_transformers
import SentenceTransformer`, its directly related model-load comment, and the
unused `model = SentenceTransformer('all-MiniLM-L6-v2')` initialization. A
repository-wide trace found no reads of `model`, no endpoint or originality
decision consumer, no dynamic lookup, and no deployment, test, script, or module
import path that relies on `zoidbergCoin.py`. Its supported originality path
remains Pillow, ImageHash, and pytesseract unchanged.

`requirements-originality.txt` removes only the direct
`sentence-transformers==3.3.1` declaration. No direct Transformers or Torch
declaration exists, so removing that parent removes the unused transitive model
chain without manually pinning or removing transitive packages.

A new source-level AST regression test verifies the legacy script contains no
SentenceTransformer import, model identifier, or model assignment; that supported
production sources do not import sentence-transformers or Transformers; and that
ImageHash, Pillow, and pytesseract remain declared. It does not import the legacy
script, access the network, or download a model.

A new external Python 3.13.5 environment installed `requirements-test.txt` and
`pip-audit==2.9.0`. `pip check` passed. `pip show sentence-transformers`, `pip
show transformers`, and `pip show torch` each reported `Package(s) not found`.
The exact CI command, `python -m pip_audit -r requirements-test.txt --strict`,
reported `No known vulnerabilities found` with exit code 0. No exception,
suppression, upgrade, or CI-threshold change was added.

With unique external Windows temporary `--basetemp`, JUnit XML, and logs, the
Task 4F plus legacy/originality/content/Protocol v1 targeted suite passed 219
tests; integration passed 21; and the complete suite passed 932. Application
imports of `api`, `blockchain`, `storage`, `protocol_v1`, and
`protocol_v1_genesis` passed from the clean installation. All Task 4 CI gates are
now expected to be green; Task 4F leaves the already-green frontend audit
untouched.
