# Milestone 2 Architecture

Date: 2026-09-02. This is a characterization baseline, not a refactor plan or
claim that the target structure already exists. Protocol v1 behavior, canonical
serialization, genesis, signatures, consensus, and media integrity are frozen.

## Current Architecture

`api.py` is the stable `api:app` compatibility entry point. `api_runtime.py`
owns application wiring, middleware, lifespan state, dependencies, request and
response schemas, shared serializers, and narrow support helpers; it owns no
endpoint handlers or generic route forwarding. The seven modules in
`api_routers/` own all concrete FastAPI endpoints. `blockchain.py` remains the
state-owning compatibility facade for acceptance, persistence coordination, and
the public domain operations used by the routers. `peer_sync.py` remains the
peer-facing compatibility facade; `services/` holds the extracted framework-free
domain, consensus, ledger, reward, and peer-service logic. `storage.py`
implements JSON and SQLite adapters, while Protocol v1 modules provide
deterministic protocol objects and validation helpers.

`blockchain.py` and `peer_sync.py` intentionally retain their compatibility
surfaces. `Blockchain` is created in the application lifespan; top-level logging
and lightweight session/store objects retain their established behavior.

### Coverage And Responsibility Matrix

| Area | Current owner and public surface | Existing characterization tests | Coverage note and later destination |
|---|---|---|---|
| Protocol objects and canonical serialization | `protocol_v1.py`: canonical JSON/domain/hash helpers | `test_protocol_v1.py`, `test_protocol_v1_golden_vectors.py`, `test_protocol_v1_freeze_consistency.py` | Strong vectors; target protocol/domain objects. |
| Genesis | `protocol_v1_genesis.py`: genesis record/media/hash validation | `test_protocol_v1_genesis.py`, `test_protocol_v1_golden_vectors.py` | Strong canonical rejection/acceptance; target protocol/domain. |
| Block construction and validation | `blockchain.py`: `Blockchain`, block validators | `test_blockchain_smoke.py`, `test_protocol_v1_block_format.py`, `test_certificate_block_validation.py` | Strong deterministic outcome coverage; target chain service. |
| Certificate validation | `blockchain.py`, `originality_certificate.py`, `protocol_v1_originality.py` | `test_originality_certificate.py`, `test_certificate_block_validation.py`, `test_protocol_v1_originality_votes.py` | Strong linkage/version coverage; target originality service. |
| Fork choice | `blockchain.py`, `peer_sync.py` candidate-chain helpers | `test_chain_originality_comparison.py`, `test_cumulative_originality_score.py`, `test_two_node_consensus_verification.py` | Tie-break outcomes covered; target consensus service. |
| Lifecycle and finality | `submission.py`, `blockchain.py` | `test_submission_statuses.py`, `test_hard_rejection.py`, `test_protocol_v1_lifecycle_finality.py` | Strong state/depth coverage; target submission lifecycle service. |
| Content and Model A integrity | `content.py`, `protocol_v1_genesis.py`, `blockchain.py` | `test_content_object.py`, `test_content_storage.py`, `test_protocol_v1_genesis.py`, `test_protocol_v1_block_format.py` | Strong hashes and immutable media record; target content service/adapter. |
| Submissions | `submission.py`, `blockchain.py`, `api.py` | `test_submission_statuses.py`, `test_approval_logic.py`, `test_submission_lifecycle_api.py` | Strong flow coverage; target submission service/router. |
| Voting and originality | `blockchain.py`, `protocol_v1_originality.py`, `api.py` | `test_community_voting.py`, `test_protocol_v1_originality_votes.py`, `test_peer_vote_sync_api.py` | Strong signed vote and threshold coverage; target originality service/router. |
| Mint queue | `blockchain.py`, `api.py` | `test_mint_queue.py`, `test_hard_rejection.py`, `test_submission_lifecycle_api.py` | Admission/blocking covered; target minting service. |
| Creator and voter rewards | `blockchain.py`, `api.py` | `test_task_10_3_voting_rewards.py`, `test_voter_rewards_api.py` | Settlement/read coverage; target rewards service. |
| Native balances | `blockchain.py`, `native_transfer.py`, `api.py` | `test_native_transfer.py`, `test_native_account_api.py`, `test_native_transfer_api.py` | Strong public balance result coverage; target ledger service/router. |
| Native transaction signing | `native_transfer.py`, `protocol_v1_native_transfer.py` | `test_protocol_v1_native_transfers.py`, `test_native_transfer.py`, `test_native_transfer_api.py` | Strong canonical signed-message coverage; target protocol/domain. |
| Nonces and replay protection | `blockchain.py`, `native_transfer.py` | `test_protocol_v1_native_transfers.py`, `test_native_transfer.py`, `test_native_transaction_block_inclusion_api.py` | Reservation, conflict, settlement replay covered; target ledger service. |
| Mempool admission and selection | `blockchain.py`, `api.py` | `test_native_transfer.py`, `test_native_transaction_block_inclusion_api.py`, `test_peer_transaction_sync_api.py` | Admission/revalidation covered; selection remains limited by current transfer-only-block limitation; target mempool service. |
| Transaction settlement | `blockchain.py` | `test_native_transfer.py`, `test_native_transaction_block_inclusion_api.py`, `test_two_node_native_transfer_verification.py` | Exactly-once outcomes covered; target ledger service. |
| Peer authentication | `protocol_v1_peer_message.py`, `api.py`, `peer_sync.py` | `test_protocol_v1_peer_messages.py`, `test_peer_auth_api.py`, `test_validation_hardening_api.py` | Strong auth/replay coverage; target network adapter. |
| Peer receive/broadcast | `peer_sync.py`, `api.py` | `test_peer_networking_api.py`, `test_peer_block_sync_api.py`, `test_peer_vote_sync_api.py`, `test_peer_transaction_sync_api.py` | Strong validation-before-acceptance coverage; target network adapter. |
| Content synchronization | `peer_sync.py`, `content.py`, `api.py` | `test_peer_content_sync_api.py`, `test_content_storage.py` | Hash/metadata paths covered; target network and content adapters. |
| Chain synchronization | `peer_sync.py`, `blockchain.py`, `api.py` | `test_chain_sync_api.py`, `test_peer_block_sync_api.py`, `test_two_node_consensus_verification.py` | Summary normalization/missing blocks/foreign chain outcomes covered; target sync service. |
| JSON and SQLite storage | `storage.py` | `test_json_storage_backend.py`, `test_sqlite_storage_backend.py`, `test_storage_regression_pass.py`, `test_json_to_sqlite_migration.py` | Backend agreement and migration covered; target storage adapters. |
| Public API | `api.py` | API tests for content, auth, submissions, native accounts/transfers, status, validation, security | Focused contract tests exist; route inventory added in Task 5; target public routers. |
| Admin API | `api.py`, `admin_auth.py` | `test_admin_api.py`, `test_ops_api.py`, `test_access_control_api.py`, `test_security_audit_api.py` | Session/access lifecycle covered; target admin router. |
| Development-only API | `api.py`, `config.py` | `test_validation_hardening_api.py`, `test_security_audit_api.py`, `test_wallet_key_exposure_api.py` | Gate coverage exists; route classification added in Task 5; target development router. |
| Peer API | `api.py`, `peer_sync.py` | `test_peer_auth_api.py`, `test_peer_*_api.py`, `test_chain_sync_api.py` | Receive/sync authentication covered; target peer router. |
| Access control | `access_control.py`, `api.py`, `blockchain.py` | `test_access_control_api.py`, `test_review_policy_api.py` | Invite/binding/restriction coverage; target access service/dependency. |
| Application lifespan/state | `api.py`, `config.py` | `test_fixture_storage_isolation.py`, Task 5 import isolation test | Prior fixture covers constructed state; Task 5 covers subprocess imports; target application assembly. |

The test suite itself is the detailed behavior specification. The new Task 5
tests deliberately add no duplicate endpoint or consensus implementation; they
guard route topology, dependency direction, current cycles, and import side
effects. The known FastAPI/Starlette `TestClient` deprecation warning remains an
existing upstream issue and is not changed here.

## Target Direction For Later Tasks

The target order is: protocol/domain objects and deterministic functions;
domain services; storage/network adapters; API schemas/dependencies/routers;
application assembly. This describes a future extraction direction only.

- Protocol/domain modules must not import FastAPI or API routers.
- Storage must not import API modules.
- Networking must call consensus/domain validation rather than redefine it.
- API routers may depend on services, never the reverse.
- Services must not raise `HTTPException`.
- Import-time application state creation is prohibited.
- Public, admin, peer, and development routes remain separated.
- `Blockchain` may temporarily remain a compatibility facade while services are extracted.

## Enforced Baseline

`tests/test_milestone_2_architecture.py` parses source with Python AST without
importing production modules for graph analysis. It excludes tests, virtual
environments, generated/temp output, and frontend files; tests cannot become
production dependencies. It rejects protocol/domain/storage/peer imports of
`api`, and any FastAPI import from a Protocol v1 module. It also compares all
detected strongly connected components to the narrow baseline fixture.

The exact pre-existing cycles are `content -> submission -> content` and
`native_transfer -> protocol_v1_native_transfer -> native_transfer`. There are
no current forbidden edges or Protocol-v1 FastAPI imports. Any new edge,
changed cycle, or changed forbidden import fails the test.

## Task 6 Access/Admin Service Extraction

Task 6 adds `services.access_admin_service` and `services.feedback_service`.
The former owns plain-record transitions for access requests/accounts/invites,
wallet bindings, allowlist entries, override requests, and audit entries. The
latter owns feedback normalization, lifecycle, filtering, summaries, and admin
notes. Neither service imports `Blockchain`, `api`, or FastAPI.

`Blockchain` remains the compatibility facade and owns the authoritative
in-memory lists plus whole-document persistence. It constructs short-lived
state views containing references to those lists and delegates to the services;
there is no copied service state and no persistence callback. Reload/refresh
continues assigning the same persisted sections to the facade attributes, and
the existing `save_blockchain` lifecycle continues to write the full document.

The dependency direction is `api -> blockchain -> services -> access_control /
wallet_auth`; storage remains independent. Access decision policy stays in
`access_control.py`, and admin session authentication stays in `admin_auth.py`
and `api.py`. `api.py` is intentionally not thin in this task; router extraction
remains a later boundary.

`blockchain.py` changed from 6,425 lines before Task 6 to 5,544 lines after the
extraction. Consensus, ledger, rewards, submissions, originality, networking,
cryptography, and storage behavior remain in their existing owners.

## Task 7 Content, Submission, Originality, and Mint Queue Extraction

Task 7 adds stateless content coordination, submission/originality, and mint
queue services. They receive explicit views over facade-owned persisted lists,
so JSON/SQLite reloads rebind naturally without synchronized duplicate state.
Blockchain remains the public compatibility facade and whole-document
persistence owner. Queue rules moved, while block-mint orchestration stays in
Blockchain because it is coupled to `add_block`, canonical reconciliation, and
existing save timing. Rewards, native ledger behavior, and consensus remain in
Blockchain. Model A immutable block media remains authoritative. `blockchain.py`
is 4,970 lines after Task 7, down from the Task 6 baseline of 5,544 lines.

`tests/fixtures/api_route_contract.json` is generated from an isolated FastAPI
application import and normalized by path, method, and name. It excludes the
FastAPI OpenAPI/documentation routes and automatic `HEAD`/`OPTIONS` behavior.
For every application route it records method, path, handler name, public/admin/
peer/development classification, resolved dependency guards, authentication and
authorization expectations, body/response model names, and a declared status
code where FastAPI supplies one.

## Task 8 Native Ledger, Mempool, And Rewards Extraction

Task 8 adds `NativeLedgerService`, `NativeMempoolService`, and `RewardService`.
Their short-lived views reference facade-owned `chain`, `transfer_intents`, and
`native_transactions` state. Reward records remain canonical-chain-derived.
Blockchain retains whole-document persistence, reload, and accepted-block
orchestration, so each call observes the authoritative collections after JSON or
SQLite reload. Transaction identity verification, transfer records, nonce and
balance calculations, mempool admission/selection, settlement/reconciliation,
reward planning, and reward-pool accounting are service-owned. Candidate block
validation, full block-native validation, block metadata/hash validation,
acceptance, chain validation, fork choice, finality, and replacement remain in
`Blockchain` for Task 9.

## Task 9 Block Production And Consensus Extraction

Task 9 adds four framework-independent consensus services. `BlockProductionService`
owns deterministic candidate assembly, including complete Model A media embedding,
native-transaction selection metadata, reward transaction ordering, and the existing
timestamp boundary. `BlockValidationService` owns candidate, block, certificate,
reward, native-transaction, content-integrity, hash-link, genesis, and whole-chain
validation. `ForkChoiceService` owns cumulative-originality scoring and the frozen
score/height/lower-tip-hash tie-break order. `FinalityService` owns canonical depth
views and the frozen confirmation/finality policy.

`Blockchain` remains the compatibility facade and authoritative state owner. It
constructs fresh immutable state/collaborator views for each production or validation
call and retains accepted-candidate mutation, miner wallet bookkeeping, mempool
settlement/rejection, cache mutation, chain replacement, canonical submission
reconciliation, persistence, and logging. The services never import `Blockchain`,
`api`, FastAPI, peer transport, or storage adapters, and never save independently.
The dependency direction is `api/peer_sync -> Blockchain -> consensus services ->
protocol objects and extracted ledger/mempool/reward services`.

## Task 10 Peer Networking And Synchronization Extraction

Task 10 keeps `peer_sync.py` as the API-compatible facade while adding focused,
framework-independent peer services. `PeerAuthenticationService` owns legacy and
Protocol v1 signing bytes, signed-header construction, inbound signature error
normalization, timestamps, and nonce-cache operations. `PeerHttpTransport` is the
raw client-library boundary, while `PeerBroadcastService` owns peer ordering,
timeouts, per-peer results, logging, and broadcast aggregation. The content sync
service owns metadata/download verification and exact Model A byte storage. The
chain sync service owns summary/block retrieval, summary normalization, failure
aggregation, and synchronization coordination.

Networking no longer implements score/height/tip-hash comparisons. Preliminary
summary ranking and full candidate fork choice both delegate through the
`Blockchain` compatibility facade to `ForkChoiceService`; block and chain
validation continue through the Task 9 validation facade methods. Actual chain
replacement, canonical reconciliation, native-transaction reconciliation, and
persistence remain in `peer_sync.py` so the service does not acquire authoritative
chain state or an alternative adoption path.

The dependency direction is `api -> peer_sync facade -> peer services -> protocol /
content helpers`, with injected calls back through `Blockchain -> Task 9 consensus
services` for ranking and validation. Peer services import neither `Blockchain`,
`api`, nor FastAPI, cache no chain collections, and persist no blockchain state
independently. The two characterized legacy cycles remain unchanged.

## Task 11 FastAPI Router And Thin-Adapter Extraction

Task 11 reduces `api.py` to the stable `api:app` compatibility entry point.
Task 11A makes the public-chain (5), access/authentication (16), and admin (29)
`APIRouter` modules real HTTP adapters. Task 11B adds explicit content (20) and
native (23) HTTP adapters; Task 11C completes peer (20) and operations (16).

The five extracted routers own explicit endpoint signatures, FastAPI parsing,
dependencies, HTTP error/status mapping, and response serialization. They call
the `Blockchain` facade for domain transitions. Task 11A-2 places access/admin
transition, audit, and persistence coordination in Task 6-backed facade
operations. Task 11B similarly places content/submission/originality/mint and
native ledger/mempool transition coordination in Task 7/8/9-backed facade
operations. Task 11C routes peer receipt/sync/broadcast work through Task 10
services and moves guarded development transitions into narrow `Blockchain`
operations. No router uses the runtime compatibility builder.

The application assembler merges the domain-owned `APIRoute` objects by their
captured pre-refactor order. This preserves route shadowing and matching behavior
as well as path, method, trailing-slash, dependency, model, status, and OpenAPI
contracts. Direct `api_runtime` imports and `importlib.reload(api)` also install
the same routers, preserving the existing test and deployment lifecycle.

The dependency direction is now `api -> api_runtime + api_routers`,
`api_routers -> api_runtime`, and `api_runtime -> Blockchain/peer_sync ->
services`. Services do not import `api`, `api_runtime`, routers, FastAPI, or HTTP
response classes. No architecture-baseline exception or new import cycle was
added.

## Task 12 Final Cleanup And Release Baseline

The 129 frozen application routes are owned by explicit router modules in this
exact classification: public-chain 5, access/authentication 16, admin 29,
content 20, native 23, peer 20, and operations/development 16. Their captured
global order remains `0..128`; the route-contract fixture continues to classify
each route as public, admin, peer, or development and records its dependency,
model, and declared-status metadata.

Task 12 removed the unused `api_routers._routing` generic forwarding builder
and the seven duplicate `ROUTES` manifests that served only its unreachable
fallback. Router assembly now rejects a non-explicit router module rather than
silently generating wrappers. The route-order maps remain because they are the
live binding from each concrete endpoint to the frozen global order.

The AST import baseline remains two cycles only: `content -> submission ->
content` and `native_transfer -> protocol_v1_native_transfer ->
native_transfer`. No forbidden API-domain edge, Protocol v1 FastAPI import, or
additional architecture exception is permitted. `api_runtime.py` re-exports
some helpers and configuration names intentionally: router modules and existing
`api` compatibility monkeypatches consume them dynamically, so static
single-module unused-import reports are not sufficient removal evidence.
