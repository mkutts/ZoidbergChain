# Milestone 7 Task 7.23 — Meme-first launch sizing recommendation

Date: **2026-10-29, America/New_York**. This is a benchmark and protocol-policy study only. **Every proposed value is PROPOSED, UNAPPROVED and INACTIVE. Original Milestone 7 remains INCOMPLETE; launch/network readiness remains BLOCKED.** MODEL A remains mandatory: recover the complete accepted original byte-for-byte using canonical on-chain data and the historical normative decoder.

## 1. Recommendation and authority

**Prefer profile B, balanced meme-first**, ranked B first, A second, C third for the initial experiment. B retains the current active 256 KiB static-image allowance and explores 512 KiB GIFs with 16 KiB text. Its full experimental block allowance is 1 MiB after reserving existing signed evidence and transactions. This is an evidence-informed starting hypothesis, not a measured optimum or production admission forecast. The synthetic corpus cannot establish actual user demand.

| PROPOSED UNAPPROVED profile | Static | Animated GIF | Text | Encoded | Complete block | Equal admitted mean R | Coverage |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A_lean | 128 KiB | 256 KiB | 8 KiB | 257 KiB | 704 KiB | 77,151 B | 60.34% (35/58) |
| B_balanced | 256 KiB | 512 KiB | 16 KiB | 513 KiB | 1,024 KiB | 118,936 B | 70.69% (41/58) |
| C_flexible | 512 KiB | 1,024 KiB | 64 KiB | 1,025 KiB | 1,728 KiB | 201,355 B | 81.03% (47/58) |

All profile values, including expected sizes and costs, are **PROPOSED / UNAPPROVED scenario results**. A/B/C are names, not an activation sequence. The static benchmark rows cover JPEG, PNG and WebP; all GIF samples are animated. Under the proposed product profile, a single-frame GIF would use the static ceiling, but that subtype is not separately measured here and receives no extra coverage claim. The GIF column covers GIF animation. Animated WebP uses the static ceiling conservatively; any deployment must classify frame structure from the fully validated container and specify these rules in its separately approved policy. No video/audio or unknown MIME is admitted.

Branch `Compression-State-Bloat-and-Node-Economics`; initial HEAD `4e8ac8f8fd023a7af4afbb1467c6343dd0ca918c`. Task 7.22 was separately committed with title `Milestone 7 Task 7.22: finalize economics and acceptance audit`. Before writes the worktree/index were clean including untracked files. No ancestor/repository AGENTS.md was found. No delegation was used. [preflight.json](../benchmarks/task723_v1/preflight.json) records the initial state and all 1141 preexisting tracked-file hashes. Only this report and `benchmarks/task723_v1/` are added. No stage, commit, push, reset, deployment, schema/fixture/genesis/reviewer/consensus/codec mutation or activation is performed.

## 2. Source-derived baseline and previous work

Read Tasks [7.18](milestone-7-original-scope-completion-audit.md), [7.19](milestone-7-reproducibility-and-regression-triage.md), [7.20](milestone-7-production-like-compression-and-metadata-acceptance.md), [7.21](milestone-7-disabled-compression-integration.md) and [7.22](milestone-7-final-economics-and-acceptance-review.md), their measurement/ledger/economics tools, frozen canonical producer/parser/evidence budgets and isolated strict decoder. Task 7.20 established synthetic general-media results and the metadata miss; 7.21 demonstrated a disabled application/recovery bridge; 7.22 corrected full capacity pricing and retained acceptance gaps. This study changes neither their data nor their verdicts.

| Source / boundary | Inspected value | Scope |
| --- | --- | --- |
| canonical_v3/primitives.py MAX_RECORD | 3,145,728 B | Inactive frozen v3 |
| canonical_v3/media.py MAX_IMAGE / MAX_ENCODED | 2,097,152 / 2,097,152 B | Inactive frozen v3 |
| canonical_v3/media.py MAX_TEXT | 262,144 B | Inactive frozen v3; canonical accepted text |
| media_admission_policy.py accepted_image_bytes | 262,144 B | Active admission |
| media_admission_policy.py accepted_plain_text_bytes_after_canonicalization | 262,144 B | Active admission; submission text has a separate UI bound |
| media_admission_policy.py canonical_serialized_non_genesis_block_bytes | 524,288 B | Active admission/legacy block policy |
| canonical_v3/block.py check_budgets | 196,608 B certificate + 98,304 B native array + 32,768 B rest | Disjoint component ceilings, plus payload base64 |
| codec_prototype/strict_decoder.py | 2 MiB output; 256 KiB window; 64 blocks; 1 MiB native arena | Codec checks/guard, not full MIME safety |

The requested 3 MiB complete / 2 MiB encoded / 2 MiB image / 256 KiB text baseline is verified for **inactive v3**. It is not the current active image/block policy. The legacy active path still uses versions 1/2. [baseline.json](../benchmarks/task723_v1/baseline.json) snapshots the complete current policy, including MIME allowlist, dimensions, frames and local resource limits. All five supported MIMEs are exercised. Larger format-capacity records are not accepted-current submissions. Per-object active technical admission outcomes/reasons are retained in records.json, independently of every proposed size-only gate.

## 3. Corpus coverage, rights and representativeness

Version **1.0.0**, fixed seed 7232026. **58 equally counted primary originals**, plus one predeclared historical raw-expansion diagnostic outside the primary coverage/metadata/economic population. All new raster/text artifacts are self-created and dedicated to CC0-1.0; no downloads, private submissions, production traffic or assumed traffic weights. Original quips, procedural cartoon shapes and the installed Pillow default font provide captions. Existing fixture keys/signature context retain repository terms; their use is public test context only.

| Dataset MIME | Primary n | Original min / p50 / max B | Coverage |
| --- | --- | --- | --- |
| image/gif | 9 | 3,095 / 260,806 / 2,097,133 | Two sizes × two two-frame styles + five boundaries |
| image/jpeg | 13 | 6,583 / 130,982 / 2,242,286 | Two sizes × four semantic types + five byte boundaries |
| image/png | 15 | 3,242 / 22,540 / 3,594,660 | Two sizes × four semantic types + five byte boundaries; two RGBA stickers |
| image/webp | 14 | 2,442 / 14,292 / 2,096,312 | Two sizes × four semantic types + five byte boundaries |
| text/plain | 7 | 8 / 4,096 / 262,144 | Seven quip lengths, 8–262,144 B |

The fixed semantic factorial has caption, screenshot, two-panel image macro and high-detail noise at 320×240 and 1280×960 for each static MIME. There are two transparent RGBA PNG stickers; animated GIFs cover flat and high-entropy frames at two dimensions plus five near-ceiling files. A small animated WebP checks relevant supported-MIME behavior. Text lengths are 8, 64, 512, 4,096, 16,384, 65,536 and 262,144 bytes; their repeated quips are a compressible text-meme control, not representative long prose. JPEG/WebP/PNG/GIF containers are already compressed before outer codec trials. Texture is synthetic high entropy, not photography.

The five boundary targets per static MIME and GIF are 128/256/512/1024/2048 KiB. Bisection varies dimensions based **only on original container size**, requiring 90–100% of target. No outer compression, runtime, adaptive outcome or desired acceptance fraction influences membership. Random seeds, native settings, dimensions/frame counts, aggregate pixels, MIME, original lengths/hashes, provenance and construction are in [manifest.json](../benchmarks/task723_v1/manifest.json); [corpus.py](../benchmarks/task723_v1/corpus.py) regenerates all bytes. Encoder/library drift must fail manifest comparison.

Two fixed-dimension texture files exceed 2 MiB: JPEG **2,242,286 B**, PNG **3,594,660 B**. They remain in all 58-object admission denominators and native codec trials. The unchanged frozen producer rejects them; complete-record size, metadata and verification timing are explicitly unavailable. No valid mandatory-evidence record is fabricated. Thus complete-record statistics use **56 legal-size primary records**, clearly separated from 58-original size coverage. These exclusions cannot silently improve a codec or metadata claim. The small expansion diagnostic is excluded by design, not for its poor compression result.

This stratified stress/feature corpus deliberately overrepresents size boundaries and high entropy. Counts are coverage statistics, not acceptance probabilities for future users. There is no real photograph, popular-template sample, mobile upload distribution, or production mix. A consented/provenance-cleared pilot remains needed before claiming representative launch demand; this study does not close Task 7.22 R2 by relabeling synthetic data.

## 4. Lossless codec and complete-record measurements

Seven native configurations: identity; Zstd levels 1/3/9 with existing 256 KiB window, checksum, content size, single-thread/no dictionary framing; Brotli levels 1/5/9, generic mode and 256 KiB window. Production experimental selection remains **unchanged Zstd level 3 versus identity**. Alternate levels are benchmark encoder configurations, not new canonical codec versions. Brotli is comparison-only and is rejected by the frozen codec-ID allowlist. No third-party submission is executed.

Five measured repetitions after one warmup; wall time and process CPU measured separately. CPU measurements amortize approximately 20 ms of work per batch (up to 200,000 iterations) to reduce Windows coarse-tick quantization, including Python loop/call overhead; per-row batch counts and observations are retained. Table CPU sums are sums of per-object amortized medians, excluding fixture construction/signing. They are local Windows observations, not admission timeouts, cross-platform qualifications or throughput promises. The 413 trials include the diagnostic; the following 406-trial table excludes it and includes both above-ceiling texture originals. The complete column covers only the 56 legal-size contexts, and Brotli remains a hypothetical byte-length substitution; one actual serialized Zstd-3 context is rejected as detailed below.

| Native profile | Primary M B | E B | Raw saving | Grow n | 56-context complete R B | Sum median encode CPU ms | Sum median decode CPU ms |
| --- | --- | --- | --- | --- | --- | --- | --- |
| identity | 24,930,635 | 24,930,635 | 0.000% | 0 | 27,316,243 legal-size contexts | 0.00 | 0.00 |
| zstd-1 | 24,930,635 | 24,104,310 | 3.314% | 26 | 26,214,024 legal-size contexts | 11.76 | 6.83 |
| zstd-3 | 24,930,635 | 24,110,066 | 3.291% | 26 | 26,221,688 legal-size contexts | 17.61 | 7.79 |
| zstd-9 | 24,930,635 | 24,097,715 | 3.341% | 25 | 26,205,219 legal-size contexts | 17.63 | 7.02 |
| brotli-1 | 24,930,635 | 24,034,318 | 3.595% | 19 | 26,157,796 hypothetical | 28.93 | 43.56 |
| brotli-5 | 24,930,635 | 23,959,107 | 3.897% | 18 | 26,059,351 hypothetical | 108.24 | 39.89 |
| brotli-9 | 24,930,635 | 23,952,918 | 3.922% | 17 | 26,051,147 hypothetical | 494.51 | 45.63 |

Every native trial compares exact original bytes and SHA-256. [codecs.json](../benchmarks/task723_v1/codecs.json) retains encoded hashes, raw sizes, descriptor/media-member sizes, complete-record sizes/statuses, timings and memory. For every legal identity/Zstd trial with E≤2 MiB, enrich.py constructs the actual complete frozen record, parses its signatures and records the strict isolated reconstruction outcome. Over-encoded and over-original trials are explicitly nonconstructible. Native roundtrip success does not establish frozen-profile acceptance: **1 alternate Zstd trial(s) were strict INVALID**, recorded as `[{"id": "gif-boundary-2097152", "candidate": "zstd-3", "stage": "frame", "code": "block_count"}]`. These complete sizes are actual serialized records but rejected encodings, not accepted canonical-storage results. All actual selected producer records remain strictly VALID. Brotli can have a smaller hypothetical R but cannot be treated as valid v3 or credited as activated storage savings.

Selected adaptive records in [records.json](../benchmarks/task723_v1/records.json) use the actual unmodified producer, fourteen cryptographically signed votes, creator attestation, all required technical evidence, rewards and empty native transfers. Public fixture context is not authority to create chain history. Full JSON field ledgers and disjoint media/certificate/transaction/header/envelope/wrapper partitions each sum to the exact complete record. Identity replacements use the same evidence and context. Canonical-only reconstruction reads embedded payloads, without external media/cache. Text is already canonical, so source and accepted hashes/lengths coincide.

Actual adaptive results below cover **only the 56 legal-size primary objects**, with **31 Zstd / 25 identity** selections. The near-2-MiB GIF's default Zstd stream exceeds the frozen 64-block limit; the existing producer's INVALID-to-identity fallback preserves strict validity and exact originals without changing its behavior. Its rejected compressed size earns no adaptive storage credit. PNG/JPEG/WebP gains are workload-specific and small in aggregate; no large outer-compression promise is made for already-compressed images.

| MIME / valid n | Original M B | Selected E B | Complete R B | Same-context identity R B | Net canonical saving | Zstd / identity |
| --- | --- | --- | --- | --- | --- | --- |
| image/gif / 9 | 4,909,587 | 4,719,335 | 6,590,993 | 6,844,694 | 3.707% | 8 / 1 |
| image/jpeg / 12 | 4,382,534 | 4,260,400 | 6,078,632 | 6,241,505 | 2.610% | 6 / 6 |
| image/png / 14 | 4,331,346 | 4,306,355 | 6,206,206 | 6,239,567 | 0.535% | 8 / 6 |
| image/webp / 14 | 5,121,478 | 5,115,184 | 7,284,713 | 7,293,117 | 0.115% | 3 / 11 |
| text/plain / 7 | 348,744 | 15,771 | 253,363 | 697,360 | 63.668% | 6 / 1 |

M = original bytes; E = encoded bytes including codec frame; B = 4·ceil(E/3) base64 content; D = full canonical descriptor; media member = D+8 for `"media":`; R = complete canonical record including envelope/hash wrapper. E is not the stored canonical BLOB size. Metadata N=R−B includes descriptor fields, quotes, every signed evidence item, certificate, header, transactions and framing. Base64 expansion B−E is separately charged. Signature subsets are not added again.

The diagnostic reproduces the natural **104→105 raw expansion** while D shrinks 363→359 B and complete R shrinks 33331→33327 B. Base64 length is unchanged and `zstd` is four label bytes shorter than `identity`. Actual adaptive selection optimizes complete serialized descriptor/R versus identity, not E≤M. All selected legal-size records satisfy R≤same-context identity R; physical SQLite allocation monotonicity is not proved.

Memory: native trials record separate untimed **Python traced allocation peaks only**, excluding native arenas/RSS. They are not codec-specific native total-memory peaks. Strict selected/alternate decoder requests record Windows Job peak commit and process resource counters; those include worker/interpreter/IPC overhead. Primary maximum selected-worker job commit is **25.37 MiB**. Complete parse/crypto/recovery wall time p50/p95/worst is **406.57 / 938.30 / 944.89 ms**, including process startup and existing verification helpers, not CPU-only decode. No unsupported native peak-memory claim is made.

## 5. Candidate ceilings, exclusions and security headroom

Common-ceiling comparison leaves text at its existing experimental 256 KiB and applies each image ceiling equally to GIF/static images. Admission here is a proposed original-size predicate only; current technical rejection reasons and all other admission checks still apply.

| Common original image/GIF cap | Admitted / 58 | Percent | M p50 / p95 / p99 / max B | R p50 / p95 / p99 / max B | E ceiling / block cap |
| --- | --- | --- | --- | --- | --- |
| 128 KiB | 37 | 63.79% | 9,698 / 131,057 / 262,144 / 262,144 | 40,587 / 207,820 / 207,920 / 207,920 | 257 KiB / 704 KiB |
| 256 KiB | 42 | 72.41% | 12,330 / 261,334 / 262,144 / 262,144 | 41,126 / 380,650 / 382,218 / 382,218 | 257 KiB / 704 KiB |
| 512 KiB | 46 | 79.31% | 16,384 / 523,046 / 524,242 / 524,242 | 43,208 / 729,579 / 731,842 / 731,842 | 513 KiB / 1,024 KiB |
| 1,024 KiB | 52 | 89.66% | 40,740 / 1,045,602 / 1,047,920 / 1,047,920 | 49,614 / 1,427,297 / 1,430,008 / 1,430,008 | 1,025 KiB / 1,728 KiB |
| 2,048 KiB | 56 | 96.55% | 52,173 / 2,096,312 / 2,097,133 / 2,097,133 | 54,772 / 2,828,268 / 2,829,360 / 2,829,360 | 2,048 KiB / 3,072 KiB |

| Original image/GIF ceiling | Excluded JPEG | PNG | WebP | GIF | Text |
| --- | --- | --- | --- | --- | --- |
| 128 KiB | 5 | 6 | 5 | 5 | 0 |
| 256 KiB | 4 | 4 | 4 | 4 | 0 |
| 512 KiB | 3 | 3 | 3 | 3 | 0 |
| 1,024 KiB | 2 | 2 | 1 | 1 | 0 |
| 2,048 KiB | 1 | 1 | 0 | 0 | 0 |

Exact excluded IDs, original bytes, MIME and reasons-by-size are in candidates.json. That file also contains the complete **100-case separate-cap grid**: five static ceilings × five GIF ceilings × four text ceilings (8/16/64/256 KiB). Each case retains admission fraction, excluded MIME/size detail, M/R p50/p95/p99/worst, certificate/metadata distributions, selected-worker peaks/timing and encoded/complete safety budgets. Text/GIF differentiation is explored rather than assumed: a common 256 KiB image cap is a viable feature tradeoff; B's larger GIF allowance offers two-frame detail at increased worst-case storage. Corpus counts do not establish its real demand benefit.

The proposed encoded ceiling is min(2 MiB, max(original caps)+1 KiB). Identity always fits. The extra 1 KiB conservatively covers label/base64-rounding selection effects such as 104→105, and an explicit independent encoded gate still applies to received alternate representations. For the unchanged selector, if E>M, stored-size digit width cannot decrease; the four-byte codec-label saving cannot pay for an extra four-byte base64 group under strict shrink. Therefore selected raw expansion is at most two bytes; 1 KiB is a deliberately rounded reservation rather than a measured expansion requirement. This is not a general promise that any compressor's output fits: an oversized compressed encoding must be rejected or a future approved producer must retain identity. Existing codec behavior is untouched. Payload/dimension/frame/decoded-pixel restrictions remain independent.

For a v3 record satisfying the **unchanged existing component-budget checks**, the conservative complete bound is:

`R ≤ 4·ceil(encoded_cap/3) + 196,608 certificate + 98,304 native array + 32,768 rest`.

The complete cap rounds this sum up to 64 KiB. The three additive budgets are disjoint as implemented by check_budgets; rest already includes all remaining descriptor/envelope/caption/hash/framing bytes. No external proof or journal is presumed to fit for free. This is an analytic sufficient serialization bound, not a claim that every simultaneously maximal field combination is constructible or that a smaller empirical maximum is safe.

| PROPOSED profile | Base64 maximum B | Full reserved evidence / tx / rest B | Analytic complete bound B | Rounded cap B | Rounding surplus B |
| --- | --- | --- | --- | --- | --- |
| A_lean | 350,892 | 196,608 / 98,304 / 32,768 | 678,572 | 720,896 | 42,324 |
| B_balanced | 700,416 | 196,608 / 98,304 / 32,768 | 1,028,096 | 1,048,576 | 20,480 |
| C_flexible | 1,399,468 | 196,608 / 98,304 / 32,768 | 1,727,148 | 1,769,472 | 42,324 |

No profile lowers certificate, transaction or rest budgets. Compared with measured ~31,533 B p50 certificates and ~33,173 B p50 total metadata, the full 192 KiB certificate reservation accommodates variable signed evidence; full 96 KiB native budget preserves transaction room, plus 32 KiB rest and rounding surplus. Sensitivity records use ten votes and independently long nonces/captions plus ten signed transfers; all are parsed/reconstructed and retained separately. They do not replace the primary fourteen-vote distribution. A proposed cap below valid mandatory evidence would be rejected by this framework.

These bounds establish byte capacity **conditional on frozen v3 and its retained gates**, not security certification. Keep codec checks: single complete frame, content-size/hash checks, no dictionary/skippable/concatenated/trailing data, bounded input/output/window/block count/work/native arena, deterministic sequence verification. Existing default worker guards are 128 MiB, 5 CPU seconds, 10 wall seconds and 5 startup seconds, with global concurrency two. Operational failure stays indeterminate/fail closed and must never become valid data or deterministic consensus-invalid solely because of a local timeout.

Keep active image defenses: ≤4096×4096, ≤60 frames, ≤16,777,216 aggregate decoded pixels, every frame validated; active technical worker 256 MiB/2 seconds. A smaller compressed/original cap does not bound decoded image pixels, image-parser bugs, signature work or pathological sequence complexity. Existing certificate size/vote/transfer/type/crypto checks remain necessary. Cold Linux/cross-platform qualification, malformed-case testing and independent security review remain required before any activation; this local study does not certify them.

## 6. Original metadata acceptance target

Use the original denominator **100·(R−B)/R**, equal-record nearest-rank p50/p95/worst. No padding, evidence removal or byte weighting is substituted.

| Population | p50 % | p95 % | Worst % | Below 15% | Original target verdict |
| --- | --- | --- | --- | --- | --- |
| All 56 format-valid primary records | 57.32356 | 99.46054 | 99.96385 | 19/56 | FAIL |
| A_lean | 80.93751 | 99.78350 | 99.96385 | 1/35 | FAIL |
| B_balanced | 77.28692 | 99.46054 | 99.96385 | 6/41 | FAIL |
| C_flexible | 67.15046 | 99.46054 | 99.96385 | 11/47 | FAIL |

Primary metadata bytes p50/p95/worst are **33,173 / 33,191 / 33,195 B**; certificate value bytes are **31,533 / 31,556 / 31,557 B**. Both above-ceiling controls have no valid R and no reported metadata ratio. Every tiny valid primary object remains included. All three requested primary statistics exceed the original **below-15%** target: **FAIL**, not PASS. Profile-specific misses are also shown directly.

For fixed N, N/R<0.15 requires B>(17/3)N, approximately E>(17/4)N. At N≈33 KiB, E must exceed roughly 140 KiB; tiny valid media cannot satisfy that threshold with mandatory evidence, and strong compression can increase metadata percentage while reducing actual R. The stricter (R−E)/R measure cannot improve the verdict. Smaller meme caps may worsen the target by admitting predominantly small records. The owner must separately accept a revised criterion/exception or authorize an evidence-preserving format redesign; this study supplies no waiver.

## 7. Three-year economics and month-36 hosting

All numbers below are **PROPOSED / UNAPPROVED analytical scenarios**, not quoted offers or production forecasts. Use Task 7.22's exact unchanged simulator/accounting assumptions and historical illustrative prices. Each profile's average is the equal-record mean of its admitted legal-size samples; its admission percentage is over all 58 originals. These means show corpus truncation effects, not changes expected in a real launch mix. No second mandatory raw-original disk copy is charged because MODEL A reconstruction is from canonical R.

36 months = 1,095 days; 109,500 / 1,095,000 / 10,950,000 accepted blocks. Month 36 has 31 days; GiB=2^30 B. C = blocks·mean R. P = 1 GiB + C + .10C index/page allowance + .15C fragmentation. These are analytical allowances, not newly measured physical indexes. H = .20P + 1.45·monthly_R·1.25 + 5 GiB. S=P (daily refresh, one retained full local snapshot); W=P (additional recovery workspace); K=4·.95P remote retained backups, four full uploads/month. L=P+H+S+W; all L is priced, including snapshots/headroom/workspace. No deduplication credit, WAL initialization or production DB access.

| Profile | Blocks/day | Canonical media GiB | Other canonical GiB | Total C GiB | Index/page allowance GiB | Fragmentation GiB | Primary P GiB |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A_lean | 100 | 4.51 | 3.36 | 7.87 | 0.79 | 1.18 | 10.83 |
| A_lean | 1000 | 45.08 | 33.59 | 78.68 | 7.87 | 11.80 | 99.35 |
| A_lean | 10000 | 450.85 | 335.93 | 786.78 | 78.68 | 118.02 | 984.48 |
| B_balanced | 100 | 8.77 | 3.36 | 12.13 | 1.21 | 1.82 | 16.16 |
| B_balanced | 1000 | 87.70 | 33.59 | 121.29 | 12.13 | 18.19 | 152.61 |
| B_balanced | 10000 | 876.97 | 335.94 | 1,212.90 | 121.29 | 181.94 | 1,517.13 |
| C_flexible | 100 | 17.17 | 3.36 | 20.53 | 2.05 | 3.08 | 26.67 |
| C_flexible | 1000 | 171.75 | 33.59 | 205.34 | 20.53 | 30.80 | 257.68 |
| C_flexible | 10000 | 1,717.48 | 335.94 | 2,053.42 | 205.34 | 308.01 | 2,567.77 |

| Profile | Blocks/day | Operational H GiB | Snapshot S GiB | Remote backups K GiB | Recovery W GiB | Total local L GiB |
| --- | --- | --- | --- | --- | --- | --- |
| A_lean | 100 | 7.57 | 10.83 | 41.17 | 10.83 | 40.07 |
| A_lean | 1000 | 28.91 | 99.35 | 377.52 | 99.35 | 326.95 |
| A_lean | 10000 | 242.27 | 984.48 | 3,741.01 | 984.48 | 3,195.70 |
| B_balanced | 100 | 8.85 | 16.16 | 61.41 | 16.16 | 57.34 |
| B_balanced | 1000 | 41.75 | 152.61 | 579.93 | 152.61 | 499.58 |
| B_balanced | 10000 | 370.66 | 1,517.13 | 5,765.09 | 1,517.13 | 4,922.05 |
| C_flexible | 100 | 11.39 | 26.67 | 101.34 | 26.67 | 91.39 |
| C_flexible | 1000 | 67.07 | 257.68 | 979.17 | 257.68 | 840.10 |
| C_flexible | 10000 | 623.92 | 2,567.77 | 9,757.53 | 2,567.77 | 8,327.23 |

Network: peer ingress=1.38·monthly_R; peer egress=11.52·monthly_R for eight peers; backup upload=4P/month; one fresh bootstrap=1.2C. Expected bootstrap serving and backup restore are each one event/year, charged as monthly fractions. These are workload assumptions, not measured network bytes. Fresh-node verification must still reconstruct/check every historical record; sync bytes alone do not quantify bootstrap CPU or elapsed recovery time.

| Profile | Blocks/day | Fresh sync once GiB | Month-36 peer ingress GiB | Peer egress GiB | Backup upload GiB | All charged egress GiB |
| --- | --- | --- | --- | --- | --- | --- |
| A_lean | 100 | 9.44 | 0.31 | 2.57 | 43.34 | 47.55 |
| A_lean | 1000 | 94.41 | 3.07 | 25.66 | 397.39 | 438.78 |
| A_lean | 10000 | 944.14 | 30.74 | 256.60 | 3,937.91 | 4,351.12 |
| B_balanced | 100 | 14.55 | 0.47 | 3.96 | 64.65 | 71.09 |
| B_balanced | 1000 | 145.55 | 4.74 | 39.56 | 610.45 | 674.22 |
| B_balanced | 10000 | 1,455.48 | 47.39 | 395.57 | 6,068.51 | 6,705.48 |
| C_flexible | 100 | 24.64 | 0.80 | 6.70 | 106.67 | 117.53 |
| C_flexible | 1000 | 246.41 | 8.02 | 66.97 | 1,030.71 | 1,138.61 |
| C_flexible | 10000 | 2,464.10 | 80.22 | 669.69 | 10,271.08 | 11,349.40 |

Inherited profiles, USD/month: budget compute $20, included 160 GiB, extra disk $.05/GiB-month, backup $.006/GiB-month, egress $.01/GiB; storage-focused $45/500 GiB/$.02/$.006/$.01; mainstream cloud $40/160 GiB/$.10/$.05/$.09. Charge ceil(max(0,L/GiB−included)) extra disk, K·backup rate and all expected peer/backup/bootstrap/restore egress. Ingress assumed free. All are illustrative storage pools with 4 vCPU/8 GiB RAM reference assumptions, no tier/volume/IOPS feasibility or CPU sufficiency promise. Taxes, labor, redundancy replicas, region/currency effects and negotiated discounts are outside these prices.

| Profile | Blocks/day | Budget VPS $/mo | Storage-focused $/mo | Mainstream cloud $/mo | 3-year total USD budget / storage / cloud |
| --- | --- | --- | --- | --- | --- |
| A_lean | 100 | 20.72 | 45.72 | 46.34 | 734.89 / 1,634.89 / 1,570.74 |
| A_lean | 1000 | 35.00 | 51.65 | 115.07 | 932.39 / 1,748.34 / 2,735.04 |
| A_lean | 10000 | 237.76 | 164.88 | 922.25 | 4,689.89 / 3,739.68 / 17,942.96 |
| B_balanced | 100 | 21.08 | 46.08 | 49.47 | 741.72 / 1,641.72 / 1,630.69 |
| B_balanced | 1000 | 47.22 | 55.22 | 163.68 | 1,139.07 / 1,816.62 / 3,611.32 |
| B_balanced | 10000 | 359.80 | 235.11 | 1,408.05 | 6,984.61 / 5,058.30 / 27,161.82 |
| C_flexible | 100 | 21.78 | 46.78 | 55.64 | 755.19 / 1,655.19 / 1,748.94 |
| C_flexible | 1000 | 71.31 | 69.08 | 259.53 | 1,574.73 / 2,005.32 / 5,395.80 |
| C_flexible | 10000 | 600.44 | 373.60 | 2,366.12 | 11,512.85 / 7,670.72 / 45,349.75 |

All profiles must disclose misses of the $100/month target at each traffic rate; the table makes no universal affordability claim. Three-year totals sum all 36 monthly bills, not 36×month-36. [economics.json](../benchmarks/task723_v1/economics.json) retains all monthly partitions and totals for 36 main cases (three profiles plus a common-average control × three rates × three hosts), plus 54 average-size sensitivity cases. This is model output based on measured logical R, not a new physical DB or hosting benchmark.

Price review **2026-10-29**: checked official [Hetzner Cloud](https://www.hetzner.com/cloud/), [AWS Lightsail pricing](https://aws.amazon.com/lightsail/pricing/) and [Backblaze B2 pricing](https://www.backblaze.com/cloud-storage/pricing). Hetzner's fetched page did not expose a complete priced regional bundle; B2 advertises a starting $6.95/TB-month, distinct from the inherited $.006/GiB-month backup assumption and not a host price. AWS lists region/bundle/storage/transfer-dependent rates. No complete same-region host+disk+backup+egress quote was established. Historical assumptions remain fixed for comparability; the review does **not** verify those rates as current purchasable offers. Obtain regional capacity/transfer/IOPS quotes before purchase or treating $100 as guaranteed.

### Worst-case ceiling versus expected average

At the cap every day, retained canonical bytes alone could reach:

| Profile | 100/day canonical GiB | 1000/day canonical GiB | 10000/day canonical GiB |
| --- | --- | --- | --- |
| A_lean | 73.52 | 735.17 | 7,351.68 |
| B_balanced | 106.93 | 1,069.34 | 10,693.36 |
| C_flexible | 180.45 | 1,804.50 | 18,045.04 |

These are ceiling envelopes, excluding extra physical/backup capacity. Lowering the cap reduces maximum permitted growth. It reduces expected disk/cost **only if accepted mean R actually falls**. Retrying/resizing images can shift the mix differently; rejected uploads do not count as accepted blocks. The common `fixed_small_average_all_caps` workload fits A/B/C unchanged and has exactly the same costs under each cap. This control is saved once and applies identically to every profile, avoiding invented savings from the cap itself.

Holding each profile's limits fixed, admitted subsets show the impact of changing the average (illustrative selection sensitivities at 1,000/day):

| Profile | Accepted workload sensitivity | Mean R B | Budget $/mo at 1000/day | Storage $/mo | Cloud $/mo |
| --- | --- | --- | --- | --- | --- |
| A_lean | small | 38,805 | 23.83 | 48.38 | 70.53 |
| A_lean | largest_quartile | 193,941 | 69.13 | 67.83 | 250.88 |
| B_balanced | small | 38,610 | 23.76 | 48.36 | 70.29 |
| B_balanced | largest_quartile | 331,881 | 109.41 | 91.01 | 411.24 |
| C_flexible | small | 38,610 | 23.76 | 48.36 | 70.29 |
| C_flexible | largest_quartile | 640,896 | 199.65 | 142.94 | 770.48 |

These small and largest-quartile subsets are labelled alternatives, not reweighting of the primary corpus. Repeated quips may compress strongly while mandatory evidence still dominates. Worst-case original size, average accepted original size and average R must be monitored independently.

**Future review journal is separate, unapproved and unpriced here.** Do not interpret its exclusion as zero cost or declare combined-node affordability. It needs independently approved event rates, canonical evidence sizes, retention, authority/closure/finality proofs, replicas/indexes, bandwidth, backup and recovery accounting. External finality proofs are likewise outside measured R unless later explicitly embedded and charged; they cannot silently consume reserved headroom.

## 8. Launch profile tradeoffs and ranked preference

**Rank 1: B balanced (preferred, PROPOSED/UNAPPROVED).** Static 256 KiB preserves today's image allowance, while a separate 512 KiB GIF hypothesis offers more frame detail. Text 16 KiB supports compact memes but rejects the long text controls. Mean admitted R is 118,936 B; size-only corpus coverage is 70.69%. Month-36 costs are in the profile/rate table above for all three hosts. Its 1 MiB complete cap safely retains full existing v3 component reservations. Users may need local resizes before submission; any resaved upload becomes a distinct original with its own hash, never a node-side lossy replacement.

**Rank 2: A lean (PROPOSED/UNAPPROVED).** Static 128 KiB, GIF 256 KiB, text 8 KiB; 60.34% coverage, 77,151 B measured admitted mean R, 704 KiB complete cap. Lowest ceiling and simplest compact workload, at the cost of more screenshot/detail/GIF rejection and more client preparation. Signed evidence still dominates tiny memes; strict safety review remains necessary. Its lower byte allowance does not certify lower CPU or give a production cost guarantee.

**Rank 3: C flexible (PROPOSED/UNAPPROVED).** Static 512 KiB, GIF 1 MiB, text 64 KiB; 81.03% coverage, 201,355 B measured admitted mean R, 1,728 KiB complete cap. More headroom for detailed screenshots and animation, with larger worst-case disk/sync exposure and greater operational provisioning. It still excludes near-2-MiB objects and both above-ceiling controls. High compression is not assumed for already-compressed images.

All three profiles keep MODEL A, every signed mandatory evidence field and independent pixel/frame/codec resource defenses. Distinct GIF/text caps are a product tradeoff to validate with actual accepted-workload data, not a demonstrated necessity. No MIME/policy/consensus activation occurs here.

## 9. Future community codec framework — PROPOSED, INACTIVE

This framework evaluates **lossless byte compression**, not visual similarity or lossy re-encoding. No submission is approved, rewarded, distributed or executed in this task. No uploaded-code execution or dynamic plugin mechanism is implemented.

1. **Normative deterministic decoding.** Publish a complete bitstream specification, canonical identifier and immutable version, supported inputs/dictionary rules, exact consumed-length behavior and deterministic reject reasons. Reject trailing/concatenated/ambiguous streams. Decoding must produce identical complete accepted original bytes and exact SHA-256 on every supported implementation/platform. Encoder determinism is desirable for benchmark reproducibility; consensus decoding cannot depend on unspecified native behavior.
2. **MODEL A closure.** All per-object side information/dictionaries must be canonical on-chain bytes or permanently specified normative historical decoder material. No URL, uploader service, private model, cache or mutable external dictionary may be required for fresh reconstruction. Include dictionary/setup bytes in net canonical accounting, including first-use and realistic amortization, not just ideal reuse.
3. **Canonical versions.** Never reinterpret existing identity/1 or zstd/1. Propose a new named/versioned codec through a separately reviewed protocol amendment and frozen test vectors. Unknown IDs remain fail closed. Preserve every existing historical decoder permanently, with maintained safe implementations; activating a new codec never makes old history undecodable.
4. **Deterministic complexity bounds plus local guards.** Specify independent encoded/output/window/block/depth/work bounds and finite memory arenas, zero unbounded allocation before size validation, bounded expansion, streaming output limits and checksums/hash verification. Test forged sizes, extreme ratios, tiny-run floods, overlapping copies, malformed tables, integer overflow, truncation, adversarial dictionaries, CPU stalls and mixed-frame bypasses. Separate consensus-validity predicates from local CPU/wall/memory failures; resource exhaustion must not manufacture validity.
5. **Cross-platform reproducibility.** Freeze a multi-architecture corpus/vector manifest, exact byte/hash outcomes on Windows/Linux and supported CPU architectures, reference and independent implementations, compiler/native-library versions and reproducible decoder builds. Test fresh-node historical replay, recovery and peer synchronization. Performance must fit an explicitly chosen minimum full-node class, including concurrency and certificate verification, not just a developer workstation.
6. **Public and withheld evaluation.** Publish independently governed semantic/entropy/size/MIME corpora plus invalid/adversarial suites and selection/weight rules before scoring. Keep an independently administered sealed holdout with commitments, controlled release and periodic refresh. Fix repeated-tuning access, benchmark leakage, duplicates and contamination; do not let submitters choose the scoring files or weights. Report all failures and per-stratum tails as well as aggregates.
7. **Net canonical benefit gate.** Measure M/E/B/D/R and physical storage separately against the same original, certificate and transaction context, identity and incumbent adaptive selector. Charge full headers, framing, dictionaries, codec/version/setup material and recovery dependencies. Require an owner-approved material improvement threshold and non-regression/security limits before eligibility; no threshold is enacted here. Better raw ratios on text alone or cherry-picked files do not justify a reward or a smaller block cap.
8. **Reward anti-gaming.** Predeclare eligible implementations, attribution/IP/license terms, fixed evaluation budget, independent judges, holdout access and appeal rules. Deduplicate equivalent submissions, prevent self-selected/duplicated traffic, Sybil votes, hard-coded benchmark lookup, hidden dictionaries, payload-specific bypasses and hardware-specific tricks. Audit exact-output failures and total verification costs. Reserve any proposed reward until independent review and approved release criteria are met; funding, recipients and payments require separate explicit authorization. No reward is promised by this study.
9. **Independent security and supply-chain review.** Review parser/decoder arithmetic, memory safety, complexity proofs, build/dependency provenance, licensing, fuzz/differential results and isolation. A native library speedup or public leaderboard win is insufficient. Resolve critical findings before proposing distribution; choose a reviewed implementation, never an arbitrary uploaded binary.
10. **Versioned approval/activation.** Owner-approved protocol specification, independent review, frozen conformance suite, supported decoder availability, staged testnet rehearsal, validator adoption/quorum policy and explicit activation height/version are prerequisites. Define failure/rollback handling without invalidating finalized history, historical reconstruction and support commitments. Codec adoption and cap reductions are separate approval items; neither happens automatically.

## 10. Cap reduction decision policy — independent of codec activation

A new codec alone does not shrink consensus worst-case requirements. High-entropy and already-compressed files may still need identity; mandatory certificates and transactions do not disappear; a stronger encoder may increase decoder work or require unavailable implementations. The existing selector's representation savings are not a universal compression ratio or physical-storage proof.

For any proposed lower cap, require an owner-reviewed record of: actual accepted original/encoded/complete distributions by MIME/dimensions/animation and workload period; tail and worst-case encoded bounds including identity and canonical framing; mandatory evidence/transaction bounds; independent CPU/memory/decoded-pixel/work verification; supported deterministic decoders on all validator platforms; permanent historical compatibility and fresh-node replay; demonstrated sync/recovery/storage capacity; and explicit validator adoption with versioned governance. Publish both fraction affected and user migration/resize costs. Size gates must not retroactively invalidate historical blocks. Keep old historical bounds under their original versions and define the new height/version rules explicitly.

Approve codec activation, original/encoded admission ceilings and complete-block cap reductions as **independent owner decisions**, each with a concrete specification and evidence. Remeasure full bounds when adding certificate fields, changing transaction counts or embedding finality/journal evidence. Never assume a higher mean compression ratio makes a cap lower than a valid mandatory-evidence record viable.

## 11. Reproduction, tests and commit readiness

Use the pinned existing Windows environment. No install/network/production DB is required. [README.md](../benchmarks/task723_v1/README.md) gives exact commands. run.py constructs originals, benchmarks native codecs and selected complete records; enrich.py constructs alternate legal identity/Zstd complete records; crosscheck.py independently checks identities/ledgers/percentiles/security budgets and Decimal economic bills without importing the simulator; test_study.py checks analytical boundary cases and retained failures. replay.py runs a fresh full measurement and compares every deterministic field/encoded/record hash, excluding only clocks/resource observations. finalize.py checks preservation and writes checksums. Tracemalloc/native peak limitations remain explicit.

Focused test execution status: **PASS**, counts `{"passed": 289, "failed": 0, "skipped": 0, "errors": 0}`. Exact commands, exit codes, counts and one excluded live-API initialization test ID/reason are in test_results.json and tests.txt. The initial default-temp/API attempt was stopped after fixture errors and live-API initialization stalled; it earns no complete-run credit. The final runner confines temporary data to the workspace and excludes that out-of-scope API test. Independent arithmetic is **PASS** in crosscheck.json (108 candidates, 1,350 Decimal monthly checks); full fresh reproduction is **PASS** in replay_comparison.json, covering seven deterministic evidence files. Platform-specific strict-worker evidence is Windows only, not a substitute for Linux qualification. [preservation.json](../benchmarks/task723_v1/preservation.json) verifies unchanged HEAD/branch/index and zero changed preexisting tracked hashes. checksums.sha256 covers this report and all package files except itself. Development failure/repair is disclosed separately, not credited as a successful replay.

**Task 7.23 is complete as an isolated sizing/policy study, ready for owner review and an owner-performed commit; no staging, commit or push is performed.** Proposed protocol values remain unapproved. These artifacts do not authorize a network transition or close Milestone 7.

## 12. Remaining original Milestone 7 acceptance issues

Retain Task 7.22 R1–R5: (R1) mandatory metadata target remains FAIL and needs explicit owner resolution or evidence-preserving redesign; (R2) representative real-media/independent-text/code evidence is still missing, and this synthetic meme coverage does not substitute for actual traffic; (R3) original scope's acceptance of disabled versus active integration requires an explicit owner decision, with any active transition separately authorized; (R4) separate physical indexes/snapshots/backup/recovery and real transfer measurements remain incomplete despite full analytical pricing; (R5) resolve the no-expansion denominator explicitly—canonical descriptor/R versus identity passes in isolation, E≤M fails the retained counterexample, and R≤raw M is impossible for tiny valid records.

Network readiness separately still needs reviewed version activation, authority/history/finality completion as applicable, independent codec/native security and cross-platform resource qualification, decoder distribution and validator adoption, approved content/reviewer policy, capacity-qualified hosting and reconstruction/recovery drills. Future journal costs are not closed here. **Do not mark Milestone 7 complete or infer launch readiness from this study.**
