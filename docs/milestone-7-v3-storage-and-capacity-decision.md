# Milestone 7 Task 7.9 — Final Block-Capacity Policy and v3 Storage Decision

Status: architecture recommendation ready for review. Numeric rules below are proposed **new-launch rules**, not active consensus rules or a production-security approval. Implementation, migration, reset and activation remain separate work.

Date: 2026-10-18 (America/New_York). Verified branch: `Compression-State-Bloat-and-Node-Economics`. Starting HEAD: `c8d9172ddd95cd7914881ed61412f145ed91ae19` (`Milestone 7 Task 7.8: model three-year full-node economics`); Task 7.7 is separately committed at `e5a3a77`. The initial worktree was clean. No applicable `AGENTS.md` was found in the repository or ancestor directories. No unexpected repository state was found.

## 1. Decision and scope

Recommend these limits for the next development-network protocol v2 / media block v3:

| Quantity | Recommended rule |
| --- | --- |
| Original accepted image M | 1..2,097,152 bytes (2 MiB); exact original accepted container bytes |
| Canonical accepted plain text M | Retain 1..262,144 bytes after the specified text canonicalization; increasing text capacity is unnecessary for this image-focused release |
| Encoded E, before base64 | 1..2,097,152 bytes (2 MiB), independently of original size; identity requires E = M |
| Complete canonical non-genesis record | At most 3,145,728 bytes (3 MiB), including envelope, hash, media, certificate, transactions and caption |
| Non-payload bytes O | At most 327,680 bytes (320 KiB), partitioned exactly below |
| Encodings | Only `identity/1` and `zstd/1`, subject to the existing security activation gates; producer selection, validator verification without recompression |
| Physical storage | Hybrid SQLite: one immutable canonical serialized block BLOB per block, a small set of derived searchable columns/indexes, separate mutable canonical-state/finality records |
| Admission guarantee | Reserve the complete mandatory **identity** block before certifying/queuing; pack optional transactions only within remaining exact budgets |

**The three candidate caps can coexist under the additional enforceable overhead rules in this decision. They cannot be proved safe from today's schema or observed fixtures alone.** No increase to 4 MiB is presently justified. The proposed caps guarantee capacity for bounded evidence, not acceptance of every file below 2 MiB: MIME, image structure, safety, attestation, review and all other validity rules still apply.

MODEL A remains mandatory: every accepted block retains all encoded media and decoding metadata needed to reconstruct original accepted bytes byte-for-byte. SHA-256(M) is media identity. The block hash authenticates E and its descriptor. No external media service, dictionary, previous media object, cache or creator-supplied codec can satisfy this obligation.

This task changes documentation only. It does not integrate compression, modify consensus/code/dependencies, migrate databases, reset a chain, deploy, implement bounties, commit/push, or begin subsequent tasks. The budgets are review proposals requiring approval and boundary vectors before launch freeze.

## 2. Evidence and inspected implementation

Read the [architecture audit](milestone-7-architecture.md), [protocol specification](milestone-7-compression-protocol.md), [codec/security contract](milestone-7-codec-security-contract.md), [block composition report](milestone-7-block-composition.md), [node economics report](milestone-7-node-economics.md), [decoder conformance](milestone-7-decoder-conformance.md), [decoder performance](milestone-7-decoder-performance.md), [Windows isolation](milestone-7-decoder-isolation.md), [Linux isolation](milestone-7-linux-decoder-isolation.md), and the [corpus admission diagnosis](milestone-7-corpus.md). Historical conclusions retain their measurement dates and limitations; this decision supplies the capacity/storage recommendation they left open.

| Actual source inspected | Finding relevant to this decision |
| --- | --- |
| `block.py:consensus_payload_v1`, `_consensus_transactions_v1`, `_consensus_native_transactions_v1`, `to_dict`; `protocol_v1.py:canonical_json_text`, `build_domain_envelope` | Current admission block v2 hashes hex-tagged raw bytes; persistence also contains `meme.encoded_image` base64. Null dropping, conversions and defaults in existing builders are unsuitable as strict v3 wire parsing. Native record dictionaries are retained broadly. |
| `media_admission_policy.py`; `services/block_production_service.py:build_candidate` | Current versioned policy declares 256 KiB image/text and 512 KiB canonical blocks. The candidate builder estimates base64, text and transaction sizes before appending complete reward/certificate metadata; default approximate limit is 500 KiB. This is not exact complete-record enforcement. |
| `services/block_validation_service.py:validate_native_transactions`, `validate_admission_block`; policy evaluator | Native ordering, hash, nonce, balance and evidence checks exist. No universal exact serialized-block size check or validator count cap matching producer selection was found. `canonical_block_bytes` is optional in policy evaluation; inspected production callers do not establish universal enforcement. |
| `admission_certificate.py:_frozen_votes`, `attestation_identity`, `validate_admission_certificate`; `dual_review.py` | Certificate and vote key sets are checked, but minimum quorum is not a maximum vote count. All frozen qualifying-dimension votes can be embedded. Nonces/messages and nested material need byte limits. Current minima are five eligible votes and one established reviewer per dimension, with 7,000-basis-point approval. |
| `media_technical_validation.py:technical_evidence_identity`, `validate_technical_evidence` | Identity removes a short exclusion list rather than selecting a closed key set. Arbitrary other digest-bound fields can survive; a correct digest alone does not bound or validate those extensions. |
| `protocol_v1_submitter_attestation.py`; `native_transfer.py`; `transaction.py`; `validators.py` | Attestation nonce has a 256-character bound; native memo has a 280-character bound and monetary precision is six decimal places. These are not general serialized-byte limits. Native integer digits/amount magnitude and several signed strings lack explicit protocol-wide maxima. Reviewer signatures explicitly require 65-byte hex; submitter/native/finality paths must freeze equally strict serialization rather than rely on library recovery. |
| `protocol_v1_finality.py`; `services/finality_service.py`; `services/canonical_reorg_service.py` | Finality signs height/hash, persists proofs separately, and prevents detaching persisted quorum-finalized history. Validator-set normalization/deduplication is not a finite membership cap. Reorg currently reconstructs an entire state document. |
| `storage.py:_initialize_database`, `_load_sections_from_connection`, `_save_sections_to_connection`, `_save_sections`, `_synchronize_canonical_claims` | Chain is whole-section `json_data TEXT`, not an authoritative media table. Section saves serialize full values; canonical claim tables are cleared/rebuilt. Native transactions have a normalized table (the redundant native section is skipped), but included native records also appear in block JSON. |
| `storage_tools.py:build_export_snapshot`, `backup_storage`, `import_storage`; `storage_migration.py` | Current portable snapshots are JSON and call current-media validation. `backup_storage` creates a logical snapshot, while `SQLiteStorageBackend.backup_sqlite_database` uses file copying. Neither is evidence of a future online, WAL-safe BLOB backup pipeline. |
| `api_routers/peer.py:peer_chain_blocks`; `api_routers/public_chain.py`; `services/peer_chain_sync_service.py` | Current suffix responses/full-chain sync are not the proposed bounded paging implementation. Media retrieval currently verifies original raw embedded bytes. |

`config.py:MAX_TRANSACTIONS_PER_BLOCK = 10` is a producer-selection default, not proof of a consensus maximum. Generic upload limits and local resource settings likewise cannot stand in for launch validity limits. Current documentation/production limits remain unchanged by this proposal.

## 3. Exact capacity accounting

### 3.1 Count the portable record, not the hash preimage

Use the Task 7.2 canonical JSON function, written here as `J` to distinguish it from a byte cap. Define:

```text
B = closed protocol-v2 domain envelope containing closed v3 payload P
h = lowercase_hex(SHA-256(J(B)))
R = J({"envelope": B, "hash": h})
L = 4 * ceil(len(E) / 3)
O = len(R) - L
```

All lengths are UTF-8 bytes. No BOM, insignificant whitespace or trailing newline is counted/allowed in canonical R. Base64 alphabet characters, `/` and padding do not escape under J, so subtracting L removes **only** the payload string contents. Quotes, field names, braces, commas and everything else stay in O. Input/output sizes must be checked before dependent allocations; bounds do not license parsing an unbounded outer document first.

For E = 2,097,152 bytes, E has remainder two modulo three: **L = 2,796,204**, including one `=`. Thus a 3 MiB R leaves **349,524 bytes** for O. `4E/3` without ceiling/padding is not exact. This is 33.3334% expansion before metadata, not codec savings.

At both size fields' maximum and a ten-character allowed MIME, the exact media object with empty payload is 231 bytes for identity and 227 for zstd. Its serialized `"media":value` member, excluding the containing object's braces, is respectively 239 and 235 bytes. Those figures include the descriptor, empty-string quotes and punctuation; add L to obtain the nonempty member size. They are analytic schema accounting, not decoder measurements. Shorter MIME/size strings use fewer bytes.

J's scalar, unique-key, UTF-8, closed-schema and depth-32 rules remain required. Escaping matters for other strings: 1,000 caption scalars can consume up to 6,000 JSON content bytes for control characters even though their raw UTF-8 length fits the existing cap. A scalar-count or raw-byte check is not a serialized-byte check. Measure all enclosing string copies too: an embedded canonical signed message escapes its own quotes/backslashes again.

**Task 7.7 accounting correction for future benchmarks:** its `complete_serialized_block_bytes` partitions `J(B)`, as confirmed by the measurement script, rather than normative R. With a 64-character hash the portable wrapper adds exactly **87 bytes**. The reported maximum projected adaptive fixture of 2,379,140 becomes 2,379,227 for R, still only a fixture. Aggregate 7,602,184 across 36 projected envelopes becomes 7,605,316 portable-record bytes. Keep published measurements and Task 7.8 baselines intact; update future benchmarks explicitly. The current SQLite v3 projection is a flattened storage record, not R or a BLOB layout.

### 3.2 Recommended enforceable budgets

Define three disjoint portions of O, using canonical value bytes (including their own braces/brackets):

```text
S_cert   = len(J(P.admission_certificate))
S_native = len(J(P.native_transactions))
S_rest   = O - S_cert - S_native

S_cert   <= 196,608 bytes  (192 KiB)
S_native <=  98,304 bytes  ( 96 KiB)
S_rest   <=  32,768 bytes  ( 32 KiB)
O        <= 327,680 bytes  (320 KiB)
len(R)   <= 3,145,728 bytes
```

S_rest includes the entire descriptor apart from L, all header/envelope/hash bytes, caption, reward/legacy transaction array, native aggregate hash, field names/delimiters for the subtracted values, and other mandatory scalar fields. Signatures already inside a certificate/transaction are **not added again**.

If these predicates and len(E) <= 2 MiB hold, then:

```text
len(R) <= 2,796,204 + 196,608 + 98,304 + 32,768
       <= 3,123,884 bytes
       <  3,145,728 bytes, with 21,844 bytes margin
```

The margin is not a discretionary extension field or transaction allowance. Changing the schema or budgets needs explicit version/policy review. Retain the complete-record check even though the sub-budgets imply a tighter bound. This is a conditional mathematical fit proof for the **proposed enforced rules**, not proof the current implementation enforces them or every hypothetical field-max combination passes the sub-budgets.

Mandatory-only identity candidates must fit with S_native = 2 (empty array) and no optional legacy transfers. Sub-budgets prevent optional transaction inclusion from displacing mandatory evidence. Their initial allocation is conservative engineering headroom, not a measured certificate percentile or a throughput claim.

### 3.3 Field and collection rules to freeze

All rows are proposed protocol validity rules for the new launch unless marked local/transport. A parent byte cap applies **in addition to** every child bound. A record whose children individually fit but whose aggregate exceeds a parent cap rejects; never truncate or normalize received signed content to make it fit.

| Fields/collection | Exact recommended maximum or grammar |
| --- | --- |
| Required block keys | Retain every required row of Task 7.2 section 4.2: version, height/link/times, both transaction arrays and native aggregate, miner, submission/certificate/vote/creator identities, content type, tally summaries, approval clock, reward fields, empty voter rewards, certificate and media. Only the specified nonempty image caption is optional. No old media aliases, `meme`, raw/text duplicate, local transaction IDs/count, arbitrary extension object or in-record finality proof. |
| Identifiers | Hashes/digests exactly 64 lowercase hex; submission IDs exactly 32 lowercase hex; wallet addresses exactly 42 lowercase ASCII characters under the existing identity validator; compressed miner/legacy public keys exactly 66 lowercase hex under existing key validity. Use full-string matching without trim/coercion. Reward sender is the exact allowed sentinel. No additional identity forms. |
| Envelope/versions | Exact protocol/domain/object strings from Task 7.2; one frozen network ID of 3..64 lowercase ASCII characters under its existing grammar. All policy/statement/validator identifiers are exact frozen constants; no user-defined names. Version integers equal supported registry constants. |
| Heights, counts, integer nonces | Integers 0..9,007,199,254,740,991 where zero is currently legal; block height and native nonce start at one. Decimal-string integer fields use the same range and canonical ASCII digits (at most 16), with no leading zeros. Counts also obey the relevant collection maximum and existing tally semantics. |
| Decimal strings | At most 32 ASCII bytes, canonical finite decimal grammar from Task 7.2; no exponent, signs on nonnegative values, redundant zeros or coercion. Monetary precision remains at most six fractional digits and existing supply/reward/balance rules remain binding. Admission ratios/scores must equal the frozen tally adapter; this limit introduces no new rounding. A missing exact adapter/vector is a freeze blocker. |
| Block times | `timestamp`/`minted_at`: at most 32 canonical ASCII decimal bytes, nonnegative, at most six fractional digits and integer part <= 9,007,199,254,740,991; retain existing time-validity checks. `approved_at` exactly integer zero. |
| Evidence times | Nonempty canonical UTC ISO-8601 form with four-digit year, `T`, seconds, optional 1..6 fractional digits, `+00:00`; <= 32 ASCII bytes. Preserve ordering/expiry semantics. The new signing context must pin this spelling before signatures are collected. |
| Free opaque signing nonces | 1..256 ASCII bytes from `[A-Za-z0-9_-]` for submitter/reviewer nonces; duplicates must equal the signed value. Native ledger nonce uses the integer rule instead. This explicitly bounds today's unconstrained reviewer nonce and character-only attestation nonce. |
| Personal-sign signatures | Exactly 65 decoded bytes, canonical lowercase `0x` plus 130 hex characters (132 ASCII bytes), with existing cryptographic recovery/validity rules; applies to submitter, reviewer, native and finality signatures. No alternate padding/case/prefix representation. Legacy transaction signatures retain raw 64-byte ECDSA representation in strict canonical padded standard base64 (88 characters), with existing verification rules. |
| Admission certificate | S_cert <= 192 KiB, exact closed nested schemas. At most 32 frozen vote records total, at most 16 per dimension, no duplicate (dimension, wallet). Each complete J(vote) <= 4,096 bytes; each `vote_message` <= 2,048 raw UTF-8 bytes and must equal the canonical message reconstructed from bounded signed fields. Existing eligibility, status/reference binding, quorum, threshold and ordering checks remain. |
| Submitter attestation | Complete J(attestation) <= 16,384 bytes, including canonical payload/message copies and signature; canonical message <= 8,192 raw UTF-8 bytes; payload/message reconstructed from closed bounded fields, exact pinned statement text and original H/size/type/policy. Parent cap counts escaped copies. |
| Technical evidence and tallies | Complete J(technical_evidence) <= 8,192 bytes. Select the exact identity keys emitted for accepted evidence by the current technical validator; reject every unknown nested key rather than using the current exclusion projection as a schema. Require accepted outcome and exactly the applicable pinned acceptance reason, correct image/text nullable fields, original length/hash/type and policy binding. Each of the two complete tally objects <= 8,192 bytes, closed schema, derived from the bounded votes; counters cannot exceed 16 per dimension. |
| Image structure | Retain dimensions 1..4,096, <= 16,777,216 aggregate decoded pixels and <= 60 frames; every required frame must validate. Encoding compression does not relax image parsing/safety policy. Animation activation remains a separate owner choice. |
| Caption and submission metadata | Caption <= 1,000 Unicode scalars **and** 4,096 UTF-8 bytes; absent for text media. Also count its escaped bytes in S_rest. Existing submission text <= 4,096 scalars and 16,384 UTF-8 bytes; display filename <= 255 sanitized ASCII bytes. These local submission fields must not be copied into v3 except the specified caption and explicitly signed evidence fields. No paths, OCR dump, original filename or arbitrary metadata map enters R. |
| Legacy/reward transactions | Required array: at most 16 records including the mandatory reward; each J(record) <= 1,024 bytes. Use the existing canonical transaction fields, bounded identities/decimal values/signature above. Retain required reward semantics; no new reward, bonus or voter reward. Optional legacy records are packed after mandatory contents. `voter_rewards` exactly `[]`. |
| Native transactions | At most **10** records, now a proposed validator-enforced cap as well as producer maximum; each complete J(record) <= 8,192 bytes; S_native <= 96 KiB. Memo <= 280 scalars and 1,120 UTF-8 bytes, and its repeated/escaped form counts. `signed_message` <= 4,096 raw UTF-8 bytes and equals reconstructed canonical signing envelope. Exact keys, nullable fields and launch-context adapter must be frozen; arbitrary `NativeTransaction.to_dict()` lifecycle/error/local timestamp copies are not an extension mechanism. |
| Generic parsing | Depth <= 32 including R/envelope containers; reject duplicate/unknown keys and invalid Unicode at every nested schema. No arbitrary collection beyond these enumerated arrays. Bound outer body bytes and strings before allocating nested objects. |

The vote ceiling is a **new bounded certificate policy**, not an assertion that the five-vote minimum already limits certificates. Freeze a qualifying snapshot within these caps, preserve its full vote set, and keep later votes outside that certificate. Never silently discard unfavorable votes or change tallies to fit. If the complete required snapshot does not fit, it cannot be certified under this launch policy; any replacement snapshot requires explicit existing-policy handling and fresh bindings. The ceiling and freeze procedure need owner review/new policy digest; this decision does not implement either.

The signature-only maximum inside a 32-vote certificate is 33 personal-sign signatures including the submitter: **33 × 132 = 4,356 content bytes**, or 4,422 including their JSON string quotes. This is a subset of S_cert; messages, identities and other evidence also consume the certificate allowance. Across a block the proposed maxima permit another ten native signatures and at most fifteen optional signed legacy records (mandatory reward unsigned). Their content maxima are 1,320 and 1,320 bytes respectively, already charged to their enclosing arrays. No separate producer block signature is specified by Task 7.2; adding one consumes S_rest and requires schema review.

### 3.4 Exact unresolved constraints in today's implementation

The proposed caps bound these categories; **none of the missing enforcement below is completed by writing this decision**:

1. **Vote sets:** no finite frozen admission vote count; quorum/eligible reviewer population and two dimensions do not supply a maximum. Reviewer nonce and issued/expiry strings are nonempty without finite byte caps; their signed message and repeated copies grow with them. Reviewer reference heights and tally integer sizes lack the new safe-integer cap.
2. **Attestation:** its nonce is character-bounded, not fixed ASCII byte grammar. Signature serialization is not explicitly frozen to 132 characters in that validator; canonical payload/message copies need aggregate byte caps. Exact constants are already finite, but duplicated variable fields and escaping need counting.
3. **Technical evidence:** digest-bound extra keys, values, arrays/maps and reason-list extensions survive the exclusion projection; size/digest validity does not establish a closed finite evidence schema. Accepted-evidence field types/structure must be fully checked.
4. **Transactions:** producer's ten-native default is not a validator count maximum; legacy pending/reward array count lacks a global block limit. Native dictionaries and lifecycle metadata, raw signed messages and legacy record strings need closed-schema byte limits. Monetary fractional precision does not bound integer magnitude; native nonce positivity does not bound digit count. A 280-character memo alone does not bound its repeated serialized copies. Cryptographic libraries' accepted signature forms are not serialized protocol maxima.
5. **Headers/scalars/captions:** current required strings often trim/check presence rather than applying the proposed exact grammar; runtime integers and decimal strings lack universal v3 byte/range limits. API-generated IDs and bounded network syntax do not prove all consensus entry paths check every identifier. Caption/submission limits exist in policy, but the producer's extracted/display text and all block acceptance paths need exact enforcement. Frozen network/statement/policy values and nested adapters are still launch decisions.
6. **Finality outside R:** membership count, evidence list length, signature/message serialization and proof response bytes need separate bounds. Equivocation history can grow even with finite membership; it is not canonical block payload. Transport/query pagination and retention for this auxiliary history need explicit policy.
7. **Record/decoder:** no production v3 serializer/strict parser or universally enforced exact R/O/sub-budget checks exist. Decoder native state/work limits are not fully proved. Whole-chain responses/exports must not allocate unbounded lists even when every block fits.

This inventory distinguishes existing finite fields (hashes when properly checked, MIME enums, pinned constants, image structure) from unenforced or missing aggregate bounds. No observed maximum, Python integer-parser limit, library error, upload route limit or finite test corpus is a consensus proof.

### 3.5 Finality and transport allocation

Keep finality proofs outside R and the block preimage, as Task 7.2 specifies. Finalizing a block must not rewrite its canonical bytes/hash. Store proofs separately keyed by the authenticated height/hash/network and preserve finalized ancestry across reorgs.

Propose a launch maximum of **128 unique validators**, at most one counted attestation per validator per proof, each J(attestation) <= 1,536 bytes with message <= 1,024 raw UTF-8 bytes and the signature/identity/height bounds above. Each complete finalization proof, including its validator set and wrappers, <= **262,144 bytes**. All limits apply together; preserve the existing quorum formula `(2*n+2)//3` and trust/validator-set validation. This membership maximum is an approval-dependent launch rule, not a current fact. Split auxiliary equivocation histories into separately bounded pages; never inject them into R or silently omit evidence needed to prove finality.

Enforce both **64 records** and **16,777,216 application-response bytes** per chain page, including wrappers/proofs/peer authentication metadata. At most five 3 MiB records fit by bytes before additional overhead; the actual page packer stops earlier when needed. Fetch finality proofs separately if required, with bounded counts and response bytes. Bound decompressed HTTP/archive input independently. Transport caps and local body/queue controls do not redefine block validity.

### 3.6 Admission-to-block fit and consensus separation

1. At initial submission, validate original byte/type/image/text limits, caption and closed metadata bounds. Preflight an upper reservation for still-missing mandatory evidence; this is a capacity estimate, not an admission certificate or promise of review approval.
2. Before issuing the frozen certificate or adding a mintable queue entry, construct the exact certificate/attestation/vote snapshot and a mandatory identity candidate. Use bounded worst-case widths for height, predecessor hash, miner, times and any reward-dependent values not fixed yet. Enforce S_cert/S_rest, identity E/M limits and complete R size. Reserve these bytes with the immutable evidence identity and launch-policy version.
3. If required evidence changes, invalidate/recompute the reservation before certification/queue acceptance. If mandatory contents cannot fit, return a deterministic capacity reason; do not certify an unmintable submission, rely on expected compression or wait for optional transfers to disappear. Raw upload/staging success is not certification.
4. At production, instantiate actual header/reward values, rebuild exact R using the single serializer and recheck the mandatory identity candidate. Then select a permitted E; producer preference is to use zstd only if the **complete record** is smaller/worthwhile. Check E/frame/descriptor and all budgets. Expanded but otherwise valid zstd remains consensus-valid within the caps.
5. Pack optional native/legacy transfers in the existing required order, rechecking parent and complete-record budgets after each addition. Omit/defer optional transfers when full. Never truncate media, captions already signed/committed, signatures, certificate votes or mandatory rewards.
6. Validators apply the same deterministic limits, canonical hashing, original-byte reconstruction, media/evidence/signature/reward/ledger checks and ancestry checks on production, reception, sync, import, restore and startup. Local reservations need not exist on peers and are not consensus evidence. Verify the final block rather than trusting a producer's reported byte count.

All numeric record/substructure/field/profile rules proposed above are consensus-validity rules once approved and activated. Submission preflight/reservation, compression selection/savings margin, mempool queue size/rates, transaction inclusion choice, cache retention and worker scheduling are admission/local policies. Operators may reject/defer local uploads more tightly but must not mark otherwise valid received blocks invalid solely for local policy, timeout, OOM or queue pressure.

### 3.7 Alternatives if these bounds are not approved

| Alternative | Exact capacity consequence | Disposition |
| --- | --- | --- |
| Retain A=B=2 MiB and R<=3 MiB with these overhead caps | Analytic bound 3,123,884 including full optional budgets; 21,844 bytes unused | Recommended, subject to implementation and acceptance vectors |
| Retain 3 MiB; reduce encoded cap given another mandatory Omax | `Bmax = 3 * floor((3,145,728 - Omax)/4)`; also require B>=A to guarantee identity for all size-eligible originals | Defensible only with finite enforced Omax. For Omax=512 KiB, Bmax=1,966,080 bytes (1.875 MiB); reduce A to match or explicitly narrow admission by fit |
| Retain A=B=2 MiB; increase complete cap to 4 MiB | At most 1,398,100 bytes remain after maximum base64 payload | Requires new overhead bounds and resource/economics tests anyway; a larger cap cannot fix unbounded evidence |
| Conservative A=B=1 MiB, complete cap 2 MiB | Base64 1,398,104 plus proposed Omax 327,680 = 1,725,784; 371,368 bytes margin | Reduces capacity/identity traffic, excludes two corpus capacity images; no claim of current launch approval or economic guarantee |

If no finite certificate/native schema and fit policy are accepted, defer v3 activation rather than claim any candidate cap is proved. Future larger/media-specific limits require a versioned upgrade; arbitrary codecs remain forbidden.

## 4. SQLite architecture choice

The storage alternatives here concern **physical layout**. They are distinct from the earlier architecture report's A/B/C choices about canonical compression.

| Criterion | A. Current JSON sections | B. Canonical BLOB rows alone | C. Canonical BLOB rows + derived metadata | D. Minimal alternatives |
| --- | --- | --- | --- | --- |
| Canonical bytes / MODEL A | Current parsed objects can reconstruct current canonical bytes; whole-section JSON is not the exact portable R. A v3 adapter would have to retain every field/E and reserialize strictly. | Store exact R; self-contained media retained. Validate on insert/read/export. | Same exact R as authority; metadata cannot replace media or authorize decoding. | Canonical TEXT per block can preserve exact UTF-8 R; separate raw E tables would require exact record reconstruction and another consistency boundary. |
| Disk and JSON/base64 | Current hex plus compatibility base64 duplicates; projected v3 sections remove that duplicate but keep base64. Whole section formatting/escaping differs from J. | UTF-8 canonical JSON **inside a BLOB still has base64 expansion**; BLOB is not decoded E. Allocation overhead unknown. | Same payload plus explicitly bounded indexes/columns. Potential write savings; net disk unknown. | TEXT vs BLOB has no measured winner. Optional local wrapping/compression adds recovery/codec complexity; no measured need yet. |
| Duplicate storage / indexes | Chain-native records and normalized transaction/evidence state overlap. Section layout coexists with several SQL indexes. | Avoids another chain document but lookup can require parsing scans; keeping old chain section would erase the benefit. | One canonical payload copy; indexes only necessary identifiers/locations/state. Durable mempool/review records remain for their own lifecycle until measured retention rules allow cleanup. | Do not add a second authoritative media table or decoded original store. Cache copies remain bounded/evictable. |
| Reads / writes | Inspected save path serializes full sections and rebuilds canonical claims; materializes history. Task 7.7 measured disk, not latency or million-block behavior. | Per-block inserts/height reads are possible; hash/media lookup needs indexing or scans. | Indexed historical lookup and incremental transactions are the intended benefit; benchmark latency, fsync, contention and memory. No automatic speed claim. | Per-block canonical TEXT offers the same incremental design; compare if implementation simpler. |
| Historical lookup / sync | Suffix selection/whole-chain materialization remains. | Ordered bounded reads possible, but tooling required. | Height/hash/content identity lookup, bounded range reads and resumable sync without decompressing unrelated media. | External file packs/object stores/LSM engines add unjustified coordination/recovery scope. |
| Export / import | Current logical JSON export is portable but must gain strict v3 support; not proof of canonical-byte preservation. | Stream length-delimited R records plus network/version manifest and proofs. | Same export; derived indexes rebuild locally. Do not export BLOBs as a second base64 layer. | NDJSON can be a transport only with bounded record lines; media's inner base64 remains. No new consensus encoding. |
| Recovery / backup / snapshots | Current logical export/file copy need consistency verification, especially under WAL. | SQLite integrity plus block/hash/original-byte validation; online consistent backups must be implemented/tested. | Same, plus derived-index rebuild and atomic head/claim/finality consistency checks. | No SQLite file copy during live WAL writes as an assumed complete backup. Use tested backup API or verified quiesced snapshot procedure. |
| Reorg / finality | Whole document replacement/reconstruction today. | Immutable branch bytes retained; canonical mapping/state transaction required. | Atomic canonical mapping/claims/ledger change; finality locks remain separate and cannot be detached. No in-place block rewriting. | Do not introduce a new fork database or retention engine; bounded local orphan policy can be separate. |
| Migration / reset / reproducibility | Least schema work but preserves whole-history rewrite/materialization risk. | New schema/read/write APIs and versioned export required. | Slightly more schema than B, far less than normalized media/evidence engine. Rebuild projections deterministically from verified R/ancestry. | Development reset can avoid old-format conversion; it does not make old blocks valid on new genesis. |
| Long-term scaling | Finite for small development state; unmeasured and structurally poor for repeated archival updates. | Retained bytes still grow linearly with accepted traffic; unindexed scans scale poorly. | Smallest practical incremental archival layout; indexes also grow linearly. Needs benchmarks and bounded streaming runtime, not merely a new table. | Sharding/dedup/external stores are deferred until evidence warrants them; cannot prune required MODEL A bytes. |

### 4.1 Recommended minimal layout and invariants

Choose **C**, implemented later as a conventional SQLite adapter. A conceptual immutable `blocks` row stores block hash, height, predecessor hash, original-media hash, original/encoded sizes, MIME/profile identifiers and `canonical_record BLOB NOT NULL`. These columns are derived from verified R. Use a hash primary key, an ordered height access path, and an original-media lookup only where existing API/originality requirements need it; measure each index. Do not index payloads, captions, signatures or complete certificates.

Use a separate height-to-hash canonical mapping when side branches are retained so a reorg does not overwrite block bytes or misuse height as block identity. Existing mutable claims, account/nonces, pending transactions, reviewer state and finality evidence remain separate. One SQLite transaction must install verified block bytes, canonical mapping/head, ledger/uniqueness/reward claims and associated finality state before acknowledgment. Reorg uses the same transaction boundary and refuses to detach finalized ancestry. An index disagreement is corruption/rebuild work, not permission to edit R or recompress E.

Avoid retaining `storage_sections.chain` alongside canonical BLOB rows after cutover. Keep unrelated JSON sections initially if their workloads do not justify normalization. Refactor chain consumers to bounded range/record access; a BLOB table underneath `load_blockchain_document()` that still loads/re-saves every block would not resolve whole-chain work. Native included payloads may remain duplicated in existing lifecycle tables initially; account for those copies instead of claiming their elimination. Index-only references can be evaluated separately.

No decoded media BLOB table, external store, local second compression layer, deduplication engine, media delta chain or customized SQLite codec is required. A canonical TEXT row is an acceptable measured implementation alternative if it preserves exactly the same UTF-8 bytes and is simpler for the adapter. The architectural benefit sought is one authoritative record and incremental access, not the SQL storage class itself.

Preserve bytes end-to-end through backup, export/import and branch changes. Physical SQLite files need not be identical across nodes (page allocation/index histories vary); verified canonical records, original hashes/bytes, state reconstruction and finality outcomes must agree. SQLite integrity checks detect structural database issues but do not replace cryptographic/semantic validation. Keep known-good consistent backups; do not repair damaged accepted media from an unverifiable cache.

## 5. Economic consequences and measurement limits

### 5.1 What was measured

Task 7.7's 36 synthetic fixtures contain 6,093,917 original bytes and 5,285,234 adaptive encoded bytes (13.27% payload reduction); projected v3 identity envelopes total 8,680,536 bytes versus 7,602,184 adaptive (12.42% smaller). Ten fixtures retain identity. These results are corpus-dependent and are already incorporated into Task 7.8; do not apply that saving a second time to its baseline.

| Existing JSON-section engine, 36 fixtures | Current v2 identity | Projected v3 adaptive |
| --- | ---: | ---: |
| Logical chain JSON | 20,896,854 B | 7,621,402 B |
| DB after checkpoint | 29,659,136 B | 10,551,296 B |
| DB after VACUUM | 21,229,568 B | 7,929,856 B |
| Transient WAL before checkpoint | 21,156,232 B | 10,728,512 B |

These measurements include a 270,336-byte empty-DB baseline and use 4,096-byte pages with **benchmark-configured WAL**. Current `_connect` sets busy timeout, not a universal WAL deployment policy. `dbstat` was unavailable; exact table/index split is unknown. No canonical BLOB layout, million-block growth, backup pipeline, filesystem compression, cache retention or write latency was measured. The v2-to-projected-v3 difference combines representation/duplicate changes and compression, not an isolated BLOB effect. The <15% universal metadata goal still fails for small images (representative-image v3 adaptive byte-weighted metadata 36.39%); keep required evidence rather than hiding that result.

### 5.2 Preserve the Task 7.8 baseline

The following uses the existing illustrative pricing/configuration, 1,095 days, representative average 211,172 projected envelope bytes/block, 1.25 physical amplification, 1 GiB DB base and recommended four retained full backups at 0.95 compression. Prices are copied model assumptions, not newly obtained quotes. Primary below excludes additional local snapshot/maintenance space. No architecture saving is credited.

| Blocks/day | Three-year canonical / primary / retained backup GiB | Month-36 USD: budget / mainstream / storage-focused |
| ---: | ---: | ---: |
| 100 | 21.54 / 27.92 / 106.09 | 21.82 / 55.99 / 46.82 |
| 1,000 | 215.35 / 270.19 / 1,026.73 | 43.18 / 205.95 / 62.67 |
| 10,000 | 2,153.53 / 2,692.91 / 10,233.06 | 322.78 / 1,837.60 / 265.00 |

All three representative 10,000/day profiles exceed $100/month. Large-media traffic already fails on all profiles at 1,000/day ($328.55 / $1,870.39 / $269.19); allowing 2 MiB does not make that workload affordable. SMALL at 10,000/day has different modeled outcomes; do not turn a representative/large negative result into a claim about every possible tiny-media workload.

The 87-byte R wrapper adds 0.00887 / 0.08872 / 0.88722 GiB canonical at 100 / 1,000 / 10,000 per day over three years. This small correction and full production certificates, bounded finality/auxiliary state, indexes and caches belong in the next model update. The proposed 320 KiB maximum overhead is a limit, not a replacement for measured average metadata; neither maximum block capacity nor the corpus average is a traffic forecast.

### 5.3 Illustrative sensitivity, not a BLOB benchmark

As an arithmetic sensitivity only, reduce representative physical amplification from 1.25 to **1.00**, leaving canonical sizes, compute, peer traffic, full-backup policy and prices unchanged. This uses `simulate(..., physical_factor=0.8)` because that parameter **multiplies** the workload's existing 1.25. It does not assert SQLite plus indexes can achieve 1.00; real amplification may exceed the baseline.

| Blocks/day | Hypothetical primary / retained backup GiB | Hypothetical month-36 USD: budget / mainstream / storage-focused |
| ---: | ---: | ---: |
| 100 | 22.54 / 85.63 | 21.49 / 53.03 / 46.49 |
| 1,000 | 216.35 / 822.14 | 37.11 / 170.95 / 59.29 |
| 10,000 | 2,154.53 / 8,187.21 | 262.05 / 1,487.65 / 220.42 |

Even this favorable hypothetical does not rescue representative 10,000/day or mainstream 1,000/day. **An unimplemented storage layout has not met the $100 target.** No value in this sensitivity is a measured saving, accepted deployment budget or new host recommendation.

| Resource | Likely mechanism to evaluate; evidence limit |
| --- | --- |
| Three-year primary/index growth | Incremental rows avoid reserializing history; canonical retained bytes remain mandatory. Measure page/index/freelist growth and durable auxiliary state at scale; no assumed disk percentage reduction. |
| Backups/snapshots | Smaller verified physical state could lower retained full-backup size and transfer. Model currently retains four 0.95x full backups plus one local snapshot; no incremental/dedup saving is evidenced. Measure consistent online backup, restore, retention and simultaneous workspace. |
| WAL/checkpoint | Removing whole-chain section rewrites may reduce write amplification. Task 7.8 assumes temporary `0.20*primary + 1.45*monthly_writes + 5 GiB`; quarterly VACUUM needs another primary-sized workspace. Retain these conservative allowances until long-run measurements replace them; WAL is temporary, not retained chain data. |
| Bandwidth | Same R/E means no peer/initial-sync byte reduction from BLOB storage. Backup transfer might fall with physical size. Existing model adds eight peers, protocol/retry factors and four full backup transfers/month; do not count only propagation. Bounded paging mainly addresses memory/resume, not promised byte savings. |
| CPU/memory | Incremental persistence/lazy reads may reduce JSON work and full-chain residency; indexes/fsync add work. Codec validation and original-byte hashing remain. The model's 4.06 GiB requirement and 0.45-second provisional worker figure are not integration tests or portable resource proofs. The Linux isolation report's fresh Windows maximum-match p95 is about 0.626 s, so 0.45 s is not a universal worst-case bound. |

### 5.4 Measurements required before approving a storage cutover

1. Compare current JSON sections, canonical per-row TEXT/BLOB and the minimal indexed hybrid using **identical complete, signature-valid production-shaped v3 records**, including identity at maximum sizes, small media, maximum permitted evidence/transactions, and the original synthetic corpus for continuity.
2. Run stepped 1k/10k/100k-record datasets and a justified longer growth run: measure logical R, DB pages, usable payload, per-table/index attribution (use a build with `dbstat` or documented equivalent), freelist, WAL peaks, checkpoint lag and VACUUM/backup workspace. Include mempool/reviewer/finality/cache duplicates and bounded side branches.
3. Measure append/fsync, historical height/hash/media reads, concurrent API/worker access, canonical reorg, restart/replay, bounded initial sync and export/import. Record latency distributions, CPU, physical/aggregate memory, lock contention and sustained burst throughput on supported native Ubuntu hardware.
4. Fault-inject interrupted transactions/checkpoints/backups/imports and storage corruption. Restore onto an independent node; require identical R/H/original bytes, state and finalized ancestry. Verify backup without relying on live WAL sidecars accidentally left behind.
5. Recompute 36-month costs at 100/1,000/10,000 per day for small/representative/large/worst-capacity mixes using measured amplification, auxiliary growth, real upload distribution and separately quoted operating costs. Include backup transfer, local snapshots and maintenance headroom. Retain adverse findings even if averages improve.

## 6. Decoder and media security dependencies

Retain exact output = declared original_size <= the applicable original cap; E <= 2 MiB; pre-base64 allocation bound 2,796,204 characters; zstd window <= 262,144 bytes; one checksum/content-size-bearing dictionary-free frame; 1..64 data blocks; regenerated block <= min(W, 131,072); complete input/checksum consumption; SHA-256(M) and every signed evidence binding. Identity is a bounded copy/hash, with the same media/evidence rules.

Task 7.6A's sequence verifier resolved the earlier prototype's unproven-offset behavior in its tests; Tasks 7.6B–D report 152 frozen vectors (42 valid/110 invalid/zero indeterminate) and exact reconstruction of 36 corpus originals on the same decoder stack across Windows/WSL2 Linux. Do not describe that as independent decoder review. Preserve checks `actual_offset <= W` and available same-frame history. At A=2 MiB, sequences <= floor(A/3) = 699,050; sequence tables <= 1,280 cells/block and 81,920 across 64 blocks. Those derived finite bounds do not finish native Huffman/error-path work accounting. No tighter sequence profile is adopted here.

Current prototype native context arena is 95,968 bytes in the pinned build; output copying can temporarily retain 2A = 4,194,304 bytes, plus E/base64, parser, verifier, stack, interpreter and allocator state. A 1 MiB algorithm-state audit target is not a demonstrated portable process-memory ceiling. Workers' operational 128 MiB limits are not consensus predicates. WSL2 Linux uses RLIMIT_AS/seccomp and other controls; Windows Job Objects constrain resources but still lack production filesystem/network/privilege confinement. The two-request per-coordinator limit does not bound all coordinators or upstream retained work.

| Unresolved gate | A. Local implementation testing | B. Cross-node testnet activation of zstd/1 | C. Public deployment |
| --- | --- | --- | --- |
| Independent decoder and verifier review | Does not block inert format/storage/identity tests or controlled offline prototype experiments; label unreviewed code and use only disposable test state | Mandatory: independent algorithm agreement and independent parsing/sequence/FSE/repeat/Huffman/security review; same libzstd on two OSes is insufficient | Mandatory, plus maintained audit/dependency/vulnerability response |
| Native state/stack/work/error-path analysis | Can proceed alongside bounded offline tests; do not claim resource/security acceptance | Mandatory reviewed finite work proof/counters and implementation-state accounting, malformed paths, sanitizers/fuzzing and boundary vectors | Mandatory on every supported production runtime/architecture |
| Native Ubuntu testing | Not required to write local Windows code/tests; existing WSL2 evidence may inform development | Mandatory on the intended Ubuntu host/kernel/Python/service configuration; unsupported architectures fail closed | Mandatory repeatable deployment, load and recovery evidence; advertise only tested platforms |
| Production worker confinement | Offline tests may use documented prototype controls without keys, live DB or network authority; no unrestricted fallback | Mandatory audited confinement/resource/queue/credential policies on participating hosts; Windows needs its missing authority restrictions if supported | Mandatory service/identity/runtime immutability, aggregate resource controls, monitoring and incident procedures |
| Pre-bootstrap parent-death/cleanup guarantee | Test the gap in disposable experiments; no readiness claim | Mandatory launch-time/supervisor ownership and kill/reap guarantees, including parent death before bootstrap/READY, not just PDEATHSIG after it runs | Mandatory under real service failure/restart/OOM and coordinator multiplicity |
| Image-admission environment failures and separate media-worker isolation | Format/math/identity tests can proceed; image-admission acceptance must be marked blocked until reproduced/fixed; direct Pillow decode is not a substitute | Mandatory working isolated image admission and evidence binding on target hosts, correct local-failure classification, no weakened safety checks | Mandatory supported-environment regression, confinement, safe previews/animation and resolved owner activation policies |

The documented image blocker is `PermissionError [WinError 5]` at isolated worker `os.chdir()` into its temporary directory, flattened to `MALFORMED_MEDIA`; valid fixtures/frozen genesis bytes direct-decode. This decision uses the recorded diagnosis and does not claim a fresh reproduction or a fix. Codec worker isolation does not repair that independent media worker.

Timeout, OOM, worker crash, cancellation, saturation, missing OS controls or cleanup uncertainty means **unvalidated/local failure**: no vote/finalization, canonical commit, successful verified import or media body. Deterministically malformed/unsupported/over-limit/checksum/hash failures reject. Machine speed/RSS/wall time never defines consensus validity. A full dual-profile testnet activation must close the zstd gates; identity-only controlled development would require an explicit restricted registry decision and is not the planned dual-profile activation or a way to bypass media admission.

## 7. Development reset and migration implications

Plan for a **fresh development genesis/network identity and fresh versioned SQLite schema** after acceptance tests and explicit later reset authorization. This is the simplest launch path given the owner permits discarding the existing development chain. New launch metadata must bind registry/profiles, every numeric/schema bound, policy/statement/review versions and validator membership. Existing block hashes/finality signatures cannot be transplanted into the new format/network. Original-hash signatures only retain meaning if every signed domain/policy/context remains identical; this new context requires fresh evidence.

Archive a verified old-network snapshot and its supported reader before a later reset; inventory keys/wallet state/configuration and in-flight submissions/votes/nonces/queues, obtain an explicit disposition, and rehearse reset/restore on copies. Do not silently convert old finalized history or re-sign old records. Re-admit retained originals under the new policy if desired. Old-chain preservation is optional for this development launch, but old/new network separation and unsupported-version rejection are mandatory.

Keep schema version and protocol version separate. A new schema alone need not change R; a reset alone does not implement storage correctness or codec safety. If preserving history becomes required, stop the reset path and prepare a separately approved, tested migration with byte/hash invariants and rollback. No migration or reset is executed or scheduled here.

## 8. Remaining implementation sequence and acceptance tests

These are **future separately committable units**, not tasks begun here. Labels are sequencing aids after Task 7.9, not changes to previously completed task numbering. Security work may run alongside format work, but its activation gate cannot be skipped. Each implementation commit must preserve default nonactivation until the full launch audit.

| Unit / scope | Dependencies | Acceptance tests / evidence |
| --- | --- | --- |
| 1a. Freeze schemas, policies and launch vectors | Owner approval of section 9; resolve native/decimal adapters and finality bounds | Closed nested field registry; accounting for every required key; golden maximum-width/escaping/duplicate-key vectors; no floats/coercion; unchanged economic/quorum semantics apart from approved capacity restrictions |
| 1b. Canonical block-format parser/serializer/hash | 1a | One strict J(B)/R implementation; canonical equality, wrapper counted, identity/base64 remainder cases, unknown/missing/null/duplicate keys, depth and at/one-over scalar/sub-budget/block limits; old/new domains separated; no permissive `Block.from_dict` fallback |
| 2a. SQLite row adapter and atomic canonical state | 1b | Exact R BLOB round-trip, derived column checks, bounded range reads; no second chain/media copy; append/duplicate/reorg transaction failure injection; hash immutability; old schema left intact by default |
| 2b. Reset/bootstrap and optional migration tooling | 2a; explicit future reset authorization | Dry run on copies, version/network mismatch refusal, verified old backup/rollback, fresh genesis/state initialization, in-flight disposition; no live reset merely by installing code |
| 3a. Submission/admission block reservation | 1b; resolved image worker and closed evidence | 2 MiB incompressible identity with largest permitted mandatory evidence; text/caption escape extremes; certificate count/byte overflow; reservation invalidation; upload succeeds but certification refuses no-fit; mandatory media never depends on compression |
| 3b. Producer fit and transaction packing | 3a | Reward/header fixed before sizing, optional native/legacy count/record/array boundaries and deferred overflow, immutable snapshot, both profiles at E/A caps, final exact R/O checks; no lost mandatory data |
| 4a. Common v3 validation and consensus integration | 1b, 3b; reviewed decoder before enabling zstd | Full media/evidence/attestation/ledger/reward verification with one immutable decode result; same acceptance at candidate, normal reception and startup; deterministic invalid vs local failure; vote withheld on incomplete validation |
| 4b. Finality and canonical reorg integration | 2a, 4a; bounded proof schema | New-context attestations bind exact height/hash; equivocation/quorum vectors, maximum validator/proof sizes; finalize without R rewrite; refuse finalized detach; atomic claim/nonces/reward rollback on unfinalized branch replacement |
| 5a. Bounded peer synchronization | 2a, 4a–b | 64-record and 16 MiB caps including proof/wrappers, maximum blocks, truncated/malformed pages, target-tip/common-prefix changes, resume/restart, local worker failure, bounded memory without full-chain materialization; E preserved |
| 5b. Versioned streaming export/import and backup/restore | 2a, 4a–b | Complete R/E/launch/proof preservation, no double base64, bounded parser/archive expansion; corrupt/missing/unknown records rejected; interrupted import rollback; online-consistent backup/restore and portable export on a fresh node |
| 6. Media retrieval and original-byte integrity | 4a, 5b | Cache absent/corrupt, identity/zstd, text already canonical, byte-for-byte M/H/length/MIME and certificate agreement, corrupted E/checksum/descriptor rejects, local decoder failure returns no media; no resave/reencode |
| 7. Independent node interoperability | 4–6 plus independent decoder implementation/review | Two independently configured fresh nodes with same frozen inputs agree on R/hash, exact M, validation outcomes, balances/nonces, reviewer refs, reorg/finality and import/sync; compare independent decoder algorithm, not only platform wrappers |
| 8a. Decoder review/work/state hardening | Existing 7.6 artifacts; may precede 1b | Independent verifier/full-decoder audit, malformed/FSE/Huffman/repeat/offset fuzzing, sanitizers, native state/stack/error-path bound and work proof/counters; all frozen/boundary vectors; no silent profile narrowing |
| 8b. Production worker/service and image isolation | 8a; target-host service design | Native Ubuntu resource tests, pre-bootstrap parent-death/cleanup, immutable credential-free worker runtime, privilege/fs/network confinement, aggregate CPU/memory/process/queue bounds, kill/reap, unsupported setup fails closed; reproduce/fix image admission without weakening checks |
| 9. Storage/validation/economics benchmarks | 2–8, especially 5a/5b and native-host evidence | Section 5.4 measurements, byte/index/duplicate/WAL/backup accounting and load/recovery results; update 100/1,000/10,000/day model with uncertainty and adverse cases, including the 87-byte record wrapper |
| 10. Final release-readiness audit and activation proposal | Every prior acceptance gate plus owner launch decisions | Trace every ingestion/recovery/API path to exact validation; independently reproduce nodes from canonical data alone; restore/reorg/finality/burst/security regressions; review actual model limits; explicit signed-off launch/reset/deployment checklist and separate authorization |

Do not merge these into one compression/storage/consensus change. Isolated identity-format work can be tested locally before security completion; release configuration cannot enable a partially validated dual-profile path. Storage benchmark cutover approval precedes using the new layout as authoritative launch state.

## 9. Decisions still requiring approval

1. Adopt the recommended 2 MiB image / 256 KiB text / 2 MiB encoded / 3 MiB record limits, 320 KiB partitioned overhead, and exact field/collection restrictions as new-network policy. In particular approve the 16-votes-per-dimension snapshot bound/freeze behavior, transaction array bounds and canonical signature/time/nonce spellings; these narrow currently unbounded forms and require new signing vectors/policy digests.
2. Freeze the nested native transaction projection, schema-permitted nulls, decimal/tally adapter and its existing ASCII-escaped native aggregate preimage without silently changing ledger arithmetic or signature semantics. Freeze closed technical evidence, statement/animation/safety activation and other carried-over owner gates.
3. Approve finality staying out of R and the proposed 128-validator/256 KiB proof envelope, or choose another finite membership/proof budget before activation. Preserve quorum and validated validator-set trust semantics.
4. Accept the minimal hybrid SQLite direction, subject to measured adapter/index/backup results before cutover. BLOB-vs-TEXT may be selected on those measurements; no physical saving is promised.
5. Choose supported native Ubuntu/runtime/architecture and any Windows deployment support, security sign-off owners and service/cleanup guarantees. Independent decoder/security gates remain unresolved.
6. Approve the fresh-network identity/genesis and exact handling of old state/in-flight submissions in a later reset task; no reset/deployment approval is inferred from this report. Accept measured operating-volume/backup tradeoffs; representative 10,000/day still exceeds $100 on all modeled profiles.

## 10. Task 7.9 verification and disposition

Repository verification confirmed expected branch, separate Task 7.8/7.7 commits and clean initial state. Targeted source/report inspection covered canonical serialization, admission, certificate/votes/signatures, transactions, finality/reorg, persistence, backup/export and sync. Read-only arithmetic checks using compact sorted UTF-8 JSON confirmed base64 ceilings, 231/227-byte descriptor objects, 87-byte portable wrapper, disjoint overhead sum/21,844-byte margin and the Task 7.7 row totals. The existing Task 7.8 simulator was called in memory to reproduce baseline and explicitly hypothetical physical-amplification scenarios; no benchmark outputs were regenerated.

Documentation checks cover local links, UTF-8, trailing whitespace/final newline and `git diff --check`. No production test suite is warranted for this documentation-only decision; no new code tests or claimed runtime/security acceptance were substituted for the outstanding implementation gates. Final changes are this report and a short pointer in the existing architecture report; HEAD is unchanged, nothing staged/committed/pushed. Task 7.9 is ready for architecture review and a later authorized documentation commit. Production implementation and activation are not ready for sign-off.
