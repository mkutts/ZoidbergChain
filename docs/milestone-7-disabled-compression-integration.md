# Task 7.21 — Disabled adaptive compression application integration

Scope: offline provisional candidates only. No protocol, routes, production
configuration, genesis, history, signer or network activation is changed.

## Source-derived interface map (recorded before implementation)

| Boundary | Current source and input → output | Trust/version assumptions and isolated gap |
| --- | --- | --- |
| A submission | `api_routers/content.py` upload routes → `services/content_coordination_service.py` upload methods: bytes/MIME or text → ContentObject and stored accepted bytes | Upload is untrusted. Text normalization precedes accepted identity. Current cache is not canonical chain authority. Offline bridge begins at the accepted-byte service boundary; no HTTP registration. |
| B validation | `media_technical_validation.py::validate_media_bytes`: bytes/declared MIME → ValidatedMedia; `media_admission_policy.py` | Actual signature/container and size checks. Hand-built ValidatedMedia is untrusted and AdmissionAdapter revalidates it. Current images remain <=256 KiB; frozen v3 allows <=2 MiB. JSON/source are text/plain. |
| C admission | `admission_certificate.py` build/validate; `canonical_v3/admission.py::AdmissionAdapter.prepare`: ValidatedMedia + signed v1 certificate + trusted resolvers → instance-bound PreparedAdmission | Existing application v1 signatures are verified as v1. Frozen v2 evidence needs separate public test signatures, never relabelling. Historical reviewer state and claims are trusted harness dependencies, not peer assertions. Missing authority is incomplete. |
| D producer | `services/block_production_service.py::build_candidate`: state/collaborators, path/text, certificate view → Block/candidate dict | Active certificate type chooses v1/v2 and raw stored_bytes. `canonical_v3/media.py::produce` and `construction.py::BlockConstructionBridge.construct` already build adaptive complete v3 bytes using explicit TestOnlyConfig/state/evidence. Missing connection to restart/retrieval is addressed offline only. |
| E validator | `services/block_validation_service.py` validates dict using application collaborators; `block.py` defines active hashes | Current version guard accepts 1/2. `canonical_v3/block.py::parse_record` verifies closed canonical envelope/hash/signatures; media.reconstruct verifies encoded bytes in a bounded worker. Still needs independent technical MIME/evidence checks and explicit incomplete authority outcome. |
| F persistence | `blockchain.py` commits via `storage.py` JSON/SQLite document interfaces → durable active chain/indexes | Active SQLite requires DELETE/EXTRA. Isolated `canonical_v3/storage.py::V3Store` retains immutable canonical BLOB plus derived indexes, but its initializer unconditionally enables WAL. A verification-only DELETE/EXTRA initializer will reuse its actual insert/get/rebuild verification methods without calling the WAL initializer. No selected-chain/finality authority is manufactured. |
| G retrieval | `api_routers/public_chain.py::download_block_media` → blockchain integrity check → Response(raw bytes, MIME/hash); `media_integrity.py::verify_media_block` | Current reconstruction supports only 1/2 and embedded media_bytes. Offline retrieval will use V3Store.get, canonical parsing and strict decode, returning original bytes/MIME/size/hash. No compressed HTTP endpoint. |

The bridge is placed under `verification/task721/`, outside all active imports.
An environment variable or uploaded protocol field cannot instantiate it.
The frozen v3 block_version=3 uses the existing protocol-v2 signing envelope;
this task defines neither a new wire contract nor activation authority.

## Prerequisites and preservation

Branch `Compression-State-Bloat-and-Node-Economics`, HEAD
`75bd376463216c27742b5d2ad96ca676db1a1e73` (separate Task 7.20 commit).
Initial index/worktree were completely clean, including untracked files.
The requested 7.18/7.19/7.20 reports, corpus generators, manifests and results
were tracked. No applicable AGENTS.md was found, including hidden directories
and ancestor locations. No delegation was used. The source-derived map above
was written before implementation.

[prerequisites.json](../verification/task721/prerequisites.json) retains hashes
of every preexisting tracked file. The only additions are this report and
`verification/task721/`; no preexisting tracked file is edited. Final evidence
is in [preservation.json](../verification/task721/preservation.json). Nothing
is staged, committed, pushed, merged, deployed or migrated. No real chain DB
or keys were opened, and Task 7.22 was not begun.

## Implemented disabled boundary

[bridge.py](../verification/task721/bridge.py) contains no keys, signing,
network configuration, environment lookup, route registration or production
factory. `construct_candidate` consumes exact accepted bytes, reruns the real
technical validator, invokes the existing AdmissionAdapter (including actual
application certificate verification and duplicate lookup), then the existing
adaptive producer and BlockConstructionBridge. Test certificates/state are
explicit dependencies using the existing public fixture keys, never new
production authority. Missing canonical certificate/state/selection remains
subject to the existing constructor's incomplete outcome.

Tests also invoke the actual `ContentCoordinationService.upload_binary_content`
for text and PNG using a disposable content directory. Its returned accepted
bytes/hash enter the bridge. The cache file is then deleted and canonical-only
retrieval succeeds. HTTP upload/signing/review endpoints are not exercised.
Text upload normalization is upstream of accepted identity; the historical
source corpus loses seven bytes in this separately labelled accepted workload,
exactly as in Tasks 7.18–7.20. The bridge itself never normalizes its input.

`canonical_media` consumes the received immutable canonical bytes. Existing
parse_record verifies the closed canonical format, expected network/version
envelope, block hash, certificate/attestation/vote signatures and bindings,
native records, component budgets and descriptor. Strict reconstruction checks
allowed codec/version, declared encoded/original sizes, bounded frame profile,
checksum and original SHA-256, including canonical text. No received payload
is recompressed, repaired, selected again or substituted from a cache.

`validate_candidate` adds actual MIME/container checks and comparison of all
technical observations with signed evidence, plus explicit trusted test parent,
time, reward-pool, ledger and reviewer snapshots. It never uses the certificate
as its own reviewer-history resolver. Missing snapshots are INCOMPLETE;
resolver/worker failures remain local failures; invalid canonical evidence is
separate from current application admission rejection. These technical worker
checks are offline application compatibility checks, not a newly approved
consensus predicate: termination cannot justify rejecting certified history.

Even after successful checks, every returned object has
`integration_status=INCOMPLETE`, `consensus_authorized=False`, and explicit
remaining reviewer-history, selection and finality obligations. The selected
chain and finality tables stay empty. This is meaningful provisional service
integration, **not active protocol-v3 or public-network integration**.

## Byte-ledger reconciliation

[reconciliation.json](../verification/task721/reconciliation.json) contains all
78 per-record ledgers and comparable per-unique-object totals. It reads frozen
Task 7.20 evidence without writing to it and checks every integer partition.

| Population | Records | Unique originals | Accepted original B | Encoded B | Base64 B | Serialized media member B | Complete R B |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Historical primary | 36 | 36 | 6,093,910 | 5,285,229 | 7,047,024 | 7,055,315 | 8,241,301 |
| New primary | 34 | 34 | 11,521,163 | 11,002,892 | 14,670,572 | 14,678,466 | 15,798,621 |
| Ten-vote sensitivities | 4 | 4 reused | 2,136,199 | 2,107,607 | 2,810,148 | 2,811,073 | 2,913,508 |
| Long-metadata sensitivities | 4 | Same 4 reused | 2,136,199 | 2,107,607 | 2,810,148 | 2,811,073 | 3,120,258 |
| All measurements | 78 | 70 | 21,887,471 counted per record | 20,503,335 | 27,337,892 | 27,355,927 | 30,073,688 |

The new published totals use the same 34-object population, not all 78 cases.
Encoding saves **518,271 B**. Base64 adds **3,667,680 B**; descriptor/member
framing adds **7,894 B**, yielding **14,678,466 B**. The frozen rule compares
complete descriptors against identity (which also uses base64), not serialized
JSON against raw media. Every measured selected encoding, descriptor and record
is no larger than its corresponding identity alternative. No adaptive-expansion
defect was found. Validators retain the frozen rule allowing a larger but valid
external encoding; the normal producer never chooses it.

Across the 70 unique accepted originals: **17,615,073 B original**, **16,288,121 B
encoded**, **21,717,596 B base64**, **21,733,781 B serialized media**. A unique
original with sensitivity variants has multiple valid certificate/record sizes;
the reconciliation reports minima/maxima rather than summing them as objects.
Complete unique-object R totals range **24,010,562–24,217,312 B** if each
original uses one of its measured variants. Primary-only R is **24,039,922 B**.

There is exactly one media payload field in each closed canonical record.
Certificates retain original hashes and signed evidence, not another full media
copy. Intentional copies of signed messages, their hashes and payload fields
are required evidence and remain counted.

The **1,073,154 B** new certificate/evidence ledger is **1,072,338 B** of complete
certificate values plus **816 B** (34 × 24) of `"admission_certificate":` keys.
It includes all mandatory certificate members, nested technical evidence,
rights statement/payload/message/signature, fourteen signed votes and both
tallies/digests, with keys, arrays and delimiters. Per-field charges are retained
for every record. Signature-only bytes are a subset, not a replacement ledger
or extra charge. Required repeated signed bindings were not removed to improve
the overhead result. No omitted-field bug was found.

## Durable storage, recovery and retrieval contract

DisposableStore uses the existing V3Store schema and real inherited immutable
insert/get, canonical verification, derived indexes and rebuild operations.
Only initialization is narrowly adapted to SQLite **DELETE / synchronous EXTRA**
before schema creation. Existing DBs must already have the exact isolated schema,
context and DELETE journal; no conversion, default DB path or migration exists.
Create is exclusive and reopen uses mode=rw. Backup/restore/WAL maintenance and
chain-selection/finalization entrypoints are explicitly unavailable in this
bridge, including the inherited backup verifier which would enable WAL.

After persistence, a new Python process with a new decoder reopens the DB and
retrieves every record. Original comparison bytes are supplied only as a test
oracle after reconstruction; the sole reconstruction source is the canonical
BLOB. The parent has already checked exact canonical bytes on insert/get;
focused identity and Zstd tests check exact unchanged canonical bytes on reopen.
Every retrieved result supplies original bytes, MIME, original size/hash and
block identity, alongside incomplete consensus status. Missing blocks are
INCOMPLETE, corrupt stored canonical bytes/indexes are StorageCorruption, and
decoder/storage operational failures are local StorageUnavailable outcomes.
No consumer receives compressed bytes as originals.

Derived indexes are deleted and rebuilt from authenticated canonical records.
Damaged/truncated canonical BLOBs and missing records cannot be recreated from
indexes or DB metadata. Actual child-process exits after BLOB write, after index
write and after COMMIT exercise rollback/recovery and lost-acknowledgement retry.
Only the committed case survives; retry is idempotent. All DBs are disposable.

The complete record cap remains **3,145,728 B (3 MiB)**, original text cap
262,144 B, image/encoded cap 2,097,152 B, with the unchanged certificate/native/
remaining component budgets. Tests exercise cap−1/cap/cap+1 byte buffers and
reject noncanonical input even at the cap. They do not fabricate a schema-valid
3 MiB block: the frozen conservative closed-schema bound is 3,058,797 B. Existing
format regressions exercise real signed maximum image/text and caption records.

## Reproduction and evidence

From the repository root, using the existing pinned venv, no installation:

```powershell
.\.venv\Scripts\python.exe -B verification/task721/run.py corpus
.\.venv\Scripts\python.exe -B -m verification.task721.reconcile verification/task721/reconciliation.json
.\.venv\Scripts\python.exe -B verification/task721/run.py tests
.\.venv\Scripts\python.exe -B verification/task721/run.py preserve
```

The corpus runner bounds the parent exercise and fresh-process recovery;
test groups have 360-second bounds and unique workspace TEMP/TMP/basetemp.
Machine outcomes retain exact test IDs, skips, deselections and failure details.
Initial harness mistakes and their corrections are separately retained in
[initial_attempts.json](../verification/task721/initial_attempts.json), with no
acceptance credit for failed attempts.

## Executed results and acceptance gates

[end_to_end.json](../verification/task721/end_to_end.json) records **70/70**
format round trips: **43 Zstd / 27 identity**. All 70 original hashes, sizes,
stored sizes and codec choices match the frozen Task 7.20 rows exactly. This is
an independent bridge run, not a replacement of the frozen measurements.
Of those originals, **58** also meet current application admission (31 historical,
27 new): **40 Zstd / 18 identity** complete constructor candidates pass independent
validation. The other **12** (5 historical, 7 new) are explicitly excluded from
the application path solely by its unchanged 256 KiB image limit. Their format
coverage remains in the 70, including near-v3-limit containers.

All **128** canonical records are persisted/retrieved and recovered byte-exactly
in a fresh process with matching MIME, original size and SHA-256. Index rebuilding
reports 128 records, zero selected blocks and zero finality proofs. Recompression
is deliberately forbidden during received-byte checks, storage/retrieval and
fresh-process retrieval. The fresh process reconstructs before comparing the
separate expected-byte oracle. No off-chain original participates in decoding.

| Final disjoint test group | Passed | Skipped | Deselected |
| --- | ---: | ---: | ---: |
| New bridge/security/service tests | 43 | 0 | 0 |
| Existing canonical format, admission, issuance, history | 324 | 0 | 0 |
| Existing strict codec, isolation and platform evidence | 476 | 193 | 0 |
| Existing atomic storage | 45 | 4 | 0 |
| Active parser/hash, producer, validation, media/finality | 74 | 0 | 2 |
| Active SQLite storage regressions | 25 | 0 | 0 |
| **Total** | **987** | **197** | **2** |

The 193 skips require an actual Linux kernel. Four atomic WAL crash skips require
a fixed SQLite runtime. The two exact active deselections are
`tests/test_milestone_6_task_6_9_media_integrity.py::test_media_api_is_derived_and_returns_exact_binary_bytes`
(known restricted-Windows TestClient socket initialization limitation from 7.19)
and
`tests/test_milestone_7_task_7_17e_finality_durability.py::test_settings_connection_ownership_and_nested_begin`
(the empty-DB WAL-refusal control described below). They are not passes. The
HTTP check was not attempted here; underlying active reconstruction, current
producer/persistence and media-integrity service checks execute. No unrelated
full suite is claimed. Test IDs/details and the two deselections are retained
in [summary.json](../verification/task721/summary.json) and group outcome files.

| Gate | Outcome | Evidence / exact boundary |
| --- | --- | --- |
| A Adaptive producer construction | **PASS** | Real validation/admission/constructor for 58 objects; normal no-expansion selection; invalid/nonbeneficial encoder fallback in existing regressions. |
| B Independent canonical validation | **PASS, isolated scope** | Separate decoder/received bytes, canonical hash/signatures/metadata, MIME and explicit trusted test snapshots; full authority still INCOMPLETE. |
| C Byte-exact reconstruction | **PASS** | 70 format + 58 application records and SHA-256, before/after process restart. |
| D Isolated persistence/restart | **PASS** | DELETE/EXTRA, 128 fresh-process recoveries, index rebuild and real process-interruption/retry tests. |
| E Retrieval compatibility | **PASS, isolated service scope** | Original bytes/MIME/size/hash for both codecs; actual upload service and deleted-cache tests; no compressed public API. |
| F Active v1/v2 nonregression | **PASS, selected scope** | All preexisting tracked sources/fixtures unchanged; 99 active-path/storage tests, frozen hashes, accidental activation rejection. Two tests explicitly deselected. |
| G Active protocol-v3 integration | **BLOCKED** | No active imports/transition/authority; bridge always provisional. |
| H Public-network activation | **BLOCKED** | No approval, audit, public route, migration or deployment. |
| I Complete original Milestone 7 acceptance | **BLOCKED** | Application remains inactive; original metadata/representativeness/economics and security gaps remain. |

Task 7.21 is ready for review and an owner-made commit **as this disabled safe
subset**, with the preliminary WAL-control deviation explicitly disclosed.
It is not complete active application integration. Original Milestone 7
completion and production activation remain blocked. No commit was made.

## Security, platform and protocol gates

The unchanged isolated decoder uses per-request native processes, default
128 MiB memory, 5 s CPU, 10 s post-READY wall and 5 s startup limits. Windows
uses job/process controls; Linux has its existing separate containment worker.
Only Windows is executed here; Linux-only skips do not establish Linux safety.
Unsupported platforms fail closed. CPU/wall/launch/decoder unavailability are
operational failures, never proof of malicious canonical evidence. Producer
encoding remains the existing native in-process Zstd implementation; this task
does not claim independent encoder-process containment or new memory evidence.

All new storage work uses DELETE/EXTRA. SQLite 3.49.1's known WAL limitation is
retained by the unchanged AtomicV3Store
runtime gate retains the four unsupported WAL crash skips. The older 7.11
storage suite is not invoked because its V3Store initializer enables WAL;
its actual storage methods are exercised through the safe initializer here and
the existing DELETE/EXTRA atomic regressions run separately. No runtime upgrade
or weakened safety gate is used. One preliminary active-regression selection
inadvertently included the existing empty-database WAL-refusal control
`test_settings_connection_ownership_and_nested_begin`: it sets WAL on an empty
disposable DB then verifies active backend refusal. It performed no WAL media
transaction or crash exercise, but enabling it conflicts with this task's
stricter prohibition. Its 75-pass initial selection remains recorded separately;
the final `active_safe` selection excludes that control. No claim that WAL was
never configured during the preliminary selection is made.

Independent native decoder/security review, actual Linux containment evidence,
complete BFT/reviewer-history authority, production application-policy mapping,
versioned network activation approval and public API integration remain missing.
The narrow trusted test snapshots establish neither complete historical review
authority nor finality. No Tendermint/G2/reviewer-journal work is implemented.
Passing functional tests is not an independent security audit.

Original Milestone 7 also retains Task 7.20's measured <15% metadata-target
failure, synthetic-corpus representativeness and disclosed economics/resource
limitations. This task does not reweight or overwrite those findings. Completion
and production activation remain blocked independently of this bridge's result.
