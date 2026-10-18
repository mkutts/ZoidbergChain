# Milestone 7 Tasks 7.1 / 7.1A — Repository Audit and Compression Architecture

Status: Task 7.1A reevaluation complete; Task 7.2 protocol contract specified in [Canonical Media Compression Protocol Specification](milestone-7-compression-protocol.md), pending review and later measurements. No compression implementation, corpus, reset, or production-code change.

Task 7.2 follow-up (2026-10-18, baseline `727a993`): the linked specification defines protocol v2 / media block v3, one media descriptor and strict base64 payload, original-byte identity, encoded-representation block commitments, bounded validation without recompression, and a fresh-network reset plan. `media_hash` / `content_hash` become derived views of `media.original_sha256` in the new block schema; signed evidence retains its original-byte bindings. “Compress only when smaller” is producer policy. Codec/profile/resource freeze remains gated by **Task 7.4 benchmarks**, as directed by the Task 7.2 request; that instruction supersedes the tentative 7.3/7.4 sequencing below. Other sections retain the Task 7.1A audit/proposal history; the linked contract resolves its media-format decisions without claiming implementation or launch readiness.

Audit / reevaluation date: 2026-10-18.

Initial Task 7.1 audit HEAD: `fda5103f72c9dcbf6b63a724a69fe79d1e9a84e2`.

Task 7.1A repository: branch `Compression-State-Bloat-and-Node-Economics`, HEAD `2924faea02ac607ab8a4b4242e92f43042027375` (`Milestone 7 Task 7.1: audit storage and compression architecture`). Working tree clean before reevaluation.

## 1. Executive summary

**Revised recommendation: Approach C, a hybrid with a versioned canonical media encoding as the required protocol foundation and optional local storage optimizations.** A complete, self-contained compressed media payload can be committed directly by the block hash while `media_hash` and `content_hash` remain SHA-256 of the original accepted, uncompressed bytes. Validators decode with bounded, protocol-defined rules and verify those original-byte bindings. No external media store or dictionary is required.

The owner has confirmed that ZoidbergChain is still in development, the chain can be reset, historical v1/v2 compatibility is optional, and protocol/database migrations are permitted before the next launch. These assumptions supersede Task 7.1's recommendation to preserve current serialization at all costs. Current production code still expects uncompressed embedded bytes; implementing this recommendation requires an explicit new block/protocol contract and coordinated launch identity. Permission to plan for a reset does not execute or schedule one.

Canonical compression addresses replicated block size, peer transfer, and portable snapshots as well as disk use. Optional local BLOB storage, indexes, and bounded caches can then reduce serialization duplication and write amplification without affecting consensus. Start with one approved lossless codec plus an identity/raw encoding for media that does not benefit; do not add several mandatory codecs or compulsory double compression.

Deterministic validation is mandatory; identical compressor output across producers is not. The producer may choose an allowed encoding once, and every validator must verify the exact committed representation rather than recompress it. This design preserves original-media identity while allowing different valid block representations of that media, subject to the existing uniqueness and fork-choice rules.

Task 7.2 **cannot proceed unchanged**: replace the local-only storage contract with a launch protocol/encoding contract and bounded-decoder specification, followed by benchmark validation before codec/profile freeze. No compression ratios, performance gains, or three-year savings have been measured in this task.

## 2. Repository state and relevant history

The working tree was clean at the start of both audits. No unrelated local changes were present. The Task 7.1 report is now committed at `2924fae`; only this report is edited for Task 7.1A. The preceding relevant history is:

- `fda5103` — Merge Milestone 6: immutable media safety and admission
- `9df8d03` — Milestone 6 Task 6.11A: finalize release readiness
- `d34da34` — Milestone 6 Task 6.9: harden immutable media byte integrity
- `63f1549` / `a92ffb5` / `a321d4e` — Task 6.7 / 6.6 / 6.5 admission lifecycle work
- `160a02e` / `454f962` — Task 6.3 / 6.2 technical validation and admission policy

Primary existing documentation is `docs/protocol-v1.md`, `docs/protocol-v1-block-format.md`, `docs/protocol-v1-lifecycle-finality.md`, `docs/protocol-v1-peer-messages.md`, `docs/milestone-6-task-6.9-media-integrity.md`, and `docs/backup-restore-runbook.md`.

### Audit mismatches with assumptions

1. “SQLite schema” does not mean a normalized media/blob table.  The canonical `chain` (including the hex bytes object) is stored as JSON in `storage_sections.json_data`; `minted_media_originality_index` is an index/cache and does not store the media bytes.  See `storage.py:SQLiteStorageBackend._initialize_database`, `_load_sections_from_connection`, and `_save_sections_to_connection`.
2. Current media blocks include original Protocol v1 blocks (`block_version: 1`) and admission blocks (`block_version: 2`). `docs/protocol-v1-block-format.md` describes v1 prominently; `block.py:ADMISSION_BLOCK_VERSION`, `media_integrity.CURRENT_MEDIA_BLOCK_VERSIONS`, and the Task 6.9 report establish v2 too. Under Task 7.1A, preserving those formats at the next launch is optional. The current runtime's version rejection still has to be changed explicitly in a later implementation task.
3. Generic runtime upload limits are 5 MiB / 256 KiB text (`config.py`), but the active versioned admission policy’s consensus limits are 262,144 bytes for both accepted images and canonical text plus 524,288 canonical non-genesis block bytes (`media_admission_policy.py`).  Technical validation enforces the tighter policy for current admission.  Benchmarks must label these separately, rather than call 5 MiB an accepted-media maximum.
4. Policy describes a peer chain page of 64 blocks and 16 MiB encoded response (`media_admission_policy.py`), but both `api_routers/peer.py:peer_chain_blocks` and `api_routers/public_chain.py:chain_blocks` select all blocks from `from_height`; `PeerChainSyncService.sync_peer` fetches from height 0. Compression alone does not provide pagination, resumability, or bounded initial-sync memory.
5. The policy declares a 524,288-byte canonical block limit, but `evaluate_media_admission_policy` checks it only when supplied `canonical_block_bytes`. Targeted searches in the production/validation paths did not find that argument being supplied. `BlockProductionService.build_candidate` instead uses a legacy approximate size estimate and `max_block_size_kb=500`. The new protocol needs an exact serialized-block check in both producer and validator, not an assumption that the declaration is already universally enforced.

## 3. Current architecture and media lifecycle

### Accepted media inventory and limits

| Accepted detected MIME | Category | Accepted-byte semantics | Consensus acceptance limit |
| --- | --- | --- | ---: |
| `text/plain` | text | UTF-8 after CRLF/CR-to-LF and outer-whitespace trim | 262,144 bytes after canonicalization |
| `image/jpeg` | image | exact accepted upload bytes | 262,144 bytes |
| `image/png` | image | exact accepted upload bytes | 262,144 bytes |
| `image/gif` | image | exact accepted upload bytes; animation capability is policy-governed | 262,144 bytes |
| `image/webp` | image | exact accepted upload bytes; animation capability is policy-governed | 262,144 bytes |

Sources: `config.SUPPORTED_*_MIME_TYPES`; `content.CONTENT_MIME_EXTENSIONS`; `media_admission_policy._ALLOWED_MEDIA_TYPES` and `consensus_protocol.byte_limits`; `media_technical_validation.validate_media_bytes`. Image structural limits are 1–4096 pixels per dimension, 16,777,216 aggregate decoded pixels, and 60 frames. The policy's canonical non-genesis block budget is 524,288 bytes; see the enforcement gap above. Declared MIME and filename are not authorities: byte detection, complete container parsing, and isolated image decoding are required (`media_technical_validation.identify_media_type`, `validate_media_bytes`). JSON and ordinary source-code text are benchmark subcategories only when accepted as `text/plain`; script/active-content prefixes are rejected by `identify_media_type`. There is no separate `application/json` or source-code MIME allowance.

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

Admission certificates and submitter/reviewer signatures depend on the original accepted-byte content hash (`admission_certificate.validate_admission_certificate`, `protocol_v1_submitter_attestation.validate_submitter_attestation`, `dual_review.verify_vote_record`). Validator finality signatures bind height and block hash (`protocol_v1_finality.build_protocol_v1_finality_attestation_payload`; `services/finality_service.py`). **Correction to Task 7.1:** lossless representation changes need not invalidate a content-hash signature if original bytes and all its signed context remain identical. A changed block hash does invalidate finality attestations for the old block. Changing network/domain/policy/reference context independently invalidates the corresponding evidence. Section 5 distinguishes those cases.

### Retrieval, synchronization, portable state, reorganization

- `GET /blocks/{block_hash}/media` in `api_routers/public_chain.py:download_block_media` verifies then returns the exact `media_bytes`, original MIME, and integrity headers.  Block summary APIs omit bytes by default; peer chain fetch explicitly requests them.
- `PeerChainSyncService.fetch_blocks` uses `include_media_bytes=true`; sync validates candidate chains prior to adoption.  `peer_sync.py` additionally validates content/block paths and may repopulate the local cache.  Peer envelopes authenticate payload transport but do not change block media semantics.
- `storage_tools.build_export_snapshot`, `backup_storage`, `export_storage`, and `import_storage`, as well as `storage_migration.migrate_json_to_sqlite`, call current-media validation before accepting/writing state.  Export is JSON and retains canonical bytes objects.  `docs/backup-restore-runbook.md` calls out cache/state restoration and post-restore validation.
- `CanonicalReorgService.rebuild_document` replaces canonical-chain-derived state, restores detached submission state where allowed, invalidates stale originality evidence, and rejects any candidate that detaches persisted quorum-finalized history (`_reconcile_finality`).  Media integrity is rechecked through chain/candidate validation; removed branch blocks are not a license to mutate retained canonical blocks.

## 4. Revised architecture decision

### Comparison under a new-launch assumption

These are architectural expectations, not benchmark results. B means one versioned, self-contained encoding in the canonical block, including raw/identity fallback. C uses B as its protocol plus optional local optimizations; it does not require compressing already-compressed frames again.

| Criterion | A. Physical storage compression | B. Canonical block media encoding | C. Canonical encoding + optional local optimizations |
| --- | --- | --- | --- |
| 1. Physical disk | Can compress repeated JSON/hex/base64 at rest; DB layout, indexes, and caches still matter. | Stores a smaller media representation when compression pays; hex/duplicate copies can negate gains. | B plus binary payload rows, less duplication, bounded cache retention, and optional metadata compression; net benefit must be measured. |
| 2. Canonical block size | Unchanged. Canonical hash input still includes uncompressed bytes in hex. | Encoded payload plus descriptor replaces raw payload; smaller only when actual serialized savings exceed overhead. | Same canonical size as B. Local optimizations cannot change it. |
| 3. Peer synchronization bandwidth | Unchanged for current wire format. Separate HTTP transport compression is possible but is another feature. | Peers exchange the exact committed compressed payload; no raw compatibility copy is needed. | Same required wire data as B; optional transport changes measured separately. |
| 4. Initial node sync | Disk savings, but full original payload transport and current whole-chain JSON processing persist. | Potentially fewer received bytes, but every block still needs bounded decompression/hash/evidence validation. | B plus incremental persistence/caches can bound memory and writes. Pagination/resume is still separate required work. Net elapsed time is unmeasured. |
| 5. Backups/snapshots | Physical copies may shrink; existing logical JSON exports expand to original representation. Archive compression could shrink them separately. | Versioned logical exports retain encoded payload and original hash; no decompress/recompress needed for portability. | Same canonical snapshot as B; optional archive/storage compression and indexes accounted separately. |
| 6. Consensus determinism | No codec in consensus, if local decoding preserves existing logical data. | Exact committed bytes and deterministic decoding/validation rules required; identical compressor output is optional. | Same protocol requirements as B; optional local codecs remain outside consensus. |
| 7. Block/media hash semantics | Both unchanged. | Block hash commits to encoded bytes and descriptor; media/content hashes commit to decoded original bytes. | Same two identities as B; local compaction preserves exact committed bytes. |
| 8. Signatures/certificates | Current signatures remain valid with unchanged signed context. | Original-hash attestations can retain their meaning; changed domain/network/policy/references require fresh evidence. Changed block hashes need new finality signatures. | Same as B. A local wrapper has no signature effect. |
| 9. CPU/memory | Local compress/decompress on persistence/read; whole-section codecs can repeatedly process history. | Producer compression once; validators, initial sync, and retrieval pay bounded decode/hash costs. Persisting the frame avoids repeated encoding. | B plus optional local overhead; lazy decode/bounded caches help RAM, but cache residency and extra layers cost resources. |
| 10. Maintainability | Simpler protocol, but misses protocol-wide size benefits and still needs storage-format support. | Decoder profile becomes a permanent protocol dependency for launched history; minimize codecs and version it explicitly. | Same permanent decoder obligation, plus a separately evolvable storage adapter. Layering helps only if boundaries remain explicit. |
| 11. Security/limits | Local corruption/bombs and migration risks; peer bodies remain bounded independently. | Adversarial encoded payloads become consensus input; frame/window/output/work limits are mandatory. | B plus bounded, recoverable local wrappers. Optional local settings cannot redefine block validity. |
| 12. Complexity/tests | Lowest protocol impact; storage round-trip/migration tests dominate. | Changes block schema/hash, validation, peer/API, exports, and launch fixtures. Cross-decoder and adversarial tests required. | Largest total scope if all local ideas are built; stage B first and add only measured local improvements. |

### Recommendation and tradeoff

Choose **C**, with **B mandatory and local optimizations optional**. For years of full-media retention, the same payload is replicated across every node, initial sync, and snapshot. Canonical compression makes those paths use one durable representation. A alone cannot reduce canonical bytes and cannot reduce today's peer payload without adding a separate transport codec. Both A and C can yield disk savings; this report does not claim C will always beat A on disk or CPU.

The extra consensus surface of B/C is a real cost. Contain it with one lossless codec profile, independently decodable payloads, raw fallback, strict resource bounds, and immutable original-byte identity. If benchmarks do not support a compressed mode, the encoding envelope can launch with identity mode alone; do not add an unproven decoder merely to meet a compression target. Codec choice remains gated by Task 7.3 measurements.

### Canonical representation and original-byte hash

The proposed block envelope below is conceptual, not a finalized schema or production implementation. `M` is the exact **accepted** original byte string: unchanged bytes for images, and the already-approved canonical UTF-8 bytes for text. Lossless compression recovers M; it does not promise to recover whitespace/newlines removed before text acceptance.

```text
H = SHA256(M)
media = {
    encoding_version: <explicit new envelope version>,
    codec: <identity or the one approved lossless codec profile>,
    original_length: len(M),
    payload: <complete encoded byte string E>
}
media_hash = H
content_hash = H
block_hash = SHA256(new_canonical_domain({..., media, media_hash, content_hash, ...}))
```

The block hash commits to E, encoding version, codec, original length, original hashes, MIME, certificate, and the other consensus fields. `Decode(codec, E)` must produce exactly M, with exactly the declared length and SHA-256 H. No original bytes need to be duplicated in the canonical block: the self-contained encoded payload, descriptor, and retained protocol decoder are sufficient for Model A. A compressed-payload hash is optional redundancy because the block hash already commits to E; it must never replace H as media identity.

Use a distinct field for the encoded payload rather than silently reinterpreting current `media_bytes`. Never hash a normalized/re-encoded substitute for E. The current canonical hex bytes tag could encode E without changing the generic serializer, although a new block version/domain is still necessary. Binary or base64 serialization would be a separate explicit protocol choice. With hex retained, payload cost is `2 * len(E)` plus envelope/JSON overhead; that overhead remains even when the compressed frame is small.

This corrects Task 7.1's blanket statement that compression necessarily changes media identity: a representation can change while its decoded original SHA-256 stays fixed. Existing `validate_admission_certificate(..., media_bytes=M, ...)` already verifies original bytes against content hash and technical evidence. New block validation must decode before calling that logic. Originality, deduplication, and certificate-to-submission uniqueness must continue using original H and the submission/certificate identities, never the codec bytes or encoded size.

### Producer choice versus deterministic compression

Two policies are possible:

- **Identical encoder output required:** mandate codec implementation/algorithm details, level, framing, metadata, and tie-breaking, then have validators reproduce output. This makes one representation per media/profile, but adds re-encoding CPU and tightly couples consensus to encoder behavior and upgrades. A library version/level label alone is insufficient to specify unique output.
- **Producer-selected representation, deterministic validation (recommended):** a producer chooses identity or an allowed compressed frame and commits it once. Validators check the selected profile, exact frame bytes, limits, decoded length/hash, technical evidence, and certificates. They do not recompress to decide validity or demand the locally optimal encoding. A producer setting/encoder update can change proposed block bytes without changing what validators accept, provided its output remains in the same profile.

Canonical here means the accepted block's serialization is unambiguous, not that every producer must generate the same compressed frame from the same M. Two allowed encodings of M may have different block hashes and the same H. That is permitted candidate variation, not ambiguous hashing of one block. Once accepted, re-encoding would create a different block and break descendants/finality; persist, sync, and export the exact E. Admission uniqueness must prevent earning a second accepted-media reward merely by changing encoding. Peer message IDs/HMACs and finality signatures cover the exact new representation/hash, not a validator's re-encoded copy.

Producer policy should prefer compressed mode only when the **complete serialized envelope** saves a chosen margin; otherwise use identity. Keep that optimization threshold as producer guidance. Consensus can impose simple objective encoded-size bounds (proposed: compressed payload no larger than original, both capped) without requiring proof of optimal compression. Whether identity mode remains valid for compressible content must be explicit; this proposal says yes. Therefore worst-case capacity/economic planning must include identity-mode traffic, not assume every producer maximizes savings.

### Codec profile and resource contract

Task 7.2 should specify one registry entry per decodable profile, with identity required. Consider a restricted Zstandard frame as a candidate and compare with a precisely framed DEFLATE baseline before selection. No codec/library has been installed or benchmarked here. Frame format, library release, and compression level are different concepts: pin tested builds operationally, but define protocol acceptance by the format and constraints, not by a producer's claimed library version.

A Zstandard profile would need explicit restrictions because the format permits frame options, dictionaries, and concatenated frames. RFC 8878 documents those features and memory-exhaustion risks; the chain should initially require a single bounded frame, no dictionary, no skippable frames or trailing bytes, a required content size matching `original_length`, and a defined checksum policy. These are proposed chain restrictions, not defaults guaranteed by any library. [RFC 8878, frame format and security](https://www.rfc-editor.org/rfc/rfc8878.html#section-3.1). DEFLATE has its own framing decisions and encoder tradeoffs, so “zlib” without a format/profile is insufficient. [RFC 1951, compression format](https://www.rfc-editor.org/rfc/rfc1951.html).

All nodes in the launch protocol must decode every allowed profile. Peer capability checks identify incompatible nodes; negotiation must not allow node-specific consensus codec support. Future encoder improvements within the existing profile need not change consensus, but adding a codec or widening accepted decoder features requires a protocol upgrade. Keep decoding support for all history of the **newly launched** network for its full retention lifetime. The permission to discard prelaunch v1/v2 history does not remove that future obligation.

Validation order and limits proposed for the new contract:

1. Bound HTTP/page/body bytes and encoded text length before allocating/decoding JSON byte tags. Enforce exact canonical schema, supported version/codec, block-size budget, and actual encoded payload length. Compute/check the block commitment over E without decompression where possible; this alone does not prove validity.
2. Check `original_length` against an absolute accepted-media cap independent of compression ratio. Start evaluation with today's 262,144-byte accepted cap and 524,288-byte canonical-block budget; exact budgets and serializer must be frozen in 7.2/7.3. The block budget includes certificate/metadata overhead, so a payload at its own cap need not fit.
3. Reject unsupported frame features and oversized windows before allocation. Decode with streaming output enforcement; stop at the declared length plus a one-byte overflow probe, require exact end-of-frame/input consumption, and reject truncation, extra frames, missing data, or hash mismatch. Do not trust a claimed length or codec checksum instead of enforcing actual bytes and SHA-256.
4. Verify M is the accepted canonical sequence, original hash/length and technical evidence match, then run certificate/signature/reviewer/native-transaction and normal chain validation. Apply image-decode frame/pixel limits separately from storage decompression limits.
5. Bound decoder window, output, frame count, memory, and aggregate page/block work by objective protocol rules. An expansion-ratio ceiling, if added, must be identical across nodes and benchmarked; absolute output/window caps remain essential and avoid rejecting harmless highly repetitive text solely for its ratio. Exact numeric window/work limits remain open, not assumed implemented.

Machine-local timeout/RAM pressure must not make a structurally valid block consensus-invalid on one node and valid on another. Local watchdogs can abort/defer processing or disconnect a peer, but cannot redefine acceptance. Require a bounded profile and test its worst-case cost; a wall-clock timeout is operational protection, not a consensus rule. Bounded queues/concurrency and bounded decompressed caches must also protect initial sync and media downloads.

## 5. Compatibility, reset consequences, and local storage boundaries

### Explicit prelaunch changes

Current code is not compression-ready: `Block.consensus_payload_v1` requires raw media, `BlockValidationService.validate_protocol_v1_payload` requires `media_bytes`, `media_integrity` accepts only versions 1/2, and `download_block_media` reads `block.media_bytes` directly. Those are implementation seams, not reasons to retain v1/v2. `protocol_v1.py` hardcodes protocol domains/network aliases; genesis, policies, peer envelopes, and export validation also pin current identities. A global constant bump alone is insufficient.

For the next launch, recommend a fresh, explicitly identified network/genesis and new block/protocol version from height zero, rather than an activation height within the disposable development chain. Exact numeric versions and network name are a Task 7.2 decision. The genesis should commit to the launch rules or their immutable digest, including encoding profiles and limits, and retain its complete media bytes in either an explicitly specified identity or compressed encoding. Merely deleting a database and recreating the same hardcoded genesis does not establish a new network identity. The existing `protocol_v1_genesis.py:canonical_public_testnet_v1_genesis_hash` and literal hash would require new reviewed fixtures/specification for the new genesis.

| State/object | Consequence of reset or new encoding/network | Required disposition before launch |
| --- | --- | --- |
| Canonical blocks, descendants, finality | New payload/domain/genesis changes block identities; old height/hash attestations cannot certify new history. | Rebuild launch chain and collect new finality evidence. Do not patch or re-sign old evidence implicitly. |
| Original media hash | H stays identical only if accepted original M stays identical, regardless of encoding. | Keep SHA-256 semantics and text-acceptance rules explicit; a new original produces a new H. |
| Submitter attestations and votes | Compression alone need not change their original-content binding. Network/protocol/domain/policy changes alter signed messages; votes can also reference old reviewer block hashes. | Reissue affected attestations/votes and recreate certificates under launch rules. Old bytes may verify cryptographically yet still be inapplicable to new state. |
| Admission/originality certificates | Certificate IDs/digests commit to signed evidence, policy and chain references; existing exact schema/version checks reject arbitrary edits. | Rebuild from valid new evidence. No assumption that old certificates survive a reset, and no need to discard encoding-independent H semantics. |
| Database/schema and snapshots | Old section JSON, relational claims, evidence indexes, finalized rows, and export/genesis metadata describe the old network. | Select clean initialization or an explicit audited offline migration. Archive old snapshots; reject wrong-network/protocol imports by default. An old backup is not a valid launch snapshot. |
| Balances, rewards, transfers/nonces, submissions/reviewer state | Resetting history can remove all these states and invalidate eligibility references. Mempool/outbox/replay records can contain stale work. | Define initial balances/reward pool and any explicit carryover; clear or migrate dependent state atomically. Identity keys/addresses need not change, but balances and approvals do not carry automatically. |
| Network and clients | Old peers/bootstrap config, wallet sessions/challenges, signed transaction domains, UI expectations and HMAC messages can target old state. | Coordinated protocol/network/genesis handshake and client/config update; isolate old peers, prevent replay, and initialize fresh launch replay/nonce state. |

The reset disposition must include caches, submission files, outboxes and derived reviewer/originality/dispute indexes alongside the main DB. Old media files may be retained as untrusted local imports only after new validation, not treated as already accepted on the new chain. Existing v1/v2 read support can be kept for an offline archive if useful; it is not a launch gate. No reset/migration is performed by Task 7.1A.

### Storage, indexes, API, and snapshots under C

Persist the exact canonical descriptor/E with block header, certificate and original H in authoritative blockchain storage. A normalized SQLite per-block record with a BLOB for E is a proposed improvement over a monolithic `storage_sections.chain` JSON array: it avoids hex-at-rest overhead and whole-chain JSON rewrites. Canonical export/wire serialization must reproduce the same committed block from those rows. The media BLOB is part of canonical block persistence, not a dispensable cache or external media reference; transactions must commit header, payload and claims together. Optional local wrapping must recover E exactly, not just some re-encoding of M.

Index block hash/height and original content hash, submission/certificate uniqueness, and relevant finality references; payload bytes need no search index. Originality/perceptual/OCR indexes are derived from M, not E. Rebuild them after reset/reorg as required. Retain finalized canonical payloads; branch retention and cleanup may vary locally, but must not orphan retained canonical blocks. Preserve the existing finality/fork-choice safety properties within the new network.

In the new schema remove the redundant `meme.encoded_image` copy from persisted/synchronized blocks; generate a compatibility view only if a client needs one. Keep any decompressed cache optional, bounded, and rebuildable from the chain. Do not rely on deleting the canonical payload after caching or on any media URL for reconstruction. Further local compression should target measured metadata/page/archive overhead, rather than automatically wrap every encoded frame.

Block sync and versioned snapshots/export must carry E and its descriptor exactly; importing and restarting must verify the new hash/original-byte contract. Media-download APIs should return M with its original MIME and SHA-256 headers, after verification, without exposing a storage codec as the image MIME. A canonical encoded-block endpoint has different semantics from the original-media endpoint. Content submission/admission continues to validate original media; canonical compression must not accidentally authorize arbitrary compressed archives as an accepted MIME.

Snapshot schema/launch identity checks in `storage_tools` and `storage_migration` must change explicitly. Design a consistent transactional backup of the new authoritative rows and format/limit metadata; raw file copying an active SQLite file is not a substitute for a consistent snapshot. Restore must work with the cache absent and must reject missing/corrupt canonical payloads, unsupported encoding, and wrong launch identity. Compression gains never remove the need for bounded chain pages, resume points, and incremental validation/persistence.

## 6. Reproducible benchmark design (proposal only)

### Corpus requirements

Create a manifest-controlled corpus with immutable SHA-256, MIME, source/license/provenance, and declared size for every accepted type: text, JSON/metadata represented as accepted `text/plain`, source code represented as accepted `text/plain`, PNG, JPEG, GIF, and WebP.  Include text/code that are low-, medium-, and high-entropy; minified and pretty JSON; photographic and synthetic/raster images; animated and still GIF/WebP where policy permits; boundary-sized valid samples; and already-compressed/near-incompressible samples.  Do not treat a filename extension as evidence of type: run `validate_media_bytes` and record its accepted canonical bytes.

The corpus must not include unaccepted archive/executable/script types as normal workload samples; they belong only in negative/resource-limit tests. Source-code examples with a rejected script/active-content prefix must be labeled rejected, not counted as newly accepted MIME types. Files beyond the accepted-media limit belong in rejection measurements, not compression-ratio aggregates. The corpus is not created by Task 7.1A.

### Harness and measurements

For each corpus item and candidate codec/scope, run isolated warm-up plus at least a documented number of repeated cold/warm trials on a declared host/OS/Python/library build.  Record raw samples and machine metadata, not only averages.  Use a fixed harness that:

1. validates input through `validate_media_bytes` and records accepted bytes/hash;
2. compares A against B/C using the same original media, representative certificate/metadata sizes, and clearly labeled old-format baselines versus proposed new-format blocks;
3. measures compression and decompression with monotonic high-resolution timing;
4. verifies decoded bytes equal accepted M byte-for-byte and original H matches; for A check unchanged old block hashes, and for B/C verify the new block hash commits to E and survives persistence/transfer exactly (the current `verify_media_block` must be adapted before it can validate the new format);
5. persists/reloads the supported backends, exports/imports exact canonical E, measures artifact sizes, and tests restart, paged initial sync and original-media download with the cache deleted; and
6. records failures, peak resident memory where the platform can provide it, compressed/decompressed byte counts, and storage component sizes.

Report separately: compressed payload ratio `compressed/original`; expansion `decompressed/compressed`; compression and decompression median/p95/max time; raw accepted bytes; canonical block serialization bytes; physical SQLite database plus WAL/journal size after checkpoint; JSON/export/backup size; content-cache size; metadata/index/table overhead; and total node state.  Never call an estimated future value “measured.”

Also measure percentage expansion `(len(E) - len(M)) / len(M)`, encoded-envelope overhead, raw-fallback frequency, peer bytes including certificates, and cold initial-sync elapsed time/peak RAM/CPU. Separate codec-only savings from removing the compatibility base64 copy or switching hex-at-rest to BLOBs. Record steady-state DB size after a controlled checkpoint and compaction separately from transient WAL/rollback/journal peaks; use before/after isolated databases and table/index page accounting where available. Vary chain length and batch size to expose monolithic section rewrites, not only one-block inserts. Exercise storage/admission/status updates and reorgs as well as append-only growth. Existing compressed image formats may produce little or negative additional saving; that is a hypothesis for these measurements, not an established result.

For three-year economics, keep a parameter sheet separate from measurements: blocks/day by MIME mix, median/p95 accepted bytes, expected cache policy, chain retention/replication factor, storage price per GB-month, backup copies, bandwidth/electricity/CPU assumptions, and growth rate.  Calculate low/base/high scenarios from measured per-block physical deltas.  Publish equations and assumptions; do not extrapolate from a single image or codec microbenchmark.

For example, let `N[t,m]` be assumed accepted blocks in month t and media class m, and `d[m]`, `w[m]`, and `cpu[m]` be measured marginal disk bytes, wire bytes, and validation CPU time. Model `state[t] = initial_state + sum(k<=t,m) N[k,m]*d[m] + indexes[t] + bounded_cache[t]`; account for measured index growth without counting it twice in d. Three-year storage cost sums `state[t] * price_per_byte_month[t]` for months 1–36, plus separately specified backup retention, sync/egress, CPU, and electricity costs. Track cumulative canonical bytes and a complete initial-sync replay separately from incremental live traffic. Include pessimistic identity-mode traffic and metadata-heavy certificates. Compression reduces a growth coefficient; full-history Model A still grows with every accepted block and provides no permission to prune original media.

### Reusable infrastructure

- Validation and accepted-byte canonicalization: `media_technical_validation.validate_media_bytes`.
- Hash/integrity checks: `media_integrity.verify_media_block`, `reconstruct_media_bytes`, `validate_current_media_chain_records`.
- Canonical serialization: `protocol_v1.encode_canonical_bytes`, `Block.consensus_payload_v1_bytes`, `Block.calculate_hash_v1_from_dict`.
- Persistence and portability: `JSONStorageBackend`, `SQLiteStorageBackend`, `storage_tools.build_export_snapshot` / `import_storage`, and `storage_migration.migrate_json_to_sqlite`.
- Existing benchmark pattern: `scripts/milestone_6_task_6_3_media_validation_benchmark.py` (timing/reporting only; it is not a compression benchmark).
- Existing focused tests: `tests/blockchain/test_protocol_v1_block_format.py`, `tests/test_milestone_6_task_6_9_media_integrity.py`, `tests/storage/test_sqlite_storage_backend.py`, `tests/storage/test_storage_tools.py`, and peer chain/block API tests.

Pillow is already used by the technical validation benchmark/test paths; no dedicated chain-compression library is currently pinned in `requirements-core.txt`. A standard-library DEFLATE harness and a separately approved Zstandard implementation are candidates for later benchmark work, not installed dependencies or selected protocol codecs here. Existing hash/integrity helpers can be reused for original-byte semantics, but their current block-version/schema checks must be versioned or replaced for B/C. Current golden vectors describe the development protocol, not the proposed launch format.

## 7. Proposed implementation areas and test requirements

These are candidates for Tasks 7.2–7.8, not changes made here:

| Area | Likely modules | Required tests |
| --- | --- | --- |
| Canonical encoding and decode limits | proposed `media_encoding.py` / new protocol helpers; `block.py`, `media_integrity.py` | every accepted MIME round-trip, identity mode, multiple valid E values for one M with equal H/different block hashes, malformed/truncated/concatenated frames, hidden trailing data, large windows, claimed-length mismatch, bad hashes, unsupported versions |
| Protocol and evidence | `protocol_v1.py`, new versioned counterparts, `admission_certificate.py`, `protocol_v1_submitter_attestation.py`, `dual_review.py`, `protocol_v1_finality.py`, `protocol_v1_genesis.py`, policy modules | new launch vectors and independent decoder agreement, preserved original-byte certificate bindings, wrong-network/evidence/reference rejection, fresh finality binding, correct genesis commitment |
| Production/acceptance | `services/block_production_service.py`, `services/block_validation_service.py`, `blockchain.py` | no duplicate rewards via encoding change, exact serialized-block and decoded-byte caps, native-transaction validation unchanged in meaning, no local recompression requirement, no hostname/clock/resource-dependent validity |
| SQLite authoritative persistence | `storage.py`, proposed per-block BLOB rows and storage adapter | atomic header/payload/claim persistence, interruption/recovery, restart without cache, bounded incremental reads/writes, different local layouts yield identical canonical blocks |
| JSON/export/backup | `storage_tools.py`, `storage_migration.py`, backup runbook, reset tooling | new-format exports/imports preserve E/H/block hash/certificates/finality; missing payload/corruption/old-network rejection; consistent backup and restore; explicit archive/reset path |
| Node media/cache behavior | `services/content_coordination_service.py`, `content.py`, `originality.py` | byte-exact reconstruction after cache deletion, original-hash/perceptual index behavior, optional bounded cache eviction, no external dependency |
| API and sync | `api_routers/public_chain.py`, `api_routers/peer.py`, `api_runtime.py`, `peer_sync.py`, peer services | versioned wire transfer of exact E; exact original-media response; page/body/concurrency limits; resumable initial sync; matching-protocol nodes with different local storage settings interoperate |
| Reorg/finality | `services/canonical_reorg_service.py`, `services/finality_service.py`, storage claims/indexes | retained finalized identities and payloads protected, detached branch handling and rebuildable indexes correct, interrupted reorg atomicity |
| Observability/economics | a new benchmark script/docs only | stable manifest, reproducible reports, component-size accounting, scenario math tests |

For the new launch, freeze **new** block/genesis/encoding/signing vectors and test decoding across supported platforms and at least two independent compatible decoder builds/implementations. Mutating E or any descriptor must change/reject the block commitment; changing decoded M while retaining H must fail. Test high-ratio text within caps, tiny/empty/malformed inputs, resource-bound violations, repeated invalid requests, and decompression-cache memory pressure. Do not require all valid encodings of M to have one block hash. Keep decoder support stable for all accepted postlaunch blocks. Legacy v1/v2 vectors are useful comparison fixtures or offline archive checks; preserving runtime acceptance is optional after an explicit reset.

## 8. Recommended sequencing for Tasks 7.2–7.8

1. **7.2 — Revised protocol and launch decision record:** specify the C boundary, new envelope/hash semantics, producer-selected encoding, initial profile candidates and resource rules, serializer/size accounting, original-byte attestation semantics, and new network/genesis/reset disposition. Define benchmark acceptance criteria and provisional numeric limits. Replace the earlier restriction against consensus serialization changes. Codec/profile/limit selection remains provisional until 7.3; no reset is executed just by accepting the design.
2. **7.3 — Benchmark harness, corpus, and protocol-profile freeze:** measure A/B/C with original-hash integrity checks, every accepted MIME, producer choice/raw fallback, adversarial decode costs, full stored/wire/snapshot overhead, and three-year scenarios. Select one codec/profile or identity-only, freeze exact limits and golden vectors, and review the launch contract before production implementation.
3. **7.4 — Canonical media encoding and validation:** implement bounded decode, new block serialization/hash, original H semantics, evidence adapters, producer policy, and new-version/genesis definitions. Preserve originality/uniqueness, rewards, fork-choice, and finality rules in meaning. Run vector and adversarial tests before connecting to a new network.
4. **7.5 — Authoritative storage, snapshots, and reset/migration tooling:** persist E atomically, remove canonical duplicate media copies, support self-contained new snapshots/restore, and rehearse the explicit reset or offline migration in isolated locations. Add optional local improvements only with measured value; v1/v2 runtime compatibility is not a gate.
5. **7.6 — Network/API and initial-sync integration:** transfer exact E, serve verified original M, enforce protocol/genesis handshake and bounded resumable sync, update client media handling and telemetry. Nodes may differ in local storage/cache settings while sharing all consensus codec rules.
6. **7.7 — Adversarial, interoperability, and recovery validation:** fuzz codecs/frames/lengths, compare decoder implementations/platforms, test wrong-network/replay/certificate cases, cache-free recovery, reorg/finality/atomicity, and full initial sync. Validate that differing producer encodings do not bypass duplicate-media or reward rules.
7. **7.8 — Prelaunch release and coordinated cutover:** review benchmark economics and protocol vectors, approve exact reset/carryover steps, archive development state, initialize the new network with updated clients/config/signing domains, and rehearse/verify rollback and backups. After launch, treat the accepted decoder/format as a long-lived consensus commitment.

These are revised dependency-based proposals for Milestone 7, not claims that later task specifications have already been approved. `docs/task-roadmap.md` and `docs/native-wallet-architecture.md` also contain older “7.2–7.8” labels for native-wallet work; those are not a compression task specification. Reconcile the next task prompt with this sequence. Only Task 7.1A is performed here.

## 9. Open decisions and blockers

Task 7.1A is ready for review. **Task 7.2 can proceed as revised architecture/specification work; it cannot proceed unchanged as a local-only storage implementation.** Development reset permission removes the historical-compatibility blocker. Remaining decisions belong in 7.2/7.3 rather than being invented measurements or reasons to retain A:

- Exact launch block/protocol/network/genesis identity and which old state, if any, is explicitly carried forward; fresh signing/reviewer/finality evidence and replay isolation.
- Codec/profile, checksum/framing restrictions, encoded byte representation, numeric output/window/aggregate-work budgets, and measured acceptance criteria. Deterministic decoder validation with producer choice is the recommendation; no consensus optimal-compression test.
- Exact encoded/canonical versus original/decompressed size accounting and any fees/admission charges. Avoid pricing only compressed bytes while ignoring bounded decode/retention costs; rates and workload forecasts require a separate measured economics decision.
- New database row/BLOB layout, export schema, duplicate compatibility-field removal, consistent backups, and reset/migration/rollback operations. Optional local compression must preserve E exactly and must not become an external reconstruction dependency.
- Full-media retention funding and growth assumptions; compression cannot eliminate ongoing Model A storage growth or the need for bounded sync and retrieval.

## 10. Task 7.1A verification and scope record

Inspected current block production/serialization/validation, independent media integrity, admission and signing bindings, genesis/network/domain constants, SQLite section persistence, peer/public retrieval, peer chain fetch, and snapshot validation. Function/file references above identify the implementation seams; RFC references describe codec candidates, not a selected implementation.

Focused existing checks run against HEAD `2924faea02ac607ab8a4b4242e92f43042027375`:

```text
.\.venv\Scripts\python.exe -m pytest \
  tests/test_protocol_v1.py::test_bytes_are_deterministic_and_round_trip \
  tests/test_protocol_v1.py::test_domain_separation_changes_bytes_and_hashes \
  tests/test_protocol_v1_golden_vectors.py::test_canonical_serialization_vectors_match_runtime \
  tests/test_protocol_v1_golden_vectors.py::test_block_vectors_match_runtime -q --tb=short
Result: 4 passed.
```

These verify today's serialization/hash foundation; they do not validate an unimplemented new codec. The earlier conversation reported JPEG technical-validator failures during Task 7.1; this reevaluation neither reproduces nor diagnoses their cause and does not treat them as evidence that the fixture itself is malformed. A general file inventory hit an access-denied temporary test directory; targeted source/document inspection completed without needing it. Documentation verification: `git diff --check` passes; the only tracked working-tree change is this report. No dependencies, benchmark corpus, production code, chain/database state, or committed Git history are changed by Task 7.1A.
