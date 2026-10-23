# Milestone 7 Task 7.17B — Reviewer-history protocol amendment

Date: 2026-10-22 (America/New_York).

**Reviewable amendment, not approval or implementation. Task 7.17 remains
BLOCKED.** Recommend a genesis-authenticated bootstrap, a complete in-block
event journal, deterministic replay, and atomic admission of a media submission
and its new signed reviews against a finalized parent. Do not require that
submission's media and votes to have been finalized in earlier blocks. This
removes the mandatory preliminary-media copy in Task 7.17A's proposal.

Use an authenticated replay commitment, not a sparse Merkle tree, for this
archival-validation milestone. Specify self-contained fixed-set finality proofs
as the candidate rule; do not let local equivocation observations change their
quorum. The latter is a substantive consensus amendment requiring approval.
The repository still lacks sufficient proposal/locking/round-change rules to
establish finality liveness, particularly with competing sibling proposals.
No local journal implementation can fill that gap.

This document supersedes the conflicting *proposals* in
[Task 7.17A](milestone-7-v2-reviewer-history-consensus-decision.md) only if
approved. The Task 7.17A document and all implemented canonical schemas remain
unchanged. “Must” below defines this candidate profile, not permission to
activate it. Section 15 distinguishes specified rules from unresolved approval
and protocol gates. No independent-node interoperability has been demonstrated.

## 1. Repository verification and audit

- Branch: `Compression-State-Bloat-and-Node-Economics`.
- HEAD: `9894bb95a2c6ec8947af397e4f40882f7bf014e7`, separate Task 7.17A commit,
  `Milestone 7 Task 7.17A: specify consensus-authenticated reviewer history`.
  Its two files are the proposal and blocker-report pointer; no canonical module
  changed relative to parent `9198709`.
- Initial worktree/index clean; no applicable repository/ancestor AGENTS.md.
  The previous proposal and approved v3 schemas match committed HEAD.
- Only this document and a new link/gate-status paragraph in the
  [Task 7.17 blocker report](milestone-7-v2-history-freeze-and-recovery.md)
  are changed. No source, schema, fixture, dependency or active state change;
  no key creation, commit, push, merge, reset, migration, activation or deployment.

Read the required proposal/blocker and
[schema](milestone-7-v3-canonical-schema-decision.md),
[signing](milestone-7-v3-signing-and-domain-separation.md),
[issuance](milestone-7-v2-evidence-issuance.md),
[atomic certification](milestone-7-v3-atomic-certification.md) and
[block implementation](milestone-7-v3-block-format-implementation.md) reports.
Source is the authority for existing behavior:

| Inspected source | Existing behavior and consequence |
| --- | --- |
| [milestone5_policy.py](../milestone5_policy.py), [reviewer eligibility](../services/reviewer_eligibility_service.py) | Empty bootstrap set; finalized activity, earliest qualification, probation, quotas and separate established requirement. No local status label can authorize a new reviewer. |
| [blockchain.py](../blockchain.py), `cast_signed_submission_vote_operation`, [reviewer_reputation.py](../reviewer_reputation.py) | Local accepted/rejected observations and challenge state drive participation/offenses. Offense verifier requires protocol 1. Neither a signature nor SQLite receipt time proves consensus acceptance. |
| [dual_review.py](../dual_review.py), [admission_certificate.py](../admission_certificate.py), [canonical evidence](../canonical_v3/evidence.py) | Five eligible votes, at least one established per dimension; equal weights; unsure outside decisive denominator; integer 70% threshold. C2/V3 schemas are closed. |
| [canonical block](../canonical_v3/block.py), [construction](../canonical_v3/construction.py) | Media-only block 3; certificate precedes block hash; separate finality; no history extension. Format validation does not confer consensus authority. |
| [history](../canonical_v3/history.py), [atomic store](../canonical_v3/atomic.py) | Trusted local acceptance journal/image; permanent off-chain issuance reservations; selected claims branch-local. This cannot establish a distributed history prefix. |
| [finality](../canonical_v3/finality.py), [finality service](../services/finality_service.py) | External validator/equivocator context; locally known equivocations excluded; quorum `(2*n+2)//3`. No complete authenticated exclusion inventory or proposal-round protocol. |
| [fork choice](../services/fork_choice_service.py) | Cumulative originality is added and rounded to eight decimal places; ties use height then smaller latest hash. It cannot consume rational objects unchanged or specify finality rounds. |
| [genesis](../protocol_v1_genesis.py), [reorg](../services/canonical_reorg_service.py) | Exact v1 genesis and hash-linked branch reconstruction/finalized protection. No new launch artifact, reviewer migration or control-block protocol exists. |

Audit of Task 7.17A:

| Proposal | Disposition in this amendment |
| --- | --- |
| Genesis-established grant | Retain explicit B0, no inherited scores/usage; spell out liveness/common-control limitations. |
| REGISTER/VOTE/ISSUE inventory | Sufficient for the five objective reviewer offenses if rejected/stale signed observations are retained and acceptance is a deterministic consensus transition. They do not cover subjective adjudication or validator discipline. |
| All inputs must already be authoritative at parent | Reject as a universal certificate precondition. It forces preliminary inclusion or a media-only lifecycle cycle. Allow atomic current-block registration/vote acceptance and ISSUE. |
| Earliest established plus fifteen | Retain as the conservative exact-set candidate, with a precise bounded current-input extension. Document all-unsure/cohort lock and censorship tradeoffs; acceptance of that policy remains a gate. |
| Sparse Merkle state | Unnecessary for full archival replay; replace with journal/replay commitment. No state-membership light-client claim. |
| Finalized-parent boundary | Candidate profile is precise but serializes progress. It needs explicit approval and a separate finality-liveness specification. |
| Local equivocation exclusions | Replace in the candidate finality policy with self-contained proof counting; no retroactive exclusion or rollback. Requires approval, not a claim of existing behavior. |
| Full preliminary media for every submission | Remove from ordinary atomic media admission. Keep optional full REGISTER when participation on still-unminted media is deliberately made authoritative. |
| Floating-point fork-choice integration | Newly identified gate: specify exact rational score units; existing service stays unchanged. |

## 2. Common primitives, versions and trust

`J` is Task 7.10A's strict sorted-key compact UTF-8 JSON, no BOM/newline,
duplicate keys, floats, invalid Unicode, normalization or coercion. Arrays have
the specified order. Reuse its Wallet, H64, ID32, UInt (actual integer, not bool),
Sig65, TimeUTC, Money, string and depth limits. `S(b)` is lowercase SHA-256 hex;
`D(x)=S(J(x))`. Native transaction aggregate alone retains ASCII-escaped `A`.
EIP-191 personal_sign uses the byte length and Keccak-256, not SHA-256 as its
signature digest; retain existing canonical recovery bytes/high-S behavior.

Recommended single PRELAUNCH profile:

| Component | Existing implemented isolated profile | Candidate amendment |
| --- | ---: | ---: |
| Protocol | 2 | **2**; no active protocol-2 history exists to preserve |
| Block | 3 | **4**, required kind/history fields |
| Certificate | 2 | **3**, seven new fields |
| Vote signature | 3 | **4**, directly signed G/reference/creator |
| Review / reviewer / reputation policy | 2 / 1 / 2 | **3 / 2 / 3** |
| Event / history policy / replay commitment | Not implemented | **1 / 1 / 1** |
| Bootstrap object | Proposal 1 only | **1** |
| Finality policy manifest | No such wire manifest | **1**, new explicit policy; counting semantics change |
| Finality signatures / native signatures | 2 / 2 | **2 / 2**, bytes unchanged |
| Technical / rights / encoding | 1 / 1 / 1 | **1 / 1 / 1**, unchanged |

Block/certificate/vote increments distinguish bytes already implemented in the
isolated laboratory. The Task 7.17A draft versions were never implemented, so
refining its draft event/replay definitions does not require event 2/block 5.
Protocol 2 remains the planned fresh-network protocol family; block 3 becomes
an archived engineering profile, not a permissive alternative accepted on the
new launch. Launch genesis MUST commit this one exact profile. If protocol 2
has actually been deployed before approval, this prelaunch premise fails:
BLOCKED, assign a separately approved activation/version plan instead.

N/W/G, policies, statement and validator set come from approved genesis/release
inputs. No actual launch values are chosen here. N MUST never be reused across
roots: creator-rights and finality signatures still do not directly sign G.
V4 and native U10 do. A peer-supplied hash/list cannot replace that trust origin.

## 3. Genesis bootstrap security

Retain the exact closed B0 proposal:

```text
{bootstrap_version:1,network_id:N,reviewer_policy_digest:RVP,
 reputation_rule_digest:REP,reviewers:[Wallet,...]}
```

Reviewers is sorted unique, proposed maximum 128; whole B0 <=8,192 bytes.
Wallets must be valid recoverable secp256k1 personal-sign identities; spelling
alone does not authorize votes. No signing secret/public-private key allocation
is created by this task. B0 grants underlying ESTABLISHED_REVIEWER status, not
validator status, balances, activity age, promotion receipts or immunity.
Validation can check only the canonical address spelling at genesis; control
of its key is cryptographically established by a valid later signature. An
unusable/uncontrolled grant is therefore a launch-liveness failure, not something
a Wallet-string parser can disprove. Any operational proof-of-control check
before launch must not become another undocumented consensus enrollment service.

**Optional reputation/quota state is forbidden in this clean bootstrap profile.**
Usage, offenses, penalties, replay ownership and probation receipts start empty.
There is no nullable “trusted old score” field. A nonempty initial schedule or
transitional history would require a different explicit import/bootstrap
profile and completeness authority. Legacy SQLite is not that proof.

```text
BD = D({domain:"zoidbergchain/reviewer-bootstrap/v1",network_id:N,payload:B0,
        protocol:"zoidbergchain",protocol_version:2})
```

Add a CLOSED `reviewer_history_genesis` value to the separately approved new
genesis payload, with exactly `bootstrap,bootstrap_digest,history_policy,
history_policy_digest,finality_policy,finality_policy_digest,validators`.
Bootstrap=B0; validators is a sorted unique Wallet list of 1..128, independent
of reviewer grants. Full policy bytes and digests must agree with the profile.
This extension <=98,304 bytes and the complete new genesis <=3 MiB; actual
genesis field integration and financial/media allocation fit still need review.
Do not alter the old v1 genesis or put G-dependent signatures/commitments into
the preimage which computes G. Compute G first, then post-genesis replay J0.

Independent nodes pin the approved release identity, recompute J(genesis), G,
BD, all policy digests and the validator set. Matching a peer's self-declared G
and BD proves no authority. The approved artifact distribution remains a launch
decision, not a new signing key/governance scheme invented here.

Minimum first-media condition is five distinct eligible NONCREATOR Wallets per
dimension, >=1 established in each; the same five can serve both dimensions.
All five may be genesis grants; one grant cannot replace five signatures.
If every possible first creator is itself in an otherwise sole grant group,
provide enough noncreator capacity; for example a five-member total group
cannot review one of its members' submissions without another eligible Wallet.
This is a condition, not allocation of actual launch people or values.

Bootstrap status is subject to exactly the normal quota, cooldown/suspension,
historical eligibility and self-vote rules. On expiry restore its underlying
established grant. Do not silently revoke it after an invented time limit or
mint new grants from an administrator. New nonbootstrap Wallets retain all
earned creator/native/mixed qualification and promotion paths.

An unavailable, malicious or commonly controlled grant set can stall or collude.
Distinct cryptographic Wallets do not prove independent humans/operators.
Genesis review must assess distribution and online capacity. Even positive
review quorum cannot bypass technical media validation, rights, original-use
claims, reward/ledger rules or validator finality. No protocol can guarantee
media approval when the required reviewers all refuse/unavailable. No emergency
admin approval or unilateral replacement is authorized. Empty bootstrap remains
possible only through a separately deliberate long startup using native
activity plus unminted participation in control history; it is not the default.
That ordinary earned path also provides conditional recovery from unavailable
bootstrap reviewers: funded nonbootstrap Wallets can qualify through finalized
native activity, accumulate ten distinct valid probationary participations on
fully registered unminted targets, wait the required epochs, then become
established. Individual VOTE acceptance does not require a media certificate's
established seat. This needs live control-block finality, funding and actual
participation; it cannot guarantee rescue from a malicious/stalled validator
set. Existing penalties mask status, not a new pause of the finalized-height
clock or a discretionary exemption from the earned paths.

## 4. Closed event model and authenticated causes

There is ONE canonical block chain, no second journal authority. Every logical
REGISTER/VOTE/ISSUE event is either explicitly stored in `reviewer_history.events`
or deterministically extracted from existing mandatory media/certificate fields.
Never store duplicate selected vote/ISSUE/media bytes just to express that same
transition. The implicit extraction is part of the new protocol, not optional
convenience parsing. The whole canonical R authenticates each source location.

An explicit event is exactly `{event_id,body}`. Body has exactly
`domain,event_version,network_id,genesis_hash,parent_height,parent_hash,kind,payload`.
Domain=`zoidbergchain/reviewer-event/v1`, event_version=1; N/G exact; parent
height/hash equal the containing block's finalized parent F. `event_id=D(body)`.
Implicit events use that IDENTICAL body/hash definition; their serialized source
is indicated by deterministic extraction, not by another wire field/signature.
No current block hash/post-commitment/certificate ID is in a VOTE body.

| Kind | Exact payload and bounds | Authentication and transition |
| --- | --- | --- |
| REGISTER | Exactly `submission_id,content_hash,creator_wallet,content_type,media,meme_text,technical_evidence,attestation`. Existing descriptor/17-field technical/14-field rights; meme_text required null for no caption/text, otherwise existing caption bound. Full event <=2,883,584 bytes. | Recover creator; validate rights interval at registration and reconstruct/safety-validate full original bytes. H/length/MIME/policy all agree. It creates immutable submission/creator binding. No eligibility/activity credit just for registration. |
| VOTE | Exactly `signed_vote`, whose exact fields are `payload,signature_scheme,signature`; scheme=personal_sign, Sig65, V4 below. signed_vote<=4,096, message<=2,048, event<=8,192 bytes. | Recover signer, validate signed context and target; derive acceptance/rejection, quota and any objective offense. Retain well-formed rejected/stale observations. No unsigned “accepted”, eligible, offense or status flag. |
| ISSUE | Exactly `certificate`; C3 below <=196,608, event<=200,704 bytes. | Full deterministic selection/history/signature/tally verification. First issuance owns original/submission/certificate; not an administrator signature or a local operation ID. |

For a media block, extract REGISTER from its media, caption and certificate's
creator/technical/rights if not already registered at F. If registered, require
identical logical submission/creator/H/technical/rights/content/caption; another
permitted encoding must reconstruct the same original, not create registration.
For EVERY certificate offered for a new ISSUE (media or explicit ISSUE event),
extract VOTE from each selected record with no identical accepted receipt at F.
For an existing accepted receipt, verify exact frozen source equality and reuse
it; do not synthesize a new acceptance/quota charge. Extract ISSUE from the
embedded C3 unless that exact certificate is already issued at F. Look up the
accepted tuple FIRST: if one exists, a different choice/signature/metadata cannot
be supplied as a second selected receipt or relabeled as a new one; it can only
be a separate observation for rejection/proof. Finally derive
media settlement once. A control ISSUE with new selected votes requires a
target REGISTER in F or its explicit current registration; C3 alone contains
no full original and cannot synthesize REGISTER. Multiple certificates share
the same bounded raw vote pool for ordering/quota checks; VOTE IDs never depend
on any ISSUE ID. An earlier issued C3 is verified at ITS issuance source,
not regenerated against the current media parent.

Explicit events provide unselected/new/rejected observations, unminted
registration/participation and issued-but-unminted certificates. Explicit copies
of an implicit event in the same block reject as duplicates, not silent dedup.
Exact repeated relay across blocks is a derived semantic duplicate, with no
extra participation/offense/claim. Duplicate REGISTER/ISSUE on ancestry rejects;
an identical client retry returns the existing source rather than a new event.
Conflicting creator/H for the same submission or conflicting issuance rejects.

Full preliminary REGISTER is OPTIONAL. It is necessary only if a node wants
consensus participation on a media submission that is still unminted; then its
bytes really must be available/validated. A hash/URL/producer assurance cannot
substitute. Ordinary first-time media admission uses its own canonical media
once. A REGISTER creates a technical preliminary record, not an accepted/minted
media submission or a reward. This is an explicit optional archival cost.

### 4.1 V4 and certificate records

Refine Task 7.17A's V4 draft with ONE additional directly signed creator binding.
Atomic registration can be contemporaneous with a review's inclusion, so an
unsigned later creator assignment must not manufacture self-vote misconduct.
V4 is a flat CLOSED **19-key** object:

```text
domain,network_id,vote_version,policy_version,policy_digest,
reviewer_policy_version,reputation_rule_version,wallet_address,submission_id,
content_hash,dimension,choice,nonce,issued_at,expires_at,genesis_hash,
reference_finalized_height,reference_finalized_block_hash,creator_wallet
```

Domain=`zoidbergchain/community-review/v4`, vote_version=4, review policy=3,
reviewer policy=2, reputation rule=3. Other primitives/choices unchanged.
Creator must match the immutable target binding, including atomic registration.
For NEW countable acceptance, signed reference MUST equal F, exactly, and the
block timestamp lies in `[issued_at,expires_at)`. No local clock/receipt order.
Historic accepted records keep their own signed reference and frozen status;
their signature expiry is checked at original acceptance, not at later issuance.
For delayed objective proofs, ancestor references may be older, but must verify
on this branch; such records cannot earn new countable participation.

`M=J(V4)`, message_id=`S(M)`;
vote_identity=`D({payload:V4,signature:Sig65})`. Semantic observation identity is
message_id, so signature/high-S variants never create a second attempt.
The selected vote record is old VOTE_FIELDS plus `genesis_hash,creator_wallet`
(25 keys), same 4,096 cap. Its vote_message/identity/duplicates equal V4;
status/eligible are derived, with existing reference fields now directly signed.
Do not relabel V3 signatures. Rights retain their existing N-only domain/bytes.

C3 is old 18-key CERTIFICATE_FIELDS plus exactly seven fields:
`genesis_hash,history_parent_height,history_parent_hash,history_parent_commitment,
history_policy_version,history_policy_digest,selection_input_digest` (25 keys).
certificate_version=3, review_policy_version=3, history_policy_version=1;
parent fields identify the ISSUE parent F and its replay commitment. Technical,
attestation, two tally schemas and 32/16/4,096 vote bounds remain, with amended
policy constants. Digest is `D(C3 without certificate_digest)`, no extra envelope
or new certificate signer. Whole C3<=196,608. Section 6 defines input_digest.

### 4.2 Every state-changing fact has a source

| Derived fact | Exact authenticated cause, not a local assertion |
| --- | --- |
| Identity / initial established | Recovered V4/rights Wallet; genesis B0 for grants. No additional reviewer enrollment authority is needed. |
| Registration/submission eligibility | Valid REGISTER source, full exact original, rights and technical policy validation. |
| Accepted participation and quota | Deterministically accepted VOTE on validated target, exact signed F, signature/interval/status/nonce checks and earlier ordered quota receipts. |
| Promotion / underlying status | Finalized creator/native activity, earliest qualification, elapsed epochs and distinct probationary accepted receipts; original source positions retained. |
| Demotion / reputation | One of the five objective incidents in section 7 derived from retained signed VOTEs and canonical references. No free-form score, majority “bad reviewer” accusation or admin label. |
| Offense escalation / penalty | Ordered distinct incident identities and reproduced schedule/intervals, not stored summary/recorded_at. |
| Duplicates / replay | Message/nonce and accepted tuple ownership; REGISTER rights claims; ISSUE original/submission/certificate claims; media settlement. |
| Issued-but-unminted certificate | Actual on-chain ISSUE, including optional control event. A service returning a certificate is an inert draft. |
| Finalized ancestry | Full hash-linked R plus self-contained quorum proof and genesis validator authority under the proposed finality policy. Not the reviewer journal by itself. |

No fourth REVIEWER event type is needed for these closed objective rules.
A VOTE may carry evidence that was withheld off-chain and is now included, even
when it is not acceptable for counting. The finding itself is a mandatory
deterministic output, not a discretionary OFFENSE command. An off-chain rate
rejection or administrator finding without these authenticated causes is not
recoverable and cannot produce a penalty. Subjective plagiarism adjudication,
collusion analytics, appeals, grant revocation, validator slashing or membership
changes require a separate approved authority/event protocol; NONE is supplied
by REGISTER/VOTE/ISSUE. No unknown event/extension dictionary is accepted.

## 5. Noncircular admission and finality lifecycle

For a child at h, F is EXACTLY height h-1 with its exact hash and a verified
finality proof (genesis is the approved exception). S_F is replayed state through
F. This profile never consults a node-local “latest finalized” timestamp. A
missing parent proof is incomplete, not permission to skip it or declare the
parent's bytes invalid. Only finalized parents may authorize accepted children;
sibling candidates can still compete provisionally. This serial boundary is a
proposal requiring approval, not current production behavior.

The actual current-block input inventory is:

1. Full parent canonical history/proof and genesis policies already available.
2. Independently signed rights and V4 records plus exact original media, which
   can be verified BEFORE inclusion but are not yet accepted consensus events.
3. The proposed candidate's explicit events and implicit media/vote/ISSUE
   extraction. Validation derives every outcome on a scratch copy of S_F.

Execute exactly this order:

1. Validate intrinsic versions, sizes, context and parent proof; derive the
   implicit/explicit raw REGISTER and VOTE event bodies without trusting C3's
   status flags or digest. Sort the combined stream by `(rank,event_id)`,
   REGISTER rank 0, VOTE rank 1, ISSUE rank 2; reject duplicate IDs. The explicit
   array itself must already be sorted; implicit/explicit duplicates reject.
2. REGISTER phase: verify original media/technical/rights and immutable target
   bindings. Current registrations may be targets for current votes. They do
   NOT qualify a reviewer as an earned creator in this block.
3. VOTE phase: use S_F reviewer status/age/penalty clock, plus earlier sorted
   current receipts for quotas/replay. Derive each outcome and incident outputs.
   No current vote promotes another vote's reviewer. New penalty intervals
   activate prospectively for children, not for another signature in this phase.
4. Form each candidate selection from parent accepted receipts PLUS accepted
   current votes. Recompute C3 input digest, selected set, record metadata,
   tallies, ratios and certificate digest; then execute ISSUE ownership in
   event_id order. Conflicting ISSUE claims invalidate the candidate atomically.
5. Validate existing ledger/native/reward order and media settlement. Current
   native/creator activity becomes finalized input for future reviewer queries,
   never for a vote in this candidate. Derive end-state receipts/penalties.
6. Compute the journal delta/commitment (section 9), canonical block envelope
   hash and R. The candidate is now fully validated PROVISIONALLY, with
   branch-owned effects; no public certificate-finality claim yet.
7. Obtain a quorum proof for the EXACT resulting block height/hash using the
   approved finality policy. Atomically promote its prefix to authoritative.
   Only then may h's state authorize child h+1. No finality material is in its
   own block/hash preimage.

The two phases “verify authenticated signed input” and “finalize consensus
acceptance” are distinct. A certificate does not need its own future block
hash or a previously finalized acceptance of every new vote. It requires signed
votes whose eligibility and current ordered admission are independently
checkable from S_F and the candidate bytes. Finality then authenticates that
whole acceptance transaction. This resolves the circular dependency without
requiring another copy of the media in a preliminary block.

Exact relative-height timeline, no deployment-specific values:

| Height/stage | Authenticated inputs available / effect |
| --- | --- |
| F at k | Genesis grants/earned state, receipts, penalties, quotas, J_k and finality through k are available. |
| Before candidate k+1 | Creator supplies fresh rights; five noncreator eligible Wallets can supply ten dimension-bound V4 signatures referencing `(k,hash_k)`. Media and signatures available, still off-chain drafts. |
| Candidate k+1 | One media descriptor, C3 selected votes and optional extras suffice. Implicit REGISTER/VOTEs/ISSUE are extracted; eligibility from S_k, accepted participation on scratch state; both quorums verified. No prerequisite k+1 finality. |
| Validated, not finalized | Exact R and branch-owned state retained; no accepted descendant. Concurrent sibling certification can use the same S_k; no global permanent consumption by either draft. |
| k+1 finalized | Its media/reward and receipts/ISSUE/offenses become authoritative. Losing sibling state is discarded. Penalty first discovered here constrains votes referencing k+1. |
| Candidate k+2 | Uses S_(k+1). New current votes reference k+1; historical accepted votes retain their original reference/status. No retroactive rewrite of k+1. |

### 5.1 Fixed references, concurrency and delayed finality

An UNISSUED C3 pins F and its current offered-vote inventory. If F advances
before inclusion, that draft cannot be silently reparented: regenerate C3 with
the new parent/history/input digest and revalidate. Previously accepted votes
can be reused unchanged. Still-unaccepted current votes require fresh V4
reference signatures/nonces; old ones become stale for counting. This cost is
explicit. Once ISSUE finalizes, its certificate bytes/reference are permanent
and may settle in a later media block unchanged (unless already settled).

Candidate timestamp changes need fresh interval checks; neither old accepted
votes nor registered rights are re-expired at certification. Current rights
and new votes must meet their inclusion intervals. Block timestamp remains
canonical decimal seconds, not a new TimeUTC wire spelling. Compare exact
integer microseconds using Gregorian UTC day arithmetic from 1970-01-01 and
decimal integer coefficients, never float timestamps/string ordering.

Serialize local candidate/source/claims/cursor writes in one transaction with
expected finalized parent comparison; a local writer lock is not cross-node
authority. Multiple candidate databases can legitimately retain different
sibling drafts. Only finalized inclusion makes claims permanent across nodes.
Stale parent or exhausted quota invalidates/rebuilds the draft with no partial
global ownership. A lost acknowledgement retries by exact block/event identity.

Delayed finality freezes F and therefore the authoritative reviewer clock.
Collecting drafts does not consume global quota. If their signatures expire,
refresh them; never use today's receipt time to change an old canonical verdict.
Stalled finality halts authoritative progress in this profile, including control
blocks. Section 8 explains why signatures/quorum arithmetic alone do not prove
that enough live validators will converge on one candidate.

History-kind control blocks remain a proposed escape from the MEDIA-review
dependency: they require full normal consensus/finality but no media quorum or
reward, and may carry events/native activity or be empty. They allow epochs to
advance while reviewers are cooling down and support unminted participation.
They do not bypass a stalled validator quorum. One accepted media still maps
to exactly one media block with its exact original; system history blocks are
an explicit extension of block kinds, not media batching or another chain.
If MODEL A is interpreted to prohibit ANY non-media block, this escape is
unavailable: when all reviewers are penalized and epochs require blocks,
restoration can deadlock. That alternative remains BLOCKED pending another
approved logical-clock/liveness design; no wall-clock pardon is invented.

## 6. Deterministic inventory, selection and identity

The authoritative HISTORICAL cutoff for a new ISSUE is end-of-parent F. Extend
that prefix ONLY with all proposed VOTE events for its target in this candidate,
including implicit new selected votes and explicit unselected/rejected votes.
Validate/accept those current receipts BEFORE selection, independently of C3.
This is a bounded, fully available current inventory, not a claim that every
signature ever cast off-chain is known. Already finalized negative/unsure
receipts cannot be suppressed from the parent inventory by a producer.

Each combined event's locator is `[height,ordinal,event_id]`; ordinal is its
zero-based position in the complete rank/id-sorted logical stream (<=256).
The source location in R (certificate vote index/media/explicit array index)
is a rebuildable retrieval index and never the ordering authority. Historical
receipt order is lexicographic locator order. At equal height, IDs fully order
the VOTEs without arrival timestamps, SQLite row IDs or threads. Duplicate IDs
reject; semantic duplicates/high-S variants yield no new accepted receipt.

Candidate ordering per dimension is ascending locator; one accepted receipt
per `(wallet,submission,dimension)`. Choose the earliest historically established
candidate as the mandatory seat, then the earliest fifteen OTHER candidates,
or all remaining when fewer. No established candidate -> incomplete; fewer
than five -> incomplete. Negative and unsure candidates are included by exactly
the same ordering, never replaced to obtain approval. Serialize selected union
by existing `(dimension,wallet,vote_identity)` order, not locator order, at most
16 per dimension/32 total. An oversized required selected record fails fit,
never causes substitution. Status is the frozen accepted status, not current
certification-time promotion/penalty.

```text
selection_input_digest = D({
 domain:"zoidbergchain/reviewer-selection-input/v1",network_id:N,genesis_hash:G,
 parent_height:F.height,parent_hash:F.hash,submission_id:ID32,content_hash:H,
 vote_event_ids:[ascending IDs of ALL current VOTE events in this block]})
```

Include all current observations, even rejected ones and other targets: their
earlier quota consumption can affect this target. Historical receipt
inventory is bound by F/J_F, not copied as a huge list. If no current VOTEs
are offered anywhere in the block, the list is empty. VOTE body/ID depends on
its raw signed input and F, not C3, its tallies or selection_input_digest.
To build: choose an offered input pool, verify outcomes/order, select, put
selected new records in C3 and the other current records in explicit events.
To validate: extract that same pool, rederive outcomes and exact equality.
This finite extraction/selection check has no hash/signature cycle; adding a
hidden/unselected current input changes input_digest and may change selection.

Per dimension let p/n/u be selected positive/negative/unsure, t=p+n+u,
d=p+n, e=established count. Require t>=5, e>=1, d>0 and
`p*10000>=d*7000`. Unsure counts for quorum and participation but not d;
all-unsure is unresolved. Existing tally fields are recomputed, with review
policy=3. Vote-set digest remains D of wallet-sorted
`{wallet,choice,identity,status}` objects. Reduced ratios use gcd, no rounding;
5/7 stays 5/7 and two positives plus three unsure gives 1/1. Both top-level
block ratios retain originality semantics, not a combined dimension score.

### 6.1 Determinism proof and selection alternatives

Assume same approved genesis/profile, canonical parent prefix, and candidate R.
Strict parsing yields identical raw records; implicit extraction depends only
on those records and replayed parent state. Event IDs, rank sorting and ordinals
are fixed. Induction over VOTEs gives equal signature/target/status/replay/quota
decisions and accepted receipts. Sorting those same receipts gives the same
mandatory established seat and next fifteen. Thus both nodes derive the same
selected records/tallies/input_digest/C3 and validity verdict, or the same
explicit invalidity/incomplete condition. This is a specification argument,
not an implemented independent-node test result. Builders with DIFFERENT
unpublished offered pools need not produce one identical proposal.

| Approach | Completeness / censorship / determinism / liveness |
| --- | --- |
| Exact-set rule above | Full committed parent inventory and all candidate-offered observations are available. An already finalized earlier vote cannot be omitted. Producer can still censor OFF-CHAIN observations or delay an ISSUE. Validators deterministically reconstruct one selection for given parent+candidate. Requires historical replay/indexes and current input equality. |
| Arbitrary valid bounded subset | C3 could prove validity of only its chosen 5..16 votes per dimension; no global-inventory selection proof. Validation remains deterministic for supplied C3, but builders can choose different certs even from the same history. Producer can ignore known finalized negative/unsure votes, e.g. choose five positives out of five positives and many negatives. More flexible and avoids cohort lock, but materially changes review semantics. |

Recommend exact-set as the conservative continuation of the approved frozen
FULL selected-set contract, conditional on explicit cohort-policy approval.
It does not solve censorship or prove absence of off-chain votes. In particular,
the earliest sixteen can all be unsure and keep that submission unresolved even
after later decisive votes; negative early cohorts can also prevent approval.
Do not falsely claim eventual media acceptance. Such media is not admitted
under this rule, even if technically valid. A rolling cohort/unsure-replacement
rule or arbitrary-subset policy could improve this liveness, but would be a
separate security-sensitive selection amendment: BLOCKED until approved.
Do not silently retry under another submission ID to erase adverse history.

C3 is stable for identical F/offered pool/frozen sources regardless of local
DB order or media encoding. Its digest changes if F/pool/selected bytes change.
Exact retry of finalized ISSUE returns its old bytes, not a new cutoff. The
first finalized ISSUE owns original/submission; no alternate encoding/policy or
certificate can remint it. Off-chain issuance has no permanent consensus claim.

Quota is charged at accepted VOTE, not ISSUE/mint. In epoch `F.height//5`,
parent status sets limit 5 probationary / 25 established, plus earlier ordered
current receipts. Two dimensions of one submission/epoch consume one; another
epoch can consume another quota slot but not another distinct promotion credit.
Rejected/duplicate observations do not consume participation. Unsure does.
Promotion requires >=3 epochs probation and ten distinct accepted probationary
submissions, including unminted ones whose REGISTER was fully validated.
Activity/age and qualification paths remain source policy values (age>=3 epochs,
creator 2, native 5 over >=3 epochs, mixed 1 creator+2 native). New activity only
affects children. Promotion cannot raise a same-block quota; next reference may
raise 5 to 25 without resetting usage. Epoch rollover namespaces usage instead
of deleting historical receipts. Parent-issued submissions are closed to NEW
accepted votes; delayed misconduct observations remain possible. This prevents
post-issuance participation farming and needs review as part of Reviewer 2.

## 7. Reviewer offenses, prospective penalties and evidence authority

Only the five existing objective offense families remain. Any peer, reviewer,
creator or block proposer may relay evidence; inclusion plus deterministic
verification authorizes the transition, not the submitter's role. A block may
not include a discretionary admin finding, penalty duration or eligibility
override. A signed statement authenticates its content; a subjective copyright,
plagiarism, collusion or moderation judgment is not thereby objective proof.
Such policy/governance is separate and BLOCKED absent explicit authority.

Incident ID is exactly
`D({domain:"zoidbergchain/reviewer-incident/v1",protocol_version:2,network_id:N,
genesis_hash:G,kind:<offense literal>,identity:<array below>})`.
Penalty ID equals incident ID. Source locators preserve the proof transcript;
signer nonce/message keys prevent high-S/identical replays counting again.

| Offense | Proof / exact identity array | Effect |
| --- | --- | --- |
| SIGNED_VOTE_EQUIVOCATION | Two V4s with same canonical target/creator, Wallet, H, dimension but distinct choices, both valid signed ancestor references; `[wallet,submission_id,H,dimension]` | One grouped incident, cooldown 3 then 10 epochs, third distinct incident onward suspension 25 |
| CREATOR_SELF_VOTE | V4 explicitly names the canonical creator equal to recovered reviewer; authenticated REGISTER/rights bind that target; `[wallet,message_id]` | Cooldown 1 then 3, third onward suspension 25 |
| RATE_LIMIT_ABUSE | Three distinct canonical VOTE receipts rejected specifically for quota exhaustion in one review epoch, with actual earlier accepted quota sources; `[wallet,epoch]` | Cooldown 1 then 3, third distinct epoch onward suspension 25 |
| VOTE_DURING_COOLDOWN | New authenticated V4 explicitly signs a reference whose replayed state has active cooldown; deterministic source penalty selected there; noncreator, no earlier accepted same-dimension conflict; `[wallet,source_penalty_id,message_id]` | Prospective extension below |
| VOTE_DURING_SUSPENSION | Same proof at a suspended signed reference; `[wallet,source_penalty_id,message_id]` | Record only, no shortening/removal of suspension |

First verify target/creator/policy/signature and ancestor reference. Malformed,
unknown/unavailable source history is invalid/incomplete, never evidence of
misconduct. For new counting, precedence is: semantic duplicate; accepted tuple
conflict; self-vote; stale reference; expired/not-yet-issued; nonce conflict;
parent active penalty; unqualified status; parent-issued closed submission;
exhausted epoch quota; accepted. Outcomes are those exact classes, with both
penalty statuses sharing penalty and exact retry sharing duplicate. A second
same-choice message conflicts with the accepted tuple but is not equivocation.
Two dimensions are separate tuples. Different choice proves equivocation even
if neither was accepted. First accepted choice is never removed by a later
conflicting statement.

Canonical accepted receipts, not standalone signatures, prove rate usage and
quota rejection. Store the first three qualifying excess locators per Wallet/
epoch; all other well-formed attempts remain observations. A later local claim
“these were rejected yesterday” proves no such event. Delayed stale signatures
alone cannot become historical quota rejections or earn participation. This
explicitly limits off-chain rate-abuse findings to application state unless
their authoritative receipts actually entered canonical history.

Derive equivocation/self incidents from the complete observation prefix, not
only accepted votes. For penalty-attempt incidents, signed penalty-bearing
reference is the objective proof: delayed inclusion cannot change that reference
to a new cooldown. Unlike Task 7.17A's blanket stale exclusion, this permits a
late proof of an ACTUAL signed penalized context. Old signatures referencing
pre-penalty state never prove a penalty attempt. This is a specified Reputation
3 amendment, not an inference from unsigned receipt/reference metadata.

For each triggering VOTE, derive new incident outputs ordered by fixed rank:
equivocation=0, self=1, rate=2, cooldown=3, suspension=4, then incident_id.
Earliest earlier observation proving a different choice and triggering locator
are the equivocation sources; single-source incidents use that VOTE; rate uses
the first three quota-rejected locators. Incident identity makes repeat proofs
idempotent. Escalation counts prior distinct incidents of that type in this
order. Mandatory derivation means a producer cannot include proof and omit its
penalty while retaining the same valid state.

An incident first proven in h activates only after h finalizes, at reference h,
with start_epoch=`h//5`; it first constrains child votes. Penalty intervals are
start-inclusive/end-exclusive `[start_epoch,start_epoch+duration)`. Epochs remain
five finalized heights; the first penalty epoch may be partial. Do not backdate
to the signed statement/reference. Newly proven incidents never invalidate
earlier finalized votes, ISSUEs, media or rewards. Current-height vote admission
still uses S_F; same-height penalties cannot punish another vote signed before
those penalties existed.

Overlaps use SUSPENDED precedence and maximum active end epoch; within chosen
status select source by greatest end_epoch then penalty_id. Escalating offenses
while suspended record sequence but add no new lower-priority interval, as in
existing schedules. A cooldown attempt uses the duration of its signed-reference
source penalty and creates a prospective interval ending at
`max(current_cooldown_end_or_start, h//5 + source_duration)`; never shorten an
active interval. If currently suspended, record only. A late proof can constrain
future eligibility after an old cooldown expired; it cannot reopen that past
epoch. Suspension attempts always record only. On expiry restore independently
derived underlying status, including a genesis grant; no current labels confer it.

A provisional new candidate still depends on its EXACT F, quota inputs and
unconsumed ownership. If another sibling wins/finalizes, discard/rebuild it.
If the same parent remains fixed, late local allegations alone change nothing.
After finalized ISSUE, historic accepted eligibility and certificate bytes are
immutable even if later penalties arise; a future media settlement verifies that
old issuance and current unspent media/reward constraints. No retroactive finality
exception, reputation-only reorg or hidden migration is authorized.

Evidence can be censored/withheld before inclusion; no protocol can prove every
off-chain signature exists. Once included, retain source bytes, locators and
canonical ancestry permanently. Anyone can fetch/replay it without knowing an
administrator or the original reporter. Validator equivocation is NOT a reviewer
offense and does not consume these schedules or grant reviewer demotion powers.

## 8. Finality proof policy, fork choice and liveness limits

Recommended new CLOSED finality-policy manifest FP has exactly:

```text
{finality_policy_version:1,validator_source:"genesis",membership_changes:false,
 quorum_rule:"ceil-two-thirds",proof_counting:"unique-genesis-signers",
 late_equivocation:"record-no-revocation",conflicting_quorum_proofs:"halt",
 parent_rule:"finalized-parent"}
```

FPD=D(FP), authenticated in genesis and HP. This is a new named policy format,
not a claim that existing finality policy already uses these semantics. Retain
the existing nine-field version-2 attestation, eight-field proof, signing bytes,
<=128 validators, <=1,536/1,024/262,144 record/message/proof caps and sorted unique
signers. The proof's list MUST equal the genesis-authorized fixed validator set.
Require q=`(2*n+2)//3` distinct authorized valid signatures for exact height/hash/N.

**A standalone proof never consults a locally supplied equivocator set.** One
validator contributes at most one signature in that proof. Learning another
same-height conflicting signature creates misconduct evidence but does not
retroactively subtract that signer, change q/membership, revoke a prior proof
or roll back finality. Two contradictory otherwise-valid quorum proofs mean
safety failure: stop advancement, preserve both and require a separately
authorized recovery decision; never choose by arrival/hash score. Under that
failure, fresh nodes shown only different withheld proofs may diverge until
the conflict is revealed. No claim of safety after the consensus fault bound.

No validator-discipline event is needed to reconstruct this fixed-set proof
validity: validator misconduct has NO automatic membership/slashing effect in
this profile. A two-attestation conflict can be independently checked/retained
as diagnostic evidence, but is not a sixth reviewer offense. If exclusion or
validator penalties are required, a minimal separate VALIDATOR_EQUIVOCATION
event would contain the two closed signed attestations and a deterministic
pair ID, authenticated by block inclusion; an approved prospective membership/
penalty policy would ALSO be necessary. That alternative is BLOCKED, not an
implicit use of local discovery. No such additional event is accepted here.

The conservative quorum's safety assumption must be stated exactly. Two
q-signature sets intersect in at least `2*q-n` validators; assume strictly fewer
Byzantine/equivocating validators than that intersection, and honest signers do
not authorize conflicting decisions at a height. Also need >=q available
coordinated signers for progress. For n=3, q=2, the intersection is one, so this
formula does NOT tolerate one Byzantine signer for unconditional safety. Do not
claim the usual one-third bound for every n. Changing to `floor(2*n/3)+1` is a
separate quorum amendment; retained q is not silently strengthened here.

### 8.1 Exact rational fork-choice adapter

Do not invoke the existing float/round service on rational block fields.
For this candidate profile, let L=lcm(1..16)=720720. Each valid media block's
reduced originality n/d contributes exact integer `n*(L//d)`; a history block
contributes zero. Cumulative score is the exact arbitrary-precision integer
sum (no float, eight-decimal rounding or coercion). Compare validated paths
sharing the approved genesis and not detaching finalized ancestry by score,
then height, then lexicographically smaller latest H64, retaining existing
priority order. The sum is a derived index, not a new block/preimage field.
No block is preferred OVER contradictory known finalized authority. Historical
v1 scoring remains unchanged. This adapter is a substantive new-profile rule,
requiring approval/tests; it is not present in source.

### 8.2 What remains BLOCKED about progress

Self-contained proof validity resolves observer-dependent counting; it does
NOT define how honest validators agree which sibling to sign, lock a proposal,
change rounds, recover from a failed proposer or release/reuse a signing lock.
Example: several valid k+1 media proposals divide honest first signatures so
none reaches q; “never double-sign” plus a finalized-parent child rule can then
stall indefinitely. Fork choice after seeing a later better proposal does not
by itself authorize safe revoting. A bare smallest-hash rule cannot promise a
globally known minimum among unpublished candidates.

Therefore finality-liveness/round coordination is a **critical unresolved
protocol gate**, even if this candidate FP is approved. Alternatives: supply
an existing audited agreement/round/locking specification with authenticated
messages and bounded resource rules, or separately design/review such a
protocol; a pipelined architecture also needs explicit finalized cursor,
advancement/expiry and pending-state rules. This task chooses none by arbitrary
timeouts/proposer keys or administrative override. Conditional on a valid parent
and a consensus-selected child obtaining q, replay is specified; guaranteed
progress and deployment readiness are not established.

## 9. Commitment architecture: archival journal, not mandatory sparse state

| Structure | Completeness and independent verification | CPU/growth/proofs/checkpoints/forks |
| --- | --- | --- |
| A. Canonical append-only event journal + deterministic replay | Full genesis-to-target canonical R authenticates every included input/order. Replay verifies acceptance, penalties, usage and selection. Signatures alone do not prove complete inclusion. | Incremental event/source checks and derived indexes; retain full history. Whole-prefix verification, no succinct state-membership proof. Branch-owned prefix/deltas; verified local checkpoints accelerate restart only. Simplest implementation surface. |
| B. Canonical logical snapshot + SHA-256 state hash | A snapshot hash is sufficient only when recomputed from authenticated complete sources; download plus matching self-supplied hash proves nothing. | Canonical full-state scan/hash grows with state size, potentially quadratic total work if repeated every block. Full snapshot is O(state) for sync/proof; historic snapshots per checkpoint also add storage. Fork-specific snapshots/cursors required. Useful diagnostic/export, unnecessary per-block consensus structure. |
| C. Sparse Merkle map + versioned proofs | Still requires source transition validation/availability. Merkle membership/nonmembership alone cannot prove no hidden accepted/offense events. | 256-bit paths, up to 256 path hashes/update; uncompressed sibling proof ~8,192 bytes plus key/value/wrapper. Extra tree nodes, encoding/cache/reorg proof rules. Can support future light clients, not needed for archival validators. Storage/CPU savings unmeasured. |

**Choose A.** A deterministic transition function bound by the approved policy
plus a commitment to all its authenticated inputs defines one state. Do not
call this an independently hashed full state map or a light-client proof.
The new block field is a *replay commitment*. A node MUST replay/verify sources,
not accept a downloaded state merely because its journal hash matches. No
sparse tree, state membership proof or snapshot trust shortcut is necessary.

The exact logical event stream is the rank/id-sorted implicit+explicit sequence.
Its bodies are recoverable from R. Let E be its ordered array of event IDs.
Define settlement as null for history blocks, or exactly
`{submission_id,content_hash,creator_wallet,certificate_digest}` for media.
The closed delta and roots are:

```text
delta_h = {block_timestamp:P.timestamp,events:E,
           native_transactions_hash:P.transactions_hash,settlement:settlement}
DD_h = D(delta_h)

J0 = D({domain:"zoidbergchain/reviewer-journal-genesis/v1",protocol_version:2,
        network_id:N,genesis_hash:G,history_policy_digest:HP,bootstrap_digest:BD})

Jh = D({domain:"zoidbergchain/reviewer-journal/v1",protocol_version:2,
        network_id:N,genesis_hash:G,history_policy_digest:HP,bootstrap_digest:BD,
        height:h,parent_hash:F.hash,previous_commitment:J_(h-1),delta_digest:DD_h})
```

The timestamp is essential: identical raw VOTEs before/after expiry can derive
different outcomes; omitting the deterministic time input would fail to bind
that distinction. Native aggregate binds full native activity; settlement binds
earned creator activity and mint claims. REGISTER IDs bind source media/rights;
ISSUE IDs bind full certificate bytes. No current block hash, proof, post-root,
SQLite image or local acceptance receipt enters these preimages. E is IDs in
logical stream order, not sorted by digest alone across different kinds.

J0 is computed AFTER G, not stored back into the genesis preimage. R's block
envelope includes parent_commitment and post_commitment=Jh; finality signs that
resulting block hash. An old proof authenticates its exact immutable parent R,
not just an unauthenticated root-shaped string. The chain/hash and E cover the
full event count and order without another journal chain/Merkle root/count field.
History-kind blocks with no events still commit their time/height/native input.

### 9.1 Exact derived-state inventory and canonical diagnostic snapshots

Maintain immutable input bodies/sources and derived facts sufficient for:
bootstrap digest; submission creator/H/technical/rights source; each first
semantic observation and outcome/source; accepted `(wallet,submission,dimension)`
and frozen status/reference; signer nonce/message ownership; distinct
`(wallet,epoch,submission)` participation; distinct probation receipts; native/
creator activity and earliest qualification; objective incidents/sequence/source
proofs; penalty intervals/duration/activation/source penalty; first three rate
excess locators; ISSUE ownership; minted media; and all replay claims.

The Task 7.17A section 8 closed logical fact kinds/identity/value fields remain
the diagnostic representation, with these precise refinements: observation
outcome additionally permits closed; selected V4 record contains creator_wallet;
the review claim literal is the existing `review`, not `vote`; a source Pos is
the combined logical locator defined here; a reviewer fact's penalty masking is
queried at the requested reference epoch, never stored as mutable truth. Source
penalty facts retain activation h separate from signed proof reference.
The SMT key/leaf/root formulas in that proposal are NOT this amendment's format.

A canonical diagnostic full snapshot is exactly
`{state_format_version:1,network_id:N,genesis_hash:G,history_policy_digest:HP,
height:h,history_commitment:Jh,facts:[...]}`. Sort facts by
`(kind, UTF8_bytes(J(identity)))`, with exact case/ASCII comparison and no
duplicates; each is the closed `{kind,identity,value}` from that logical table.
Full diagnostic bytes may grow with history; each individual fact<=262,144,
stream bounded pages rather than require one giant JSON allocation. Its optional
SHA-256 is diagnostic only, not a wire state-root field or additional authority.
No scalar float/reputation score, observed_at or current DB label is allowed.

Reviewer status is a deterministic QUERY at a specific prefix/epoch from those
facts. No rule requires rewriting every Wallet on an empty epoch-advance block.
Derived indexes may schedule/compute earliest age/qualification/promotion and
penalty expiry lazily as long as the exact query results match full replay.
Historic snapshots are reconstructed by prefix replay or already fully verified
local checkpoints. Without full verification, a snapshot is untrusted data.

Replay claims use unchanged existing preimage
`D({network_id:N,genesis_hash:G,protocol_version:2,kind,identity:[...]})`.
Kinds/identity arrays: original `[H]`, submission `[ID32]`, certificate `[C_digest]`,
attestation_nonce `[wallet,nonce]`, attestation_message `[message_id]`,
attestation_signature `[Sig65]`, review `[submission,dimension,wallet]`,
vote_nonce `[wallet,nonce]`, vote_message `[message_id]`, vote_signature `[Sig65]`.
REGISTER owns rights claims; first VOTE owns message/signature and unowned nonce,
accepted VOTE owns the review tuple; ISSUE owns original/submission/certificate.
Current implicit REGISTER can establish rights ownership once. Existing owned
nonce/different message is a rejection, never overwrite; a semantic retry adds
no signature-variant claim/attempt. Policies/encoding do not reset namespaces.
Only finalized ownership is permanent. Candidate-only claims roll back with
their branch; local off-chain issuance never reserves global ownership. This
explicitly replaces Task 7.16's laboratory permanence for unselected local issues.

## 10. Frozen schema and hash-preimage amendment

Closed HP manifest has exactly `history_policy_version,rule_set,
review_policy_digest,reviewer_policy_digest,reputation_rule_digest,
finality_policy_digest,state_commitment_version,limits`.
Values are version=1, rule_set=`zoidbergchain/reviewer-history/7.17b`, referenced
approved new policy digests, state_commitment_version=1 and the closed limits
table below. HP=D(that full manifest); referenced policies and FP are available
in full approved genesis/registry bytes, not arbitrary digest parameters at
validation time. A changed rule/cap requires a newly approved profile/digest.

| Exact limits key | Fixed value |
| --- | ---: |
| max_record_bytes | 3,145,728 |
| max_events | 256 |
| max_register_events | 1 (implicit plus explicit) |
| max_register_bytes | 2,883,584 |
| max_vote_event_bytes / max_vote_bytes / max_vote_message_bytes | 8,192 / 4,096 / 2,048 |
| max_issue_event_bytes / max_certificate_bytes | 200,704 / 196,608 |
| max_media_extra_bytes / max_history_extra_bytes | 262,144 / 2,949,120 |
| max_rest_bytes | 32,768 |
| max_native_count / max_native_record_bytes / max_native_array_bytes | 10 / 8,192 / 98,304 |
| max_bootstrap_reviewers / max_bootstrap_bytes | 128 / 8,192 |
| max_history_genesis_bytes / max_policy_bytes | 98,304 / 65,536 |
| max_depth / max_validators / max_finality_proof_bytes | 32 / 128 / 262,144 |

Each slash-separated key names a SEPARATE required member of limits. No slash
occurs in the actual keys. Depth applies to the complete received R, not each
component separately. Other frozen primitive/child limits remain mandatory.
The one-REGISTER cap limits expensive original-media validations; if a new media
block implicitly registers its target, defer another registration to a control
block. A media block on an already registered target can carry one other
REGISTER, with total fit required. No list of compressed preliminary media can
evade original-decode resource accounting.

New required `reviewer_history` has EXACT keys
`history_version,history_policy_digest,parent_commitment,post_commitment,events`.
history_version=1; roots H64 are J_F/Jh, HP exact; events is the explicit array.
All implicit+explicit events together <=256 and <=1 REGISTER. History roots and
all extra source bytes are inside the envelope hash preimage.

Media P4 is old exact PAYLOAD_FIELDS plus `block_kind,reviewer_history`, with
block_version=4, block_kind=`media`; retain old optional bounded image meme_text.
C3 replaces C2. Every old media/rights/technical/creator/ledger/reward/rational
binding remains and must agree with REGISTER. Exactly one unsigned creator
reward, native U10/T18 and original SHA-256/reconstruction/identity or zstd
remain. Selected vote bytes appear only in C3, not another VOTE array copy.
Previously finalized ISSUE still owns its old C3/reference; embedding it later
does not synthesize another ISSUE or change its selected records.

History P4 is exactly
`block_version,block_kind,index,previous_hash,timestamp,miner,native_transactions,
transactions_hash,reviewer_history`, with kind=`history`. It has no media,
creator reward, legacy transactions, admission certificate, minted_at or ratio
fields. Empty events/native arrays are valid if the block is consensus-authorized;
no fake submission or zero-vote certificate is used. These blocks carry no media
mining reward or new fee/incentive. All count for finalized height/epochs.

Block hashing stays
`h=S(J({domain:"zoidbergchain/block/v2",network_id:N,object_type:"block",
payload:P4,protocol:"zoidbergchain",protocol_version:2}))`;
`R=J({envelope:<that exact object>,hash:h})`. The required discriminator changes
the P preimage unambiguously; no second meaning under block_version=3. C3,
V4, event bodies, BD, HP, replay root and selection digest use their formulas
above. Finality signs h afterward under the unchanged finality/v2 message.
Native ID/aggregate, technical digest and creator-message domains remain as in
Task 7.10B/C; no hidden root in a nonce/policy ID or signer's message string.

Dependency DAG is:
`approved policies/B0 -> G -> J0 -> signed rights/V4 + media -> REGISTER/VOTE IDs
-> ordered acceptance/selection_input_digest -> C3 -> ISSUE ID -> delta/Jh
-> P4/envelope/h -> separate finality proof`.
Only already-finalized parent hashes/commitments occur in current signatures.
No current h/Jh/ISSUE ID is required to compute a current VOTE or its selection.

Reusable IMPLEMENTATION COMPONENTS later: canonical J/A and primitive parsers,
personal-sign recovery, native U10/T18, technical/rights formats, descriptor/
isolated reconstruction, integer tally/ratio arithmetic and fixed reward rules.
Replacement/new validators required: P4 kinds/history extraction, C3/V4 closed
schemas/signing adapters, replay/selection/claims, new genesis extension/profile,
standalone FP proof counting, exact fork-choice adapter and source-only storage/
sync/reorg verification. Existing finality.validate_proof's equivocators callback,
history._History's clocks and atomic snapshot images cannot be authoritative
adapters for this profile. Keep every existing canonical_v3 module/vector intact.

## 11. Capacity, fit policy and economics

Maintain the 3 MiB complete-R limit for both block kinds. For media define
L=base64 CONTENT bytes, C=len(J(C3)), T=len(J(native_transactions)),
X=len(J(explicit events)), Rest=len(R)-L-C-T-X.
Require C<=196,608, T<=98,304, X<=262,144, Rest<=32,768 and complete R<=3,145,728
SIMULTANEOUSLY. Roots/history keys/arrays/portable wrapper are included in Rest;
implicit source bodies are derived without another serialized copy. For history,
X<=2,949,120, T<=98,304, Rest=len(R)-X-T<=32,768; complete cap also applies.
Parent budgets are disjoint accounting, never extra capacity outside R.

Independently recalculated conservative maxima (serialized UTF-8, not purported
jointly attainable valid records/signatures):

| Quantity | Exact calculation / ceiling |
| --- | ---: |
| Encoded/original image cap; base64 L | 2,097,152; `4*ceil(2097152/3)` = 2,796,204 |
| Existing C2 closed-schema bound | 172,901 |
| New V4 message / compact signed_vote / selected record width bounds | **1,202 / 1,396 / 2,877**, all below retained caps |
| Seven new C3 members incl keys/quotes/commas | 517 |
| Additional bytes per selected V4 record versus V3, other widths held fixed | <=448 (including longer embedded signed message and two record members) |
| New C3 bound, votes still 32*4,096 + 33 | **173,418**, within 196,608 |
| Empty explicit-history object | 296 |
| Media block extra members versus block 3 | C3 517 + block_kind 21 + reviewer_history member 316 = **854** |
| Mandatory/max-width P4 media record, no optional explicit events, with max caption and ten max native records | **3,059,651** = old analytic 3,058,797 + 854 |
| Margin under 3 MiB | **86,077** |
| P4 history at full 2,949,120-byte explicit array and ten max native records, conservative widths | **3,032,032**, margin 113,696 |
| Parent-budget history ceiling | 2,949,120 + 98,304 + 32,768 = **3,080,192**, also below cap |
| B0 max-width 128-Wallet array/object | **6,061**, within 8,192 |

For an object use `2 + (k-1) + sum(len(name)+3+value_width)`; every new member
adds its comma as well. Both complete-object and nested caps apply. New V4
records must fit their actual 4,096 serialized/2,048 message bounds before
signing/admission; adding creator/reference/G is not permission to enlarge
votes. For the 19-key all-ASCII V4 object there are 14 string values and five
integers: 66 double quotes become 66 extra escape bytes when M is embedded as
vote_message; its quoted value is <=1,270. Full selected-record accounting
gives 2,877 without fabricating a signature. C's bound conservatively retains
4,096 per vote instead of assuming these widths are jointly attainable.
Technical 8,192, rights 16,384, two tallies 16,384, array delimiters and
existing scalar widths are included in C's bound. Depth and escaping remain
independent rejection gates. The whole maximal REGISTER fits its control record;
putting several inside a compressed blob is forbidden.

### 11.1 No size-induced circular wait

Before admitting/ISSUING a selected certificate, reserve the complete mandatory
identity-format MEDIA record with worst-width future header/caption/roots,
empty optional extras and, if necessary, no optional native transfers. Check
every actual field/child/parent cap. The bound above shows this base can fit
under the proposed limits even with ten native transfers; actual reservation
still runs and cannot be replaced by a media-size-only check. Freeze neither
an unrepresentable certificate nor a pending permanent original claim.

Choose an offered pool and freeze C3 only after its selection fits. Once frozen,
do not remove a selected negative/oversized vote or an offered input needed by
its input digest. The digest also binds other-target VOTEs affecting quota;
removing those requires rebuilding, too. Do not promise optional extras at their
maximum can coexist
with max media; defer them to history blocks BEFORE freezing that candidate,
or rebuild its whole unissued pool/C3. Mandatory registration/new selected
votes/ISSUE have implicit sources, so they do not need a preliminary record
or two C3 copies to make this reservation succeed. Parent advancement requires
the explicit refresh in section 5, not waiting forever on an old reference.

A finalized ISSUE in a control block additionally needs proof that its target
REGISTER exists in that block or F and its future mandatory media record fits.
Source media may later use another permitted encoding, but H/MIME/length/rights
and frozen selected evidence remain. There is no height-dependent growth of
certificate selection proof: the needed history is retrieved separately and
already authenticated; only <=32 selected records go into C3.

Empty/no-reward history blocks can advance epochs despite reviewer quota or
temporary penalties and can carry evidence deferred for space. They need live
consensus/finality and an approved production/pacing agreement. If all qualified
reviewers are absent forever, or validators cannot finalize, media liveness
remains impossible. These are availability/authority failures, not justification
to waive quorum, raise the cap, mint fake media or invent emergency authority.

### 11.2 CPU, retained bytes, bandwidth and three-year scenarios

One REGISTER per block bounds preliminary media validation; with one mandatory
media reconstruction and a distinct optional REGISTER only when the main target
was already registered, at most TWO originals of <=2 MiB each are reconstructed
per media block (control: at most one). Media safety may require larger bounded
image-worker pixel memory; existing decoder/platform gates still apply. Count
all implicit events in the <=256 event bound. A loose signature-work ceiling
is `256*33 + 33 + 10 + 128 = 8,619` verifications including a repeated media
certificate, native transfers and one maximal parent proof; this is deliberately
conservative and not a measured latency/throughput promise. Archival replay
additionally processes all ancestor inputs. Actual work/time/memory and lazy
index queries require adversarial resource measurement before implementation
is considered deployment-ready. No full-state scan/hash is prescribed per block.

Ordinary atomic media does NOT duplicate its media/selected votes/ISSUE just
for history. Optional preliminary REGISTER DOES retain another full encoding
before the eventual media block, plus its rights/technical evidence. Unminted
registrations and rejected VOTEs remain forever. Each VOTE event<=8,192 and
ISSUE<=200,704; replay claims are derived, not another on-chain per-key list.
One canonical source BLOB per R plus derived indexes/proofs is a reasonable
storage design; no measured BLOB/binary/SMT savings or SQLite amplification is
claimed. Keep existing supported safe transaction/journal runtime rules.

Formula: over three 365-day years, extra raw bytes are
`1095*(media_per_day*mean_extra_media_bytes + history_per_day*mean_history_R_bytes)`.
Add separately retained finality proofs if not already in those means, measured
DB amplification/indexes, backup copies, gossip/retries and bootstrap metadata.
Illustrative ASSUMPTIONS, not measured workload or prices:

- At 1,000 media/day the FIXED 854-byte certificate/header/history increment
  alone adds **935,130,000 bytes**, about **0.871 GiB**. This excludes V4 vote
  growth as well as optional events/control blocks/proofs; it is not total
  overhead or measured savings. Holding other field widths fixed, four added
  V4 signed members add <=290 message bytes, its fourteen extra quote escapes
  add 14, and two new selected-record members add 144: <=448 more per vote.
  With ten selected votes per media, a width-bound scenario is <=5,334 extra
  bytes/media or **5,840,730,000 bytes (5.440 GiB)** over three years; with 32,
  <=15,190 bytes/media or **16,633,050,000 bytes (15.491 GiB)**. No source data
  distribution, index/proof cost or runtime performance is inferred.
- At 100 additional history records/day averaging 65,536 bytes R, their extra
  raw three-year bytes are **7,176,192,000**, about **6.683 GiB**, before proofs.
- At 1,000 optional maximum-cap REGISTERs/day, their event bytes alone remain
  **3,157,524,480,000**, about **2,940.674 GiB**, before minting/proofs/indexes.
  Atomic media no longer REQUIRES that preliminary workload.

One complete independent sync needs at least the retained canonical bytes and
required proofs; p full replications send at least p times that amount, with
transport and retransmission added. Bootstrap B0 is kilobytes, not a daily
grant cost. All structures A/B/C retain authenticated history for full archival
validation; a sparse root cannot erase that three-year cost. Rerun the
[Task 7.8 model](milestone-7-node-economics.md) later with observed block rates,
source distributions, amplification, backups, proof traffic and replay CPU.
No new provider pricing/performance/economic benefit is asserted here.

## 12. Independent-node verification and recovery

1. Pin the approved genesis/release N/W/G/profile. Recompute exact genesis hash,
   bootstrap list/digest, full policy registry and fixed validator set. Compute
   J0 only after G. Old v1 history/SQLite images cannot confer new-network
   reviewer status or nonce/issuance ownership.
2. Fetch exact canonical R and required separate finality proofs in contiguous
   hash-linked height order from genesis to an explicitly claimed target.
   Enforce <=3 MiB per record, existing <=64 records/16 MiB per page including
   proofs/wrappers, and split pages earlier when needed. A tip advertisement,
   hash-only URL or snapshot is not complete history or proof of the latest tip.
3. Strict-parse/context/size/hash-check every record; require the exact P4 kind
   and HP, correct index/parent, predecessor time and parent finality under FP.
   Verify unique authorized proof signers against genesis, not a peer-chosen
   set or local exclusion list. Detect conflicting finalized references and
   stop, never replace one by score. Genesis has its explicit trust exception.
4. Reconstruct/safety-validate all media originals/REGISTERs, rights and technical
   bindings; verify raw V4 payloads/signatures/references/creator and all source
   locations. An isolated decoder/I/O failure is local failure, not a negative
   vote, invalid-media verdict or accepted partial prefix.
5. From the prior VERIFIED state, extract the complete implicit+explicit event
   pool and deterministic positions. Replay REGISTER and VOTE phases. Derive
   accepted/rejected receipts, identity/nonce claims, participation, penalties
   and historical status at their actual reference. Do not use current labels
   or unsigned accepted/status metadata from a peer.
6. Reconstruct each ISSUE's whole selection and all-current-VOTE input digest;
   check exact selected set, historic frozen records, new scratch outcomes,
   both quorums/tallies/ratios and C3 digest. For already issued C3, verify its
   original issuance block/context, not just its signature bundle or today's
   state. Check original/submission/cert ownership and once-only settlement.
7. Validate ledger/native/reward transitions, creator/native activity and all
   remaining state causes; reconstruct delta_h/Jh and compare parent/post
   commitments in R. Hash-derived commitments do not substitute for this replay.
8. Persist verified R/proofs and branch-owned projections/claims/cursor atomically
   before acknowledgement. Promote to authoritative only on exact valid finality.
   Maintain competing sibling projections separately. Under this profile, no
   unfinalized sibling can authorize accepted descendants. Losing provisional
   claims may be released; finalized accepted/ISSUE/nonces/usage never are.
9. After crash/restart, SQLite recovery first supplies an atomic local transaction
   state. Then check integrity/schema, retained source/proof/cursor linkage and
   recomputed commitments; replay from genesis or an already FULLY verified
   local checkpoint. Rebuild all indexes/labels/claims from canonical sources.
   No source may be invented from a root/summary when lost. Missing source or
   proof is INCOMPLETE and withholds eligibility/certification until fetched.
10. For backup/import/new-node sync use the same staged full verification before
    publishing state. Downloaded snapshots are acceleration only after source
    replay establishes their facts; no trusted checkpoint/fast-sync proof is
    introduced. Compare logical snapshot bytes/facts and Jh, not DB file bytes.

Authoritative retained records are the full approved genesis/registry/B0,
canonical R with all explicit and implicit source bytes, and required signed
finality proofs/trusted validator context. Rebuildable records are submission/
vote/incident/penalty/participation/claim tables, native/reviewer activity indexes,
event locators, selected/provisional branch indexes, diagnostic snapshots and
UI/current-state labels. A retained rights/V4 signature alone cannot rebuild
when it was ACCEPTED. SQLite insertion order/page allocation/WAL layout must
never affect a result. Full history remains archival, including unminted
registration/issuance and rejected/stale misconduct sources.

Specific adversarial outcomes:

| Attempt | Required result / exact guarantee |
| --- | --- |
| Peer drops an included VOTE or REGISTER but advertises old R/hash/proof | Byte/hash or implicit inventory/commitment check fails. Peer cannot reserialize another history under that old finalized hash. |
| Proposer never includes a privately seen signature, or finalizes a block without it | Censorship before acceptance; signatures prove neither universal broadcast nor completeness. No omitted-authoritative-event claim exists for that off-chain record. |
| Peer skips a history block or offers only certificate/root | Parent hash/height/source dependency/proof continuity fails or remains incomplete. Do not assume zero offenses/usage. |
| Delayed vote signed at old F | Not a new countable receipt at the new parent. It may prove signed self/equivocation/penalized-reference misconduct, never backdated quota acceptance. Previously accepted historic vote remains valid. |
| Forged admin penalty / invented acceptance flag | No closed event/proof source; reject. Reproduced schedule/status overrides no source. |
| False eligibility snapshot with valid-looking state hash | Replay activities, probation/penalty/usage at the exact reference; reject contradictions. Snapshot+hash supplied together is not authority. |
| Same valid signatures shown with a different creator | V4 directly signs creator; REGISTER immutable binding and signature comparison fail. |
| Different local validator-equivocation knowledge | Same standalone QC has same validity under FP. Revealing an actual conflicting valid QC triggers explicit safety failure, not subtract-and-rewrite behavior. |
| Different insertion/physical layouts | Same ordered canonical prefix gives same replay/facts/Jh/selection by induction; future independent DB tests must verify this, not same-file backup. |

The guarantee is completeness and deterministic replay of an AUTHENTICATED
TARGET PREFIX, assuming no conflicting finality beyond the stated fault bound.
It is not discovery of the globally latest tip, proof that off-chain votes were
all published, liveness under censorship/partitions, or independent-node
interoperability already tested. Consensus finality, not standalone reviewer
signatures, authenticates which complete branch/prefix became accepted.

## 13. Exact byte examples and future test contract

These are specification arithmetic only. Reuse the existing symbolic fixture
`zoidberg-signing-vector-v2`, G=`a`*64, b/c digest placeholders and its published
creator/submission/media fields. These are NOT launch identifiers or approved
genesis/policies. Empty B0 intentionally fails the first-media launch condition;
its bootstrap digest from the existing Task 7.17A example is
`54c806886d13f1bea28d8c33457d1b4f0ae60dccffe146386aa2fa860caf37c0`.
HP=`c`*64 below is a symbolic parameter, not the digest of the actual new HP
manifest. G is the symbolic fixture root, not claimed to hash this example B0.

Exact J0 preimage, 376 UTF-8 bytes, no final LF:

```json
{"bootstrap_digest":"54c806886d13f1bea28d8c33457d1b4f0ae60dccffe146386aa2fa860caf37c0","domain":"zoidbergchain/reviewer-journal-genesis/v1","genesis_hash":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","history_policy_digest":"cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc","network_id":"zoidberg-signing-vector-v2","protocol_version":2}
```

J0=`5a277480a466018d68b952d834e6f554c3a77c6273e7be8dd11983129aca507c`.
Empty-history delta preimage, 156 bytes:

```json
{"block_timestamp":"1792368000","events":[],"native_transactions_hash":"4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945","settlement":null}
```

DD1=`cab451e2579994b24fe26ca9e338099bd96ffbe2d98269c253894c4fa0bf3b70`.
Exact J1 preimage, 631 bytes:

```json
{"bootstrap_digest":"54c806886d13f1bea28d8c33457d1b4f0ae60dccffe146386aa2fa860caf37c0","delta_digest":"cab451e2579994b24fe26ca9e338099bd96ffbe2d98269c253894c4fa0bf3b70","domain":"zoidbergchain/reviewer-journal/v1","genesis_hash":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","height":1,"history_policy_digest":"cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc","network_id":"zoidberg-signing-vector-v2","parent_hash":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","previous_commitment":"5a277480a466018d68b952d834e6f554c3a77c6273e7be8dd11983129aca507c","protocol_version":2}
```

J1=`abb72035aacf4331eef2f784985d89af037dccc8bad2e4333d44ae1c9dd37be3`.
This is a hash oracle, not an accepted history block/finality proof. Altering
timestamp, event membership/order, F, N/G or policy must change the bound input.

Exact empty offered-VOTE input preimage, 430 bytes:

```json
{"content_hash":"ca978112ca1bbdcafac231b39a23dc4da786eff8147c4e72b9807785afee48bb","domain":"zoidbergchain/reviewer-selection-input/v1","genesis_hash":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","network_id":"zoidberg-signing-vector-v2","parent_hash":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","parent_height":0,"submission_id":"dddddddddddddddddddddddddddddddd","vote_event_ids":[]}
```

Digest=`20cde214251ae76c9cfa83f555c07eda600c0db92085245e9523986a523a2f72`.
Empty input alone cannot create a new certificate unless enough accepted votes
actually exist at its reference; none is invented by this example.

Exact UNSIGNED V4 message preimage using the first existing fixture vote's
payload, changing only the documented new domain/version/context fields and
adding G/reference/creator; 898 bytes, no signature or fresh key:

```json
{"choice":"admissible","content_hash":"ca978112ca1bbdcafac231b39a23dc4da786eff8147c4e72b9807785afee48bb","creator_wallet":"0x19e7e376e7c213b7e7e7e46cc70a5dd086daff2a","dimension":"admissibility","domain":"zoidbergchain/community-review/v4","expires_at":"2026-10-20T00:00:00+00:00","genesis_hash":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","issued_at":"2026-10-19T00:00:00+00:00","network_id":"zoidberg-signing-vector-v2","nonce":"fixture-admissibility-2","policy_digest":"cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc","policy_version":3,"reference_finalized_block_hash":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","reference_finalized_height":0,"reputation_rule_version":3,"reviewer_policy_version":2,"submission_id":"dddddddddddddddddddddddddddddddd","vote_version":4,"wallet_address":"0x1563915e194d8cfba1943570603f7606a3115508"}
```

Message SHA-256=`736712dc80dca9664afdf406f8eac1ebb7cb3e71c10053b269927748f34a96fd`.
Its EIP-191 signing preimage is raw `0x19 || ASCII("Ethereum Signed Message:\n")
|| ASCII("898") || exact_message_bytes`; this is NOT the SHA-256 hex string.
No old signature is promoted or asserted valid on this V4 message. Future
fixtures must independently check Keccak/recovery and a real fixture signature.

Python and Node independently reconstructed/serialized all five examples and
agreed byte-for-byte; .NET SHA-256 independently matched their lengths/hashes.
The REGISTER body/event example from Task 7.17A keeps its identical schema and
is still a primitive oracle; its old SMT examples are not this replay format.
No new accepted fixture manifest or protocol implementation is supplied here.

Future versioned golden package must include full B0/FP/HP/genesis, J0, signed
V4, explicit/implicit event source transcripts and outcomes/claims, a C3 issuance
and later settlement, all byte/hash intermediate preimages, media/history R4,
proofs and exact rational fork scores. Author independent expected bytes, not
expected hashes regenerated by the new implementation under test. Use only
published test identities; no launch identities/signing secrets in vectors.

| Future vector / implementation test | Required exact assertion |
| --- | --- |
| Genesis grants | Full B0/policies/G/J0; list sorted/unique/bounded; forged grant/digest/root/set reject; no optional legacy score/usage, no G cycle; wrong policy grammar/profile rejects. |
| Bootstrap first block | Five noncreator signatures in EACH dimension, at least one established; one repeated signer/self vote fails. Atomic first media works with no prior REGISTER/VOTE block; empty/unavailable bootstrap cannot magically approve media. |
| Complete inventory | Selected sources extracted once; explicit duplicate implicit event rejects; each optional REGISTER/VOTE/ISSUE has source bytes; no accepted flag/admin penalty creates state; implicit REGISTER cap counts. |
| Independent replay | Two DBs ingest same genesis/R/proofs with different insertion/physical layouts and restarts -> identical facts/canonical diagnostics/Jh/status/usage/selection/C3. Same-file two connections is insufficient. |
| Same-height order | Wrong wire ordering/ID/duplicate rejects; two new votes competing for last quota slot choose earlier logical ID; tenth probation receipt cannot promote another same-height voter. |
| New/old mixed selection | Historical prefix + current raw pool; mandatory earliest established then first fifteen others, exact set and serialization order; missing earlier negative/unsure receipt fails; other-target quota VOTEs are bound by input digest. |
| Unsure/cohort policy | Quorum with two decisive positives+three unsure gives 1/1; all-unsure unresolved. Explicitly test earliest-16 all-unsure lock despite later decisive votes; no favorable substitution/implicit resubmission appeal. |
| Exact ratios/fork choice | 5/7 -> 514800 score units; 7/10 -> 504504; 6/9 fails approval; nonreduced/bool/zero-denominator reject; history contributes zero; no float adapter; finalized protection outranks score. |
| Reviewer equivocation | Distinct signed choices/creator/target/dimension; grouped once, same-choice and high-S retries nonpenalizing; first accepted vote remains; neither accepted needed for objective signed contradiction. |
| Self/penalty proof | Signed creator prevents later creator reassignment framing; source penalty at signed reference required; pre-penalty replay cannot become a penalty attempt. |
| Rate evidence | First two quota rejections no incident, third one; full accepted sources; stale off-chain rejection claim cannot substitute; dimensions count once per submission/epoch; signature variants never count as excess. |
| Late offenses | Proof accepted at h after an earlier finalized C3 -> first future effect h, no old cert/root/reward rewrite; signed old penalty context extension prospective, suspension precedence preserved. |
| Qualification/promotion/expiry | All creator/native/mixed thresholds, age at origin+14/+15/+16, earliest qualifying height and epoch difference 3; nine/ten distinct receipts, unsure/unminted receipts, half-open expiry at boundary, bootstrap restores under penalty. |
| Stable identity | Same F/all-current-pool/frozen inputs -> same C3 regardless DB order or media encoding. Different pool/F changes input/digest. Finalized ISSUE reused at later media parent unchanged; same H/policy/encoding cannot reissue/remint. |
| Finality advancement | F=k draft valid only for parent k; if k+1 finalizes another sibling, old draft cannot reparent. Accepted historical signatures reusable; unaccepted new signatures need new reference. |
| Delayed finality | Parent remains k, no global draft quota consumption; signature expiry evaluated at candidate inclusion; no child accepted without parent proof; retry/ack handling atomic. |
| Stalled/split finality | Two siblings divide first signatures below q; assert profile withholds progress, never fabricates proof. Future approved round/locking protocol must prove its own recovery/liveness before deployment. |
| Validator equivocation | Same QC validity despite local knowledge of another conflicting signature; unauthorized/set/duplicate signatures reject; two valid conflicting QCs halt. Test n=3 q=2 intersection counterexample; no reviewer slashing or retroactive removal. |
| Forks/rollback | Siblings independent; losing candidate's provisional claims released; finalized accepted/ISSUE claims never released; no finalized detach and no accepted descendant from unfinalized parent. |
| Missing sources | Drop a canonical event, implicit record, intermediate block or proof -> invalid/incomplete; no absent-history=>zero default; opaque root/snapshot/URL insufficient. |
| Context replay | Change N then G, policy, protocol/profile, creator/ref/dimension or purpose independently -> reject; V3 never relabeled V4; retained N-only rights require N nonreuse. |
| Capacity | At/one-over vote/message/event/cert/native/depth/register-count/explicit-array/whole-R limits; all maxima reservation; no preliminary double-copy requirement; exact-size instrumentation not fake valid signatures. |
| Resources | Worst-case compressed REGISTER/media, 256 source events, repeated signature work, proof/page bounds, bounded workers and local failures; measure actual CPU/memory/bytes, no assumed savings. |
| Crash/source-only recovery | Kill pre/post transaction commit, lost acknowledgement, delete ALL derived indexes/claims, rebuild from genesis/R/proofs; identical state or explicit missing-source failure, never invent acceptance. |

## 14. Required implementation sequence — none begun here

1. Approve the profile choices in section 15; supply/review the missing finality
   agreement/pacing specification. Freeze selection/cohort and admission scope.
2. Independently author/review signed fixture transcripts and size/resource
   vectors for the precise approved profile, including mixed implicit/explicit
   event extraction and its dependency DAG. Do not change old v3 vectors.
3. In a separately authorized task, implement inert P4/C3/V4/profile/event/replay
   validators, leaving canonical_v3/active paths intact; use explicit test-only
   contexts and published fixture identities. No launch values required for
   these tests, but no ad hoc trusted callback may stand in for missing history.
4. Implement source-only two-database replay/recovery and branch-owned atomic
   source/claim/projection transactions; reproduce golden state and failures.
5. Integrate the approved consensus/finality/fork-choice and bounded sync/import/
   export paths, full media safety and worker/resource containment; test actual
   independent nodes. A format parser alone never authorizes a block.
6. Only after separate launch approval choose N/W/G, grant/validator identities,
   genesis allocations/state disposition and signed artifact distribution; then
   separately authorize any reset/migration/activation/deployment. This task
   performs none of them and does not resume Task 7.17 automatically.

## 15. Gate status and remaining approvals

| Decision | Concrete recommendation / remaining gate |
| --- | --- |
| Event completeness/authority | Three reviewer event kinds with mandatory implicit extraction and explicit rejected/stale evidence suffice for the stated objective rules. No admin/subjective transition. Approve canonical acceptance/issuance ownership replacing local lifecycle authority. |
| Bootstrap | B0 genesis-established grants, empty initial scores/usage/incidents, quorum/self exclusion unchanged. Approve trust distribution and later launch artifact/schema; no real allocations here. |
| Admission cycle | Atomic same-block registration/new vote acceptance/ISSUE against F; no mandatory preliminary media. Approve current-input extension of the old parent-only cutoff, signed creator and changed journal port. |
| Selection | Exact-set conservative rule specified. **BLOCKED pending cohort-policy approval**, including permanent all-unsure lock versus separately reviewed rolling/arbitrary-subset alternative. No universal media-liveness claim. |
| Penalties | Objective sources, signed-reference penalty proofs, canonical rate receipts and prospective h activation/schedules specified. Approve Reputation 3/Reviewer 2/Review 3; no subjective adjudication or automatic validator discipline. |
| Finality proof validity | Self-contained static-set counting specified; no local equivocation exclusion/retroactivity. **BLOCKED pending approval** of that change and explicit fault-bound/quorum decision. |
| Finality progress | **CRITICALLY BLOCKED**: proposal agreement, locking/round change and safe recovery from split signatures are not established by source. An audited consensus/round specification is required; no timeout/proposer/governance invented here. |
| Control-block/model compatibility | Approve no-reward history-kind records, logical-height effects, production/pacing/incentives. Without them all-penalized media-only epoch restoration can deadlock. Epoch age means blocks, not wall time; rapid control history could accelerate earned-age progression, so pacing is a security/economic review requirement. |
| Exact fork choice | Exact LCM score units and zero score for history proposed; approve adapter and summary/peer handling. Existing float service cannot handle new rational records. |
| Admission-control scope | **BLOCKED pending approval** to treat runtime allowlists/daily clocks/challenge caches/manual service blocks as relay controls only; fresh signatures/canonical nonce/epoch/status still consensus. If global controls required, specify authenticated policy/time/challenge events before implementation. |
| Commitments/schema | Journal/replay commitment, P4/C3/V4 and HP/FP/genesis extension explicit; no mandatory SMT. Approve all version/preimage/cap changes; keep existing v3 bytes unchanged. Full new genesis layout/registry integration still requires its launch-schema review. |
| Resource/economic readiness | Analytic fit specified; aggregate signature/worker cost, storage, control pacing/spam and target-platform behavior remain unmeasured activation gates. No new fee/bounty/reward is selected. |

No rule is automatically approved by appearing in this document. Remaining
protocol choices are material to safety/liveness; arbitrary code defaults or
SQLite data cannot resolve them. Missing actual launch identities is NOT what
prevents inert implementation; the missing agreement/liveness and unapproved
selection/admission/finality authority changes are.

**Task 7.17 implementation may NOT safely resume yet.** The amendment makes the
reviewer-history and noncircular admission contracts concrete, but approvals
and the critical finality protocol above must precede a separately authorized
implementation. This report does not claim new independent-node reproducibility,
production readiness or completion of subsequent tasks.

## 16. Focused verification record

Windows project environment; existing selected regression tests unchanged:
**145 passed in 2.58 seconds**, no failures/errors/skips. The selection covers
73 v1 protocol/golden/native/quorum cases, 70 existing canonical fixture/ratio/
size/nonactivation cases, and two preserved reviewer/reputation policy tests.
It exercises no new consensus profile; no random signing keys or live DBs were
created. Existing published fixtures/scalars remain unchanged. Disposable JUnit:
`temp/task717b-focused.xml`; runtime artifacts under ignored `temp/task717b-*`.

Independent Python and Node canonical preimage construction agreed on all five
section 13 examples; .NET independently matched each SHA-256/length. Python and
Node checked the new 517/296/854-byte accounting and 3,059,651-byte media bound;
explicit object-width enumeration also checked history and bootstrap bounds.
Economics and exact LCM/quorum intersection arithmetic were checked locally.
No performance measurements or new signing/vector implementation is claimed.

Final documentation checks include UTF-8/no BOM, final newlines, trailing space,
balanced fences, local links, exact embedded JSON lengths/hashes, unchanged
Task 7.17A/canonical modules, tracked/untracked diff checks and unstaged-only
scope. Branch/HEAD unchanged; only this new amendment and blocker-report status
pointer differ from HEAD. No full suite, cross-platform, actual independent
nodes, new-profile or finality-liveness tests were run/claimed.
