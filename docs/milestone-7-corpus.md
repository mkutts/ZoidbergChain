# Milestone 7, Task 7.3 / 7.3A — Representative Media Benchmark Corpus

Status: prepared for review.  This task creates a reproducible corpus and capacity analysis only.  It does **not** select, implement, run, or report a compression algorithm.

## Method and scope

The versioned machine-readable contract is [`tests/fixtures/milestone_7_corpus_v1_manifest.json`](../tests/fixtures/milestone_7_corpus_v1_manifest.json).  [`scripts/milestone_7_task_7_3_corpus.py`](../scripts/milestone_7_task_7_3_corpus.py) deterministically regenerates every sample from repository-authored pixels or UTF-8 source bytes, records SHA-256 and metadata, and verifies the result against that manifest.  It neither downloads material nor needs network access.

Generated binary files are deliberately written only to an operator-chosen ignored `artifacts/` destination; Git tracks the small manifest, generator, documentation, and focused tests instead.  Every image is direct-decoded with Pillow to establish container validity.  Current application admission is recorded separately because this execution environment cannot run the validator's isolated image worker (see [JPEG investigation](#jpeg-validation-investigation)).

The corpus contains no corrupt or adversarial input.  Those remain security-test material and are explicitly excluded from representative statistics and future benchmark scoring.

## Current admission inventory and corpus composition

Current policy admits `image/jpeg`, `image/png`, `image/gif`, `image/webp`, and canonical UTF-8 `text/plain`.  JSON, structured metadata, and source code in this corpus are comparison subcategories stored as `text/plain`; there is no separate JSON or source-code MIME admission rule.

| MIME | Samples | Original bytes | Coverage |
| --- | ---: | ---: | --- |
| `image/jpeg` | 7 | 2,500,693 | small/medium/large text-heavy, photographic-like, mixed, and high-entropy images |
| `image/png` | 7 | 1,795,174 | small/medium/large text-heavy, photographic-like, mixed, and high-entropy images |
| `image/webp` | 7 | 904,502 | small/medium/large text-heavy, photographic-like, mixed, and high-entropy images |
| `image/gif` | 6 | 874,256 | small/medium/large text-heavy, photographic-like, mixed, animated, and high-entropy images |
| `text/plain` | 9 | 19,292 | three plain-text, three JSON/metadata, and three source-code samples |
| **Total** | **36** | **6,093,917** | primary images plus secondary text |

The 27 image examples span 320×180 through 1280×720 and 1024×768.  Each supported image MIME has small (320–480 px wide), medium (640–960 px), and larger (1024–1280 px) examples.  They include simple, illustrated, caption-dense, photographic-like gradient, mixed-complexity, animated, already-compressed-container, moderately compressible, and difficult/high-entropy forms.  The deterministic rasters intentionally use multiple independent seeds and visual structures, rather than byte repetition engineered for a favorable ratio.  They are repository-authored and redistributable without third-party meme-image licensing claims.

The text categories can be independently selected for future per-category scoring while retaining the only currently supported text MIME, `text/plain`:

| Category | Samples | Original bytes | Representative material |
| --- | ---: | ---: | --- |
| `plain_text` | 3 | 3,287 | caption, node release note, human-readable chain audit log |
| `structured_metadata_json` | 3 | 14,871 | pretty metadata, minified admission events, nested peer snapshot |
| `source_code` | 3 | 1,134 | label helper, typed admission model, snapshot-inspection CLI |

JSON and code are benchmark-only subcategories of `text/plain`, not distinct currently supported MIME types.  They use plausible chain records, peer snapshots, application data structures, and source modules rather than repeated filler text.

## Original-size and provisional-capacity analysis

Percentiles use the nearest-rank method over original image bytes only; they do not predict encoded or compressed sizes.

| Metric | Bytes |
| --- | ---: |
| Image p50 | 10,474 |
| Image p95 | 1,530,684 |
| Image p99 | 1,772,761 |
| Image maximum | 1,772,761 |

Five of 27 representative images (18.5%) exceed the provisional 262,144-byte original-media limit, and therefore also exceed the provisional encoded-media limit if no size reduction is assumed.  These are clearly marked as capacity-analysis samples and are excluded from benchmark scoring.  Their containers are valid; the limit outcome is not a corruption claim.

This small, purposefully stratified corpus is not a population survey, so it cannot set a final cap.  It nevertheless shows that the proposed 256 KiB media limit admits common small, flat, illustration, and some WebP examples while excluding all included high-entropy capacity samples and one 1280×720 JPEG gradient.  Subsequent evaluation should compare candidate original-media caps of 256 KiB, 512 KiB, 1 MiB, and 2 MiB against a broader rights-cleared real-world sample.  The 512 KiB complete-block proposal cannot be selected from image bytes alone: exact serialized descriptor, certificate, transaction, hash/signature, and future encoding metadata overhead must first be measured in the Task 7.4-compatible block format.  No result here assumes compression makes an image smaller.

Complexity is visibly related to size in this corpus: flat and palette-oriented images are hundreds to thousands of bytes, caption/illustration/mixed samples range from thousands to hundreds of thousands, while seeded noise is hundreds of thousands to over one MiB.  That relationship is a constructed coverage signal, not a compression result or claim about user uploads.

## Validator compatibility and JPEG investigation

Valid sample containers are independently decoded with Pillow.  All nine plain-text/JSON/code samples are accepted by the current validator.  In this Windows sandbox, all 22 valid in-limit image samples fail current `validate_media_bytes` with `MALFORMED_MEDIA`; the five oversized images instead stop at the expected policy byte-limit rejection before worker decoding.

Reproduction:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_milestone_7_task_7_3_corpus.py -q
.\.venv\Scripts\python.exe -m pytest tests\test_milestone_6_task_6_3_technical_media_validation.py::test_m6_ac03_all_supported_images_require_complete_decode -q
```

The second command fails all four valid image formats in this environment.  Directly invoking the isolated decoder reveals `PermissionError: [WinError 5] Access is denied` at `os.chdir()` into its `TemporaryDirectory` under the sandboxed package Temp path.  The frozen genesis JPEG is 57,343 bytes, has the expected SHA-256, opens as JPEG via Pillow, and reproduces the same error.  Thus the observed JPEG failure is neither invalid fixture bytes nor a MIME mismatch; it is an environment/isolation compatibility defect that is currently flattened to `MALFORMED_MEDIA` by the validator's fail-closed error handling.  This task does not alter the production validator.  The manifest labels this outcome `rejected_environment_isolation` rather than calling the images malformed.

## Reproducibility and verification

The v1.1.0 manifest pins the observed generator environment: Python 3.13.5, Pillow 12.3.0, JPEG codec 8.0, and WebP codec 1.6.0.  A changed encoder/library version is expected to change generated bytes and cause verification to fail until an intentional corpus-version update is reviewed.

```powershell
# Verify deterministic samples, hashes, dimensions, policy categorization, and percentiles.
.\.venv\Scripts\python.exe scripts\milestone_7_task_7_3_corpus.py --verify

# Materialize disposable sample binaries outside Git tracking.
.\.venv\Scripts\python.exe scripts\milestone_7_task_7_3_corpus.py --verify --output artifacts\milestone-7-corpus

# Run the focused automated checks.
.\.venv\Scripts\python.exe -m pytest tests\test_milestone_7_task_7_3_corpus.py -q
```

Focused tests cover manifest completeness/counts/MIME classification, exact byte sizes and SHA-256, reproducible generation, image dimensions/direct decode, supported versus text-subcategory categorization, validator environment outcomes, exclusion of corrupt samples, and nearest-rank percentile calculations.  They intentionally contain no compression calls or result assertions.

## Future bounty compatibility and Task 7.4 handoff

The manifest has stable IDs, semantic corpus version, MIME/category/complexity labels, original byte hashes, dimensions, seeds, generation method, environment, validator outcome, benchmark-scoring flag, and capacity-analysis flag.  That supports a public reference set with byte-weighted storage savings, per-MIME/category analysis, exact original-byte checks, and reproducible versions.  A future competition must maintain a separately versioned independent holdout corpus with restricted access, independently execute compression/decompression performance measurement, and prevent submissions from receiving holdout bytes or derived outputs.  This repository does not claim that a secret holdout exists yet.

Known biases: all image content is synthetic and generated with one pinned stack; it has no licensed real-world photographic meme set, no user-upload frequency weighting, limited animation, and no audio/video because current admission does not support them.  The corpus is stratified coverage, **not** a statistically random sample of internet memes.  Task 7.4 may use this public reference corpus to measure approved candidate encodings, but should add rights-cleared external diversity under a separately reviewed provenance process, preserve this corpus unchanged as v1.1.0, report raw fallback behavior, and measure exact canonical-block overhead before recommending any limit or codec.
