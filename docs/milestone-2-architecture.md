# Milestone 2 Task 5: Architecture Characterization

Date: 2026-09-02. This is a characterization baseline, not a refactor plan or
claim that the target structure already exists. Protocol v1 behavior, canonical
serialization, genesis, signatures, consensus, and media integrity are frozen.

## Current Architecture

The application is currently a flat Python module set. `api.py` owns FastAPI
assembly, route handlers, schemas, access dependencies, and substantial
orchestration. `blockchain.py` is the compatibility facade for chain state,
consensus-facing validation, submission lifecycle, rewards, native ledger,
mempool, and persistence coordination. `peer_sync.py` owns signed transport and
cross-node exchange. `storage.py` implements JSON and SQLite backends. Protocol
v1 modules provide deterministic protocol objects and validation helpers.

`api.py`, `blockchain.py`, and `peer_sync.py` are intentionally still oversized.
`api.py` creates the FastAPI application at import time but creates the
`Blockchain` instance in the application lifespan. Top-level logging and
lightweight session/store objects remain current behavior and are not moved by
this task.

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

`tests/fixtures/api_route_contract.json` is generated from an isolated FastAPI
application import and normalized by path, method, and name. It excludes the
FastAPI OpenAPI/documentation routes and automatic `HEAD`/`OPTIONS` behavior.
For every application route it records method, path, handler name, public/admin/
peer/development classification, resolved dependency guards, authentication and
authorization expectations, body/response model names, and a declared status
code where FastAPI supplies one.
