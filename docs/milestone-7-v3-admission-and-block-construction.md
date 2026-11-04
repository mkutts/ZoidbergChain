# Milestone 7 Task 7.13 — Nonactivated v3 admission and block construction

Date: 2026-10-20 (America/New_York). Protocol v2 / block v3 remain inactive.
MODEL A is retained: one accepted media item per candidate block, with the full
accepted original reconstructible from canonical on-chain media.

## Repository verification and scope

- Branch: `Compression-State-Bloat-and-Node-Economics`.
- Starting HEAD: `6f50035f04cae5a1c5935eb5cdd6d07dc492059c`, separately committed
  Task 7.12 (`repair isolated image admission failures`). Initial worktree clean.
- No repository/ancestor `AGENTS.md` found. Inspection covered admission,
  submission, reviewer, certificate, production/validation and isolated v3 code.
- Read the [canonical implementation](milestone-7-v3-block-format-implementation.md),
  [schema](milestone-7-v3-canonical-schema-decision.md),
  [signing](milestone-7-v3-signing-and-domain-separation.md),
  [capacity](milestone-7-v3-storage-and-capacity-decision.md),
  [codec security](milestone-7-codec-security-contract.md),
  [storage](milestone-7-v3-storage-implementation.md) and
  [admission regression](milestone-7-image-admission-regression.md) boundaries.
- Only four new files: `canonical_v3/admission.py`,
  `canonical_v3/construction.py`, `tests/test_milestone_7_task_7_13_admission.py`,
  and this report. No existing implementation, vector, dependency or config edit.
- No staging, commit, push, merge, reset, deployment, migration or next task.

## Existing admission lifecycle and authority

| Stage | Existing implementation and authority |
| --- | --- |
| Upload | `api_routers/content.py` delegates to upload operations and `ContentCoordinationService.upload_binary_content` / `upload_text_content`. MIME declarations are checked, filenames are display metadata. |
| Byte/technical validation | `media_technical_validation.validate_media_bytes`: detection, canonical UTF-8 text, exact image bytes, policy sizes, container/metadata/dimensions and full-frame isolated Pillow decode. `ValidatedMedia.raw_media_bytes` is the accepted original; `result.raw_media_sha256` hashes those bytes. |
| Content registration | `services/content_coordination_service.py` stores the accepted bytes, SHA-256 content identity and technical evidence. Text upload normalization happens here, before signing; v3 never normalizes certified bytes. |
| Submitter attestation | WalletAuthManager challenge and `Blockchain.submit_signed_content_operation` bind creator, submission, exact hash, policy and technical evidence to the submitter signature. Replay/nonce checks remain here. `require_valid_submitter_attestation` protects review. |
| Review | Signed voting operations plus `dual_review.verify_vote_record` enforce creator exclusion, both originality/admissibility dimensions, one reviewer vote per dimension, historical reviewer resolution, signatures and threshold/quorum. `ReviewerEligibilityService` supplies status at an authenticated reference. |
| Certification | `Blockchain.evaluate_submission` freezes `build_admission_certificate`; `validate_current_admission` rebinds stored technical evidence and attestation, raw media, submission and creator. Negative/unresolved review cannot produce a qualifying certificate. |
| Queue/selection | `MintQueueService` and `_evaluate_mint_queue_item` require queued status, unblocked minting, verified content and certificate. `commit_certified_submission` owns atomic replay, chain-head/state revalidation and commit. These are minting authorities; an offline candidate grants none of them. |
| Accepted block | `BlockProductionService.build_candidate` constructs current admission block version 2, checks certified content and duplicate submission/certificate/reward; `BlockValidationService` checks certificate/reward/native bindings and ancestry. Finality is separate. |

The original content hash and submitter's signed identity are authoritative;
compressed payload hashes, file extensions, local paths, mutable display
percentages and codec choices cannot replace them. Technical evidence proves
neither copyright nor reviewer/ledger authority. Both review dimensions remain
mandatory even when an identical-looking file has a different original hash.

## Explicit integration boundaries

`AdmissionAdapter(TestOnlyConfig(context, test_only=True), dependencies,
decoder=IsolatedDecoder())` is instantiated only by an offline harness. Context
has no default network, genesis or policy digests. Tests reuse the existing
symbolic Task 7.10C context; it is not a launch identity. No active module imports
these new modules, no public route exists, and the storage factory is unchanged.

The integration input is the application's `ValidatedMedia` plus its complete
frozen **v1** admission certificate. `prepare` reruns the existing byte validator
and the existing full certificate verifier: constructing a `ValidatedMedia` or
passing an ACCEPT field does not confer admission. Fresh technical observations
must exactly equal both supplied evidence identities with typed canonical JSON
equality. The original bytes must already be canonical accepted bytes. Rights
signatures, review signatures, both tallies, creator exclusion and historical
reviewer statuses are independently checked. Dependencies are trusted harness
bindings, never uploaded boolean admission assertions.

Prepared results hold the original immutable bytes by reference and frozen
canonical descriptor/certificate bytes. Accessors return fresh parsed objects.
Only the issuing adapter accepts its prepared object; copied/hand-built objects
cannot enter construction. The harness is single-owner and disposable; it is
not a persistent admission queue or a cross-process authorization mechanism.

An explicit authoritative `original_claimed(SHA256(original))` lookup runs before
preparation and before/after candidate construction. The adapter also rejects
duplicate originals in its own prepared set. Identity and Zstd representations
therefore use the same claim key. No claim is written or released by construction.
Future atomic chain selection must close claim races and replay checks under
the application's existing commit boundary; candidate creation never claims to
do so, and never bypasses queue, quarantine or manual blocking.

## Bytes, compression and candidate records

Image bytes are unchanged. For text, “original” means the policy-canonical UTF-8
bytes already accepted and signed by the application. A noncanonical upload
cannot be substituted for that accepted byte sequence. Original SHA-256 is
preserved across encoding choices, evidence, certificate and block bindings.

The adapter reuses `canonical_v3.media.produce`, with only identity/1 or zstd/1.
It compares complete canonical descriptors, choosing Zstd only if strictly
smaller. Encoder inability or deterministic producer framing rejection permits
worker-verified identity fallback; local decoder failure does not. All strict
reconstruction uses `IsolatedDecoder`, including identity, preparation and final
candidate verification. No recompression of received media, new codecs or
decoder/containment bypass is introduced. Worker outputs must match the exact
held original, hash and size. Base64, reconstruction and canonical serialization
necessarily allocate buffers; the original byte object itself is not copied.

`BlockConstructionBridge.construct` requires an explicit closed header, a
newly signed **v2** admission certificate, a trusted `ConstructionState`, and
an explicit native selection (including `[]`). Omitted certificate/state/selection
returns `IncompleteConstruction` with named missing inputs and no record. Explicit
null is malformed rather than absence. Unknown/missing certificate fields reject;
text's four image observations must be present null, not omitted or zero.

The bridge verifies the v2 certificate using the isolated canonical verifier,
then binds submission/hash/creator and every structural technical observation
to the independently validated v1 admission. Policy/context fields necessarily
differ and must be covered by **new** rights/review signatures. Runtime code
never copies a v1 signature into a v2 envelope or signs anything. Current
application v1 evidence alone therefore yields an incomplete v3 candidate.

`ConstructionState` explicitly supplies parent height/hash/time, reward-pool
balance, account balances/next nonces and a historical v2 reviewer resolver.
Construction checks parent binding and increasing timestamp, five-ZOID reward
capacity, all reviewer statuses and sequential native balance/nonce application.
Native records must satisfy the existing domain-separated U10/T18 signing,
genesis context, ordering, uniqueness, count and size rules. Missing historical
reviewer or ledger entries return incomplete; a lookup exception is operational.
These are offline snapshot checks, not live ledger or fork-choice authorization.

Complete candidates contain exactly one unsigned five-ZOID creator reward,
no voter rewards, the complete closed certificate and media descriptor, native
aggregate, and reduced exact rational originality summaries. Hashes come only
from `canonical_v3.block.encode_record`; its complete-record and component checks
run after all evidence, signatures and transactions are known.

`CandidateRecord` contains immutable canonical R bytes, measured component
sizes and the admission reservation. It explicitly has `finalized=False`, with
canonical-selection authorization and finality proof outstanding. The bridge
does not construct, sign or accept consensus certificates, create finalized
state, write SQLite or select a canonical block. Finality is outside R and its
existing separate budgets still apply to any later finality protocol.

## Capacity guarantee

No compression gain is assumed. Before encoding, `reserve_identity` reserves
the analytic Task 7.10C bound, replacing only the maximal base64 payload width
with the original's identity width. Every other width stays at its maximum.

| Enforced component | Bytes / count |
| --- | ---: |
| v3 original image / original text | 2,097,152 / 262,144 |
| Encoded bytes | 2,097,152 |
| Max identity base64 / complete descriptor bound | 2,796,204 / 2,796,435 |
| Certificate / per technical evidence / attestation | 196,608 / 8,192 / 16,384 |
| Reviews | 32 total, 16 per dimension, 4,096 each |
| Native records | 10, 8,192 each; array 98,304 |
| Remaining disjoint canonical bytes | 32,768 |
| Complete canonical R cap | 3,145,728 |
| Simultaneous analytic maximum R | **3,058,797** |
| Guaranteed margin at maximal image | **86,931** |
| Reservation at maximal text | **612,121** |

The certificate's field-by-field bound is 172,901 and native array's bound is
81,931 under the tighter nested schema caps. The analytic bound includes all
keys/delimiters, escaping, maximal image caption, reward and the 87-byte portable
wrapper. It is deliberately conservative and not a fabricated valid block.
After exact serialization, all component caps, complete cap and admission
reservation are checked again. Changing evidence requires a new construction.

Optional transactions cannot consume mandatory media/evidence space: the
reservation already includes ten maximal valid native records. Invalid or
over-budget selections fail that construction without invalidating the issued
admission; a caller can explicitly retry with fewer transactions or `[]`.
Required evidence is never dropped. A valid record exactly at 3 MiB is
unreachable under the tighter schema bounds; tests distinguish analytic proof,
valid records, and synthetic C-1/C/C+1 instrumentation of the actual final gate.
There is no block-fit blocker under the approved closed schema combinations.

## Failure classifications

| Classification | Meaning and handling |
| --- | --- |
| `invalid_admission` | Malformed/unsupported/oversize original, evidence mismatch, invalid v1 signatures/reviews, unissued object, or duplicate original. No protocol/consensus verdict is emitted. |
| `invalid_canonical` | Malformed v2 evidence, descriptor, header or transaction/reward/state constraint, signature/hash mismatch, deterministic strict decoding rejection, or exact budget failure. Local construction refusal, not an active consensus rejection. |
| `incomplete` | Missing application certificate/history (typed IntegrationError) or missing v2 certificate/construction inputs/reviewer/ledger state (typed IncompleteConstruction). No invented evidence or record. |
| `local_failure` | Worker unavailable/crash/timeout, technical local-defense termination, lookup I/O exception, bad lookup contract or coordinator inconsistency. No admission or consensus-invalid verdict. Original worker Outcome is retained where available; exception causes are chained. |

`IntegrationError.classification`, `.code` and optional `.outcome` are the common
application-facing exception boundary; incomplete construction also carries the
same classification. Constructor misconfiguration is a programmer `V3Error`.
There is no HTTP registration; Task 7.12's existing 503 behavior remains intact.

## Verification

Before editing: existing Task 7.10C, Task 7.11 and non-HTTP Task 7.12 selection:
**190 passed, 1 deselected, 89.75 seconds**. The HTTP case is covered separately
with the API-capable regression selection below. Standard process-local TEMP/TMP
points to `temp/task713-runtime`; no permissions or worker restrictions change.

New deterministic fixtures use predictable published test scalars and real
rights/review/native signatures, actual technical validation and the actual v1
certificate builder/verifier. The application integration case exercises upload,
WalletAuthManager signed submission, both signed reviews, application evaluation
and `validate_current_admission` before entering the offline bridge. Fixture
v2 signatures are authored only in test code. Historical vectors are unchanged.

Coverage includes all four images/text; exact original hash/reconstruction;
identity fallback/beneficial Zstd; cross-encoding duplicate claims; handmade
ACCEPT forgery, malformed/oversize/MIME rejection; certificate/evidence
missing/null/tampering; exact rational 5/7; native/reward/ledger limits;
conservative maximal reservations; exact final record gates and retry without
optional transactions; unavailable/crash/timeout classifications at both
integration stages; dependency outages and nonactivation checks. The existing
isolation suite independently exercises real crash/timeout/reaping controls.

The first new-test run passed 53 cases with four setup errors caused by oversized
automatically generated parameter names. Explicit short IDs correct test naming;
no admission, fixture acceptance or validation assertion was weakened.

Final verification used Windows and the existing repository `.venv`; the
API-containing selection ran in the host test environment because Task 7.12
documents the outer sandbox's TestClient loopback-socket stall. Worker isolation,
application policy and temporary-file confinement were unchanged. No new Linux
execution or production containment approval is claimed.

| Final selection | Result |
| --- | --- |
| Task 7.13 complete focused selection before adding the three real-process cases | **65 passed, 125.80 s** |
| Three subsequently added real codec startup/crash/timeout cases | **3 passed, 65 deselected, 1.58 s** |
| Application admission / current and historical protocol / storage regressions | **237 passed, 74.91 s** |
| Existing canonical v3 / isolated SQLite / codec / containment regressions | **559 passed, 193 skipped, 219.25 s** |

The two final Task 7.13 selections cover all **68** collected cases; no case is
unrun. The 193 skips require an actual Linux kernel. Baseline and intermediate
runs overlap these results and must not be added as distinct coverage. The
maximal-text test admits all 262,144 bytes through current application validation,
forces identity fallback, constructs ten freshly signed native transfers and
verifies the exact candidate and reconstructed original against the 612,121-byte
reservation. Cross-encoding tests also construct both records and independently
check that original hashes stay equal while canonical block hashes differ.

Reproduce from the repository root (each basetemp is disposable test state):

```powershell
New-Item -ItemType Directory -Force temp/task713-runtime | Out-Null
$env:TEMP=(Resolve-Path temp/task713-runtime).Path
$env:TMP=$env:TEMP
# Final focused run (65 cases at collection time).
.\.venv\Scripts\python.exe -B -m pytest tests/test_milestone_7_task_7_13_admission.py -q --tb=short --basetemp=temp/task713-final-focused
# Added real-process cases; a fresh full focused run now collects all 68.
.\.venv\Scripts\python.exe -B -m pytest tests/test_milestone_7_task_7_13_admission.py -k real_codec_process_failures -q --tb=short --basetemp=temp/task713-real-worker
# API-capable host environment.
.\.venv\Scripts\python.exe -B -m pytest tests/test_milestone_7_task_7_12_image_admission.py tests/test_milestone_6_task_6_3_technical_media_validation.py tests/test_milestone_6_task_6_6_admission.py tests/test_protocol_v1.py tests/test_protocol_v1_golden_vectors.py tests/test_protocol_v1_native_transfers.py tests/blockchain/test_protocol_v1_block_format.py tests/blockchain/test_protocol_v1_genesis.py tests/blockchain/test_task_3_5_validator_quorum_finality.py::test_validator_quorum_is_ceiling_of_two_thirds tests/storage/test_sqlite_storage_backend.py tests/storage/test_storage_tools.py -q --tb=short --basetemp=temp/task713-application-regression
.\.venv\Scripts\python.exe -B -m pytest tests/test_milestone_7_task_7_10c_v3.py tests/test_milestone_7_task_7_11_storage.py tests/test_milestone_7_task_7_6_decoder.py tests/test_milestone_7_task_7_6a_sequences.py tests/test_milestone_7_task_7_6c_isolation.py tests/test_milestone_7_task_7_6d_linux_isolation.py tests/test_milestone_7_task_7_6d_evidence.py -q --tb=short --basetemp=temp/task713-canonical-regression
```

Four-file UTF-8, trailing-whitespace, final-newline and Python syntax checks
passed. `git diff --check` passed. Final HEAD/branch are unchanged; only the four
new files listed above are untracked/unstaged. No existing active source or
historical vector changed. Active v1/v2 behavior remains unchanged, including
the already-approved Task 7.12 HTTP 503 correction.

## Remaining activation and interoperability blockers

1. Freeze approved real v2 network/genesis/policy context and new signed
   attestation/reviewer issuance. Existing v1 signatures cannot be migrated by
   relabelling, and current routes cannot issue the needed v2 certificate.
2. Deliberately version/activate media policy. Current image admission is
   **256 KiB**, not v3's proposed 2 MiB. This adapter preserves that stricter
   authority and rejects larger images. The full 2 MiB reservation is proven,
   but full-size v3 application admission is not claimed or enabled.
3. Integrate trusted frozen reviewer-history resolution and authoritative
   v2 ledger snapshots, queue/manual-block checks, atomic original/submission/
   certificate replay protection and canonical commit under explicit activation.
   Candidate construction is never mint/selection authorization.
4. Complete production decoder/native-work and platform containment approval,
   independent protocol review and cross-platform application interoperability.
   The admission Pillow worker retains Task 7.12's documented weaker containment;
   the strict codec worker remains an offline controlled prototype.
5. Deliberately integrate production validation, finality, synchronization and
   persistence with their independent trust/ancestry/selection gates. No v3
   SQLite connection or active storage registration is added here.

These are activation gates, not permission to start subsequent work. Task 7.13
adds the explicitly nonactivated integration pathway only. **Task 7.13 is ready
for review and a later authorized commit; production activation is not ready.**
No commit was performed and no subsequent task was started.
