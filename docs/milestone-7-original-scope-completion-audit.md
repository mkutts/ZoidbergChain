# Milestone 7 Task 7.18 — Independent original-scope completion audit

Audit date: 2026-10-28, America/New_York. Audited branch:
`Compression-State-Bloat-and-Node-Economics`. Audited HEAD:
`2752e0eb7b7a89cace6c9adf61a38a12dad61883`.

## 1. Executive verdict and scope

**Original Milestone 7 acceptance: INCOMPLETE.**

**Production/network activation readiness: BLOCKED.**

Do not close Milestone 7 now. Substantial executable work exists: a seven-profile
codec comparison, deterministic corpus, adaptive producer, strict decoder and
workers, frozen canonical v3 format, isolated persistence/recovery and admission
laboratories, block instrumentation and a reproducible three-year simulator.
These are real implementations, not merely specifications. However, a current
submission cannot traverse adaptive compression into the active blockchain,
active full-node verification, persistent storage and public retrieval. The
representative-production and metadata-target evidence is also insufficient,
and several documented reproduction commands fail at this HEAD.

This conclusion does **not** depend on implementing the later BFT review journal.
The original contract supplied by the owner is the authority: benchmark suitable
lossless codecs; store algorithm, sizes, MIME and original hash; reconstruct
exact originals; project 100/1,000/10,000 blocks/day for three years; measure
database/media/index/backup/bandwidth; apply compression adaptively; report
representative overhead; expose assumptions for $100/month or disclose misses.
MODEL A requires the original accepted media to remain recoverable from canonical
on-chain data. No off-chain media substitution was found in the audited designs.

The original wording does not explicitly demand a public launch or chain reset
to accept a benchmark/model deliverable. It **does** say to store the compression
metadata and apply adaptive compression to accepted media. An unregistered,
test-only admission/store path does not establish those application behaviors.
Thus this is more than a separate launch-approval deficiency. If all original
behaviors and evidence were complete, network activation could still be BLOCKED
independently; that is not the evidence at this HEAD.

## 2. Preconditions, inventory and preservation

Before any audit writes, `git branch --show-current`, `git rev-parse HEAD`,
`git status --porcelain=v1 --untracked-files=all`, `git log` and `git ls-files`
were checked. Branch matched; status output was empty, including untracked
files. No applicable repository or ancestor AGENTS.md was found. No delegation
was used. The previous stopped attempt's staged state is resolved.

Task 7.17S is separately committed at HEAD, commit title
`Milestone 7 Task 7.17S: verify cryptographic review journal evidence`:
its report, wire-contract amendment, test module,
`tests/fixtures/review717s_v1/vectors.json`, and all twelve
`verification/review717s/` code/evidence files are tracked and present.
Its focused tests are included in this audit's execution record.

The tracked inventory and SHA-256 of every preexisting tracked file are retained
in [execution.json](../verification/task718/execution.json). The relevant groups
are:

| Evidence family | Tracked artifacts inspected |
| --- | --- |
| Corpus/comparison | `scripts/milestone_7_task_7_3_corpus.py`, `7_4_benchmark.py`, `7_4a_image_evaluation.py` under the same prefix; corpus manifest and benchmark/image configs under `tests/fixtures/`; raw 7.4/7.4A JSON; corresponding tests and reports |
| Decoder | `codec_prototype/strict_decoder.py`, `sequence_verifier.py`, isolated coordinator/IPC/Windows/Linux worker modules; codec-v1/v2 vectors and checksums; 7.6/6A/6B/6C/6D scripts, tests, raw JSON and reports |
| Canonical format/storage | Entire `canonical_v3/` package; frozen `milestone_7_v3_v1` fixtures; 7.10C vectors/conformance scripts and tests; 7.11 storage runner/results/tests; 7.13–7.16 admission, issuance, history and atomic laboratory tests/reports |
| Composition/economics | 7.7 and 7.8 scripts/tests, versioned configs, raw JSON, monthly CSV, block-composition and node-economics reports |
| Active application | `api_routers/content.py`, `public_chain.py`, `content.py`, `media_technical_validation.py`, `media_admission_policy.py`, `media_integrity.py`, `admission_certificate.py`, `block.py`, `blockchain.py`, `storage.py`, relevant production/validation/content/sync services |
| Later journal | 7.17P/Q/R/S specifications, fixtures, calculators/verifiers, raw results, tests; evaluated as a scope boundary, not as original compression completion |

Generated corpus binaries under `artifacts/` and the portable Linux replay bundle
`temp/task76d-inputs.json` are ignored, as confirmed by `git check-ignore`.
They are not secretly treated as tracked inputs. The corpus generator, manifest,
frozen hostile vectors, portable-bundle exporter and paired historical results
are tracked. On this reference Windows environment the exact 36 original byte
sequences can be regenerated. The historical Linux bundle is not committed and
must be exported from a matching reference encoder stack; native Linux encoder
byte portability is not established. No published result was overwritten.

Only this audit and `verification/task718/` are deliverables. Disposable test
databases and temporary worker directories are under ignored temporary paths.
No production database or live node was opened. No implementation, test, schema,
fixture, historical report, dependency, production configuration, index entry or
commit was changed. Final preservation/status checks are recorded in section 16.

## 3. Original requirement traceability

Commands below use `.venv/Scripts/python.exe -B` from the repository root.
`7_N` abbreviates the common `milestone_7_task_7_N` filename prefix only in this
table; the exact argv and outcomes are in execution.json and section 13.
“Pass in laboratory” never means acceptance by active nodes.

| Requirement | Implementation | Tests | Results / reproduction | Actual outcome and integration | Status / limitation |
| --- | --- | --- | --- | --- | --- |
| Scope 1: Zstd/Brotli/other codecs over text/metadata/code/media | Corpus, 7.4 and 7.4A runners | 7.3, 7.4, 7.4A tests | Frozen 7.4/7.4A JSON; `scripts/milestone_7_task_7_4_benchmark.py --output verification/task718/codec.json`; supplemental.py | Historical 252 rows; documented command refuses stale manifest; supplemental exact-source comparison runs independently | **PARTIAL**: all supported MIME categories covered, synthetic/very small text/code corpus |
| Scope 2: durable algorithm, original/stored size, MIME, original hash | `canonical_v3/media.py`, block.py, storage.py | 7.10C, 7.11 | Frozen v3 vectors; isolated storage runner/output | Closed descriptor serialized, hash-bound and retained/reopened; no active v3 import | **PARTIAL** overall; laboratory implementation PASS |
| Scope 3: reconstruct exact original | strict decoder, media.reconstruct, block.reconstruct_record_media, V3Store | 7.6/6A/6C/6D, 7.10C/7.11 | 7.6–6D JSON; storage.json; supplemental strict 72 streams | Exact equality/hash demonstrated; active chain supports raw bytes only | **PARTIAL** overall; tested correctness PASS, universal production guarantee unverified |
| Scope 4: three-year tooling at all three rates | 7.8 node_economics.py | 7.8 tests | 7.8 config/JSON/CSV; `--output verification/task718/economics.json --csv verification/task718/economics.csv` | Simulator JSON and CSV reproduce exactly | **PASS** as explicitly bounded historical analytical model |
| Scope 5: primary/media/index/snapshot/backup/bandwidth | 7.7, 7.11, 7.8 | 7.7/7.11/7.8 tests | Frozen composition/SQLite results; new storage/economics outputs | SQLite totals measured, snapshots/backups/traffic modeled; separate index bytes unavailable | **PARTIAL**: dbstat absent, no measured backup/network population, snapshot/headroom costs omitted |
| Addition 6: apply adaptively by media type | media.produce; admission.prepare; construction bridge | 7.10C/7.13 tests | supplemental and 7.11 result; `pytest` v3 group | MIME allowlist/caps plus per-object complete-descriptor comparison; 26 zstd / 10 identity | **PARTIAL**: real isolated code; not active submission/consensus/storage |
| Addition 7: realistic JPEG/WebP/video expectations | identity fallback and image evaluation | 7.4/7.4A/7.10C/7.13 | 7.4/7.4A JSON, supplemental | Expansions retained in raw results; identity fallback measured; video unsupported | **PASS** for measurement/policy honesty; application integration remains partial |
| Addition 8: representative p50/p95/worst overhead | 7.7 component accounting; supplemental frozen-R accounting | 7.7 and 7.10C budget tests | 7.7 JSON; supplemental.json | Percentiles calculated with full certificate/signatures, but no production population | **PARTIAL**: numerical evidence exists; production-like representativeness lacking |
| Addition 9: backup/snapshot/transfer costs beyond disk | 7.8 simulator | 7.8 tests | Config and identical reproduced 36-month grid | Full backup storage/upload and propagation charged; snapshot and workspace only counted as bytes | **PARTIAL**: published totals conditional on unpriced capacity |
| A: realistic roughly 60–80% text/metadata/code saving | Executed codec operations | 7.4 tests plus supplemental assertions | Per-category codec table below | Structured JSON compresses well; aggregate text hides much weaker tiny code/text cases | **PARTIAL**; no universal category-level target demonstrated |
| B: never select a larger representation | media.produce, complete canonical descriptor comparison | producer/fallback tests in 7.10C/7.13 | supplemental / frozen v3 vectors | Local producer selects strictly smaller descriptor; validators deliberately permit larger valid zstd encodings | **PARTIAL** overall; default producer PASS, no network-wide no-expansion invariant |
| C: measured overhead targeting <15% | 7.7 + frozen-R instrumentation | 7.7/7.10C | Tables below | Synthetic equal-block p50/p95/worst exceed 15%; large-byte weighting masks this | **FAIL** to demonstrate target attainment; production-population compliance NOT VERIFIED; measurement itself exists |
| D: explicit $100 assumptions or transparent miss | 7.8 simulator and config | 7.8 tests | Identical simulator outputs; audit sensitivity | Provider/workload-specific pass/fail disclosed, with unpriced capacity corrected separately | **PARTIAL** for complete node economics; historical scenario arithmetic PASS |
| E: every compressed accepted object exact + original hash | strict decoder + canonical media/storage adapters | decoder/v3/store tests | 72 exact worker round trips, signed persisted fixture recovery | Correct within tested inputs; no compressed object is accepted by active nodes today | **PARTIAL**; not a vacuous production PASS |
| F: reproducible reports/raw corpus/commands/environment | Tracked generators/configs/results; locked benchmark dependencies | corpus/composition/image and evidence tests | execution.json and logs | Exact bytes, codec sizes, SQLite and simulator reproducible; original corpus/benchmark/composition commands fail | **FAIL** for current documented command reproducibility |
| MODEL A: full original recoverable from canonical data | active raw media + isolated descriptor/BLOB | v1, media-integrity, decoder and v3/store tests | canonical-only recovery; no cache needed | Original bytes retained or losslessly encoded in canonical record | **PASS** for audited storage design/correctness; activation/security qualified separately |

## 4. Corpus coverage and representativeness

Frozen corpus: `zoidbergchain-media-benchmark-v1`, version 1.1.0. Manifest
SHA-256: `d872a8669cad218b72e5dbcf1dfbbff4de8718fc48c37f4950bf7dc46bff121f`.
There are **36 objects / 6,093,917 original bytes**. Exactly 31 are primary scoring
objects; five oversized images are capacity-only under the historical 256 KiB
cap. All 36 fit the isolated 2 MiB image / 256 KiB text limits.

| Category / MIME | Objects | Original bytes | Size range, bytes |
| --- | ---: | ---: | ---: |
| Plain text / text/plain | 3 | 3,287 | 36–2,852 |
| JSON/metadata / text/plain | 3 | 14,871 | 110–11,814 |
| Source code / text/plain | 3 | 1,134 | 126–545 |
| JPEG / image/jpeg | 7 | 2,500,693 | 3,530–1,530,684 |
| PNG / image/png | 7 | 1,795,174 | 638–1,772,761 |
| WebP / image/webp | 7 | 904,502 | 376–625,250 |
| GIF / image/gif | 6 | 874,256 | 652–802,666 |

Image original-size nearest-rank p50/p95/max: **10,474 / 1,530,684 / 1,772,761 B**.
Images span 320×180 through 1280×720 and 1024×768, including seeded noise,
caption-heavy rasters, gradients, illustrations and limited animation. Text is
repository-authored plausible chain data/source, not repeated padding. Every
image is synthetic and emitted by one pinned Pillow/native encoder stack.
There are **zero rights-cleared real-world production uploads** and no empirical
traffic weights, held-out population, photographic diversity or substantial
source modules. This is useful stratified functional coverage, not sufficient
production representativeness.

The current technical validator/policy allowlists cover `text/plain`,
`image/jpeg`, `image/png`, `image/webp`, `image/gif`, subject to content,
canonical-text, size, container and activation rules. JSON/source are benchmark
subcategories of text/plain, not separately accepted JSON or script MIME types.
No supported MIME is absent from the corpus. Video/audio are unsupported by the
active code, rather than omitted supported categories. This is an inspected code
inventory, not a claim that a public network's mutable launch policy was queried.

The accepted “original” for text is the canonical UTF-8 sequence accepted and
signed by admission, after upload normalization. Task 7.11 normalizes its nine
text fixtures before constructing canonical v3 records: totals become
**6,093,910 B**, seven bytes below the source corpus. Encoded totals become
5,285,229 B rather than historical 5,285,234 B. Both source and accepted hashes
are retained in supplemental.json. Codec comparison uses the **unchanged source
bytes**, not this normalized format workload. No silent corpus substitution.

## 5. Codec comparisons and actual selection

Frozen Task 7.4 compares identity, Zstd levels 3/6/9, Brotli qualities 4/6 and
zlib level 6: 36×7=252 raw rows. The supplemental audit repeats those operations
only after verifying every source length/hash against the unchanged manifest.
Its category-specific bytes, ratios, reductions, encode/decode timings and
expansion counts are appended below and retained per object in supplemental.json.

Configuration: Zstd has one frame, checksum/content size, no dictionary,
window_log=18 (256 KiB), threads=0; Brotli uses generic mode, lgwin=18; zlib has
wbits=15. Timings use two warmups and nine repetitions, perf_counter_ns, medians
and nearest-rank p95. Summed category medians are local operation time totals,
not end-to-end validator latency or service capacity. Native codec peak memory
is unavailable in the comparison; Python allocation tracing would miss it.

Historical adaptive **descriptor** savings, including base64/framing, primary
scoring / all text, respectively: Zstd-3 35.21% / 81.07%; Zstd-6 35.76% / 81.50%;
Zstd-9 35.77% / 81.53%; Brotli-4 37.22% / 81.90%; Brotli-6 38.39% / 82.76%;
zlib-6 35.58% / 80.64%. These are not raw category reductions or whole-block
savings. Historical aggregate encode/decode MB/s: 642/4,113, 267/3,947,
247/4,047, 134/638, 39/619 and 74/464 in that same order.

Identity plus **zstd/1**, default level 3, is the implemented isolated producer
strategy. Brotli's slightly better corpus size trades much slower encoding and
another decoder dependency; higher Zstd levels add little primary-score saving.
The codec version is a frame/acceptance profile, not an encoder level. Other
conforming encodings are permitted. JPEG XL was investigated in 7.4A but not
executed; missing cjxl/djxl/jpegtran and no audited binding are recorded blockers.
Pixel-preserving transcoding or metadata stripping cannot meet original-byte
identity and is not credited as lossless storage evidence.

Zstd-3 raw expansions occur in JPEG 1/7, PNG 1/7, WebP 2/7, GIF 5/6 and one tiny
text. The noisy JPEG expands 1,530,684→1,530,734 B; PNG noise expands
1,772,761→1,772,817 B; WebP noise expands 625,250→625,279 B. Identity fallback
prevents those local selections. The synthetic JPEG aggregate's ~28.44% raw
saving is not a real JPEG-traffic forecast: six low-structure images compress
strongly, while a single noisy image contains over 61% of JPEG bytes. No demand
for 60–80% JPEG/WebP/video saving is imposed.

## 6. Adaptive path and active application boundary

| Stage | Active application at audited HEAD | Isolated implemented path |
| --- | --- | --- |
| A submission | content router → ContentCoordinationService upload; signed submission, review and mint queue | Explicit TestOnlyConfig/dependencies only; no public route |
| B originals | accepted exact image bytes / canonical text | Adapter takes ValidatedMedia and frozen application certificate |
| C MIME/safety | validate_media_bytes detects/validates MIME, container, dimensions, frames, caps | Adapter reruns existing byte validation and evidence bindings |
| D–F selection/compression/fallback | No codec selector or compression call | media.produce attempts Zstd for allowed MIME, compares complete canonical descriptors, verifies identity fallback |
| G metadata | raw media_bytes, media/content hash, MIME and technical evidence | Closed eight-field descriptor + signed certificate bindings |
| H block creation | BlockProductionService.build_candidate selects block version 1/2 and raw stored_bytes | BlockConstructionBridge creates exact canonical v3 R with budgets |
| I persistence | Blockchain commit/save; storage_sections chain JSON and current indexes | V3Store immutable canonical BLOB, derived indexes; AtomicV3Store laboratory |
| J independent verification | BlockValidationService accepts current versions 1/2, recalculates original/hash and admission bindings | parse_record + reconstruct; isolated history/admission/atomic checks are explicit and limited |
| K retrieval | public_chain.download_block_media / media_integrity return hash-checked raw bytes | V3Store.get revalidates R; reconstruct_record_media uses worker output |

No active blockchain/service/router path imports canonical_v3 or codec_prototype.
The active validator explicitly rejects other current media block versions.
Therefore adaptive compression is specified **and implemented**, used in
test-only construction/persistence, but is neither accepted by active full nodes
nor stored or served through active production paths. No approved live version
transition or launch identity can be inferred from symbolic contexts in tests.
Existing v1/v2 parsing remains unchanged and was regression-tested.

Producer comparison is `len(J(compressed_descriptor)) < len(J(identity_descriptor))`.
Every other block field and fixed-width block hash has the same length, so this
is the complete-record size delta, not just raw-payload comparison. MIME selects
allowlist/caps; there is no separate tuned codec per MIME or promise of media-type
savings. Images may retain identity. Encoder failure/deterministic frame rejection
can fall back to worker-verified identity; a local decoder failure cannot be
masked. Received data is never recompressed by validators.

**No-expansion limitation:** this preference is not consensus validity. The frozen
tiny-original zstd block is 34,601 B, while identity is 34,588 B, both valid format
fixtures for the same original `b'a'`. Thus the default producer fulfills the
comparison but the protocol permits an expanding representation. Unsupported
codec/profile/encoding versions reject; codec sniffing and normalization of
received signed records are absent. Original SHA-256 stays invariant, while
block identity changes with the representation.

## 7. Exact reconstruction and hostile-input evidence

strict_decoder validates closed descriptor fields, strict canonical base64,
stored/original bounds, exactly one supported Zstd frame, mandatory checksum and
declared content size, no dictionary, window <=262,144, <=64 blocks and complete
input consumption. It verifies sequence offsets/window/history and reconstructed
block lengths before bounded native reconstruction. SHA-256 is computed over
the decoded original, not the compressed frame or MIME label. The coordinator
also authenticates returned bytes/count/hash; canonical_v3 adds canonical text
and signed original-hash/size/MIME bindings.

Tests include empty original/payload rejection, one-byte/small identity and Zstd,
high entropy, maximum original/encoded sizes, very high expansion, corrupt
checksums, truncation, forged sizes/hash, output over/underrun, dictionaries,
unknown modes, noncanonical base64, trailing/skippable/concatenated frames,
64/65 blocks, offsets at/over window and malformed sequence/FSE data. Empty media
is invalid rather than a positive round-trip case. Boundary-format images are
not automatically safe images or admission-valid records.

Native output allocation is bounded to declared size <=2 MiB; native arena guard
is 1 MiB; frame window is 256 KiB. Derived sequence count <=floor(original/3)
(699,050 at 2 MiB), <=43,690 per block and bounded FSE table work are checked.
These do not prove every malformed Huffman/native error path, stack or total
work property. Workers default to 128 MiB local limit, five CPU seconds, ten
execution-wall seconds, five startup seconds and two coordinator slots, no queued retry.
Local time/resource/backend failures remain INDETERMINATE_LOCAL_FAILURE, not a
consensus invalidity verdict. Operators must bound coordinators and ingress too.

Windows Job Object resource/process containment was tested; it is **not**
filesystem/network/privilege confinement. Linux x86_64 worker implements
resource limits, no_new_privs, a default-deny seccomp policy and parent-death
handling. Historical Ubuntu 24.04/WSL2 evidence is paired with Windows requests;
it shares the same strict/libzstd algorithm, not an independent full decoder.
Native Ubuntu, ARM64, other runtimes and deployment hardening remain unverified.
The trusted pre-confinement runtime/import boundary and allowed syscall/native
attack surface still require independent security review. No such independent
review is recorded here. AtomicV3Store additionally refuses WAL on this host's
SQLite version under its own runtime gate; skipped WAL crash tests are not passes.

Distinctions: **A byte correctness PASS for tested inputs; B tested hostile-input
hardening PASS with bounded scope; C independent native/security/platform proof
NOT VERIFIED; D production-safe integrated decoder BLOCKED.** Source-only recovery
in V3Store needs canonical bytes plus authenticated context/trust anchors, not
upload/cache files. This is implemented and tested within laboratory authority;
format-valid signed fixtures do not establish accepted public-chain history.

## 8. Durable compression metadata and identities

| Required field | Exact canonical encoding | Serialization / validation / durability |
| --- | --- | --- |
| Algorithm/version | `codec_id`: identity or zstd string; `codec_version`: integer 1; `encoding_version`: integer 1 | media.descriptor/validate_descriptor; closed schema; unsupported values reject |
| Original size | `original_size`: integer 1..262,144 text or 1..2,097,152 image | declared original output/frame count, text cap and coordinator output checked |
| Stored size | `stored_size`: integer 1..2,097,152 | exact strict-base64 decoded length; identity additionally equals original size |
| MIME | `mime_type`: one of five exact strings | allowlist; text canonicality; separate admission container/technical evidence checks |
| Original content hash | `original_sha256`: exactly 64 lowercase hex characters | SHA-256(decoded original) checked; cross-bound to certificate/technical/attestation/review identities |

These are inside J(descriptor) → payload P → canonical block envelope B.
`block_hash=SHA256(J(B))`; stored portable record `R=J({envelope:B,hash:h})`
includes an exact 87-byte wrapper beyond J(B). V3Store stores exact R as a BLOB;
insert, reopen, lookup, integrity scan and retrieval revalidate original bytes
and derived indexes. No required descriptor field is transient-only in isolated
storage. Active raw-media block v1/v2 lacks this explicit versioned compression
descriptor; that unmet application integration is not cured by runtime objects.

Multiple conforming lossless encodings of M are valid. Media identity H is
SHA256(M); block identity commits the exact chosen encoding, descriptor and
evidence. High-S signature variation also changes block bytes without changing
the media hash. Validators verify bytes actually received and do not demand the
producer's default encoder output.

## 9. Metadata overhead and limits

Historical 7.7 measured **36 rows per representation**, five representations,
180 total constructed observations. Its v1/v2 serializer measurements are direct;
v3 was then a projected envelope with generated schema-shaped ten-vote
certificates and signature-sized placeholders, not issued/finalized blocks.
Its percentage excludes the entire serialized media member:
`100*(envelope_bytes - media_member_bytes)/envelope_bytes`.
Thus descriptor overhead is a separate diagnostic, not included in that reported
“nonmedia” percentage. Current v3 portable R also needs its 87-byte wrapper.

| Historical representation | Nonmedia p50 | p95 | Worst | Byte-weighted |
| --- | ---: | ---: | ---: | ---: |
| Current v1 identity | 15.13% | 84.07% | 91.79% | 0.64% |
| Current v2 identity | 57.74% | 98.12% | 99.10% | 4.36% |
| Projected v3 identity | 66.28% | 97.43% | 98.12% | 6.30% |
| Projected v3 adaptive | 72.85% | 97.57% | 98.12% | 7.19% |

The projected representative-image subset has p50/p95/worst **64.39% / 95.59% /
96.94%**, byte-weighted 36.39%. Large-media v3 weighted nonmedia is 1.36%, so
the <15% goal is achievable for large payloads, not the typical equal-block
fixture. No tiny objects or negative results were discarded. No universal
production distribution or size qualification was defined in the original target.

Historical 36 projected adaptive envelopes total **7,602,184 B**:
serialized media 7,055,323; certificate 476,357 (includes signatures); transaction
members 34,594; header 7,695; structural metadata 22,311; envelope 5,220;
delimiters 684. Descriptor overhead is an 8,291-byte subset of media. Raw encoded
media totals 5,285,234 B. Reviewer signatures/evidence stay inside certificates;
signature subsets must not be added again. Finality proofs are external and
absent from these corpus fixtures; that omission is disclosed, not counted as
proof that finality is costless. The frozen standalone finality record is 880 B
and its one-validator proof fixture 1,194 B; these are format examples, not a
production validator-set/proof-size distribution. They are not silently added
as a universal per-block allowance in the media-only simulator.

Supplemental frozen-v3 measurement uses the **unchanged** Task 7.11 signed
fixture generator and canonical serializer, not the old projection. It partitions
36 exact R records, reports the certificate's votes separately as a subset,
native arrays, header, reward/transaction members, descriptor/framing, wrapper,
base64 contents and other canonical bytes. All components reconcile. Its exact
totals and percentiles are appended below.

For audit target interpretation, metadata is **R minus base64 payload content
characters** (therefore includes the media descriptor and all JSON framing),
divided by **R**. Base64 expansion is part of media representation, not silently
reclassified as original bytes. Also report metadata/original accepted bytes;
these percentages can exceed 100% for tiny media. Historical nonmedia/R is
provided too, so changing definitions cannot hide the target miss. The original
checklist did not freeze a denominator; metadata/full canonical bytes is the
usual block-share interpretation used for this verdict, with descriptor costs
included. The original-relative alternative does not rescue the small-block result.
Physical SQLite/index overhead is separate from all canonical percentages.

### Implemented limits and historical size discrepancies

| Limit | Active path | Isolated frozen v3 |
| --- | --- | --- |
| Original image / text | Policy declares 256 KiB each, technical validator enforces original admission limits | Image 2,097,152 B; text 262,144 B |
| Encoded media | Raw bytes, no compressed path | E<=2,097,152 B; canonical base64 length checked before decoding |
| Complete block | Policy declares 524,288 B; producer uses an approximate default 500 KiB estimate before full certificate/reward assembly; universal exact canonical-record enforcement absent | R<=3,145,728 B in encode/parse/store and construction |
| Evidence/other allocations | Current full evidence is not bounded by frozen v3 parent budgets | certificate<=196,608; native<=98,304; rest<=32,768 B |
| Decoder output/work | Raw-media image decode/pixel/frame/local defenses; no active Zstd decoder | 2 MiB output maximum; 256 KiB window; 64 blocks; bounded sequence/table accounting plus local worker limits |
| Other bounds | Do not infer proposed limits are current consensus | 32 votes total, 16/dimension, 4,096 B/vote; 10 native records, 8,192 B/record; caption 1,000 scalars/4,096 UTF-8 bytes; JSON depth 32 |

Exact caps and cap+1 cases exist in 7.10C/7.13 tests. The 3 MiB C-1/C/C+1 tests
probe the byte gate, not fabricated valid space-padded blocks. Tighter component
caps make an exactly-3-MiB valid record unreachable. Real-signature tests exercise
max-size image/caption and text, ten signed native transfers and construction
fit/one-byte-over behavior; maximum-image format probes are not production
admission proof. Separate finality record/message/proof caps are 1,536/1,024/
262,144 B with <=128 trusted validators in the isolated format, outside R.

Current `conservative_size_bound()` is **3,058,797 B**, leaving 86,931 B under
3 MiB: maximal base64 2,796,204; certificate bound 172,901; native array 81,931;
remaining widths 7,761. This includes the wrapper. Prior reports contain
3,123,884 (generic parent-budget sum), 3,115,183 (earlier top-level/parent-width
ceiling), 3,083,804 and 3,098,808 (different certificate/native/rational tightening
assumptions). These are different historical conservative bounds, not observed
valid maximum blocks. The current reward-only frozen implementation/test agrees
on 3,058,797; using an older number as its measured maximum would be wrong.
The 7.7 observed 2,379,140 B projection is yet another workload statistic, not a
worst-case proof. Later V4/C3/block4/review-journal fields are not added to this
frozen v3 budget or treated as approved active fields.

## 10. SQLite measurements and three-year storage

The new 7.11 reproduction matches every published non-environment JSON field:
36 closed v3 records contain **8,241,301 canonical BLOB bytes**. Post-checkpoint
DB is 8,376,320 B; post-VACUUM DB 8,372,224 B; observed pre-checkpoint WAL
9,377,152 B; consistent backup 8,376,320 B; empty schema 49,152 B. Post-VACUUM
excess over R is 130,923 B (1.589%), including schema/allocation/identifiers/
indexes, not a direct index-only measurement. dbstat is unavailable; index cost
is **unknown, not zero**. Four secondary indexes and WITHOUT ROWID primary keys
are present. The logical block-index value-width total is 7,200 B, not physical
B-tree pages. These are 36-record experiments, not million-block linearity tests.

Same-R minimal JSON-section control post-VACUUM is 8,261,632 B. Indexed BLOB is
**110,592 B larger**, not smaller. BLOB's observed WAL is 2,055,880 B lower for
different append/whole-section save sequences; no storage-class or universal
throughput claim follows. Against 7.7's different projection, v3 BLOB post-VACUUM
is 442,368 B larger. The projected old envelopes lacked 36×87=3,132 portable
wrapper bytes and had different certificate/transaction/context/text shapes.
Neither comparison justifies claiming BLOB saved retained disk in these runs.

Historical active v2 measurement: logical chain JSON 20,896,854 B; checkpoint
DB 29,659,136; VACUUM DB 21,229,568; transient WAL 21,156,232. Historical projected
v3 JSON section: logical 7,621,402; checkpoint 10,551,296; VACUUM 7,929,856;
WAL 10,728,512. Active storage duplicates raw hex and compatibility base64 media;
v3 BLOB retains one canonical representation but still contains base64 expansion.

The following is the **reproduced historical Task 7.8 representative profile**,
not an active-chain capacity forecast. It uses 211,172 canonical B/block,
146,812 encoded media B/block, 15,190 nonmedia B/block; equal sample weights,
not production traffic. Three years means 1,095 days, not leap-year forecasting.

| Blocks/day | Blocks in 3 yr | Canonical GiB | Primary GiB | Retained backups GiB | Snapshot GiB | Temporary headroom GiB | Initial sync GiB | Month-36 peer outbound GiB |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 100 | 109,500 | 21.54 | 27.92 | 106.09 | 27.92 | 11.69 | 25.84 | 7.02 |
| 1,000 | 1,095,000 | 215.35 | 270.19 | 1,026.73 | 270.19 | 70.09 | 258.42 | 70.23 |
| 10,000 | 10,950,000 | 2,153.53 | 2,692.91 | 10,233.06 | 2,692.91 | 654.09 | 2,584.23 | 702.35 |

The historical per-block original and encoded averages separately imply:

| Blocks/day | Original media GiB | Encoded payload GiB | Nonmedia metadata GiB |
| ---: | ---: | ---: | ---: |
| 100 | 17.26 | 14.97 | 1.55 |
| 1,000 | 172.63 | 149.72 | 15.49 |
| 10,000 | 1,726.26 | 1,497.19 | 154.91 |

Encoded payload plus nonmedia does not equal canonical bytes: base64 expansion
and descriptor/framing bytes also occupy the media representation. Original
bytes are recoverable from that encoding, not a required second decoded copy.

Primary=1 GiB base +1.25×canonical (large workload 1.30×). Retained weekly
full backups=4×0.95×primary; one additional local snapshot is separate. Temporary
headroom=20% primary +1.45×month writes×physical amplification +5 GiB;
quarterly VACUUM additionally needs one full-primary working copy. These are
modeled allowances, not measured filesystem peaks. Recommended month-36 full
backup uploads are 111.68 / 1,080.76 / 10,771.64 GiB at the three rates.

Incoming=month canonical×1.15×1.20; peer outbound=month canonical×8×1.20×1.20;
bootstrap=all canonical×1.20. Traffic is analytical, not packet measurement.
Historical canonical/media bytes are retained indefinitely; savings come from
encoding/amortization, not pruning or off-chain canonical media. No extra full
replica is hidden inside one node. Separate operator backups have explicit copies.
Retained alternate branches, reviewer histories, journal/source archives, content
cache growth and real recovery/repair traffic are not independently measured here.

SMALL and LARGE are assumptions: 16,384→15,319 B with 26,500 canonical B/block;
and 1,572,864→1,541,407 with 2,070,000 canonical B/block. LARGE at 10,000/day
reaches 21,109.82 GiB canonical, 27,443.77 GiB primary and 104,286.33 GiB backups.
Media mix, object-size tails, codec gains, DB amplification, peers and retention
dominate these projections. CPU/RAM assume 4 vCPU/8 GiB, ~4.06 GiB reserved,
two workers and 0.45 sec provisional validation per block. This excludes full
validation, bursts, duplicate peer work and disk contention. Bootstrap/recovery
is much more demanding than steady average rates.

Audit corrections to historical reporting: exact initial-sync outputs should
be read from the simulator (the old narrative's 258.45 and 2,584.24 GiB do not
match its exact model). The model's 211,172 B/block is an older projected shape;
the closed v3 fixture mean is 8,241,301/36 = 228,925.028 B/block, ~8.4% larger.
The appendix prices that mean separately without changing the historical inputs.
It still is a test workload, not a new production estimate.

## 11. Month-36 node economics

All numbers are **historical illustrative USD assumptions dated 2026-10-18**,
not measured invoices, current offers or binding provider quotes. Budget is
Hetzner-class, cloud is Lightsail-class, storage-focused blends a host with
object backup economics. No exact region is fixed. Source URLs are retained in
the versioned 7.8 config; no price refresh or purchase advice is part of this audit.

| Profile | Compute/month | Included primary GiB | Extra disk $/GiB-month | Backup $/GiB-month | Egress $/GiB | Compute class |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Budget VPS | 20 | 160 | .05 | .006 | .01 | 4 vCPU / 8 GiB |
| Mainstream cloud | 40 | 160 | .10 | .05 | .09 | 4 vCPU / 8 GiB |
| Storage-focused | 45 | 500 | .02 | .006 | .01 | 4 vCPU / 8 GiB |

Monthly billed egress includes peer propagation **and four full backup uploads**;
the model supplies no free-transfer allowance. Incoming and one-time bootstrap
are byte series, not separate monthly bill items. Required primary disk above
the bundle is charged. Backup storage is charged separately from local snapshots.

| Representative blocks/day | Budget VPS | Mainstream cloud | Storage-focused |
| ---: | ---: | ---: | ---: |
| 100 | $21.82 PASS | $55.99 PASS | $46.82 PASS |
| 1,000 | $43.18 PASS | $205.95 FAIL | $62.67 PASS |
| 10,000 | $322.78 FAIL | $1,837.60 FAIL | $265.00 FAIL |

For 1,000/day the monthly components compute/disk/backup/egress are respectively
$20.00/$5.51/$6.16/$11.51 (budget), $40.00/$11.02/$51.34/$103.59 (cloud),
$45.00/$0.00/$6.16/$11.51 (storage-focused). These are month-36 run rates,
not cumulative three-year spend. Corresponding three-year spend is
$1,102.64/$4,504.76/$1,959.38. SMALL at 10,000/day costs $51.10/$252.16/$67.16;
LARGE at 1,000/day $328.55/$1,870.39/$269.19; LARGE at 10,000/day
$3,176.50/$18,482.07/$2,376.19. Cheap hosting is not a universal <$100 guarantee.

**Audit finding: snapshot and temporary/VACUUM capacity is not priced.**
`simulate` computes snapshot_bytes and temporary_headroom_bytes, but passes only
primary storage, retained backups and egress to monthly_cost. Changing snapshot
copies alone cannot change the bill. This is a real model coverage limitation,
even though the historical arithmetic is exactly reproducible. The appendix adds
an explicitly illustrative disk-capacity allowance for one snapshot, stated
temporary margin and one-primary VACUUM workspace at unchanged marginal rates.
It also shows the frozen-v3 fixture-mean sensitivity. No historical result or
simulator implementation was repaired. Backup compression .95, physical factors,
regional allowances, taxes, service availability, IOPS and actual maintenance
capacity remain assumptions. A backup/restore primitive test does not validate
three years of operational recovery practice.

## 12. Review-journal economic boundary

The later separate BFT review journal is **not in the supplied original milestone
scope**. Task 7.8 modeled media-block chains and embedded certificate-shaped
evidence, not network-wide voting, fixed journal ticks, failed-review originals,
source proofs, signer/round logs or independent journal archives. Its analytical
media profile remains valid on its own terms, subject to this audit's schema,
representativeness and unpriced-capacity corrections. It never modeled a future
architecture by implication.

7.17P's five-second fixed tick assumptions alone add 96,878,592,000 B/three years
before votes. Q adds more explicit framing/index/clock/control assumptions:
continuous idle 117.657 GB or checkpoint-only idle 2.149 GB over three years;
active hybrid 147.394 / 415.023 / 3,091.313 GB per archive at 10/100/1,000 votes/min.
These are decimal GB and analytical proposed workloads, not measured SQLite
growth or approved protocol fields. 10,000/min is unserviceable offered demand,
not admitted traffic. Four validators plus two independent archives mean six
service copies network-wide, not six copies inside every node.

Q's hypothetical media+active-journal 1,000-media/day month-36 estimates are
$63.35/$324.82/$74.26 at 10 votes/min and $99.31/$534.65/$99.71 at 100/min;
1,000/min gives $458.88/$2,632.96/$365.81. Snapshot/workspace, source/original
retention and operating uncertainty can materially raise them. Failed-review
2 MiB originals at 144/1,440 sessions/day alone add ~330.679 GB/~3.307 TB over
three years. Do not add accepted originals twice, or rely on a disposable cache
for required history. Combined full media-chain-plus-journal-plus-source costs
are **not proven below $100/month**. A bounded retention/cost contract belongs
to the future voting/consensus requirement; implementing that journal is not a
minimum original-scope compression completion item.

## 13. Reproducibility, outcomes and exclusions

Windows 11 build 26200 AMD64; CPython 3.13.5; SQLite 3.49.1; zstandard 0.25.0
(linked libzstd 1.5.7), Brotli 1.2.0, Pillow 12.3.0, cffi 2.0.0,
pytest 8.4.1, cryptography 49.0.0, eth-account 0.13.7. Corpus encoders:
JPEG 8.0, WebP 1.6.0. Existing dependencies were used without installs/upgrades.
Additional observed versions: Node v22.17.0; zlib compile/runtime 1.3.1;
zstandard cext backend/libzstd 1.5.7; anyio 4.14.0; Starlette 1.3.1;
httpx2 2.5.0 (httpx is not installed); FastAPI 0.138.0. SQLite compile options
do not include ENABLE_DBSTAT_VTAB. These details matter to the API environment
timeout and missing physical index attribution; no package mismatch is repaired
or blamed without further evidence.
Benchmark codec dependencies are pinned in requirements-benchmark.txt, not
silently added to production requirements.

Run the bounded orchestrator with:

```powershell
.\.venv\Scripts\python.exe -B verification/task718/run_audit.py
```

It runs corpus --verify; 7.4 --output audit/codec.json; 7.7 --output
audit/composition.json; 7.8 --output audit/economics.json --csv audit/economics.csv;
7.11 --output audit/storage.json; then focused measurement, codec/worker,
v3/admission/persistence, 7.17S and legacy suites. The actual absolute output path
is verification/task718, not a directory named audit. Exact argv, environment,
per-command timeout/elapsed/exit status and logs are in execution.json.
TEMP/TMP point at a unique writable repository-local temporary directory and
pytest cache writing is disabled; this is process-local test setup, not a
production configuration edit. Logs explicitly retain failures and skips.

The first three documented runners fail their full-manifest equality check.
The frozen manifest contains mutable historical image-admission outcomes as well
as source hashes. Task 7.12 repaired the image-worker path; this audit's writable
temp root lets valid images be accepted. Thus original bytes and encoder versions
can match while those historical observations no longer match. The full-manifest
gate couples benchmark reproducibility to an obsolete environment-failure record.
The audit reports this defect rather than editing the manifest, weakening a gate
in production code, or relabeling the command PASS.

Supplemental measurement is a **different, labeled audit command**:

```powershell
.\.venv\Scripts\python.exe -B verification/task718/supplemental.py
```

It checks all 36 source hashes/sizes first, records field-by-field manifest
differences, executes unchanged codec profiles on those bytes, checks exact
reconstruction/hash on every result, compares raw encoded lengths to the frozen
252 rows, replays 72 identity/Zstd streams through the worker, and measures
36 signed frozen-format R records. It does not monkeypatch a historical runner
or replace corpus/configuration. Timing differences are observations, with no
speed PASS threshold; deterministic byte-size/hash comparisons use zero tolerance.
SQLite comparison excludes environment metadata only; simulator outputs require
exact equality (JSON structures and CSV bytes). Final counts/tables follow below.

Excluded from fresh execution: full repository/frontend suites, expensive
performance/profiling runners, native Linux/WSL/deployment tests, fuzz/sanitizer
campaigns, external decoder implementation, public network/sync/load/operating
tests, current provider-price validation and new journal throughput experiments.
The Linux-only tests are explicitly skipped on Windows; retained paired Linux
evidence is read/checked, not called a fresh Linux run. No security review or
production-readiness claim follows from passing these selected tests.

## 14. Completion/readiness matrix

| Item | Status | Reason |
| --- | --- | --- |
| A Compression benchmark design complete | PARTIAL | Seven profiles and raw results; production corpus and current documented command reproduction deficient |
| B Adaptive codec implementation complete | PASS, isolated scope | Real canonical-descriptor selection/fallback; active application status is separate |
| C Exact round-trip correctness complete | PASS, tested scope | Source/fixture exact bytes and hashes, including persistence; no universal native-security proof |
| D Canonical metadata schema complete | PASS, frozen isolated v3 | Eight-field closed schema, canonical hashing and persistence |
| E Canonical block-size instrumentation complete | PASS, measured scope | Historical partition plus frozen-R audit; no production population |
| F Three-year economics simulator complete | PARTIAL | Deterministic all-rate/provider tools work; snapshots/workspace unpriced, index split and finalized traffic lacking |
| G Isolated v3 compressed-media path complete | PARTIAL | Codec/format/store/admission laboratory exists; its history authority is test-only and incomplete for live acceptance |
| H Active blockchain integration complete | FAIL | Producer remains raw v1/v2; no active codec call |
| I Active full-node validation/persistence integration complete | FAIL | Current version gate/storage/retrieval do not support v3 |
| J Production protocol activation ready | BLOCKED | No approved transition/context; integration and decoder/platform/security gates remain |
| K Independent security review complete | NOT VERIFIED | No recorded independent native decoder/worker review; paired OS tests share algorithm |
| L Original Milestone 7 acceptance complete | FAIL | Application behavior, representativeness/target evidence and reproducibility gaps above |

## 15. Minimum remaining original-scope work, ranked

This is an acceptance gap list, not a new implementation task or permission to
make these changes during Task 7.18. No additional 7.17 substep is created.

| Rank | Acceptance requirement / exact missing behavior | Kind / scope | Security or consensus implication | Independent of new BFT journal? |
| --- | --- | --- | --- | --- |
| 1 | Scope 2/3/6, B/E: accepted submission → adaptive encoding → authenticated canonical record → full-node verification → persistence → exact retrieval through application paths; approved version boundary and historical v1/v2 compatibility | Implementation + end-to-end verification; large | New compressed-byte validity/storage boundary needs reviewed decoder and explicit version policy. Demonstrate identity fallback/size behavior across accepted inputs; do not activate from an audit | Yes as original compression acceptance work; owner must define a supported transition without importing the new journal architecture |
| 2 | Scope 1/8, A/C: separately versioned, provenance-cleared production-like MIME/size/traffic corpus, substantive text/JSON/code; valid full evidence/finality accounting; explicit overhead denominator and workload target assessment | Evidence/verification medium; metadata representation work only if target remains unmet and required | Preserve original bytes and required evidence; reducing or omitting signatures/votes is not an acceptable way to claim <15%. Any encoding change needs consensus review | Yes; current frozen-v3/media-chain population can be evaluated separately |
| 3 | F: working reproduction commands/tests at current HEAD, separating immutable corpus byte/environment checks from mutable historical admission observations; retain frozen source reports unchanged | Small implementation of verification tooling + documentation/tests | Do not weaken hostile-input checks or rewrite historical expected bytes to obtain a PASS | Yes |
| 4 | Scope 5/9, D/F: close snapshot/workspace cost accounting, state optional index-attribution blocker explicitly or measure it, and rebase a clearly labeled economics scenario on the intended frozen record/workload; retain original scenario reproducibility | Verification/model-accounting medium | Transparent retained/full-backup/restore capacity; no migration or off-chain canonical media dependency | Yes; journal/source costs remain a separately disclosed future model |

A public launch, chain reset, broader BFT redesign or complete new review-journal
implementation is not added as an independent original-milestone checkbox.
Independent native security review and deployment/platform sign-off remain
production gates; the exact guarantees necessary for accepting hostile compressed
media cannot be waived by labeling the path “implemented.” No estimate here
authorizes production changes.

## 16. Audit completion and owner review

Final numeric appendices, command outcomes and preservation checks are recorded
below. The audit is ready for owner review and an owner-made
commit only. Neither verdict authorizes deployment or protocol activation.

**Final original-milestone verdict: INCOMPLETE. Production readiness: BLOCKED.**
Continue only the minimum original-scope acceptance gaps; do not officially close
Milestone 7 on the basis of isolated test success or inexpensive provider models.

## Appendix A. Final measured evidence

These are final audit measurements, read directly from the retained JSON/logs.

### A1. Execution outcomes

| Command/group | Outcome | Seconds | Final test summary | Log |
| --- | --- | --- | --- | --- |
| corpus | FAIL | 17.136 | No pytest summary | [corpus.txt](../verification/task718/corpus.txt) |
| codec | FAIL | 9.012 | No pytest summary | [codec.txt](../verification/task718/codec.txt) |
| composition | FAIL | 20.621 | No pytest summary | [composition.txt](../verification/task718/composition.txt) |
| economics | PASS | 0.196 | No pytest summary | [economics.txt](../verification/task718/economics.txt) |
| storage | PASS | 89.73 | No pytest summary | [storage.txt](../verification/task718/storage.txt) |
| tests_measurements | FAIL | 41.231 | 17 passed, 5 failed | [tests_measurements.txt](../verification/task718/tests_measurements.txt) |
| tests_codec | PASS | 41.211 | 476 passed, 193 skipped | [tests_codec.txt](../verification/task718/tests_codec.txt) |
| tests_v3 | TIMEOUT | 480.014 | No pytest summary | [tests_v3.txt](../verification/task718/tests_v3.txt) |
| tests_717s | PASS | 41.951 | 154 passed | [tests_717s.txt](../verification/task718/tests_717s.txt) |
| tests_legacy | PASS | 20.264 | 115 passed | [tests_legacy.txt](../verification/task718/tests_legacy.txt) |
| api_diagnostic | TIMEOUT | 45.023 | No pytest summary | [api_diagnostic.txt](../verification/task718/api_diagnostic.txt) |
| format_storage_recheck | PASS | 83.075 | 172 passed | [format_storage_recheck.txt](../verification/task718/format_storage_recheck.txt) |
| image_recheck | PASS | 6.139 | 18 passed, 1 deselected | [image_recheck.txt](../verification/task718/image_recheck.txt) |
| admission_history_atomic_recheck | PASS | 249.976 | 250 passed, 4 skipped | [admission_history_atomic_recheck.txt](../verification/task718/admission_history_atomic_recheck.txt) |
| supplemental | PASS | 62.092 | No pytest summary | [supplemental.txt](../verification/task718/supplemental.txt) |
| supplemental_recheck | PASS | 61.48 | No pytest summary | [supplemental_recheck.txt](../verification/task718/supplemental_recheck.txt) |


Completed, disjoint test selections total **1202 passed, 5 failed, 197 skipped**; 1 deselected. The incomplete combined v3 run is not added to these counts. The same API case timed out in that run and in the bounded standalone diagnostic; neither attempt is a pass or skip.

The five failed node IDs are retained in tests_measurements.txt: corpus manifest regeneration; the obsolete genesis-image-isolation failure expectation; image-evaluation baseline verification; and the two composition-build tests. The 193 Linux-only skips require a Linux kernel. Any four atomic WAL crash skips are caused by the repository runtime gate on SQLite 3.49.1.

Follow-ups were invoked with `.venv/Scripts/python.exe -B verification/task718/followup.py`; it records exact argv in followup.json. The standalone API faulthandler trace blocks in socket.accept/_fallback_socketpair while creating the Windows asyncio loop, before the upload handler. Host-local event-loop verification is unavailable; no production codec defect is inferred. No further socket or application changes were attempted.

Deterministic comparisons: simulator JSON exact=True; CSV byte-exact=True; storage fields excluding environment exact=True; codec sizes differing from frozen rows=0/252.

All 36 source lengths/hashes match. Manifest observation differences occur in 22 samples; field deltas are in supplemental.json. Frozen and regenerated encoder/Python environment dictionaries are compared there. Fresh strict-worker source-byte round trips: 72/72 exact; signed frozen-format reconstruction: 36/36 exact.

### A2. Raw category codec measurements

Ratio is encoded/original; reduction=100*(1-ratio), before adaptive fallback. Timings are summed per-object medians in milliseconds, not p95 latency. Object-level median/p95 and exact configurations are retained in supplemental.json; native memory remains unmeasured. Negative reductions are honest expansion results. Identity remains the comparison baseline.

| Profile | Category | Objects | Original B | Encoded B | Ratio | Reduction % | Encode ms | Decode ms | Expands |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| identity-1 | plain_text | 3 | 3,287 | 3,287 | 1.00000 | 0.000 | 0.0004 | 0.0003 | 0 |
| identity-1 | structured_metadata_json | 3 | 14,871 | 14,871 | 1.00000 | 0.000 | 0.0003 | 0.0003 | 0 |
| identity-1 | source_code | 3 | 1,134 | 1,134 | 1.00000 | 0.000 | 0.0003 | 0.0003 | 0 |
| identity-1 | image/jpeg | 7 | 2,500,693 | 2,500,693 | 1.00000 | 0.000 | 0.0007 | 0.0007 | 0 |
| identity-1 | image/png | 7 | 1,795,174 | 1,795,174 | 1.00000 | 0.000 | 0.0007 | 0.0007 | 0 |
| identity-1 | image/webp | 7 | 904,502 | 904,502 | 1.00000 | 0.000 | 0.0007 | 0.0007 | 0 |
| identity-1 | image/gif | 6 | 874,256 | 874,256 | 1.00000 | 0.000 | 0.0006 | 0.0006 | 0 |
| zstd-3 | plain_text | 3 | 3,287 | 575 | 0.17493 | 82.507 | 0.0097 | 0.0045 | 1 |
| zstd-3 | structured_metadata_json | 3 | 14,871 | 1,200 | 0.08069 | 91.931 | 0.0173 | 0.0089 | 0 |
| zstd-3 | source_code | 3 | 1,134 | 684 | 0.60317 | 39.683 | 0.0111 | 0.0045 | 0 |
| zstd-3 | image/jpeg | 7 | 2,500,693 | 1,789,567 | 0.71563 | 28.437 | 3.8527 | 1.0169 | 1 |
| zstd-3 | image/png | 7 | 1,795,174 | 1,783,751 | 0.99364 | 0.636 | 0.7423 | 0.4745 | 1 |
| zstd-3 | image/webp | 7 | 904,502 | 889,182 | 0.98306 | 1.694 | 0.5771 | 0.0809 | 2 |
| zstd-3 | image/gif | 6 | 874,256 | 820,507 | 0.93852 | 6.148 | 0.9531 | 0.6415 | 5 |
| zstd-6 | plain_text | 3 | 3,287 | 586 | 0.17828 | 82.172 | 0.0174 | 0.0046 | 1 |
| zstd-6 | structured_metadata_json | 3 | 14,871 | 1,106 | 0.07437 | 92.563 | 0.0384 | 0.0082 | 0 |
| zstd-6 | source_code | 3 | 1,134 | 679 | 0.59877 | 40.123 | 0.0138 | 0.0045 | 0 |
| zstd-6 | image/jpeg | 7 | 2,500,693 | 1,756,572 | 0.70243 | 29.757 | 7.9220 | 0.8881 | 1 |
| zstd-6 | image/png | 7 | 1,795,174 | 1,783,472 | 0.99348 | 0.652 | 1.1207 | 0.4702 | 1 |
| zstd-6 | image/webp | 7 | 904,502 | 888,330 | 0.98212 | 1.788 | 1.1944 | 0.0806 | 2 |
| zstd-6 | image/gif | 6 | 874,256 | 819,377 | 0.93723 | 6.277 | 0.9239 | 0.5896 | 5 |
| zstd-9 | plain_text | 3 | 3,287 | 589 | 0.17919 | 82.081 | 0.0201 | 0.0046 | 1 |
| zstd-9 | structured_metadata_json | 3 | 14,871 | 1,098 | 0.07383 | 92.617 | 0.0475 | 0.0086 | 0 |
| zstd-9 | source_code | 3 | 1,134 | 679 | 0.59877 | 40.123 | 0.0154 | 0.0048 | 0 |
| zstd-9 | image/jpeg | 7 | 2,500,693 | 1,755,400 | 0.70197 | 29.803 | 10.2624 | 0.8888 | 1 |
| zstd-9 | image/png | 7 | 1,795,174 | 1,783,451 | 0.99347 | 0.653 | 1.2156 | 0.4686 | 1 |
| zstd-9 | image/webp | 7 | 904,502 | 888,310 | 0.98210 | 1.790 | 1.2988 | 0.0817 | 2 |
| zstd-9 | image/gif | 6 | 874,256 | 819,377 | 0.93723 | 6.277 | 1.0118 | 0.6550 | 5 |
| brotli-4 | plain_text | 3 | 3,287 | 532 | 0.16185 | 83.815 | 0.0390 | 0.0074 | 1 |
| brotli-4 | structured_metadata_json | 3 | 14,871 | 1,107 | 0.07444 | 92.556 | 0.0684 | 0.0122 | 0 |
| brotli-4 | source_code | 3 | 1,134 | 630 | 0.55556 | 44.444 | 0.0390 | 0.0082 | 0 |
| brotli-4 | image/jpeg | 7 | 2,500,693 | 1,754,791 | 0.70172 | 29.828 | 13.3611 | 7.2246 | 0 |
| brotli-4 | image/png | 7 | 1,795,174 | 1,783,740 | 0.99363 | 0.637 | 3.9888 | 0.6398 | 1 |
| brotli-4 | image/webp | 7 | 904,502 | 876,158 | 0.96866 | 3.134 | 3.2147 | 0.6889 | 2 |
| brotli-4 | image/gif | 6 | 874,256 | 810,216 | 0.92675 | 7.325 | 6.7911 | 3.4234 | 5 |
| brotli-6 | plain_text | 3 | 3,287 | 506 | 0.15394 | 84.606 | 0.5041 | 0.0069 | 1 |
| brotli-6 | structured_metadata_json | 3 | 14,871 | 1,000 | 0.06724 | 93.276 | 0.7448 | 0.0112 | 0 |
| brotli-6 | source_code | 3 | 1,134 | 583 | 0.51411 | 48.589 | 0.5035 | 0.0079 | 0 |
| brotli-6 | image/jpeg | 7 | 2,500,693 | 1,729,648 | 0.69167 | 30.833 | 20.8489 | 6.9981 | 0 |
| brotli-6 | image/png | 7 | 1,795,174 | 1,783,471 | 0.99348 | 0.652 | 7.0064 | 0.6567 | 1 |
| brotli-6 | image/webp | 7 | 904,502 | 872,809 | 0.96496 | 3.504 | 7.7773 | 0.6934 | 2 |
| brotli-6 | image/gif | 6 | 874,256 | 810,746 | 0.92736 | 7.264 | 10.0531 | 3.2820 | 4 |
| zlib-6 | plain_text | 3 | 3,287 | 660 | 0.20079 | 79.921 | 0.0222 | 0.0071 | 1 |
| zlib-6 | structured_metadata_json | 3 | 14,871 | 1,248 | 0.08392 | 91.608 | 0.0576 | 0.0145 | 0 |
| zlib-6 | source_code | 3 | 1,134 | 641 | 0.56526 | 43.474 | 0.0181 | 0.0064 | 0 |
| zlib-6 | image/jpeg | 7 | 2,500,693 | 1,850,324 | 0.73992 | 26.008 | 53.0931 | 7.9903 | 0 |
| zlib-6 | image/png | 7 | 1,795,174 | 1,783,746 | 0.99363 | 0.637 | 37.6557 | 1.1049 | 1 |
| zlib-6 | image/webp | 7 | 904,502 | 882,432 | 0.97560 | 2.440 | 18.1703 | 1.1564 | 2 |
| zlib-6 | image/gif | 6 | 874,256 | 822,562 | 0.94087 | 5.913 | 28.1924 | 3.3503 | 4 |


Zstd-3 category result: plain text 82.51% raw reduction; JSON/metadata 91.93%; source code 39.68%. The first two exceed the approximate target on this small synthetic corpus; the source snippets do not demonstrate 60–80%. This is not evidence that suitably sized code cannot reach that target. Do not pad or reweight the corpus to make it pass.

### A3. Frozen v3 full-record metadata

| Definition | p50 % | p95 % | Worst % |
| --- | --- | --- | --- |
| canonical_metadata_percent | 85.97237 | 99.60381 | 99.85557 |
| historical_definition_percent | 85.37104 | 98.92547 | 99.16654 |
| original_relative_metadata_percent | 621.43526 | 30444.95413 | 94820.00000 |


| 36-record total | Bytes |
| --- | --- |
| accepted_original | 6,093,910 |
| base64_characters | 7,047,024 |
| canonical_record | 8,241,301 |
| descriptor_and_media_field_framing | 8,291 |
| encoded | 5,285,229 |
| native_array_bytes | 72 |
| nonmedia_metadata | 1,185,986 |
| protocol_metadata_including_descriptor | 1,194,277 |
| reviewer_evidence_bytes | 923,364 |
| signature_characters_subset | 71,280 |


Definitions: historical_definition_percent=(R-serialized media member)/R; canonical_metadata_percent=(R-base64 content characters)/R; original_relative_metadata_percent=(R-base64 content characters)/accepted-original bytes. All percentiles are equal-block nearest rank, including tiny records. Required reviewer/submitter signatures remain inside certificate totals. Reviewer evidence/native-array/signature values below are diagnostic subsets, not extra additive bytes. The old signature-subset helper counts arbitrary array strings, including acceptance reason codes. Audit signature totals instead count only explicit signature/vote_signature fields (71,280 ASCII content bytes across these records); the unmodified helper diagnostic in each parts object is retained for traceability and is 864 bytes higher. There is no separate producer block signature in this frozen format. Finality proofs are separate retained objects, absent from this corpus population.

| Additive full-R partition | Bytes |
| --- | --- |
| certificate_bytes | 1,136,216 |
| transaction_record_bytes | 9,180 |
| header_bytes | 8,559 |
| remaining_structural_metadata_bytes | 22,995 |
| envelope_bytes | 5,220 |
| delimiter_bytes | 684 |
| serialized_media_representation_bytes | 7,055,315 |
| portable_wrapper_bytes | 3,132 |


Full-R metadata byte-weighted share including descriptor: **14.49136%**; mean R=228925.027778 B. The equal-block p50/p95/worst target remains unmet. Accepted original size p50/p95/worst={'p50': 4961, 'p95': 1530684, 'worst': 1772761}. The supplemental gate probes confirm certificate/native/rest at-cap acceptance by the respective byte gate and cap+1 rejection. They are explicitly analytic gate inputs, not forged valid maximum records; real-signature max-media tests are in the passed format suite.

### A4. All historical month-36 scenarios

| Blocks/day | Workload | Budget USD | Cloud USD | Storage-focused USD |
| --- | --- | --- | --- | --- |
| 100 | small_media | 20.28 | 42.49 | 45.28 |
| 100 | representative_corpus | 21.82 | 55.99 | 46.82 |
| 100 | large_media | 43.76 | 209.22 | 62.99 |
| 1000 | small_media | 22.27 | 59.92 | 47.27 |
| 1000 | representative_corpus | 43.18 | 205.95 | 62.67 |
| 1000 | large_media | 328.55 | 1870.39 | 269.19 |
| 10000 | small_media | 51.10 | 252.16 | 67.16 |
| 10000 | representative_corpus | 322.78 | 1837.60 | 265.00 |
| 10000 | large_media | 3176.50 | 18482.07 | 2376.19 |


### A5. Audit-only schema and disk-capacity sensitivities

Historical prices, peer/backup rules and DB amplification are held fixed. Closed-v3 mean substitutes only the measured canonical bytes/block. Capacity-priced total provisions primary + one local snapshot + stated temporary margin + one additional primary-sized VACUUM workspace, charging max(0, allocated GiB - bundle GiB) at the same marginal disk rate; backup and egress charges are unchanged. This is a planning sensitivity, not a provider quote or a measured minimum workspace, and leaves journal/source costs excluded.

| Basis | Blocks/day | Canonical GiB | Primary GiB | Allocated disk GiB | Budget published-rule / capacity-priced USD | Cloud same USD | Storage-focused same USD |
| --- | --- | --- | --- | --- | --- | --- | --- |
| historical_projected | 100 | 21.535 | 27.919 | 95.446 | 21.82 / 21.82 | 55.99 / 55.99 | 46.82 / 46.82 |
| historical_projected | 1000 | 215.353 | 270.191 | 880.662 | 43.18 / 73.70 | 205.95 / 266.99 | 62.67 / 70.28 |
| historical_projected | 10000 | 2153.528 | 2692.910 | 8732.817 | 322.78 / 624.78 | 1837.60 / 2441.59 | 265.00 / 385.79 |
| closed_v3_fixture_mean | 100 | 23.346 | 30.182 | 102.781 | 21.97 / 21.97 | 57.29 / 57.29 | 46.97 / 46.97 |
| closed_v3_fixture_mean | 1000 | 233.457 | 292.822 | 954.009 | 45.79 / 78.85 | 221.19 / 287.31 | 64.15 / 73.23 |
| closed_v3_fixture_mean | 10000 | 2334.573 | 2919.217 | 9466.287 | 348.90 / 676.26 | 1990.02 / 2644.72 | 284.33 / 415.27 |


### A6. Preservation and final disposition

HEAD remains `2752e0eb7b7a89cace6c9adf61a38a12dad61883` on `Compression-State-Bloat-and-Node-Economics`. Index diff is empty. SHA-256 comparison of every preexisting tracked file found **zero changes**. Git reports only the requested new audit document and files under verification/task718 as untracked. summary.json records that status before its own creation on the first assembly; it is not a historical initial-clean claim. The initial clean prerequisite was independently checked before any audit file was created. No staging, commit, push, merge, activation, migration, reset or deployment occurred.

Audit document and retained evidence are ready for owner review and an owner-performed commit. **Original acceptance: INCOMPLETE. Production readiness: BLOCKED. Do not officially close Milestone 7 now.**
