# Protocol v1 Audit

## 1. Repository baseline

- Audited branch: `Freeze-ZoidbergChain-Public-Testnet-v1-Protocol`
- Audited commit: `d965aa3362124b40c97c676a7503c03007877707`
- Working tree at start: not clean
- Pre-existing untracked files:
  - `rollback-prep-working-tree.patch`
  - `zoidbergcoin-ui/zoidbergchain-dist.zip`
- Python/runtime used for the passing test run: `Python 3.13.5`
- Storage backends discovered: JSON and SQLite
- Test commands run:
  - `python -m pytest -q` -> failed because `pytest` was not installed in the system Python
  - `.\.venv\Scripts\python.exe -m pytest -q` -> `738 passed in 77.25s`
- Post-change verification commands run on Friday, August 28, 2026:
  - `.\.venv\Scripts\python.exe -m pytest -q tests/api/test_peer_auth_api.py tests/api/test_peer_block_sync_api.py tests/api/test_peer_vote_sync_api.py tests/api/test_peer_certificate_sync_api.py tests/api/test_peer_transaction_sync_api.py tests/api/test_peer_content_sync_api.py tests/api/test_chain_sync_api.py tests/test_protocol_v1_peer_messages.py` -> `134 passed in 12.96s`
  - `.\.venv\Scripts\python.exe -m pytest -q tests/api/test_peer_submission_sync_api.py tests/api/test_peer_auth_api.py tests/api/test_peer_block_sync_api.py tests/api/test_peer_content_sync_api.py tests/api/test_peer_vote_sync_api.py tests/api/test_peer_certificate_sync_api.py tests/api/test_peer_transaction_sync_api.py tests/api/test_chain_sync_api.py tests/api/test_wallet_auth_api.py tests/api/test_native_transfer_api.py tests/api/test_native_transaction_block_inclusion_api.py tests/blockchain/test_protocol_v1_block_format.py tests/blockchain/test_certificate_block_validation.py tests/test_protocol_v1.py tests/test_protocol_v1_originality_votes.py tests/test_protocol_v1_native_transfers.py tests/test_protocol_v1_peer_messages.py tests/storage/test_storage_tools.py tests/storage/test_json_to_sqlite_migration.py tests/config/test_security_modes.py` -> `363 passed in 34.75s`
  - `.\.venv\Scripts\python.exe -m pytest -q tests/integration/test_two_node_native_transfer_verification.py tests/integration/test_two_node_consensus_verification.py tests/integration/test_two_node_storage_backends.py` -> `17 passed in 5.57s`
  - `.\.venv\Scripts\python.exe -m pytest -q` -> `843 passed in 240.42s (0:04:00)`

## 2. Current protocol overview

The current implementation is a hybrid of older legacy block-mining code and newer signed content/native-transfer flows.

1. A user creates a submission through the API in `api.py` (`submit_content`) or via `Blockchain.submit_existing_content` / `Blockchain.submit_content` in `blockchain.py`.
2. Content is stored in `content.py` using a content hash and local filesystem persistence under the configured content directory. For remote peers, the bytes can be fetched and re-stored locally.
3. Votes are created through wallet-authenticated signing messages in `wallet_auth.py`, verified with recovered wallet addresses, then recorded on-chain in `Blockchain.cast_submission_vote`.
4. Originality is evaluated in `Blockchain.evaluate_submission`, which considers vote totals, approval percentage, and whether the submission is eligible for certification.
5. An originality certificate is created by `OriginalityCertificate.from_approved_submission` and persisted through `Blockchain.create_originality_certificate`.
6. A submission becomes eligible for block creation when it is approved and placed in the mint queue. The mint queue is checked in `Blockchain.add_to_mint_queue`, `mint_next_queued_submission`, and related helpers.
7. The block is created in `Blockchain.mint_submission` / `Blockchain.add_block`. Modern minted blocks include certificate metadata, reward metadata, and native transaction metadata; the legacy `add_block` path still exists for direct image/text mining.
8. Rewards are assigned through `Blockchain.build_meme_reward_metadata`, creator reward logic, and optional voter-reward planning.
9. Native transactions are built, signed, and validated in `native_transfer.py` and `Blockchain.create_signed_transfer_intent` / `validate_signed_native_transaction`.
10. The new block is accepted locally when `Blockchain.add_block` or `Blockchain.mint_submission` appends it and persists the chain. `peer_sync.receive_peer_block` can also append valid peer blocks.
11. Peers learn about submissions, votes, certificates, blocks, and native transactions through the broadcast and receive paths in `api.py` and `peer_sync.py`.
12. Forks are resolved by `Blockchain.compare_chains_by_originality`, which prefers higher originality score first, then higher height, then lower latest block hash. Genesis mismatch is an invalid candidate.

Where the README-like story diverges from the code: the code still contains legacy direct-upload block creation and runtime-generated genesis, but Protocol v1 accepted-media blocks now embed full media bytes while legacy blocks still depend on auxiliary content storage.

## 3. Consensus-critical file and function inventory

| Area | File | Class / Function | Current behavior | Consensus critical? | Needs Protocol v1 change? |
|---|---|---|---|---|---|
| Block construction | `blockchain.py` | `Blockchain.add_block`, `Blockchain.mint_submission` | Builds block objects from transactions, certificate metadata, reward metadata, and native tx metadata | Yes | Yes |
| Block hashing | `block.py` | `Block.calculate_hash` | Hashes index, previous hash, timestamp, transaction fields, meme value, miner, certificate metadata | Yes | Yes |
| Block serialization | `block.py` | `Block.to_dict` | Serializes transactions and block metadata to a Python dict | Yes | Yes |
| Block validation | `blockchain.py` | `Blockchain.validate_block_with_native_transactions`, `Blockchain.validate_block_certificate_metadata`, `Blockchain.is_chain_valid` | Validates hash, links, certificate metadata, transaction rules, and chain rules | Yes | Yes |
| Chain validation | `blockchain.py` | `Blockchain.is_chain_valid`, `Blockchain.compare_chains_by_originality` | Validates chain linkage and chooses the better fork | Yes | Yes |
| Fork choice | `blockchain.py` | `Blockchain.compare_chains_by_originality` | Originality score, then height, then latest hash | Yes | Yes |
| Genesis | `blockchain.py` | `Blockchain.create_genesis_block` | Runtime-generated genesis using current time and `./zoidberg.jpg` | Yes | Yes |
| Certificate creation | `originality_certificate.py`, `blockchain.py` | `OriginalityCertificate.from_approved_submission`, `Blockchain.create_originality_certificate` | Builds certificate from votes and approved submission | Yes | Yes |
| Certificate ID generation | `originality_certificate.py` | `calculate_certificate_id` | Canonical JSON hash of core certificate fields | Yes | Yes |
| Certificate validation | `originality_certificate.py` | `validate_certificate_for_submission` | Checks IDs, hashes, vote counts, thresholds, and score formula | Yes | Yes |
| Submission ID creation | `submission.py` | `Submission.__post_init__` | Random UUID hex submission_id | Yes | Yes |
| Content/media hash calculation | `content.py`, `submission.py` | `calculate_content_hash`, `compute_text_content_hash`, `calculate_submission_content_hash` | Canonical hash for content object; submission hash includes submitter and possibly file bytes | Yes | Yes |
| Vote signing payload creation | `wallet_auth.py` | `build_wallet_vote_message` | Human-readable wallet vote authorization message | Yes | Yes |
| Vote signature verification | `wallet_auth.py`, `peer_sync.py` | `WalletAuthManager.verify_vote_signature`, `recover_signed_wallet_address` | Recovers signer and checks exact message match | Yes | Yes |
| Wallet recovery | `wallet_auth.py`, `native_transfer.py`, `peer_sync.py` | `recover_signed_wallet_address`, `normalize_wallet_address` | Recovers Ethereum address from personal_sign-style messages | Yes | Yes |
| Native transfer signing payload | `native_transfer.py` | `build_transfer_signing_message`, `canonicalize_transaction_payload` | Human-readable signing message and canonical tx payload | Yes | Yes |
| Native transfer signature verification | `native_transfer.py`, `blockchain.py` | `verify_transfer_signature`, `Blockchain.validate_signed_native_transaction` | Reconstructs message, recovers signer, matches tx fields | Yes | Yes |
| Transaction ID calculation | `native_transfer.py` | `compute_transaction_id` | sha256 of canonical JSON payload | Yes | Yes |
| Nonce validation | `native_transfer.py`, `blockchain.py` | `parse_transfer_nonce`, `Blockchain.validate_transaction_nonce`, `Blockchain.reserve_transaction_nonce` | Enforces positive sequential nonces | Yes | Yes |
| Replay protection | `wallet_auth.py`, `native_transfer.py`, `protocol_v1_peer_message.py` | `WalletAuthManager.verify_*`, `Blockchain.validate_transaction_nonce`, `ProtocolV1PeerReplayStore` | Challenge reuse prevention, nonce sequence, durable peer replay-state rejection | Yes | Yes |
| Peer message signing | `protocol_v1_peer_message.py`, `peer_sync.py` | `build_protocol_v1_peer_envelope`, `calculate_protocol_v1_peer_message_id`, `sign_protocol_v1_peer_message`, `build_protocol_v1_peer_request_headers` | HMAC over canonical Protocol v1 peer envelope bytes | Yes | Yes |
| Peer authentication | `api.py`, `peer_sync.py`, `protocol_v1_peer_message.py` | `require_peer_secret`, `verify_protocol_v1_peer_request`, `_require_protocol_v1_peer_claims_match_auth`, `_require_protocol_v1_active_peer` | Explicit Protocol v1 peer headers or explicit legacy shared-secret validation depending on configuration | Yes | Yes |
| Peer replay protection | `protocol_v1_peer_message.py`, `api.py` | `ProtocolV1PeerReplayStore`, `get_protocol_v1_peer_replay_store`, `require_peer_secret` | Rejects duplicate message IDs and sender-scoped nonces within the configured window and persists them across restart | Yes | Yes |
| Network identification | `config.py` | `NETWORK_NAME`, `ENVIRONMENT` | Configurable network name and environment | Yes | Yes |
| Lifecycle transitions | `submission.py`, `blockchain.py` | `Submission.transition_to`, `evaluate_submission`, `mint_submission` | Enforces submission state progression | Yes | Yes |
| Consensus-object persistence | `storage.py`, `storage_tools.py` | `save_blockchain_document`, `load_blockchain_state`, `build_export_snapshot` | JSON/SQLite persistence plus export snapshots | Yes | Yes |
| Media persistence and sync | `content.py`, `peer_sync.py` | `store_content_bytes`, `content_object_from_submission_data`, `fetch_content_from_peer` | Local filesystem media storage plus peer fetch/store | Yes | Yes |

## 4. Current serialization and hashing behavior

### Block

- Source: `block.py`
- Functions: `Block.calculate_hash`, `Block.calculate_hash_legacy`, `Block.calculate_hash_v1`, `Block.consensus_payload_v1`, `Block.consensus_payload_v1_bytes`
- Legacy block hashing: manual string concatenation plus `json.dumps(..., sort_keys=True, separators=(",", ":"))` for certificate metadata only
- Protocol v1 hashing: `sha256(protocol_v1.canonical_domain_bytes(..., object_type="block", network_id=...))`
- Protocol v1 included fields: explicit payload fields for block version, index, previous hash, timestamp, ordered transactions, miner, submission/certificate/content metadata, embedded `media_bytes`, reward metadata, ordered native transactions, ordered voter rewards, and `meme_text` when present
- Encoding: UTF-8 canonical JSON bytes for Protocol v1; UTF-8 legacy string assembly for legacy blocks
- Normalization: Protocol v1 converts consensus-critical numeric scalars to normalized decimal strings and rejects raw floats in canonical serialization
- Classification: dual-mode. Legacy block hashing remains non-canonical for backward compatibility; Protocol v1 block hashing is explicit, canonical, domain-separated, and deterministic

### Originality certificate

- Source: `originality_certificate.py`
- Functions: `calculate_vote_hash`, `calculate_certificate_id`, `validate_certificate_for_submission`
- Included fields for Protocol v1 vote hash: `vote_set_version`, `submission_id`, `content_hash`, and the sorted final vote set of `{voter, vote_type}` entries; legacy vote hashes remain on the older `created_at` / `submission_id` / `vote_type` / `voter` payload
- Included fields for Protocol v1 certificate ID: `certificate_version`, `submission_id`, `content_hash`, `creator_wallet`, `vote_hash`, `vote_total`, `decisive_vote_total`, `original_votes`, `not_original_votes`, `unsure_votes`, `minimum_votes_required`, `approval_threshold`, `approval_percentage`, and `originality_score`; the envelope binds `network_id`, `object_type`, and `protocol_version`
- Serialization method: Task 2 canonical serialization with explicit legacy/v1 dispatch
- Encoding: UTF-8
- Hash algorithm: SHA-256
- Classification: explicit dual-mode behavior. Legacy certificate IDs remain unchanged; new Protocol v1 certificates are deterministic, domain-separated, and exclude non-deterministic issuance metadata from the ID.

### Submission

- Source: `submission.py`
- Functions: `calculate_submission_content_hash`, `Submission.__post_init__`, `Submission.to_dict`, `Submission.from_dict`
- Submission ID: random UUID hex
- Content hash: hashes raw file bytes when the file exists; otherwise hashes the image path string, then NUL-separated text content and submitter
- Serialization method: Python dataclass dict with direct field values
- Classification: submission_id is non-deterministic; content hash is deterministic only when the same bytes/path/text/submitter inputs are provided

### Content object

- Source: `content.py`
- Functions: `calculate_content_hash`, `compute_text_content_hash`, `resolve_payload_hash`, `store_content_bytes`, `ContentObject.__post_init__`, `content_object_from_submission_data`
- Included fields for content hash: content type, MIME type, normalized text, caption, file name, file size, metadata
- Serialization method: canonical JSON for object metadata; raw bytes for binary payload hashing; normalized text bytes for text hashing
- Classification: mostly deterministic and explicit, with MIME sniffing and filesystem presence as external inputs

### Vote

- Source: `wallet_auth.py` and `peer_sync.py`
- Functions: `build_protocol_v1_vote_message`, `WalletAuthManager.verify_vote_signature`, `peer_sync._normalize_vote_payload`
- Signed payload: canonical Task 2 vote envelope binding domain, protocol version, canonical network ID, submission ID, content hash, voter wallet, vote choice, nonce, and challenge timestamps
- Persisted state: Protocol v1 vote records store `vote_version`, `protocol_version`, `network_id`, `vote_message`, `vote_signature`, `signed_message_hash`, `vote_nonce`, `vote_issued_at`, `vote_expires_at`, and existing vote metadata; legacy signed votes remain versionless
- Classification: explicit dual-mode behavior. New votes use a canonical domain-separated schema; legacy human-readable vote messages remain available only through explicit legacy dispatch.

### Native ZOID transfer

- Source: `native_transfer.py`, `protocol_v1_native_transfer.py`, `wallet_auth.py`, `blockchain.py`, and `peer_sync.py`
- Functions: `build_protocol_v1_native_transfer_payload`, `build_protocol_v1_native_transfer_message`, `build_transfer_signing_message`, `canonicalize_transaction_payload`, `compute_transaction_id`, `WalletAuthManager.issue_transfer_challenge`, `Blockchain.validate_signed_native_transaction`
- Signed payload: Protocol v1 canonical transfer envelope binding domain, protocol version, canonical network ID, sender wallet, recipient wallet, amount, fee, nonce, timestamp, and memo; legacy human-readable transfer messages remain explicit legacy-only payloads
- Transaction ID: Protocol v1 uses SHA-256 of the canonical domain-separated transfer identity payload; the signature is excluded from the v1 tx ID, while legacy tx IDs remain on the legacy payload branch
- Replay/nonce checks: strict sequential nonces, per-wallet reservation and settlement checks, duplicate tx detection, and peer revalidation against the same nonce ledger rules
- Classification: explicit dual-mode behavior. New Protocol v1 transfers use a canonical domain-separated schema; legacy versionless records remain readable but are not admitted into the live Protocol v1 mempool or new Protocol v1 blocks

### Peer message

- Source: `peer_sync.py`
- Functions: `build_peer_signature_payload`, `sign_peer_request`, `verify_peer_signature`
- Auth envelope fields: method, path, timestamp, nonce, body hash, node ID, signature
- Replay protection: nonce cache keyed by node ID
- Classification: deterministic and explicit for HMAC-authenticated peer requests

### Genesis

- Source: `blockchain.py`
- Function: `Blockchain.create_genesis_block`
- Included fields: runtime timestamp, GENESIS sender transactions, `./zoidberg.jpg` base64 payload, and fixed genesis text
- Classification: potentially non-deterministic because it depends on the local clock, filesystem availability, and supplied wallets

## 5. Consensus-critical objects

### Block

Current block behavior is split explicitly by version:

- legacy blocks: hash-affecting fields remain block index, previous hash, timestamp, legacy transactions, meme payload, miner, and certificate metadata
- Protocol v1 blocks: the hash-affecting payload is explicit and includes block version, network binding, previous hash, timestamps, ordered transactions, ordered native transactions, ordered voter rewards, submission/certificate linkage, deterministic reward metadata, declared content metadata, and embedded `media_bytes`

Persisted-but-not-hashed Protocol v1 compatibility fields are limited to the stored `hash` and `meme.encoded_image`.

### Originality certificate

The logical certificate schema is now split explicitly:

- Protocol v1 identity: certificate version, canonical network binding, submission/content identity, creator wallet, deterministic vote-set hash, vote totals, threshold, approval percentage, and originality score
- persisted metadata outside the Protocol v1 ID: approved timestamp, content ID, display network name, and issuing node ID
- legacy certificates: explicit versionless records that keep their legacy ID payload

### Submission

Submission identity is a random UUID hex. Submission content identity is derived from content hash / content ID, and the content hash itself includes submitter plus normalized content inputs.

### Vote

Votes are still stored as submission ID, voter, vote type, and timestamp, but Protocol v1 signed votes now also persist the exact canonical message and version tuple needed for later revalidation. Legacy signed votes remain explicit legacy records.

### Native ZOID transfer

Native transfers are now split explicitly:

- Protocol v1 identity: `transaction_version`, canonical network binding, sender wallet, recipient wallet, amount, fee, nonce, timestamp, and memo, all wrapped by the Task 2 domain envelope
- persisted metadata outside the Protocol v1 tx ID: display `network`, signature bytes, signature scheme, signed message text/hash, and local lifecycle metadata
- legacy transfers: explicit versionless records that keep the legacy human-readable signing message and legacy tx ID payload

### Peer message

Peer auth now uses an explicit Protocol v1 peer-message envelope binding domain, protocol version, canonical network ID, message type, sender node ID, timestamp, nonce, and canonical payload. `message_id` is the SHA-256 hash of the canonical envelope without the signature, and HMAC uses the canonical envelope bytes.

### Genesis

Genesis is runtime-generated, not hard-coded. The current clock time and local `./zoidberg.jpg` file content influence the resulting object and hash.

## 6. Current signature domains

| Object | Signing function | Network bound? | Protocol version bound? | Object/domain bound? | Replay fields | Address verification | Cross-network replay risk | Cross-object replay risk |
|---|---|---:|---:|---:|---|---|---|---|
| Vote | `build_protocol_v1_vote_message` / `WalletAuthManager.verify_vote_signature` / `peer_sync._normalize_vote_payload` | Yes | Yes | Yes, by canonical domain envelope and submission/content binding | Nonce, issued/expires, duplicate-vote rules | Yes | Low for Protocol v1; explicit legacy path remains transitional | Low for Protocol v1; explicit legacy path remains transitional |
| Submission auth | `build_wallet_submission_message` / `verify_submission_signature` | Yes | No | Yes, by message text and included content fields | Nonce, issued/expires | Yes | Reduced by network name | Moderate if message text is reused elsewhere |
| Native transfer | `build_protocol_v1_native_transfer_message` / `WalletAuthManager.verify_transfer_signature` / `Blockchain.validate_signed_native_transaction` | Yes | Yes | Yes, by canonical domain envelope and sender/recipient/amount/fee/nonce/timestamp/memo binding | Nonce, tx ID, per-wallet reservation, and settlement rules | Yes | Low for Protocol v1; explicit legacy path remains transitional | Low for Protocol v1; explicit legacy path remains transitional |
| Wallet login | `build_wallet_login_message` / `verify_signature` | Yes | No | Yes, by challenge message | Challenge nonce, expiry, one-time use | Yes | Reduced by network name | Lower, but still message-text based |
| Peer message | `calculate_protocol_v1_peer_message_id` / `sign_protocol_v1_peer_message` / `verify_protocol_v1_peer_request` | Yes | Yes | Yes, by the explicit `zoidbergchain/peer-message/v1` envelope | Timestamp, nonce, message ID, durable replay state | Sender node ID plus registered active-peer checks | Low; canonical network ID is authenticated | Low; explicit message type is authenticated and route-checked |

Replay protection is in-memory for wallet challenges, durable and bounded for Protocol v1 peer messages, and ledger-backed for native-transfer settlement nonces.

## 7. Network, protocol, chain and object versioning

- Network name: `config.NETWORK_NAME` in `config.py`
- Protocol v1 network ID: `zoidberg-public-testnet-v1`, resolved through `protocol_v1.resolve_network_id(...)`
- Environment: `config.ENVIRONMENT`
- Chain ID: not currently defined
- Protocol version: `protocol_v1.PROTOCOL_VERSION = 1` for canonical object domains introduced in Task 2/Task 3
- API version: not currently defined
- Schema version: export snapshots use `storage_tools.EXPORT_VERSION = 1`
- Block version: `block_version = 1` for Protocol v1 blocks; absent for legacy blocks
- Certificate version: `certificate_version = 1` for Protocol v1 certificates; absent for legacy certificates
- Transaction version: `transaction_version = 1` for Protocol v1 native transfers; absent for legacy transfers
- Vote version: `vote_version = 1` for Protocol v1 signed votes; absent for legacy signed votes
- Peer message version: `peer_message_version = 1` for Protocol v1 peer transport
- Peer protocol version: explicit `protocol_version = 1` for Protocol v1 peer transport
- Storage version: export snapshots have a version, but the live blockchain document does not

Tasks 3, 4, 5, and 6 close the versioning gap for blocks, originality certificates, signed votes, signed native transfers, and peer transport. Genesis and lifecycle/finality semantics still need later freezing work.

## 8. Genesis behavior

- Source file: `blockchain.py`
- Function: `Blockchain.create_genesis_block`
- Height: `0`
- Previous hash: `"0"`
- Timestamp: `time.time()`
- Transactions: GENESIS funding transactions for the supplied wallets, if any
- State/allocation: initial supply is split among the provided wallets
- Miner/creator: `"GENESIS"`
- Certificate-related fields: none
- Content/media fields: block `meme` contains a base64-encoded copy of `./zoidberg.jpg` plus fixed text
- Network information: not directly committed into the genesis block itself
- Validator information: none
- Environment dependencies: filesystem path and current time; wallet objects supplied by caller
- Resulting hash: derived from the legacy block hash function

Two clean nodes with the same source code are **not** guaranteed to create the same genesis object and hash.

Answer:

- `NO`

Why:

- the timestamp is generated at runtime
- the genesis image is loaded from a local file path
- the provided wallets can differ

## 9. Submission and block lifecycle

Current meanings:

- submitted: submission object exists
- pending: submission is waiting for votes or evaluation
- voting: not a distinct persisted state; this is an operational phase
- approved: submission passed evaluation and can be certified
- accepted: not currently defined as a distinct protocol state
- rejected: submission failed evaluation
- certified: certificate exists for the submission
- mint-queued: submission is queued for block creation
- block-created: block object has been minted or appended
- block-accepted: block has been appended to the local chain
- confirmed: not currently defined as a distinct protocol state
- finalized: not currently defined as a distinct protocol state

Real transitions:

- `api.py` / `submit_content`: public or authenticated submission creation
- `blockchain.py` / `evaluate_submission`: pending -> approved or rejected
- `blockchain.py` / `create_originality_certificate`: approved -> certified
- `blockchain.py` / `add_to_mint_queue`: certified/approved -> mint-queued
- `blockchain.py` / `mint_submission` or `api.py` / `mint_queued_submission`: mint-queued -> block-created / block-accepted
- `peer_sync.py` / `receive_peer_block`: peer block acceptance path

Duplicate prevention:

- certificate issuance: yes, by existing certificate lookup
- mint queue insertion: yes, by queue membership checks
- block creation: partially, through submission status and queue flow, but legacy direct block creation remains
- submitter reward: mostly yes through reward metadata and block append rules
- voter reward: yes, reward IDs are deterministic and deduped
- block broadcasting: no strong global dedupe beyond block hash/state checks
- chain acceptance: yes, via chain validation and fork-choice comparison

Current implementation does enforce the practical rule that one accepted content submission in the modern flow maps to one minted block, but the presence of the legacy direct block path makes this weaker than a hard protocol invariant.

## 10. Block acceptance, confirmation and finality

The code distinguishes:

- block creation: yes
- local block validation: yes
- local chain acceptance: yes
- peer acceptance: yes
- confirmation: not formally defined
- finality: not formally defined

Implicit assumptions:

- a block in the accepted local chain is treated as usable immediately
- the best chain chosen by fork choice is the working chain
- persisted state is treated as authoritative until replaced by a better chain

These semantics should be formalized later so "accepted", "confirmed", and "finalized" do not drift apart.

## 11. MODEL A compatibility

MODEL A is fixed:

> The full accepted media file must be part of the immutable blockchain record.

### Current media storage

- Uploaded bytes are stored in `content.py` under the local content directory
- Filenames and paths are derived from content hash and MIME type
- Hashes are calculated from content bytes for binary data and canonicalized text for text payloads
- Duplicate content can reuse the same storage location when the hash matches
- For Protocol v1 blocks, the same accepted bytes are also embedded directly in the persisted block record
- Peer sync can validate and re-store the bytes locally from the block payload alone

### Current block representation

- Legacy blocks still store content-related metadata without embedded media bytes
- Protocol v1 blocks add explicit `block_version`, `network_id`, `media_hash`, and `media_bytes`
- Protocol v1 block hashes commit directly to the embedded `media_bytes`
- A fresh node can reconstruct Protocol v1 accepted media from the block record itself, then optionally repopulate the auxiliary content cache

### Failure/removal analysis

If the auxiliary content directory/database were deleted while blockchain block records remained, would the immutable blockchain record still contain the original media file?

Answer:

- Protocol v1 block: `YES`
- Legacy pre-v1 block: `NO`

### Compliance rating

- Protocol v1 blocks: `PASS`
- Legacy pre-v1 blocks: `FAIL`

Why:

- Protocol v1 accepted-media blocks now embed the immutable bytes and validate them against declared hashes
- Legacy blocks still store only metadata plus auxiliary content references

## 12. Persistent consensus data

- Blocks and chain: persisted through `storage.py` JSON and SQLite backends
- Submissions: persisted in the same blockchain state document
- Votes: persisted in the same blockchain state document
- Certificates: persisted in the same blockchain state document
- Native transfers: persisted in the same blockchain state document
- Nonces: derived from transaction state and persisted through native transaction records
- Replay state: wallet challenges remain in memory; Protocol v1 peer replay state is persisted as bounded non-consensus security state in `peer_message_replay_state.json`
- Peer state: persisted in `peers.json` or the SQLite-backed equivalent state
- Rewards: persisted as part of block and account/reward records
- Media: Protocol v1 block records persist embedded accepted-media bytes inside the chain document; the content directory remains a cache/index/serving layer
- Genesis/network metadata: stored implicitly in chain state and config, not as a dedicated versioned consensus schema

Migration risk note: changing canonical representation in Milestone 1 would invalidate existing persisted block and signature data unless a reset/migration plan is defined.

## 13. Compatibility and migration risks

| Current representation / behavior | Likely Protocol v1 change | Existing data affected | Risk | Suggested migration/reset strategy |
|---|---|---|---|---|
| Blocks now run in dual legacy/v1 hash modes | Mixed legacy and Protocol v1 validation | Stored chains, peer payloads, dev fixtures | Critical consensus split risk if nodes disagree on version branch | Keep explicit `block_version` branching and prefer a clean Public Testnet v1 reset |
| Protocol v1 block serialization now embeds full media bytes | Larger chain exports and peer payloads | All v1 accepted-media blocks | High operational size risk | Keep summary APIs lean and reserve full bytes for detail/sync paths |
| Certificate ID/hash inputs are fixed core fields | Add version/domain separation | Existing certificates | High signature/validation risk | Reissue or accept old certs under legacy rules |
| Vote signing payload is human-readable text | Canonical vote envelope | Existing signed votes | High | Keep legacy verifier for old votes during transition |
| Submission IDs are random UUIDs | Deterministic or namespaced IDs | Existing submissions | Medium | Preserve old IDs; add new namespace if needed |
| Native transfer signing payload and tx ID are currently coupled to message text and canonical JSON | Add protocol version and explicit domain separation | Pending and historical transfers | High | Snapshot nonce state; maintain legacy verification path |
| Peer-message signing/envelope is now explicit Protocol v1 HMAC over a canonical envelope | Roll out strict v1 peer transport on Public Testnet v1 | Peer API clients, peer registrations, and rollout sequencing | Medium | Keep signed peer messages enabled on Public Testnet and coordinate secret rollout |
| Network ID is explicit for Protocol v1 blocks but not yet frozen across all object domains | Extend chain/protocol identifiers beyond blocks | All nodes and peers | High | Freeze the launch network identity and migrate other domains later |
| Genesis is runtime-generated | Hard-code or version genesis | Every node bootstrapping from scratch | Critical | Publish a new genesis and treat old chain as legacy |
| Existing stored blocks/certificates/votes | Mixed legacy and Protocol v1 validation | Entire existing dataset | Critical | Full reset likely safer than in-place rewrite |
| Pending native transfers and nonce state | Recompute under new rules | Mempool and account state | High | Drain/clear mempool before upgrade |
| Peer replay state | Durable replay window | Peer sessions | Medium | Reset on deployment or persist with versioning |
| Submissions created before Task 3 may still carry legacy content-hash semantics until recertified | Canonical accepted-media hash for new certifications | Approved/queued legacy submissions and certificates | High | Re-evaluate or reissue affected certificates before public v1 launch if needed |
| Submissions and rewards | Harden one-to-one lifecycle | Submission and reward records | Medium | Duplicate-mint guard now exists for certified v1 minting; review remaining legacy bypasses later |
| MODEL A media inclusion | Implemented for Protocol v1 blocks only | Legacy accepted submissions | Medium | Treat legacy accepted-media history as legacy data and reset or migrate deliberately |

Severity summary:

### Critical

- genesis
- existing stored chain data
- mixed legacy/v1 block validation during any transition window

### High

- certificate/content-hash upgrade path for pre-Task-3 approved submissions
- certificate IDs and hashes
- vote payloads
- pending legacy native-transaction reset / drain policy
- network/protocol identifiers outside the block domain
- embedded-media payload size for peer sync and exports

### Medium

- submission IDs
- replay state
- shared peer-secret rollout/rotation
- reward lifecycle
- storage/export volume and duplicate canonical content storage during transition

### Low

- cosmetic metadata and non-consensus summaries

## 14. Current security invariants that must be preserved

- MetaMask/0x wallet recovery: `wallet_auth.py`, `native_transfer.py`, `peer_sync.py`
- Expected signer matching: `WalletAuthManager.verify_*` and `verify_transfer_signature`
- Signature validation: all wallet-auth and native-transfer verification helpers
- Nonce ordering: `Blockchain.validate_transaction_nonce`, `reserve_transaction_nonce`
- Transaction replay prevention: strict sequential nonces and status checks
- Peer replay prevention: `ProtocolV1PeerReplayStore` durable duplicate rejection in `protocol_v1_peer_message.py`
- Peer authentication: `require_peer_secret`, `verify_protocol_v1_peer_request`
- Content hash verification: `content.py` verification helpers and content object checks
- MIME/content integrity: `resolve_payload_hash`, `store_content_bytes`, `verify_content_object_payload`
- Public vs admin authorization: `api.py` route dependencies and access-control helpers
- Invite/access controls: `config.py`, access-control route guards
- Validator/allowlist controls: peer registration and access-control enforcement

The most likely accidental regression points in later work are hash normalization, message formatting, and nonce/replay state handling.

## 15. Existing test coverage

| Protocol area | Test file(s) | Current coverage | Important missing coverage |
|---|---|---|---|
| Blocks | `tests/test_protocol_v1.py`, `tests/blockchain/test_protocol_v1_block_format.py`, `tests/blockchain/test_certificate_block_validation.py`, `tests/api/test_peer_block_sync_api.py` | Legacy/v1 hash branching, fixed canonical block vectors, embedded media persistence, peer block sync | Genesis is still missing a fixed golden vector |
| Block validation | `tests/test_protocol_v1.py`, `tests/blockchain/test_protocol_v1_block_format.py`, `tests/blockchain/test_certificate_block_validation.py` | Canonical payload bytes, byte-tag collision regression, embedded-media tamper rejection, certificate metadata checks | No fixed genesis validation corpus yet |
| Chain validation | `tests/blockchain/test_chain_originality_comparison.py`, `tests/api/test_chain_sync_api.py` | Genesis mismatch, fork choice, best-chain selection | No hard-coded genesis hash fixture |
| Fork choice | `tests/blockchain/test_chain_originality_comparison.py` | Originality-score / height / latest-hash ordering | No independent golden vector |
| Certificates | `tests/test_protocol_v1_originality_votes.py`, `tests/submissions/test_originality_certificate.py`, `tests/api/test_submission_lifecycle_api.py`, `tests/api/test_peer_certificate_sync_api.py` | Creation, literal Protocol v1 certificate vectors, deterministic IDs, vote hash linkage, peer tamper rejection, persistence | Reset policy for legacy launch data is still not fixed |
| Submissions | `tests/api/test_submission_lifecycle_api.py`, `tests/api/test_access_control_api.py`, `tests/content/test_content_storage.py` | Submission lifecycle, content linking, access control | No fixed submission ID vector |
| Votes | `tests/test_protocol_v1_originality_votes.py`, `tests/api/test_wallet_auth_api.py`, `tests/api/test_submission_lifecycle_api.py`, `tests/api/test_peer_vote_sync_api.py` | Literal Protocol v1 vote payload/message/hash vectors, local signed-vote persistence, peer replay/tamper rejection, vote-set ordering invariance | Login/submission challenge domains still use older human-readable formats |
| Wallet recovery | `tests/test_protocol_v1_originality_votes.py`, `tests/api/test_submission_lifecycle_api.py`, `tests/api/test_native_account_api.py`, `tests/api/test_chain_sync_api.py` | Fixed recovered-address vector plus existing signed-message recovery paths | Login/submission challenges still use older human-readable formats |
| Native transactions | `tests/test_native_transfer.py`, `tests/test_protocol_v1_native_transfers.py`, `tests/api/test_native_transfer_api.py`, `tests/api/test_native_transaction_block_inclusion_api.py`, `tests/api/test_peer_transaction_sync_api.py`, `tests/storage/test_storage_tools.py` | Literal Protocol v1 transfer payload/message/hash vectors, signature recovery, signature-independent tx IDs, explicit legacy/v1 dispatch, API challenge flow, block inclusion, peer sync, and storage/export round trips | Durable launch reset policy for pending legacy tx state is still not fixed |
| Nonces / replay | `tests/test_native_transfer.py`, `tests/api/test_peer_auth_api.py`, `tests/test_protocol_v1_peer_messages.py`, `tests/api/test_peer_transaction_sync_api.py` | Sequential transfer nonces, peer nonce validation, duplicate-message rejection, durable restart replay rejection | Wallet challenge restart durability is still not covered by a similar persisted-state vector |
| Peer messages | `tests/api/test_peer_auth_api.py`, `tests/api/test_peer_block_sync_api.py`, `tests/api/test_peer_vote_sync_api.py`, `tests/api/test_peer_certificate_sync_api.py`, `tests/api/test_peer_content_sync_api.py`, `tests/api/test_peer_transaction_sync_api.py`, `tests/api/test_chain_sync_api.py`, `tests/test_protocol_v1_peer_messages.py` | Explicit envelope vectors, wrong-network/version/type rejection, sender binding, payload mutation failure, replay rejection, signed inner-object revalidation, and chain/content sync auth | No asymmetric peer-signature mode exists today |
| Genesis | `tests/blockchain/test_chain_originality_comparison.py`, `tests/api/test_chain_sync_api.py`, `tests/integration/test_two_node_consensus_verification.py` | Genesis mismatch detection and summary checks | No fixed genesis object/hash golden vector |
| Storage | `tests/storage/test_json_storage_backend.py`, `tests/storage/test_sqlite_storage_backend.py`, `tests/storage/test_storage_tools.py`, `tests/blockchain/test_protocol_v1_block_format.py` | JSON/SQLite Protocol v1 block round trips, export/import preservation of embedded media, content persistence | No launch-reset migration fixture yet |
| Lifecycle transitions | `tests/api/test_submission_lifecycle_api.py`, `tests/api/test_voter_rewards_api.py`, `tests/integration/test_task_10_3_voting_rewards.py` | Pending -> approved/rejected -> minted/rewarded | No protocol-state-machine reference table test |
| MODEL A / content integrity | `tests/test_protocol_v1.py`, `tests/blockchain/test_protocol_v1_block_format.py`, `tests/api/test_peer_block_sync_api.py`, `tests/api/test_peer_content_sync_api.py` | Full media bytes committed in Protocol v1 blocks, cache deletion recovery, peer rejection of tampered media, cache repopulation from block payload | Legacy accepted-media migration/reset policy is still not tested |

True golden vectors now exist for Protocol v1 block payload bytes and hashes, vote payloads and signatures, vote-set hashes, certificate identity payloads and IDs, native transfer payloads/messages/tx IDs/signature recovery, and Protocol v1 peer envelopes/message IDs/HMAC tags.

## 16. Determinism risks

- Runtime timestamps in genesis and some certificate creation paths: consensus critical
- Random UUID submission IDs: protocol-adjacent
- Wallet challenge nonces: protocol-adjacent, but handled as auth state
- Peer replay-state files: protocol-adjacent security state, because stale snapshot restore changes replay windows
- Legacy block hashing still depends on pre-v1 string assembly
- Floating-point values in rewards and percentages are normalized for Protocol v1 blocks, but other domains still need review
- Filesystem state for the genesis image remains consensus critical; Protocol v1 block validity no longer depends on auxiliary content paths
- Environment variables for network, peer auth, access control, and storage backend: consensus critical
- Address casing normalization: consensus critical and handled in helpers
- MIME inference: protocol-adjacent for submission handling and storage, but Protocol v1 block validation uses the declared MIME type instead of local MIME sniffing
- Database ordering / insertion order: protocol-adjacent for persistence, consensus critical only if it leaks into hashes or validation

## 17. Prompt-vs-current-implementation mismatches

| Fixed project decision | Current implementation status | PASS / PARTIAL / FAIL | Evidence |
|---|---|---|---|
| Independent Layer 1 blockchain with native ZOID | Native transfer layer exists and is on-chain | PASS | `native_transfer.py`, `blockchain.py` |
| MetaMask / 0x signatures for identity | Wallet recovery uses Ethereum message signing | PASS | `wallet_auth.py`, `native_transfer.py` |
| ZOID is not an ERC-20 token | Native transfer layer is separate from ERC-20 | PASS | `native_transfer.py`, API transfer routes |
| Meme Proof of Originality earns a block | Submission voting and certificate flow exist | PASS | `submission.py`, `originality_certificate.py`, `blockchain.py` |
| One accepted media submission creates exactly one blockchain block | Modern mint flow enforces one-mint-per-submission, but legacy direct block creation still exists | PARTIAL | `blockchain.py`, `api.py` |
| MODEL A full accepted media file is part of immutable blockchain record | Protocol v1 accepted-media blocks embed immutable bytes and validate them in-block; legacy blocks do not | PARTIAL | `block.py`, `blockchain.py`, `docs/protocol-v1-block-format.md` |
| Native ZOID transfers settle on-chain and may be included in content blocks | Signed native txs are included and settled in blocks | PASS | `native_transfer.py`, `blockchain.py`, `api.py` |
| Controlled validator set is acceptable for Public Testnet v1 | Peer registration and authenticated peer sync are centralized enough for a controlled set | PASS | `peer_sync.py`, `api.py`, `config.py` |
| Preserve existing security checks | Strong checks remain in place | PASS | `wallet_auth.py`, `peer_sync.py`, `native_transfer.py`, `api.py` |
| Public API paths remain separated from privileged/admin lifecycle operations | Separate route guards exist | PASS | `api.py` |
| Consensus-affecting behavior must be deterministic and reproducible | Protocol v1 blocks, votes, certificates, native transfers, and peer transport now bind canonical network/version/domain deterministically, but genesis and lifecycle/finality are still not frozen | PARTIAL | `protocol_v1.py`, `protocol_v1_peer_message.py`, `protocol_v1_native_transfer.py`, `block.py`, `blockchain.py`, `peer_sync.py` |

## 18. Recommended remaining Milestone 1 implementation order

1. Freeze and publish genesis so every honest node boots from the same committed object.
2. Publish reset/migration policy for mixed legacy and Protocol v1 data.
3. Tighten finality/lifecycle semantics after the core object formats are frozen.
4. Review the remaining legacy direct block-creation path.
5. Define a coordinated peer shared-secret rotation policy for validator operations.

## Test result summary

### Pre-change

- `python -m pytest -q`
  - failed: `No module named pytest`
- `.\.venv\Scripts\python.exe -m pytest -q`
  - passed: `738 passed in 77.25s`

### Post-change

- `.\.venv\Scripts\python.exe -m pytest -q tests/api/test_peer_auth_api.py tests/api/test_peer_block_sync_api.py tests/api/test_peer_vote_sync_api.py tests/api/test_peer_certificate_sync_api.py tests/api/test_peer_transaction_sync_api.py tests/api/test_peer_content_sync_api.py tests/api/test_chain_sync_api.py tests/test_protocol_v1_peer_messages.py`
  - passed: `134 passed in 12.96s`
- `.\.venv\Scripts\python.exe -m pytest -q tests/api/test_peer_submission_sync_api.py tests/api/test_peer_auth_api.py tests/api/test_peer_block_sync_api.py tests/api/test_peer_content_sync_api.py tests/api/test_peer_vote_sync_api.py tests/api/test_peer_certificate_sync_api.py tests/api/test_peer_transaction_sync_api.py tests/api/test_chain_sync_api.py tests/api/test_wallet_auth_api.py tests/api/test_native_transfer_api.py tests/api/test_native_transaction_block_inclusion_api.py tests/blockchain/test_protocol_v1_block_format.py tests/blockchain/test_certificate_block_validation.py tests/test_protocol_v1.py tests/test_protocol_v1_originality_votes.py tests/test_protocol_v1_native_transfers.py tests/test_protocol_v1_peer_messages.py tests/storage/test_storage_tools.py tests/storage/test_json_to_sqlite_migration.py tests/config/test_security_modes.py`
  - passed: `363 passed in 34.75s`
- `.\.venv\Scripts\python.exe -m pytest -q tests/integration/test_two_node_native_transfer_verification.py tests/integration/test_two_node_consensus_verification.py tests/integration/test_two_node_storage_backends.py`
  - passed: `17 passed in 5.57s`
- `.\.venv\Scripts\python.exe -m pytest -q`
  - passed: `843 passed in 240.42s (0:04:00)`
