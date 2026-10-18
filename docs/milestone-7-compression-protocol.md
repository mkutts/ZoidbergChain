# Milestone 7 Task 7.2 — Canonical Media Compression Protocol Specification

Status: proposed protocol contract, ready for design review; not implemented or activated. Task 7.5 selects identity/1 plus zstd/1 in the [Baseline Compression Codec and Security Contract](milestone-7-codec-security-contract.md), which governs exact framing, decoder requirements and remaining activation gates. Launch limits and complete-block overhead remain unresolved. No performance results are claimed by this document.

Date: 2026-10-18. Baseline: branch `Compression-State-Bloat-and-Node-Economics`, HEAD `727a993eb81005a0b81d5079f2c7d70d93ae3ac6` (`Milestone 7 Task 7.1A: revise canonical media compression architecture`), clean worktree before this task. Task 7.1A is committed; no repository-state mismatch was found.

This document specifies the next development-network contract. It does not amend the running v1 protocol or authorize a reset. MUST, MUST NOT, SHOULD, and MAY describe requirements for the future implementation. Task 7.5 supersedes historical codec-selection **benchmark gates** and the provisional size/state conclusions below; unresolved release gates are not implementation defaults. A, B and C denote respectively the future original-media, encoded-media and complete-canonical-record caps; their numeric values must be frozen in launch policy before activation.

## 1. Protocol contract and decisions

ZoidbergChain remains an independent Layer 1 using MODEL A. Every accepted media object MUST be recoverable byte-for-byte from canonical blockchain data alone, without a media service, content cache, external dictionary, earlier media block, or local compressor configuration.

Let `M` be the original **accepted** media bytes, `E` the stored encoding, and `H = lowercase_hex(SHA-256(M))`. For images, M is the exact accepted upload byte sequence, including accepted container metadata. For text, M is UTF-8 after the existing admission canonicalization, not the pre-canonicalization upload. Compression MUST NOT transcode images, strip metadata, resize, change animation, normalize text again, or substitute an equivalent rendering.

The decisions are:

1. Introduce protocol version **2**, non-genesis media block version **3**, and media encoding version **1**. These are separate discriminators: today's admission block version 2 still uses protocol version 1.
2. Replace the old media fields with one `media` object containing E and its complete descriptor. Extend the remaining admission block schema rather than replace transaction, reward, originality, or finality semantics.
3. Hash the actual chosen E and every descriptor field in the block commitment. Original-media identity remains H, independent of MIME, codec, frame, compression level, or block identity.
4. Require the `identity/1` profile and select `zstd/1` as the sole initial compressed profile under the Task 7.5 security contract. Admission requires the fixed launch registry and closure of all activation gates; selection does not activate either new protocol path in production.
5. Allow a producer to choose E once. Validators MUST decode and verify it, and MUST NOT recompress to decide validity. There is no global unique compressed representation of M.
6. Make “compress only when smaller” a producer policy. Absolute size, frame, output, and profile restrictions remain consensus rules.
7. Preserve exact E through storage, synchronization, exports, backups, and reorganization. Optional local physical compression must recover E exactly, not merely another encoding of M.

No production code, dependencies, corpus, benchmarks, chain state, commits, pushes, merges, resets, or deployments are part of Task 7.2. This task's instruction that **Task 7.4 performs compression benchmarks** supersedes the tentative 7.3/7.4 labels in the Task 7.1A sequencing proposal; no other later task is renumbered here.

## 2. Verified implementation baseline

These are observations at the baseline HEAD, not claims that the proposed contract already works:

| Concern | Inspected implementation and consequence |
| --- | --- |
| Serialization/hash | `protocol_v1.py:canonical_json_text`, `encode_canonical_bytes`, `build_domain_envelope`; `block.py:consensus_payload_v1`, `consensus_payload_v1_from_dict`, `calculate_hash_v1`. Current media is a hex-tagged bytes object. The block envelope commits raw media and metadata; its network/domain use protocol v1. |
| Object parsing | `Block.from_dict` and the current payload builders can supply defaults, normalize numeric values, and omit nulls. They cannot be reused as permissive v3 wire parsers. Current `meme.encoded_image` is an extra base64 copy outside the hash. |
| Production/admission | `services/block_production_service.py:build_candidate` uses accepted raw bytes, creates the compatibility copy, and estimates size. `services/block_validation_service.py:validate_protocol_v1_payload`, `validate_admission_block`, `validate_candidate`, `validate_chain` expect versions 1/2 and raw media. The policy's exact serialized-block limit needs enforcement at every acceptance path. |
| Accepted-byte identity | `content.py:canonicalize_text_content`, `resolve_declared_payload_hash`; `media_integrity.py:reconstruct_media_bytes`, `verify_media_block`. Current integrity requires raw embedded bytes to match both `media_hash` and `content_hash`, plus block and admission bindings. |
| Evidence/signatures | `admission_certificate.py:build_admission_certificate`, `validate_admission_certificate`; `protocol_v1_submitter_attestation.py`; `dual_review.py:vote_payload`, `verify_vote_record`. Certificates bind original SHA-256, technical evidence, signatures, policy, and reviewer references. The certificate is a digest-bearing evidence bundle, not an independent producer signature. |
| Media safety | `media_admission_policy.py` and `media_technical_validation.py:validate_media_bytes`, `validate_technical_evidence`. Accepted images/canonical text have 262,144-byte caps; canonical non-genesis blocks have a declared 524,288-byte cap. Generic upload configuration is not the accepted-media consensus limit. Evidence verification is not the same operation as rerunning an isolated image decoder. |
| Voting/finality | `protocol_v1_finality.py`, `services/finality_service.py`; finality signatures bind validator, height, block hash, and network/domain. `CanonicalReorgService._reconcile_finality` refuses to detach persisted quorum-finalized history. Older protocol documentation describing depth-only finality does not describe all current behavior. |
| Network/retrieval | `api_routers/peer.py:peer_chain_blocks`, `api_routers/public_chain.py:chain_blocks`, `download_block_media`; `services/peer_chain_sync_service.py:fetch_blocks`, `sync_peer`; `peer_sync.py`. Current chain endpoints select the entire suffix and sync fetches from height 0. Declared page limits are not evidence of implemented pagination. Retrieval verifies and returns raw original media today. |
| Persistence/portability | `storage.py:SQLiteStorageBackend._load_sections_from_connection`, `_save_sections_to_connection` store chain JSON in `storage_sections.json_data`; no authoritative per-media BLOB table exists. `storage_tools.py` and `storage_migration.py` call current-media validation. Their version filtering must not silently skip v3 records. |
| Originality/reorg | `originality.py` indexes SHA-256 of reconstructed original media, alongside decoded-image/OCR features. `services/canonical_reorg_service.py:rebuild_document` reconciles claims, evidence references, and finality. Those indexes and references must follow the winning chain, not the codec. |

The existing v1 specification and golden vectors continue to describe the old network. This proposed v2 contract intentionally differs and requires new vectors and new runtime paths.

## 3. Canonical media representation

Every non-genesis v3 media block MUST contain exactly one `media` object with these exact keys; all are required, including in identity mode:

| Field | JSON type | Validation/meaning |
| --- | --- | --- |
| `encoding_version` | integer | Exactly `1`; boolean, string, float, and null are invalid. |
| `codec_id` | string | Exact case-sensitive identifier in the network registry; `identity` is mandatory. No aliases or auto-detection. |
| `codec_version` | integer | Positive registry profile version; exactly `1` for identity. This is a protocol decoding profile, not a package release or producer's compression level. |
| `original_size` | integer | `1..A`, byte length of M; 262,144 is a provisional candidate, not a frozen launch cap. |
| `stored_size` | integer | `1..B`, byte length of E before base64; B is independently selected. |
| `mime_type` | string | Exactly `text/plain`, `image/jpeg`, `image/png`, `image/gif`, or `image/webp`, subject to the launch admission policy. Lowercase ASCII, no parameters, spaces, or alternate spellings. |
| `original_sha256` | string | Exactly 64 lowercase hexadecimal characters, H; no `0x` prefix. |
| `payload` | string | Strict standard padded base64 of E, as specified below. It is never a URL, raw text, hex object, or decoded image. |

There is no arbitrary `parameters` object in encoding version 1. Any decoding-affecting choice MUST be fixed by `(codec_id, codec_version)` or be an explicitly permitted, bounded in-frame field committed through E. Encoder level, library name/version, thread count, and timestamp MUST NOT be separate descriptor fields. Changing required parameters/profile semantics requires a new profile version and network activation, not a new local default.

For identity, E MUST equal M, and `original_size == stored_size`. Empty media is invalid for all profiles. For compressed mode, decoding E under the selected profile MUST yield M. A descriptor is not valid just because its declared hash and sizes look valid.

Example of the complete canonical media object for accepted text `hello` (five bytes, no newline), shown in canonical key order:

```json
{"codec_id":"identity","codec_version":1,"encoding_version":1,"mime_type":"text/plain","original_sha256":"2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824","original_size":5,"payload":"aGVsbG8=","stored_size":5}
```

This is an illustrative identity serialization, not a valid block, admission certificate, benchmark sample, or compressed-profile golden vector.

### 3.1 Byte encoding and decoding

`payload` uses the alphabet `A-Z a-z 0-9 + /` with the required terminal `=` padding, no whitespace/newlines, no URL alphabet, and no data-URI prefix. Its ASCII character count MUST equal `4 * ceil(stored_size / 3)` and MUST be at most `4 * ceil(B / 3)` before allocation/decoding (349,528 for the provisional 256 KiB B). Padding MUST be minimal and unused pad bits zero. Strict decode followed by exact base64 re-encode equality is required; permissive library decoding alone is insufficient. The decoded length MUST equal `stored_size`.

The schema itself declares the string's meaning, so a tagged bytes object adds no information here. Base64 is selected over today's hexadecimal to limit wire expansion and leave room under the existing block budget. That arithmetic is not a measured compression gain. Original and stored sizes are intentionally distinct: each bounds a different processing stage.

### 3.2 Replacement and compatibility views

The v3 canonical payload MUST NOT contain old top-level `media_bytes`, `media_hash`, `content_hash`, `mime_type`, or `content_id`, or a `meme` compatibility object. It also MUST NOT contain a second original text/base64 media copy. The following are derived application/API views only:

| Existing name | v3 authoritative source |
| --- | --- |
| `media_hash`, `content_hash`, `byte_hash` | `media.original_sha256`; these aliases always mean H, never a hash of E. |
| `media_bytes` | Verified reconstructed M; obtaining this view may require bounded decoding. |
| `mime_type` | `media.mime_type`. |
| `content_id` | Existing derivation `lowercase_hex(SHA-256(UTF8(H)))[:32]`; convenience key, not authoritative media identity. |
| Media length | `media.original_size`; stored length is a separate reported value. |

Existing certificate/attestation/evidence fields named `content_hash` or `raw_media_sha256` remain in their signed/digested structures and MUST equal H. Those repetitions authenticate separate evidence and are not alternate authoritative metadata. Compatibility API views MUST be labeled as views and MUST NOT be parsed as canonical v3 block records.

## 4. Exact canonical serialization and block commitment

### 4.1 Canonical JSON function C

For this contract, `C(x)` is the UTF-8 encoding, without BOM or final newline, of canonical JSON:

- Object keys are unique strings sorted by Unicode scalar value, lexicographically; arrays preserve order. Schema keys are ASCII. Duplicate keys MUST be rejected while parsing, before dictionary construction discards them.
- No insignificant whitespace. Separators are `,` and `:`. Strings preserve Unicode scalar values without normalization; reject invalid UTF-8, overlong UTF-8, and lone surrogates.
- Escape quote and backslash as `\"` and `\\`; use `\b`, `\t`, `\n`, `\f`, `\r` for their respective control characters, and lowercase `\u00xx` for other U+0000..U+001F values. Emit all other scalars directly, including `/` and U+2028/U+2029. This matches the existing serializer's string output on valid scalar strings.
- Integers use base-10 ASCII with no leading zeros, plus sign, exponent, decimal point, or negative zero. Values must be within `[-9007199254740991, 9007199254740991]` and their field-specific ranges. Booleans are not integers. Native JSON numeric floats, NaN, Infinity, and implicit numeric conversions are invalid.
- Decimal-valued fields use canonical finite decimal **strings**: no exponent, plus sign, surrounding spaces, unnecessary leading zeros, trailing fractional zeros, or negative zero. `0`, `12`, and `0.25` are examples. Byte construction never accepts floats; ledger/tally values must already be in their canonical scalar form under the existing normalization rules. This contract does not introduce new tally rounding or monetary arithmetic.
- `true`, `false`, and `null` exist only where a referenced nested schema explicitly permits them. There is no generic null-dropping transform. Opaque binary types are not valid JSON inputs; E is represented only by `media.payload`.

Canonical standalone records MUST equal their reserialization with C. A JSON page/export container may have transport formatting, but MUST parse without duplicate keys or type coercion and reconstruct exactly the same C(record). Whitespace or JSON string escape choices in such an outer transport are not alternate compression encodings; canonical hashing always uses C. Unknown keys, defaults that create missing required fields, and ambiguous aliases are rejected.

### 4.2 Non-genesis payload P

The v3 payload is a **closed schema**. Its exact required keys are the rows below. The only optional key is `meme_text` under the condition stated below; all other absent or null top-level fields are invalid. No field is inferred from a local submission database.

| Required field(s) | Type and contract |
| --- | --- |
| `block_version` | Integer exactly `3`. |
| `index` | Integer `1..9007199254740991`, exactly predecessor height plus one. |
| `previous_hash` | 64 lowercase hex characters, exact predecessor block hash. |
| `timestamp`, `minted_at` | Nonnegative canonical decimal strings of seconds, preserving existing time-validation semantics. No local receipt time enters P. |
| `transactions` | Ordered array of the existing canonical reward/legacy transaction payloads. Required even when empty; existing economic/signature rules apply. |
| `native_transactions` | Ordered array of existing canonical native transaction records, required even when empty; existing nonce, amount, fee, signature, and ordering rules apply under the new launch context. |
| `transactions_hash` | Required 64-character lowercase hex native-transaction aggregate defined below, including its empty-array value. |
| `miner` | Nonempty canonical public-key identity accepted by the existing miner validator; no trimming/coercion on receipt. |
| `submission_id` | Nonempty exact submission identifier, equal to the frozen certificate. |
| `certificate_id`, `vote_hash` | 64 lowercase hex characters, equal respectively to certificate digest and frozen originality vote-set digest. |
| `creator_wallet` | Canonical wallet identity, equal to certificate creator. |
| `content_type` | Exact `text`, `image`, or `mixed`; text MIME requires `text`, image MIME requires `image` or `mixed`. This retains content/caption semantics, not another MIME authority. |
| `approval_percentage`, `originality_score` | Canonical decimal strings of the existing admission tally values; must agree with the certificate adapter. Compression does not change tally arithmetic. |
| `decisive_vote_total`, `minimum_votes_required` | Nonnegative JSON integers, equal to the admission tally/policy values. |
| `approved_at` | Nonnegative integer; exactly `0` for the current frozen admission semantics, excluding local approval clocks. |
| `reward_type`, `reward_source` | Exact `meme_mining_reward` and `reward_pool`. |
| `reward_recipient` | Existing canonical reward wallet identity, checked against creator/reward eligibility and reward transactions. |
| `reward_amount` | Nonnegative canonical decimal string, equal to the launch reward rule and reward transaction. No compression bonus is introduced. |
| `voter_rewards` | Required array exactly `[]`, retaining the current admission-block prohibition on legacy originality voter rewards. |
| `admission_certificate` | Complete frozen launch-context certificate; nested keys, vote ordering, identities, and validation derive from `admission_certificate.py:validate_admission_certificate`, `_frozen_votes`, `attestation_identity`, and their referenced evidence schemas at the baseline, with the explicit context changes in section 5. Unknown nested keys are not an extension mechanism. |
| `media` | Exact object defined in section 3. |

`meme_text`, when present, is a nonempty caption/OCR/display string distinct from the canonical media object. Preserve it exactly, with the admission caption bounds (at most 1,000 scalars and 4,096 UTF-8 bytes). For `text/plain` it MUST be absent: the text is recoverable from M, so storing it again is unnecessary. Absence is the only “no caption” representation; empty string and null are rejected. Caption text is hash-committed but is not part of media identity.

Non-media nested transaction and evidence formats retain their baseline canonical payload rules, not arbitrary `Block.to_dict()` output. Specifically, legacy/reward transaction payloads use required `sender`, `recipient`, `amount`, `tip`, `payload_size_kb` and `signature` only where the existing transaction schema requires it; absent optional signature remains absent. Native transaction records follow `protocol_v1_native_transfer.py` and the native transaction validator; evidence identities use their existing explicit field selections. Schema-permitted nested nulls remain distinct values. Runtime implementation must publish new-context vectors for these referenced formats rather than copy locally observed fields into consensus data. No compression-specific changes to ledger arithmetic or signature schemes are proposed.

For the retained native aggregate, use `services/native_ledger_service.py:compute_block_native_transactions_hash`: SHA-256 of the ordered native-record array serialized with sorted keys, compact separators and **ASCII escaping**, equivalent to `json.dumps(records, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")` on schema-valid records. This existing nested aggregate preimage is distinct from C's unescaped-Unicode block preimage; do not silently replace it with C. Its empty value is SHA-256 of ASCII `[]`. Compute it from the exact nested records carried in P, preserving schema-permitted nulls. Application `transaction_ids` and `transaction_count` are derived from that array and supplied to existing ledger adapters as needed; neither is an additional canonical field.

Top-level certificate summary fields retained above are equality-checked adapters for existing admission/reward processing. They cannot disagree with the frozen certificate. Removing those additional repetitions would be a separate schema simplification; this task removes duplicated media identity and media byte copies.

### 4.3 Hash preimage and record

For the new network ID `N`, the exact block envelope B is:

```text
{
  "domain": "zoidbergchain/block/v2",
  "network_id": N,
  "object_type": "block",
  "payload": P,
  "protocol": "zoidbergchain",
  "protocol_version": 2
}
block_preimage = C(B)
block_hash = lowercase_hex(SHA-256(block_preimage))
canonical_record = C({"envelope": B, "hash": block_hash})
```

The displayed layout is explanatory; C emits the actual compact bytes. `canonical_record` is the complete portable block format, with exactly `envelope` and `hash`. N occurs once in B, not as an unverified duplicate in P. N MUST equal the configured, frozen launch ID, already in canonical lowercase network-ID syntax. N is a specification variable, not an accepted literal or a fallback to `zoidberg-public-testnet-v1`. Its release value is a launch blocker.

The hash commits to **all of P**, including the base64 representation of every E byte, original and stored sizes, original hash, codec/profile/version, MIME, caption if any, transactions, and complete certificate. Base64 is bijective under strict rules, so this commits to the actual encoded bytes without a redundant `encoded_sha256`. `hash` itself, finality proofs, API URLs, caches, local storage wrappers, and derived views are not in the preimage. The canonical block-size rule counts the **complete canonical_record**, including its hash and envelope; it is not the size of E, an estimate, or a self-referential field.

Unknown protocol, block, encoding, or profile versions MUST fail closed before decoding. Missing versions MUST NOT select a legacy path. Genesis is separately discriminated by `object_type = "genesis"` and its frozen schema, never by a missing media block field.

## 5. Media identity, evidence, signatures, and uniqueness

1. Compute H by hashing M directly, with no MIME prefix, filename, JSON serialization, length prefix, codec header, or domain envelope. SHA-256 output is lowercase hexadecimal. For text, canonicalize at submission before evidence is signed; when validating a block, require decoded M already to be canonical. Never repair it silently.
2. MIME is **not** in media identity. It is in the block commitment and MUST match detected/admission-evidenced type. Identical M has identical H even if a caller tries another MIME. A falsely labeled payload is invalid, not a new media identity.
3. A change to E or any descriptor field changes B's bytes and therefore normally changes the block hash; it can also make the block invalid. Two valid encodings of the same M MAY have different block hashes. Uniqueness applies within the candidate canonical ancestry, not across mutually exclusive forks.
4. Submitter attestations and community originality/admissibility votes continue to commit to H, submission, policy and relevant signed context, not E. Technical evidence MUST bind H, `original_size`, and `mime_type` through its existing hash, length, and detected-type fields. The frozen certificate digest authenticates that evidence bundle and its votes. The block then authenticates the whole certificate and descriptor together.
5. There is no new implicit block-producer signature. Existing native transaction signatures still authenticate transfers. Validator consensus/finality attestations authenticate their existing height/block-hash/validator payload under the new network and signing domain; they transitively authenticate E and all decoding metadata. Community admission votes are not finality votes.
6. Reusing a content signature for another encoding is possible only if **all** its signed bytes/context remain the same. It does not authorize changing a finalized block's E. Changed block hashes require fresh finality signatures. At the reset, new network/domain/policy/reference context requires fresh admission and transfer signatures as applicable; do not transplant old evidence merely because H is unchanged.
7. All exact duplicate/originality indexes use H. Perceptual hashes, OCR/text comparison, and near-duplicate evidence use M or its existing deterministic features, never E. Reencoding cannot earn another mint/reward or evade submission, certificate, exact-media, or reward claims. Validation MUST check these against the candidate predecessor state atomically with acceptance. Existing originality/admissibility thresholds and review authority are preserved.

The launch adopts protocol-v2 domain envelopes for existing domain-envelope objects, including submitter attestations, native transfers, peer messages, genesis, and finality. Their payload meanings and wallet signature mechanisms stay the same. Community review currently uses its own `zoidbergchain/community-review/v2` payload domain; the new launch MUST use `zoidbergchain/community-review/v3`, increment its vote format, and bind N and the new policy digest. The admission certificate format version increments from 1 to 2 and its network/policy bindings change. Its digest remains `lowercase_hex(SHA-256(C(certificate_without_certificate_digest)))`, with the certificate's own version/network fields included. Updated policy/evidence adapters must enumerate their accepted versions; do not infer them from package versions. Policy digests commit the encoding registry and limits so admission and consensus cannot silently disagree.

## 6. Admission, encoding, and resource policy

### 6.1 Codec registry and framing

The launch manifest, committed by the genesis policy/registry digest, maps exact `(codec_id, codec_version)` pairs to immutable decoder specifications and limit profiles. Its entries are consensus data fixed for the network, not a local plugin negotiation. Every validator MUST support every active profile; an unknown codec is rejected even if a local library can decode it. A software update must not silently add an allowed codec.

| Profile | Contract/status |
| --- | --- |
| `identity`, version `1` | E = M; no frame, header, dictionary, or decompression step. Complete now as a specification. |
| `zstd`, version `1` | Selected by Task 7.5; the linked security contract is authoritative for the pinned grammar, one frame, required checksum/content size, no dictionaries, 256 KiB window, 64-data-block ceiling and exact consumption. Not activated; work/state, adapter, conformance and launch-policy gates remain. Level 3 is producer guidance, not a validity rule. |

A future compressed profile MUST define exactly one independently decodable frame per media object, exact end-of-frame/input consumption, and bounded header/window/table/block parsing. Concatenated frames, skippable frames, hidden trailing bytes, archive members, recursion/nested compression wrappers, external dictionaries, cross-block references, and dictionary-fetch hooks MUST be rejected. A profile may use a fixed algorithm constant/table, but cannot require producer-supplied external bytes. If its framing has a content-size field, it must be present and equal `original_size`; if the chosen format has none, exact output counting is mandatory instead. The profile must define whether its in-frame checksum is required, its exact verification, and forbid optional ambiguous variants. H is always checked regardless of checksum.

Valid bitstreams need not be what the default encoder would emit. Decoder acceptance is defined by the profile, not compressor output. No decoder may ignore checksums, recover corrupt streams, accept a prefix, or guess another codec after failure.

### 6.2 Consensus bounds

The following table distinguishes mandatory kinds of bounds from unresolved numbers. Task 7.5 governs the size scenarios and exact-block-overhead gate. Existing production limits remain unchanged; the new launch must not treat the earlier 256 KiB / 256 KiB / 512 KiB proposal as permanent policy. Codec working-state budgets are **not measured safe performance claims**.

| Quantity | Proposed consensus maximum/rule |
| --- | --- |
| Original accepted image or canonical UTF-8 text M | A bytes, nonempty, independently of E. Candidate baseline 262,144; evaluate up to 2,097,152 for images before freeze. |
| Stored E | B bytes, nonempty; reject above cap before codec invocation. Baseline 262,144; evaluate B >= A for identity fallback. |
| Serialized base64 string | `4 * ceil(B / 3)` ASCII characters, plus exact length/padding rules in section 3.1. |
| Decompression output | Exactly `original_size`, at most A. Abort before producing byte `original_size + 1`, including hidden buffered output. |
| Complete non-genesis canonical record | Cap C is unresolved pending measured/bounded mandatory overhead; 524,288 is only the earlier candidate. Count exact canonical record bytes and enforce on every acceptance path once frozen. |
| Codec history window | At most 262,144 bytes, checked from the frame before allocating it; not a substitute for total decoder-state bounds. |
| Codec algorithm working state | 1,048,576 bytes remains a candidate audit target, not an enforceable portable counter established here. Profile accounting and safe decoder implementation are activation gates; RSS/library heap cannot determine validity. |
| Frames per media object | One for zstd/1 with at most 64 data blocks; identity has zero codec frames. |
| Canonical JSON nesting | At most 32 object/array containers on any root-to-leaf path, including envelope and record wrappers. |
| Encoded chain page | At most 64 blocks **and** 16,777,216 application-response bytes including wrapper and proofs; stop at whichever limit is reached first. These are interoperability/transport limits, not alternate per-block validity rules. |

With the earlier 256 KiB media / 512 KiB record candidates, identity occupies 349,528 base64 characters, leaving **174,760 bytes before descriptor/envelope/certificate/transaction overhead**. This does not establish block fit. Task 7.5 requires bounded mandatory overhead and either B >= A with sufficient complete-record capacity, or a deterministic admission fit check before certification. Optional transactions may be omitted; mandatory media/evidence cannot be truncated and local caps cannot be raised. Larger A/B require reevaluating C; no final complete-block cap is selected here.

There is **no expansion-ratio consensus test**. Small compressed text can legitimately have a high ratio. Absolute input/output/window limits and safe state accounting must prevent unbounded allocation; complete defenses against bounded-output CPU attacks remain gated by the unresolved work bound. A compressed frame with `stored_size >= original_size` remains valid if it satisfies every absolute restriction. E may never exceed B, even if a codec normally adds framing overhead; identity is the fallback when it fits.

**Activation gate: deterministic work bound.** Task 7.5 defines structural Zstd limits but leaves a complete work bound unresolved. Before activation, publish either consistent semantic counters/maxima or a reviewed finite algorithmic bound for every accepted and rejection path, verified independently. Input/output/window caps alone are insufficient. Identity has bounded copy/hash work. No unspecified counter or unbounded decoder may be activated; wall-clock time and machine instructions do not define consensus validity.

### 6.3 Existing media safety and local defenses

Compression is a storage encoding, not a new accepted media MIME. Original admission continues to reject archives, executables, scripts/active content, malformed containers, disallowed metadata, and unsupported types according to the versioned media policy. Enforce the existing image bounds on M: width/height 1..4,096, total decoded pixels at most 16,777,216, and at most 60 frames, with every required frame checked. Lossless storage compression does not replace image safety checks or admission votes. Animation activation and other unresolved safety policy choices remain separate launch requirements.

Submission runs technical validation on M before attestation and review. Chain validators verify the frozen technical evidence, its deterministic policy fields/digest and byte/type/size bindings as well as the existing admission checks. They MUST NOT substitute machine-dependent image/OCR worker timeouts for those consensus checks. Any additional local decoding/screening is a local defense; it cannot silently change valid-chain rules or turn missing evidence into acceptance.

Nodes SHOULD isolate codec/media workers with no network or secret access and bound memory, concurrency, queues, request bodies, and cache residency. Existing local image-worker defaults include 2-second structural-decode timeout and 256 MiB worker memory; they are **not** consensus decompression deadlines or codec budgets. Timeouts, out-of-memory events, cancellation, or saturated queues mean **not yet validated/local processing failure**: do not vote, import, finalize, or serve unverified bytes. Retry/defer/backpressure or mark the node unhealthy. A slower node must not declare a valid block consensus-invalid solely because a wall clock expired. Protocol limit violations, wrong output, bad checksums, and malformed streams are deterministic rejection reasons.

### 6.4 Encoder requirements and producer choice

The producer MUST start with accepted M and frozen admission evidence, verify H/length/type, and select identity or an active compressed profile. It MAY try candidate compression levels locally; after proposing a block it MUST preserve that exact E and descriptor. It MUST perform the same bounded decode/hash/size checks required of validators before publication.

Recommended producer policy: prefer compression only if the **complete canonical block** is smaller than the identity candidate with the same non-media fields by a configured worthwhile margin, within local CPU/latency budgets. For incompressible media, failed encoding, profile-limit failure, or insufficient savings, select identity if the complete block fits. Codec performance and thresholds require measurement; no compression level or gain is mandatory.

Making “only if smaller” a consensus rule would require defining the comparison (payload versus full serialized record), exclude otherwise decodable expanded frames, and constrain producer choice. Enforcing optimal output or minimum savings across all compressor settings would require recompression/search and implementation-dependent judgments. This contract avoids those obligations: validators accept every registered, bounded, correctly decoded representation, including equal/larger ones. The consequence is that the network must budget worst-case accepted E/block sizes; predicted savings cannot be a consensus assumption or guaranteed storage reduction. Fork choice/reward rules gain no preference for “better” compression.

## 7. Decoder and validator procedure

The same validation boundary MUST protect production, normal block reception, candidate-chain validation, synchronization, chain import/export verification, startup integrity checks, restore, and media retrieval. Do not add v3 to a version allowlist while leaving its integrity path skipped.

1. Bound incoming application bytes before JSON/base64 allocation. Parse with duplicate-key, depth, integer, string, and closed-schema checks. Reject missing/null/unknown versions and wrong network/genesis context. Compute exact C(record) size and enforce the complete block cap. Outer HTTP/archive decompression also requires its own application-byte cap.
2. Validate the descriptor's ranges and registry membership before invoking a codec. Bound/check base64 character length, alphabet, padding and pad bits; decode E and verify `len(E) == stored_size`. Never allocate from an unchecked claimed size.
3. Recompute SHA-256(C(B)); require equality to the supplied hash and linkage/height context. Check cheap certificate/network/policy structure before expensive work. A matching block hash alone does not validate the media.
4. For identity, read M directly from E. For compressed mode, inspect the allowed frame under profile limits; stream decoding with bounded chunks, state/window/work counters and an output ceiling equal to `original_size`. Hash output incrementally while retaining at most one bounded original buffer or temporary spool if needed by media validation. Require successful end-of-frame, checksum verification if required, and consumption of **all** E.
5. Require exact output count, SHA-256(M) = H, allowed MIME and evidence type agreement. Require canonical UTF-8 text already normalized under the frozen text rule; reject noncanonical text rather than canonicalize after hashing. Corruption, truncation, extra output/input, unsupported flags/dictionaries, size mismatch, or hash mismatch is invalid even if a decoder returned some useful bytes.
6. Pass that same verified M and its computed H/length into existing technical-evidence, attestation, admission, and originality checks. Enforce certificate/summary/creator/reward equality and original-media duplicate claims against the candidate ancestry. Validate transactions, signatures, references, rewards, fork choice, and finality with existing semantics in the launch context.
7. Only after all checks succeed, atomically persist the exact canonical representation and canonical-state claims. Consensus attestations require this complete validation. Never publish partial decoded output as verified media or certify a block with absent payload.

Use a per-operation immutable validation result containing the exact block hash, verified descriptor, H/length, and bounded M handle; reuse it through the cooperating validators instead of decoding separately in payload, certificate, and media-integrity helpers. State-dependent results (uniqueness, reviewer references, finality) must be checked against the current candidate prefix even if byte decoding is cached. A shared decode cache must bind the verified block identity/representation, not just H or height; distinct encodings of one H cannot share an unverified encoding-validity result. Caches are optional and evictable.

The text rule is strict UTF-8 decode, `CRLF -> LF`, then remaining `CR -> LF`, then trim the following scalars from both ends, followed by UTF-8 encoding: U+0009..U+000D, U+001C..U+0020, U+0085, U+00A0, U+1680, U+2000..U+200A, U+2028, U+2029, U+202F, U+205F, U+3000. This explicitly pins the baseline Python trim set rather than depending on a future runtime's Unicode tables. Interior scalars are preserved; no NFC/NFKC conversion or BOM removal is added. Empty-after-trim is rejected. Validators require M already to equal that canonical result. Freeze UTF-8/trim edge cases in vectors before launch.

## 8. Network and lifecycle integration

| Component | Consumes/preserves | Required behavior |
| --- | --- | --- |
| Submission and technical/community admission | M; H/length/type evidence | Validate/canonicalize before signing. Uploaded compressed archives are not automatically accepted media. Staging is temporary; acceptance cannot rely on staging bytes. |
| Block production | M and frozen certificate; emits E + descriptor | Choose a profile, validate the proposed bytes, enforce exact record size, propose once. No second canonical raw copy. |
| Block validation | E and descriptor, then bounded M | Verify commitment and reconstruction, all evidence and original-media claims. Decode once per verification context. |
| Community voting | Original media/policy evidence | Review M or existing safe preview with its original identity; votes bind H and context. No community review of a codec-specific identity. |
| Consensus voting and finality | Validated block hash | Attest height/hash under new network/domain after full validation. Proofs need not embed another media copy; hash commits to E and descriptor. |
| Peer broadcast/sync | Exact canonical record/E | Never transcode E for another node. Require protocol, genesis, and registry/policy agreement. Header/summary-only responses cannot validate, restore, or finalize a full-media block. |
| Paged initial sync | Encoded records; one bounded decoded object at a time | Enforce both page limits including proofs. Pin target tip and predecessor hash; verify every page and persist incrementally with resume checkpoints. On tip changes, restart from a validated common prefix. No unbounded suffix response or whole-chain decoded list. |
| Chain import/export | Complete encoded records and launch metadata | Preserve exact E, descriptor, certificate, block hashes, order and finality proofs; verify at import and before claiming a verified export. No reencoding. Unsupported versions, missing media or wrong launch are rejected, not skipped. |
| Snapshots/backups | All canonical E/metadata/proofs and state | A full-node snapshot/backup MUST contain complete canonical history, including all media. Header-only/pruned/state-only artifacts cannot claim MODEL A restoration. Archive compression is optional and outside consensus; safely unwrap with bounds, then validate canonical records. |
| Reorganization | Both branch representations; decoded M as needed | Validate new ancestry, preserve retained blocks' E, atomically rebuild H/submission/certificate/reward claims and derived indexes. Refuse detachment of persisted quorum-finalized identities; discard only branch-specific noncanonical attestations. Equal H does not make different block hashes interchangeable. |
| Original-media API | Verified M, H, original MIME | `GET /blocks/{hash}/media` returns exact M with original MIME, original-byte length, block hash and media SHA-256 integrity headers. Do not set HTTP Content-Encoding to the storage codec. Withhold bytes until verification succeeds; presentation/dispute policy stays separate. |
| Encoded-block API | E + authenticated descriptor/certificate | Return canonical_record. Optional summary/compatibility views are explicitly incomplete and cannot be imported as blocks. URL or cache paths are never reconstruction authorities. |
| SQLite/JSON storage | Exact E and descriptor plus committed metadata | Today's section JSON can preserve the canonical record but still rewrites chain sections. A later normalized per-block BLOB adapter is recommended, not required for consensus. BLOB E is authoritative blockchain data, not disposable cache. |
| Cache/index/local compression | Optional M or local reversible wrapping of E | Rebuild from canonical data with the cache removed. Index H and relevant chain references, not compressed bytes as media identity. Local layout/codec/cache differences must not affect canonical bytes or validity. |

For normalized SQLite, write header/descriptor, E BLOB, certificate, claims, canonical tip and required finality state in a single transaction. Export must re-create the exact canonical_record by strict base64 encoding the unchanged BLOB. Do not key authoritative payload storage solely by H: two valid branch encodings of H may differ. A block-hash key or explicit exact-encoding reference is needed. Deleting/compacting a cache must never delete canonical E. Crash recovery must not expose a header with a missing payload or a claim without its block.

Backups must use a consistent SQLite backup/transaction mechanism including required WAL state, not a casual copy of an active database file. A local physical wrapper must be versioned/bounded and recover E exactly; required decoding assets, if any, must be in the backup. Logical exports remain self-contained canonical records. A restore must succeed without original staging files, cache, producer compressor, or external service.

## 9. Node interoperability and activation

Nodes on one launch MUST agree on N, protocol version 2, block version 3, media encoding version 1, genesis hash, allowed codec/profile registry, resource limits, media/admission policy and digests, and signing context. Handshake/chain summary must advertise the protocol/genesis and registry/policy digest; mismatches abort before bulk transfer. Registry data is already genesis-bound, so the digest need not be redundantly added to each media descriptor.

Nodes MAY differ in encoder choices, compressor implementations/levels, optional physical database layout, cache retention, and bounded scheduling. They MUST agree on decoding, rejection, hashes, and original bytes for every active profile. Validators must not dynamically negotiate a smaller codec set with one peer and then fork on blocks from another peer. HTTP transport compression or backup compression does not expand the allowed canonical codec set.

Before enabling a compressed profile, compare at least two independent compatible decoder implementations/builds and supported platforms against valid and adversarial bitstreams. Disagreement or inability to enforce limits blocks activation. Encoder byte equality is not required. Future changes to codec acceptance, resource ceilings, or interpretation require an explicit protocol/network upgrade; historical support cannot be removed because a new encoder is preferred. The hash contract and identity-only mode can be reviewed now, while compressed activation remains gated.

## 10. Development reset and launch plan — not executed

The recommended route is a **fresh development network**, not rewriting existing finalized blocks in place. Existing v1/v2 runtime compatibility is optional and not a launch requirement. Retain old documents/vectors and an archived old client/state for inspection where useful.

Required version changes are protocol 1 -> 2, media blocks 1/2 -> 3, genesis 1 -> 2, media encoding schema -> 1, admission certificate 1 -> 2, and new-context signing/policy versions as described in section 5. Version constants must be disentangled where `PROTOCOL_V1_BLOCK_VERSION = PROTOCOL_VERSION` currently couples unrelated concepts. Full-state export/snapshot `export_version` increments from the current `1` (`storage_tools.EXPORT_VERSION`) to `2`, with explicit N/genesis/registry binding and complete canonical records; an old container cannot be accepted by shape alone.

The new genesis MUST commit the exact protocol identity, initial allocations/reward parameters, admission and codec-registry/limit digests, and frozen genesis media if retained. Use the same media descriptor in **identity mode** for genesis media and a separate closed genesis-v2 payload, excluding non-genesis admission requirements. Freeze its exact original bytes, descriptor, canonical preimage and genesis hash; existing genesis hash/signatures are not reusable. Any reused allocation/media values must be explicit launch inputs, not accidental imports. Final N, genesis timestamp/allocations/media choice, and manifest are release decisions still to be made.

Deployment order for a later authorized task:

1. Complete Task 7.4 benchmarks and close codec/resource/text-policy gates. Freeze registry/limits, signing adapters, exact new genesis/identity, export format, and independently checked golden vectors.
2. Implement and validate production, decoding/admission, persistence, API/sync, snapshots/reorg, and startup identity checks in isolation. Rehearse cache-free restore and multi-node interoperability before network cutover.
3. Stop old development writers/validators, take and verify a consistent old-state backup, and record old chain identity/tip. Preserve it under a distinct old-network data location.
4. Initialize new database/data directories. Old database documents and claims, peer auth/replay state, cached chain references, reviewer/originality indexes, pending signatures, finality records and mempool must not be treated as new canonical state. Default is no old chain/state carryover. Any later balance/reviewer carryover requires a separately explicit genesis input and review.
5. Start upgraded bootstrap/validator nodes with identical manifest/genesis, validate initialization, then enable compatible peers, API clients, submitters/reviewers and minting. Fail startup on old or mixed-version database identity; do not silently migrate/reinterpret records.
6. Verify new hashes, signature isolation, peer sync, fresh admission/mint, persistence/restart, and backup/restore on the new network before opening access.

A JSON-to-SQLite or section-to-BLOB migration is a **physical storage migration** only if it preserves canonical_record and block hash exactly. Converting historical raw blocks to v3 changes every affected hash and descendant reference; it is a new chain with invalidated finality, not a physical migration. Such conversion is not the recommended reset path and is not authorized here.

Rollback before new-chain activity can restore old binaries plus the complete old-network backup/configuration. Once new blocks/signatures/transactions exist, returning to the old chain abandons that new history; old clients cannot consume v3 by changing a flag. Reencoding accepted v3 blocks is also not rollback: it creates different block identities. Postlaunch codec/security changes must preserve historical verification or use an explicit coordinated protocol decision. No automatic dual-network acceptance or silent downgrade is permitted.

## 11. Required implementation changes (future work only)

| Area | Required changes |
| --- | --- |
| Protocol/schema | Add versioned strict parser/serializer/domain helpers and frozen launch manifest; implement section 3's descriptor/base64 rules and section 4's record/preimage. Do not mutate existing golden-vector behavior in place. |
| Block model | Add v3 constructor/from-record/hash paths and exact type/version checks. Remove canonical duplicate raw/hex/base64/text media copies and supply explicitly derived API adapters. Distinguish media, stored, canonical-record, and transport byte sizes. |
| Media codec/integrity | Add registry, identity decoder, selected bounded decoder only after freeze, shared verification context, streaming length/hash checks and deterministic error categories. Update every integrity/version filter and cache binding. |
| Admission/evidence | Adapt content-hash/MIME/size access to the media descriptor and verified M, new network/domains/policy/certificate versions, existing safety/attestation/vote bindings and duplicate/reward claims. No recompression at validation. |
| Production/consensus | Replace approximate size checks with full canonical_record accounting; choose encoding once, validate it, retain existing consensus/reward/finality meanings, and sign new block identities. |
| Persistence | Teach JSON/SQLite adapters to round-trip exact E/descriptor and atomically maintain claims. Add explicit database launch/schema checks; normalized BLOBs and optional physical compression remain separate measured optimizations. |
| Sync/API | Upgrade peer block schemas/summary/handshake, exact encoded transfer, bounded paging/resume, streaming validation and original-media reconstruction; distinguish complete records from summaries. |
| Portability/recovery | Version snapshots/exports, full-history payload checks, consistent backup/restore, cache-free reconstruction, old-network rejection, and atomic reorg/index rebuild. Add explicit reset tooling only in a later authorized task. |
| Documentation/fixtures | New protocol/genesis/signature/export vectors and updated runbooks/API docs; old v1 docs remain historical until implementation/release. Do not report design arithmetic as measured savings. |

## 12. Required regression and golden-vector tests

These are requirements for implementation, not tests of an existing codec. Fixtures MUST record exact original bytes, E, descriptor, canonical record/preimage bytes, block/media hashes, signatures and expected accept/reject outcomes as applicable.

| Test group | Required cases |
| --- | --- |
| Canonical media/schema | Identity example above; every accepted MIME; Unicode/control escaping/key ordering; maximum and empty data; integer vs boolean/string/float; null vs missing vs empty; unknown/extra/duplicate keys; invalid UTF-8/surrogates; unsupported versions; wrong network. |
| Base64 | Each input length modulo 3; exact max character bound; invalid alphabet/URL variant/whitespace; missing/excess/interior padding; nonzero pad bits; decoded-size mismatch; hex/tagged/raw-text inputs rejected. |
| Commitments | Mutate E, codec/profile/version, sizes, MIME, H, certificate, caption, predecessor and network independently: hash changes or validation rejects. Standalone/paged/persisted records have identical preimages. Unhashed views cannot override the descriptor. |
| Original identity | Same M with two distinct valid encodings has equal H and different block hashes; MIME is excluded from H but authenticated/type-checked. Different M with retained H rejects. Text upload canonicalizes before signing, while noncanonical block text rejects. Freeze trim-set, Unicode and newline cases. |
| Compressed profile | After selection: independent decoder agreement, every supported frame/flag edge; valid non-default encoder output; truncated/corrupt/checksum failure; concatenation/skippable/trailing data; dictionaries; invalid frame tables/windows; declared-size mismatch and partial-success decoders. No recompression required. |
| Bounds/adversaries | Exactly-at/one-over original, stored, full-record, output, window, state and deterministic work counters; small high-ratio valid M; bounded-output excessive-work attacks; frame/header-count limits. Verify output ceiling before overflow allocation, plus local timeout/OOM/defer behavior with no vote/acceptance. |
| Producer policy | Incompressible media falls back to identity; equal/larger valid compression is consensus-accepted; profile/size violations are rejected; validator requires a decoder but no encoder/recompression capability. Maximum media that cannot fit its certificate remains unminted without truncation. |
| Admission/signing | Certificate H/length/MIME mismatch, bad digest/signature, wrong policy/network/domain, stale reviewer reference and forged technical evidence rejected. Encoding choice does not change valid original-byte evidence in the same signed context. Old-network evidence and finality cannot replay. |
| Duplicate/reward/forks | Reencoding, MIME relabeling, new submission/certificate IDs cannot bypass original-media claims; atomic concurrent mint protection; retained originality/perceptual results derive from M. Alternative forks may contain different valid encodings, but only winning ancestry supplies canonical claims. |
| Persistence/API | JSON and SQLite round trips preserve exact E/preimage/hash; no cache/staging files needed; corrupt/missing BLOB fails; optional local wrappers/layouts preserve record; API returns exact verified M/MIME/H, never E as an image. No partial unverified response. |
| Sync/export/restore | New-peer identity/registry mismatch; complete encoded blocks through paged sync, resume/tip change; both page caps; exports preserve full history and proofs; truncated/old/unknown-version snapshots rejected; archive bomb bounds; restart and verified consistent backups without cache. |
| Reorg/finality/crash | Detached claim/index reconciliation, stale evidence invalidation, alternate E not substituted for a retained identity, rejection of finalized detachment; crashes between header/payload/claim/tip writes recover atomically. |
| Launch/regression | New genesis preimage/hash, protocol/media/profile/signature vectors, native transfers and rewards unchanged in meaning, explicit old-database rejection, isolated reset/rollback rehearsal. Retain old vectors for old code/archive checks without requiring live v1/v2 acceptance. |

New compressed golden vectors must specify accepted frames, not mandate one encoder's output for every M. Cross-platform verification compares decoded bytes, validity decisions and hashes for **the same E**, not all producers' compression output.

## 13. Remaining benchmark and release gates

Task 7.5 update: codec selection and framing are now specified in the [security contract](milestone-7-codec-security-contract.md). Complete-record overhead, final A/B/C, safe decoder state/work, independent conformance and launch integration remain open; the security contract enumerates their current requirements.

Tasks 7.4/7.4A supplied corpus measurements supporting the initial identity plus Zstd strategy. They did not measure complete-block/wire/database/snapshot costs, native peak resource use or adversarial behavior. Those gates remain; distinguish codec gains from replacing hex/duplicate copies or changing database layout, and do not generalize synthetic-image results to real-world uploads.

Compressed-profile gates remaining after Task 7.5: deterministic work proof/counters; table/state accounting and safe adapter implementation; independent decoder/platform agreement and adversarial vectors; final media/block ceilings with admission fit guarantees. Exact codec/profile IDs and frame/header/checksum restrictions are now defined, but not activated. No compressed activation with placeholders. Producer savings thresholds and optional physical compression are local decisions informed by measurements, never validity rules.

Release gates independent of compression speed: exact N/genesis/allocations/manifest and snapshot schema freeze; text trim-table conformance vectors; new-context signed-object vectors and policy versions; safety-policy activation choices carried from Milestone 6; complete implementation plus the tests above. Codec-profile limits must be genesis/policy-bound before signing new admission evidence. Fee/storage economics and any future admission pricing remain separate decisions; this task changes no fees.

The representation, media/block identity split, commitment rules, producer/validator split, absolute-size accounting and reset strategy are ready for review and commit as a **design specification**. They are not a launch-ready compressed protocol until these gates are closed.

## 14. Task 7.2 verification and scope record

Repository verification confirmed the expected branch/HEAD, committed Task 7.1A and clean starting worktree. Source inspection covered the implementation paths in section 2 and existing protocol/golden-vector documentation. The only intended file changes are this specification and a reference/status clarification in `milestone-7-architecture.md`.

Checks completed against the baseline runtime:

```text
.\.venv\Scripts\python.exe -m pytest
  tests/test_protocol_v1.py::test_bytes_are_deterministic_and_round_trip
  tests/test_protocol_v1.py::test_domain_separation_changes_bytes_and_hashes
  tests/test_protocol_v1_golden_vectors.py::test_canonical_serialization_vectors_match_runtime
  tests/test_protocol_v1_golden_vectors.py::test_block_vectors_match_runtime
  -q --tb=short -p no:cacheprovider
Result: 4 passed in 0.84s.
```

Read-only documentation checks also passed: the identity illustration's exact canonical JSON, original bytes/SHA-256, base64 and lengths; maximum base64/remaining-budget arithmetic; the explicitly listed trim set against the baseline interpreter; local architecture reference; and whitespace/final-newline checks on both documents, including the new untracked file. `git diff --check` passed. The final change set contains only the two intended documentation files; HEAD is unchanged. The new specification remains untracked until a later authorized staging/commit step.

Current-runtime tests establish only baseline behavior. They do not validate the proposed unimplemented v3 format or compressed profiles. No compression, dependency installation, corpus construction, benchmark execution, production-code change, chain/database reset, deployment, or Git history mutation was performed. There is no blocker to reviewing/committing the design document; the benchmark and release gates in section 13 remain blockers to compressed activation and launch.
