# Milestone 7 Task 7.6 — Strict codec decoder conformance and security validation

Date: 2026-10-18. **Isolated prototype and evidence ready for review; full strict Zstd conformance and production activation remain blocked.** In particular, release libzstd does not establish the strict per-sequence window rule. The public adapter fails closed as **unvalidated** where it cannot prove that rule. Successful reconstruction is not conformance approval.

## Repository and scope

Expected/actual branch: `Compression-State-Bloat-and-Node-Economics`. Starting and final HEAD: `744d427fc973a0e00aae93fcd4161702485b5099` (`Milestone 7 Task 7.5: define codec security and consensus contract`). Task 7.5 is separately committed; the initial worktree was clean. No applicable repository/ancestor `AGENTS.md` was found. Final changes are newly added prototype, dependency, test, fixture, measurement, and documentation files only. No existing tracked file is modified, no Git staging/commit/push/merge/deployment occurs, and no chain state is opened/reset.

Read the [architecture](milestone-7-architecture.md), [protocol](milestone-7-compression-protocol.md), [security contract](milestone-7-codec-security-contract.md), [benchmark](milestone-7-compression-benchmark.md), and [image evaluation](milestone-7-image-compression-evaluation.md). Existing benchmark compressor settings, deterministic corpus/manifest, protocol JSON/hash conventions, and validation tests were inspected. Existing production consensus, block creation/admission, storage, sync, media validation and API modules do not import this prototype. There are no active block-format changes. This task implements no block/certificate/signature/evidence/uniqueness/lifecycle integration or subsequent milestone work.

## Implementation boundary and validation methodology

[`codec_prototype/strict_decoder.py`](../codec_prototype/strict_decoder.py) is self-contained apart from the pinned codec bridge. Its public `decode(descriptor)` returns bytes only after all implemented checks pass. `parse_descriptor(raw)` optionally handles a **canonical standalone descriptor**, with a bounded byte length, UTF-8/canonical serialization, duplicate-key rejection and a flat-JSON structural check before object construction. It is not a block/page parser. Caller-supplied protocol/block/network/policy context is outside this codec-only boundary.

Validation order:

1. Require the exact eight keys; exact integer types excluding booleans; encoding/profile versions 1; exact `identity`/`zstd` identifiers; permitted MIME spelling; lowercase SHA-256 syntax; nonempty original and encoded lengths bounded independently by candidate A=B=2,097,152 bytes.
2. Check base64 character length against `stored_size` before decoding. Require standard alphabet, exact decoded size, minimal padding and zero pad bits through decode/re-encode equality. No codec guessing.
3. Identity requires E=M and exact original size; verify SHA-256 of those exact bytes. Zstd preflight checks exact magic, rejects all sixteen skippable magics, both forbidden descriptor bits, all dictionary-ID fields including explicit zero, missing checksum/content-size, false content size, and W>262,144. Single-segment W equals FCS; other windows use the contract exponent/mantissa formula. All permitted/nonminimal FCS widths are accepted.
4. Walk bounded block headers/bodies through exactly the final checksum end; reject reserved type, header/body sizes over `min(W,131072)`, truncation, a 65th block, concatenation and any trailing bytes. The structural walk skips bodies without copying them. This does not validate entropy/sequence contents.
5. Initialize fresh dictionary/prefix-free native state in an aligned caller-owned static arena. Use bufferless streaming `ZSTD_nextSrcSizeToDecompress`, `ZSTD_nextInputType`, and `ZSTD_decompressContinue`. Each call consumes its exact requested slice or fails; every nonterminal call makes positive input progress. This is an alternative to `ZSTD_decompressStream`, avoiding unbounded accumulating convenience APIs.
6. Allocate exactly `original_size` output bytes. Each native call receives at most the remaining output capacity **and** `min(W,131072)`, enforcing regenerated block size as well as total output. Retain contiguous output for same-frame history. Native entropy/table/sequence corruption and absent external dictionary references fail in libzstd; no dictionary retry exists. Require terminal native state, checksum verification, all E consumed, exact actual output length and original SHA-256. Full output without the last checksum byte rejects.
7. Where compressed output extends beyond W, release libzstd cannot prove every offset <=W; the public adapter withholds the result as `DecoderUnavailable`. Raw/RLE-only later blocks have no back-references. Compressed output entirely within the first W bytes cannot refer farther than W because the context starts empty. This conservative availability guard does **not** redefine invalid bitstreams or create a new narrower consensus profile.

`CodecReject` carries stable `stage`/`code` categories (`descriptor`, `frame`, `decode`, `integrity`); native English error messages are not protocol categories. Native checksum failure maps to `decode:checksum`; other malformed internals map to `decode:invalid_stream`. Version/setup/allocation/workspace failures and unproven window conformance are local `DecoderUnavailable`, meaning **unvalidated**, with no output returned. There is no time-based invalidity decision.

The private `_decode_native` function is also used by the measurement harness to diagnose byte reconstruction when the public adapter is unavailable. It is **not a second acceptance API**; its `compressed_history_unproven` result must not be ignored in validation. No production caller exists. A future worker must return no usable bytes on local failure.

## Toolchain and reproducible commands

Executed on Windows 11 build 26200 / AMD64, CPython 3.13.5 (MSC 1943, 64-bit), `zstandard` 0.25.0, libzstd 1.5.7 in both installed cext and CFFI builds, CFFI 2.0.0. Corpus generation uses the existing pinned Pillow environment. [`requirements-codec-prototype.txt`](../requirements-codec-prototype.txt) reuses benchmark dependencies and pins CFFI; it changes no production requirement. The bridge `zstandard._cffi` and static-only native APIs are private/version-specific; other builds must be explicitly audited. The adapter refuses a different package/libzstd version, rather than silently drifting.

Run from the repository root in the existing development environment:

```powershell
# Optional environment setup; no installation was needed for this run:
.\.venv\Scripts\python.exe -m pip install -r requirements-codec-prototype.txt

# Replay frozen fixtures, verify corpus, compare producers, measure resources:
.\.venv\Scripts\python.exe scripts/milestone_7_task_7_6_conformance.py > temp/task76-measurements.txt 2>&1

# Exact final regression command:
.\.venv\Scripts\python.exe -m pytest tests/test_milestone_7_task_7_6_decoder.py tests/test_milestone_7_task_7_3_corpus.py tests/test_milestone_7_task_7_4_benchmark.py tests/test_milestone_7_task_7_4a_image_evaluation.py tests/test_protocol_v1.py::test_bytes_are_deterministic_and_round_trip tests/test_protocol_v1.py::test_domain_separation_changes_bytes_and_hashes tests/test_protocol_v1_golden_vectors.py::test_canonical_serialization_vectors_match_runtime tests/test_protocol_v1_golden_vectors.py::test_block_vectors_match_runtime -q --tb=short > temp/task76-regression-final.txt 2>&1

git diff --check
```

Final regression: **155 passed in 21.90 seconds**. The suite includes decoder replay, JSON boundary checks, bounded systematic bit mutations, preflight-before-native assertions, output-overrun probes, checksum completion, dictionary state isolation, backend/local-failure distinctions, encoder-free operation, production-import absence, and baseline corpus/report consistency. Corpus regeneration/verification and the measurement runner completed successfully. Lengthy logs are in ignored `temp/`; durable evidence is [`benchmarks/milestone_7_task_7_6_results.json`](../benchmarks/milestone_7_task_7_6_results.json), including source hashes, raw timings, every corpus row and vector result. Source hashes, fixture inventory/digests, local documentation links, UTF-8, trailing whitespace, final-newline conventions and `git diff --check` pass. The whole repository suite was not run; production integration is absent.

Intentional fixture regeneration only (not needed for replay):

```powershell
.\.venv\Scripts\python.exe scripts/milestone_7_task_7_6_vectors.py
```

## Golden vectors and integrity

Versioned suite `zoidbergchain-codec-conformance` **1.0.0** lives in [`tests/fixtures/milestone_7_codec_v1/manifest.json`](../tests/fixtures/milestone_7_codec_v1/manifest.json). Manifest SHA-256:

```text
0cef315b6514cd7d19a6e74ad685dab5aa9ea9cdff9996f571bbc90f50fb66a5
```

The manifest binds each stable ID to canonical descriptor file bytes and their SHA-256, exact original binary file/length/SHA-256, encoded SHA-256 where base64 can be interpreted, and expected profile/prototype stage/outcome. E is committed verbatim as base64 in each descriptor; replay never needs an encoder. Shared originals are content-addressed. Inputs are bounded; the largest original is 2 MiB. There are no fixture timestamps or unspecified random generators. Binary samples are codec-layer inputs, not claims of valid MIME containers or accepted chain records.

| Inventory | Results |
| --- | --- |
| Positive codec vectors | 21 accepted; exact output bytes/count/SHA-256 and consumed E verified twice each |
| Negative codec vectors | 94 rejected with expected deterministic stage/code, twice each |
| Known strict-window gap | 2 withheld as unvalidated: one profile-invalid forged-offset frame, one producer-valid cross-window compressed frame |
| JSON/parser and other adversarial checks | Separate unit cases for duplicate keys, nesting, arrays, bad UTF-8/surrogates/NaN, noncanonical JSON and oversized JSON; scalar-type matrix and bounded bit mutations |

Positive coverage includes identity/base64 remainder cases, identity at A/B, high-ratio Zstd at A, default/non-default compression, raw/RLE/compressed blocks, single/non-single segments, FCS widths 1/2/4/8 including nonminimal widths, W at/below ceiling, exactly 64 empty/tiny blocks and encoded expansion. Negative coverage includes magic/magicless, all skippable variants, truncation at every boundary of a small frame, missing/corrupt checksum, missing/false FCS, wrong hash, over-window/single-segment windows, all dictionary field widths with zero/nonzero IDs, unadvertised raw dictionary dependency, reserved flags/block type, malformed literals/tables/sequences, absent final block, trailing zero/garbage/skippable suffix, nonempty/empty second frame, output under/overrun, excessive regenerated block size, over-A bombs/lying sizes, over-B declaration, empty fields, false sizes, malformed base64, missing/extra keys and unknown codec/profile/encoding.

The two `unvalidated` fixtures explicitly retain `profile_expected` values `reject` and `accept`, respectively. They are **unresolved conformance cases**, not passing accept/reject vectors, xfails, or new profile rules. This suite does not cover the full Task 7.5 block/network/signature/media/lifecycle vector inventory; those require later integration and frozen launch context.

## Window and corpus findings

All 36 verified corpus inputs (9 text, 27 images, including 5 oversized capacity-only samples) reconstructed exactly as identity. With restricted Zstd-3 (`window_log=18`, checksum/FCS on, dictionary off, threads=0), all 36 emitted headers and block layouts meet the proposed profile bounds and all 36 native audit decodes reproduce exact M and SHA-256. **34/36** also complete the strict public adapter; the JPEG gradient and GIF noise capacity frames remain unvalidated by the history guard. No compressor reproduction is required during replay/validation.

| Oversized sample | M bytes | Restricted E bytes | Data blocks | Strict public status |
| --- | ---: | ---: | ---: | --- |
| jpeg-photo-like | 689,193 | 173,191 | 52 | Unvalidated window/offset proof |
| jpeg-noise-capacity | 1,530,684 | 1,530,734 | 12 | Accept |
| png-noise-capacity | 1,772,761 | 1,772,817 | 14 | Accept |
| webp-noise-capacity | 625,250 | 625,279 | 5 | Accept |
| gif-noise-capacity | 802,666 | 748,847 | 39 | Unvalidated window/offset proof |

All restricted encoded byte counts match Task 7.4. Every corpus M/E fits candidate A=B=2 MiB; incompressible images still expand. These are synthetic, deterministic benchmark samples, not a real-world upload distribution or a final capacity-policy decision.

Producer comparison uses identical M, flags, level 3, thread count, warmups and repetitions; only `window_log=18` versus the level's default window differs:

| Producer | Aggregate E | Encode MB/s from summed per-sample median times | Window/header acceptance |
| --- | ---: | ---: | --- |
| Restricted 256 KiB | 5,285,466 | 648.35 | 36/36 within window/block bounds |
| Default window | 5,278,909 | 658.12 | 31/36; all 5 oversized samples exceed W |

Restriction costs 6,557 encoded bytes across this corpus (about 0.124% of default E) and about 1.48% aggregate encode throughput in this local run. This is not a universal performance penalty. Default-window maximum is 1,772,761 bytes; restricted maximum is 262,144. Exact per-sample timing distributions and hashes are recorded in the report.

### Strict-offset blocker and proposed contract clarification

`offset-exceeds-declared-window` contains eight distinct raw 1,024-byte blocks followed by a compressed repeat of the first block. The actual backward distance is 8,192; the forged header declares W=1,024 and every block stays within 1,024 regenerated bytes. The original length is 9,216, checksum and SHA-256 are correct. Both installed release libzstd wrappers reconstruct it with the retained contiguous output; native output/window capacity checks alone do not reject it. The public prototype reports unvalidated and never returns those bytes.

Pinned source inspection supports the observation: the [sequence-validation assertion](https://github.com/facebook/zstd/blob/v1.5.7/lib/decompress/zstd_decompress_block.c) checks offset against W only behind fuzz/debug compile guards. The [format](https://github.com/facebook/zstd/blob/v1.5.7/doc/zstd_compression_format.md) requires available history up to W. Header-window limits and actual offset validity must therefore be treated as separate audit requirements.

Proposed exact clarification for Task 7.5 section 4, **left for review; the contract is unchanged**:

> In addition to preflighting the declared window, the adapter MUST verify that each decoded sequence offset is no greater than the declared frame window and does not reference unavailable same-frame history. Header parsing, destination capacity, and ZSTD_DCtx_setMaxWindowSize alone do not establish this property for release libzstd. If the selected implementation cannot prove it, the result remains unvalidated and the profile MUST NOT be activated. A local inability to prove this property MUST NOT be mapped to consensus-invalid.

Resolution requires an audited checked/instrumented decoder build or another vetted implementation with explicit offset validation, followed by these fixtures and independent-node agreement. Removing the window rule or pretending ordinary streaming APIs prove it is not justified by this task. There is no silent amendment to frozen grammar or consensus limits.

## Block-count and resource findings

The 64-data-block ceiling is straightforward to enforce before native calls. Restricted Zstd-3 reaches **52** blocks on the JPEG gradient, well above the sixteen full-block assumption but below 64. It remains feasible for this corpus with twelve blocks of margin; smaller-flush encoders can still exceed it and must select another permitted representation/identity. Exactly 64 accepts and 65 rejects. Do not loosen the cap based on averages.

It is **insufficient as a complete work bound**. Keep it as structural protection and require a reviewed semantic bound/counters for sequence execution, literal decoding and entropy/table construction, including failed streams. A proposed addition to the activation gate is: “The reference decoder must expose reviewed counters for sequences, decoded literals and table construction, with exact increment and failure rules and golden boundary vectors; alternatively publish an equivalent finite algorithmic proof.” A valid-stream sequence candidate bound is `floor(A/3)` because each match emits at least three bytes, but this alone omits table construction and malformed-stream paths. No arbitrary new threshold or fabricated complete work formula is frozen here.

Measurements use `perf_counter_ns`, two warmups/nine corpus trials; resource/error probes use 101 trials, median/nearest-rank p95. Fresh context creation, output allocation, hashing and immutable-result copy are included in native-audit timing. Base64/descriptor/frame checks are additionally included in public-boundary timing. Native audit throughput: **841.04 MB/s** over all samples, **850.57 MB/s** over 27 images, **836.09 MB/s** over five oversized samples. Complete public-boundary throughput is **198.52 MB/s** over its 34 accepted samples; these groups are different and not directly interchangeable.

| Bounded resource probe | Median / p95 elapsed | Native calls | Native arena | Output capacity |
| --- | ---: | ---: | ---: | ---: |
| 64 bytes, one raw block | 13.6 / 17.3 microseconds | 5 | 95,968 bytes | 64 bytes |
| Same 64 bytes, 64 one-byte blocks | 125.9 / 138.9 microseconds | 131 | 95,968 bytes | 64 bytes |
| One byte, 63 empty + one raw block | 81.8 / 93.9 microseconds | 68 | 95,968 bytes | 1 byte |
| 2 MiB repeated byte, 87-byte frame | 1,883.6 / 2,193.4 microseconds | 35 | 95,968 bytes | 2,097,152 bytes |

The 64 tiny-block frame takes about **9.26x** the one-block elapsed time for identical output, including Python framing/native-call overhead. The 2 MiB case expands about **24,105x** yet fits A and the exact output bound, so a high ratio alone is correctly accepted. Checksum corruption, malformed sequence tables, truncation, 65 blocks and a lying bomb size reject at medians 12.8, 11.8, 4.3, 23.6 and 4.1 microseconds respectively. These measurements are observations, not worst-case adversarial CPU guarantees.

Windows process CPU clocks are coarse, so the report also records fixed batches: 2,048 one-block decodes consume 31.25 ms CPU; 2,048 tiny-block decodes 265.625 ms; 2,048 mostly-empty-block decodes 156.25 ms; 128 high-ratio decodes 234.375 ms. Each figure is the median of three measured batches after one warmup batch. Per-operation CPU times often quantize to zero; raw batch CPU/elapsed samples are retained. No elapsed deadline or CPU measurement changes validity.

The native context uses an **explicit fixed 95,968-byte arena**, independently confirmed by `ZSTD_sizeof_DCtx`. The pinned [static-context API contract](https://github.com/facebook/zstd/blob/v1.5.7/lib/zstd.h) specifies that it does not resize/malloc and errors if its arena is insufficient. It is not freed through the native destructor; CFFI owns the workspace lifetime. This is stronger evidence about this build's heap context than a Python allocation trace, but excludes native stack, interpreter/CFFI/allocator overhead and other host memory. A local 1 MiB arena guard causes unvalidated failure if a future build requires more; it is not consensus validity or a portable state-budget proof.

Peak caller-owned decoded storage is exactly A during reconstruction and **2A=4,194,304 bytes** temporarily while copying into returned immutable bytes, in addition to E, base64 strings and bounded descriptor/parser overhead. The high-ratio probe's Python `tracemalloc` peak is 2,098,158 bytes; **it misses the native output/arena and is not a portable native-memory or RSS guarantee**. Process RSS/peak working set is not measured. The 256 KiB history setting does not imply a 256 KiB total decoder process budget.

## Independence, remaining controls and review disposition

The installed cext and CFFI high-level raw decoders agree on output/error/length/SHA-256 for all **92** Zstd fixture inputs compared. Raw libraries intentionally accept some profile-forbidden forms, so this comparison does not claim profile conformance. Both wrap libzstd 1.5.7; **algorithmic independence is not established**. No Go/Rust/Zstd CLI alternative was available in the checked toolchain. No second OS or architecture was executed. A Windows subsystem launcher alone is not Linux testing.

Before activation, run the frozen suite against a second independent decoder algorithm and supported Windows/Linux architectures. Compare profile validity, exact E consumption/terminal status, checksum, FCS/window interpretation, reconstructed M/SHA-256 and error stages, including the unresolved offset probe. Extend with reviewed pathological table/offset/repeat/sequence fuzzing and native sanitizers; current bounded malformed vectors are not exhaustive. Repeat after security/library changes. Later block/signature/lifecycle vectors must bind frozen launch identity and run through real validation/sync/import/restore boundaries.

Remaining security blockers are the strict per-sequence window gap; reviewed deterministic work bound/counters; portable state/stack accounting; private binding portability/audit; native crash isolation and production workers with restricted network/filesystem/credentials, process memory, concurrency, queues and cancellation/backpressure; independent implementation/platform verification; and the separately unresolved media-worker isolation issue. No watchdog, worker sandbox or portable process-memory control is implemented here, and a native fault in this in-process prototype can still terminate its host. It must remain offline tooling. Final A/B/C and complete-record/admission fit remain unresolved launch work.

The artifacts are reviewable and suitable for an explicitly scoped **prototype/evidence commit** after human review. **Task 7.6 cannot receive full strict-decoder security/conformance sign-off with this backend**, and production integration/activation remains blocked. No commit is created, no contract rule is changed, and the next task is not begun.
