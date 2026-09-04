# Continuous Integration

GitHub Actions runs [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) for every `push` and `pull_request`. All jobs use `contents: read`, check out without persisted credentials, have explicit time limits, and cancel an older in-progress run for the same workflow and Git ref. CI has no deployment, release, package publication, administrative, or write steps.

## Runtime Versions

- Python 3.13 is used by every Python job, matching the fresh-install verification in Milestone 2 Task 3.
- Node.js 24.13.0 is used by the frontend job. It is the recorded tested Node version and is supported by the Vite 6 lockfile.

## Gates

| Job | What it runs | Failure means |
| --- | --- | --- |
| `backend` | `pip check`, imports of `api`, `blockchain`, `storage`, and Protocol v1 modules with `DATA_DIR`, `NODE_DATA_DIR`, and `CONTENT_STORAGE_DIR` under the runner temporary directory, then `pytest --ignore=tests/integration` | A non-integration backend test fails, dependencies are inconsistent, or a major import is broken. |
| `integration` | `pytest tests/integration` with temporary state paths | An integration flow fails. It is partitioned from the backend job so the full suite is not run twice. Test fixtures retain their per-test temporary node state. |
| `frontend` | `npm ci`, `npm test`, `npm run build`, and `npm audit --audit-level=high` in `zoidbergcoin-ui` | The clean lockfile installation, frontend test/build, or a high/critical npm advisory fails. npm does not alter the lockfile. |
| `repository-hygiene` | `scripts/check_repository_hygiene.py` and its focused tests | Runtime state, environments, backups, caches, secret environment files, or generated artifacts have been tracked. |
| `secret-scan` | Exports `git archive HEAD`, then runs the maintained Gitleaks CLI container `zricethezav/gitleaks:v8.21.2` with `dir --source /repo --redact --no-banner` | A secret is detected in the current tracked revision. Findings are redacted; raw secret values are not printed. The scan runs locally in the GitHub runner and does not upload repository contents. |
| `python-dependency-security` | Complete test dependency installation followed by `pip-audit==2.9.0 -r requirements-test.txt --strict` | A dependency resolved from the complete documented test environment has an actionable published vulnerability, dependency resolution is incomplete, or the audit cannot run. The output identifies the package, advisory, and available fixed version. |

Python dependency caches key off all requirements files that define the complete test environment. The npm cache keys off `zoidbergcoin-ui/package-lock.json`. Neither cache contains repository runtime state or credentials.

## Local Equivalents

Use the Task 3 Python 3.13 environment. Keep node state outside the repository for import checks.

```powershell
.\.venv\Scripts\python.exe scripts\check_repository_hygiene.py
.\.venv\Scripts\python.exe -m pip check
$env:DATA_DIR = Join-Path $env:TEMP 'zoidbergchain-ci-data'
$env:NODE_DATA_DIR = $env:DATA_DIR
$env:CONTENT_STORAGE_DIR = Join-Path $env:TEMP 'zoidbergchain-ci-content'
.\.venv\Scripts\python.exe -c "import api, blockchain, storage, protocol_v1, protocol_v1_genesis"
.\.venv\Scripts\python.exe -m pytest --ignore=tests/integration
.\.venv\Scripts\python.exe -m pytest tests/integration
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m pip install pip-audit==2.9.0
.\.venv\Scripts\python.exe -m pip_audit -r requirements-test.txt --strict
$frontendCopy = Join-Path $env:TEMP "zoidbergchain-frontend-ci-copy"
$npmCache = Join-Path $env:TEMP "zoidbergchain-npm-cache"
Copy-Item -Recurse -Force zoidbergcoin-ui $frontendCopy
Push-Location $frontendCopy
$env:npm_config_cache = $npmCache
npm.cmd ci
npm.cmd test
npm.cmd run build
npm.cmd audit --audit-level=high
Pop-Location
```

For the exact current-tree secret scan, use a Bash-capable shell with Docker available:

```bash
scan_dir="$(mktemp -d)"
git archive --format=tar HEAD | tar -x -C "$scan_dir"
docker run --rm --volume "$scan_dir:/repo:ro" zricethezav/gitleaks:v8.21.2 dir --source /repo --redact --no-banner
```

The inherited Windows `esbuild.exe` and PyCharm npm-cache lock can block
`npm.cmd ci` inside the repository. The isolated copy/cache commands above
avoid that local lock without changing `package.json` or `package-lock.json`.
GitHub Actions runs `npm ci`, tests, the production build, and the audit in a
clean Linux checkout.

## Secret-Scanning Scope

The workflow exports exactly `HEAD` with `git archive` and scans that export with Gitleaks directory mode, rather than scanning the worktree or Git history. This excludes ignored local files and `.git` history. Task 2 removed current-tree credential and private-key-bearing state, but documented exposure remains in historical commits. A full-history scanner would therefore fail on known historical findings before owner-approved credential rotation and history cleanup. After owners complete that cleanup and coordinate fresh clones/force-push requirements as needed, change this gate to a full-history Gitleaks scan.

There is no allowlist in the current-tree scan. If a verified placeholder, fixture, hash, or scanner false positive requires one later, it must be narrowly documented and must not suppress an entire source directory or secret category. Actual secret values must never be added to an allowlist.

## Remediation

Do not use `npm audit fix`, `npm audit fix --force`, automatic Python upgrades, or broad advisory suppressions in CI. Record each finding by package and advisory, determine the smallest compatible dependency update in a separately scoped change, update the relevant declaration or lockfile there, and re-run these gates. A false-positive suppression requires concrete evidence and narrow documentation.

### Historical Task 4 Audit Baseline

The Task 4 local `pip-audit -r requirements-test.txt --strict` result intentionally fails with 47 advisories in the declared environment. No finding is suppressed. The affected packages and advisory identifiers are:

| Package | Advisory identifiers |
| --- | --- |
| `cryptography==45.0.6` | `PYSEC-2026-36`, `PYSEC-2026-35`, `PYSEC-2026-2141`, `PYSEC-2026-3552`, `PYSEC-2026-3553`, `PYSEC-2026-3554`, `GHSA-537c-gmf6-5ccf` |
| `ecdsa==0.19.0` | `PYSEC-2026-1325`, `PYSEC-2026-2467` |
| `python-multipart==0.0.20` | `PYSEC-2026-1852`, `PYSEC-2026-3038`, `PYSEC-2026-3037`, `PYSEC-2026-3036`, `PYSEC-2026-3040`, `PYSEC-2026-3039` |
| `requests==2.32.3` | `PYSEC-2026-1872`, `PYSEC-2026-2275` |
| `pillow==11.0.0` | `PYSEC-2026-165`, `PYSEC-2026-2250`, `PYSEC-2026-2253`, `PYSEC-2026-2255`, `PYSEC-2026-2257`, `PYSEC-2026-2256`, `PYSEC-2026-2254`, `PYSEC-2026-2252`, `PYSEC-2026-2249`, `PYSEC-2026-2874`, `PYSEC-2026-3453`, `PYSEC-2026-3451`, `PYSEC-2026-3454`, `PYSEC-2026-3495`, `PYSEC-2026-3496`, `PYSEC-2026-3494`, `PYSEC-2026-3493` |
| `pytest==8.4.1` | `PYSEC-2026-1845` |
| `starlette==0.41.3` | `PYSEC-2026-161`, `PYSEC-2026-249`, `PYSEC-2026-248`, `PYSEC-2026-1942`, `PYSEC-2026-1941`, `PYSEC-2026-2281`, `PYSEC-2026-2280` |
| `transformers==4.57.6` | `PYSEC-2025-217`, `PYSEC-2026-2290`, `PYSEC-2026-2288`, `PYSEC-2026-2289`, `GHSA-xrqw-3rrv-vx5w` |

The Task 4 lockfile-only `npm audit --audit-level=high` result also intentionally fails: five high and one critical finding, with two additional moderate findings. The high/critical affected packages are `axios`, `form-data`, `nanoid`, `postcss`, and `rollup`; `esbuild` and `follow-redirects` are the moderate findings. These require a separate lockfile/dependency remediation task.

### Task 4F Current Python Result

Task 4F retains `zoidbergCoin.py` but removes only its unused
`SentenceTransformer('all-MiniLM-L6-v2')` import-time initialization and the
direct `sentence-transformers` declaration. The model had no consumers, and the
supported Pillow, ImageHash, and pytesseract originality path is unchanged.

In a new external Python 3.13.5 environment, the exact current CI input,
`requirements-test.txt`, passed `python -m pip check`; `sentence-transformers`,
`transformers`, and `torch` were absent; and the exact command
`python -m pip_audit -r requirements-test.txt --strict` reported `No known
vulnerabilities found` with exit code 0. The five historical Transformers
advisories are resolved without an exception, suppression, dependency upgrade,
or CI-threshold change. The Python dependency-security gate is expected to pass.

Lint and formatting enforcement are deliberately deferred to a later milestone task.
