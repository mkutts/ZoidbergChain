# Milestone 7 Task 7.5 — Baseline Compression Codec and Security Contract

Status: design specification for review; no codec is activated. Task 7.5 selects **identity/1 plus zstd/1** as the initial strategy. Production readiness remains blocked by decoder work/state accounting, conformance, exact block overhead, and launch-policy freeze. This document supersedes the codec-selection placeholders and provisional size-policy conclusions in the [Task 7.2 protocol specification](milestone-7-compression-protocol.md); its canonical schema and hashing rules otherwise remain in force.

Date: 2026-10-18. Verified branch: `Compression-State-Bloat-and-Node-Economics`. Starting HEAD: `83e327c5e41e3d64b2c547e2fbb240eee7edf27d`, separately committed Task 7.4A. Initial worktree: clean. No applicable `AGENTS.md` was found in the repository or its ancestor directories. Scope: documentation and read-only investigations only; no production code/dependencies/limits, chain state, or Git history changes.

## 1. Evidence and authority

Read: [architecture](milestone-7-architecture.md), [protocol](milestone-7-compression-protocol.md), [corpus](milestone-7-corpus.md), [benchmark](milestone-7-compression-benchmark.md), and [image evaluation](milestone-7-image-compression-evaluation.md). Tasks 7.4/7.4A recommend this minimal strategy; they do not establish optimal compression for real-world images. JPEG XL was investigated but **not executed**. The synthetic corpus is neither an upload-population sample nor an independent holdout.

Source inspection reconfirmed the integration boundaries:

| Current source | Consequence for the future implementation |
| --- | --- |
| `block.py` consensus payload/hash builders; `protocol_v1.py` canonical JSON/domain envelopes | Current blocks hash raw hex-tagged bytes. The proposed v3 schema needs explicit parsing/hash paths, without permissive defaults or null dropping. |
| `services/block_production_service.py:build_candidate`; `services/block_validation_service.py` candidate/admission/chain validation | Production estimates size; validators expect raw-media blocks 1/2. Exact record accounting and the new decoder must protect every entry path. |
| `admission_certificate.py`; `media_integrity.py`; `media_technical_validation.py`; `media_admission_policy.py` | Evidence binds original hash/size/type. Current integrity reconstructs raw bytes, and version-filtered checks must not skip v3. Current policy still declares 256 KiB media and 512 KiB blocks. |
| `storage.py` section load/save; `storage_tools.py`; `storage_migration.py` | Chain JSON is authoritative; export/import/migration call current integrity checks. Preserve the exact encoding, not a recompressed equivalent. |
| `api_routers/public_chain.py`; `services/peer_chain_sync_service.py`; `peer_sync.py` | Retrieval returns verified original bytes today; sync currently requests the whole chain from height zero. Bounded v3 paging is required work, not an existing guarantee. |
| `services/canonical_reorg_service.py`; `services/finality_service.py`; `protocol_v1_finality.py` | Canonical claims/references follow the winning ancestry; persisted quorum-finalized identities cannot be detached. Finality authenticates height and block hash. |

MUST/MUST NOT below specify future consensus behavior unless explicitly labeled producer preference, local defense, candidate, or unresolved gate. Selection of a profile is distinct from activation. The future genesis/policy registry MUST bind all active profile rules and finalized limits; local configuration cannot redefine validity.

## 2. Versioned registry and identity encoding

Use the existing descriptor without adding fields: `encoding_version`, `codec_id`, `codec_version`, `original_size`, `stored_size`, `mime_type`, `original_sha256`, `payload`. Types, exact keys, strict padded base64, canonical JSON and duplicate-key rejection remain as specified in Task 7.2. Let M be accepted original bytes, E the decoded base64 payload, and H = lowercase hexadecimal SHA-256(M).

| Discriminator | Value/meaning |
| --- | --- |
| Protocol / media block / media encoding | `2` / `3` / `1`, respectively; current admission block version 2 is not protocol v2. |
| Identity profile | `codec_id="identity"`, `codec_version=1`; shorthand `identity/1`. E = M, nonempty; `stored_size == original_size == len(E)`; SHA-256 and media checks still required. No frame, flags or dictionary. Identity bytes may happen to begin with Zstd magic; never autodetect a codec. |
| Zstd profile | `codec_id="zstd"`, `codec_version=1`; shorthand `zstd/1`. One self-contained frame under section 3, not an encoder level or package version. |

Unknown/missing protocol, block, encoding or codec/profile versions reject before codec invocation. Integers exclude booleans, floats and coercible strings. No aliases, case folding, alternate wrappers, arbitrary parameter objects, executable decoders, remote decoders, plugins, dictionaries or fallback codec guessing. Empty M/E rejects for both profiles; a structurally valid empty Zstd frame is still invalid media.

Zstd level 3, `window_log=18`, checksum/content-size enabled, no dictionary and single-threaded encoding are the **default producer recommendation**, matching the benchmark. Other encoders/levels/thread counts are permitted when their actual output satisfies the profile. Validators need no encoder and MUST NOT reproduce the producer's compressed stream. Prefer identity when the complete canonical block with compression is not smaller or worthwhile; compression savings and level are not consensus tests. A larger valid E remains acceptable within every absolute limit.

## 3. Exact zstd/1 framing contract

The underlying normative grammar is [Zstandard format 0.4.3, pinned to zstd v1.5.7](https://github.com/facebook/zstd/blob/v1.5.7/doc/zstd_compression_format.md), narrowed by this profile. [RFC 8878](https://www.rfc-editor.org/rfc/rfc8878.html) provides additional framing descriptions; it does not override the pinned grammar or these stricter rules. Future extensions to that grammar are not implicitly accepted.

```text
E = magic[4] || frame_header || data_block{1..64} || content_checksum[4]
frame_header = descriptor[1] || window_descriptor[0..1] || content_size[1|2|4|8]
data_block = block_header[3] || block_body
```

Exactly the final data block sets `Last_Block=1`. All lengths and offsets must be checked against remaining E before reads, using overflow-safe arithmetic. Header fields, data-block structure and checksum all belong to E and are hash-committed.

### 3.1 Header acceptance

Required magic is exactly `28 b5 2f fd` (little-endian integer `0xFD2FB528`). Reject magicless/legacy frames and all skippable magic `0x184D2A50..0x184D2A5F`, even if they contain zero bytes. Only one frame is allowed; no preceding metadata frame, second frame, trailing padding, garbage or transport footer belongs in E.

Descriptor bits: 7–6 select content-size width; bit 5 selects single-segment; bits 4 and 3 MUST both be zero; bit 2 MUST be one (checksum); bits 1–0 MUST both be zero (no dictionary-ID field). In particular, reject a present dictionary-ID field even if its value is zero. These are deliberate profile restrictions, including the otherwise unused bit.

For content-size flag values 0/1/2/3, widths are respectively 1/2/4/8 bytes when single-segment is set, and 0/2/4/8 otherwise. Width zero rejects. Read little-endian; add 256 for the two-byte field. Other widths encode the value directly. Nonminimal permitted size widths remain valid; validators do not demand the default encoder's header. The resulting size MUST equal `original_size`, be nonzero, and satisfy A before any output allocation.

Single-segment frames omit the window byte and have effective window W equal to content size. Otherwise, for window byte exponent `e = byte >> 3` and mantissa `m = byte & 7`, compute `base = 1 << (10+e)`, `W = base + (base/8)*m`. Reject W > **262,144 bytes** before decoder creation/allocation. A single-segment frame larger than this window rejects even if a future A is larger; a larger original must use multiple segments under the same window ceiling.

### 3.2 Blocks, checksum and complete consumption

Interpret the three-byte little-endian block header: bit 0 is last-block, bits 2–1 are type, bits 23–3 are size. Types raw/RLE/compressed are allowed; reserved type 3 rejects. Raw/compressed bodies occupy size bytes; an RLE body occupies one byte, with size specifying output repetitions. Enforce the underlying format's per-block compressed and regenerated size bounds `min(W, 131072)`, entropy/table validity, sequence validity and references limited to available same-frame history. No initial tables, history or dictionary may be inherited from another operation.

This profile additionally limits a frame to **64 data blocks**, including empty blocks. This is a conservative design restriction against excessive tiny/empty-block overhead, not a benchmark-derived optimal value or complete CPU bound. It permits sixteen full 128 KiB blocks for the 2 MiB capacity scenario with room for smaller blocks; encoders emitting more blocks must choose another valid representation or identity. A structural pass can count these without decompressing by walking the length-delimited bodies. Reject the 65th header, missing final block, truncated body/header/checksum, or bytes beyond the four-byte checksum following the final body. This pass does not validate compressed internals and never substitutes for decoding.

The required checksum is the low 32 bits of xxHash64 of M with seed zero, stored little-endian. It MUST be verified. SHA-256(M) MUST also equal H; the checksum is not media authentication. Require output count exactly `original_size`, input consumption exactly `stored_size == len(E)`, and successful checksum/end-of-frame completion. Neither a correct hash nor apparently complete output excuses a missing checksum or unconsumed input.

Initialize each decode with **no dictionary or prefix**, even if a previous operation used one. An absent dictionary ID alone does not prove independence: Zstd can use unadvertised raw dictionaries. Any stream requiring such external state must fail under the empty context; never fetch a dictionary or retry with local data. No nested codec dispatch or recursive decompression of M.

### 3.3 Sequence/window validation clarification — Task 7.6A

The declared window and an implementation's allocation-window setting do not prove that actual sequence offsets obey that window. For every decoded sequence, resolve repeat codes under the pinned grammar and require `1 <= actual_offset <= W` and `actual_offset <= available_same_frame_history`, where history is measured at match start after the current sequence's literals. No dictionary/prefix exception is enabled. Preserve sequence tables and repeat-offset state across blocks only within the same frame. Raw/RLE blocks do not reset that state. Require each regenerated block's actual output to obey `min(W,131072)` and the remaining original-output capacity, including trailing literals.

These are clarifications of the existing pinned-format/history restrictions, not permission to narrow or relax zstd/1. Implementations may use a bounded sequence verifier or a checked native decoder; a header check or a successful release-libzstd reconstruction alone is insufficient. A backend/verifier disagreement is a local unvalidated failure. Independently demonstrated invalid offsets deterministically reject. Task 7.6A supplies exact-at/one-over window fixtures and preserves the Task 7.6 forged-offset reproducer.

Before an untrusted sequence-count loop, require `literal_count + 3 * sequence_count <= min(W,131072,remaining_original_output)` for that block. Every match emits at least three bytes. Thus total verified sequences are at most `floor(original_size/3)` (699,050 at candidate A=2 MiB), and each block has at most 43,690 sequences. Require the grammar's sequence-table modes/reserved bits and maximum FSE accuracy logs (LL/ML 9, offsets 8); no repeat table exists at frame start. At most three sequence tables are selected/rebuilt per compressed block, with at most 512+256+512=1,280 table cells per block, or 81,920 selections' worth of cells across 64 blocks. Reusing a table does not rebuild it. All such limits are derived from existing format/output/block bounds, not new arbitrary work thresholds or serialized descriptor fields.

The prototype's sequence/output/table counters do **not** close the complete native-work proof: Huffman/literal-table construction, malformed-stream native paths, stack/host overhead, independent verifier review, platform testing and worker isolation remain activation gates under section 5. A/B remain candidate policy values; this clarification does not finalize launch capacities or alter any active production pathway.

## 4. Installed binding investigation and required decoder adapter

Observed locally: CPython **3.13.5**, `zstandard` **0.25.0**, `cext` backend, linked libzstd **1.5.7**. These are benchmark/investigation dependencies, not newly approved production packages. Inspected installed `zstandard/backend_cffi.py` implementations of `decompress`, `decompressobj`, and `_ensure_dctx`, alongside [the versioned binding documentation](https://python-zstandard.readthedocs.io/en/0.25.0/decompressor.html). The selected C extension was tested directly; inspecting the alternate CFFI source does not establish its runtime conformance.

Read-only in-memory probe: compress `b"hello codec contract\n" * 32` with the section 2 settings (672 original bytes; 42 encoded bytes):

```text
28b52ffd64a001e50000a868656c6c6f20636f64656320636f6e74726163740a01001161359930399165
```

| Probe | Observed behavior, not an acceptance rule |
| --- | --- |
| Default `decompress(E + b"X")` or `decompress(E + E)` | Returns 672 bytes and ignores extra input. |
| `decompress(..., allow_extra_data=False)` on either | Raises unused-input error. |
| Valid E with `max_output_size=1` | Returns all 672 bytes. Declared content size drives allocation; this argument is not a general output ceiling. |
| `decompressobj()` with trailing byte / concatenation | `eof=True`, `unused_data` length 1 / 42. |
| `decompressobj()` with last checksum byte removed | Returns all 672 bytes but `eof=False`. Output alone does not prove a complete stream. |
| Checksum bit flip | Both tested interfaces raise a checksum error. |
| 300,000-byte single-segment frame; window setting 262,144 | One-shot returns all output; object streaming rejects excessive window. |
| Window setting 256 | Constructor rejects; 1,024 and 262,144 construct. Streaming permits the 300,000 window at setting 524,288, rejects at 262,144. |

The documentation labels the window argument in KiB, but installed CFFI source forwards it directly to `ZSTD_DCtx_setMaxWindowSize`, whose [libzstd API contract](https://github.com/facebook/zstd/blob/v1.5.7/lib/zstd.h) uses bytes; local C-extension behavior matches byte units. Also, window controls must not be assumed to cover all decoding modes. The protocol specifies W in **bytes independently of any binding argument**. Recheck units/enforcement for each production backend/version and preflight W regardless.

To reproduce the critical observations using the existing environment, run the following in `.venv/Scripts/python.exe`; the frames remain in memory. The positive probe's exact E above is an observation pinned to this toolchain, not a requirement on every producer:

```python
import zstandard as z
p = z.ZstdCompressionParameters.from_level(
    3, window_log=18, write_checksum=1, write_content_size=1,
    write_dict_id=0, threads=0)
e = z.ZstdCompressor(compression_params=p).compress(b"hello codec contract\n" * 32)
print(z.__version__, z.ZSTD_VERSION, z.backend, e.hex())
for label, data in [("valid", e), ("trailing", e+b"X"), ("concat", e+e),
                    ("truncated", e[:-1]),
                    ("checksum", e[:-1]+bytes([e[-1]^1]))]:
    for strict in (False, True):
        try:
            out = z.ZstdDecompressor().decompress(
                data, max_output_size=1, allow_extra_data=not strict)
            print(label, strict, len(out))
        except z.ZstdError as exc:
            print(label, strict, type(exc).__name__)
    try:
        obj = z.ZstdDecompressor().decompressobj()
        print(label, len(obj.decompress(data)), obj.eof, len(obj.unused_data))
    except z.ZstdError as exc:
        print(label, "object", type(exc).__name__)
big = z.ZstdCompressor(level=3, write_checksum=True).compress(b"X" * 300000)
print("window", z.get_frame_parameters(big).window_size)
for cap in (256, 1024, 262144, 524288):
    for streaming in (False, True):
        try:
            d = z.ZstdDecompressor(max_window_size=cap)
            out = (d.decompressobj().decompress(big) if streaming
                   else d.decompress(big, allow_extra_data=False))
            print(cap, streaming, len(out))
        except z.ZstdError as exc:
            print(cap, streaming, type(exc).__name__)
```

Required implementation boundary:

1. Bound and validate the descriptor/base64/E, parse the complete restricted frame header, check size/window, and walk block framing through the exact checksum end before decoding. `get_frame_parameters` is useful but does not expose every descriptor bit or prove frame consumption.
2. Use a fresh dictionary-free decoder with checksums enabled. Expose actual consumed/produced counts and terminal status. Prefer an audited adapter over `ZSTD_decompressStream` with caller-owned output capacity, or an independently verified equivalent. Feed no more than bounded E; disable reading across frames.
3. Give the decoder a total output capacity of exactly `original_size`, with bounded internal state. When that capacity is exhausted it must still be able to consume the checksum and finish without producing another byte; any required extra output rejects. Never decode to an unbounded buffer and check its size afterward. Check progress and handle incomplete input without a spin loop.
4. Require first-frame completion, verified checksum, full input consumed, exact output length and SHA-256. For an object API, require `eof=True`, empty `unused_data`, no outstanding input and total supplied input equal to E; do not let a stream reader's read-ahead hide trailing data. An API lacking a trustworthy consumption signal needs the independent structural end check and an audited equivalent terminal guarantee.
5. One-shot `allow_extra_data=False` is useful defense but does not establish output/window/state safety. `decompressobj(write_size=...)` controls chunk sizing, not a total output limit; the inspected implementation joins accumulated chunks. Neither interface is approved here as a complete production adapter. Hidden allocations, library behavior and error mapping remain an audit gate.

The probe is not an adversarial suite, performance benchmark, production decoder or independent-platform test. It supplies concrete reasons for the adapter requirements.

## 5. Resource policy, work and failure semantics

| Resource | Future contract / status |
| --- | --- |
| Original/output cap A | Mandatory finite genesis/policy value; candidate choices in section 6. Require `1 <= original_size <= A`, frame size equal to it, and stop before emitting byte `original_size+1`. |
| Encoded cap B | Independently mandatory finite value; reject `stored_size > B` and base64 length > `4*ceil(B/3)` before decoding/allocation. Exact encoded length/padding rules also apply. |
| Complete block cap C | Mandatory before launch, unresolved numeric value; exact canonical-record accounting in section 6. |
| History window | Hard profile ceiling 262,144 bytes for zstd/1, independent of A/B. |
| Frames / data blocks | Exactly one / 1..64 for zstd/1. Identity has no codec frames. |
| Internal block sizes/tables | Pinned format bounds, including maximum 131,072 regenerated bytes per block; check before dependent allocations. Working memory includes window, entropy tables, literals, input/output scratch and context. |
| Algorithm working state | Earlier 1,048,576-byte budget is a **candidate audit target**, excluding bounded E/M and host overhead. No portable accounting or safe universal implementation bound has been established. RSS/allocator totals MUST NOT decide consensus validity. |
| JSON / transfer | Retain proposed depth 32; chain pages at most 64 records and 16,777,216 application bytes including proofs/wrappers, both enforced. Bound transport/archive expansion and incremental parsing independently of E. These transport limits do not change block validity. |

Input/output/window limits, the 64-block cap, and fixed entropy grammar provide implementable structural defenses. A complete deterministic work counter is **unresolved**. The installed interfaces do not expose an agreed platform-independent count of entropy/table/sequence operations. Bytes, machine instructions, elapsed time and native allocation counts are not interchangeable. Do not invent a work formula or claim these probes prove a CPU ceiling.

Before zstd/1 activation, specify and independently verify either (a) semantic counters with exact increment rules, maxima and instrumented enforcement for every decoding path, or (b) a reviewed finite algorithmic work bound derived from the restricted grammar, block/table/sequence limits and bounded output, demonstrated for each decoder. Examine degenerate tables/bitstreams, many empty blocks, zero-progress loops, repeat-table state, invalid offsets, long matches and malformed data, including rejection paths. Any additional acceptance restriction requires a reviewed profile definition and vectors before freeze; published profile semantics must not drift. A local watchdog is useful scheduling protection, not a substitute for this gate.

Run native codec and media parsing in restricted workers without network, filesystem write authority, credentials or chain mutation access; bound concurrency, queues and process memory. Workers return bytes/counts/digests/status; the coordinator authenticates the result against the immutable block context and controls persistence/voting. Reset contexts between inputs; never share one context concurrently. Protect optional caches with exact block/representation/profile identity and bounded residency.

Deterministic malformed/unsupported/limit/checksum/hash/type violations reject the candidate. Timeout, OOM, worker crash, cancellation or saturation means **not validated / local processing failure**, not consensus-invalid. Withhold votes, finalization, imports and verified API bytes; discard partial buffers and retry/defer with backpressure or mark the node unhealthy. Never repair the stream, disable checksums, substitute cache bytes, fall back to identity or publish partial decoded output. Deterministic error categories should be stable; native exception strings need not match between nodes.

## 6. Three separate size limits and a block-fit guarantee

The existing production 256 KiB / 256 KiB / 512 KiB limits remain unchanged. The corresponding Task 7.2 numbers are **provisional candidates, not permanent launch rules**. For the new launch distinguish:

- **A — maximum original media:** len(M), after existing text canonicalization at submission; never image transcoding.
- **B — maximum encoded canonical media:** len(E), before base64, independently of A; not the whole media object.
- **C — maximum complete canonical block:** `len(C({"envelope": envelope, "hash": block_hash}))`; the serializer C here is the Task 7.2 canonical JSON function, distinct from the cap named C.

Corpus v1.1.0 has 27 synthetic images, original p50 10,474; p95 1,530,684; p99/max 1,772,761 bytes. The following counts use original byte lengths, not claims of technical admission (the isolated image worker has the previously documented Windows environment failure):

| Candidate A and B | Images fitting identity by bytes | Maximum base64 payload characters | Interpretation |
| --- | ---: | ---: | --- |
| 262,144 each (256 KiB) | 22/27 | 349,528 | Conservative baseline candidate; excludes five capacity examples. |
| 524,288 each (512 KiB) | 22/27 | 699,052 | No additional coverage in this corpus. |
| 1,048,576 each (1 MiB) | 25/27 | 1,398,104 | Excludes the largest noise JPEG and PNG. |
| 2,097,152 each (2 MiB) | 27/27 | 2,796,204 | Recommended image-capacity candidate for the next overhead/resource evaluation; covers this corpus with identity fallback. |

Recommendation: compare the conservative baseline against **A=B=2 MiB** before launch freeze, retaining the 1 MiB intermediate scenario. This is evidence for further measurement, not a finalized increase, a representative meme percentile, or proof that a node can safely validate the larger workload. Future text/media categories may retain smaller versioned caps. Window remains 256 KiB; a larger original does not authorize a larger history window.

Do not depend on compression to make an otherwise admitted original fit. Capacity originals / Zstd-3 encodings are 689,193/173,191 (JPEG gradient), 1,530,684/1,530,734 (JPEG noise), 1,772,761/1,772,817 (PNG noise), 625,250/625,279 (WebP noise), and 802,666/748,847 (GIF noise). Several expand. A=1 MiB with B=256 KiB admits only the gradient among these five by byte sizes, because the original and encoded limits are separate. This asymmetric option deliberately restricts incompressible content and is not the recommended image-capacity policy.

**Do not finalize C yet.** Even 512 KiB originals in identity mode need 699,052 payload characters, exceeding a 512 KiB block before any other fields. For A=B=2 MiB, C must exceed 2,796,204 plus all mandatory non-payload bytes; this is a lower-bound calculation, not a selected block cap. At the old 256 KiB candidate, 174,760 bytes remain under 512 KiB before descriptor/envelope/evidence/transaction overhead; availability of that budget is unproven.

Required measurement and enforcement work:

1. Serialize complete future records for every MIME with minimal and maximum permitted certificate/vote counts, evidence, attestations/signatures, hashes, headers, captions, reward/native transactions and all descriptor/envelope/JSON/base64 overhead. Bound identifier/string lengths and every evidence/transaction collection; averages or an example certificate cannot establish a maximum.
2. Define `Omax` as the measured-and-analytically-bounded maximum non-payload bytes for mandatory block contents, including all mandatory transaction/signature material. Optional transactions must have a separate packing budget. Check escaping/Unicode extremes and boundary scalar lengths using the actual frozen serializer and schemas.
3. To guarantee every policy-admissible original fits using identity, finalize B >= A and C >= `4*ceil(A/3) + Omax` for each allowed policy case. Alternatively, before admission is certified/reserved, deterministically reject any submission/evidence combination whose mandatory identity candidate cannot fit, and document that narrower admission rule. Media-size eligibility alone is insufficient. Frozen evidence must not grow after a fit reservation without rechecking.
4. Measure validator memory/work, worst-case identity traffic, bounded sync pages, import/restore and storage on the larger candidates. Measure optional finality/proof transport separately: Task 7.2 keeps finality proofs outside the canonical record, so do not silently add them to the hash/size formula. Their signatures/proof wrappers still need independent application-response budgets. Any future in-record signature counts toward C.
5. Enforce exact complete-record size at production, reception, validation, sync, import, restore and startup. Pack/omit optional transactions only; never truncate media, signatures or mandatory evidence. Add exactly-at/one-over vectors and admission-to-mint fit tests. Until this is implemented, no guarantee of accepted-submission block fit exists.

## 7. Threat model and validation order

Attackers control uploads, descriptors, encoded blocks, peers and import/archive files, and may replay different branches. Consensus agreement, exact reconstruction, availability, decoder isolation, evidence and duplicate/reward integrity are protected assets.

| Threat | Required defense / remaining condition |
| --- | --- |
| Decompression bomb / excessive decoded output | Check A and declared frame size first; hard output capacity/count; high compression ratio alone is not invalid. |
| Excessive memory / oversized window | Header preflight W; bounded E/M/scratch; no dictionary; safe table allocation. Portable state bound remains an activation gate. |
| Pathological bounded-output streams | 64-block cap and full grammar checks; deterministic work proof/counters still unresolved. Local watchdog never defines chain validity. |
| Truncation / corrupted checksum / wrong H | Full terminal/checksum/input/output checks, then original SHA-256. No verified prefix responses. |
| Multiple/skippable frames / hidden bytes | Magic/profile checks, structural frame end and exact consumption; disable multi-frame mode. |
| Malformed descriptor/base64/header | Closed schema, exact scalar types/keys/versions, strict base64 and sizes, flag restrictions, bounded parser. |
| MIME/container/metadata mismatch | Check reconstructed M against frozen media policy and evidence; MIME is authenticated but not included in H. Compression is not media-safety evidence. |
| Same original, different E | Original H uniqueness against candidate ancestry, atomically with submission/certificate/reward claims; no codec-specific duplicate key. |
| Sync/import/resource exhaustion | Same decoder boundary on every path; bounded pages/archives/queues and incremental verification, no trust shortcut for snapshots or local DBs. |
| Reorg / stale decode cache / representation substitution | Validate winning branch and chain-dependent evidence; cache by exact committed identity; preserve retained E and finalized identities, rebuild original-H claims atomically. |
| Native decoder fault / local timeout | Restricted worker, discard unverified results; local failure/defer semantics from section 5. |

Required validation sequence, shared by all acceptance paths:

1. Bound transport, JSON depth/strings/collections and exact canonical-record length; validate network/genesis/versions, closed schemas and cheap policy context. Validate strict base64 and encoded count before codec invocation.
2. Recompute the block commitment/linkage, check profile membership and descriptor ranges. For Zstd, perform section 3 header/framing preflight before allocating decoder resources.
3. Decode once with bounded state/output/work handling; verify checksum, termination, complete E consumption, exact M size and SHA-256. Identity uses E directly with the same size/hash checks.
4. Require MIME/type/metadata agreement and canonical text already equal to the accepted normalization. At submission, existing technical media validation operates on M before signing. During chain validation, verify the frozen technical evidence's deterministic policy/hash/length/type fields and admission signatures/references. Additional image/OCR worker screening must not introduce wall-clock-dependent consensus rejection. Existing image dimensions/pixel/frame rules remain independently applicable; compression does not waive them.
5. Verify certificate, attestation, votes, transactions, reward rules, original-H uniqueness and finality against candidate ancestry. Atomically persist exact E/metadata and canonical claims only after complete validation. A hash match or successful decompression alone never accepts a block.

## 8. Hash, signature and lifecycle interoperability

Original-media preimage is exactly M with no MIME, length, codec, JSON or domain prefix. Images retain every accepted file byte. Text is canonicalized only at submission under the fixed Task 7.2 trim/newline rule; block validation rejects noncanonical text instead of repairing it.

The block preimage remains exactly canonical UTF-8 `C(envelope)`:

```text
envelope = {"domain":"zoidbergchain/block/v2", "network_id":N,
            "object_type":"block", "payload":P,
            "protocol":"zoidbergchain", "protocol_version":2}
block_hash = lowercase_hex(SHA-256(C(envelope)))
record = {"envelope":envelope, "hash":block_hash}
```

P is the closed Task 7.2 v3 payload including the complete media descriptor, strict base64 E, certificate, transactions and other mandatory fields. N must be the frozen launch ID, not a literal placeholder. Every decoding-affecting value is authenticated by E/descriptor or the genesis-bound registry/policy. There is no unauthenticated local decoder option, redundant encoded hash or second canonical original-media copy. The record's hash field and external finality proofs are outside their own block preimage.

Two distinct valid E representations of identical M preserve **identical H** and normally produce different block hashes with otherwise identical fields (subject to SHA-256 collision resistance). All nodes compute the same block hash for the same record, regardless of their encoder. Submitter/admission signatures and certificate evidence bind H, length, type and signed context; certificates are digest-bearing evidence bundles, not new implicit producer signatures. Consensus/finality signatures bind height/block hash/network/domain, thereby authenticating E and metadata. Never reuse finality signatures after reencoding a block. Original-H duplicate detection prevents another mint/reward on one canonical ancestry, while alternative forks may contain distinct representations pending fork choice.

| Boundary | Required semantics |
| --- | --- |
| Original-media API | Return fully verified M, original MIME and length, block hash, media SHA-256 and integrity status. Preserve existing `X-Zoidberg-Block-Hash`, `X-Zoidberg-Media-SHA256`, `X-Zoidberg-Media-Integrity` meanings. Do not label storage Zstd as HTTP `Content-Encoding`. Integrity failure returns an error without media; local unavailability is retryable, not a successful unverified body. |
| Encoded/summary API | Complete canonical record carries exact E/descriptor/evidence. Summaries and compatibility aliases are explicit derived views, unsuitable for import or full validation. |
| Peer sync | Agree on network/genesis/protocol/registry/policy digest before bulk transfer. Preserve E exactly; bounded incremental pages, tip/prefix checks, resume and reorg validation. No shared encoder or transcoding negotiation. |
| Export/import/backup | Preserve complete encoded history, descriptors, hashes, evidence and required finality proofs plus launch/schema identity. Validate before advertising verified export and before atomic import/restore; unknown versions and missing payload reject rather than being skipped. Reconstruct with staging/cache absent. |
| Persistence/reorg | Store exact E keyed by block identity or equivalent exact-encoding reference, not solely by H. Retained blocks cannot be reencoded. Reconcile original-H claims/evidence/rewards on winning ancestry atomically and refuse finalized detachment. Optional local storage wrappers must reproduce the same E. |
| Upgrade/history/reset | Explicit activation by network policy is mandatory. Historical decoding uses the rules active at that block, not today's preferred encoder/limits. Retain decoders for launched history. A future authorized development reset creates new network/genesis/domain/policy contexts and fresh applicable signatures; never rewrite old finalized blocks. Old backups are archival, not new-launch state. No reset is performed here. |

## 9. Required golden vectors and independent verification

This task specifies the suite; it does **not** supply production-ready v3 vectors or claim the binding probes satisfy conformance. Every future fixture needs a stable ID, frozen registry/policy/limits and network context; exact M and E bytes (hex/base64 plus lengths/digests); descriptor; exact canonical preimage/record bytes; original/block/certificate hashes; test signing identities/messages/signatures where applicable; expected stage and deterministic acceptance/rejection category. Negative fixtures must isolate the intended fault where possible. Record encoder/backend/library/OS/architecture and generation commands for provenance, but never require reencoding to reproduce E. Commit fixture bytes and their manifest digest; no timestamps, random seeds or unspecified generator versions may enter expected bytes.

| Vector group | Required positive and negative cases |
| --- | --- |
| Identity | Each permitted MIME; one-byte canonical text and each base64 remainder; exactly A/B and one-over; E=M size equality; empty original and empty payload reject. Binary codec-level boundary bytes may be valid for framing but still invalid as MIME media; label layers separately. |
| Valid Zstd | Raw, RLE and compressed blocks; single/non-single-segment; every permitted content-size width and nonminimal width; windows at/below ceiling; exactly 64 blocks; valid non-default encoder output; small high-ratio output; equal/larger-than-identity encoding within caps; representative boundary M, streaming across chunk boundaries. |
| Magic/frame structure | Invalid/magicless/legacy magic, every skippable magic including zero length, skippable prefix/suffix, second frame including an empty second frame, trailing zero/garbage, absent last block, 65 blocks, reserved block type, every truncated header/body/checksum boundary. |
| Header/dictionary | Both forbidden bits separately, missing checksum, absent/false content size, inconsistent frame/descriptor/output size, illegal window and single-segment window above limit; dictionary flags 1/2/3 including explicit ID zero; nonzero dictionary ID; unadvertised raw/prefix dictionary dependency; no state leakage between decodes. |
| Corruption/output/work | Bit-flipped checksum/content, output overrun and underrun, bad tables/repeat state/offsets/sequence streams, excessive regenerated block size, pathological empty blocks/table rebuilds/long matches, exactly-at/one-over any finalized work/state limit. Truncated input that emits all M still rejects without EOF. |
| Descriptor/media | Unsupported versions/codecs; boolean/float/string integers, null/missing/extra/duplicate keys; invalid base64/pad bits/length; wrong H; unsupported or mislabeled MIME, malformed media, evidence/type/length mismatch, illegal metadata; text normalization/UTF-8/trim edge cases. |
| Identity/commitments/signatures | Same M as identity and two distinct valid Zstd encodings: equal H, distinct block hashes. Nodes agree on exact preimages and verify frozen test signatures/certificates/finality for each record. Mutations of E/metadata/network/certificate change hashes or reject. Wrong-hash signatures and old-context replays reject. |
| Duplicate/branch | Reencoding and MIME relabeling cannot bypass H claims or earn another reward; concurrent acceptance is atomic. Branch-specific claims rebuild on reorg; retained E unchanged; finalized detachment rejects; stale cache keyed only by H must not authorize another E. |
| Sync/portability | Identical records/hashes after peer paging/resume, JSON/SQLite round trip, export/import, backup/restart without caches. Wrong registry/network, missing/corrupt payload, unknown history version, archive expansion, page caps and interrupted atomic writes fail safely. |
| Decoder/API/local failure | Default prefix-success interfaces cannot pass trailing/concatenation vectors; bounded output before allocation; window-unit regression; decoder enabled without encoder installed; OOM/timeout/crash/cancel -> unvalidated with no vote/persist/media response. API returns exact M and integrity headers. |
| Admission/block-fit | Worst mandatory certificate/evidence/signature and metadata combinations with identity at A; exact C and C+1; optional transaction packing; no accepted fit reservation becomes unmintable as frozen evidence changes. |

Production readiness requires a second **independent decoder implementation** (two wrappers of the same libzstd do not establish algorithmic independence), plus supported Windows/Linux and architecture coverage. For every identical E, compare validity, output bytes, input consumption, size/window interpretation, checksums, hashes and signed-message verification. Signers may differ in nonce/signature production; verification and signature preimages must agree. Vectors must also be replayed through real sync/import/restore/validation boundaries, not just codec APIs. Publish exact toolchain/build versions, commands, manifest digests and results; investigate every disagreement before activation. Software/library security updates must rerun conformance; a change in accepted bitstreams requires explicit protocol review, not silent acceptance drift.

## 10. Extensibility and remaining blockers

Registry entries bind `(codec_id, codec_version)` to immutable grammar/restrictions and versioned policy/resource requirements. A better encoder emitting valid zstd/1 frames needs no new consensus algorithm or reward rule. A new algorithm or incompatible acceptance rule requires an explicit upgraded profile, approved non-executable registry data, audited decoder implementation, security/resource contract, vectors, independent verification and coordinated activation. A package upgrade alone never registers a codec. Preserve old profiles for historical verification under their original rules.

A future open-source compression bounty may compare better encoders against the versioned public corpus and a separately governed rights-cleared independent holdout, with byte-exact reconstruction, full-record costs and independent resource measurement. Candidate algorithms run only in isolated evaluation infrastructure until a protocol upgrade approves them. No reward logic, arbitrary submitted code execution, decoder downloading or executable codec loading is introduced here.

Remaining implementation/launch blockers:

1. Audited decoder adapter with proven consumption, output/window/checksum enforcement and bounded native allocation; resolution of backend/unit behavior.
2. Reviewed deterministic work proof/counters and portable working-state accounting; the earlier 1 MiB target is unvalidated.
3. Broader rights-cleared real-world image evidence; final A/B choice, full mandatory-overhead bounds, final C and admission-to-block fit guarantee.
4. Actual golden fixtures, independent decoder/platform results, adversarial tests and lifecycle round trips.
5. Versioned production schema/hash/admission/storage/API/sync/import/reorg integration; bounded paging and atomic persistence; frozen launch/genesis/network/policy/registry/signing contexts. Existing Windows image-worker isolation failure remains a separate validation-environment blocker.

These block activation and launch, not review/commit of this design. No next task is begun by documenting them.

## 11. Task 7.5 verification record

Repository state and installed binding observations are recorded above. Capacity counts/base64 arithmetic were recomputed directly from the checked-in corpus manifest. Focused existing verification:

```text
.venv/Scripts/python.exe -m pytest
  tests/test_protocol_v1.py::test_bytes_are_deterministic_and_round_trip
  tests/test_protocol_v1.py::test_domain_separation_changes_bytes_and_hashes
  tests/test_protocol_v1_golden_vectors.py::test_canonical_serialization_vectors_match_runtime
  tests/test_protocol_v1_golden_vectors.py::test_block_vectors_match_runtime
  tests/test_milestone_7_task_7_4a_image_evaluation.py
  -q --tb=short -p no:cacheprovider
Result: 6 passed in 39.98s.
```

The checks establish baseline serialization/hash behavior and existing image-evaluation reproducibility only, not conformance of the unimplemented v3 codec contract. Local in-memory probes checked the binding behaviors in section 4; no new full benchmark was run. Documentation checks cover local links, UTF-8/final newline/whitespace, the probe frame/header/size/hash arithmetic, corpus capacity counts, and `git diff --check`, including separate checks for the new untracked document. Final intended worktree: only this new document and the modified compression protocol specification; HEAD unchanged at `83e327c5e41e3d64b2c547e2fbb240eee7edf27d`. No production changes, commits, staging, push, merge, reset, deployment or subsequent task work. Task 7.5 is ready for design review and a later authorized commit, subject to the activation blockers in section 10.
