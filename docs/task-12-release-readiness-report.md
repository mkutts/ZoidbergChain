# Task 12 Release-Readiness Report

Date: 2026-09-04. Scope was limited to final dead-code cleanup, documentation,
and verification. No commit, push, dependency change, route-contract update,
frontend source change, CI change, or protocol/consensus/signing/storage change
was made.

## Starting Evidence

- Branch: `Repository-Hygiene-and-Core-Refactor`.
- HEAD: `9041908f6842e52a4a1859005fe54ae005859679` (`Extract FastAPI domain
  routers and service boundaries`).
- The worktree was clean before Task 12 edits.
- Task 11 was separately committed as the current tip. The preceding Task 6--10
  extraction commits are also separate history entries.
- No pre-edit mismatch or unrelated tracked change was found.

## Deletions With Evidence

| Deleted item | Proof of non-use | Regression evidence |
| --- | --- | --- |
| `api_routers/_routing.py` and its `build_router` forwarding adapter | Static repository search found its only production use in the fallback branch of `api_routers.__init__`; all seven installed router modules declare `EXPLICIT_ROUTER = True`. | `tests/api/test_task_12_cleanup.py` asserts that the builder is absent and imports the app to verify all 129 concrete routes in frozen order. |
| Seven `ROUTES` manifests in the explicit router modules | The manifests were consumed only by that deleted builder; actual decorators and `_ROUTE_ORDER` maps already own the endpoints and their order. The old Task 11 tests used the manifests only for static introspection and now inspect installed `APIRoute` objects instead. | Route contract, router ownership, OpenAPI, import-isolation, and full backend tests pass. |
| Duplicate `import time` in `blockchain.py` | Both imports bound the same module name; the second binding had no semantic effect. | Protocol, genesis, serialization, integration, and full backend suites pass. |

## Intentionally Retained Compatibility Code

- `api.py` remains the `api:app` compatibility module and forwards historical
  attributes to `api_runtime`.
- Router `_sync_runtime_globals` helpers remain: tests and deployment-style
  callers monkeypatch historical `api` globals, which must become visible to
  concrete router handlers without replacing module identity.
- `api_runtime` re-exports and shared helpers remain. Static single-file
  import-use analysis cannot classify them as dead because routers import them
  through the established compatibility surface; examples include content hash
  helpers and environment predicates used directly by API tests.
- `_ROUTE_ORDER` maps remain live route-order bindings. They preserve matching
  and shadowing semantics for the frozen 129-route contract.

## Verification

The full backend and integration runs used a clean short-path disposable copy
to prevent repository runtime-state writes and avoid Windows path-length issues.

An early focused pytest invocation used the source worktree before that isolation
strategy was adopted. Its existing fixtures create ignored directories under
`temp/test-data`; that directory already contained substantial user-owned test
data, so Task 12 does not delete any of it without a precise ownership boundary.
Tracked hygiene is clean, but the strict claim that no ignored repository-root
runtime path was modified during the entire local verification sequence cannot
be certified retrospectively. All subsequent authoritative suites ran only in
the disposable copy.

| Check | Result |
| --- | --- |
| Task 12 cleanup, Task 11 router architecture, and architecture/import guards | 18 passed in 4.11s; exit 0. |
| Protocol v1, serialization, genesis, golden vectors, lifecycle, and certificate block tests | 132 passed in 11.95s; exit 0. |
| Explicit integration suite | 21 passed in 7.63s; exit 0. |
| Full backend suite | 971 passed in 142.20s; exit 0. |
| Repository hygiene checker | Passed; exit 0. |
| Repository hygiene tests | 2 passed in 0.02s; exit 0. |
| `pip check` | `No broken requirements found`; exit 0. |
| `python -m pip_audit -r requirements-test.txt --strict` | `No known vulnerabilities found`; exit 0. |
| Isolated frontend `npm ci` | 63 packages installed, 64 audited, 0 vulnerabilities; exit 0. |
| Isolated frontend tests | 130 passed, 0 failed; exit 0. |
| Isolated frontend build | Passed; 114 modules transformed; exit 0. |
| Isolated frontend `npm audit --audit-level=high` | 0 vulnerabilities; exit 0. |
| Tracked JSON validation | 12 files parsed successfully; exit 0. |
| `git diff --check` | Passed; exit 0. |

The FastAPI/Starlette `TestClient` deprecation warning remains documented and
unsuppressed. It does not fail the suite.

## Secret Scan And Owner Actions

The current-tree scan was prepared from the tracked tree plus Task 12 changes,
but Gitleaks could not run locally: Docker Desktop's Linux daemon was not
running or reachable, including after an elevated retry. The CI
`secret-scan` job remains verified as configured: it exports the tracked tree
and invokes pinned `zricethezav/gitleaks:v8.21.2` with no allowlist. Local
absence of the daemon is not a substitute for that CI gate.

Owners must still rotate any historically exposed credentials and coordinate
history cleanup and fresh-clone/force-push procedures before enabling a
full-history scan. That action is intentionally outside Task 12.

## Final Assessment

All code-level Milestone 2 acceptance checks exercised locally pass: 129 frozen
routes in order, unchanged import-cycle baseline, no runtime endpoint handlers
or generic forwarding in `api_runtime`, and Protocol v1/Model A/genesis
regressions. The frozen genesis media SHA-256 remains
`dfba5a7e5e8e5f5da047a2ed58660c9d52665c39f2793da90cba51419f8525c7`; the
frozen genesis hash remains
`2b99e87f80e0e855ab98b3269b635be5415273f41d7d4bf1a2aeb8b277b13061`.

Release approval still requires the configured CI current-tree Gitleaks job (or
a local Docker daemon), the owner-managed historical credential remediation,
and a clean verification rerun if the no-repository-runtime-write requirement
must be evidenced without qualification.
