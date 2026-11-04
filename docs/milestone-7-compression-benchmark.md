# Milestone 7 Task 7.4 — Lossless Compression Benchmark and Baseline Selection

Status: measurement complete and ready for review. This task adds no production compression, protocol change, validator change, reset, reward, or admission-limit change.

## Reproduction and scope

Run from the repository root:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-benchmark.txt
.\.venv\Scripts\python.exe scripts\milestone_7_task_7_3_corpus.py --verify
.\.venv\Scripts\python.exe scripts\milestone_7_task_7_4_benchmark.py
.\.venv\Scripts\python.exe -m pytest tests\test_milestone_7_task_7_3_corpus.py tests\test_milestone_7_task_7_4_benchmark.py -q
```

The checked-in machine-readable run is [`benchmarks/milestone_7_task_7_4_results.json`](../benchmarks/milestone_7_task_7_4_results.json). It has 252 per-sample/profile rows, original hashes, timing distributions, reconstruction checks, raw and descriptor-size estimates, and grouped aggregates. The runner first regenerates and byte-compares corpus `zoidbergchain-media-benchmark-v1` v1.1.0 against its manifest; the recorded manifest SHA-256 is in that result file.

Environment: Windows 11 / CPython 3.13.5, Pillow 12.3.0 (corpus only), `zstandard` 0.25.0, Brotli 1.2.0, and the CPython-linked zlib. Benchmark-only dependencies are pinned in `requirements-benchmark.txt`; no production requirement changed. Timings use `perf_counter_ns`, two warmups and nine per-operation repetitions, with median and nearest-rank p95 recorded. Imports, corpus generation/verification, and result writing are excluded. Native-code peak memory is deliberately reported as unavailable rather than guessed; `tracemalloc` would not reliably measure those allocations.

The corpus is a small, synthetic, stratified coverage set rather than a user-population sample: 36 samples / 6,093,917 bytes, including 31 primary-scoring samples and five capacity-only oversized images. Its public, deterministic composition means it is a reproducible baseline, not a competition-ready or representative holdout.

## Candidates and measured storage results

Identity, Zstandard levels 3/6/9, Brotli qualities 4/6, and standard-library zlib level 6 were tested. Zstandard uses one frame, checksum and content size, no dictionary, single thread, and `window_log=18` (256 KiB). Brotli uses generic mode, `lgwin=18`; zlib uses one zlib-wrapped DEFLATE stream with `wbits=15`. The exact profile data, framing, compatibility notes, and versions are in the JSON result.

Savings below are adaptive **effective media-object** savings: each profile is compared with the proposed v3 identity descriptor, including codec fields, SHA-256, sizes, and strict base64 payload. This is an explicitly labeled estimate, not a measured complete canonical block: the future certificate, transactions, envelope, and signature overhead are not implemented yet.

| Profile | Primary scoring | All images | Text/plain | Encode / decode MB/s* |
| --- | ---: | ---: | ---: | ---: |
| Zstd-3 | 35.21% | 13.03% | 81.07% | 642 / 4,113 |
| Zstd-6 | 35.76% | 13.61% | 81.50% | 267 / 3,947 |
| Zstd-9 | 35.77% | 13.63% | 81.53% | 247 / 4,047 |
| Brotli-4 | 37.22% | 13.98% | 81.90% | 134 / 638 |
| Brotli-6 | 38.39% | 14.44% | 82.76% | 39 / 619 |
| zlib-6 | 35.58% | 12.11% | 80.64% | 74 / 464 |

\*Aggregate source bytes divided by the sum of per-sample median times. They are local benchmark figures, not validator service-level guarantees.

For Zstd-3—the recommended performance/storage baseline—adaptive effective savings by MIME are: text/plain 81.07% (one small file expands), JPEG 28.43% (one expands), PNG 0.64% (one expands), WebP 1.70% (two expand), and GIF 6.15% (five expand). All profiles reconstruct every original byte and SHA-256 exactly. The JSON provides p50/p95 savings, worst case, expansion count, byte-weighted savings, raw and encoded size distributions by MIME/category, and per-sample variability.

The following Zstd-3 image distributions are bytes over the combined in-limit and capacity corpus; percentiles use nearest rank. They make the capacity tail visible rather than folding it into primary scoring.

| MIME | Original p50 / p95 / p99 / max | Encoded p50 / p95 / p99 / max | Adaptive savings | Expansions |
| --- | --- | --- | ---: | ---: |
| JPEG | 66,371 / 1,530,684 / 1,530,684 / 1,530,684 | 21,220 / 1,530,734 / 1,530,734 / 1,530,734 | 28.43% | 1/7 |
| PNG | 4,314 / 1,772,761 / 1,772,761 / 1,772,761 | 1,883 / 1,772,817 / 1,772,817 / 1,772,817 | 0.64% | 1/7 |
| WebP | 10,992 / 625,250 / 625,250 / 625,250 | 10,322 / 625,279 / 625,279 / 625,279 | 1.70% | 2/7 |
| GIF | 4,961 / 802,666 / 802,666 / 802,666 | 4,975 / 748,847 / 748,847 / 748,847 | 6.15% | 5/6 |

The text/metadata/code goal is supported only for sufficiently sized structured content: Zstd-3 achieves 81.07% byte-weighted saving over all nine text samples; its structured metadata subset is strongly compressible, while the tiny 36-byte caption expands because framing dominates. Thus “about 60–80%” is defensible for this corpus’s aggregate text payload, not as a guarantee for individual short texts. Do not manipulate or pad uploads to obtain that result.

## Image capacity findings

Primary scoring contains 22 in-limit images; five capacity-analysis images are kept separate. With Zstd-3, the five original/encoded pairs are JPEG photo-like 689,193/173,191; JPEG noise 1,530,684/1,530,734; PNG noise 1,772,761/1,772,817; WebP noise 625,250/625,279; GIF noise 802,666/748,847 bytes. Exact original file bytes—not pixels, transcodes, or format changes—were compressed.

At the current 256 KiB original and stored caps, compression does not make an oversized original admissible because the original cap remains binding. For later evaluation, a 1 MiB original limit paired with a 256 KiB encoded limit would let one of these five capacity samples (the 689 KiB JPEG) fit through encoding; the other four would not. This corpus is too small to set a final cap. Retain 256 KiB / 256 KiB as the conservative candidate and evaluate 512 KiB and 1 MiB originals only after exact record/certificate overhead is measured. Do not choose a complete-block cap yet.

JPEG had useful aggregate compression in this constructed set, but PNG/WebP/GIF gains were slight and individual containers frequently expanded. Adaptive fallback to identity is therefore required: retain original bytes whenever the complete descriptor representation is not smaller, not merely when the raw compressed payload is smaller. Across profile results, this avoids every expansion by construction.

## Recommended initial policy and safety gates

Recommend `identity/1` plus one **candidate** `zstd/1` profile based on Zstd level 3 with the fixed settings above. It is materially faster to encode than higher Zstd and Brotli profiles, while storage differences versus Zstd-6/9 are small on primary scoring. This is a benchmark recommendation, not authorization to add a live codec: the current specification has no compressed profile ID and must not claim activation readiness.

If later selected, consensus rules must freeze the exact Zstandard frame grammar/version profile; require one frame, checksum, content-size field equal to declared original size, no dictionaries, no skippable/concatenated frames or trailing data, and frame window at most 256 KiB. Decoders must enforce stored bytes <= 256 KiB before decoding, decoded bytes exactly equal declared original size and <= 256 KiB, and bounded allocation/work accounting. They must reject malformed headers, output overrun, checksum failure, undeclared content size, and unconsumed input. Require independent decoder/platform agreement and a deterministic Zstandard work bound before activation; this benchmark does not establish either. Brotli and zlib remain comparison baselines, not recommended consensus codecs.

## Limitations and next task

Measurements do not include a real complete block, validator worker, peer transport, database/snapshot layout, cross-language decoders, malicious-frame tests, RSS, or a rights-cleared real-world upload distribution. Capacity results and percentiles should not be generalized beyond this corpus. The next task should first close the compressed-profile security and interoperability gates, then measure exact canonical-record overhead before any implementation or limit decision.
