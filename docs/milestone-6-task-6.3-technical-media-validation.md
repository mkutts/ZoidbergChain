# Milestone 6 Task 6.3 — hardened pre-review technical media validation

Task 6.3 enforces the technical subset of Public Testnet v1 media-admission
policy version 1. It does not activate the policy, create signed attestations or
admission certificates, add safety voting/quarantine/report/dispute behavior, or
change finalized-block consensus validation.

## Validation order and trust boundaries

Candidate media passes these gates in order:

1. The HTTP middleware rejects a known oversized `Content-Length` and wraps the
   ASGI receive stream so chunked or missing/false lengths cannot exceed the
   versioned local request bound. Multipart overhead and accepted media bytes
   are separate limits.
2. Upload readers stop at accepted-limit plus one byte. Peer canonical wrappers
   are length-checked before hex/base64 decoding, and peer content downloads are
   streamed with an independent actual-byte counter.
3. The exact candidate bytes are hashed with SHA-256. Images retain those exact
   bytes. Plain text becomes the frozen policy-canonical UTF-8 byte sequence
   (CRLF/CR to LF, then outer-whitespace trim) before its immutable hash.
4. The filename is NFKC-normalized and reduced to bounded ASCII display metadata.
   Traversal, absolute-path syntax, separators, NUL/control characters, Windows
   device names, and overlong values cannot form storage paths. Storage remains
   hash-addressed; filenames have no protocol identity authority.
5. Fixed byte signatures identify JPEG, PNG, GIF, and WebP. Strict UTF-8 text is
   recognized only after executable/archive/script signatures and control-byte
   checks. Client MIME and extensions are never type authority. Declared MIME
   mismatch rejects; extension mismatch is recorded but does not reject.
6. Format-specific parsers require a complete container: PNG chunks and CRC/IEND,
   terminal JPEG EOI plus dimensions, terminal GIF trailer, and exact RIFF/WebP
   chunk length/padding. Trailing/polyglot payloads, malformed containers, obvious
   executable/archive/script families, and embedded active-content markers fail
   closed.
7. Header dimensions are checked before decoding. This rejects small compressed
   dimension bombs without allocating their decoded representation.
8. The pinned Pillow decoder runs in a child process. All frames are loaded and
   converted to RGBA, warnings are errors, decoder type must match the signature,
   and Pillow's ambient decompression-bomb threshold is disabled only inside the
   worker because the versioned width/height/frame/aggregate-pixel rules are the
   authority. Every frame, dimensions 1–4,096, at most 60 frames, and at most
   16,777,216 aggregate pixels are enforced explicitly.
9. A stable technical evidence record is produced. Only `ACCEPT` evidence may be
   persisted with candidate content or used to enter originality processing.
10. OCR, perceptual hashes, minted-corpus originality search, review creation,
    certificate work, mint queueing, and Model A chain storage occur only after
    the technical gate. Default Tesseract OCR receives the frozen five-second
    local timeout.

Rejected request buffers are released with the request and no content object,
submission, originality evidence, review state, content file, or block is
created. Task 6.6 quarantine/retention semantics are not implemented.

## Technical evidence v1

Accepted content metadata contains `technical_validation` with:

- evidence version and validator identity;
- policy ID, integer version, and canonical policy digest;
- detected media type/MIME plus declared-MIME and extension match facts;
- staged length, accepted raw-media length, SHA-256, and raw-byte semantics;
- safe display filename;
- width, height, frame count, and aggregate decoded pixels where applicable;
- outcome, stable sorted reason codes, local-resource-failure flag, and canonical
  evidence digest.

Transport/local observations (declared MIME, extension match, safe display
filename, staged length, and local resource-failure flag) remain in the record
but are excluded from its protocol-identity digest. Peers therefore reproduce
the same digest for identical accepted bytes even when transport metadata differs.

Evidence revalidation fails closed for unknown evidence/policy/validator versions,
non-accept outcomes, digest mutation, byte-length changes, or raw-media hash
mismatch. Historical content objects remain readable without this metadata, but
they cannot be newly admitted to review until their available bytes pass Task 6.3
and receive evidence. No database schema migration is required because the
existing durable content-object metadata map carries the versioned record in JSON
and SQLite.

## Deterministic rules versus local defense

Signature/type identification, canonical text, exact byte length/hash, complete
container structure, dimensions, frame/pixel accounting, active/container rules,
declared MIME mismatch, and evidence serialization are deterministic technical
policy results. The pinned decoder is used to generate pre-admission evidence;
Task 6.3 does not re-run it as block-consensus truth.

The 5 MiB staging bounds, request-body bounds, two-second decoder timeout,
five-second OCR timeout, and 256 MiB worker target are local defenses. A timeout
refuses local admission with `RESOURCE_LIMIT_TERMINATED`; it never invalidates an
already-certified peer block. Local overrides may only tighten the Task 6.2
defaults.

## Isolation implemented and still operational

Decoder work executes outside the API process in a fresh child with a temporary
empty working directory. Uploaded values are never used as commands or paths,
and no uploaded code or arbitrary decoder plugin is executed. On POSIX the worker
also applies `RLIMIT_AS` to the versioned memory ceiling. Pillow and ImageHash are
pinned by the existing dependency group.

Windows does not provide a portable Python `RLIMIT_AS`; therefore the code does
not claim an enforced 256 MiB Windows job-object sandbox. The child also inherits
the process environment, and network denial is architectural (the worker has no
network code), not an OS firewall. Deployment-owned job/container memory, CPU,
network, secret-scrubbing, worker-pool capacity, and incident response remain the
Task 6.2 owner/operations TODO. OCR preprocessing remains in the node process,
while the Tesseract subprocess has its hard timeout. These limitations must be
closed operationally before policy activation.

## Protected candidate-ingestion paths

- `POST /content/upload` and `POST /content/text`;
- signed content linkage and development file mode under `POST /submit_content`;
- development-only `POST /add_block`, including its direct blockchain operation;
- content coordination `upload_binary_content`, `upload_text_content`,
  `submit_content`, `submit_existing_content`, and the final
  `evaluate_prevote_originality` service boundary;
- peer submission and originality-evidence receive paths, with bounded canonical
  media decoding;
- peer content fetch/registration when it can hydrate candidate content.

Peer acceptance of already-built blocks, chain sync/adoption, backup/import,
restart, historical reads, block-media recovery, and cache reconstruction are
intentionally not routed through the local pre-admission worker. They operate on
finalized/legacy or already-certified chain records and must retain their existing
deterministic block validation. Later activation/evidence binding and end-to-end
chain-integrity work belong to Tasks 6.4–6.11.

## Known policy and implementation notes

Task 6.2's peer-limit prose says “before base64 decode,” while the current
Protocol v1 canonical bytes object uses lowercase hex. Task 6.3 bounds both the
existing canonical hex wrapper and a narrowly shaped compatibility base64
wrapper without changing Protocol v1 wire format.

Animation remains provisionally allowed within all-frame limits because the owner
decision on GIF/WebP activation and safe animated review is unresolved. All other
Task 6.2 owner decisions remain unresolved, and the overall media-admission
policy remains inactive. This task does not implement Tasks 6.4 or later.

## Benchmark

Run:

```powershell
.\.venv\Scripts\python.exe .\scripts\milestone_6_task_6_3_media_validation_benchmark.py
```

The benchmark records wall-clock observations for a 4,096 × 4,096 near-limit
valid PNG, one-byte-oversized text, a small compressed 4,097 × 4,096 dimension
bomb, and a malformed PNG. Timing is diagnostic local evidence only and never a
consensus threshold.

## Task 6.3A lifecycle-performance remediation

### Diagnosis

The reported Task 6.3 lifecycle run was 578.88 seconds versus the historical
approximately 42-second architecture. A controlled rerun on this machine did
not reproduce that comparison literally: the unmodified Task 6.3 worktree took
168.126299 seconds, while a clean export of committed Task 6.2 took 196.276052
seconds on the same host. The repository's historical recorded run remains
40.978989 seconds total and 33.880567 seconds for commits. The earlier 578.88
seconds therefore included substantial host/run variability and cannot be
attributed solely to the Task 6.3 validator.

Instrumenting the unchanged 100-item run nevertheless identified a real,
pathological production call graph:

- four commit workers repeatedly materialized and fully validated the complete
  remaining mint queue before taking its first item;
- 402 queue listings caused 20,200 full queue-record validations (the
  four-worker form of a triangular N+1 scan);
- those validations and later whole-prefix candidate checks caused 27,460 full
  deterministic originality-evidence recomputations;
- queue evaluation consumed 371.55 inclusive worker-seconds and originality
  recomputation consumed 132.30 inclusive worker-seconds;
- 806 whole-state restores constructed 81,400 content objects and performed
  84,500 fully validated policy reads, consuming 35.42, 22.88, and 10.76
  inclusive worker-seconds respectively;
- SQLite section loads consumed 17.23 inclusive worker-seconds, while all
  ordinary blockchain saves consumed 5.13 and section JSON writes 0.73;
- Task 6.3 `validate_media_bytes` work consumed only 0.46 inclusive seconds,
  evidence verification/digest work remained below 0.30, and content-file
  storage remained below 0.70;
- this text-only lifecycle fixture started no image decoder child and ran no
  OCR. There were no sleeps, timeouts, busy retries, stale-head retries, or
  repeated full image decodes in this run.

The dominant cause was therefore quadratic/replayed service-layer validation,
not SHA-256, technical-evidence JSON, fsync, SQLite commit count, OCR, or the
isolated image decoder. Task 6.3's larger durable content records amplified the
already-quadratic restore path, but were not independently responsible for the
reported 13.8x wall-clock comparison.

### Remediation

Task 6.3A makes six scoped changes:

1. Canonical next-mint selection sorts the same immutable certificate order
   keys but fully validates candidates only until the first mintable item. An
   invalid earlier candidate is still fully rejected and skipped. Later items
   cannot affect the identity of the first valid candidate, so evaluating them
   was redundant.
2. Candidate validation maintains a process-local, cryptographically bound
   fully-validated chain-prefix optimization. Every reuse recalculates every
   cached block hash and previous-hash link from the restored durable document,
   and each newly observed suffix block still receives complete block,
   certificate, originality, reward, native-transaction, and Model A media
   validation. Cache loss/restart performs a full validation. Any content or
   hash mismatch falls back to the full validator and fails closed.
3. Protocol-v1 promotion reuses existing durable technical PASS evidence only
   after checking evidence/validator/policy versions, policy digest, evidence
   digest, byte length, exact raw-media SHA-256, content hash, and MIME. Invalid
   evidence is never silently replaced by a new success.
4. Immutable built-in media policies and their digest are validated/calculated
   once per version. Public callers still receive a deep defensive copy, so no
   caller can mutate policy authority.
5. A whole-state restore reuses an existing content object only when its full
   serialized durable dictionary is exactly equal. Any evidence or metadata
   difference takes the normal constructor/validation path.
6. Certified selection plus commit is coordinated by one process-local lock per
   normalized durable storage identity. Multiple `Blockchain` facades for the
   same SQLite database therefore cannot all select and replay the same
   pre-transaction queue head. The lock covers only reload, canonical selection,
   commit, and any retry for that logical call. Distinct storage identities use
   distinct locks and proceed independently. A weak-value registry drops lock
   bookkeeping when no live facade retains an identity.

No database schema, transaction, fsync, compare-and-swap, retry, canonical
ordering, consensus rule, policy limit, decoder isolation, or persistence rule
changed. The existing SQLite `BEGIN IMMEDIATE`, expected-head CAS, uniqueness,
and idempotent replay boundary remain the authoritative cross-process safety
mechanism. The coordinator neither caches authorization nor shares validation
results between callers. The prefix optimization is not evidence authority and
is not durable: deleting it can only cause more validation. Persisted technical
evidence remains authoritative; restart and concurrency cannot turn missing,
failed, incomplete, stale, or tampered evidence into PASS.

### Measurements

The controlled pre-fix Task 6.3 lifecycle result was 168.126299 seconds total,
150.245968 seconds commit duration, and 0.665575 blocks/second. After eliminating
the full-queue scan, a run took 96.352096 seconds. After validated-prefix reuse,
the next run took 78.833730 seconds total, 60.074498 seconds commit duration, and
1.664600 blocks/second. Back-to-back stressed-host observations of 300.357784 and
278.590837 seconds showed that this Windows benchmark has substantial
environmental variance.

On the final coordinator code, three complete 100-item observations were:

| Run | Total seconds | Commit seconds | Blocks/second |
| --- | ---: | ---: | ---: |
| final 1, host-load outlier | 202.815875 | 98.707280 | 1.013097 |
| final 2, instrumented | 37.570242 | 17.506579 | 5.712138 |
| final 3 | 35.277674 | 17.314790 | 5.775409 |

The final total-time median is 37.570242 seconds (minimum 35.277674, maximum
202.815875). The median is 77.65% below the controlled 168.126299-second pre-fix
run. The outlier is retained rather than discarded; its unchanged approval and
finality stages also slowed materially. All three runs committed and finalized
exactly 100 blocks with zero stale-head, SQLite-busy, or submission retries.

The instrumented final run gives the environment-independent acceptance signal:

| Work metric | Controlled pre-fix | Final | Change |
| --- | ---: | ---: | ---: |
| mint-queue record evaluations | 20,200 | 302 | -98.50% |
| full originality recomputations | 27,460 | 2,506 | -90.87% |
| candidate-path whole-prefix validations | 101 | suffix validation only; 14 full-chain validations across the complete restart/replay/sync scenario | removed from every appended candidate |
| certified/SQLite atomic commit attempts | 402 | 106 | -73.63% |
| redundant concurrent same-head attempts | 296 | 0 | eliminated |

The final run selected 100 distinct submissions. Its one repeated selection was
the benchmark's deliberate pre-transaction failure followed by its required
retry, not a local-worker race. The 106 atomic attempts are the 100 logical
commits plus the test's deliberate failure, lost-response replay, direct replay,
and four representative post-workload replays. Thus the durable failure and
idempotency probes remain exercised while the former 296 local race attempts are
gone.

The Task 6.3 microbenchmark implementation did not change. The final median
seconds were: near-limit valid image 0.276605; oversized early rejection
0.016115; dimension/pixel early rejection 0.000280; malformed-container rejection
0.000160. The valid case remained `ACCEPT`; hostile cases retained their exact
fail-closed outcomes and reason codes. These results match the earlier Task 6.3A
observations (near-limit 0.311210/0.280469, oversized 0.016485/0.017090,
dimension 0.000282/0.000280, malformed 0.000197/0.000172), confirming that the
lifecycle improvement neither bypasses media validation nor moves its cost into
the benchmark.

Remaining wall time is dominated by the intentionally serialized canonical-head
commit queue, SQLite durable state loading, and process-isolated finality
validators. Host scheduling/antivirus contention can still dominate individual
runs. The optimization does not parallelize canonical block creation, coordinate
separate operating-system processes, or relax any validation to chase a wall-clock
number; separate processes intentionally continue to meet at the durable SQLite
CAS/replay boundary.
