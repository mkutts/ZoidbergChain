# Milestone 7 Task 7.17C — Current finality and reviewer-history dependency audit

**Task 7.17D follow-up (2026-10-24):** The
[finality safety and remediation decision](milestone-7-finality-safety-and-remediation-decision.md)
defines trust-model alternatives, exact quorum/fault bounds, proposed safety and
durable-signing contracts, local storage remedies, distributed-agreement gates
and a bounded implementation/test roadmap. It recommends an initially static,
independently operated permissioned BFT testnet for owner review; no model or
agreement protocol is adopted. Local durability repair is ready to scope in a
separate implementation task. Distributed finality and reviewer-history gates
remain **BLOCKED**; Task 7.17 is not resumed. The original audit and findings
below are preserved.

Date: 2026-10-23 (America/New_York). **Decision: BLOCKED for independent-node
reviewer-history implementation. Task 7.17 must not resume.** This is an audit
of implementation at the HEAD below, not a new agreement protocol. Existing
signature, media, certificate, storage and replay components are reusable;
neither their composition nor quorum arithmetic establishes distributed
agreement or complete reviewer history.

## 1. Repository verification, scope and evidence

- Branch: `Compression-State-Bloat-and-Node-Economics` (expected).
- HEAD: `d075cb2e8182bb410ace4a2f96165ab811752e20`.
- Initial worktree and index: clean. Task 7.17B is separately committed as
  `d075cb2`, following Task 7.17A `9894bb9`, Task 7.17 blocker report `9198709`,
  Task 7.16 `b3aa0b4` and Task 7.15 `4944aca`.
- Relevant finality history: `65ea1ab` introduced validator quorum finality;
  `01bae92` exposed its public status. Later Milestone 3 batching and Milestone
  4 atomic reorganization do not supply a validator agreement protocol.
- No applicable repository/ancestor `AGENTS.md` found. No delegation used.
- Deliverables are this document and
  [targeted current-behavior diagnostics](../tests/test_milestone_7_task_7_17c_finality_audit.py).
  No production code, previous specification, fixture, golden vector, dependency,
  signing schema or assertion in an existing test is changed. HEAD/branch/index
  stay unchanged. No commit, push, merge, activation, migration, reset, deployment
  or subsequent implementation task.
- Final worktree scope: the two new deliverables above only, unstaged/untracked;
  no tracked-file or staged changes. Task 7.17B remains exactly as committed.

Read the [7.17 blocker report](milestone-7-v2-history-freeze-and-recovery.md),
[7.17A decision](milestone-7-v2-reviewer-history-consensus-decision.md), and
[7.17B amendment](milestone-7-v2-reviewer-history-protocol-amendment.md), including
their admission, selection, finality, replay and approval gates. Relevant prior
context: [Milestone 3](milestone-3-release-readiness-report.md),
[Milestone 4](milestone-4-release-readiness-report.md),
[Milestone 5](milestone-5-release-readiness-report.md),
[Milestone 6](milestone-6-release-readiness-report.md),
[lifecycle/finality](protocol-v1-lifecycle-finality.md),
[primary v1 specification](protocol-v1.md),
[fixed reviewer quorum](milestone-5-task-5.6-fixed-quorum-reviewer-snapshot-and-certificate-v3.md),
[immutable-media contract](milestone-6-task-6.1-immutable-media-safety-spec.md),
[peer networking](peer-networking.md), and
[restart checklist](testnet-restart-recovery-checklist.md).
Source and tests take precedence over claims in these reports.

Two different implementations must be distinguished throughout:

1. **Active v1 protocol family**, including admission block version 2: selected
   chain in `Blockchain`, v1 finality attestations and the services below.
2. **Inert protocol-2 / block-3 laboratory**, `canonical_v3`: strict canonical
   formats, separately stored proofs, provisional candidate storage and trusted
   local-history certification. It has no active finality signer, network
   agreement service or authenticated reviewer-history implementation.

## 2. Findings ranked by severity

| ID / severity | Finding, primary evidence and consequence |
| --- | --- |
| F1 **Critical** | **No enforced signer-side agreement/non-equivocation/ancestry rule.** `FinalityService.process_attestation` counts valid signatures for the receiver's canonical target. There is no production signer call site, durable signing decision/lock, round, proposer election or safe revoting protocol. Independent nodes can finalize different branches if overlapping signers sign both; cross-height conflicts need not double-sign at the same height. Even a policy of signing only once per height can split votes permanently. Diagnostics `test_conflicting_quorums_with_one_equivocator_in_three`, `test_verifier_does_not_enforce_signer_side_non_equivocation`, `test_incompatible_cross_height_proofs_need_no_same_height_double_vote`, `test_split_first_votes_and_exact_retries_do_not_reach_quorum`. |
| F2 **Critical** | **Finality persistence is not monotonic across all writers.** `Blockchain.submit_validator_finality_attestations` copies/mutates facade state before `save_blockchain`; the latter replaces durable state without a finality revision/union/anchor check. Two simultaneous calls can lose a quorum vote; a stale facade can erase an already durable QC on BOTH JSON and SQLite. Reorg's stronger transaction does not protect against a later stale whole-document save. Diagnostics `test_concurrent_attestation_calls_can_lose_a_quorum_vote`, `test_stale_whole_document_save_erases_durable_finality`. |
| F3 **High** | **Failure before persistence can expose non-durable finality.** A failed save leaves mutated in-memory votes/finality. An exact duplicate retry takes the duplicate path and does not retry persistence. Diagnostics `test_failed_save_leaves_in_memory_finality_and_duplicate_retry_does_not_save`. A crash then loses that alleged finality; this is distinct from a lost acknowledgement AFTER a successful commit. |
| F4 **High** | **Historical validator authority is external and not reconstructed.** Active `validate_finalization_evidence` trusts the validator list inside the record; `_validate_persisted_finality_state` checks signatures/chain matches but never compares that list to an authenticated historical configuration. A proof using a disjoint one-member set passes that boundary under assumed authentic signatures. This is a trusted-local/import boundary, not a demonstrated unauthenticated remote proof-injection endpoint. The inert validator correctly requires external trusted validators, but its store cannot authenticate caller-supplied trust. |
| F5 **High** | **No finality-proof synchronization/reconciliation path.** `PeerChainSyncService.fetch_blocks` transfers blocks, originality certificates and originality evidence, not finality attestations/proofs or validator authority. Same-tip summary equality also stops ordinary chain fetch. Existing two-node finality tests supply attestations separately. A newly synced chain alone does not reconstruct finality or reviewer history. |
| F6 **High** | **Equivocation knowledge is incomplete and has different roles.** Active live counting discounts locally retained pairs; ordinary submission rejects a noncanonical conflict before retaining it, and reorg deletes detached votes. A previously retained QC stays valid. Inert `canonical_v3.finality.validate_proof` instead uses caller-supplied `equivocators`, so the SAME real published proof passes/fails under different such context. No authenticated completeness/cutoff authority supplies it. |
| F7 **High** | **Reviewer-history authority still missing.** Neither a valid finality signature nor a media certificate authenticates absent accepted-unminted votes, rejected proof observations, off-chain issuance ownership or local finding order. `canonical_v3.history._History._authenticate` uses trusted local timestamps; no chain event replay can recreate those facts today. |
| F8 **High** | **7.17B's finalized-parent/control-block lifecycle is not implemented and changes progress semantics.** Active acceptance can extend an unfinalized parent; a target can receive finality without a parent QC. Full 7.17B unminted-participation/penalty-clock guarantees cannot be obtained from the current media-only block lifecycle without an explicit scope/clock decision. |
| F9 **High** | **Preliminary REGISTER can make unreviewed full media permanent.** 7.17B permits full technical/rights-validated originals in history records before community originality/admissibility approval. No reward or media-mint label removes those immutable bytes. This is a separate hostile-content/admission-policy decision, not a harmless journal encoding change. Ordinary same-candidate media needs no preliminary copy; do not implement this optional route as a bypass of both review dimensions. |
| F10 **Medium** | **Draft exact-set selection can permanently strand media.** Sixteen early unsure votes in a dimension, including the mandatory established seat, can fill the selected cohort, with no decisive denominator even when later positive votes exist. Arbitrary favorable subsets remove protection against suppressing finalized negative votes; they are not an equivalent simplification. |
| F11 **Medium** | **Fork-choice/schema adapter absent.** Existing scoring sums numbers and rounds to eight places. The rational objects in block 3 are not valid inputs. 7.17B's exact score adapter, P4/C3/V4 and history/genesis manifests are specifications, not enforced paths. |
| F12 **Low** | **Documentation contradictions obscure the boundary.** `protocol-v1.md` section 16 still says depth 6 finalizes; the lifecycle document retains historical depth/genesis and reorg statements despite its Task 3.5 supersession. Current executable finality requires signatures, not depth. Reports of healthy test convergence do not establish adversarial agreement. Existing docs are left untouched by this audit. |

F1 is a missing consensus contract, F2/F3 are concrete implementation defects,
and F4/F5/F6/F7 are trust/availability/integration gaps. They must not be collapsed
into a demand for a particular branded BFT protocol.

## 3. Actual current finality state machine

### 3.1 Production, acceptance and finalization

```text
locally admitted signed reviews + validated original + creator rights
    -> frozen media certificate -> mint queue
    -> build candidate on current selected tip (no parent-QC requirement)
    -> validate media/certificate/ledger/rewards/hash/parent
    -> persist selected block and settlement (accepted)
    -> external delivery of validator attestations for selected height/hash
    -> validate signature/membership/network/target
    -> count unique locally non-equivocating signers
    -> first quorum creates separately persisted finality record
    -> local fork-choice/reorg checks protect retained finalized anchors
```

Unfinalized blocks may accumulate above a finalized head. Confirmation depth is
display metadata, not a finality transition. Any selected target, including
genesis or a tip with zero confirmations, may receive quorum finality. A QC for
a descendant protects its hash-linked ancestry against ordinary reorg, but does
not automatically create individual QC records or `finalized=true` for every
ancestor in the active API.

Primary implementation: [production](../services/block_production_service.py#L49)
`BlockProductionService.build_candidate`, [local validation](../services/block_validation_service.py#L298)
`validate_candidate`, [certified commit](../blockchain.py#L4408)
`commit_certified_submission`, [finality facade](../blockchain.py#L2798)
`submit_validator_finality_attestations`, and [counting service](../services/finality_service.py#L130)
`process_attestation`. `accept_block_candidate` also exists for direct/legacy
construction; the production certified path has its own stronger commit
boundary. These must not be confused with distributed validator agreement.

### 3.2 Fourteen implemented answers

| Question | Implemented answer and exact evidence |
| --- | --- |
| 1. Who may propose? | A caller with a valid certificate/media and allowed local mint operation can construct a candidate; `Blockchain.is_valid_public_key` accepts an Ethereum-form address or registered legacy wallet for the miner field. There is no consensus elected proposer or validator-membership requirement for a proposer and no producer signature on the block. `api_routers/content.py:mint_queued_submission`, `Blockchain.mint_submission_operation`, `commit_certified_submission`, `BlockProductionService.build_candidate`; service direct-candidate and lifecycle tests. Service access/authentication restrictions do not create an elected leader. |
| 2. Who may vote on finality? | Recovered Ethereum addresses in `Blockchain.validator_set`, distinct from reviewers and HMAC peer identities. `FinalityService.validate_attestation`; `test_attestation_rejects_unknown_bad_domain_bad_signature_and_noncanonical_target`. Review eligibility/reputation does not confer finality membership. |
| 3. How selected? | Controlled configuration `PUBLIC_TESTNET_V1_VALIDATOR_ADDRESSES`, or explicit constructor injection. Normalized, sorted and deduplicated; malformed settings reject. No on-chain election, membership transition, stake or authenticated historical registry. `config._parse_validator_addresses`, `Blockchain.__init__`, `normalize_validator_set`; configuration test. Default environment value is empty. |
| 4. Quorum? | `q=(2*N+2)//3=ceil(2*N/3)` unique counted signers. Empty set never finalizes despite computed q=0. No weights. `required_quorum`, `process_attestation`; seven parameterized quorum cases. |
| 5. Exact signed message? | `canonical_domain_bytes` JSON envelope with `domain`, `network_id`, `object_type`, `payload`, `protocol`, `protocol_version`. Payload exactly `attestation_version:1,validator_address,block_height,block_hash`; object type finality-attestation, protocol zoidbergchain/1, domain zoidbergchain/finality-attestation/v1. Ethereum EIP-191 personal_sign signs these UTF-8 message bytes, recovered by the established wallet helper. `protocol_v1_finality.build_protocol_v1_finality_attestation_message`, `protocol_v1.canonical_domain_bytes`, `FinalityService.validate_attestation`. |
| 6. Height/parent/round/network/protocol? | Height/hash explicitly signed, N and protocol/version/domain in envelope. Parent and full block content are transitively committed by the validated block hash. No round, step, validator-set ID, direct genesis hash, lock or finality-policy digest is signed. Distinct N per genesis root remains essential. Inert v2 keeps the same four payload concepts with v2 domain/context. |
| 7. Valid vote? | Exact nine-field shape, normalized member, supported version/domain/scheme, expected N, canonical matching message, recoverable signature matching address and normalized nonnegative height/hash. Facade additionally validates selected chain and target's stored hash, existence and exact canonical identity. It does not enforce what that signer previously signed elsewhere. |
| 8. Valid certificate? | **Finality QC:** eight fields, nonempty snapshotted set, recomputed q, matching N/domain/version, sufficient valid target signatures, deterministic unique signer order. Active verifier uses the proof's set, not trusted genesis membership. **Media certificate:** separate admission/signature/technical/tally validation; it is not a validator QC. `validate_finalization_evidence`, `admission_certificate.validate_admission_certificate`, `canonical_v3.evidence.validate_certificate`, `canonical_v3.finality.validate_proof`. |
| 9. Accepted versus finalized? | Acceptance selects/persists a valid block and its settlement; finalization separately retains first quorum evidence. Confirmation depth neither signs nor finalizes. `get_block_chain_state`, `FinalityService.block_chain_state`; public-status and depth-without-quorum tests. F2/F3 limit durability claims. |
| 10. Multiple candidates at height? | Yes, independently produced branches can compete. Active facade durably stores the selected chain, not a full side-branch pool; wrong-parent realtime receipt returns sync-needed. Inert `V3Store.candidates_at_height` and `select_chain` explicitly retain provisional alternatives, but are storage-only. |
| 11. Prevents conflicts? | Local existing-finalization check and reorg anchor preservation. Across nodes only a common authorized set, safe quorum intersection and an EXTERNAL honest nonconflicting signing discipline provide a conditional argument. No implemented global exclusion/lock guarantees it. F1/F2 are blockers. |
| 12. Disappearance? | No leader/round/failover state machine or automatic finality signer exists. Other callers can try building a media candidate; finality waits for q valid delivered attestations. Fewer than q available cannot finalize. q available is necessary, not sufficient for common-candidate progress. |
| 13. Conflicting votes? | `votes_for_block` groups retained valid records by validator/height and discounts a signer when more than one hash appears. No slashing or membership change. Normal facade refuses noncanonical conflict input; reorg drops detached attestations. The direct service equivocation test does not prove durable network-wide detection. |
| 14. Restart? | `load_blockchain`/`_restore_blockchain_state_document` restore votes/QCs and `_validate_persisted_finality_state` checks QC signatures, duplicate heights and chain equality. It does not reconstruct signing decisions or trusted historical membership, recompute missing QCs from a lone vote list, fetch missing proofs or recover absent off-chain history. `test_quorum_finality_is_authoritative_durable_and_idempotent`, public-status reload tests cover a successfully retained local checkpoint. |

### 3.3 Implemented versus specified versus missing

| Class | Reusable or unresolved rules |
| --- | --- |
| **A: implemented and tested** | Canonical signed-target validation; unique counted signers; q calculation and no empty-set finality; local first QC; extra post-quorum votes retain one QC; serialized successful restart/idempotency; local finalized-anchor reorg rejection; validated originality/height/hash fork choice; inert strict schemas, exact rational tallies, bounded records, proof validation with explicit trust inputs, branch storage/CAS and immutable proof retention. Scope limitations above apply. |
| **B: specified but not enforced** | Nondecreasing durable finality across ALL save paths; complete durable equivocation evidence; 7.17B genesis authority, self-contained proof counting, contradictory-QC halt, immediate finalized-parent gate, event extraction/replay, parent-owned scratch state, exact cohort and rational fork choice. The older depth-finality text is obsolete, not an additional accepted rule. |
| **C: missing for independent-node consensus** | Durable safe signer behavior, agreed candidate/failover/progress contract, consistently authenticated validator policy/history, finality synchronization independent of chain score/tip changes, cross-writer atomic monotonic finality, authenticated complete reviewer inputs and independent source-only replay. |
| **D: simplifiable proposals** | Mandatory separate preliminary media, duplicated implicit event bytes, separate discretionary reviewer findings, mandatory SMT/full-state root, unconditional off-chain ISSUE authority, separate validator penalty journal when membership never changes, and redundant replay/input digests if their intended guarantees are already supplied by authenticated canonical replay. See section 8; semantics cannot be removed silently. |

## 4. Trust assumptions and safety argument

For a conditional SAME-HEIGHT safety argument assume: unforgeable signatures and
collision-resistant block hashes; all nodes use the same externally authorized
static validator set and N/root/policy; every honest signer permanently refuses
conflicting height decisions across branches/restarts; and no stale writer loses
the decisions/anchors required by that discipline. Two size-q signer sets
intersect in at least `I=2*q-N`. If `b<I` signers can equivocate, both conflicting
QCs would require at least one honest signer to violate that discipline. This
proves conditional certificate exclusion, not that the implementation enforces
those assumptions or that nodes will make progress. Cross-height ancestry safety
also requires honest signing decisions to preserve finalized ancestry; a
same-height-only slogan is insufficient for an arbitrary gapped QC history.

| N | q | Minimum intersection | Maximum equivocators for this arithmetic safety bound |
| ---: | ---: | ---: | ---: |
| 1 | 1 | 1 | 0 |
| 2 | 2 | 2 | 1 (but one absent already stops progress) |
| 3 | 2 | 1 | 0 |
| 4 | 3 | 2 | 1 |
| 5 | 4 | 3 | 2 (progress separately needs four available) |
| 6 | 4 | 2 | 1 |

In particular, the older documentation's assumption that at least a quorum of
keys is honest is NOT sufficient generally: with N=3/q=2, honest A signs X,
honest C signs Y, and Byzantine B signs both. A+B and B+C separately form QCs.
Each node can have an honest quorum in the configured set, yet finalize a
different valid block when given different evidence. The structural diagnostic
executes the real receiver/counting logic under authentic-signature assumptions;
it does not claim a new real-signature two-node attack transcript.

There is also a cross-height hole even if nobody signs twice at one height:
A+B sign X at height 1, its QC is withheld, and B+C sign height 2 on another
valid branch `genesis -> Y@1 -> Z@2`. Both receivers can form QCs; the shared
signer B signed different heights, so same-height equivocation detection finds
nothing. The diagnostic `test_incompatible_cross_height_proofs_need_no_same_height_double_vote`
verifies both current proof/counting paths and that Z's branch would fail an
X-aware node's anchor check, assuming independently valid branch targets. It
does not claim a new real-media fork transcript. Preventing this requires
persistent safe ancestry decisions or an approved finalized-parent contract in
addition to same-height intersection; "sign once per height" alone is not a
sufficient active-protocol safety rule, even with no malicious keys.

Under externally coordinated trusted administration that selects one immutable
branch and prevents key reuse for conflicts, current receivers can authenticate
its decisions. That is a meaningful controlled-testnet trust model, not an
independent-node agreement guarantee. Honest operators merely signing their
changing local canonical tip is not equivalent. No unstated eventual synchrony
can replace a signing contract; a partition can preserve different candidate
views indefinitely, and healing does not by itself release a one-vote lock.

### 4.1 Adversarial scenarios

| Scenario | Current outcome / boundary |
| --- | --- |
| Conflicting blocks at one height; different candidate sets | Both can be valid before a QC. Different nodes can select different branches. Receiver validates only its selected target, not global candidate completeness. Conditional intersection argument applies only with the honest signer discipline above. |
| Double-signing / overlapping QCs | Signatures verify independently. Hidden second statements are not visible locally. Revealing them can reduce a live count but cannot revoke a retained active QC; no global contradiction protocol or full proof relay exists. F1/F6. |
| Stale/disjoint validator sets | Live receipt uses current local configuration; restart proof checks its embedded set. Changing configuration has no authenticated epoch/height transition. Different sets can authorize incompatible outcomes even if each is internally honest. F4. |
| Conflicting parents | Hash validation binds each block to its parent, and local extension rejects wrong parent. This prevents changing a signed block's ancestry without changing its hash. It does not prohibit signatures for two different valid parent-linked branches. |
| Reorg near finality | `compare_chains_by_originality`, durable recheck in `adopt_canonical_chain` and `CanonicalReorgService._reconcile_finality` reject detaching any retained finalized target. Reorg above it is permitted; orphan ledger/reward/claims are rebuilt. A later stale save can defeat retention, so this property is local to guarded paths. |
| Crash after acceptance, before finality | A successfully committed block survives as accepted, without invented finality. It needs supplied votes/proof after restart. No extra media is required merely to attest that block. |
| Crash/save failure during finality | Successful checkpoint reload is tested. Pre-save memory mutation and duplicate retry are unsafe under F3; F2 can erase even previously successful finality. No end-to-end finality crash-atomicity guarantee follows from atomic file replacement/SQLite alone. |
| Concurrent finality attempts | Two calls can both copy the empty vote pool and each count one vote, then overwrite each other. Two facade snapshots can overwrite durable QC state. The diagnostic imposes that deterministic interleaving; no load/performance claim is made. |
| Invalid certificate propagation | Invalid signatures/target/network/signer count reject at the respective validator; HMAC peer transport does not confer validator authority. Active sync lacks a QC-import path, so there is no tested remote finality-certificate ingress guarantee to attribute to it. The v2 primitive rejects the unchanged fixture with bad signature or wrong external set. |
| Network partition | Neither side with fewer than q signatures progresses. With missing signing discipline or beyond the exact fault bound, conflicting QCs are possible. Safe signing without coordinated candidate choice can instead strand both sides. |
| New node verifying history | Can validate hash-linked media/ledger and separately supplied properly trusted proofs. Ordinary chain sync does not deliver those proofs, reconstruct validator authority or authenticate missing reviewer events. A copied trusted backup is a different recovery model. |

## 5. Fork choice and liveness

[ForkChoiceService](../services/fork_choice_service.py#L15) skips genesis and
sums originality numbers, rounding the sum to eight decimal places. Comparison
uses higher score, then higher tip height, then lexicographically lower tip hash.
Same tip is equivalent. Different genesis or invalid full candidate rejects.
`Blockchain.compare_chains_by_originality` adds local finalized-anchor protection;
`adopt_canonical_chain` repeats score and finality checks against locked durable
state before rebuilding and atomically publishing. The standalone scoring
service and a summary comparison alone do not check finality.

[PeerChainSyncService.sync_peer](../services/peer_chain_sync_service.py) first
compares advertised summaries, fetches a preferred full candidate, validates it,
recomputes comparison and adopts through the facade. The advert is not proof.
No QC weight overrides conflicting finality. With different finalized anchors,
two nodes may each reject the other's chain, even if one has a better score.
Finalized conflict resolution is not ordinary fork choice.

The rational `originality_score` in the inert schema cannot be passed directly
to this number-summing service. An exact version-scoped adapter is justified;
7.17B's `lcm(1..16)=720720` score units are one specified compatible ordering
for bounded denominators. This audit neither implements nor activates it.

| Progress situation | Actual guarantee / exact stall condition |
| --- | --- |
| Missing/delayed proposal | No producer schedule or protocol timeout. Another local caller can propose a ready certified submission, but eventual production is an operational assumption. No new certificate/media, invalid admission, exhausted reward resources or no caller means no new media block. |
| Missing validators / stalled quorum | Finality requires q delivered valid signatures for the same canonical target. No production service automatically creates/gossips them; existing callers are tests/benchmarks. Empty validator configuration and fewer than q available stop finality. |
| Competing candidates | Fork choice converges for the SAME fully available candidate set. It does not guarantee that set becomes common before signatures, nor authorize safe revoting after a better candidate appears. N=4/q=3 split 2+2 stalls under permanent one-shot signing. Replaying the same vote does not repair it. |
| Parent finality advances while certifying | Active production extends current selected tip without pinning its immediate parent QC. Reviewer certificates may bind an earlier finalized reference. There is no implemented 7.17B scratch-replay/rebuild rule when its required F changes. Inert local snapshot/head CAS can detect stale local authority, but does not define cross-node replacement. |
| Repeated proposals / retry | Certified commit's head CAS, identity replay and `commit_next_certified_submission_with_retry` handle local stale-head/SQLite contention with bounded retries (default 200 plus initial attempt, backoff capped at .032 s). This is not a consensus round timeout. No finality round-change/reproposal mechanism exists. |
| Are rounds/locks necessary? | A trusted coordinator and sign-once discipline can support a narrower conditional model without a named multi-round protocol. With independent competing candidates, disappearing coordinators and fault tolerance as requirements, some reviewed safe decision/retry/failover contract is necessary. Merely adding a round number or a lock can introduce deadlock; this audit specifies neither. Existing one-step final signatures provide no demonstrated safe unlock rule. |
| No new media | Validators can finalize an EXISTING accepted tip or genesis without a new block. Once pending targets are finalized, no more heights/epochs arise without another valid media block. Native transactions are carried by media blocks; no active empty/history/control block exists. Distinguish existing-target finality from growth of the reviewer clock. |
| Reviewer cooldown/quota/all-unsure | Epoch is finalized height divided by five. If no eligible two-dimensional media quorum can produce the next media block, the block clock may not advance to quota rollover/penalty expiry. All-unsure provides voices but zero decisive denominator. An immutable all-unsure selected cohort can remain unresolved permanently. |

There is no unconditional progress bound, fairness guarantee or censorship-free
offered pool. Healthy ordered-mint benchmarks and reversed-attestation tests
establish their controlled delivery cases only. 7.17B's immediate finalized
parent would also remove today's ability to continue accepting a deeper
unfinalized media suffix; approving it is a material availability decision.

## 6. Existing certificate, persistence and replay guarantees

- [Admission certificate](../admission_certificate.py#L165) validation binds
  original media identity, creator rights, technical evidence and both review
  dimensions. The canonical inert evidence format also verifies exact bytes,
  signature/context duplicates, derived tally/ratio and certificate digest.
  Five eligible voices, at least one established reviewer and integer 70%
  approval with a positive decisive denominator remain mandatory PER dimension.
  Unsure counts toward voices/participation, not the decisive denominator.
- Certificate selected records authenticate signed choices and the supplied
  bounded evidence. Eligibility/status metadata still require independently
  authenticated historical state; signed records do not prove receipt time,
  consensus acceptance, absence of omitted records or runtime policy history.
- Active `ReviewerEligibilityService.finalized_context`, `qualification` and
  `status_at_reference` derive chain activity and historical rules; probation
  participation, quotas and penalties also use application storage. The phrase
  "solely finalized ancestry" in a class description does not authenticate
  those external accepted-vote/finding inventories.
- [History reader](../canonical_v3/history.py#L95) explicitly opens an EXISTING
  trusted SQLite database read-only. `FrozenReviewJournal` is a port with no
  active consensus implementation. `_History._authenticate` merges local
  observed/recorded times; equal chain bytes do not constrain those local rows.
- [Atomic certification](../canonical_v3/atomic.py#L56) retains a trusted local
  image and permanent issuance claims, with transactional revalidation,
  snapshots and branch-specific selected claims. It cannot make off-chain
  reservations globally authoritative. Tests of shared-store concurrency,
  restart and backup prove local atomicity, not independent event agreement.
- [V3Store](../canonical_v3/storage.py#L348) has useful immutable source/proof
  records, caller-selected branch CAS, contiguous lineage checks, transactional
  finality retention and rebuildable indexes. `finalize` takes authenticated
  validator/equivocator context from its caller; retained context is not a
  genesis authorization protocol. These are reusable primitives with an
  explicit missing authority integration.
- `storage_tools` portable snapshots retain finality sections, unlike ordinary
  peer block sync. Milestone 5 export/import tests can preserve a trusted
  application image. They do not prove an arbitrary peer's historical validator
  set or recover events never committed to the chain.

## 7. Reviewer-history dependencies and the 7.17B timeline

| Required fact | What exists / what consensus must additionally authenticate |
| --- | --- |
| Reviewer bootstrap | Existing immutable reviewer policy has empty grants; finalized creator/native activity is reusable. A nonempty launch snapshot and its policy/set authority must be in approved genesis/release inputs. Finality cannot authorize its own trust root. Reviewer grants and validator roles remain separate. |
| Signed vote inventory | Existing signatures authenticate offered choices. Retain selected votes already present in certificates; additional included accepted-unminted and rejected/stale proof observations need canonical source bytes/order. No signature proves a complete global off-chain inventory. |
| State transitions | Qualification/schedules/quota formulas can be reused after source authority is established. Local labels/clocks/receipt flags cannot choose transition order. Same parent and same full candidate must yield identical transitions. |
| Certificate issuance | An embedded media certificate authenticates its issuance on that finalized path. Independent issued-but-unminted permanence requires an included canonical ISSUE; a service returning a draft cannot consume global ownership. |
| Penalty evidence | Objective signed conflicts/self-votes and authenticated acceptance/quota sources can derive prospective penalties. Local administrator findings and subjective originality accusations are not automatically consensus-authorized. Current offense verifier's protocol-v1 restriction cannot silently accept new V4. |
| Epoch quotas | Need deterministic accepted participation inventory, including unminted targets if preserving that rule, and finalized height semantics. Counting selected media certificates alone omits some current participation. Two dimensions of one submission/epoch count once. |
| Replay commitments | Exact canonical source chain, fixed genesis/policy and deterministic replay are fundamental. A hash of a local SQLite image or producer-supplied state is not authority. A separate rolling journal digest can be useful for comparison but is not a substitute for source validation. |

### 7.1 Eight required lifecycle checks

1. **Finalized-parent cutoff.** 7.17B fixes F to immediate h-1 and requires its
   proof (genesis exception). Current code requires a selected parent, not that
   QC, and permits finality gaps. Adopting F is a new acceptance/eligibility
   contract, not reuse of `get_finalized_head()` as a moving local oracle.
2. **Same-candidate signed votes.** Independently signed rights/media/V4 can
   be checked against parent state before finality, then accepted on scratch
   state and certified in the same block. This is noncircular: signed sources
   and parent -> vote outcomes -> C3 -> block hash -> QC. Existing production
   already certifies before block finality, but has no canonical new-event
   extraction or scratch transition replay. Its signatures are not V4.
3. **Complete offered pool.** Verify all authoritative parent receipts plus all
   candidate-offered observations, implicit and explicit, if retaining exact-set
   selection. This does NOT mean every private signature worldwide. Parent and
   candidate bytes must fix the relevant inventory; different producers may
   still offer different unpublished subsets and hence different valid proposals.
4. **All-unsure.** Zero decisive denominator prevents ISSUE/media approval;
   five/16 unsure voices do not bypass originality OR admissibility. Under
   7.17B's earliest established plus fifteen cohort, a saturated unsure set may
   lock that submission even after later decisive input. A control record could
   retain observations/advance a clock, but cannot manufacture media approval.
5. **Evidence subset.** Selected evidence can be independently checked for
   signature/tally/eligibility using trusted historical state. Exact equality
   to the policy-selected set needs the authenticated candidate inventory too.
   Allowing any favorable 5..16 subset is a policy change that can suppress
   finalized negatives; reject it as a semantics-preserving shortcut.
6. **Candidate replacement.** Once F changes, a draft C3 cannot be reparented
   unchanged. Revalidate/regenerate against the new state; unaccepted V4 inputs
   pinned to old F need fresh signatures under the proposal, while already
   accepted historical receipts keep their acceptance context. A finalized
   ISSUE remains fixed. No implementation of this behavior is claimed here,
   and this audit creates no new signatures.
7. **Event completeness.** Extract REGISTER/VOTE/ISSUE once from media and
   certificate fields; retain extra sources only when not already represented.
   Replay all included events and mandatory outputs. Neither finality nor a
   root proves the producer disclosed private votes; they authenticate the
   selected branch and its included complete byte sequence.
8. **Fresh recovery.** Needs pinned genesis/grants/validator policy, source
   blocks, all required separate proofs and exact deterministic replay. Source
   absence is incomplete, never zero offenses/unused quota. Current chain sync,
   local image backup and the unimplemented journal port do not meet this.

The abstract 7.17B admission dependency graph is coherent; implementing it on
today's lifecycle unchanged is not. In particular, adding a history reader
without fixing finality authority/durability would authenticate divergent local
decisions or accept unbacked snapshots.

## 8. Minimum journal and protocol simplifications

These are recommendations for a later specification revision. Task 7.17B is
unchanged. Each removal below is conditional on keeping the stated semantics.

| Structure / proposal | Minimum justified disposition |
| --- | --- |
| REGISTER / VOTE / ISSUE as three stored commands everywhere | They are three useful logical transition kinds, not three mandatory new copies per media. Existing canonical media/rights/technical/certificate fields can be their source. 7.17B already recognizes implicit extraction; retain that simplification. No extra event signer or journal administrator is needed. |
| Preliminary media before every certificate | Unnecessary for ordinary same-candidate admission. Keep the complete original exactly in its media block, verify rights/technical policy and both quorums there. Preliminary REGISTER is needed only when deliberately granting authoritative participation to a still-unminted target; that requires full validated original availability and has immutable-content costs. A hash/URL does not establish admissibility. |
| All off-chain issuance as permanent ownership | Remove that authority claim; off-chain certificates are drafts. Embedded finalized media already yields ISSUE ownership. Explicit ISSUE is needed only if the approved policy insists that issued-but-unminted certificates independently acquire permanent claims. Removing that feature is a separately disclosed semantic simplification. |
| Selected certificate history alone | Sufficient for its own signed evidence and media settlement, with replayed eligibility. Insufficient to preserve unminted participation/promotion, quotas, rejected misconduct sources or independent unminted issuance. Either commit those extra facts or explicitly narrow the policy; do not fabricate them from selected certificates. |
| Global offered-pool log | No need to prove the existence of never-included private input. Full canonical parent receipts and candidate sources suffice for exact-set policy. A signed selection alone cannot prove that finalized unfavorable receipts were included correctly. |
| Local challenges, allowlists, daily clocks and manual service restrictions | They can remain relay/service controls rather than new consensus event families only if that scope is explicitly approved. Signed nonce/context/inclusion intervals and canonical epoch quotas still apply. If global enforcement is required, its historical policy/time/acceptance authority must actually be authenticated; local challenge-cache entries cannot supply it. |
| Mandatory SMT, materialized full snapshots or a second journal authority | Unnecessary for archival replay. One trusted genesis snapshot plus deterministic replay of canonical source events is sufficient to derive state, provided finality is sound and the needed events actually exist. Indexes/local verified checkpoints are caches. Light-client state proofs would be a separate need. |
| Rolling replay root and selection_input_digest | Already hash-covered full parent/candidate sources and deterministic policy fix both state and offered input. These separate digests are not additional safety authority and may be diagnostic/redundant in a full archival profile. If retained as explicit versioned comparison commitments, use only the minimum agreed digest; do not also require full-state hashes/Merkle state. Removing draft C3/history fields requires a coherent new specification/vector review, not silent omission. |
| Explicit reviewer OFFENSE/penalty commands | For the specified objective five families, derive incidents/schedules from authenticated signed observations and quota history. No separate subjective finding authority is needed. Do not equate objective equivocation with proof that someone's content opinion was false. |
| Validator misconduct events | Not reviewer offenses. With fixed membership and no discipline, proofs need not depend on a global validator-offense event journal. Retain conflicts as safety diagnostics. If membership/exclusion/slashing is introduced, it needs separate prospective consensus authority; reviewer journals cannot implicitly provide it. |
| History/control/empty blocks | NOT a minimum consequence of adding commitments. They are a new block kind with pacing, epoch-age, reward/incentive, spam and one-media-per-block implications. Under a strict every-block-is-media interpretation they are unavailable. Under full unminted-participation and block-clock recovery requirements, the proposal must separately justify/approve an escape from media-quorum deadlock. Do not fake media or bypass its two-dimensional review. |

Model A permanence and originality/admissibility protection remain fixed. No
simplification permits replacing original bytes, disregarding required negative
votes, expiring a finalized certificate retroactively or letting validator
signatures substitute for community media approval.

In particular, optional preliminary REGISTER is not automatically safe merely
because it has no reward. Under 7.17B it can place the full original permanently
on chain before community admissibility review, including originals that never
qualify for a media certificate. Technical validity and creator rights do not
prove that community admissibility/originality has approved those bytes. That
route needs an explicit reconciliation with Milestone 6's before-permanence
protection and the one-media-per-block requirement. Excluding it from a minimum
profile may require explicitly deferring unminted participation credit and
revisiting its promotion/recovery assumptions; that is a policy change, not a
silent implementation shortcut. A hash-only REGISTER cannot claim equivalent
full-original validation/availability. No preliminary-media route is authorized
by this audit.

## 9. Architectural alternatives grounded in the implementation

| Dimension | A. Preserve finality, bounded history commitments | B. Minimum repair/strengthening of existing finality | C. Separately versioned agreement protocol |
| --- | --- | --- | --- |
| Required code | Add canonical extra sources/replay/bootstrap and source sync around reusable media/certificates. Keeping finality literally unchanged retains F1-F6; therefore usable only as a narrowly trusted laboratory, not this objective's safe independent-node implementation. | Repair atomic monotonic finality/signing persistence; pin historical validator authority; supply finality-proof sync/conflict handling; specify then implement safe signing/decision/retry behavior for actual concurrency/fault goals. Add minimum source/replay and rational fork-choice integration. | Replace agreement/validator messaging and integrate signer state, proofs, storage, sync, fault testing and recovery. Reuse validated media, ledger and reviewer replay where possible. Only justified if a separately reviewed minimum B contract cannot meet the desired fault/progress model cleanly. |
| Hash/signature schema | History sources in a closed new block/certificate schema change hashes. Existing finality height/hash signature transitively authenticates them. No new certificate signer required. Direct signed vote reference/G/creator requires V4 if those semantics retained. | Storage fixes and trusted-set comparison need no new signing fields. Review whether the approved agreement contract can use existing signed targets; if additional signed context is required, version it explicitly. This audit invents none. Self-contained counting/policy must be distinguished from old context semantics. | New protocol/message/proof versions and domain separation would likely be needed, determined by its reviewed specification. No detailed rules designed here. |
| Compatibility/reset | Cannot insert roots/events into closed block 3/C2/V3 bytes unchanged. Inert new profile may coexist as a separate laboratory; no automatic legacy-state import. Reset/launch disposition remains separate. | Keep v1 behavior historical; repair local durability separately from new consensus semantics. New profile genesis can pin policies. No automatic reset is required by this audit, but adoption/old-state treatment needs a later authorized plan. | Explicit old/new chain and activation/reset/state policy, broad compatibility review. No reset assumed or performed. |
| Safety assumptions | Common trusted administration, one immutable signing branch, matching validator configuration; current durability defects remain if literally preserved. Cannot claim independent-node safety. | Common authenticated fixed set and exact fault bound, persisted honest signer discipline and safe ancestry decisions, sound atomic state/replay. Requires proof against the specified adversary before making a BFT claim. | Depends on chosen protocol's proved fault/model assumptions AND faithful implementation; naming an established protocol is not proof. |
| Liveness assumptions | Coordinated q signatures and approved media; no automatic failover. No guarantee when reviewers cannot produce media. | At least q available plus reviewed candidate agreement/retry assumptions and source availability; media/clock limits explicitly retained or separately resolved. | Protocol-specific synchrony/availability/proposer assumptions plus unchanged media-admission dependencies. A rewrite cannot force positive community votes. |
| Verification effort | Moderate replay/schema work, but cannot validate away existing finality gaps. | Targeted persistence/concurrency/restart fixes, signed adversarial agreement transcripts, partitions/recovery, source-only independent DB replay and regression checks. Substantial but bounded to identified gaps. | Highest: new protocol conformance/safety/liveness and operational recovery plus all B integration tests. |
| Reproducibility | Same authenticated chosen prefix can replay deterministically after implementation; choosing/learning that prefix remains externally trusted. | Achievable only after validator authority/proof sync and exact event replay are implemented/tested on independent nodes. Not established today. | Must be demonstrated anew across independent implementations/nodes. |
| Fork risk / Milestone 7 impact | High if misrepresented as trustless, or new history accepted under old closed schemas. Narrow data changes alone do not unblock 7.17. | Changes must be version-scoped with explicit policy/genesis; minimum credible prerequisite before resuming 7.17. Separate active-v1 repairs from inert history integration. | Broadest fork/migration risk and scope expansion; separate milestone/protocol decision, not automatic continuation of Milestone 7. |

**Recommend B as the next specification direction, not a consensus rewrite.**
First specify the intended controlled-versus-independent trust/fault/progress
contract and remove redundant history structures. Then separately authorize
targeted production defect repairs and inert implementation. A may remain a
trusted prototype; it does not pass this independent-node audit. C is a reserve
option if the reviewed B contract proves inadequate; no such impossibility or
need for Tendermint/HotStuff has been established here.

## 10. Minimum changes and versioning gates

Required before independent reviewer-history consensus:

1. Establish one authenticated validator-set/policy origin and historical
   interpretation. Explicitly state N/q/fault assumptions; do not rely on the
   proof's self-declared membership or “quorum honest” alone.
2. Make vote/finality acceptance a locked durable read/validate/merge/write
   operation tied to canonical ancestry, monotonic against every stale writer.
   Publish finality after commit; rollback/reload after errors and make duplicate
   retries verify durable state. Persist signer safety decisions independently
   of disposable branch vote projections if a signer is introduced.
3. Specify safe signer/ancestry decision and progress/failover requirements for
   competing candidates and partitions. No new round, signature, key, timeout
   or lock rule is invented by this audit. Test conflicting decisions and
   split-vote recovery against that contract before claiming consensus safety.
4. Synchronize verified finality proofs and their trusted authority independently
   of preferred chain-score/same-tip gating. Handle a contradictory valid QC as
   a surfaced safety failure, not a routine reorg or locally discounted proof.
   Prefer self-contained fixed-set proof validation over an unauthenticated
   global exclusion inventory, subject to explicit policy approval.
5. Approve the minimum reviewer bootstrap/source/acceptance/selection/penalty
   contract, canonical ordering, inclusion-time semantics and candidate-owned
   claims. Commit only facts not already available in media/certificates and
   required by retained unminted/rejected-event semantics. Verify exact replay
   from genesis in independent fresh databases.
6. Decide immediate finalized-parent versus another explicitly bounded cursor
   lifecycle; decide whether one-media-per-block is strict for ALL blocks and
   accept its clock/liveness limits or separately review an alternative. Do not
   bundle new history-block incentives/pacing into a “small commitment” change.
7. Review closed schema/hash/policy versions, exact rational fork-choice and
   bounded proof/event transport, then independently authored vectors and full
   adversarial integration. Existing byte vectors remain immutable.

Version consequences are selective. Atomic persistence fixes, finality proof
transport and checking against an already authorized fixed set do not inherently
require changing signed payloads. New block/history fields do change the hash
preimage and require a distinct block profile (7.17B proposes block 4). Changed
C2 content requires a distinct certificate contract; fresh direct G/reference/
creator binding needs V4 signatures, not relabeling old V3. Review/reviewer/
reputation policy IDs must change when acceptance/selection/penalty meaning
changes. Event/bootstrap/history manifests begin at 1 if introduced; refining
unimplemented drafts does not require endless increments. No evidence requires
an additional protocol-family v3, new native signature version, creator-rights
version or finality signature version merely to hash history. A consensus
semantic change still needs an explicit approved policy/profile even if its
signature bytes are preserved. Network identity must not be reused across roots
whose rights/finality signatures lack direct G binding. No launch values,
migration/reset plan or activation is selected here.

## 11. Focused verification record

All diagnostics execute current production functions. New structural diagnostics
use synthetic chain targets and replace signature recovery with an explicit
authentic-vote assumption; full media/chain checks are stubbed only in the small
facade harness. They generate NO new keys or signatures. Thus they isolate
counting/control-flow/storage behavior, not an end-to-end cryptographic attack
or a hypothetical future protocol. Two diagnostic cases use the existing signed
v2 finality fixture and real recovery unchanged. Existing regression tests retain
their own original test signing setup.

The new diagnostic suite: **17 passed in 1.89 s**, no failures/errors/skips.
It covers conflicting overlapping and cross-height QCs, unrestricted signer inputs, split votes,
local exclusion versus retained proof, proof-contained validator authority,
post-quorum single-record preservation (batch and individual), no parent-QC
requirement, detached vote deletion, stale-save finality loss on JSON/SQLite,
failed-save duplicate retry, deterministic concurrent vote loss, peer omission
of supplied finality material, real v2 external-equivocator dependence and real
v2 rejection of wrong signature/trusted set.

The initial diagnostic hypothesis that a third new validator vote duplicates a
finality record was DISPROVED (two initial diagnostic assertions failed). Source
inspection confirms `process_attestation` creates new finalization only when
`locked is None`. The retained diagnostic positively verifies one record after
all three votes. No duplicate-QC defect is claimed and no existing assertion was
weakened.

Completed existing selections:

| Selection | Result | Pytest elapsed / retained JUnit |
| --- | --- | --- |
| `tests/blockchain/test_task_3_5_validator_quorum_finality.py`, `test_task_3_6_public_finality_status.py`, `test_protocol_v1_lifecycle_finality.py`; `tests/services/test_task_9_consensus_services.py`, `test_task_4_7_canonical_reorg_recovery.py`; `tests/integration/test_task_4_7_atomic_reorg_recovery.py`, `test_two_node_consensus_verification.py` | **52 passed**, no failures/errors/skips | 30.44 s; `temp/task717c-core-final.xml` |
| `tests/api/test_chain_sync_api.py`, `test_peer_block_sync_api.py`, `test_peer_certificate_sync_api.py`; `tests/blockchain/test_certificate_block_validation.py` | **65 passed**, no failures/errors/skips | 55.46 s; `temp/task717c-peer-final.xml` |
| `tests/test_protocol_v1_golden_vectors.py`, `test_protocol_v1_freeze_consistency.py`, `test_milestone_7_task_7_10c_v3.py`, `test_milestone_7_task_7_15_history.py`, `test_milestone_7_task_7_16_atomic.py` | **254 passed, 4 skipped**, no failures/errors | 948.16 s; `temp/task717c-canonical.xml` |
| New Task 7.17C current-behavior diagnostics | **17 passed**, no failures/errors/skips | 1.89 s; `temp/task717c-diagnostics.xml` |

The selections cover active finality/signatures/status, production lifecycle,
fork choice, reorg/recovery, peer chain/block/certificate validation, v1
golden/freeze vectors, inert canonical schemas/proofs and trusted local
history/atomic certification. Each abbreviated file in a row uses its preceding
directory. These are current implementation tests, not implementation of 7.17B.

Final distinct results: **371 existing regression passes + 17 new diagnostic
passes = 388 passed, 4 skipped**, no final failures/errors. The four skips are
the existing optional WAL process-termination cases in Task 7.16, guarded because
this Python SQLite runtime is 3.49.1 and lacks the required WAL-reset fix. They
are not counted as successful WAL crash verification. The existing DELETE-mode
process-termination/recovery cases pass. Pytest elapsed above is the console
duration; JUnit suite times exclude some reporting overhead.

Reproduction in the Windows project environment:

```powershell
New-Item -ItemType Directory -Path temp/task717c-runtime -Force | Out-Null
$env:TEMP=(Resolve-Path temp/task717c-runtime).Path
$env:TMP=$env:TEMP
.\.venv\Scripts\python.exe -m pytest tests/test_milestone_7_task_7_17c_finality_audit.py --basetemp=temp/task717c-diagnostic-data-durable -q
```

Disposable JUnit/log/runtime evidence stays under ignored `temp/task717c-*`.
No live chain/database is opened. An initial broader run using the sandbox
default temp root was interrupted without a completed result; a bounded core
run showed **43 passed / 4 failed in 5.33 s**, all four failures caused by the
existing image worker receiving Windows `PermissionError` for its sandbox temp
directory. All previously failing core cases were rerun in the completed
52-test group with workspace TEMP/TMP and a workspace pytest base directory.
The corrected combined run and the first
separate peer run were interrupted when TestClient stalled before application
code. A single-test faulthandler diagnostic localized the stall to Windows
`socket._fallback_socketpair -> accept` during asyncio loop initialization.
The API/peer group then completed outside the sandbox, retaining workspace
TEMP/TMP and pytest base directories. No automatic approval review rejection
occurred. These are environment corrections, not a media-validation bypass or
a finality assertion change; interrupted runs have no claimed final pass count.

No full-suite, Linux, deployed-node, new-profile, actual Byzantine-validator
network, performance, protocol-agreement proof or independent reviewer-history
interoperability result is claimed. Passing current-behavior defect diagnostics
does NOT make their reproduced failures safe.

## 12. Decision and next task

**BLOCKED. Task 7.17 cannot safely resume.** This audit and its focused
verification are complete; the proposed reviewer-history implementation
remains blocked by F1-F9 and explicit policy decisions. Approval of 7.17B alone
would not repair actual finality persistence or provide agreement/proof sync.

Recommended next authorized task: a bounded **finality trust, durability and
progress specification**, with a minimal reviewer-history profile decision.
Resolve the fault/quorum model, signer persistence/ancestry and concurrent-writer
contract, independently verifiable historical proofs/conflicts, candidate
progress and media-only clock limits. State which 7.17B features are required
versus optional, retaining original/admissible media protection. Produce concrete
acceptance tests/specification first; separately authorize active persistence
repairs and inert protocol implementation afterward. Do not resume history
freeze/recovery code by inventing authority callbacks, new signatures/keys,
administrative finality overrides or unreviewed consensus rules.
