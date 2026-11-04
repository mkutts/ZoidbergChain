# Milestone 7 Task 7.4A — Image-Specific Lossless Compression Evaluation

Status: complete and ready for review. This is a measurement and codec-selection extension only; it changes no production implementation, protocol, consensus rule, validator, corpus, or admission limit.

## Verification, commands, and evidence

Task 7.4 is the committed predecessor (`eb1f685`). Its corpus and raw results are retained unchanged. This task reads the checked-in Zstd-3 rows rather than re-benchmarking a different workload.

```powershell
.\.venv\Scripts\python.exe scripts\milestone_7_task_7_3_corpus.py --verify
.\.venv\Scripts\python.exe scripts\milestone_7_task_7_4_benchmark.py
.\.venv\Scripts\python.exe scripts\milestone_7_task_7_4a_image_evaluation.py
.\.venv\Scripts\python.exe -m pytest tests\test_milestone_7_task_7_4a_image_evaluation.py -q
```

[`benchmarks/milestone_7_task_7_4a_image_results.json`](../benchmarks/milestone_7_task_7_4a_image_results.json) records its configuration, hashes of the corpus manifest and source baseline result, per-JPEG container diagnostics, and complete image-only aggregates. The original Task 7.4 result remains the source for its timing distributions and 27 per-image Zstd-3 records.

The image corpus is unchanged: 27 repository-authored, deterministic **synthetic** image files (7 JPEG, 7 PNG, 7 WebP, 6 GIF), including five capacity-analysis examples. It contains no independently sourced real-world images. A rights-cleared, representative corpus was not added: downloading arbitrary meme images would not establish adequate rights or provenance, and none is bundled with the repository. Consequently, this report does not generalize to real-world meme uploads or assign user-upload weights. Equal-sample percentiles and corpus-byte-weighted figures are both shown only as explicit evaluation assumptions.

## Candidates

Identity and Zstd-3 are actually tested via Task 7.4. Zstd-3 uses one frame, checksum/content-size, no dictionary, one thread, and a 256 KiB window; it reconstructs all 27 tested image files byte-for-byte and matches all original SHA-256 values.

JPEG XL JPEG-reconstruction is **not tested**. `cjxl`, `djxl`, and `jpegtran` are absent, and no audited JPEG XL Python binding is installed. This task intentionally did not add a native experimental dependency. The reference libjxl documentation says that JPEG XL can retain JPEG reconstruction data sufficient to recreate the exact original JPEG file, and its CLI documentation says `cjxl` defaults to lossless JPEG recompression while `djxl` can reconstruct a `.jpg` output exactly when reconstruction data is present. [libjxl format overview](https://github.com/libjxl/libjxl/blob/main/doc/format_overview.md) [libjxl CLI documentation](https://github.com/libjxl/libjxl/blob/main/doc/man/djxl.txt)

That capability is not blanket proof for this corpus or for consensus use: the report has no local byte-exact encode/decode evidence, no pinned libjxl release, no independent decoder test, and no malformed-frame evaluation. Ordinary PNG optimization, metadata stripping, JPEG re-encoding, and coefficient-domain JPEG transforms are not candidates because pixel equality does not reproduce original file bytes, metadata, chunk/marker ordering, or original entropy streams. They are recorded as not applicable to the byte-identity contract, not as failed compression trials.

## Zstd-3 image findings

| MIME | Samples | Raw p50 / p95 savings | Raw byte-weighted savings | Raw expansions | Adaptive effective savings | Exact reconstructions | Encode / decode MB/s* |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| JPEG | 7 | 63.88% / 83.60% | 28.44% | 1 | 28.43% | 7/7 | 645 / 2,517 |
| PNG | 7 | 56.31% / 70.53% | 0.64% | 1 | 0.64% | 7/7 | 2,428 / 3,844 |
| WebP | 7 | 4.92% / 20.56% | 1.69% | 2 | 1.70% | 7/7 | 1,610 / 11,522 |
| GIF | 6 | -0.28% / 6.71% | 6.15% | 5 | 6.15% | 6/6 | 951 / 1,372 |

\*Source bytes divided by summed per-sample median time from the Task 7.4 local run. These are not cross-platform validator guarantees. Native-code peak memory remains unmeasured rather than inferred.

“Adaptive effective” compares the complete proposed media descriptor (including base64 and descriptor fields) against identity and retains identity when it is smaller. Thus its storage result has no expansion by definition; the raw-expansion columns are the important evidence that a producer must make this choice per complete representation, especially for GIF/WebP/PNG.

## Why the earlier JPEG result was high

The 28.44% JPEG byte-weighted saving is a corpus artifact, not a JPEG population estimate. All seven JPEG files are emitted by the same deterministic Pillow/libjpeg path (quality 91, non-progressive, 4:4:4); each has the same small 14-byte JFIF APP payload, no comment payload, and the same pre-scan marker layout. It is therefore not metadata stripping or variable camera/application metadata.

Six synthetic low-structure gradient/poster/illustration files total 970,009 bytes and compress by 73.32% with Zstd-3. The one seeded high-entropy JPEG is 1,530,684 bytes—over 61% of JPEG corpus bytes—and expands slightly (1,530,734 bytes). That single capacity-only outlier reduces the combined byte-weighted JPEG result to 28.44%, while nearest-rank p50/p95 statistics describe the six highly compressible synthetic members. This directly identifies synthetic construction, shared encoder settings, and byte-size weighting as the cause; it does not establish a real-world JPEG benefit.

## Security, maintenance, and policy decision

JPEG XL’s documented JPEG bitstream reconstruction is technically relevant, and libjxl is available under BSD-3-Clause with an additional IP-rights grant. [libjxl README and license statement](https://github.com/libjxl/libjxl/blob/main/README.md) Its use as a consensus decoder would nevertheless add a permanent native decoder dependency, a second complex image/container parser, profile/version pinning, output/window/work bounds, exact trailing-input behavior, cross-platform testing, and historical verification burden. The JPEG reconstruction path also needs a rule that rejects any input for which exact reconstruction is unavailable; falling back to pixel decode/re-encode is prohibited.

Recommended initial strategy: **Option A — identity plus Zstd-3**, with complete-representation adaptive fallback. Do not add JPEG XL or a PNG/JPEG-specific codec at this stage. The only executed image-specific evidence is the existing Zstd baseline; it is not sufficiently representative to justify a second consensus codec, and JPEG XL has no local byte-exact evidence yet. The minimum future gate for Option B is a pinned libjxl toolchain tested against a separately versioned, rights-cleared real-world corpus, with byte equality/hash checks on every JPEG plus malformed-frame, resource-bound, independent-decoder, license review, and fixed-frame profile tests.

## Remaining blockers

No real-world image corpus; no local JPEG XL/JPEG reconstruction run; no exact full canonical record/certificate overhead; no native RSS figure; no independent decoder or adversarial frame test; and no deterministic consensus work bound. These block JPEG XL activation and any final image-oriented codec or limit decision. They do not block review of this evaluation.
