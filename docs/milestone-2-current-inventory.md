# Milestone 2 Task 1: Current Repository Inventory

Inventory date: 2026-09-01. Scope: diagnostic baseline only. No production code, dependencies, tracked files, or git history were changed.

## 1. Executive Summary

The repository is `mkutts/ZoidbergChain`, and the active branch is exactly aligned with `origin/main` at the frozen Public Testnet v1 commit. The backend baseline is healthy: 898 tests pass, including 21 explicit integration tests. The frontend cannot be installed or fully exercised in this Windows environment because `npm ci` fails on an existing locked `esbuild.exe`; the current partial `node_modules` tree consequently causes five frontend module-resolution failures and a build failure.

The worktree is clean. Tracked hygiene is not clean: `.env`, private-key-bearing blockchain state, wallets/peers/chain state, backups, uploaded content, patches, debug material, and a complete Windows virtual environment are committed. A tracked `blockchain.json` is runtime state, not the canonical genesis source. The authoritative genesis source is the frozen base64 fixture consumed by `protocol_v1_genesis.py`; the frozen genesis record is also embedded in the runtime chain representation and must be preserved semantically.

No protocol changes are proposed. Task 2 should address repository hygiene, credential exposure, and dependency cleanup only after owner decisions and any needed credential/history response.

## 2. Repository Identity and Environment

| Item | Result |
|---|---|
| Remote | `https://github.com/mkutts/ZoidbergChain.git` |
| Initial branch | `Repository-Hygiene-and-Core-Refactor` |
| HEAD | `5bd09cb39d25189c8918460b3ca3e63f824ac4ee` |
| HEAD decoration | `public-testnet-v1-protocol-freeze` |
| `origin/main` | `5bd09cb39d25189c8918460b3ca3e63f824ac4ee` |
| HEAD vs origin/main | `0 ahead, 0 behind` |
| Relevant tags | `public-testnet-v1-protocol-freeze`; `backup-broken-privy-merge-before-rollback` |
| OS | Windows 10 Home, build 2009, x64 |
| Python used for tests | Python 3.13.5 from `.venv` |
| pip used for inventory | pip 25.1.1 |
| Node | v24.13.0 |
| npm | `npm.cmd` available; `npm.ps1` blocked by PowerShell execution policy |
| Worktree | Clean before and after diagnostics; no pre-existing changes found |
| Fetch | `git fetch origin --prune` succeeded with elevated filesystem permission; no merge/rebase |

The configured PyCharm interpreter probe failed on the inaccessible `.pytest_cache` path. The repository `.venv` was used explicitly and is valid. The separately tracked `venv` is broken and points at `C:\Users\19142\AppData\Local\Programs\Python\Python312\python.exe`.

## 3. Prompt-versus-Current-Repository Mismatches

- The historical claim that the old `Freeze-ZoidbergChain-Public-Testnet-v1-Protocol` branch is one commit behind main is verified for the remote refs: `origin/Freeze-ZoidbergChain-Public-Testnet-v1-Protocol` is `173251c`, one commit behind `origin/main`. The current working branch is not that old ref and is at main.
- The historical report of tracked runtime state, backups, a Windows venv, content, `.env`, patches, and debug artifacts remains materially accurate.
- The current repository contains later Task 10/11 work and documentation, while its public roadmap still describes the older Task 1/Task 10-18 sequence. No explicit Milestone 2 Task 1 definition was found in the tracked repository; this report follows the supplied prompt as the authority.
- The repository uses FastAPI in current production code, but `requirements.txt` still includes several Flask-era packages.
- The prompt calls for `npm ci`; the command is documented and was attempted, but Windows denied unlinking `zoidbergcoin-ui/node_modules/@esbuild/win32-x64/esbuild.exe`.

## 4. Baseline Test and Build Results

| Area | Exact command | Result |
|---|---|---|
| Backend | `.venv\Scripts\python.exe -m pytest` | PASS, 898 passed in 83.04s |
| Integration | `.venv\Scripts\python.exe -m pytest tests\integration -q` | PASS, 21 passed in 7.67s |
| Frontend install | `cd zoidbergcoin-ui; npm.cmd ci` | BLOCKED, `EPERM` unlinking existing `esbuild.exe`; likely file lock/Windows permissions |
| Frontend tests | `npm.cmd test` | FAIL, 87 discovered, 82 passed, 5 failed, 300.58ms; missing `axios`, `vue` modules |
| Frontend build | `npm.cmd run build` | FAIL, missing `vite` module because install is incomplete |

The full pytest run includes the integration tests, but the integration directory was also run explicitly. No pytest failures, skips, or xfails were reported. The frontend command emitted npm's warning about unknown config `min-release-age`; this was not the blocking cause.

## 5. Tracked-File Hygiene Findings

There are 1,323 tracked paths. Of these, 1,031 are under `venv/` and are virtual-environment files. The remaining tracked tree includes 21 content/media paths, 5 runtime/backup state paths in the targeted inventory, 2 patch files, and environment/runtime files listed below.

| Classification | Tracked examples | Assessment |
|---|---|---|
| Runtime state | `blockchain.json`, `peers.json`, `wallets.json`, `data/`-related committed state where present | Mutable node state; should not be source-controlled except for an explicitly designated canonical fixture |
| Backup | `blockchain.json.bak`, `peers.json.bak`, `legacy-chain-backup/`, `pre-genesis-meme-v1-backup/` | Historical/export material; owner must choose retention location and access policy |
| Runtime media/cache | `content/**`, `temp/download.jpg`, `preprocessed_image.jpg` | Mutable uploaded/downloaded/derived content; distinct from canonical genesis media |
| Virtual environment | `venv/**` | Generated environment; also broken due to an absolute path to another user installation |
| Environment/secrets | `.env` | High-confidence credential exposure; tracked despite `.gitignore` because it was committed previously |
| Debug/diagnostic | `collect.txt`, `DIAGNOSTIC_REPORT.txt`, `api.log` if tracked in history/working copies | Generated or diagnostic output, not source; inspect before owner-approved removal |
| Obsolete patches | `rollback-prep-working-tree.patch`, `zoidberg-runtime-config-fix.patch` | Generated change artifacts; likely obsolete, retain only if owner identifies a recovery purpose |
| Required static assets | `static/**`, frontend public assets, whitepaper files | Retain when referenced by the application or deployment documentation |

The repository `.gitignore` covers `.env`, virtual environments, logs, `data/`, `temp/`, caches, `node_modules/`, and build output, but those rules do not remove already tracked paths. Test execution generated/used ignored temporary state; it did not create tracked changes.

## 6. Secret Findings Without Secret Values

No secret scanner was installed (`gitleaks`, `trufflehog`, and `detect-secrets` were unavailable). Targeted current-tree and history searches were performed without documenting secret values.

| File/category | Finding | Confidence | Required owner action |
|---|---|---|---|
| `.env`, line 1/category `API_KEYS` | Tracked API credential mapping contains concrete credential values | High | Treat as exposed; revoke/rotate affected API credentials, remove from future repository state, and decide on history cleanup |
| `blockchain.json`, repeated `private_key` fields | Tracked runtime chain/wallet records contain private-key material | High | Assume keys are compromised; identify affected wallets, move/replace funds or testnet identities as appropriate, rotate/remove material, and decide on history cleanup |
| `wallets.json`, `peers.json`, chain state | Runtime identity/peer data may expose operational identities or credentials; exact value classification was intentionally not printed | Medium/uncertain | Owner review of the files and deployment use; do not publish or rotate blindly |
| Source/tests/docs | Secret-shaped names and test fixtures include placeholders and test-only values | Low for production exposure | Confirm test values are non-production; keep values out of reports and logs |

Relevant history shows `.env` and state files were committed as early as `2ddc841` and repeatedly carried into later commits, including `5bd09cb`. No rotation or history rewrite was performed.

## 7. Canonical Protocol Assets Versus Runtime State

The authoritative Public Testnet v1 genesis media representation is `public_testnet_v1_genesis_meme_base64.txt`, loaded and validated by `protocol_v1_genesis.py`. The module fixes the media hash, MIME type, byte length, encoded length, canonical payload, and canonical genesis hash. `tests/fixtures/protocol_v1_golden_vectors.json` is a protocol test fixture. `blockchain.json` contains a runtime serialized chain whose genesis record includes the embedded Model A media bytes and the frozen genesis hash; it is not the source-of-truth fixture merely because it contains the same media. `legacy-chain-backup/**` and `pre-genesis-meme-v1-backup/**` are backups/legacy state, not canonical protocol sources.

Classification:

- `protocol_v1.py`, `protocol_v1_genesis.py`, `protocol_v1_native_transfer.py`, `protocol_v1_originality.py`, `protocol_v1_peer_message.py`: source code implementing frozen protocol objects, serialization, genesis, native-transfer, originality, and peer-message rules.
- `public_testnet_v1_genesis_meme_base64.txt`: canonical protocol/genesis fixture, required by the genesis builder.
- `tests/fixtures/protocol_v1_golden_vectors.json`: canonical test fixture for frozen vectors.
- `blockchain.json`: mutable runtime state containing a canonical genesis record; not disposable until validated/exported and reset under an owner-approved plan.
- `content/**`: runtime content cache/upload store, not canonical genesis material.
- `blockchain.json.bak`, `legacy-chain-backup/**`, `pre-genesis-meme-v1-backup/**`: backup or obsolete historical state requiring owner review.

## 8. Dependency Inventory

Dependency groups are: FastAPI/Pydantic/Starlette/Uvicorn API stack; security and signing (`cryptography`, `ecdsa`, `eth-account`, `eth-keys`, `pycryptodome`); HTTP/storage (`requests`, `httpx`, SQLAlchemy, SQLite stdlib); content/originality (`Pillow`, `ImageHash`, `pytesseract`); rate limiting and configuration (`slowapi`, `python-dotenv`); legacy/data-science/ML (`numpy`, `pandas`, `scipy`, `scikit-learn`, `matplotlib`, `PyWavelets`, `joblib`, `networkx`, `sentence-transformers`, `torch`, `transformers`, `huggingface-hub`, `safetensors`, `tokenizers`, `lightgbm`, `xgboost`); forecasting/Spark/Mongo (`prophet`, `cmdstanpy`, `holidays`, `pyspark`, `py4j`, `pymongo`); test-only (`pytest`, `pytest-cov`); and transitive/support packages.

Static import evidence, not proof of necessity:

- Clearly imported by current production paths: `fastapi`, `pydantic`, `slowapi`, `Pillow`, `ImageHash`, `pytesseract`, `eth-account`, `cryptography`, `ecdsa`, `requests`, `python-dotenv`, and test/runtime support packages.
- Imported by scripts or legacy production entry points: `sentence-transformers` appears in `zoidbergCoin.py`; `requests` appears in `sync.py` as well as peer sync; `pytesseract` and Pillow appear in legacy/content paths.
- Likely Flask-era or unused by current FastAPI production imports: `Flask`, `Flask-Cors`, `Flask-JWT-Extended`, `Flask-SQLAlchemy`.
- No current source import evidence found for the Spark/Mongo/Prophet family: `pyspark`, `py4j`, `pymongo`, `prophet`, `cmdstanpy`, `holidays`, `stanio`.
- No current source import evidence found for the XGBoost/LightGBM and broad data-science stack in the maintained API/blockchain paths: `xgboost`, `lightgbm`, `pandas`, `scipy`, `matplotlib`, `scikit-learn`, `torch`, `transformers`, `huggingface-hub`, `safetensors`, and `tokenizers`, subject to the legacy `zoidbergCoin.py` exception above.
- `pytest` and `pytest-cov` are test/development-only. `requirements-test.txt` includes the full runtime requirements plus these test packages.

Do not remove or edit dependencies in Task 1. Import analysis cannot prove optional, dynamic, transitive, deployment, or operator-script requirements are unnecessary.

## 9. Architecture and Module-Responsibility Map

| Module | Lines | Major responsibilities/symbols |
|---|---:|---|
| `api.py` | 6,913 | FastAPI app/lifespan, routers, auth/access/admin services, upload/content endpoints, submission/voting/certificate endpoints, peer sync endpoints, native-account/transfer/mempool endpoints, ops/status endpoints |
| `blockchain.py` | 6,424 | `Blockchain`, chain loading/saving, block and transaction validation, originality/certificate lifecycle, mint queue/rewards, native balances/nonces/mempool, fork replacement/finality-adjacent checks |
| `peer_sync.py` | 3,026 | Signed peer HTTP requests, replay protection, submission/vote/certificate/block/transaction exchange, content sync, chain candidate validation and synchronization |
| `content.py` | 1,290 | `ContentObject`, content hashing/canonicalization, MIME/type checks, local content storage and verification |
| `storage.py` | 1,121 | `StorageBackend`, JSON and SQLite backends, atomic writes/backups, entity query helpers, integrity checks and backend factory |
| `submission.py` | 163 | Submission statuses/transitions, content hash derivation, `Submission` model |
| `native_transfer.py` | 832 | Native ZOID transfer message/transaction models, canonical transaction IDs, amount/nonce/status validation, MetaMask signature verification |
| `protocol_v1.py` | 303 | Protocol identifiers/domains, canonical JSON and byte encoding, domain envelopes and hashes |
| `protocol_v1_genesis.py` | 593 | Frozen genesis fixture loading, Model A media validation, canonical genesis record/hash and chain validation |
| `protocol_v1_native_transfer.py` | 262 | Frozen native-transfer payload/signing/identity serialization and parsing |
| `protocol_v1_originality.py` | 333 | Frozen vote/certificate payloads, normalization, vote/certificate hashes and IDs |
| `protocol_v1_peer_message.py` | 883 | Frozen peer envelope/header serialization, signed peer messages, routes, replay store and verification |

Responsibility map: protocol objects/serialization live in `protocol_v1*.py` and are consumed by block, native-transfer, originality, and peer layers; consensus validation and fork choice live primarily in `blockchain.py` and candidate-chain helpers in `peer_sync.py`; submissions and certificates span `submission.py`, `originality_certificate.py`, `blockchain.py`, and API routers; ledger, balances, nonces, mempool, and rewards are in `blockchain.py` with persistence through `storage.py`; networking/synchronization is split between `api.py`, `peer_sync.py`, and `peers.py`; storage is abstracted by `storage.py`; API routing and service orchestration are concentrated in the large `api.py` module.

## 10. Duplicate and Dead-Code Candidates

- `blockchain.py:5200` and `blockchain.py:5226` both define `remove_invalid_mint_queue_entries`; determine which definition is authoritative before Task 2. Tests currently pass, so this is a review candidate, not an approved removal.
- `api.py:42` and `api.py:6286` duplicate the `extract_text` import; likely redundant, but leave unchanged in Task 1.
- `storage.py` repeats interface methods in `StorageBackend`, `JSONStorageBackend`, and `SQLiteStorageBackend`; these are expected abstract/concrete overrides, not automatically duplicate dead code.
- `protocol_v1_native_transfer.py` imports from `native_transfer.py`, while `native_transfer.py` imports from `protocol_v1_native_transfer.py`; this is an obvious import-cycle risk requiring owner-reviewed sequencing/refactor in a later task. Current tests pass, so no change was made.
- `zoidbergCoin.py`, `sync.py`, `tessTest.py`, patches, logs, and collection/debug files are dead-code or generated-output candidates only after checking deployment/runbook references.
- Import-time state creation and API lifespan initialization exist around `api.py:1771` and `api.py:1738`; verify startup side effects and test isolation before any relocation.

## 11. Exact Proposed Cleanup List for Task 2

1. Remove tracked `.env` from repository state after credential rotation and owner approval; retain `.env.example` only.
2. Remove tracked `venv/**`; retain environment creation instructions and verify `.venv/` remains ignored.
3. Remove or relocate mutable `blockchain.json`, `peers.json`, `wallets.json`, their `.bak` files, and state under legacy/pre-genesis backup directories according to an explicit retention/export policy.
4. Remove tracked runtime content/cache files under `content/**`, `temp/download.jpg`, `preprocessed_image.jpg`, and similar generated media, while preserving the canonical genesis fixture and required static assets.
5. Remove or archive `rollback-prep-working-tree.patch` and `zoidberg-runtime-config-fix.patch` after confirming they are no longer recovery inputs.
6. Remove tracked diagnostic/collection artifacts such as `collect.txt` and any committed logs/debug outputs after owner review.
7. Separate canonical protocol/genesis fixtures from mutable runtime state in documentation and reset/deployment procedures.
8. Build a dependency-removal proposal from import evidence, starting with clearly unused Flask-era, Spark/Mongo/Prophet, and broad ML/data-science packages; verify scripts and deployment before editing dependency files.
9. Resolve the duplicate mint-queue definition, redundant import, and protocol/native-transfer cycle in a separately scoped production-code task.
10. Add/verify ignore rules and CI checks for secrets, virtual environments, runtime state, caches, logs, backups, and generated output.

## 12. Owner-Only Actions

- Rotate/revoke API credentials found in tracked `.env` immediately.
- Treat tracked blockchain `private_key` material as compromised and determine whether any non-disposable wallet or signing identity was exposed.
- Decide whether repository history must be rewritten to remove credential/private-key material. This report did not rewrite history.
- Decide retention and secure storage for chain backups, wallet/peer state, and any public or private testnet identities.
- Confirm whether the legacy `zoidbergCoin.py` ML path and its dependencies remain supported.
- Approve any cleanup that could remove state needed to reproduce or audit the frozen genesis; canonical genesis source must remain available.

## 13. Remaining Uncertainties and Risks

- No dedicated secret scanner was available; targeted scanning is not equivalent to a complete historical secret scan.
- The exact operational meaning of every wallet/peer field was not printed or inferred from values.
- Static imports do not prove dependency necessity or dispensability.
- Frontend verification is incomplete because `npm ci` was blocked by a Windows file lock/permission condition.
- The repository has many ignored generated files from tests and prior operations; they are not tracked findings but can obscure local-state provenance.
- The current branch name suggests hygiene/refactor work, but the prompt forbids beginning Task 2; no cleanup was performed.

## 14. Task 1 Acceptance-Criteria Result

| Criterion | Result |
|---|---|
| Baseline identity, fetch, and origin comparison recorded | PASS |
| Existing worktree changes preserved | PASS; worktree was clean |
| Repository and tests inspected | PASS |
| Tracked hygiene and targeted secret audit completed without documenting secret values | PASS, with scanner-unavailable limitation |
| Canonical genesis distinguished from runtime cache/state | PASS |
| Dependency and architecture inventories recorded | PASS |
| Documented backend and explicit integration baselines run | PASS |
| Frontend install/test/build attempted and failures captured | PASS; environment blocked install and dependent commands |
| Only requested inventory reports changed | PASS at final verification |
| Production code/dependencies/history changed | PASS; none changed |
| Task 2 started | NO; intentionally not started |

Overall Task 1 result: **PASS with documented environment limitations and owner-only security actions required before cleanup.**
