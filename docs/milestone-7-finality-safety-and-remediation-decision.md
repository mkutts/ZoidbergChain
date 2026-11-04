# Milestone 7 Task 7.17D — Finality safety and remediation decision

**Task 7.17G follow-up (2026-10-24):** The
[distributed finality protocol decision](milestone-7-distributed-finality-protocol-decision.md)
compares Tendermint, chained HotStuff, a CometBFT engine adapter and repair of
the current signature tally. It recommends the precise Tendermint paper v3
Algorithm 1, with static equal-power `N=4,f=1,q=3`, sequential finalized parents
and one admitted media per decision, for owner review. It specifies reference
lock/valid-value/round predicates, candidate signing/proof bytes, durable signer
state, ancestry/sync rules and a bounded implementation/security roadmap.
7.17E local durability remains reusable. No launch trust model or engine route
is approved; complete G2/agreement/application schema and byte-vector freeze,
fenced signer recovery, implementation, independent adversarial verification,
and reviewer-history/admission/clock approvals remain **BLOCKED**. A durable
signer contract can now be specified against a concrete reference; production
signer implementation and Task 7.17 resumption are not ready or authorized.
No agreement code, activation or subsequent task is begun. Earlier analysis and
follow-ups below remain historical records.

**Task 7.17F follow-up (2026-10-24):** The
[validator authority and quorum decision](milestone-7-validator-authority-and-quorum-decision.md)
audits current configuration-based authority and specifies a candidate
genesis-authenticated static membership commitment, epoch, quorum verification,
historical recovery and emergency policy. It recommends `N=4,f=1,q=3` for owner
review, with `7/2/5` evaluated; no launch configuration is approved. Separately
committed Task 7.17E repaired the local received-finality durability gates
R1a/R1b within its documented scope. Authority/quorum specification is advanced,
but R0 approval/full agreement and R2 implementation remain open; safe signer
transitions, agreement, proof synchronization, adversarial validation and
reviewer-history/admission/clock gates remain **BLOCKED**. Signer specification
can use this authority interface, but a BFT signer implementation still needs
the complete approved agreement contract. The original 7.17D analysis below is
preserved as historical pre-7.17E findings; Task 7.17 is not resumed.

Date: 2026-10-24 (America/New_York).

**Specification and security analysis only. No consensus implementation is
authorized by this document. Task 7.17 remains BLOCKED.** Local finality
durability repair is sufficiently specified to begin in a separately requested
task. An independently operated Byzantine-tolerant testnet requires additional
authority, signer, agreement, synchronization and adversarial verification gates.

**Recommendation for owner review:** an initially static, permissioned validator
set operated by independent organizations, with an explicit fault budget, pinned
genesis authority and a complete reviewed BFT agreement specification. Start with
the smallest set meeting the approved budget: `N=3f+1`, `q=2f+1`; for example,
four independent validators tolerate at most one Byzantine validator. This is
an example, not allocation of operators or selection of launch values. Prefer
reusing existing validation, media, storage and networking components around a
separately versioned finality state machine. If a bounded extension cannot carry
a complete safety/liveness argument, select a separately specified BFT engine
instead of improvising unlock rules. Permissionless admission remains out of
scope and unimplemented.

## 1. Repository verification and scope

| Check | Observed result before any edit |
| --- | --- |
| Branch | `Compression-State-Bloat-and-Node-Economics`, as requested |
| HEAD | `3b8bbce70fa0c35827b48d499760bca2c3bfd56a` |
| Separate Task 7.17C commit | HEAD, `Milestone 7 Task 7.17C: audit distributed finality safety and history dependencies`; exactly the audit document and its diagnostic tests |
| Preceding work | Task 7.17B `d075cb2`, Task 7.17A `9894bb9`, original blocker `9198709`, isolated atomic certification `b3aa0b4` |
| Initial index/worktree | Clean; no staged or untracked files |
| Audit and diagnostics | Both present and tracked; diagnostics rerun unchanged, section 14 |
| Instructions | No applicable repository/ancestor `AGENTS.md`; no delegation |

Only this decision document and a short follow-up in the
[7.17C audit](milestone-7-finality-and-history-dependency-audit.md) change.
The [7.17B amendment](milestone-7-v2-reviewer-history-protocol-amendment.md),
[7.17A proposal](milestone-7-v2-reviewer-history-consensus-decision.md) and
[original history freeze/recovery audit](milestone-7-v2-history-freeze-and-recovery.md)
are historical, frozen inputs, not silently amended specifications. Their gate
status is discussed here. Existing production code, tests, vectors and schemas
are unchanged. No database migration, active database operation, protocol-2 /
block-3 activation, reset, operational signing-key generation, deployment,
commit, push or merge is performed. Existing regression fixtures use their
ordinary disposable test accounts; no validator key is provisioned.

The words **required**, **must** and **reject** below define the proposed security
contract, not claims about current enforcement. Unresolved choices are marked
**BLOCKED**. Completing this task does not approve a trust model or start repair.

## 2. Implementation evidence and present trust boundary

Implementation is the source of truth. These are the primary inspected paths:

| Path | Actual behavior and relevant boundary |
| --- | --- |
| [`config.py`](../config.py), [`blockchain.py`](../blockchain.py), `Blockchain.__init__` | Validator Ethereum addresses come from `PUBLIC_TESTNET_V1_VALIDATOR_ADDRESSES` or constructor injection; normalize/sort/deduplicate. Empty default can never finalize. No authenticated membership history or admission mechanism. |
| [`services/finality_service.py`](../services/finality_service.py), `required_quorum`, `validate_attestation`, `process_attestation` | `q=(2*N+2)//3`. Verify canonical message, signature, network, configured live membership and exact receiver-selected target. First quorum creates a QC. No proposer election, signer implementation, ancestry lock or round change. |
| [`protocol_v1_finality.py`](../protocol_v1_finality.py), [`protocol_v1.py`](../protocol_v1.py), [`wallet_auth.py`](../wallet_auth.py) | EIP-191 `personal_sign` over canonical domain-envelope UTF-8. Payload is exactly attestation version, validator address, block height/hash. Envelope binds domain, network, object type, protocol/version. Parent is indirectly bound through validated block hash; direct genesis, epoch, view and step are absent. |
| `FinalityService.validate_finalization_evidence`, `Blockchain._validate_persisted_finality_state` | Proof's embedded set determines its quorum; restart checks signatures, duplicate heights and selected-chain equality, without authenticating that historical set against a pinned authority. Not evidence of a remote arbitrary-set injection endpoint. |
| `Blockchain.submit_validator_finality_attestations`, `save_blockchain` | Copies facade votes, counts outside the durable mutation, publishes memory before save. The locked whole-document replacement protects reporting state, but lacks a finality union/revision/anchor guard. Concurrent votes can be lost; stale saves erase QCs; failed save leaves finality in memory and duplicates skip save. |
| [`storage.py`](../storage.py), `SQLiteStorageBackend.atomic_update_blockchain_document` | One `BEGIN IMMEDIATE`, durable reread, mutation, projections and commit through connection context. The primitive exists; current finality's stale replacement defeats its logical protection. `_connect` sets 30-second busy timeout, not an explicit finality durability profile. Finality is stored in document sections, not a relational finality vote ledger. |
| `JSONStorageBackend._commit_lock`, `atomic_update_blockchain_document` | OS-held advisory lock and atomic document replacement; no relational outbox/dedup guarantee. Stale replacement still erases votes/QCs. JSON compatibility must also reject rollback, without claiming SQLite's guarantees. |
| [`services/fork_choice_service.py`](../services/fork_choice_service.py), `Blockchain.compare_chains_by_originality`, `adopt_canonical_chain` | Validated same-genesis chains rank by cumulative numeric originality rounded to eight places, then height, then lower tip hash. Facade checks finalized anchors; adoption repeats against locked durable state and publishes after commit. A later stale save can erase the protection. Fork scoring is not consensus agreement. |
| [`services/canonical_reorg_service.py`](../services/canonical_reorg_service.py), `_reconcile_finality` | Rejects detached retained finality; deletes noncanonical attestations. A disposable canonical vote projection is unsuitable as signer safety memory or permanent equivocation archive. |
| [`services/block_production_service.py`](../services/block_production_service.py), [`services/block_validation_service.py`](../services/block_validation_service.py), `Blockchain.commit_certified_submission` | Valid media/certificate/ledger validation and selected-parent commit; no immediate-parent-QC requirement. No consensus-elected proposer or producer signature is supplied by mint access control. |
| [`services/peer_chain_sync_service.py`](../services/peer_chain_sync_service.py), [`protocol_v1_peer_message.py`](../protocol_v1_peer_message.py) | Sync transfers blocks, originality certificates and originality evidence; equal tip stops ordinary fetch. No finality proof/authority reconciliation. HMAC peer identity/authentication is distinct from validator signature authority and cannot replace it. |
| [`canonical_v3/finality.py`](../canonical_v3/finality.py), [`canonical_v3/storage.py`](../canonical_v3/storage.py) | Inert proof checker takes external trusted validators and equivocators. Same proof changes verdict with caller's exclusion list. Store has useful immutable records, branch CAS and finality retention, but caller context is not authenticated governance. No active agreement/signing service. |
| [`canonical_v3/history.py`](../canonical_v3/history.py), [`canonical_v3/atomic.py`](../canonical_v3/atomic.py) | Trusted local history, local observation-time ordering and atomic certification/snapshot retention are reusable laboratory components, not complete cross-node acceptance history. Separate stores are not one transaction. |

Prior specifications/tests inspected include the
[Milestone 3 report](milestone-3-release-readiness-report.md),
[v1 lifecycle/finality](protocol-v1-lifecycle-finality.md),
[Milestone 4 report](milestone-4-release-readiness-report.md),
[Milestone 5 report](milestone-5-release-readiness-report.md),
[fixed reviewer quorum](milestone-5-task-5.6-fixed-quorum-reviewer-snapshot-and-certificate-v3.md),
[Milestone 6 report](milestone-6-release-readiness-report.md),
[immutable media specification](milestone-6-task-6.1-immutable-media-safety-spec.md),
[peer networking](peer-networking.md) and
[restart checklist](testnet-restart-recovery-checklist.md).
Task 3.5 supersedes historical depth finality, but its prose assumption
"at least a quorum ... honest" is insufficient (section 4). Milestones 3–6
successful controlled delivery, reorg, import and restart tests do not prove
agreement under partitions, Byzantine signing or stale writers. In particular,
Milestone 5 application export/import retains finality sections; normal peer
chain sync does not. MODEL A full original retention remains mandatory.

**Current model: centrally configured, trust-based validator attestations.**
Operators/administration must externally coordinate one safe chain and signing
discipline. Even this trust assumption does not repair local durability defects.
Independent validators simply signing their current preferred tip are unsafe.

## 3. Intended network trust alternatives — owner decision

| Dimension | A. Centrally administered trusted operators | B. Permissioned independent operators | C. Permissionless validators |
| --- | --- | --- | --- |
| Identity/authorization | Pinned administrative list of signing addresses; operational control authenticates distribution | Publicly verifiable genesis/release manifest, fixed unweighted validator addresses and consensus policy; keys operated independently | Requires a separately approved objective admission and Sybil-resistance mechanism; none exists here |
| Membership changes | Coordinated configuration change is external governance, not current chain-verifiable history | Initially disabled. Any later change requires authenticated old/new authority, activation context and a reviewed transition proof | Dynamic eligibility/exit/reentry and adversarial capture rules require a separate design |
| Maximum faults | Assumes zero equivocation/compromise of trusted signing discipline; can lose up to `N-q` signers on a common decision. No current Byzantine protocol guarantee | Explicit `b<=f`, `N>=3f+1`, `2q>N+f`, `q<=N-f`; includes malicious or compromised keys, not just named bad operators | Unknown until admission, fault distribution and key-security model are approved; cannot inherit B's operator count as a Sybil bound |
| Safety conditions | One externally coordinated ancestry, crash-safe nonconflicting signing, correct common configuration and monotonic storage | Authenticated common authority; complete safe rounds/locks/commit rules; valid available media; durable signer state; cryptography; fault bound over relevant signing history | All B requirements plus authenticated changing authority and secure admission/economic assumptions yet to be selected |
| Liveness | Coordinator, at least q compatible signers and transport available; replacement coordination is manual; split first votes may stall forever | Eventual synchrony, fair processing/proposer opportunities, at least q responsive compatible honest signers, valid available candidate and safe view change | Additional admission/availability/incentive assumptions unresolved |
| Synchrony | No delay bound needed for the conditional safety argument; no progress during indefinite separation. Current software supplies no convergence guarantee even after healing | Safety despite arbitrary delay/partition; eventual progress only after a finite unknown stabilization time and a stable bounded-delay interval (section 8) | Cannot be specified before authority and agreement selection; do not claim asynchronous guaranteed progress |
| Independent verification | Verify signatures only after trusting externally distributed set, policy and historical mapping | Genesis-to-target verification of media, certificates, membership context, commit proofs and ancestry, without trusting a peer's DB | Public verifiers must additionally reconstruct objective validator eligibility/weight; absent |
| Governance/operator trust | Administration trusted for chain choice, key discipline, updates and recovery | Governance trusted for initial membership/independence and release identity; consensus tolerates bounded malicious operators, not a malicious authority changing the rules | Governance and Sybil/admission assumptions must be explicit; permissionless cannot mean arbitrary unauthenticated key lists |
| Decentralization claim | Controlled testnet only, even if several machines | Independently operated, permissioned validator testnet; not permissionless validator entry, proof of personhood or mainnet readiness | Not feasible as a minimal repair of current architecture; research/approval gate |
| Feasibility/public-testnet fit | Lowest implementation cost; useful controlled demonstration if limitations accepted | Plausible initial public testnet with public verification; requires repairs and a reviewed agreement contract first | Substantial new scope, BLOCKED; no stake, PoW or token-weighted selection is invented |

Public submission/observation and independent archival verification can coexist
with permissioned consensus. Distinct addresses are not evidence of independent
operators; correlated ownership, infrastructure and key custody count against
the assumed fault diversity. Pin an initial static set to avoid designing
reconfiguration inside a durability fix. Static membership means permanent loss
of more than `N-q` validators can permanently stop progress; no admin override
or silent validator removal is authorized.

If dynamic membership is later requested, its authenticated transition must bind
the old/new set digests and epochs, exact activation height/parent and policy,
and prove a unique handoff under the approved old authority. Specify whether
joint authorization is required, how pending locks/decisions survive handoff,
and why old/new signers cannot authorize incompatible histories. A local edit,
two independently valid sets or a new epoch number supplies none of that proof.
Reconfiguration liveness and historical-key compromise need their own analysis;
static membership deliberately leaves this gate closed initially.

## 4. Exact quorum and fault analysis

Let `V` be one authenticated unweighted set, `N=|V|>0`, `q` distinct signers per
decision and at most `b` Byzantine signers. Two size-q subsets intersect in at
least `I=max(0,2q-N)` members. If an honest signer cannot authorize conflicting
decisions in the relevant context, same-height certificate exclusion requires
`I>b`, equivalently `2q>N+b`. The proof is by contradiction: intersecting QCs
must share an honest signer who would have signed both. This assumption must
hold across views and restarts; merely carrying different round numbers does
not make conflicting final decisions safe.

Progress despite `f` withholding/crashed validators requires `q<=N-f` and an
agreement mechanism that actually collects those compatible signatures. For
one common budget `b<=f`, the feasible integer interval is:

```text
floor((N+f)/2)+1 <= q <= N-f
feasible iff N >= 3f+1
```

These are quorum conditions, not a complete BFT protocol. Honest non-equivocation
must cover the protocol's decision/lock rules, and cross-height safety needs the
ancestry condition in section 5. Crash and Byzantine allowances are not additive:
with `b` possible equivocators and `c` other unavailable validators, separately
require `2q>N+b` and `q<=N-b-c` for progress without Byzantine cooperation.

For the CURRENT `ceil(2N/3)` rule:

| N | q | Minimum I | Safety-only maximum b, assuming honest nonconflicting final commitments | Maximum unavailable N-q | Joint Byzantine safety/progress budget f | Conflicting same-height QC pair possible when b>= |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 1 | 1 | 0 | 0 | 0 | 1 |
| 2 | 2 | 2 | 1 | 0 | 0 | 2 |
| 3 | 2 | 1 | 0 | 1 | 0 | 1 |
| 4 | 3 | 2 | 1 | 1 | 1 | 2 |
| 5 | 4 | 3 | 2 | 1 | 1 | 3 |
| 7 | 5 | 3 | 2 | 2 | 2 | 3 |
| 10 | 7 | 4 | 3 | 3 | 3 | 4 |
| 13 | 9 | 5 | 4 | 4 | 4 | 5 |

All rows assume the same fixed authority, authentic signatures and enforceable
honest signer rules. At each listed threshold `b=I`, construct two quorums with
exactly I shared members, make the shared members Byzantine, and give each
exclusive honest group only its own proposal. Both proofs pass a standalone
signature/threshold check. Below I, a pair is excluded only under those signer
assumptions. Current code does not enforce them; with externally unconstrained
signing, conflicting proofs are possible for every nonempty N. **One particular
honest non-equivocating validator is insufficient** unless every pair of quorums
must include that validator (e.g. q=N); the theorem requires an honest member in
every intersection. N=2's safety-only b=1 is not a one-fault live BFT network.

**Smallest necessary quorum correction:** declare f first, refuse configurations
with `N<3f+1`, and require `q>=floor((N+f)/2)+1` while preserving `q<=N-f`.
For the recommended `N=3f+1` profile current q already equals `2f+1`; changing
the formula alone is unnecessary for those counts. For arbitrary N, a simple
alternative `q=floor(2N/3)+1` with `f=floor((N-1)/3)` meets both bounds but can be
more conservative than the minimum. It increases q only when N is divisible by
three. N=3 cannot tolerate one Byzantine validator with both safety and progress:
q=3 repairs exclusion but one absent signer stops progress; choose N>=4 for f=1
or explicitly accept f=0. Do not use `2f+1` blindly for an oversized set: N=5,
f=1, q=3 has intersection one and is unsafe; q=4 is needed. Both a changed quorum
and restricting allowable configurations are consensus-policy changes requiring
an approved activation boundary, not an edit to an old proof verifier.

### 4.1 Different failures have different effects

| Failure | Required interpretation |
| --- | --- |
| Crash-stop | No extra signature; removes availability. Restart remains honest only with intact signer safety state. Forgotten signing state can turn a crash into equivocation. |
| Network partition | Delays/withholds messages; does not create signing authority. Safety must hold on all sides; only a side with an eligible compatible quorum can progress. Healing requires proof reconciliation and safe round recovery. |
| Byzantine behavior | May sign conflicting targets, withhold, send different messages and manipulate timing; count by validator identity, not number of messages. |
| Stale/inconsistent membership | The common-universe intersection proof no longer applies. Two disjoint honest sets can each form a QC. Epoch labels without authenticated transitions do not fix it. |
| Key compromise | Signatures authenticate the key, not the human intent. Compromised keys count as Byzantine. Later compromise of enough historical keys can forge alternative history absent additional protection. |
| Equivocation | Conflicting signed statements as defined by the selected protocol; evidence may be hidden. Safety cannot depend on discovering every conflicting message before counting a QC. |

For independent genesis replay with ordinary persistent keys, bound compromised
identities over the historical contexts whose signatures remain usable, not just
simultaneously online operators. A mobile adversary accumulating old keys can
exceed that bound. Key erasure/forward security or trusted recent checkpoints
would change assumptions and require separate approval. No such mechanism is
claimed here; static-set key custody and cumulative compromise risk must be
disclosed. Network/genesis context prevents cross-network replay, not signing a
new alternative history with enough stolen keys.

## 5. Proposed finality invariants and present enforcement

Notation: `F(h,x)` means an authoritative finalized block x at height h, and
`x <=anc y` means x is an ancestor of y, including equality. A signature or
downloaded QC is not locally authoritative until required target validation,
authority verification and durable promotion succeed. Global safety refers to
honest nodes, not a Byzantine node's arbitrary UI labels.

| ID / proposed invariant | Current status and evidence / minimum enforcement |
| --- | --- |
| S1. `F(h,x) and F(h,y) => x=y` within the approved model | **Partial locally, missing distributed.** Existing height lock rejects a second local target; split receivers can accept two proofs. Require safe quorum, authenticated authority and complete signing/agreement contract. Counterexamples C1/C2. |
| S2. `F(h,x) and F(k,y), h<k => x <=anc y` | **Partial.** Local anchor-preserving reorg/selected-chain checks help; a target needs no parent QC and remote signers need no safe ancestry. Require finalized-parent induction or a separately proved pipelined ancestry/lock rule. C3. |
| S3. Every honest signature is allowed by one persistent signing state machine | **Missing.** No production signer/lock/round state. Signer decisions survive crash/reorg and are serialized across peers/processes. |
| S4. Validator authority is derived from pinned authenticated state | **Partial live, missing historical.** Config membership checked on receive; proof/restart trusts embedded list. Require manifest equality and, if enabled later, verified membership transitions. C4. |
| S5. Proof binds network, genesis, protocol/profile, height, parent, block hash, validator epoch/set and voting context | **Partial.** Existing envelope/height/hash binds network/protocol and parent transitively; no direct G, epoch, round or step. Define new closed signing/proof formats and domain. Verify parent/hash from actual validated bytes; no need to duplicate media. |
| S6. Conflicting independently valid finality is detected and handled deterministically | **Partial local evidence, missing reconciliation.** Count discounts locally known equivocation; noncanonical receipt normally rejects before retention; retained QC stays. Inert verifier uses external exclusion set. Require proof-stable verification, permanent conflict evidence and fail-stop advancement on contradictory QCs. |
| S7. Published finalized state survives crash and stale writers | **Violated.** Precommit memory mutation, stale overwrite and lost votes, C5–C7. Commit-before-publish plus monotonic all-writer checks. |
| S8. No reorg replaces finalized ancestry | **Partial.** Adoption rechecks durable anchors; stale whole-document writes can erase them. Enforce across every storage/restore/import path and race. |
| S9. Fresh nodes independently verify historical authority, finality and full target history | **Missing end-to-end.** Individual signature/chain validators exist; proof/authority sync and authenticated bootstrap absent. No use of tip equality, peer DB labels or byte-copy backup as a proof. |
| S10. Invalid protocol evidence and local operational failure stay distinct | **Partial.** Inert error classes and incomplete history paths help; active save exception leaves alleged finality in memory. Invalid => deterministic reject; missing dependencies => incomplete; storage/decoder failure => local unavailable; contradictory valid authority => safety fault. No penalty or invalid-media verdict from disk failure. |
| S11. Validation/proof verdict depends only on approved authority and supplied authenticated bytes | **Partial.** Canonical formats reusable, but local equivocator context and self-declared membership defeat common verification. Remove observer-dependent QC revocation in the new profile; future penalties must be prospective authenticated transitions. |
| S12. Signing/finality availability entails complete validated MODEL A source availability | **Partial.** Existing full media reconstruction/chain validation is reusable. New agreement signer must validate/retain exact original representation and sources before voting; proof of signatures alone does not fetch missing media or guarantee eternal serving. |

An enforceable conservative cross-height contract is to permit a final commitment
only for a valid child of an already verified finalized parent, with a pinned
genesis exception. Same-height uniqueness plus induction then gives one finalized
ancestry: every child at h extends the unique finalized h-1. It requires an actual
safe same-height agreement protocol; it does not resolve split votes. This is
the proposed 7.17B serial lifecycle and changes active acceptance availability.
If the owner retains acceptance on unfinalized parents, specify a distinct
provisional path and a complete gapped/pipelined commit-safety proof before
activating it; a moving local `get_finalized_head()` is insufficient.

### 5.1 Formal and executable counterexamples

The unchanged [7.17C diagnostic suite](../tests/test_milestone_7_task_7_17c_finality_audit.py)
executes receiver/storage behavior under stated synthetic-target/authentic-vote
assumptions. Signature recovery is stubbed only in structural scenarios; a
separate published v2 fixture uses real recovery. These are not claims of newly
generated real-media attack chains.

| Witness | Trace / existing diagnostic |
| --- | --- |
| C1: one Byzantine out of three | A signs X, C signs Y, B signs both; `{A,B}` and `{B,C}` form q=2 QCs. `test_conflicting_quorums_with_one_equivocator_in_three`. |
| C2: no enforced external signing constraint | N=4, the same three keys sign X and Y; both receiver contexts finalize. `test_verifier_does_not_enforce_signer_side_non_equivocation`. |
| C3: sign once per height still unsafe | A+B sign X@1, QC withheld; B+C sign Z@2 on `genesis -> Y@1 -> Z@2`. B never signs twice at one height. Both QCs pass; X-aware reorg check rejects Z's branch. `test_incompatible_cross_height_proofs_need_no_same_height_double_vote`. |
| C4: self-authored membership | A one-key proof passes persisted validation at a facade configured with disjoint keys. `test_persisted_v1_proof_trusts_its_own_validator_set`. Formal variant: honest disjoint sets each certify a conflicting child. |
| C5: lost update | Two facade calls copy empty votes before either writes; each counts one; later save retains one vote, no quorum. `test_concurrent_attestation_calls_can_lose_a_quorum_vote`. |
| C6: durable rollback | Writer A saves QC; old writer B saves empty finality and erases it on JSON and SQLite. `test_stale_whole_document_save_erases_durable_finality`. |
| C7: memory outruns disk | Save raises; facade retains QC; exact retry reports duplicate and never saves. `test_failed_save_leaves_in_memory_finality_and_duplicate_retry_does_not_save`. |
| C8: no guaranteed retry progress | N=4, honest first votes split X:2/Y:2 with q=3; exact retries remain duplicates. `test_split_first_votes_and_exact_retries_do_not_reach_quorum`. |
| C9: observer-dependent proof | Published v2 QC passes with no excluded signers and fails with its signers in caller's equivocator set. `test_existing_v2_signature_proof_depends_on_external_equivocator_context`. |
| C10: missing finality sync | Peer supplies `finalized_blocks` alongside blocks; fetch result discards them. `test_peer_block_fetch_does_not_transfer_finality_even_if_peer_supplies_it`. |

## 6. Durable validator signing and anti-equivocation contract

Validator signing safety is distinct from a receiver durably retaining someone
else's QC. A receiver can restore certificates from authenticated sources; an
honest signer must also remember signatures it released that never reached a QC.
Reconstructing only finalized blocks cannot recover those private decisions.

### 6.1 Minimum state and ownership

Persist one authoritative signer namespace per key and `(network,genesis,
protocol/profile,finality-policy,validator-epoch/set-digest)`. Its minimum logical
state includes:

- Key identity and authorization evidence, immutable context and policy digest.
- Highest authorized height/round/step cursor; exact canonical sign bytes and
  their digest; target block hash and validated parent identity; issued signature
  bytes or a recoverable pending-signature reservation.
- For a round-based protocol: locked value and lock round/certificate, highest
  valid/prepare/progress certificate and safe justification for each transition.
  Nil votes/timeouts need explicit message types distinct from commit votes.
- Last committed finalized ancestry and source/proof references; durable revision
  and exclusive signing ownership/fencing across concurrent processes.
- Enough prior decision records to reject every prohibited request, not just
  the current highest height. Pruning requires a protocol proof; retaining all
  small decisions is the initial conservative option.

The precise lock/prepare/commit fields and transition predicates are **BLOCKED**
on selecting the complete agreement specification. A durable `(height,hash)` map
is adequate only for the deliberately non-live sign-once option plus safe ancestry;
it cannot masquerade as a BFT round signer. The highest observed certificate
must be verified and retained, never accepted from a peer's unsigned progress
counter. A higher round number alone cannot override a lock.

Use one key exclusively through one fenced signing authority. Two independently
restored signer databases sharing a key can each honestly sign a different value;
SQLite cannot serialize different machines' databases. Remote signer/HSM design,
if selected, must preserve the same single-authority contract. Arbitrary wallet
access to the validator key bypasses it and invalidates the honest-signer premise.

### 6.2 Required release sequence

1. Authenticate request context/authority; fully validate target sources/parent
   and the chosen protocol's round/step justification. Serialize with the signer
   store's durable transaction and reread authoritative safety state.
2. Before any signature leaves the signer, durably reserve the exact message and
   all safety transitions making that signature irrevocable. Conflicting requests
   lose the compare-and-swap/uniqueness predicate; exact repeats reuse the record.
3. Produce the signature only for the reserved bytes. Persist the exact signature
   and updated release record, with required sync, before returning/gossiping it.
   If signing occurs before a final store commit, no byte may escape on failure;
   a pending reservation already forbids a conflicting signature. A simpler
   implementation may sign within the serialized transaction if justified for
   the selected signer, but must still commit before release.
4. After unknown commit/acknowledgement outcome, reopen/reconcile the record and
   return the retained signature for an exact retry. Never infer that timeout
   means no signature was emitted. Fail closed while storage outcome is unknown.

Crash before reservation commit releases nothing and may retry. Crash after
reservation but before signature leaves a durable obligation to those same bytes,
not permission to choose a new target. Crash after signature release retains the
decision/signature across restart. Duplicate requests from different peers return
the same durable result; different messages in a prohibited context reject and
can retain authenticated evidence. Conflicting requests must be tested with two
processes, not just one mutex.

For sign-once safety, require every next-height decision to extend the signer's
already protected ancestry, or require the unique immediate finalized parent.
For rounds, do **not** permanently lock on the first proposal or unlock after a
timer. Neither rule supplies safe live recovery: C8 demonstrates the first
deadlock; a hidden QC demonstrates why unproved unlocking is dangerous. The
approved protocol must prove that no unlock certificate allows an honest signer
to help decide a value conflicting with an earlier possible decision, including
when that decision's QC was withheld. Carrying old prepare/lock evidence across
view changes and deciding only at the specified commit phase are mandatory
proof obligations, not an algorithm invented here.

### 6.3 Reset, backup, rollback and key compromise

Network/genesis and signature-purpose separation must be signed, not only stored
in a local filename. Never reuse a v1 network identity across chain resets whose
messages lack G binding. A fresh G does not authorize two active clones of the
same context. Restore signer backups only with proof they cannot forget released
decisions and with exclusive key ownership/fencing. An old image, corrupt signer
store or lost signing history disables signing until a separately approved safe
recovery/key transition; finality QCs alone cannot prove a withheld vote never
existed. Static membership may then halt. No deletion/reset-and-resign recovery,
new key, chain reset or governance override is introduced by this task.

## 7. Local finality durability and storage requirements

### 7.1 Atomicity boundary and smallest implementation route

The minimum repair can reuse `atomic_update_blockchain_document`: perform the
entire read/validate/merge/count/finalize operation on its locked **durable** state,
not on a precomputed facade replacement. Capture the chain identity/revision for
any expensive prevalidation; under the transaction reread/check that exact chain,
authority and finalized revision before using the result. If stale, retry from
fresh authoritative state. An existing-head CAS by itself is insufficient:
votes/finality can advance without a head change.

One SQLite database/connection transaction must cover:

```text
BEGIN IMMEDIATE
  read durable chain, authority, vote set, QCs, anchor and revisions
  compare expected validated-chain identity and finality revision
  verify/revalidate incoming identities, target and policy
  append/deduplicate vote/equivocation evidence; union durable retained votes
  derive first QC from that committed-union view, never caller snapshot alone
  preserve all earlier finalized targets and ancestry; detect conflict
  write vote evidence, exact QC, monotonic anchor/revision and required projections
  write idempotency receipt and relay work if these are part of this same store
COMMIT with the approved durable sync profile
publish committed memory/status; acknowledge; relay from durable work
```

Finalized anchors are append-only facts: repeated height/hash is idempotent,
same height/different hash is conflict, new higher anchor must extend all retained
anchors. Height alone is not a monotonicity check. Adding an older missing QC is
allowed only for a compatible ancestor; it cannot lower the highest anchor or
replace an immutable proof. An additional valid signature need not rewrite the
first retained QC; retain its vote separately. Different sufficient signer
subsets may yield different valid proof bytes for the **same** block; do not
declare that a conflicting finalized block. Select a deterministic local proof
representation or retain separately identified compatible proofs.

For two contradictory otherwise-valid QCs, first validate both authorities,
targets and complete conflicting ancestry; an invalid signature or unverified
peer claim must not trigger a consensus-wide safety alarm. Persist both verified
proofs and a safety-fault latch without replacing the existing anchor; stop new
authoritative promotion/signing in that context, retain diagnostic/source access
and require separately approved recovery. If fault persistence itself fails,
stop locally until storage is reconciled. An evidence-only transaction may commit
the latch while refusing canonical advancement; do not roll back the only copy
of the contradiction with the rejected promotion. Receipt order, block score,
lower hash and locally subtracting equivocators cannot choose a replacement.
Nodes that have not yet received the hidden proof cannot detect it; the protocol
must prevent conflicting decisions within its fault bound rather than rely on
instant global discovery. Preserve individual equivocation evidence similarly,
without revoking a previously valid QC or automatically changing membership.

Enforce this at **every writer boundary**, including generic saves, low-level
document saves, mint/ledger/reorg callbacks, restore/import/backup tools and
future stores. Generic facade saves must preserve durable finality-owned fields
or reject stale revisions; they must reject a proposed chain dropping any
durable finalized target. A union of QCs without a chain/authority check is unsafe.
Current direct document save APIs cannot remain an unguarded rollback bypass.
Use explicit administrative offline recovery boundaries instead of granting
ordinary imports permission to erase finality.

A first no-migration repair can retain current document sections and serialize
logical uniqueness/union checks under the transaction. A subsequent relational
optimization may use a context/height/round/step/validator decision key and
separate signed-message evidence key. Conflicting signed votes must be retained
as evidence rather than overwritten by an upsert. QCs require a unique
context/height authoritative target and immutable target/proof identity. An anchor
row revision can use conditional `UPDATE ... WHERE revision=expected`, checking
exactly one affected row; SQL `CHECK` of a single row does not enforce historical
monotonicity. A trigger/guard must compare OLD/NEW target ancestry and block
deletion/replacement where applicable. Concrete SQL schema/migration is a later
reviewed task. No migration is necessary merely to stop stale document replacement.

### 7.2 Failure-specific contract

| Failure / scenario | Remedy and required observable result |
| --- | --- |
| 1. Concurrent vote updates | Durable reread/union/count under one writer transaction, with per-facade serialization/refresh for publication. Two distinct compatible votes survive even if both calls began on empty memory. |
| 2. Stale-save finality erasure | All-writer monotonic anchor/revision guards and target-preserving chain checks. Stale saves either merge finality-owned fields into a compatible chain or fail stale without writes. Test JSON and SQLite. |
| 3. Save failure after memory advancement | Build isolated proposed state; publish only after successful commit. On any exception with uncertain outcome mark facade unavailable and reload before serving finality. Duplicate handling checks durable receipts and retries persistence if necessary. |
| 4. Partial QC persistence | Votes, proof bytes, anchor/revision and any authoritative promotion/cursor in the same transaction. No QC referring to absent target/authority, no published anchor without proof. Disposable derived indexes can be rebuilt but cannot authorize ahead of the committed cursor. |
| 5. Concurrent finalization | Read first-QC identity under lock; same target yields one authoritative record, incompatible target is a safety conflict with no canonical replacement. Compatible extra evidence is retained idempotently. |
| 6. Repeated delivery | Dedup by canonical logical signed-message/context identity, not transport nonce or signature variant alone. Exact acknowledged result is recoverable; repeated votes never add weight. Retain variant evidence only with explicit bounded policy. |
| 7. Crash before commit | No acknowledged/published new finality; transaction rolls back. Replay message after restart can retry from durable state. |
| 8. Crash after commit before acknowledgement | New state survives; exact retry reads committed result and does not duplicate QC, event or relay effect. Postcommit/prepublish crash recovers from disk. |
| 9. Busy/locked SQLite | Bounded busy wait/backoff; reread after transaction retry. `SQLITE_BUSY`/`LOCKED` is local unavailable, not invalid vote. COMMIT can be busy; never publish before it succeeds. Avoid nested transactions/shared unsafe connection use. |
| 10. Disk full/I/O/sync failure | No signature/finality success from an unconfirmed commit; explicit local storage failure, rollback/reopen/reconcile as supported by error state. If the outcome is uncertain, stop publication/signing until reconciled. Inject before/at commit; include real SQLite full-page-limit coverage. |
| 11. Stale process/recovery image | Ignore old memory as authority, reread committed revisions; reject stale callbacks and stale backups that would roll back anchors. Signer-store rollback additionally follows section 6; receiver replay is not sufficient signer recovery. |
| 12. Reorg at finalized boundary | Race finalization versus reorg inside the same serialized authority. If finality wins, replacement must preserve anchor; if reorg wins before any QC, stale target promotion must reject/revalidate. Reorg strictly above anchors can proceed atomically, retaining permanent signer/equivocation records. |

The existing SQLite transaction primitive supports local atomic replacement, but
its use must be corrected and its durability settings asserted. SQLite's
[transaction documentation](https://www.sqlite.org/lang_transaction.html) explains
single-writer serialization and busy outcomes; it does not make an outside
read-modify-write logically atomic. Avoid treating timeout as evidence of invalid
consensus input.

Prefer the repository's already tested isolated `DELETE / synchronous=EXTRA`
profile for a new safety-critical signer/finality store unless a separately
validated profile is approved. Explicitly read back settings on every relevant
connection. The active `_connect` currently sets only busy timeout; do not claim
it already applies the isolated profile. Durability assumes a supported local
filesystem/VFS, correct locking and truthful storage flushes; verify the target
platform and backup/recovery behavior. SQLite documents the additional directory
sync for DELETE/EXTRA and the WAL/FULL distinction in its
[synchronous reference](https://www.sqlite.org/pragma.html#pragma_synchronous).

Preserve `canonical_v3.atomic.wal_is_fixed` and pre-open WAL refusal: accepted
families are `>=3.51.3`, `3.50.7..<3.51.0`, or `3.44.6..<3.45.0` as implemented.
This runtime is SQLite 3.49.1 and is refused for that isolated WAL mode. Do not
disable the guard, opt into WAL for convenience or infer that an older generic
`V3Store` WAL default meets the stronger `AtomicV3Store` protection. Any new
finality/signer path must preserve/apply the applicable protection. No runtime or
journal settings are changed here.

JSON must use durable-state mutation inside its OS lock and the same monotonic
logical guards. Its atomic replace is not a proof of power-loss durability or
cross-file transactionality; do not advertise parity without platform-specific
tests. Recommend SQLite as the initial independent-validator safety profile.

### 7.3 Independent databases and downstream state

There is no proven atomic commit across active `storage.py`, a separate signer
database and isolated `canonical_v3` certification/history stores. Do not write
them sequentially and call that one atomic promotion. Minimum choices:

1. Co-locate authoritative chain/finality/history source promotion in one SQLite
   transaction, leaving derived caches replayable; or
2. Commit one authoritative immutable source/anchor with an idempotent durable
   outbox, apply to other stores in order, and expose a verified applied cursor
   only after their transaction succeeds. Missing application is incomplete.

The second choice is recoverable eventual application, **not** cross-database
atomicity. A signer can reference externally stored immutable proof bytes/digests
only if its own transaction durably records enough validated safety justification
to enforce locks after a crash; no signature release depends on an uncommitted
record elsewhere. Backups must preserve both receiver history and signer safety;
copying a live WAL database without its supported backup procedure is insufficient.

## 8. Distributed agreement and liveness requirements

### 8.1 What current code supports

| Situation | Current behavior / needed target behavior |
| --- | --- |
| One candidate at a height | Can count q supplied valid signatures on the locally selected target. No automatic signing/gossip guarantee. Safe only with external common authority/discipline and repaired durability. |
| Competing candidates | Deterministic ranking for the same available set, not common knowledge. No safe competing-proposal signing/round contract. Target must decide one value while preserving validation/media rules. |
| Proposer failure | No elected proposer/failover protocol. Another mint caller can try a certified submission; no guarantee it shares locked target. Target must permit an honest proposer opportunity with safe carryover justification. |
| Validator disappearance | Fewer than q compatible signers stalls. Never lower q based on a local timeout. Within approved fault budget, target view changes must progress without unavailable members. |
| Partition | Different branches can be selected; no distributed exclusion without signer assumptions. Target retains safety indefinitely; no progress promise for a component below quorum. |
| Reconnection | Block sync alone does not reconcile QCs, signing locks or views. Target fetches/verifies proof/authority gaps and resumes safe rounds; valid contradictory commits fail stop. |
| Parent advancement | Current production extends selected tip, not necessarily finalized parent. Recommended serial target pins immediate finalized parent; stale drafts must rebuild; next height cannot release an old lock unsafely. |
| Delayed votes | Count only in their exact context. Target cannot mix epochs/views/steps or treat a delayed prepare/timeout as a commit. A late valid commit proof remains authoritative for its target, independent of receipt time. |
| Equivocation | Local live exclusion, partial evidence retention. Target safety relies on fault bound and protocol, with permanent evidence, standalone QC validity and no retroactive threshold rewriting. |
| View/round change | Absent. Target needs authenticated progress/timeout messages, safe lock transfer, duplicate/ordering rules and restart state. Adding an integer round is insufficient. |
| Stalled finality | Current retries can deadlock (C8); no emergency recovery. Target distinguishes no valid media, insufficient quorum and protocol view stall; only the last is potentially resolved by safe view change. |
| Restart | Restores retained receiver QCs, not signer decisions/pending round safety. Target restores both, reconciles sources and resumes without signing a forbidden message. |

### 8.2 Three agreement options

**A. Constrained one-shot final signing.** A trusted coordinator chooses one
immutable candidate per finalized parent, every signer validates full ancestry
and durably signs once, with no conflicting proposal progress or unlock. Under
`2q>N+f`, common authority and the finalized-parent rule, safety has a short
intersection/induction argument. Progress needs q signers agreeing on that exact
value; coordinator equivocation, split votes or permanent disappearance can halt
forever, even after network healing. Suitable only if the owner approves this
availability/centralization limitation. A permanent first-vote lock does not meet
independent Byzantine failover goals.

**B. Minimum safe permissioned BFT extension.** Retain existing proposal/media
validation and add a separately versioned, complete round-based decision engine.
Before code, its closed transition specification must define proposer schedule,
round/step messages, prepare/lock and decision certificates, nil/timeout behavior,
safe value/reproposal constraints, justification selection on view change,
future/old message buffering, exact membership context and crash recovery. Prove
agreement within and across rounds, validity, ancestry and conditional termination.
It must handle a committed-but-hidden certificate and lock holders on different
rounds, rather than assuming every honest signer saw the same QC. A two-phase
label alone is not a proof. **BLOCKED pending selection/review of that entire
state machine.** No safe unlock rule is fabricated by this document.

**C. Separately specified BFT finality replacement.** Integrate a complete
published/reviewed protocol if B cannot be justified as a bounded extension.
Keep MODEL A admission and original-byte validation as the application validity
predicate, and keep reward eligibility separate from the consensus proposer role.
Adapt interfaces, authority, canonical signing and persistence explicitly. Do not
assume a library or protocol name supplies the correct application integration,
runtime, proof encoding, membership or cross-version behavior. Replacement is
also **BLOCKED** until protocol/version/adaptation scope is approved.

As references for the level of completeness required, the official
[Tendermint consensus specification](https://docs.tendermint.com/master/spec/consensus/consensus.html)
separates proposal, prevote, precommit, commit and later rounds with certificate
conditions. It is an example to evaluate, not an adopted protocol or permission
to copy a subset of its rules. Research in
[Dissecting Tendermint](https://arxiv.org/abs/1809.09858) identifies correctness
conditions and bugs in preliminary variants; this supports requiring a precise
reviewed variant rather than improvising round/lock changes. These references
do not prove ZoidbergChain's current or future integration correct.

### 8.3 Agreement versus provisional fork choice

The current finality receiver only counts signatures for its selected target,
and ordinary adoption first requires a preferred originality score. B/C must
define how a valid commit on another available provisional branch becomes the
common selected prefix. Recommended new-profile rule: verify the full committed
branch and authority, preserve all previous finalized anchors, then give the
approved consensus decision priority over a conflicting **unfinalized** local
suffix. Rank still-undecided candidates only within the protocol's permissible
proposal/lock rules; a newly seen higher-score candidate cannot revoke a decision
or authorize an unsafe revote. This is a substantive finality/fork-choice
integration change requiring owner/profile approval, not current behavior.
If preserving today's unconditional score-first adoption is mandatory, the owner
must select/prove a compatible agreement design instead; otherwise B/C progress
can fail even after a valid quorum decision. No score ever resolves two valid
contradictory finalized decisions. The exact rational adapter proposed in 7.17B
also needs this priority contract; exact arithmetic alone does not supply it.

### 8.4 Exact conditional liveness assumption

For B/C, require a finite but unknown stabilization time GST. After GST, honest
validators needed for quorum can communicate through available paths within a
finite bound Delta, validate available bounded proposals within a finite bound
P, obtain durable signer/receiver storage service within a finite bound D, and
receive fair CPU/proposer scheduling. The selected protocol's increasing or
otherwise justified timeouts/pacemaker must eventually provide sufficiently
long overlapping rounds with an honest eligible proposer. Do not choose a fixed
timeout value in this task. Byzantine validators may remain silent; the honest
responsive set must suffice for q.

Media liveness additionally requires at least one available valid media/certificate
and inclusion opportunity. Arbitrary reviewer refusal, exhausted quotas, invalid
media, lack of a decisive vote cohort or indefinite storage outage falls outside
that assumption. Safety must not rely on a wall clock or GST detection. No
guaranteed finite decision time before GST or during an indefinite partition is
claimed. Exact theorem/protocol timeout conditions remain part of the B/C gate.

## 9. Progress without accepted media

Finalizing an already accepted media target, retransmitting its proof, restarting,
and reconciling votes do **not** require a new block. Agreement can exchange
authenticated rounds/timeouts for a pending height without accepting media or
earning rewards. Such messages are protocol evidence, not new media blocks or
automatically ordered reviewer events. With no pending valid media there is no
next media decision to make.

| Need | Strict media-only history | Additional control-history alternative |
| --- | --- | --- |
| Finality of existing accepted targets | Can progress with q compatible signatures; no empty block necessary | No extra history required merely for proof collection |
| Static validator membership | Can remain unchanged without blocks; loss beyond budget stalls | Control records only needed if approved dynamic transitions/recovery must advance while media is absent |
| Reviewer penalties/quota/age | Finalized-height clock (`h//5`) stops once media stops; all reviewers penalized/exhausted can create a circular wait | A separately approved authenticated sequence/clock can advance; its relation to media height/epoch must be specified |
| Epoch progression/native activity | No new heights or native settlement absent accepted media | Control history could carry native activity and explicit epoch causes; changes economics and earned eligibility |
| Recovery | Verify/recover existing sources without new media; cannot manufacture forgotten signing authority | Any emergency authority is a separate governance decision, not implied by a control record |
| Repeated certification/missing submissions | Draft retry does not advance consensus or globally spend quota. Accepted-unminted participation/ISSUE cannot become authoritative absent an authenticated inclusion source | Can order extra accepted/rejected observations or issuance while media absent, if admission/completeness/availability rules are approved |

**Choice is BLOCKED:** retain strict media-only history and explicitly accept its
clock/participation/recovery limits, or approve a distinct control-record design.
Do not insert empty blocks or fake media. The one-media-per-media-block and
complete original retention rules are preserved in either case, but if **every
chain block must contain one accepted media**, 7.17B's history blocks are forbidden.

If separate control records are approved, they must have a distinct type/domain,
bounded canonical contents, authenticated order and connection to the finalized
media prefix, explicit consensus authorization/finality, production pacing/rate
limits, availability and retention requirements, replay cursor and activation
rules. If placed in the existing chain, that is a newly approved non-media block
kind (as 7.17B proposes). If kept in an auxiliary sequence, that sequence is also
consensus history: cross-sequence order, finality and atomic cursor dependencies
must be proved, with no two independent authorities or circular commitments.
Neither choice is implemented or approved here. Round/timeout messages by
themselves do not authorize penalties, membership changes or epoch increments.

Control records may contain no media reward and must not weaken two-dimensional
admission. Any fee, incentive, proposer role or subsidy change is separate
approval. Pacing and archival costs must enter node economics; unlimited empty
records create unlimited height/age inflation and storage/CPU work. Preliminary
REGISTER retains full media before community approval; it makes those bytes
permanent even without a media reward. That hostile-content/admission decision
remains separate and BLOCKED. Ordinary atomic media admission needs no preliminary
copy. Control progress cannot solve missing validator quorum or force reviewers
to approve all-unsure/negative media.

## 10. Reviewer-history dependency and frozen proposals

The minimum foundation is one independently verifiable, durable, available
finalized prefix with authenticated validator authority and deterministic source
ordering. Honest nodes with the same approved bootstrap and prefix must derive
the same reviewer state; they must not finalize incompatible prefixes within the
fault model. This requirement is stronger than locally authenticating a QC.

| Dependency | Minimum contract before Task 7.17 integration |
| --- | --- |
| Genesis bootstrap | Pin actual N/G/profile/policies, validator set and reviewer grants independently. Validators and reviewers remain distinct. Compute G without a G-dependent self-reference; derive post-genesis journal bootstrap afterward. Grant authority is not a peer-supplied state hash. |
| Signed reviewer votes | Verify original canonical signed bytes and target/creator/reference/policy context. Finality authenticates inclusion/order/acceptance, not private receipt or completeness of all off-chain signatures. Do not relabel V3 as V4. |
| Historical eligibility | Replay creator/native activity and complete accepted participation at the exact finalized reference; no current labels, local clocks or imported DB rows as authority. |
| Promotion/penalties | Deterministic authenticated causes/order, prospective effective boundaries and immutable past acceptance; withheld evidence first affects the approved inclusion boundary, not an invented past snapshot. |
| Quota consumption | Full accepted receipt inventory including unminted participation if retained; dimensions dedup per submission/epoch; candidate quota is branch-owned, finalized quota permanent. Missing history is incomplete, not zero. |
| Certificate issuance | Same-candidate signed inputs can be validated from finalized parent scratch state before obtaining current finality. Only finalized canonical ISSUE/inclusion gives global ownership; off-chain returned drafts are not permanent consensus claims. |
| Event completeness | All committed sources, implicit extraction and mandatory transition outputs must be reconstructable. A QC commits included bytes, not every signature a producer privately saw; do not promise censorship completeness. |
| Finalized-parent cutoff | Use an exact immutable `(height,hash,verified proof)` and source cursor, not the receiver's moving latest label. Approve immediate h-1 finality or fully specify a different cursor lifecycle. Drafts with changed parent must rebuild under the approved expiry/reference rules. |
| Independent replay | Genesis-to-target full original media, votes/events, policy/authority and proofs, verified in separate fresh databases; identical logical state and certificate outcomes despite insertion/layout/restart differences. A journal/root hash or SQLite image alone is insufficient. |
| Reorganization | Finalized source/receipt/penalty/ownership never rolls back. Losing provisional branch effects can be discarded; durable signer safety/equivocation evidence never is. Apply authoritative prefix and derived cursor under section 7's actual transaction boundary. |

**Retain from 7.17A/B as design work:** immutable sources and exact canonical
serialization, explicit trusted bootstrap, deterministic replay, direct signed
review references/creator binding, noncircular same-candidate admission,
prospective penalties, branch-owned scratch state, source-only verification and
reuse of existing selected vote/media bytes. A canonical archival journal is a
reasonable simpler choice than a mandatory sparse Merkle state tree; neither
structure cures missing finality.

**Requires a subsequent explicit amendment:** 7.17B's FP fixed `ceil-two-thirds`
must bind the approved f/N/quorum contract, full agreement and membership context;
its retained nine-field finality attestations cannot encode new view/step/G/epoch
signing semantics. Its standalone proof-stable/no-retroactive-exclusion policy
is a useful target, but needs approved proof/commit format and activation. The
immediate finalized-parent rule and control/history-block clock need approval.
Old-set/new-set transitions are absent and cannot be inferred from reviewer events.
Exact earliest-16 cohort can permanently strand an all-unsure submission; changing
it to a favorable subset changes censorship/review policy and is not a finality
repair. Preliminary unreviewed media archival, selection, fresh-vote offense
verification, issuance permanence and schema/resource budgets remain separate
history gates. Do not modify frozen A/B documents or vectors automatically.

Task 7.15/7.16 local checks, immutable snapshots, rollback/idempotency and ownership
primitives remain valuable within their stated trusted-local scope. Their
off-chain permanent issuance claims cannot become distributed authority without
the approved history amendment. Passing their tests does not open Task 7.17.

## 11. Architecture decision matrix and resource implications

| Criterion | A. Durability + trust-based finality | B. Durability + minimum complete permissioned BFT semantics | C. Separately versioned BFT replacement |
| --- | --- | --- | --- |
| Safety | Conditional on trusted administration, common authority and external safe signing/ancestry; patch removes local rollback only | Conditional Byzantine safety after a complete reviewed round/commit/ancestry contract and fault bound are enforced | Conditional on selected protocol's proof and correct application/authority/storage integration |
| Liveness | Single coordinated value may progress; split votes/coordinator loss can halt permanently | Eventual-synchrony progress within fault bound and valid-candidate availability, once safe view change is supplied | Selected protocol's precise conditional liveness; no media approval guarantee |
| Byzantine tolerance | No current distributed BFT claim; arithmetic alone does not supply it | `b<=f`, safe q, independent operators, durable correct signers | Bound and quorum from selected unweighted permissioned protocol/adaptation |
| Effort | Low–medium local repair plus honest operating contract | Medium–high; B is not just adding one field/timeout | High integration/replacement effort; may reduce custom-protocol proof burden |
| Code reuse | Nearly all active validation/storage/networking reused | Reuse MODEL A, media/admission/ledger/reward checks, hashing primitives, transactional storage and transport shell | Same application reuse; replace finality engine/wire/proof adapters; more integration changes |
| Testing | All-writer concurrency/crash tests plus disclosed external trust | State-machine/model checking, adversarial scheduling, real multi-node crash/partition tests and interoperability | Protocol conformance/model evidence plus equally necessary application/integration adversarial tests |
| Networking | Add bounded proof/authority relay; may remain centrally coordinated | Authenticated proposal/vote/timeout/progress gossip, bounded anti-entropy and proof/authority fetch | Protocol-specific transport/pacemaker/state transfer and version negotiation |
| Sign/canonical schema | Existing bytes may remain only under their disclosed static context restrictions; authenticated authority still required | New exact G/set/epoch/view/step/justification signing/proof contracts; old v1/v2 messages unchanged | New protocol-specific signed/proof contracts and explicit application binding |
| Reviewer history | Can authenticate a centrally trusted journal only if that trust is expressly accepted; does not meet independent Byzantine goal | Compatible once finality plus separate history/admission/clock gates pass | Compatible through a precise finalized-prefix adapter, same separate history gates |
| Independent reproducibility | Reproduce given a trusted authority inventory; not independently established historical membership today | Source-only replay of common approved genesis/authority and finalized prefix | Source-only replay through protocol-specific proofs; no opaque engine DB as authority |
| Three-year cost | Smallest control-message set; current whole-document writes may amplify costs; no measured total | More durable signer records, QC/progress storage, verification and gossip; quantify with bounded rounds/retention | Implementation/protocol dependent; possibly larger proofs/state/traffic; benchmark instead of claiming savings |
| Public-testnet suitability | Controlled demonstration if owner accepts trusted operators and stalling | Recommended initial independent permissioned testnet after gates; no permissionless claim | Appropriate fallback if a complete safe B extension is not actually small/reviewable |

**Smallest architecture meeting the recommended objectives:** B with an approved
initial static independent set, explicit f/q, a conservative finalized-parent
contract, durable single-authority signer and complete reviewed agreement
state machine, standalone context-bound commit proofs, atomic monotonic receiver
storage and bounded source/proof synchronization. If the owner requires safe
competing proposals and proposer failover, option A does not meet that objective.
If B cannot provide the full proof/transition contract with a bounded adaptation,
C is the smaller *security risk* despite greater integration effort. No protocol
name, release or new admission mechanism is selected by this recommendation.

### 11.1 Three-year accounting, without invented prices

Use `H=1095*M` media decisions for M per day; K additional control decisions;
Q mean retained commit-proof bytes; S mean durable signer-record bytes per
signature; r mean rounds; s signed steps per validator per round; a bytes per
round message; and measured database/index/backup amplification A.

```text
raw proof archive per node = (H+K)*Q
raw local signer archive = (H+K)*r*s*S for a validator signing every step
simple all-to-all vote delivery bytes = (H+K)*r*s*N*(N-1)*a
additional control source bytes = K*mean_control_record_bytes
```

Gossip topology, proposal media transmission, retries, invalid traffic, proof
fetch, quorum variants, backups and indexes are additional measured costs. A
unilateral round/message flood must not cause unbounded retained work; choose
per-context buffering/retention and admission limits without discarding required
lock/equivocation evidence. Eventual synchrony gives no unconditional finite
round bound, so a hard three-year worst-case cost cannot be inferred from M.

Illustrative accounting only: at M=1,000/day, one 8,192-byte proof per decision
adds 8,970,240,000 bytes (about 8.35 GiB) raw over three years. A 262,144-byte
proof per decision instead adds 287,047,680,000 bytes (about 267.33 GiB). These
are assumed mean versus existing inert size-cap scenarios, not predictions or
new caps. With N=4, r=1, s=2 and a=1,536, simple directed all-to-all vote delivery
is 40,366,080,000 bytes (about 37.59 GiB) network-wide; at r=10 it is ten times
that, before proposal/full-media traffic. A may differ for source, indexes and
signer records; measure each rather than multiply by an invented factor.
Option A can require fewer messages; B/C cannot be priced or ranked numerically
before the selected protocol's actual proof/round bounds are known.

Full original media remain the dominant separately retained workload in many
scenarios and cannot be replaced with proofs, URLs or commitments. Optional
preliminary media and control records add permanent archives, replay CPU and
sync costs described by the [node economics model](milestone-7-node-economics.md)
and 7.17B capacity analysis. Recompute those budgets after finality signing/proof
format selection; old 3 MiB/page/proof fit calculations are not automatically
valid with new context/round fields. No provider price or measured performance
claim is made here.

## 12. Versioning and activation implications

| Change | Required boundary |
| --- | --- |
| Durable read/union/count, all-writer monotonic guards, commit-before-publish, retry/reload | Local repair can retain active signed bytes/quorum/validity semantics; storage format change, if any, needs its own backup/migration review. No consensus-family activation inherently required. Preserve historical evidence. |
| Check a proof against an already pinned authorized static set | Can be local hardening only if it exactly preserves the approved historical authority; incompatible or unknown historical sets require explicit disposition, not relabeling old proofs. |
| New trusted genesis manifest, allowed N/f, changed q or membership transitions | Consensus-policy/profile activation; old proof rules stay historical. Changing runtime configuration is not authenticated reconfiguration. |
| New direct G/set epoch, round/step/type/justification signed fields | New closed signing/proof version/domain and vectors; never reinterpret the existing v1 or inert v2 signed payload. No finality bytes in their own block preimage. |
| Immediate finalized-parent gate, commit priority over provisional score, or pipelined commit semantics | Explicit active behavior/availability/fork-choice change with agreed activation anchor, mixed-version handling and historical verifier dispatch. |
| Proof transport alone | Can be wire capability extension with bounded parsing/version negotiation; does not inherently change block hashes. Old peers unable to verify required proofs must remain incomplete at the new profile. |
| Reviewer P4/C3/V4, event/control kinds, clock and exact rational fork choice | Separate history/profile/policy and preimage amendments, renewed resource vectors and activation approval; do not activate canonical_v3 as a shortcut. |

Before any live change choose approved release identity, activation anchor and
old-state disposition. Alternatives are preserving old trusted-finality history
under its honest scope, an explicitly trusted checkpoint boundary (which changes
fresh verification trust), or a separately approved new-network genesis. No
conversion can retrospectively make old trust-based history Byzantine safe.
Neither a reset nor checkpoint trust shortcut is selected here. Freeze the
initial authority/policy with an owner-approved distribution mechanism; a peer
advertising the same root is not that approval. No arbitrary new protocol-family
number is assigned merely to name this work.

## 13. Bounded, separately testable remediation roadmap

Each row is a separate future review/commit unit. No unit begins in Task 7.17D.
Split a unit further when needed; do not bundle activation with implementation.
The dependency order places complete protocol specification before live signer
or round logic, even though local durability can proceed independently.

| Unit | Scope and likely modules | Prerequisites | Acceptance tests and invariants | Active behavior / activation |
| --- | --- | --- | --- | --- |
| R0. Owner/security contract and finality specification | Approve A/B/C, independent operator assumptions, N/f/q, static authority, parent rule, complete agreement variant and signing/proof grammar; decision/spec docs and independent vectors | This decision; owner choices in section 15 | Check quorum inequality across allowed counts; model hidden QCs, cross-round locks, ancestry, proposer failures and termination assumptions. S1–S6, S11–S12 | Documentation first; no activation. Gate for semantic/signing implementation |
| R1a. Atomic received-vote/QC promotion | Move finality operation into durable mutation; publish/ack after commit; `blockchain.py`, `services/finality_service.py`, `storage.py` | Can begin as local repair in a new task; preserve existing policy | Concurrent same-facade/process votes, q-th vote race, pre/post commit kills, failure and exact retry. S7, S10 | Local fix; no new consensus/signing format; no activation needed if validity semantics preserved |
| R1b. All-writer monotonic finality and recovery | Guard generic/low-level saves, mint/reorg/import/backup; durable revisions, ancestry-preserving merge, committed-cache refresh; `storage.py`, `blockchain.py`, `storage_tools.py`, reorg service | R1a storage contract; inventory all writers | Stale facade/DB connection erasure, chain-head-unchanged finality race, reorg-vs-QC ordering, corrupt/stale backup, busy/full. S7–S10 | Local fix; explicit storage compatibility review if format changes; do not migrate live DB in tests |
| R2. Authenticated static authority and quorum verification | Manifest/policy verification, historical proof trust adapter, declared budget/config validation; config/genesis/finality validators and new profile module | R0 authority/quorum decision; R1 | Disjoint/stale/self-declared sets, wrong G/N, allowed/forbidden N/f, old profile dispatch, forged epoch. S1, S4–S6, S9 | Existing policy checks harden locally where already authorized; changed N/q/authority needs approved profile activation |
| R3. Durable signer primitive and protocol adapter | Isolated signer state store, reservation/signature-release API, fencing, exact canonical message formats; new signer module, protocol signing helpers, storage adapter | R0 complete signer/round specification, R2; R1 reused where relevant | Crash at reservation/sign/release boundaries, concurrent processes/peers, duplicate bytes, stale backup/owner, cross-genesis reset and lock evidence. S3–S5, S7 | Inert first; no production signer enabled. New signatures/round semantics require activation |
| R4. Agreement and safe round recovery | Implement selected B extension or C integration with proposer/view/lock/commit rules and finalized-parent adapter; new consensus service, production/validation/fork-choice adapters | R0 complete proof/transition contract; R1–R3 | Conformance/model traces, 2+2 split, hidden QC, old/future views, stalled proposer, Byzantine messages, lock-holder restart. S1–S6, S12 | Material consensus/liveness change; versioned inactive profile until separate activation |
| R5. Proof/authority sync and independent recovery | Bounded proof inventory/pages, same-tip reconciliation, missing-proof requests, retained conflict evidence, source verification/import and cursor; peer sync/routes, protocol peer messages, storage tools | R1/R2; R4 proof format for target profile | Fresh node genesis-to-tip, same tip/different QC inventory, incomplete pages, alternative valid same-target QCs, contradictory targets, wrong authority and full originals. S4–S12 | Proof transport may ship separately under old rules; target semantics remain version gated |
| R6. Multi-node adversarial/reliability gate | Deterministic scheduler/model plus real isolated-node databases/processes and fault injection; consensus/integration tests | R1–R5 | Section 14.1 matrix; safety under all schedules within f, convergence after GST with valid candidate, explicit stalls beyond assumptions, restart/corruption/full-disk recovery. All S invariants | Tests only; no activation. Failures block target release; keep witnesses |
| R7a. Re-review history/clock/admission amendment | Approve revised FP/signatures, strict-media vs control history, unminted acceptance, selection/all-unsure, preliminary media, quotas/penalties/ISSUE and budget changes; new amendment docs/vectors | R0, completed finality evidence R6; remaining 7.17A/B choices | Noncircular dependency graph; exact source inventory, fit/resource accounting, no admission bypass. S1–S12 foundation | Specification only; new history/profile approval required |
| R7b. Resume Task 7.17 only by separate instruction | Source-authorized journal/replay/branch claims integration; history/coordinator/new profile modules | R6 and approved R7a, independent vectors | Two independent DBs derive identical prefix/state/eligibility/usage/C3 after varied insertion, crash and permitted provisional reorg; finalized replay never rolls back | Future implementation and activation reviews; not started or automatically authorized |

Proof transport and protocol-independent signer-store experiments can be developed
inertly after their specifications are frozen, but cannot invent authority or
commit rules to bypass R0. Do not deploy a receive-side durability fix as evidence
that the new network security model has been achieved.

## 14. Verification record and adversarial test contract

### 14.1 Required future tests, with actual oracles

Use independent canonical/signature vectors, a deterministic network scheduler
and fresh per-node databases. Assert identical decision/ancestry and retained
signing state, not just equal tip summaries. Tests of unavailable inputs must
distinguish explicit incomplete/local-failure outcomes from protocol rejection.

| Test family | Required schedules and acceptance oracle |
| --- | --- |
| Same-height conflicts/Byzantine quorums | Enumerate small-N signer partitions and all approved N/f/q; Byzantine shared intersection signs both. Within f, honest finalized targets agree. At/outside safety bound, reproduce witness and detect/halt on both QCs; do not claim beyond-bound prevention. |
| Cross-height/competing forks | Hidden X@h QC followed by incompatible child at h+1 and gapped proof at h+2; reject unsafe commitment under selected parent/lock rules. Safe child must preserve every earlier finalized anchor; originality score never overrides it. |
| Quorum intersections | Independent set enumeration and threshold inequality, including N=1,2,3,4,5,7,10,13 and rejected configurations. Test `2f+1` misuse on oversized sets and no empty-set finality. |
| Concurrent/stale writes | Barrier two vote calls before durable read; two processes/connection snapshots; stale whole-document/low-level save after QC with unchanged head. Union retains both votes/QC, stale ancestry rejects, acknowledged finality survives. |
| Durable signing | Kill before/after reservation, signature persistence/release and acknowledgement; restart with duplicate/conflicting requests from different peers/processes. Exact signature replay or fail closed; no forbidden extra signature. Restore stale image and cloned-owner tests. |
| Split votes/proposer failure/view change | 2+2 split at N=4, silent/invalid/equivocating proposer, hidden prepare/commit QC and locks in several rounds. Selected protocol eventually decides after assumptions hold without violating earlier possible commits; sign-once option explicitly remains stalled. |
| Partition/reconnection/delayed finality | Schedule quorum/minority partitions, duplicate/reordered/old/future messages, healing and restart mid-round. Safety throughout; conditional progress after GST; no timeout-based quorum reduction. Delayed valid commit proof remains valid. |
| Membership and keys | Wrong/stale/disjoint set, forged set digest/epoch, attempted silent config change, key compromise within/exceeding bound. Static profile rejects all changes; any future dynamic profile tests full handoff and delayed old-epoch votes separately. |
| Wrong context/purpose | Independently vary N, G, protocol/profile, epoch/set, height, parent/hash, round and step; cross-purpose votes/timeouts never count as commits. Old v1/v2 fixture signatures retain original semantics. |
| Rollback/reorg races | Reorg-vs-finalization in both commit orders, deeper higher-score fork, stale import/backup and stale callback. Finalized ancestry never detaches; unfinalized suffix can reorg with branch-specific claims. |
| Fresh bootstrap/proof synchronization | Separate nodes start only with approved genesis and sources; fetch missing intermediate blocks, originals, authority and required proofs including same-tip case. Validate exact prefix independently; no database image or peer label grants authority. |
| Corrupt database/missing proof | Truncate/tamper QC/target/authority rows, corrupt indexes, missing original, foreign-key/integrity failure, skipped proof page and mismatched cursor. Fail closed or rebuild derived state from verified sources; never silently initialize empty finality/signer history. |
| Storage failures | Busy at begin/commit, real SQLite full-page-limit, injected I/O/sync failures and process death pre/post commit; prove old-or-new transaction outcome and durable retry, no premature finality/signature publication. Test platform durability separately from process-kill rollback. |
| Reviewer replay/reorganization | Same approved prefix and event order -> identical eligibility, promotion/penalties, quota, ISSUE and snapshots in independent DBs; later penalties cannot rewrite past certificate. Drop sources -> incomplete. Losing provisional sibling releases only its branch claims; finalized sources/claims remain. |
| Resource/availability | Max originals/proof/page/message/round buffers, malicious view spam, bounded verification workers, pending lock evidence and disconnected proof sources. No hash-only media shortcut or unbounded proof fetch; report measured CPU/disk/bandwidth and censorship limits. |

Preserve current witnesses and add expected-safe regression coverage in repair
tasks. Passing tests that document a bug cannot be relabeled as a fixed bug, and
failing adversarial tests must not be weakened/deleted to obtain a green gate.
Model checking explores bounded state/schedules and complements, not replaces,
the protocol proof and actual multi-process storage/network tests.

### 14.2 Tests executed for this documentation task

Runtime: Windows CPython **3.13.5**, SQLite **3.49.1**. Tests run unchanged with
workspace TEMP/TMP and separate disposable basetemps/logs under ignored `temp/`.
No test opens a live chain database. All results below are from this task, not
copied historical pass counts.

| Run | Selection | Result |
| --- | --- | --- |
| Core | Task 7.17C diagnostics; Task 3.5 quorum, Task 3.6 public status, v1 lifecycle; consensus services, canonical reorg recovery, atomic reorg recovery, two-node consensus verification | **69 passed in 39.91 s**, including all 17 unchanged diagnostic cases. `temp/task717d-core.log`, `.xml` |
| Peer | Chain sync API, block sync API, certificate sync API, certificate block validation | **65 passed in 52.68 s**, host run; `temp/task717d-peer-host.log`, `.xml` |
| Isolated storage | Existing atomic success/settings, busy-local-failure, lost-acknowledgement, actual disk-full/local-worker failure and affected-WAL refusal cases from Task 7.16 | **5 passed, 44 deselected in 69.13 s**; `temp/task717d-storage.log`, `.xml` |
| Independent arithmetic diagnostic | Exhaustive **526,118 ordered quorum pairs** for the eight requested counts; all f values for N=1..13 checked against the feasible q interval | **Passed**; `temp/task717d-quorum.log`. No keys, signatures or new protocol implementation |

Distinct completed test cases: **139 passed, no failures/errors/skips**. The
storage selection's 44 deselections were outside its focused scope; optional WAL
process-death tests were not selected and are not claimed verified. The affected
runtime refusal test passed. No live WAL mode or runtime upgrade was enabled.
The first sandbox peer run produced no completed result and was interrupted;
the unchanged selection then passed with host access, using fresh workspace
TEMP/TMP and basetemp paths. This matches the Task 7.17C documented Windows
TestClient/asyncio loopback-socket sandbox stall. No assertions or fixtures were
modified; the incomplete `temp/task717d-peer.log` is not a passing run. Automatic
approval review permitted the host rerun; no approval rejection occurred.

Reproduction selection (use fresh basetemp/output names for another run):

```powershell
$env:TEMP=(Resolve-Path temp/task717d-runtime).Path
$env:TMP=$env:TEMP
.\.venv\Scripts\python.exe -B -m pytest tests/test_milestone_7_task_7_17c_finality_audit.py tests/blockchain/test_task_3_5_validator_quorum_finality.py tests/blockchain/test_task_3_6_public_finality_status.py tests/blockchain/test_protocol_v1_lifecycle_finality.py tests/services/test_task_9_consensus_services.py tests/services/test_task_4_7_canonical_reorg_recovery.py tests/integration/test_task_4_7_atomic_reorg_recovery.py tests/integration/test_two_node_consensus_verification.py -q --tb=short --basetemp=temp/task717d-core-repeat
.\.venv\Scripts\python.exe -B -m pytest tests/api/test_chain_sync_api.py tests/api/test_peer_block_sync_api.py tests/api/test_peer_certificate_sync_api.py tests/blockchain/test_certificate_block_validation.py -q --tb=short --basetemp=temp/task717d-peer-repeat
.\.venv\Scripts\python.exe -B -m pytest tests/test_milestone_7_task_7_16_atomic.py -k 'affected_wal_runtime or atomic_success_proposal_indexes or busy_is_local_failure or lost_acknowledgement or worker_unavailable_and_actual_disk_full' -q --tb=short --basetemp=temp/task717d-storage-repeat
```

The arithmetic diagnostic enumerates all size-q subsets of `range(N)`, computes
every ordered pair's intersection, checks the minimum equals `2q-N`, and retains
a witness attaining it. Independently enumerate integer q=1..N for every f=0..N-1
at N=1..13: feasible iff `N>=3f+1`, minimum feasible q is `(N+f)//2+1`. This
validates set arithmetic, not signer correctness, signatures or distributed
agreement. Existing diagnostics explicitly reproduce unsafe behavior; their
green result means the finding remains demonstrable. No new target protocol,
multi-node Byzantine implementation or reviewer journal is claimed verified.

### 14.3 Final repository/document checks

UTF-8/no BOM, final newline, local links and whitespace checks passed. JUnit
reports independently confirm 69 + 65 + 5 passing cases, with no failures,
errors or skips. Final worktree scope is exactly this untracked decision document
and the unstaged 11-line follow-up in the tracked audit; removing that follow-up
reproduces the original audit text exactly. Branch and full HEAD remain as in
section 1; the index is unchanged/empty of staged changes. `git diff --check`
passes. No full-repository test run or mainnet/public deployment readiness is
claimed.

## 15. Remaining owner decisions and gate status

| Decision | Alternatives requiring approval / current gate |
| --- | --- |
| D1. Network security objective | A trusted coordinated demonstration; B independent permissioned BFT testnet (recommended); C permissionless network requiring separate admission research. **Not selected by this task.** |
| D2. Validator authority/fault budget | Actual independent operators, pinned genesis/release distribution, N/f/q and key custody/historical compromise assumptions. Recommend static `N=3f+1`; no actual identities or launch values chosen. |
| D3. Distributed agreement | Accept sign-once stalling under A; select a complete reviewed B round/lock/commit contract; or C separately versioned engine/adaptation. Safe failover **BLOCKED** until chosen and proved. |
| D4. Parent/fork-choice/activation/history disposition | Immediate finalized-parent versus separately proved pipelining; approved commit priority over unfinalized score or another proved compatible rule; old trusted-history treatment and explicit mixed-version activation anchor. No reset, retrospective upgrade of old proofs or launch activation assumed. |
| D5. Membership loss and safety-fault recovery | Static set may halt beyond availability bound. Dynamic transitions or extraordinary recovery require a distinct authenticated governance/transition design; no unilateral replacement or fork-choice rollback. |
| D6. No-media history/clock | Strict every-block-is-media with disclosed stalled clock/unminted-event limits, or explicitly approved distinct control-history order/clock/pacing/economics. 7.17B history blocks are not silently authorized. |
| D7. Reviewer semantics/admission | Bootstrap grants, exact cohort/all-unsure handling, preliminary unreviewed full-media archival, objective offense/inclusion timing, global issuance permanence and source completeness. Existing A/B frozen proposals remain for review. |
| D8. Storage/recovery operating profile | Supported filesystem/durable sync, signer exclusivity/backup fencing, source/proof retention and cross-store co-location versus recoverable cursor/outbox. No unproved multi-DB atomicity or unsafe WAL bypass. |

**Can finality repair begin?** R1a/R1b local durability defects and acceptance
tests are concrete enough for a separately authorized implementation task now;
they do not require pretending that B/C is already selected. R0 owner/security
decisions can proceed alongside that repair. Live signer/round/quorum changes
must wait for their complete approved contract and version boundary.

**Can Task 7.17 eventually resume?** Yes, conditional on passing the finality
foundation gate R0–R6 and separately resolving/amending the reviewer-history,
admission and no-media progress gates R7a. **It remains BLOCKED now and is not
resumed.** Task 7.17D produces a reviewable remediation specification only.
