# Task 10 Peer Networking And Synchronization Extraction

Date: 2026-09-03

## Scope And Preflight

The initial branch was `Repository-Hygiene-and-Core-Refactor` at
`13c0e2d2b2cc4bc7f99cd8b060eb45c3581087c6`. That separate top commit is Task 9,
`Extract block production and consensus services`. The worktree was clean before
editing, and no repository/prompt mismatch was found. No commit or push is part of
this task.

This change is limited to peer authentication, transport/broadcast, content
synchronization, chain-summary/block retrieval, synchronization coordination,
facade delegation, characterization tests, and architecture documentation. It does
not alter FastAPI routes, Protocol v1, genesis, storage formats, peer discovery,
consensus, validator selection, or finality.

## Ownership

| Prior `peer_sync.py` responsibility | Task 10 owner |
|---|---|
| Canonical body hashing/serialization, signature payloads, signed and shared-secret headers, timestamp verification, signature error mapping, nonce-cache maintenance | `PeerAuthenticationService` |
| Concrete HTTP GET/POST calls | `PeerHttpTransport` |
| Submission, vote, certificate, block, and native-transaction outbound payloads; peer ordering; timeouts; success/failure aggregation; existing warning messages | `PeerBroadcastService` |
| Content metadata and binary retrieval, size/MIME/hash validation, Model A full-byte storage, and multi-peer missing-content outcomes | `PeerContentSyncService` |
| Chain-summary and candidate-block retrieval, response normalization, per-peer failure accounting, synchronization coordination, and adoption requests | `PeerChainSyncService` |
| Score/height/lower-tip-hash summary ranking | Existing Task 9 `ForkChoiceService`, reached through `Blockchain.compare_chain_summaries` |

`peer_sync.py` remains the public compatibility facade. Its original 3,026 lines
are 2,122 lines after Task 10, a reduction of 904 lines.

## Deliberately Retained Responsibilities

Inbound submission, vote, certificate, native-transaction, and block receipt stays
in the facade because normalization is tightly coupled to the existing domain
objects and facade-owned collections. Certificate storage and vote-set comparison,
candidate block normalization, and accepted-block mutation also remain there.

The facade exclusively performs candidate-chain replacement: removal of confirmed
pending transactions, authoritative `chain` rebinding, reward-pool recomputation,
submission canonical-state reconciliation, native-transaction reconciliation, and
whole-state persistence. This preserves ordering and prevents networking services
from owning or caching blockchain state. Startup/application lifespan scheduling is
not present in `peer_sync.py`; the existing explicit synchronization entry point is
preserved and now delegates per-peer coordination and aggregation.

## Security And Compatibility Boundaries

- Existing public names, arguments, return shapes, exceptions, side effects, and
  tested warning messages remain available from `peer_sync.py`.
- Canonical JSON separators, UTF-8 encoding, body hashes, signing domain, signed
  GET query payloads, headers, timestamps, nonces, shared-secret fallback, and
  authentication order are unchanged.
- Peer paths, methods, query parameters (`from_height` and
  `include_media_bytes=true`), payload fields, configured timeouts, active-peer
  ordering, and broadcast aggregation are unchanged.
- Unknown-peer and wrong-network rejection remains in the receipt facade before
  any accepted mutation. Signature, replay, content-integrity, and transaction
  checks are not weakened.
- Content sync still verifies metadata, MIME type, size, and payload hash before
  registration. The exact accepted media bytes are written and then represented by
  the existing content object; persistence remains a facade action.
- Summary ranking delegates to Task 9 fork choice. Candidate normalization and
  validation still call the existing Blockchain compatibility methods, and the
  sole adoption callback preserves the previous mutation/save sequence.
- Peer services import neither the concrete `Blockchain` class, `api`, nor FastAPI,
  and add no storage ownership, import cycle, or architecture exception.

## Verification Contract

Focused direct service tests cover canonical signed bytes and tampering, broadcast
partial failure, exact full-media-byte preservation, chain-sync delegation and
adoption, and framework-independent imports. Existing peer/API/integration suites
remain the detailed characterization for missing/invalid signatures, shared-secret
failures, unknown peers, networks, timestamps, replay, all propagated object types,
malformed responses, candidate rejection/adoption, and operational finality.

The API route fixture remains exactly 129 routes. Frozen genesis media SHA-256 is
`dfba5a7e5e8e5f5da047a2ed58660c9d52665c39f2793da90cba51419f8525c7` and frozen
genesis hash is
`2b99e87f80e0e855ab98b3269b635be5415273f41d7d4bf1a2aeb8b277b13061`.

## Recorded Verification

All final pytest commands used Python 3.13, a unique `--basetemp`, and a JUnit XML
report. Final runs reported zero failures, zero errors, and zero skips.

| Verification | Result |
|---|---|
| Direct Task 10 networking services | exit 0; 5 passed; 0 failed/errors/skipped; 3.52s |
| Peer auth, hardening, and Protocol v1 peer messages | exit 0; 45 passed; 0 failed/errors/skipped; 2.41s |
| Submission, vote, certificate, content, block, and native-transaction propagation | exit 0; 94 passed; 0 failed/errors/skipped; 9.01s |
| General peer networking API | exit 0; 8 passed; 0 failed/errors/skipped; 1.23s |
| Chain sync, candidate adoption, and storage regression | exit 0; 33 passed; 0 failed/errors/skipped; 5.99s |
| Task 9 consensus-service regressions | exit 0; 5 passed; 0 failed/errors/skipped; 0.86s |
| Protocol v1, canonical/golden vectors, genesis, block format, and finality | exit 0; 116 passed; 0 failed/errors/skipped; 3.33s |
| Architecture, import cycles, isolated imports, and 129-route contract | exit 0; 5 passed; 0 failed/errors/skipped; 3.07s |
| Existing two-node consensus/native/storage tests | exit 0; 17 passed; 0 failed/errors/skipped; 5.91s |
| Explicit integration suite | exit 0; 21 passed; 0 failed/errors/skipped; 7.39s |
| Final peer-content facade/service tests | exit 0; 15 passed; 0 failed/errors/skipped; 8.14s |
| Historical anomalous complete backend suite (not acceptance timing) | exit 0; 958 passed; 0 failed/errors/skipped; JUnit 5,325.838s, caused by one 5,219.715s non-networking mint-queue testcase |
| Verification follow-up: mint-queue plus direct Task 10 peer services | exit 0; 13 passed; 0 failed/errors/skipped; pytest 1.44s; measured process wall time 2.074s |
| Verified complete backend suite | exit 0; 958 passed; 0 failed/errors/skipped; JUnit 81.730s (80.357s testcase sum; 1.373s suite overhead) |
| Repository hygiene checker | exit 0; passed; 0.128s |
| All tracked JSON fixtures/documents | exit 0; 12 parsed; 0 failures; 0.144s |
| `git diff --check` | exit 0; no whitespace errors; 0.050s |

An earlier complete-suite attempt placed every fixture outside the workspace. It
reported 953 passed and five reset-script failures in 79.04s because those security
tests deliberately reject reset targets outside the repository. No application test
failed.

The 5,325.838-second JUnit value is an actual pytest testcase measurement, not
detached-terminal waiting: testcase durations sum to 5,324.132 seconds and suite
overhead is only 1.706 seconds. One unrelated test,
`tests.submissions.test_mint_queue::test_mint_removal_and_status_update`, accounts
for 5,219.715 seconds. It bypasses block construction with an instance-level
`add_block` monkeypatch and does not call peer synchronization or transport. The
same test took 0.075 seconds in the immediately preceding successful Task 10 full
run; Task 10 networking tests were 19.024 seconds in the anomalous run versus
16.195 seconds in that preceding run. Static review found no sleep, retry loop,
executor, session, or response lifecycle in the Task 10 peer services. The
historical delay is therefore an isolated, non-reproducible pause during that test,
not a Task 10 networking regression or wrapper-reporting artifact.

The verification rerun used the repository's standard isolated fixtures and a
fresh `--basetemp`, after clearing `NODE_DATA_DIR` and `DATA_DIR` from the child
environment. Its pytest child was observed starting at 2026-09-03T15:01:09-04:00;
the completed JUnit report was written at 2026-09-03T15:02:32.0872270-04:00. It
reports 958 passed with zero failures, errors, and skips in 81.730 seconds (pytest
exit code 0). The desktop wrapper again stopped relaying console output before its
trailing timing record, but the finished child and fresh JUnit establish the actual
pytest duration. No production code changed. Metadata snapshots confirmed that the
repository-root blockchain, wallet, peer, SQLite, secret, log, content, data, and
log directory targets were unchanged across the run. All peer traffic in tests used
fake clients or monkeypatched requests; no external peer was contacted.
