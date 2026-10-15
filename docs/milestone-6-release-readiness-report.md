# Milestone 6 release-readiness report

Date: 2026-10-15

Scope: Milestone 6 Task 6.11 only — final adversarial audit and narrowly scoped remediation for Immutable Media Safety and Admission. No Milestone 7 work, commit, or push was performed.

## Release decision

**CONDITIONAL PASS**

All Milestone 6 implementation acceptance criteria and all final code, protocol,
frontend, build, integrity, storage, peer, and dependency gates passed. The two
release-readiness defects found by Task 6.11 were fixed:

1. a duplicate `Blockchain.remove_invalid_mint_queue_entries` definition had
   silently overridden the hardened fail-closed implementation; and
2. the frontend dependency graph contained four HIGH npm findings.

The only release condition is external and operational: an authoritative Python
advisory scan was not run because the available `pip-audit` service would send
the installed package inventory to an external vulnerability service and that
disclosure was not authorized. `pip check` is clean. This limitation is not a
known exploitable protocol or implementation defect, but the Python advisory
status must be verified through an approved process before a public release.

The npm release target is fully met: **0 HIGH, 0 CRITICAL, 0 total known npm
vulnerabilities** in the final live audit.

## Repository and scope state

| Item | Verified value |
| --- | --- |
| Branch | `Immutable-Media-Safety-and-Admission` |
| HEAD | `35fe2d023d81431668a8c8e8ee7d3bb6eb0cb31f` — `Milestone 6 Task 6.10: integrate media safety lifecycle UI and API` |
| Upstream | `origin/Immutable-Media-Safety-and-Admission` |
| Worktree before Task 6.11 | clean |
| Worktree at continuation | dirty only with the intended uncommitted Task 6.11 changes |
| Tasks 6.1–6.10 | separate commits `6225499`, `454f962`, `160a02e`, `b4ae98f`, `a321d4e`, `a92ffb5`, `63f1549`, `f2fae23`, `d34da34`, `35fe2d0` |
| Pre-edit mismatch | none |
| Commit/push | none |

Final Task 6.11 paths are:

- `blockchain.py`
- `tests/test_milestone_6_task_6_11_release_readiness.py`
- `zoidbergcoin-ui/package.json`
- `zoidbergcoin-ui/package-lock.json`
- `docs/milestone-6-release-readiness-report.md`

No unrelated change or Milestone 7 implementation was found.

## Architecture summary

The current admission path is:

`bounded media validation -> deterministic technical evidence -> signed submitter attestation -> independent originality and admissibility review -> frozen admission certificate -> quarantine-aware canonical mint queue -> activation-enforced v2 block -> exact embedded media bytes -> chain validation/finality`

Pre-mint REPORT observations are a separate signed overlay that can quarantine a
submission but cannot change either review tally. Post-mint DISPUTE observations
are an additive warning overlay and cannot change a block, its admission
certificate, media, hash, canonical validity, or finality.

The consensus and security owners inspected for this audit include the frozen
Milestone 6 specifications and Task 6.3–6.10 reports/tests; block construction
and validation; submission lifecycle; technical evidence; submitter
attestation; dual review; admission certificates; activation; report/dispute
overlays; media integrity; reviewer eligibility/reputation; JSON/SQLite storage;
migration/export/import/backup; peer receipt and chain sync; API routers/access
controls; frontend lifecycle/signing utilities; dependency manifests; and CI
and operational documentation.

## Threat model and acceptance criteria

The audit treated the submitter, reviewer, reporter, disputer, browser, storage
document, cache, and authenticated peer as potentially malicious. It attempted
signature and domain replay, cross-submission/network/dimension reuse, evidence
mutation, direct and stale queue insertion, certificate/media/block swapping,
activation downgrade, illegal post-H legacy blocks, conflicting same-wallet
observations, concurrent report/mint operations, stale saves, malformed storage
encoding, corrupt export/import, one-bit media mutation, forged lifecycle state,
and unauthorized wallet/peer operations.

Release acceptance required no remaining correctness, consensus, determinism,
mint-gate, activation, finalized-media, or reachable HIGH/CRITICAL npm defect;
green full backend/frontend/build results; deterministic tested overlays; and
fail-closed handling of missing, malformed, unknown-version, or tampered current
evidence.

## Defects found and fixed

### Fail-closed mint-queue cleanup

`Blockchain` contained two definitions of
`remove_invalid_mint_queue_entries`. The later legacy body won Python method
resolution and could change a queued current-admission submission with invalid
evidence back to `approved`. It did not immediately permit minting because the
queue entry was removed and the commit boundary still required valid evidence,
but it weakened lifecycle semantics and duplicated security-sensitive logic.

The later override was removed. The sole active method delegates to
`MintQueueService.remove_invalid`, which quarantines an invalid current
submission with `invalid_admission_queue_entry`. AST inspection confirms one
definition and no duplicate `Blockchain` method names. The Task 6.11 regression
forces a current submission into a forged queue state, runs cleanup, verifies
quarantine/removal, and verifies direct certified commit still fails.

Restart reconstruction, queue evaluation, `require_valid_certificate_for_submission`,
candidate validation, and atomic commit independently revalidate current
admission evidence; a stale row or forged status cannot resurrect mintability.

### Frontend dependency findings

The initial live audit reported four HIGH package findings and no CRITICAL
findings. The smallest compatible remediation was applied:

| Package | Before | Final | Security threshold |
| --- | ---: | ---: | ---: |
| `axios` | 1.18.0 | **1.20.0** | 1.20.0 or later |
| `vue` | 3.5.13 | **3.5.42** | 3.5.42 or later |
| `@vue/server-renderer` | 3.5.13 | **3.5.42** | 3.5.42 or later |
| `source-map-js` | 1.2.1 | **1.2.2** | 1.2.2 or later |

The Vue architecture and application code were unchanged. Required transitive
lockfile entries moved only as resolved by those direct Vue/Axios upgrades.
Final frontend tests, production build, installed dependency tree, and live npm
audit all pass.

## Protocol invariant results

### Model A and media integrity

- The complete canonical accepted byte sequence is embedded in every current v2
  block and participates in the block hash.
- `media_hash` and `content_hash` are SHA-256 over those exact accepted bytes.
- Reconstruction uses block data and does not require a mutable cache file.
- A flipped bit, truncation, append, reorder, malformed canonical encoding,
  recompression, metadata-only byte change, media swap, stale digest, or stale
  block hash fails verification.
- Restart, peer receipt, JSON/SQLite, JSON-to-SQLite migration, portable
  export/import, report overlays, dispute overlays, and API reads preserve exact
  bytes. Finalized bytes cannot change without invalidating the block.

### Technical validation and attestation

- Unsupported, truncated, malformed, polyglot, dimension/frame/aggregate-pixel
  violating, noncanonical text, and unknown-evidence current media fail before
  review.
- Evidence is versioned, deterministic, and binds exact bytes, MIME/type, limits,
  policy, and evidence digest.
- The submitter signature binds the wallet, exact media hash, submission,
  network, policy, technical evidence, nonce, and canonical statement.
- Expired/used challenges, wrong signer/network/media/submission, unknown
  versions, altered evidence, replay, and development/unsigned masquerading fail.

### Dual review and admission certificate

- Originality and admissibility use distinct choices and signature-bound
  dimensions. The same eligible wallet may answer both without a double-vote
  penalty, while contributing only once per dimension.
- `UNSURE` counts toward quorum but not the decisive approval denominator.
- Both positive outcomes are mandatory for current admission.
- The certificate freezes canonical signed votes, reviewer references,
  technical evidence, attestation, media/policy/network/submission identity, and
  both tallies. Later votes or reputation changes cannot mutate it.
- Cross-domain, cross-dimension, cross-submission, cross-network, choice,
  attestation, evidence, policy, certificate, media, and block swaps fail.

### Activation and legacy

- `H - 1` is the last permitted legacy height and `H` is the first mandatory
  admission-v2 height.
- v1 and unknown block versions fail at or above H, including valid-looking
  records with recomputed hashes.
- The activation record is bound to network/genesis, fixed once, persisted in
  both configuration and chain state, compared during peer sync, and cannot be
  removed or weakened after activation.
- Historical v1 blocks remain readable below H with unchanged hashes. Legacy
  originality certificates remain historical/readable but are not current
  admission authority; missing historical fields are not fabricated.

## Mint-bypass audit

No tested current post-activation path minted without the complete Task
6.3–6.6 evidence chain. The following attempts failed closed:

- direct service/commit calls;
- direct or stale queue insertion;
- restart reconstruction of an invalid row;
- forged submission/storage/lifecycle state;
- legacy originality-only certificate;
- missing prerequisite or tampered current certificate;
- wrong network or activation/block version;
- pre-activation pending legacy semantics after H;
- development/unsigned submission;
- quarantined submission; and
- report-threshold versus mint and queue-selection races.

The certified atomic commit reloads durable state, verifies the canonical head,
submission status, quarantine/report evidence, queue membership, certificate,
technical evidence, attestation, reviews, and exact media before append.

## Report and dispute determinism

REPORT remains independent of admissibility. Three distinct eligible wallets,
including at least one established reporter, are required. One wallet has one
counted representative. Conflicting signed observations are sorted by signed
identity and record digest, so delivery order does not affect counted sets,
reason counts, report-set digest, established evidence, threshold, or quarantine
identity. A stale facade save is rejected and cannot erase committed quarantine.

DISPUTE uses the corresponding deterministic representative rule for finalized
media. The threshold changes only the additive `finalized`/`disputed`
presentation overlay. It never deletes or rewrites media, certificate, block
hash, canonical validity, or validator finality.

## Race and concurrency results

The focused suites exercise concurrent duplicate/conflicting votes, reports and
disputes; same-dimension uniqueness; duplicate submission; report threshold
versus atomic mint; stale save versus quarantine; restart during pending state;
and peer/local idempotent receipt. Repetitions and storage transactions/locks
produced one durable winner or deterministic conflict evidence. No duplicate
same-head commit or quarantine erasure was observed.

## Storage, durability, migration, export, and backup

JSON and SQLite clean restart, SQLite additive/idempotent schema startup,
malformed records, stale snapshots, rebuildable reviewer indexes, corrupt
non-rebuildable evidence, legacy records, JSON-to-SQLite migration, portable
export/import, and backup/reopen are covered by the focused and full suites.
Current media and admission evidence are fully validated before import/migration
acceptance; cryptographic evidence is not silently regenerated. Corrupt exact
bytes, hashes, canonical encoding, certificates, or non-rebuildable evidence
fail closed.

Abrupt operating-system power loss was not physically injected. The audit
simulated restart at lifecycle boundaries, concurrent facades, atomic storage
transactions, backup/reopen, and stale saves.

## Peer and cross-node results

Peer routes require the configured peer authentication mode, active peer/network
identity, and local revalidation. Peer-supplied approved/admitted/verified flags
are not authority. Invalid signatures, wrong networks/policies/activation,
malformed media/certificates, altered reviewer references, duplicate/conflicting
messages, illegal legacy blocks, partial chains, and invalid candidate chains
fail or remain non-authoritative.

The test harness used independently instantiated nodes and independent JSON or
SQLite stores with the same deterministic genesis/network, activation, signed
inputs, and validator/reviewer context. Reversed delivery converged for dual
review tallies/certificate inputs, report and dispute representative sets and
digests, accepted v2 block hash, admission certificate digest, media hash,
reconstructed bytes, chain, and finality view. This was an in-process multi-node
test harness, not a live geographically deployed network exercise.

## API, frontend, and access control

- Public reads expose policy, lifecycle/status, and intended finalized
  metadata/integrity without local paths or private evidence.
- Review, report, dispute, and signing challenges require verified wallet/access
  policy on public-testnet configurations.
- Peer receive/sync routes retain peer authentication, active-peer, network, and
  replay checks.
- Admin/development mutations remain authenticated and/or environment gated.
- No public force-admit, force-mint, force-unquarantine, clear-dispute,
  delete-finalized-media, activation mutation, or finality override exists. A
  caller may request ordinary mint processing, but cannot bypass the canonical
  queue/certificate/quarantine/atomic-commit gates.
- UI/API copy and conservative fallbacks keep technical pass distinct from full
  approval, originality distinct from admissibility, REPORT distinct from vote,
  DISPUTE distinct from deletion, integrity distinct from safety, and legacy
  distinct from current admission certification. Missing/loading/malformed
  lifecycle data never renders as approved.

## Fail-closed and architecture review

Security-sensitive current paths reject unknown versions, missing evidence,
failed signatures, invalid hashes, malformed encodings, absent or conflicting
activation, invalid certificates, and uncertain non-rebuildable state. Cached
chain-prefix validation is cryptographically keyed and loss causes full
revalidation; a failed verification is not cached as true.

The duplicate queue-cleanup method was the material duplicated-logic defect and
was removed. Canonicalization remains centralized in the versioned protocol,
review, report, dispute, attestation, certificate, and media-integrity modules.
No other material process-local-only security state, mutable consensus field,
API/business divergence, or unsafe fallback was found in the audited scope.

## Performance findings

Structural counter tests confirm:

- report/dispute eligibility uses the finalized reviewer qualification index,
  rather than a whole-chain ancestry walk per observation;
- dispute vote lookup is wallet-indexed;
- chain-prefix validation is cached by exact cryptographic prefix while still
  checking hashes/links on reuse;
- queue selection ranks certificate identities and validates candidates until
  the first mintable item, rather than rescanning unrelated global state;
- ordinary lifecycle/UI reads do not repeatedly hash full media unless exact
  integrity verification is requested; and
- report/dispute tallies operate on the submission's observed set, not a global
  rescan.

No pathological correctness-affecting regression was observed. Remaining scale
risks are the expected per-submission observation-set sort, initial/rebuild
qualification-index ancestry traversal, full exact-byte hashing when integrity
is explicitly verified, and authenticated peer transfer of complete Model A
media.

## Dependency and verification record

All pytest commands used workspace-local base temporary directories.

| Gate | Final result |
| --- | --- |
| Dedicated Task 6.11 adversarial suite | **16 passed** |
| Tasks 6.3–6.10 focused regression suite | **185 passed** |
| Task 6.11 + mint queue + activation regression group | **65 passed** |
| Wallet/signature + reviewer/reputation + queue/mint/block + chain/reorg/finality sweep | **282 passed** |
| API/access + peer + storage/migration + two-node + media-integrity sweep | **585 passed** |
| Full backend suite | **1,381 passed in 1,351.47s** |
| Full frontend suite | **148 passed** |
| Frontend production build | **passed; 122 modules transformed** |
| Python compileall | **passed** for root modules, routers, services, scripts, and tests |
| `pip check` | **passed — no broken requirements** |
| Python vulnerability advisory scan | **unverified; external inventory disclosure not authorized** |
| Live `npm audit` | **0 total, 0 HIGH, 0 CRITICAL** |
| `git diff --check` | **passed**; informational working-copy line-ending notice only |

The full backend suite is the authoritative aggregate result for signature and
wallet, reviewer/reputation, queue/mint/block, chain/reorg/finality, peer sync,
storage/migration/export/import/backup, API/access/router, and media-integrity
coverage. Additional focused category sweeps were run as Task 6.11 evidence and
remained green.

## Deployment procedure

1. Build and distribute one identical Milestone 6 release to every node.
2. Confirm every node has the same frozen genesis and network identity.
3. Stop block producers and, where necessary, peer ingestion while the boundary
   is selected and persisted.
4. Determine the canonical tip and choose one network-wide activation height
   `H = canonical tip + 1`.
5. Configure and persist the identical H on every node. Do not independently
   calculate H at different tips.
6. Verify storage integrity, migration state, dependency lock/build, and backup
   coverage before restart.
7. Verify `/status` reports the expected network/genesis, canonical tip,
   activation height, and non-misconfigured activation state.
8. Restart nodes on the upgraded binary and confirm peer summaries agree on H.
9. Resume peer ingestion/producers only after compatibility checks pass.
10. Verify H-1 is the last legacy height and the first block at H is a valid v2
    block with complete admission evidence and exact embedded bytes.
11. Monitor admission failures, queue cleanup, report quarantine, dispute
    overlays, peer rejection, storage integrity, and exact-media verification.

Rollback cautions:

- Never restart a node that has crossed H with missing or weaker activation
  configuration.
- Never downgrade a post-H node to a binary that could accept new v1 blocks or
  omit v2 admission validation.
- Do not rewrite H after it is fixed; recover the canonical configuration and
  chain together.
- A rollback may stop production or restore an exact pre-activation backup, but
  it must not rewrite finalized media or post-activation history.

## Compatibility and migration notes

Historical block hashes and pre-H v1 interpretation are unchanged. Current v2
records add frozen admission evidence and retain complete media bytes. Existing
JSON and SQLite formats upgrade additively; migrations are idempotent and
validate current evidence. Old originality certificates remain readable but
cannot authorize a current post-H mint. Operators must deploy the new frontend
lockfile and must not mix activation heights or weaker binaries.

## Known limitations and remaining risks

### Security

- Python advisory status is externally unverified. This is the sole release
  condition. There are no known HIGH or CRITICAL npm findings.
- Immutable media can remain harmful even when technically valid; integrity is
  not safety or legality. Browser/reviewer exposure still requires operational
  content-handling controls.
- Authenticated malicious peers may consume bandwidth/storage with independently
  valid but ultimately orphaned auxiliary evidence; it cannot authorize a v2
  block without complete embedded admission evidence.

### Consensus and determinism

No known remaining consensus or determinism defect exists. Deployment still
depends on identical genesis/network, activation H, validator set, and frozen
policy/runtime versions. The multi-node evidence is a deterministic harness,
not a live WAN soak test.

### Performance

No release-blocking regression was observed. Large Model A media transfers,
explicit integrity hashing, observation-set sorting, and qualification-index
rebuilds remain bounded operational workloads to monitor.

### Operations

- No physical power-cut/fault-injection campaign or long-duration WAN soak was
  performed.
- Activation is an operator-coordinated one-way boundary; mixed H values or a
  post-H binary downgrade are unsafe and intentionally rejected.
- Backup/restore drills remain an operator responsibility even though automated
  round-trip and integrity tests pass.

## Remaining OWNER/POLICY TODOs

These do not weaken the frozen Public Testnet engineering rules but require
owner/legal/operations decisions before broader deployment:

- final prohibited-content definitions and jurisdiction;
- final admissibility authority/quorum policy beyond the current testnet rule;
- appeals, conflicts/recusal, reviewer welfare, and escalation procedures;
- legal review and production wording for the submitter rights/permanence
  attestation;
- final network activation height and coordinated rollout window;
- operational response/presentation policy for quarantined or disputed harmful
  content that preserves Model A immutability; and
- approval for an authoritative Python advisory scan and resolution of any
  finding it reports.

## Explicit final answers

| Question | Answer |
| --- | --- |
| Can any current post-activation submission mint without complete valid admission evidence? | **NO** |
| Can a v1 block be newly accepted at or above activation H? | **NO** |
| Can finalized media bytes change without invalidation? | **NO** |
| Do independently instantiated test nodes converge given the same signed inputs and protocol state? | **YES** |
| Can REPORT alter the admissibility tally? | **NO** |
| Can a post-mint dispute alter block validity or finality? | **NO** |
| Are any HIGH npm dependency findings left? | **NO** |
| Are any CRITICAL npm dependency findings left? | **NO** |
| Did every Milestone 6 implementation acceptance criterion pass? | **YES** |

## Final recommendation

**CONDITIONAL PASS**: the implementation and tested protocol are ready, the two
Task 6.11 defects are remediated, all final suites/builds/checks are green, no
tested mint or activation bypass remains, exact media integrity and deterministic
overlay convergence hold, and npm is clean. Authorize and complete an
authoritative Python vulnerability advisory scan before public release. If that
scan reports no unmitigated reachable HIGH/CRITICAL issue, this decision becomes
**PASS** without further protocol change.

