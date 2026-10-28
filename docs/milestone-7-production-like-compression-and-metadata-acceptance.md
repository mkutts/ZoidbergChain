# Milestone 7 Task 7.20 — Production-like compression and metadata acceptance

Date: 2026-10-28, America/New_York. **Task 7.20 is ready for owner review with
measured acceptance misses. Original Milestone 7 is not complete.** No compressed
media was activated. This is a focused acceptance experiment on the existing
inactive v3 implementation, not production integration or a new protocol design.

The new synthetic production-like workload covers every permitted MIME, but
cannot establish a production traffic distribution. Adaptive selection and
exact reconstruction pass in the measured scope. The full-record metadata
target fails: **p50 54.70902%, p95 99.80752%, worst 99.81935%** across 34 new
records. A **7.14017%** canonical-byte weighted share does not replace those
statistics. Even the 22-image subset fails at p95/worst.

## 1. Git prerequisites, scope and preservation

Branch: `Compression-State-Bloat-and-Node-Economics`.
HEAD: `681e74863a2985b706138a95956d4bd885d062cd`.
Task 7.19 is separately committed in `ce082a2` and its script-repair follow-up
`681e748`. The index and worktree were clean, including untracked files, before
creating the new directory. All relevant frozen corpus generators/manifests,
benchmarks, Task 7.18/7.19 reports and evidence were tracked. No applicable
repository/ancestor AGENTS.md was found; no agents were delegated.

Read the complete original-scope audit and reproducibility/triage report, then
inspected original corpus/codec/image/composition reports, scripts and settings,
the media admission routes/services/policy, and the frozen v3 descriptor,
canonical serializer, record, evidence and transaction schemas. The original
Task 7.7 projection is not the later complete frozen v3 record.

[before.json](../benchmarks/task720_v1/before.json) records SHA-256 for all
**1,018** preexisting tracked files and the environment. The sole existing file
changed is `tests/test_milestone_7_task_7_3_corpus.py`, containing the two
authorized obsolete-test corrections below. All production code, historical
fixtures, corpora, results and reports retain exact hashes. The new deliverables
are this report and [benchmarks/task720_v1](../benchmarks/task720_v1/README.md).
The final preservation record and checksum inventory verify the complete scope.
Nothing was staged, committed, pushed, merged, migrated, reset or deployed.
No Task 7.21 or later BFT/reviewer-journal work was begun.

## 2. Actual MIME coverage and acceptance boundaries

| Profile | Exact accepted MIME registry | Relevant bounds |
| --- | --- | --- |
| Current application technical admission | `text/plain`, `image/jpeg`, `image/png`, `image/webp`, `image/gif` | Canonical text/image 262,144 B; policy complete-block bound 524,288 B; image dimensions/frame/pixel/metadata constraints also apply |
| Proposed isolated v3 | Same five types, with `identity/1` and `zstd/1` | Original text 262,144 B; original image and encoded media 2,097,152 B; complete record 3,145,728 B; mandatory component/schema budgets also apply |
| Unsupported/future | `application/json`, source-language MIME types, PDF, SVG, BMP, TIFF, AVIF, JPEG XL, audio, video and archives | No support added or benchmark acceptance claimed |

Trace: `config.py` MIME tuples → `content.py` supported MIME/byte-sniff checks →
`api_routers/content.py` upload declaration gate →
`services/content_coordination_service.py` →
`media_technical_validation.validate_media_bytes` and
`media_admission_policy.evaluate_media_admission_policy`. Complete detected bytes
are authoritative; octet-stream is an unspecified transport declaration, not a
sixth content type. Text containing JSON or harmless source is carried as
`text/plain`; active executable/script markers remain forbidden. The current
policy's own activation annotations are preserved; this experiment does not
interpret a validator success as protocol activation or a finalized admission.

Isolated v3 has an explicit five-MIME allowlist in `canonical_v3/media.py`.
Codec/format validity alone does not establish image safety, live certificate
issuance, historical reviewer authority or accepted-chain validity. Its signed
test certificates bind the MIME, size and hash using existing public fixture
keys and symbolic context, without creating real validator/production keys.

Every new object was also passed to the current technical validator: **27
accepted; 7 rejected solely for the current image-byte cap**. These are
`png-medium`, `jpeg-medium`, `gif-medium` and the four `*-near-v3` images.
All remain in the full v3 population. The separately reported 27-object current
accepted subset does not replace it or imply complete active block acceptance.
The `medium` image label is a 512×384 dimension scenario, not a guarantee of
fitting today's byte cap. [admission.json](../benchmarks/task720_v1/admission.json)
records every observed reason and the unchanged policy.

## 3. Audit of the historical 36-object corpus

[historical_audit.json](../benchmarks/task720_v1/historical_audit.json) lists
each object's type, category, exact size/hash, seed/origin, original Zstd result,
historical admission/scoring flags and both record/byte weights. Original source
bytes total **6,093,917**. Inventory is 9 plain-text objects (3 prose, 3 JSON,
3 code), 7 JPEG, 7 PNG, 7 WebP and 6 GIF. These are repository-authored synthetic
rasters, captions, repeated operational logs/JSON and short source snippets;
there is no real user media or measured upload population.

Every record has weight 1/36 (2.77778%) in equal-record percentiles. **9/36 are
under 1,024 B and 24/36 under 16,384 B**. Tiny objects do not alone comprise a
majority, but small payloads dominate the median while fixed certificate bytes
dominate those records. Five capacity-only images were excluded from historical
primary codec scoring; all 36 remain in the historical full-record experiment.
Historical p50/p95/worst overhead is **85.97237/99.60381/99.85557%**.

Useful evidence remains: exact original hashes, byte reconstruction, codec
framing, identity fallback, deterministic arithmetic and current regression
coverage. Synthetic gradients/flat images inflate some JPEG benefits; the tiny
historical source category demonstrates only 39.68% Zstd-3 reduction. Neither
that corpus nor its percentiles establish representative production behavior.
Frozen observations of the old image-worker failure remain historical evidence.
No historical source, manifest or published result was rewritten.

## 4. New profile, provenance and representativeness

`task720-production-like-v1`, version **1.0.0**, contains **34 objects /
11,521,163 original bytes**: 4 plain prose, 4 structured JSON, 3 source-code,
1 ASCII entropy control, 5 PNG, 5 JPEG, 6 WebP and 6 GIF. No object was excluded
because its compression or overhead result was unfavorable.

All new content is self-created for this experiment, with CC0-1.0 provenance
recorded in the manifest/source. No media was downloaded and no private user
files were read. Only the existing public test fixtures are reused for record
construction. There is no separately bundled rights-cleared photographic corpus.
This is therefore explicitly **synthetic/production-like**, not representative
real-world media or a production-weighted sample.

The deterministic seed is **7202026**, with per-member derivatives in
[manifest.json](../benchmarks/task720_v1/manifest.json). The manifest pins every
hash, size, origin and generator source hash, plus Pillow/JPEG/WebP versions.
Prose contains varied operational events, regions, tickets and observations;
JSON contains nested event records, unique digest IDs and varied numeric values.
Source members are a short new function, the actual new corpus generator and
the complete generator/measurement suite (102, 8,008 and 31,972 B). The suite
contains the smaller module; these are related coverage examples, not independent
samples. No padding/repetition was added to make source pass. One module's
54.80% result is retained beside the larger suite's 65.09% result.

Images include one-pixel containers, a rendered operations dashboard, uniform
seeded noise textures, and original-container sizes at 90–100% of the current
256 KiB and proposed 2 MiB caps. GIF/WebP also include a two-frame dashboard
animation. The dimension search uses original-container size only, independently
of downstream compression results. Noise is a stress control, not a photograph.
The 65,536-B entropy text uses 64 ASCII symbols (six bits per character), so its
approximately 25% encoding reduction is expected, not evidence about arbitrary
eight-bit random data. The actual maximum prose member is 262,144 B; the medium
member is 32,767 B after its deliberate canonical endpoint construction.

There are no real production traffic measurements or fabricated weights.
Equal-record and byte-weighted summaries are explicit descriptive calculations.
Current-cap subsets and metadata sensitivities are separately labeled, and never
replace the declared full population.

## 5. Lossless codec comparison

The unchanged historical candidate settings are used: identity; Zstd levels
3/6/9, window_log=18, checksum/content size enabled, no dictionary, threads=0;
Brotli qualities 4/6, generic mode, lgwin=18; zlib level 6 with wbits=15 wrapper.
Brotli/zlib are justified existing comparison baselines, not accepted v3 codecs.
All **238 native-codec object/profile trials** reconstruct exact original bytes
and SHA-256. Raw compression of already compressed images is not expected to
reach 60–80%; expansion remains visible.

[codecs.json](../benchmarks/task720_v1/codecs.json) contains original/encoded
bytes, complete descriptor sizes, expansions, exact hashes, 9 encode/decode
observations after 2 warmups, and category p50/p95/worst/means and byte-weighted
aggregates. Timings use `perf_counter_ns`, excluding imports, generation and
serialization; timing variability is not a byte-reproducibility failure. Descriptor
sizes for comparison-only codecs are estimates, not valid complete v3 blocks.
Actual full stored records are measured separately with the real adaptive producer.

The numerical appendix gives all profiles by category and the Zstd-3 timing/tail
table. Substantive compressible prose/JSON reach or exceed the approximate goal;
source code is **62.88359% byte-weighted, p50 54.79520%, worst 4.90196%**.
The goal is demonstrated on the 31,972-B suite (65.09446%), not every short or
medium source file. This prevents strong JSON results from hiding weaker code.

## 6. Actual adaptive producer, strict profile and reconstruction

Every full record uses the actual isolated `media.produce` through the existing
`corpus_record` fixture helper. Production-like choices are **17 Zstd / 17
identity**; historical choices are **26 Zstd / 10 identity**. Every selected
descriptor and complete record is no larger than its otherwise identical
identity representation. An independent cross-check uses the native trial size
and strict-profile outcome to verify the exact expected producer choice on all
34 new originals. Hash, MIME, original/encoded sizes and canonical commitment
are checked by the existing parser/worker, not inferred from nominal codec ratio.

There is one important profile constraint: `gif-near-v3` is **2,096,459 B**;
native default Zstd emits **1,954,542 B** that reconstruct exactly in the native
benchmark, but strict v3 rejects it as `frame/block_count` (64-block limit).
The existing producer tries that beneficial representation, receives INVALID,
and correctly returns verified identity. It is retained in every population;
no protocol limit, encoder or validator was changed. This is a strict-profile
limitation, not corruption or byte loss. A local operational failure would abort
the measurement; it is not converted into identity or validity.

Source-byte worker trials: **139 VALID exact reconstructions / 140 trials**,
plus **1 intentionally recorded INVALID candidate** above. All 70 identity
source trials reconstruct exactly. All **70 selected full records** and **8
sensitivity records** reconstruct their accepted original bytes exactly.
The historical source/accepted domains remain distinct: canonical text admission
removes 7 source bytes overall, leaving 6,093,910 accepted bytes. New source and
accepted bytes are identical. An invalid candidate is not counted as a successful
roundtrip; byte-exact reconstruction holds for every selected representation.

Producer policy and validator acceptance are separate. For `Accept exact bytes.`
the identity descriptor/record is **249/33,215 B**; a larger but conforming Zstd
descriptor/record is **261/33,227 B**. The actual producer selects identity;
the unmodified validator accepts the externally supplied larger record and
recovers the same original SHA-256. This is the specified contract: no-expansion
is producer policy, not a new consensus ban on alternative encodings.

## 7. Complete canonical metadata composition

Let M be accepted original bytes, E encoded bytes, B base64 content characters
and R the complete portable canonical record, including its hash wrapper.

* Primary nonmedia bytes N = R − B; metadata percentage = 100 N/R.
* Original-relative percentage = 100 N/M.
* The stricter binary-exclusion percentage = 100 (R − E)/R is also in each row.
* Base64 expansion B − E is separately reported. It is not silently called
  security metadata or omitted from the complete stored representation.

Every one of the 78 measured records has a disjoint **field-by-field JSON byte
ledger** in [records.json](../benchmarks/task720_v1/records.json). Every field
name/colon, scalar value, quote, brace, comma, array and portable wrapper is
charged once. A second component partition independently reconciles to R.
Existing closed-schema parsing and cryptographic checks validate every mandatory
field; new tests independently serialize a valid fixture and verify the ledger.
Required metadata is neither deleted nor shortened to improve the result.

The additive partition includes the entire media descriptor/base64 member,
certificate (creator attestation, technical evidence, reviewer votes, signed
messages, tallies and all signatures), reward/native transaction members,
header, other identity/reward/summary fields, envelope, delimiters and hash
wrapper. Signature token counts and reviewer evidence are diagnostic subsets,
not extra additive bytes. There is no separate producer-block signature field
in this frozen format; inventing one would misstate the measured schema.

Baseline records have fourteen votes (seven per dimension), an existing creator
reward and an empty native array. They are independent signed format fixtures,
not an admitted or ledger-valid chain. Eight additional records exercise valid
ten-vote certificates and unusually long nonces/captions/ten signed native
transfers using the same existing public test keys. Native signature/memo bytes
are thereby counted on real validated records, without pretending all baseline
blocks contain transfers or changing the primary distribution.

Outside R, counted separately in
[external_overhead.json](../benchmarks/task720_v1/external_overhead.json):
the existing finality-message and proof examples are **880 B and 1,194 B**,
respectively. These are examples, not a finality proof population or an assumed
constant per record. SQLite/pages/indexes/backups are not canonical media-block
metadata; existing 7.11 observations and their source hash are retained as
historical references only, with no new physical/index attribution. Unapproved
future review-journal commitments are excluded without an invented zero cost.
No unsafe historical WAL replay was attempted.

## 8. Statistics, denominator and the 15% decision

Percentiles use **nearest rank**, sorted value at `ceil(n × p / 100)`, giving
each record equal weight. The equal-record mean, `sum(N)/sum(R)` canonical-byte
weighted share, and `sum(M × metadata_percent)/sum(M)` original-byte weighted
mean are different statistics and are all retained. There are no measured
production-traffic weights. Per-MIME, size-band and combined MIME×size-band
statistics for both corpora are in [metrics.json](../benchmarks/task720_v1/metrics.json).

| Population | n | p50 % | p95 % | Worst % | Equal-record mean % | Canonical-byte share % | Original-byte weighted mean % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Historical complete v3 | 36 | 85.97237 | 99.60381 | 99.85557 | 70.81241 | 14.49136 | 7.74398 |
| New complete v3 | 34 | 54.70902 | 99.80752 | 99.81935 | 53.05444 | 7.14017 | 5.55595 |
| New image-only | 22 | 9.26784 | 99.73530 | 99.81935 | 39.53473 | 4.79743 | 3.08806 |
| New, current-validator accepted subset | 27 | 77.97423 | 99.80752 | 99.81935 | 65.92440 | 32.36367 | 24.69711 |

**The <15% criterion FAILS.** Only 12/34 new records are individually below
15%; none of the 12 text objects is below it. Image p50 passes, but p95 and
worst do not. A small canonical-byte weighted average is not a percentile pass.
All large image objects and all tiny ones retain their originally declared
membership. The stricter R−E definition cannot improve this verdict.

Sensitivity preserves security metadata and leaves primary weights unchanged:
for a 48-B text object, reducing a valid fourteen-vote certificate to ten votes
still produces **99.75300%** overhead. Long metadata with ten native transfers
raises it to **99.91537%**. For a 2,096,062-B PNG the corresponding scenarios
are **0.91605%** and **2.76604%**. A 7,322-B PNG has **73.38031%** and
**89.45722%**. These are measured, cryptographically valid format records, not
truncated certificates. Complete per-scenario byte ledgers are retained.

The dominant limitation is fixed evidence/identity cost relative to small or
strongly compressed payloads. Compressing media can raise its metadata fraction
while reducing total storage. For fixed N, N/R < 0.15 requires B > (17/3)N;
with roughly 33 KiB nonmedia overhead this needs roughly 188 KiB of base64
payload. This algebra explains the scale, not a proposal to pad media, discard
small uploads, change weights or remove security evidence. Any alternate
protocol encoding is a separate owner design decision outside this task.

## 9. Boundary and hostile-input coverage

The new boundary rows exercise tiny accepted text/images, real medium/near-cap
containers, canonical maximum text, high-compressibility and entropy controls,
invalid codec/version/MIME descriptors, wrong original hash, encoded/text
oversize, checksum corruption, framing expansion and a larger conforming
alternate record. All corrupt/oversized cases fail closed with recorded stage
and code. Selected records stay within unchanged component and total budgets.

Exact original/encoded limits are additionally exercised at 262,144/2,097,152 B;
the arbitrary-byte image-cap probe is explicitly a descriptor/codec boundary,
not an admitted image. Existing frozen-format regression tests also construct
real-signature records at maximum original image/text size, image caption caps,
native transfer limits and component budgets. The maximum image fixture has
an ancillary padding chunk; it establishes format/codec capacity, not current
technical admission of that metadata.

The complete-record 3 MiB gate is checked at cap−1/cap/cap+1. At-cap spaces
are not a valid canonical record. The existing conservative closed-schema bound
is **3,058,797 B**, 86,931 B below the total cap; an exact 3 MiB schema-valid
record is therefore not fabricated or claimed. Existing parser tests reject
at-cap noncanonical input and exercise actual fully signed large records.

Default decoder limits remain **128 MiB**, **5 s user CPU**, **10 s post-READY
wall time**, **5 s startup**, with one worker at a time in this measurement.
Windows job commit peaks and timings are recorded per worker and summarized
separately. Native codec benchmark parent peak memory is **unmeasured**; Python
allocation tracing is not offered as a native peak measurement. This is a
resource-evidence limitation, not an omitted zero. No test-only limit was raised.

## 10. The two historical test corrections

Only these two obsolete assertions were corrected, in the existing test module;
neither test was deleted and no production implementation changed.

1. Full-manifest equality previously demanded replay of old mutable validator
   observations, including 22 images' obsolete MALFORMED_MEDIA failures. It now
   calls the existing 7.19 `verify_manifest`: source hash/size, complete field
   inventory, ordering, dimensions, category, pinned encoder environment and
   all non-observation values still match. The existing independent test checks
   every original size/hash and Pillow dimension/validity. Twelve unchanged
   fail-closed reproduction guards also catch identity/schema/environment drift.
   Historical observation values remain untouched.
2. The genesis JPEG test previously required the repaired isolation defect to
   reject a valid JPEG. It now requires current acceptance, exact returned input
   bytes, independently computed SHA-256, and detected `image/jpeg`, retaining
   the independent Pillow JPEG validation. It is renamed to describe that current
   contract. The 7.12 repair and 7.19 triage establish why the requirement is
   obsolete; no consensus-critical requirement was reinterpreted.

Both corrected tests pass in the final regression selection. An initial edit
used lowercase `accept`; the current validator's exact outcome is uppercase
`ACCEPT`, and the assertion was corrected before the final run. The first new
measurement attempt had an aggregate-key construction error; a second attempt
incorrectly required every native Zstd candidate to meet the narrower strict
profile. Both stopped before complete results and are retained as failed
measurement-attempt logs. The final run explicitly records the rejected GIF
candidate and validates actual fallback; neither failed attempt is counted as
acceptance evidence or a passed test.

## 11. Reproduction, independent checks and test scope

Use the exact PowerShell commands in
[README.md](../benchmarks/task720_v1/README.md). The reference environment is
**Windows 11 build 26200, AMD64 CPython 3.13.5; Pillow 12.3.0 / JPEG 8.0 /
WebP 1.6.0; zstandard 0.25.0 / libzstd 1.5.7; Brotli 1.2.0; zlib 1.3.1;
cffi 2.0.0; eth-account 0.13.7; cryptography 49.0.0; pytest 8.4.1; SQLite
3.49.1**. No dependency was installed/upgraded. Native encoder cross-platform
byte identity is not assumed; source/environment/manifest drift fails closed.

The reference command is `python -B benchmarks/task720_v1/measure.py` using
`.venv/Scripts/python.exe`. A complete fresh run uses `--output temp/task720-replay`.
`crosscheck.py` independently recomputes all integer ledger partitions, base64
sizes, population coverage, adaptive choices, aggregate sums and nearest-rank
statistics without importing the instrumented measurement code. `compare.py`
requires exact replay of all non-timing/hash/size/admission results; only native
timings and worker process/resource observations are excluded. No numeric byte
tolerance or favorable drift is allowed. Output and source hashes are in the
checksum inventory, with fresh replay comparison hashes separately retained.

The focused regression selection is corpus/codec/image/composition,
strict decoder/sequences/performance/isolation/OS evidence, frozen v3 format,
the twelve 7.19 reproduction guards and nine new acceptance cases. Exact
commands, process bounds and node outcomes are retained under this directory.
No DB replay, atomic WAL crash suite, public API/socketpair test or unrelated
later consensus/journal suite is run. The 193 Linux-only tests are separately
reported skips on this Windows host; they are not passes. The four historical
security-gated WAL crash tests remain outside this selection, not newly passed.

## 12. Original-criterion acceptance decision

| Criterion | Decision | Evidence / smallest defensible next action |
| --- | --- | --- |
| A Codec benchmark representativeness | **PARTIAL** | Full declared MIME/size coverage, credible source/code structures, but synthetic images/events and no observed traffic distribution. Obtain a separately versioned, rights-cleared real-world media/usage sample before making production-population claims. |
| B Approximately 60–80% realistic compressible reduction | **PARTIAL** | New sufficiently sized prose/JSON reach or exceed the range and larger actual source reaches 65.09%; code p50 is 54.80% and tiny code 4.90%. Validate independent substantive source modules and human text; retain size/category results rather than promising 60–80% per file. |
| C Adaptive no-expansion selection | **PASS, isolated scope** | Actual producer, all 70 selected records and 8 sensitivities no larger than identity; beneficial but forbidden GIF candidate safely falls back; validator's separate larger-representation contract preserved. Active integration remains pending activation work. |
| D Byte-exact reconstruction | **PASS, measured scope** | 238 native trials, 70 selected records, 8 sensitivities exact; 139 valid strict source trials exact, one invalid candidate separately rejected. No universal decoder-security or active integration claim. |
| E Canonical metadata accounting | **PASS, frozen v3 scope** | 78 exact disjoint ledgers and independent partitions, closed required schemas/crypto, native/signature sensitivity; external finality and DB overhead separated. |
| F Less-than-15% representative production-like overhead | **FAIL** | New p50/p95/worst 54.71/99.81/99.82%; image-only p95/worst also fail. Owner must assess the target against small-media fixed evidence costs; any encoding redesign is separate work and cannot delete required evidence. |
| G Reproducibility | **PASS, pinned Windows scope** | Full independent local replay, deterministic byte/hash/admission comparison, independent arithmetic and checksum preservation. Linux containment, native benchmark peak memory and security-gated storage behavior remain distinct unverified qualifications. |

Missing real-world representativeness and native benchmark peak memory are
measurement gaps. High small-media metadata and the strict GIF frame limit are
current protocol/profile design limitations. Active compression integration is
pending approved version activation work, outside this task. Linux/security-gated
storage exclusions are platform/security qualifications. These are distinct
causes; none requires resuming the reviewer-journal redesign here.

The smallest resource-measurement follow-up is to run the unchanged candidate
settings in separately measured codec processes with reliable native peak-memory
instrumentation. Linux containment needs an actual Linux host, and gated WAL
crash verification needs a qualifying fixed SQLite runtime; neither should be
simulated by weakening today's gates. These remain follow-ups, not work begun
under Task 7.20.

**Ready for owner review and an owner-made commit of Task 7.20, with PARTIAL/FAIL
findings retained. This does not complete Milestone 7 or authorize activation.**

## Numerical appendix

The following tables are transcribed directly from the retained machine-readable
rows and independently cross-checked totals. Byte counts are exact; displayed
percentages are rounded only for readability.

### A. Raw codec byte-weighted reduction by category

| Category | identity-1 | zstd-3 | zstd-6 | zstd-9 | brotli-4 | brotli-6 | zlib-6 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| high_entropy_text | 0.00000% | 24.92371% | 24.92371% | 24.92371% | 24.96796% | 24.96033% | 24.25385% |
| image/gif | 0.00000% | 6.78028% | 6.93354% | 6.93354% | 8.12050% | 8.04827% | 6.55988% |
| image/jpeg | 0.00000% | 0.08801% | 0.09675% | 0.09693% | 1.38928% | 1.38232% | 1.04838% |
| image/png | 0.00000% | 0.00592% | 0.00646% | 0.00646% | 0.00342% | 0.00423% | -0.01847% |
| image/webp | 0.00000% | -0.00555% | -0.00555% | -0.00555% | 0.00004% | -0.00012% | -0.02890% |
| plain_text | 0.00000% | 87.55131% | 89.11593% | 89.75820% | 88.47231% | 89.95888% | 89.47676% |
| source_code | 0.00000% | 62.88359% | 64.30817% | 64.44539% | 64.07365% | 66.50616% | 65.14395% |
| structured_metadata_json | 0.00000% | 81.35711% | 82.64631% | 82.95552% | 82.33159% | 82.12208% | 80.44006% |

These are raw encoded/original reductions, before descriptor selection and strict-profile acceptance. Negative values are expansion.

### B. Default Zstd-3 category bytes, savings tails and encode/decode time

| Category | n | Original B | Encoded B | Savings p50 / p95 / worst % | Raw expansions | Encode p50 / p95 / worst µs | Decode p50 / p95 / worst µs |
| --- | ---: | ---: | ---: | --- | ---: | --- | --- |
| high_entropy_text | 1 | 65,536 | 49,202 | 24.92371 / 24.92371 / 24.92371 | 0 | 52.60 / 52.60 / 52.60 | 55.90 / 55.90 / 55.90 |
| image/gif | 6 | 2,648,358 | 2,468,792 | 6.64261 / 6.94981 / -30.23256 | 2 | 23.00 / 3142.80 / 3142.80 | 1.50 / 2135.30 / 2135.30 |
| image/jpeg | 5 | 2,757,687 | 2,755,260 | -0.00296 / 25.83201 / -0.00733 | 3 | 223.50 / 2103.60 / 2103.60 | 18.40 / 603.90 / 603.90 |
| image/png | 5 | 2,955,825 | 2,955,650 | -0.00491 / 4.06993 / -18.84058 | 4 | 43.70 / 862.10 / 862.10 | 18.50 / 596.50 / 596.50 |
| image/webp | 6 | 2,540,038 | 2,540,179 | -0.06797 / -0.00297 / -19.69697 | 6 | 15.60 / 924.50 / 924.50 | 1.70 / 635.40 / 635.40 |
| plain_text | 4 | 295,983 | 36,846 | 59.08203 / 87.83379 / -27.08333 | 1 | 5.00 / 324.30 / 324.30 | 1.90 / 110.00 / 110.00 |
| source_code | 3 | 40,082 | 14,877 | 54.79520 / 65.09446 / 4.90196 | 0 | 27.00 / 96.10 / 96.10 | 8.10 / 29.90 / 29.90 |
| structured_metadata_json | 4 | 217,654 | 40,577 | 73.60000 / 81.59275 / 29.28177 | 0 | 9.00 / 282.10 / 282.10 | 3.50 / 71.00 / 71.00 |

Time distributions are across per-object medians of nine repetitions; every raw timing sample and every profile/category distribution remains in codecs.json. Savings worst means minimum reduction; timing worst means maximum duration.

### C. Full canonical additive byte ledger

| Component | Historical 36 records B | New 34 records B |
| --- | ---: | ---: |
| certificate_bytes | 1,136,216 | 1,073,154 |
| delimiter_bytes | 684 | 646 |
| envelope_bytes | 5,220 | 4,930 |
| header_bytes | 8,559 | 8,083 |
| portable_wrapper_bytes | 3,132 | 2,958 |
| remaining_structural_metadata_bytes | 22,995 | 21,714 |
| serialized_media_representation_bytes | 7,055,315 | 14,678,466 |
| transaction_record_bytes | 9,180 | 8,670 |
| **Complete R (sum above)** | **8,241,301** | **15,798,621** |

Media/member overhead is included above, not an omitted additional charge. The following are diagnostic byte domains, not an additive second partition:

| Byte domain | Historical B | New B |
| --- | ---: | ---: |
| source_bytes | 6,093,917 | 11,521,163 |
| original_bytes | 6,093,910 | 11,521,163 |
| encoded_bytes | 5,285,229 | 11,002,892 |
| base64_media_bytes | 7,047,024 | 14,670,572 |
| nonmedia_bytes | 1,194,277 | 1,128,049 |
| Base64 expansion B − E | 1,761,795 | 3,667,680 |
| Descriptor/media-field framing | 8,291 | 7,894 |
| All bytes outside encoded E | 2,956,072 | 4,795,729 |

The new aggregate stricter `(R−E)/R` share is **30.35536%**, including base64 expansion. Exact per-record field paths/byte charges are in records.json; all 78 ledgers reconcile.

### D. New per-MIME and payload-size results

| Group | n | Metadata p50 % | p95 % | Worst % | Canonical-byte weighted % |
| --- | ---: | ---: | ---: | ---: | ---: |
| band:large | 8 | 1.17630 | 43.83898 | 43.83898 | 2.02530 |
| band:medium | 12 | 33.59717 | 84.76823 | 84.76823 | 18.36287 |
| band:small | 7 | 78.51529 | 98.34064 | 98.34064 | 80.03198 |
| band:tiny | 7 | 99.72327 | 99.81935 | 99.81935 | 99.39893 |
| mime:image/gif | 6 | 9.26784 | 99.81935 | 99.81935 | 5.40807 |
| mime:image/jpeg | 5 | 8.75968 | 98.15275 | 98.15275 | 4.32006 |
| mime:image/png | 5 | 8.69408 | 99.72327 | 99.72327 | 4.03854 |
| mime:image/webp | 6 | 13.69351 | 99.73530 | 99.73530 | 5.55099 |
| mime:text/plain | 12 | 84.76823 | 99.80752 | 99.80752 | 67.85656 |

Bands by accepted original bytes: tiny 1–1,023; small 1,024–16,383; medium 16,384–262,143; large 262,144–2,097,152. The exact upper text cap belongs to the large byte band. MIME×band and historical equivalents are in metrics.json.

### E. Focused regression outcomes and resources

| Completed selection | Passed | Failed | Skipped |
| --- | ---: | ---: | ---: |
| acceptance | 21 | 0 | 0 |
| measurements | 15 | 0 | 0 |
| codecs | 476 | 0 | 193 |
| format | 119 | 0 | 0 |
| **Disjoint final total** | **631** | **0** | **193** |

There are zero deselections. Acceptance includes nine new cases and twelve unchanged reproduction guards; measurements includes both corrected historical tests. All 193 skips explicitly require an actual Linux kernel; exact IDs/reasons are retained. No incomplete or earlier failed attempt is added to these totals.

| Worker observation (210 record/source trials) | p50 | p95 | Worst |
| --- | ---: | ---: | ---: |
| peak_job_commit_bytes | 13,217,792 | 25,948,160 | 26,431,488 |
| peak_process_commit_bytes | 11,948,032 | 24,727,552 | 25,223,168 |
| process_kernel_ns | 46,875,000 | 78,125,000 | 93,750,000 |
| process_user_ns | 31,250,000 | 125,000,000 | 171,875,000 |
| total_ns | 127,716,800 | 335,654,100 | 381,817,900 |

Commit bytes are Windows job/process measurements, not RSS. Sensitivity-worker and boundary-worker peak observations are not part of this 210-observation summary. Native in-process codec peak memory remains unavailable.

### F. Reproduction fingerprints

| Artifact | SHA-256 |
| --- | --- |
| admission.json | `9ed06d32d50438264215375f6c1e399e809bb87af7cddbf5a9b827402b486762` |
| codecs.json | `b53d1e7b72f185eecd919a76833870fa74d18135554c9aaf0e9ee6530e4f43b1` |
| historical_audit.json | `b1cbbe330deccda5b76e5f46c538b1a549460697d7eeeaa00c9da10053c6064b` |
| manifest.json | `f0f9a374f6e13c6cb38edf8b8d6ebe68d1a451dfaa756964040189aa2cee61a5` |
| metrics.json | `960ac0a6cba0e6a9bb809a3d3c098c6f5f5b2466269e743716df04f56aec8485` |
| records.json | `280b709a99400e05e0103c4ae2ba7c19de072dd028bc499412b38418e06fc9fc` |

The fresh second run reproduced manifest/metrics/admission/historical audit bytes exactly and all non-timing codec/record data exactly. Raw codec/record file hashes differ only because timing/process/resource observations are retained. Independent cross-checks pass on both runs. The complete inventory is checksums.sha256.
