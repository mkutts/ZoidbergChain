# Milestone 7 Task 7.1 — Repository Audit and Compression Architecture

Status: investigation complete; no compression implementation or benchmark corpus was created.  
Audit date: 2026-10-18.  
Repository examined: branch `Compression-State-Bloat-and-Node-Economics`, HEAD `fda5103f72c9dcbf6b63a724a69fe79d1e9a84e2`.

## 1. Executive summary

Public Testnet v1 already implements Model A for current accepted-media blocks: the exact accepted byte string is `Block.media_bytes`, it is hash-committed by the block, and it can be reconstructed without the mutable content cache.  The right architecture for Task 7 is therefore **transparent physical storage compression (Approach A)**: compress only a local persistence representation while retaining the existing logical block record, canonical bytes-object encoding, block hash inputs, peer payloads, exports, and media API response bytes exactly as they are today.

Approach B—placing a compressed payload and compression metadata in the canonical block serialization—is not compatible with the frozen current block format.  It would change block hashes, certificate/media bindings, peer interoperability, and historical validation.  It must not be introduced under block versions 1 or 2.  A future explicit protocol upgrade could choose it only after a separately approved activation/negotiation decision and a new block version; it is not a Task 7.1 implementation decision.

This conclusion is not an endorsement of a particular codec or claimed storage saving.  No ratios, timings, database sizes, or node-economics figures have been measured.

## 2. Repository state and relevant history

The working tree was clean at the start of the audit.  No unrelated local changes were present, so documentation work was safe.  The recent relevant history is:

- `fda5103` — Merge Milestone 6: immutable media safety and admission
- `9df8d03` — Milestone 6 Task 6.11A: finalize release readiness
- `d34da34` — Milestone 6 Task 6.9: harden immutable media byte integrity
- `63f1549` / `a92ffb5` / `a321d4e` — Task 6.7 / 6.6 / 6.5 admission lifecycle work
- `160a02e` / `454f962` — Task 6.3 / 6.2 technical validation and admission policy

Primary existing documentation is `docs/protocol-v1.md`, `docs/protocol-v1-block-format.md`, `docs/protocol-v1-lifecycle-finality.md`, `docs/protocol-v1-peer-messages.md`, `docs/milestone-6-task-6.9-media-integrity.md`, and `docs/backup-restore-runbook.md`.

### Audit mismatches with assumptions

1. “SQLite schema” does not mean a normalized media/blob table.  The canonical `chain` (including the hex bytes object) is stored as JSON in `storage_sections.json_data`; `minted_media_originality_index` is an index/cache and does not store the media bytes.  See `storage.py:SQLiteStorageBackend._initialize_database`, `_load_sections_from_connection`, and `_save_sections_to_connection`.
2. Current media blocks include both original Protocol v1 blocks (`block_version: 1`) and admission blocks (`block_version: 2`).  `docs/protocol-v1-block-format.md` describes v1 prominently, while `block.py:ADMISSION_BLOCK_VERSION`, `media_integrity.CURRENT_MEDIA_BLOCK_VERSIONS`, and the Task 6.9 report establish v2 as another current immutable-media format.  Any Task 7 work must preserve both.
3. Generic runtime upload limits are 5 MiB / 256 KiB text (`config.py`), but the active versioned admission policy’s consensus limits are 262,144 bytes for both accepted images and canonical text plus 524,288 canonical non-genesis block bytes (`media_admission_policy.py`).  Technical validation enforces the tighter policy for current admission.  Benchmarks must label these separately, rather than call 5 MiB an accepted-media maximum.
4. Policy describes a peer chain page of 64 blocks and 16 MiB encoded response (`media_admission_policy.py`), but `api_routers/public_chain.py:chain_blocks` returns all blocks from `from_height`; `PeerChainSyncService.fetch_blocks` requests from height 0.  This is an existing scalability/API-limit gap, not something compression may silently mask.

## 3. Current architecture and media lifecycle

### Accepted media inventory and limits

| Accepted detected MIME | Category | Accepted-byte semantics | Consensus acceptance limit |
| --- | --- | --- | ---: |
| `text/plain` | text | UTF-8 after CRLF/CR-to-LF and outer-whitespace trim | 262,144 bytes after canonicalization |
| `image/jpeg` | image | exact accepted upload bytes | 262,144 bytes |
| `image/png` | image | exact accepted upload bytes | 262,144 bytes |
| `image/gif` | image | exact accepted upload bytes; animation capability is policy-governed | 262,144 bytes |
| `image/webp` | image | exact accepted upload bytes; animation capability is policy-governed | 262,144 bytes |

Sources: `config.SUPPORTED_*_MIME_TYPES`; `content.CONTENT_MIME_EXTENSIONS`; `media_admission_policy._ALLOWED_MEDIA_TYPES` and `consensus_protocol.byte_limits`; `media_technical_validation.validate_media_bytes`.  Image structural limits are 1–4096 pixels per dimension, 16,777,216 aggregate decoded pixels, and 60 frames; block canonical serialization is capped at 524,288 bytes.  Declared MIME and filename are not authorities: byte detection, complete container parsing, and isolated image decoding are required (`media_technical_validation.identify_media_type`, `validate_media_bytes`).

### Submission to accepted block

1. HTTP submission enters `api_routers/content.py:submit_content`; local service entry points include `Blockchain.submit_content_operation`, `register_uploaded_content`, and `ContentCoordinationService.upload_binary_content` / `upload_text_content`.
2. `validate_media_bytes` identifies and structurally validates the bytes, canonicalizes text, enforces policy, and emits hash/length-bound technical evidence.  Content is staged in the content-addressed local cache through `content.store_content_bytes`.
3. Submission, attestation, review, originality evidence, and admission certificate processing run in `Blockchain` and the services called from it.  The v2 certificate binds the exact media SHA-256 and technical evidence; validation is in `admission_certificate.validate_admission_certificate` and `BlockValidationService.validate_admission_block`.
4. `BlockProductionService.build_candidate` obtains `resolve_declared_payload_hash(...)["stored_bytes"]` and creates a block with those bytes in `media_bytes`, with `media_hash` and `content_hash` bound to them.  `Blockchain.commit_certified_submission` / `mint_next_queued_submission` is the accepted mint path.
5. Candidate and chain validation use `BlockValidationService.validate_candidate`, `validate_block`, `validate_protocol_v1_payload`, and `validate_certificate_metadata`; chain validation recalculates each block hash before acceptance.

### Authoritative bytes, persistence, and integrity

For current blocks, authoritative bytes live in `Block.media_bytes`, not in the auxiliary cache.  The local content directory and `ContentObject` records are staging/cache/index facilities; `ContentCoordinationService.recover_block_media_bytes` has cache fallback solely for non-embedded legacy records.  `Blockchain.reconstruct_immutable_media` and `media_integrity.reconstruct_media_bytes` use the embedded bytes only for current media blocks.

`Block.to_dict` serializes the bytes using `protocol_v1.encode_canonical_bytes` as `{"$type":"bytes","$encoding":"hex","$value":"..."}`.  `Block.from_dict` rehydrates them.  SQLite persists the `chain` section JSON in `storage_sections`; JSON storage persists the chain document.  Thus the current persistence multiplier is at least hexadecimal expansion of media within JSON, plus the non-hashed `meme.encoded_image` base64 compatibility copy and optional content-cache duplicate.  This is an architecture observation, not a measured multiplier for a dataset.

`content.resolve_declared_payload_hash`, `media_integrity.verify_media_block`, and `validate_current_media_chain_records` verify that current bytes are valid/canonical for their MIME, SHA-256 equals both `media_hash` and `content_hash`, and the stored block hash is correct.  For admission blocks, verifier checks include frozen certificate, attestation, votes, technical-evidence digest/length/hash, and cross-field bindings.

### Serialization, hashing, certificates, and finality

`Block.consensus_payload_v1` contains `media_bytes` directly, plus media/content hashes, MIME/content type, identities, rewards, and for version 2 the entire `admission_certificate`.  `Block.consensus_payload_v1_bytes` wraps it in the network-bound canonical envelope; `Block.calculate_hash_v1` applies SHA-256.  `Block.calculate_hash_legacy` remains an explicit legacy branch.  Canonical JSON rules and bytes-tag rules are frozen in `protocol_v1.py` and `docs/protocol-v1.md`.

Admission certificates and submitter/reviewer signatures depend on the original accepted-byte content hash.  Validator finality signatures bind height and block hash (`services/finality_service.py`; `docs/protocol-v1-lifecycle-finality.md`).  Therefore changing media encoding or block hash invalidates certificate binding and finality evidence even if decompressed pixels or text are equivalent.

### Retrieval, synchronization, portable state, reorganization

- `GET /blocks/{block_hash}/media` in `api_routers/public_chain.py:download_block_media` verifies then returns the exact `media_bytes`, original MIME, and integrity headers.  Block summary APIs omit bytes by default; peer chain fetch explicitly requests them.
- `PeerChainSyncService.fetch_blocks` uses `include_media_bytes=true`; sync validates candidate chains prior to adoption.  `peer_sync.py` additionally validates content/block paths and may repopulate the local cache.  Peer envelopes authenticate payload transport but do not change block media semantics.
- `storage_tools.build_export_snapshot`, `backup_storage`, `export_storage`, and `import_storage`, as well as `storage_migration.migrate_json_to_sqlite`, call current-media validation before accepting/writing state.  Export is JSON and retains canonical bytes objects.  `docs/backup-restore-runbook.md` calls out cache/state restoration and post-restore validation.
- `CanonicalReorgService.rebuild_document` replaces canonical-chain-derived state, restores detached submission state where allowed, invalidates stale originality evidence, and rejects any candidate that detaches persisted quorum-finalized history (`_reconcile_finality`).  Media integrity is rechecked through chain/candidate validation; removed branch blocks are not a license to mutate retained canonical blocks.

## 4. Compression architecture decision

### Approaches evaluated

| Property | A. Transparent physical compression | B. Versioned compression inside canonical block |
| --- | --- | --- |
| Current hash/signature stability | Preserved if decompressed logical record is byte-for-byte identical | Broken for every affected current block |
| Current/historical block compatibility | Preserved, including v1 and v2 | Requires a new version and dispatch; cannot rewrite history |
| Node interoperability | Existing peers/export/API continue to exchange canonical bytes | Every node needs negotiated codec/version before accepting blocks |
| Algorithm/version dependency | Local persistence implementation only; still needs durable migration/read support | Consensus dependency; deterministic byte output and decoder behavior become protocol rules |
| Decompression limits | Node-local bounded reads, integrity-before-use, resource limits needed | Consensus-critical bounded decode; decompression bombs affect peer validation |
| SQLite/index impact | Add optional physical codec/metadata only; canonical indexes remain logical | New canonical fields/schema/index semantics plus migration/version dispatch |
| API retrieval | Decode local physical copy, verify, return original bytes | Decode canonical payload, verify original hash, return bytes; changes protocol/API validation contract |

### Recommendation: Approach A, with an explicit boundary

Implement only an **optional storage-layer codec** that is invisible above the persistence boundary.  The decoded value must be exactly the present `Block.to_dict(include_media_bytes=True)` logical data, including the existing canonical bytes object once serialized for export/transport.  The following must remain unchanged: `Block.consensus_payload_v1`, `Block.calculate_hash_*`, the peer wire payload, backup/export snapshot schema, `media_integrity` contract, certificate evidence, and media API response.

This is compatible with the present implementation because consensus is calculated from logical reconstructed bytes, not SQLite file layout.  It is also the only option that preserves already finalized identities and cross-node behavior while still allowing a node to store data more efficiently at rest.

Approach A is **not** permission to replace the only durable canonical copy with a cache, a content hash, an external object, or a codec-dependent sidecar.  The compressed local object itself must be an atomically persisted, recoverable representation of the full logical canonical record.  A node lacking a cache must still reconstruct original media from its own compressed canonical state.  Checksums/digests for physical records are supplementary and must not replace `media_hash`, `content_hash`, or block hash verification.

### Required design decisions before Task 7.2

No consensus protocol decision is needed to investigate/implement A, but these operational/storage decisions are blockers:

1. **Compression scope:** whole SQLite database/file, `storage_sections.chain` document, individual embedded media values, and/or non-consensus cache copies.  The scope must state which is the authoritative on-disk representation after restart.
2. **Codec and pinned format:** algorithm, library/runtime version policy, framing format, level, deterministic settings, checksum, and recovery behavior.  Compression output need not be consensus-deterministic for A, but decoder compatibility across supported releases is mandatory.
3. **Migration and rollback:** atomic migration, interrupted-write recovery, uncompressed backward read support, backup/export behavior, and whether a downgrade can read compressed state.
4. **Limits:** maximum compressed and decompressed input, expansion-ratio ceiling, streaming/chunking, CPU/memory/time budgets, and error handling.  Fail closed before serving, syncing, exporting, or adopting corrupt canonical state.
5. **Duplication policy:** whether the non-hashed `meme.encoded_image` compatibility copy and local cache are retained, derived, or physically compressed.  Removing a persisted compatibility field is separate compatibility work and is out of scope unless proven safe.
6. **Measurement gate:** benchmark results and a three-year workload/economic model must approve a codec/scope.  The existing code supplies no evidence that a chosen codec yields net value after indexes and operational costs.

If someone proposes B instead, the exact required prior decision is: approve a new protocol/block version with an activation height, capability/version negotiation for peers, a canonical compression framing and decompression limits, an explicit definition of what original bytes the block hash/certificates bind, and historical v1/v2 verification unchanged.  That is a consensus upgrade, not an implementation detail.

## 5. Compatibility and security risks

- Compressing `media_bytes` before existing hashing would create a different media identity and invalidate admission certificates and finality signatures.  Never do this.
- A codec that silently recompresses at export, peer send, or API response risks changing current canonical data.  At these boundaries, materialize and verify original bytes.
- Hex/base64 expansion, JSON escaping, the compatibility `meme.encoded_image`, SQLite page/journal/WAL behavior, indexes, cache duplication, and backups can dominate the apparent media ratio.  Measure complete persisted state, not only codec output.
- Decompression bombs, truncated frames, checksum collisions/misuse, unbounded allocation, malicious peer payloads, and interrupted migrations need independent limits and negative tests.  Existing technical-media decode limits do not automatically protect a new storage codec.
- A local compressed state unreadable by another software release is an availability/restore failure even if consensus hashes are intact.  Portable export must stay self-contained in the existing canonical format unless a separately documented compatible export format is introduced.
- Reorg handling must never retain a compressed physical object under a canonical key after its source block is detached, nor remove/alter a retained finalized block’s object.  Physical cleanup requires recovery-safe, reorg-aware ordering.

## 6. Reproducible benchmark design (proposal only)

### Corpus requirements

Create a manifest-controlled corpus with immutable SHA-256, MIME, source/license/provenance, and declared size for every accepted type: text, JSON/metadata represented as accepted `text/plain`, source code represented as accepted `text/plain`, PNG, JPEG, GIF, and WebP.  Include text/code that are low-, medium-, and high-entropy; minified and pretty JSON; photographic and synthetic/raster images; animated and still GIF/WebP where policy permits; boundary-sized valid samples; and already-compressed/near-incompressible samples.  Do not treat a filename extension as evidence of type: run `validate_media_bytes` and record its accepted canonical bytes.

The corpus must not include unaccepted archive/executable types as normal workload samples; they belong only in negative/resource-limit tests.  Files beyond the policy limit belong in rejection measurements, not compression-ratio aggregates.  The benchmark corpus is not created by this task.

### Harness and measurements

For each corpus item and candidate codec/scope, run isolated warm-up plus at least a documented number of repeated cold/warm trials on a declared host/OS/Python/library build.  Record raw samples and machine metadata, not only averages.  Use a fixed harness that:

1. validates input through `validate_media_bytes` and records accepted bytes/hash;
2. constructs representative v1 and v2 logical block records without changing production block behavior;
3. measures compression and decompression with monotonic high-resolution timing;
4. verifies decompressed bytes equal accepted bytes byte-for-byte, `resolve_declared_payload_hash` matches, `verify_media_block` passes, and existing block hash is unchanged;
5. persists/reloads through both JSON and SQLite paths as applicable, runs export/import, and measures artifact sizes; and
6. records failures, peak resident memory where the platform can provide it, compressed/decompressed byte counts, and storage component sizes.

Report separately: compressed payload ratio `compressed/original`; expansion `decompressed/compressed`; compression and decompression median/p95/max time; raw accepted bytes; canonical block serialization bytes; physical SQLite database plus WAL/journal size after checkpoint; JSON/export/backup size; content-cache size; metadata/index/table overhead; and total node state.  Never call an estimated future value “measured.”

For three-year economics, keep a parameter sheet separate from measurements: blocks/day by MIME mix, median/p95 accepted bytes, expected cache policy, chain retention/replication factor, storage price per GB-month, backup copies, bandwidth/electricity/CPU assumptions, and growth rate.  Calculate low/base/high scenarios from measured per-block physical deltas.  Publish equations and assumptions; do not extrapolate from a single image or codec microbenchmark.

### Reusable infrastructure

- Validation and accepted-byte canonicalization: `media_technical_validation.validate_media_bytes`.
- Hash/integrity checks: `media_integrity.verify_media_block`, `reconstruct_media_bytes`, `validate_current_media_chain_records`.
- Canonical serialization: `protocol_v1.encode_canonical_bytes`, `Block.consensus_payload_v1_bytes`, `Block.calculate_hash_v1_from_dict`.
- Persistence and portability: `JSONStorageBackend`, `SQLiteStorageBackend`, `storage_tools.build_export_snapshot` / `import_storage`, and `storage_migration.migrate_json_to_sqlite`.
- Existing benchmark pattern: `scripts/milestone_6_task_6_3_media_validation_benchmark.py` (timing/reporting only; it is not a compression benchmark).
- Existing focused tests: `tests/blockchain/test_protocol_v1_block_format.py`, `tests/test_milestone_6_task_6_9_media_integrity.py`, `tests/storage/test_sqlite_storage_backend.py`, `tests/storage/test_storage_tools.py`, and peer chain/block API tests.

Pillow is already used by the technical validation benchmark/test paths; no compression library is currently pinned in `requirements-core.txt`.  Select and pin one only after the preceding codec decision and security/license review; do not install one for Task 7.1.

## 7. Proposed implementation areas and test requirements

These are candidates for Tasks 7.2–7.8, not changes made here:

| Area | Likely modules | Required tests |
| --- | --- | --- |
| Codec abstraction and limits | new narrowly scoped storage-codec module; `storage.py` integration | round-trip, malformed/truncated input, expansion limits, unsupported codec/version, deterministic recovery semantics |
| SQLite authoritative persistence | `SQLiteStorageBackend` section load/save and migration path | restart, atomic commit interruption/recovery, WAL/checkpoint accounting, old uncompressed database read |
| JSON/export/backup | `storage_tools.py`, `storage_migration.py`, backup runbook | export/import across compressed/uncompressed nodes, bit-exact block/media/hash/certificate/finality preservation |
| Node media/cache behavior | `services/content_coordination_service.py`, `content.py` only if needed | cache deletion, cache rebuild, duplicate-accounting, no off-chain dependency |
| API and sync regression | `api_routers/public_chain.py`, peer services | exact download response, peer transfer of canonical bytes, no changed wire payload, corrupt local physical record failure |
| Observability/economics | a new benchmark script/docs only | stable manifest, reproducible reports, component-size accounting, scenario math tests |

Every implementation phase must retain golden v1 and v2 block hashes, certificate digests/signatures, finality evidence, and legacy read behavior.  Add cross-version and mixed-node tests before enabling compression by default.

## 8. Recommended sequencing for Tasks 7.2–7.8

1. **7.2 — Decision record and codec contract:** resolve the six operational blockers above; freeze scope, on-disk framing, limits, compatibility, and rollback requirements.  Do not alter consensus serialization.
2. **7.3 — Reproducible benchmark harness and corpus manifest:** build the harness and approved corpus, then measure candidates and publish raw results/assumptions.
3. **7.4 — Storage codec implementation behind opt-in compatibility mode:** implement atomic, bounded physical compression with uncompressed-read compatibility; no default migration yet.
4. **7.5 — Migration, backup, export/import, and recovery:** add resumable/atomic conversion, corruption handling, portable canonical export verification, and restore rehearsal.
5. **7.6 — Sync/API/cache integration and economics instrumentation:** prove peer/API logical payloads are unchanged; add component-size telemetry and a documented node-growth model.
6. **7.7 — Adversarial and compatibility validation:** fuzz/truncate/expand/corrupt tests; mixed compressed/uncompressed node tests; v1/v2/legacy, reorg, and finality regressions.
7. **7.8 — Release decision and operational rollout:** review measured benefit versus complexity, set migration/backup policy, stage opt-in rollout, and only then consider default enablement.

The precise titles or scope labels for later tasks should be reconciled with the project milestone plan before implementation; this sequence expresses the dependencies discovered in the current repository, not a claim that later task specifications have already been approved.

## 9. Open decisions and blockers

Task 7.1 is ready for review, but Task 7.2 is blocked on an approved storage-codec decision and benchmark plan.  In particular, the project needs a chosen physical-compression scope, codec/framing/version support policy, safety limits, migration/rollback strategy, duplicate-storage policy, and measurable economics acceptance criteria.  A protocol-change proposal is additionally required if anyone wants canonical compression (Approach B).
