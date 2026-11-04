# Milestone 7 Task 7.15 — Authenticated history and replay integration

Date: 2026-10-21 (America/New_York). Protocol v2 / block v3 remain inactive.
MODEL A, current consensus, reviewer rules and active persistence are unchanged.

## Repository verification and scope

- Branch: `Compression-State-Bloat-and-Node-Economics`.
- Starting HEAD: `4e8648047aa3b3959bfa16aa81e62ffb56f84dc3`, separately committed
  Task 7.14, `implement isolated v2 evidence issuance`.
- Initial worktree clean; no applicable repository or ancestor `AGENTS.md` found.
- Before editing, all **60 Task 7.14 tests passed in 21.25 seconds**.
- Read the [issuance report](milestone-7-v2-evidence-issuance.md),
  [admission/construction boundary](milestone-7-v3-admission-and-block-construction.md),
  [closed schema](milestone-7-v3-canonical-schema-decision.md), and
  [signing contract](milestone-7-v3-signing-and-domain-separation.md).

Only three new files: `canonical_v3/history.py`,
`tests/test_milestone_7_task_7_15_history.py`, and this report. No active source,
schema, configuration, dependency, historical test or golden fixture changes.
No commit, push, merge, deployment, key creation/rotation, chain reset,
activation, public route or subsequent task.

## Authoritative sources and authentication

| Fact | Existing source and checks at this boundary |
| --- | --- |
| Reviewer identity | Durable signed payload and signature, verified by `canonical_signed_vote_evidence`; selected fresh v2 votes use `canonical_v3.evidence.validate_vote` and personal-sign recovery. Display names and caller wallet claims confer nothing. |
| Chain activity and wallet age | Application's previously validated canonical `chain` section; `ReviewerEligibilityService.qualification` derives creator/native/mixed paths from finalized ancestry. No uploaded activity counts. |
| Finalized references | Persisted `finalized_blocks` on that chain, the same authority used by `Blockchain.get_finalized_head` and `is_finalized_canonical_reference`. Index/link/root/network consistency is checked; a vote must reference an explicit persisted finalized canonical record. |
| Historical participation | SQLite `durable_vote_records`, restricted to relevant wallets. Accepted lifecycle is local application authority. Source JSON and relational columns must agree, signatures/identity must verify, submission/hash/creator must match, and historical status and epoch quota must be reproducible. Rejected rows do not earn participation. |
| Established status | Existing `ReviewerEligibilityService.status_at_reference`, earned finalized activity, elapsed probation and accepted distinct-submission participation. Current `reviewer_states` labels are not authority. The unchanged policy bootstrap set is empty. |
| Reputation | `reviewer_offense_records` with signed evidence, creator/finalized/accepted-vote bindings, and `reviewer_penalties`. The existing reputation service reproduces escalation and penalties; the stored penalty schedule and offense outcome must match. No reputation summary or arbitrary score enters issuance. |
| Originality/admissibility | The immutable complete selected fresh v2 records from `FrozenReviewJournal`, checked independently and kept separate. Historical v1 votes can establish same-context participation but are never converted into selected v2 votes. |
| Creator and admission | Persisted submission hash/creator/frozen v1 `admission_certificate` must equal the prepared application's source certificate. Its complete signatures and media binding are independently revalidated with the reconstructed historical resolver. |
| Prior certification/replay | Current canonical chain duplicate media/submission checks plus the journal's persisted replay-claim lookup. Future v2 issuance, including issued-but-unminted certificates, must be represented by that journal/claim authority. |

The database is the **trusted local application's store**, already validated by
the application. This is not an arbitrary database import, peer history proof,
or a new consensus/finality verifier. A local administrator replacing both
canonical state and its validation provenance remains outside this boundary.
Signature verification authenticates signed contents; it does not authenticate
unsigned lifecycle/status/reference metadata on its own.

`SQLiteHistoryReader` requires explicit `TestOnlyConfig` and an existing
`SQLiteStorageBackend`. It opens that existing path with SQLite `mode=ro`,
`query_only=ON`, and one read transaction. A connection-bound facade reuses
existing section/vote/offense/penalty read methods without nested connections,
schema initialization, or nested commits. The frozen journal and replay lookup
receive the **same connection**. Readers cannot create or modify a database.

The source chain's network ID and root must equal the configured N/G. Missing
network provenance is incomplete; a contradictory network/root is invalid.
Historical participation/offense signatures must also belong to that network.
Matching reviewer/reputation rule versions does **not** authorize migration of
old-network reputation to a fresh launch. No cross-network/root state mapping is
introduced. A new launch needs its own approved history and genesis context.

## Eligibility snapshots and unusable history

Accepted durable events are checked in deterministic observation/identity order.
Before each accepted vote earns participation, its signature, canonical identity,
submission/creator, recorded finalized reference, derived status and quota are
checked. Only verified earlier accepted events enter the disposable projection.
Both dimensions of one submission count once, including unsure participation.
No duplicate `(wallet, submission, dimension)` can count twice.

Historical status filters out activity and penalty references after the requested
height. Epoch participation likewise excludes later heights. Offenses are
validated and replayed through the unchanged `ReviewerReputationService`; stored
penalty rows are compared with reproduced outcomes, not trusted as summaries.
Current `NEW`, established or penalty labels cannot confer historical status.
Unbacked legacy penalty transitions with no durable penalty evidence are
incomplete. No reviewer system or active historical rule is replaced.

Records marked `legacy_unverifiable`, missing required historical references,
missing source submissions, missing finalized state, or absent accepted v2
selection produce an explicit `IncompleteEvidence` and no certificate.
Signed records with contradictory metadata, unsupported policy/rule versions,
forged status, invalid signatures, exhausted quota or mismatched penalties fail
closed as `INVALID_CANONICAL`. Database/SQLite and trusted journal outages are
`LOCAL_FAILURE`; invalid callback contracts are operational failures as well.
None of these become a live consensus verdict.

Daily admission controls and challenge consumption have an additional boundary:
the existing vote path calls wallet authentication, runtime review policy and
durable quota admission. The current store does not retain every historical
runtime daily-policy configuration/challenge needed to independently replay
that entire admission process. Accepted local lifecycle is its authority;
caller counts/allowlist flags are not. The frozen-v2 journal contract requires
accepted challenge/nonce/expiry, daily admission policy and participation checks
at the stored references. If that acceptance history is unavailable, `load`
must return `None`; a producer cannot substitute a purported valid flag.

Current active v1 storage has no approved fresh-v2 acceptance/freeze journal.
The supported historical participation verifier handles its existing signed v1
and dual-review records under their original contracts. It does not pretend
those records are new v2 signatures or implement a future v2 reputation journal.
Production v2 participation/offense retention and its approved context bindings
remain required before activation. Unsupported history cannot earn eligibility.

## Nonactivated issuance pathway

`AuthenticatedHistoryAdapter(admission_adapter, history_reader).issue(prepared)`
has no votes, eligibility flags, reputation summaries or attestation parameters.
It obtains the complete accepted records from the trusted journal, validates
them, reads/reconstructs application history, and then invokes Task 7.14's
`EvidenceIssuer` with concrete history-backed dependencies. The issuer still
checks exact selection equality, signatures, technical evidence, media/submission
binding, separate tallies, ordering and every closed schema/cap.

The `FrozenReviewJournal` protocol supplies only accepted immutable fresh
records and persisted claim lookups, never an eligibility decision. There is
deliberately **no active implementation, default selection policy, registration,
signing service or public endpoint**. Missing journal/selection is incomplete.
This port represents the existing application's local acceptance authority, not
a new signer, certificate authority or trust in caller reputation. Approving
the bounded selection/freeze policy is still necessary; the adapter never picks
a favorable subset or silently drops oversized/unfavorable votes.

Success returns immutable `CertificationProposal(VerifiedCertificate, ReplayPlan)`.
Its evidence is ordinary acceptable Task 7.14 v2 evidence. Its replay plan is
**unconsumed**, and the proposal grants no mint, canonical-selection or finality
authority. Access to a result wrapper does not bypass later revalidation.

The unchanged per-dimension rules require at least five eligible votes, at least
one established reviewer, a nonzero decisive denominator, and
`positive*10000 >= decisive*7000`. Unsure contributes to quorum/participation but
not the denominator. The tests retain exact **5/7** summaries. Identity/1 and
zstd/1 preparation produce the same certificate and replay plan for identical
accepted originals. Compression is absent from review and replay identities.

## Signing and replay boundaries

No signing domain or signed field changes. Selected votes retain the approved
flat `zoidbergchain/community-review/v3` payload; creator rights retain the
`zoidbergchain/submitter-attestation/v2` envelope. New signatures are supplied
records; runtime code never signs, fabricates a reviewer or promotes an old
signature. Only test code signs with existing published deterministic scalars.

| Replay attempt | Intrinsic or stateful protection |
| --- | --- |
| Vote reused for another submission/media | Signed submission ID and original SHA-256, exact duplicate-field equality, and application submission/media binding. |
| Vote reused in another dimension | Signed dimension/choice and fixed dimension-specific choices; no relabelling. |
| Cross-network or protocol/signing version | Fixed N/domain/versions/policy bindings, signer recovery, source network/context checks; no fallback. |
| Cross-genesis | Reader's trusted root, frozen journal's full Context, replay namespace and finalized ancestry pin G. Admission signatures do **not directly sign G**. Reusing N with identical policies across roots remains cryptographically indistinguishable to those signatures; N reuse is forbidden. No silent direct-G amendment. |
| Duplicate reviewer signatures/votes | Closed-vote validation rejects repeated dimension/wallet, including identical/high-S-equivalent signatures. Cross-issuance message/nonce/signature/review claims require persisted state. |
| Creator attestation replay | Persisted signer+nonce, message and signature claims; signed creator/submission/H/technical/policy binding. Nonce/message claims also cover signature malleability. |
| Duplicate/conflicting certificates | Original-media, submission and certificate claims. The original key excludes submission/policy/encoding, so conflicting valid certificates for the same original intersect. Existing canonical originals/submissions are also rejected from application history. |
| Reorg/stale history | Proposal carries expected canonical/finalized heads and a source revision fingerprint. Final atomic integration must compare/revalidate these and reconcile fork-local claims on rollback. |
| Concurrent attempts | Read preflight detects already persisted claims; it cannot reserve them or elect one writer. Final atomic integration must serialize competing writers. |

`replay_keys` produces sorted local SHA-256 claim identifiers. Their namespace is
N/G/protocol=2, deliberately excluding media/review policy so policy changes
cannot authorize another mint of an original. Claim kinds are original,
submission, certificate, attestation nonce/message/signature, and per-vote
submission/dimension/wallet, nonce, message and signature. Repeated keys in one
proposal reject. These are **local storage identifiers**, not new signing
domains, wire fields, signed attestations or canonical certificate commitments.

The history revision hashes relevant raw application inputs plus exact selected
votes/rights. Legacy application JSON may contain floats; the local revision
fingerprint uses its deterministic JSON representation. It never changes v3's
strict float-free canonical encoding or any historical block commitment.

## Atomic persistence and concurrency requirements

`AtomicCertificationStore.commit(proposal, canonical_record)` is a bounded
**interface only**. No production implementation or active SQLite migration is
added. The existing reference boundary is
`Blockchain.commit_certified_submission` /
`SQLiteStorageBackend.atomic_commit_blockchain_document`: `BEGIN IMMEDIATE`,
locked reread, expected-head comparison, uniqueness synchronization and
commit-before-acknowledge. The isolated `V3Store` currently has its own connection;
independently committing it and replay state would not satisfy this interface.

Eventual integration must perform all of the following under one write boundary:

1. Re-read canonical head, finalized anchors, verified media/admission,
   submission/queue/manual-block state, complete selected review history and
   reviewer/ledger state. Compare the expected revision or rebuild the proposal
   after a stale result. Recheck new v2 participation and daily admission state;
   a fingerprint of legacy state alone cannot account for other v2 admissions.
2. Reverify original bytes, fresh rights/vote signatures, historical eligibility,
   both quorums/tallies and exact certificate/block bytes under trusted N/G.
3. Check and consume every vote/attestation/certificate/submission/original claim
   with durable uniqueness. Charge one distinct-submission participation per
   reviewer/epoch; serialize predicate/quota checks as well as individual keys.
4. Persist the frozen issued certificate, canonical block, canonical indexes,
   replay claims and relevant ledger/reviewer effects in that same transaction.
   An idempotent retry must compare the immutable certificate/block/context;
   conflicts must not be treated as successful retries.
5. Commit before acknowledging. Any exception, stale snapshot, duplicate,
   failed block persistence or rejected canonical selection rolls back all
   effects, with no orphan certificate or permanently consumed challenge.

Fork-local canonical claims need a block/branch owner and must be reconciled in
the same transaction as rollback/selection. Finalized history must never be
detached. Decide explicitly which accepted challenge/issued-certificate claims
are permanent and which canonical settlement claims are branch-local; do not
release all nonces on reorg or keep orphaned canonical media claims forever.

Two concurrent read preflights intentionally return the same valid proposal and
consume **zero** claims. A disposable SQLite claim-contract probe demonstrates
one winner under `BEGIN IMMEDIATE` plus unique claims and full rollback after an
injected failure. It does **not** implement or test atomic certificate+canonical
block persistence, live signing/challenge consumption, or production reorgs.
Durable replay protection is not complete in this task.

## Tests and results

The new suite uses real SQLite records, original accepted media validation,
fresh fixture signatures, the full admission verifier and unchanged reviewer/
reputation services. Its symbolic chain/finality fixture is trusted state, as in
existing reviewer-service tests; it is not a fully mined/finality-verified chain.
Its explicit same-root historical test context uses the old network label and a
symbolic genesis, **not** the actual public-testnet root or a launch mapping.
Staging/claim tables exist only in disposable test databases. No active table
definition changes, and the real reader is checked for zero writes.

Coverage includes forged eligibility and historical reputation, source-column
contradictions, signature/dimension/media/submission/network/genesis/version
replay, high-S duplicates, nonce duplicates, separate quorum/established/unsure
cases, missing records, penalties/expiry and future-reference exclusion,
conflicting original certificates, concurrent preflight and claim rollback,
identity/Zstd equivalence, unavailable/corrupt storage, and nonactivation.

Verification used Windows and the existing repository `.venv`. The historical
selection ran in the API-capable host test environment because prior repository
reports document sandbox TestClient loopback stalls. No assertions, worker
restrictions or source behavior were weakened. TEMP/TMP and all disposable state
were confined to `temp/`.

| Selection | Result |
| --- | --- |
| Pre-edit Task 7.14 baseline | **60 passed, 21.25 s** |
| Combined Task 7.15/7.14/7.13/7.10C/7.11, before the final transition-support refinement and three additional cases | **374 passed, 181.94 s**; includes the first 74 Task 7.15 cases and 300 unchanged cases |
| Final complete Task 7.15 suite, including the final refinement and all three additional cases | **77 passed, 30.29 s** |
| Milestone 6 attestation/dual review/admission; Milestone 5 eligibility/certificate/reputation; originality certificates, certificate blocks, v1 protocol/golden/native transfers; Task 3.7 concurrent certified minting | **201 passed, 66.77 s**, one existing JUnit `record_property` compatibility warning |

These selections cover **578 distinct passing cases**, with no skips or
failures: final 77 + unchanged 300 + historical 201. Intermediate/baseline cases
overlap and are not added again. The final refinement is confined to the new
history module; its complete 77-case suite was rerun after that change. No
full-repository, Linux or cross-platform test run is claimed.

Disposable reports: `temp/task715-final-canonical.xml`,
`temp/task715-final-focused.xml`, `temp/task715-final-historical.xml`.

Reproduce the focused combined selection from the repository root:

```powershell
New-Item -ItemType Directory -Force temp/task715-runtime | Out-Null
$env:TEMP=(Resolve-Path temp/task715-runtime).Path
$env:TMP=$env:TEMP
.\.venv\Scripts\python.exe -B -m pytest tests/test_milestone_7_task_7_15_history.py tests/test_milestone_7_task_7_14_issuance.py tests/test_milestone_7_task_7_13_admission.py tests/test_milestone_7_task_7_10c_v3.py tests/test_milestone_7_task_7_11_storage.py -q --tb=short --basetemp=temp/task715-canonical-recheck -p no:cacheprovider
```

The API-capable historical selection used:

```powershell
.\.venv\Scripts\python.exe -B -m pytest tests/test_milestone_6_task_6_4_submitter_attestation.py tests/test_milestone_6_task_6_5_dual_review.py tests/test_milestone_6_task_6_6_admission.py tests/test_milestone_5_task_5_5_earned_reviewer_eligibility.py tests/test_milestone_5_task_5_6_certificate_v3.py tests/test_milestone_5_task_5_7_reviewer_reputation.py tests/submissions/test_originality_certificate.py tests/blockchain/test_certificate_block_validation.py tests/test_protocol_v1.py tests/test_protocol_v1_golden_vectors.py tests/test_protocol_v1_native_transfers.py tests/integration/test_task_3_7_concurrent_certified_minting.py -q --tb=short --basetemp=temp/task715-historical-recheck -p no:cacheprovider
```

UTF-8, Python syntax, local documentation links, final newlines and whitespace
checks passed. The final branch/HEAD are unchanged. The only worktree changes
are the three new files listed above; no tracked source or fixture changed.

## Production blockers and review status

The isolated adapter and test contracts are reviewable; production activation
remains blocked by the approved real N/W/G/policy/statement context, complete
accepted v2 history/selection journal and its bounded freeze policy, future v2
participation/offense retention, and the final shared atomic transaction above.
There is no approved cross-launch reviewer-history migration or new trusted
history/signing authority. Missing prerequisites remain incomplete or rejected;
the adapter cannot manufacture them. Existing decoder/platform/independent
review and broader production integration gates also remain unchanged.

Active v1 code and historical readers are untouched and the selected historical
regressions pass. **Task 7.15's nonactivated integration boundary is ready for
review and a later authorized commit. Production activation is not ready.**
Task 7.15 does not authorize v2/v3 activation or the next task, and nothing is
staged or committed.
