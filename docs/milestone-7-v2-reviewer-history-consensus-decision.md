# Milestone 7 Task 7.17A — Consensus-authenticated reviewer history decision

Date: 2026-10-22 (America/New_York).

**Specification for review; Task 7.17 implementation remains BLOCKED.** Recommend
an explicit genesis-authenticated established-reviewer allocation (strategy B),
fresh signed observations, and complete event bytes in canonical blocks. Local
SQLite lifecycle records, database images and off-chain certificate issuance are
not consensus authority. This document specifies a candidate protocol, including
its necessary amendments; it does not authorize those amendments or launch.

The simplest fully specified boundary below requires a finalized parent before
accepting a child. That restriction, history-only blocks, preliminary on-chain
media registration, prospective penalties and changed replay ownership are
material protocol decisions. They require approval, not an implementation-time
default. Section 15 lists the gates and alternatives, especially unresolved
validator-equivocation authority. No claim of independent-node reproducibility
is made before implementation and the tests in section 14.

## 1. Repository verification and source authority

- Branch: `Compression-State-Bloat-and-Node-Economics`.
- HEAD: `91987091967703901df6b59870fa5e126aa29bf0`.
- HEAD separately commits the Task 7.17 blocker report, `Milestone 7 Task 7.17:
  document reviewer-history authority blockers`; its only change is that report.
  Parent `b3aa0b4` separately commits Task 7.16.
- Initial index and worktree clean. No repository or ancestor `AGENTS.md` found.
- Scope: this new specification and a current-status link/gate note in the
  [Task 7.17 report](milestone-7-v2-history-freeze-and-recovery.md). No source,
  tests, fixtures, schemas, active state or configuration changed. No commit,
  push, merge, activation, migration, reset, key generation or deployment.

Read the required [history blocker](milestone-7-v2-history-freeze-and-recovery.md),
[authenticated integration](milestone-7-v2-authenticated-evidence-integration.md),
[atomic certification](milestone-7-v3-atomic-certification.md),
[issuance](milestone-7-v2-evidence-issuance.md),
[schema](milestone-7-v3-canonical-schema-decision.md),
[signing](milestone-7-v3-signing-and-domain-separation.md) and
[block implementation](milestone-7-v3-block-format-implementation.md) reports.
Current source takes precedence over old reports and their historical stops:

| Source | Finding relevant to this decision |
| --- | --- |
| [milestone5_policy.py](../milestone5_policy.py) | Empty literal bootstrap set; epoch=finalized height // 5; age, qualification, promotion, quotas and integer quorum constants; five objective offense types. |
| [reviewer eligibility service](../services/reviewer_eligibility_service.py) | Earned activity from finalized creator/native ancestry; earliest qualification height; distinct accepted submissions; current labels are insufficient. |
| [reviewer_reputation.py](../reviewer_reputation.py) | Per-type escalation and half-open penalty intervals; signed offense verification currently explicitly requires protocol 1; local accepted/creator resolvers supply missing context. |
| [blockchain.py](../blockchain.py), `cast_signed_submission_vote_operation` | Challenge verification, conflict/self/penalty/quota rejection precedence, accepted/rejected observation retention; local acceptance affects future qualification even without minting. |
| [review_policy.py](../review_policy.py), [wallet_auth.py](../wallet_auth.py) | Runtime allowlists, daily controls, challenge issuance/consumption and wall-clock expiry are application admission controls, not a committed network policy. |
| [dual_review.py](../dual_review.py), [admission_certificate.py](../admission_certificate.py) | Separate dimensions; >=5 votes and >=1 established per dimension; unsure and exact integer threshold; immutable evidence binding. |
| [history.py](../canonical_v3/history.py) | Local `(observed_at,kind,id)` replay; unsigned lifecycle/references; explicit trusted journal port, not a peer proof. |
| [atomic.py](../canonical_v3/atomic.py) | Image-based local snapshot identity; permanent off-chain issuance/participation versus selected-branch claims; caller-supplied selection; no independent history authority. |
| [evidence.py](../canonical_v3/evidence.py), [block.py](../canonical_v3/block.py) | Implemented closed 23-field vote/18-field certificate/media-only block 3; no history slot or state root; 3 MiB complete record cap. |
| [finality.py](../canonical_v3/finality.py), [finality service](../services/finality_service.py) | Separate proofs, trusted validator set and equivocation exclusions; proof's self-declared set is insufficient. Locally known equivocations are not a complete authenticated inventory. |
| [genesis](../protocol_v1_genesis.py), [reorganization service](../services/canonical_reorg_service.py), [storage_tools.py](../storage_tools.py) | Frozen v1 genesis identity; hash-linked reconstruction and finalized protection; export retention does not authenticate missing records. |
| [post_mint_dispute.py](../post_mint_dispute.py) | Additive dispute status, not authority to revoke finalized media or introduce new penalty types. |

## 2. Consensus facts and their lifetime

Notation: `J` is the existing strict, compact, sorted-key UTF-8 canonical JSON;
`S(b)=lowercase_hex(SHA256(b))`; `D(x)=S(J(x))`. Keep its exact Unicode,
integer/bool, duplicate-key, null, depth, signature and field-bound rules. Use
`N,W,G,Wallet,H64,ID32,UInt,TimeUTC,Sig65` as defined by Task 7.10A/B. No floats
or local timestamps enter this state. Native aggregate retains its existing
ASCII-escaped serializer `A`, not `J`.

Under the candidate finalized-parent profile, `S_h` is the deterministic logical
state after block h's ordered transitions. It becomes authoritative when h
finalizes. A candidate at h reads authoritative `S_(h-1)` and an ordered scratch
projection for intra-block quota/replay conflicts. Its reference is exactly
`(h-1,parent_hash)`; its review epoch is `(h-1)//5`. Genesis is authoritative
without a signature on itself. A child of an unfinalized parent is incomplete,
not invalid because a local node has not received the proof.

The following table covers source, authentication, availability, ordering,
effective boundary, persistence, reorg and recovery for each fact. All rows use
full canonical ancestry plus genesis, not a peer's eligible flag. `E` means the
canonical event position in section 5; `P` means finalized parent state.

| Fact | Authority/authentication and availability | Order and effective boundary | Persistence, reorg and replay |
| --- | --- | --- | --- |
| Reviewer identity | Recovered personal-sign Wallet; N/G/policy/parent bound in new signed vote | E; identity never taken from display name or local account row | Retain exact signed bytes; provisional observation rolls back; finalized observation replays forever |
| Submission eligibility/creator/original | REGISTER event includes full media descriptor, validated original bytes, technical record and creator rights; block/finality authenticates acceptance | Earlier registration, visible in P; self-vote always excluded | Retain even if never minted; rebuild submission index from events; no URL-only authority |
| Originality vote | Signed dimension/choice, accepted VOTE event and registration | Pre-vote P status plus earlier E quota claims | Immutable accepted outcome; no relabeling or counting rejected records |
| Admissibility vote | Same independent signature/choice rules | Same boundary, separate dimension quorum | Same; one dimension cannot stand for the other |
| Established qualification, wallet age, promotion | Genesis grant or finalized creator/native activity and accepted participation | At end of each block for the next parent snapshot; no within-block promotion | Derive earliest qualification and probation counts; never trust current `reviewer_states` label |
| Historical reputation/demotion | Objective signed observations, derived incident identities/escalation/penalties | E orders findings; new penalties first constrain child votes | Retain source observations and derived proofs; restore underlying status after expiry; no arbitrary scalar score |
| Epoch quota | Accepted distinct `(wallet,submission,epoch)` records | P plus earlier E in the block; 5 probationary/25 established | Both dimensions same submission/epoch charge once; finalized usage never released by issuance failure |
| Promotion participation | Accepted distinct submission with probationary status, including unsure and unminted media | First accepted participation is authoritative; counted before next snapshot only | Count submission once across all epochs for promotion; preserve first probationary receipt |
| Vote replay claims | Message, signer nonce, and `(wallet,submission,dimension)` acceptance identities | First ordered observation/acceptance; high-S variant cannot consume again | Derive from canonical observations; orphan branch claims do not bind another branch |
| Certification replay claims | ISSUE event, certificate bytes and media/submission ownership | First ISSUE at E; selection cutoff is P | Permanent after finalization, including never minted; candidate-only claims roll back |
| Finalized ancestry | Verified block links and external quorum proof from authenticated genesis validators | Parent must be finalized; no locally discovered “latest” cursor | Retain proofs/trust source; no finalized detach; validator-equivocation authority remains a gate |
| Bootstrap status | Closed sorted grant list inside genesis commitment | Initial S_0; no activity, age, reputation or quota usage fabricated | Recompute bootstrap digest/G, then initial state root; no automatic legacy import |

Local UI names, queue order, manual service blocking, receipt times, database row
IDs, challenge caches, analytics/collusion alerts and display percentages are
convenience state. They may restrict what one service relays but cannot change a
peer block verdict. This explicitly amends the Task 7.15 journal requirement to
prove local challenge issuance/daily configuration. Fresh signature, on-chain
nonce/replay, chain qualification and epoch quota remain mandatory. If daily
quotas/allowlists must be global consensus rules, a separately committed policy,
logical time and challenge authorization protocol is required: BLOCKED; an
environment variable or producer attestation cannot supply it.

## 3. Bootstrap choice and first-block liveness

| Strategy | Secure authority and operational consequence | Decision |
| --- | --- | --- |
| A. Empty genesis reviewer state | Clean, but >=1 established is mandatory in BOTH dimensions. Promotion itself requires ten accepted probationary submissions and time. Existing media-only blocks also require a certificate; activity cannot bootstrap the first block. Native-only blocks could earn qualification, but do not alone satisfy established promotion. | Reject as the default; otherwise explicitly redesign startup qualification/quorum and block progress. Never silently exempt the first media. |
| B. Explicit genesis allocation | Genesis commits a finite Wallet list granting established status. Auditable and independently replayable without claiming old history complete. Requires approved identities and enough independent noncreator participants. | **Recommended, least complex secure trust origin.** |
| C. Transitional import | Requires old authenticated ordered complete sources, signatures, validator context, boundary and completeness proof. Local SQLite cannot prove absence of omitted acceptances/offenses/issuances. | Unsupported today; BLOCKED unless a separate verified import protocol supplies that evidence. |

A becomes viable under the NEW proposed history blocks if genesis funding can
support finalized native activity: Wallets first earn qualification through the
native path, then accept probationary votes on registered but unminted media,
and after the required time/ten distinct participations become established.
Vote acceptance itself does not require a submission to have reached quorum;
otherwise this path would be circular. Thus A is not mathematically impossible
under the proposed event model. It requires multiple epochs, funded activity,
registration availability and enough participants before the first media, with
no fixed completion time guaranteed. Without those control-block capabilities,
the current media-only format has the startup deadlock described above. B
avoids that operational qualification dependency while preserving all normal
earned paths; its explicit initial trust distribution remains the tradeoff.

Proposed closed bootstrap object `B0` has exactly
`bootstrap_version,network_id,reviewer_policy_digest,reputation_rule_digest,reviewers`.
Version is 1, N is fixed, digests pin the amended policies, and reviewers is a
sorted unique Wallet array, proposed maximum 128. Each entry grants only
`ESTABLISHED_REVIEWER` as underlying status; no balances, activity counts, clean
legacy reputation assertion or signing keys are imported. All usage/incident
counts start empty in the new chain. Financial allocations and validator roles
remain separate explicit genesis data. Reviewer authority is not validator
authority.

Commit `bootstrap_digest=D({domain:"zoidbergchain/reviewer-bootstrap/v1",
network_id:N,payload:B0,protocol:"zoidbergchain",protocol_version:2})` and the
full B0 in the new genesis inputs before calculating G. Do not put G or a
G-dependent state root back in that genesis preimage. Verify full B0/digest and
the approved genesis envelope/G; a bootstrap digest supplied alongside an
untrusted list is not authority. All policy bytes must also be available, not
just unknown digests. The final new genesis field layout remains a separate
launch-schema gate; no actual B0, identity, value or genesis is created here.

Launch acceptance requires at least five distinct eligible noncreator Wallets
available for each dimension, at least one established in each; choosing all
five from the grant list is the simplest first-media path. A creator who is one
of only five grants leaves four: arrange another noncreator, or more grants.
One Wallet may review both dimensions, consuming one participation; one Wallet
can never satisfy five seats. Different Wallets do not prove different humans:
the reviewed distribution must address common control. No admin signature or
single bootstrap reviewer can bypass the five-person signature requirement,
negative votes, 70% threshold, media safety, rights or finality validation.

History-only blocks (section 10) allow registration, voting and elapsed epochs
before the first minted media. They carry no creator reward and cannot approve
arbitrary media. Their admission, production incentive and finality pacing must
be approved; assuming existing code already supports them is incorrect.

## 4. Closed authoritative event inventory

Prefer direct canonical block data to a separate journal chain or external
availability committee. The complete authoritative inventory is: genesis B0;
validated native/creator activity already in blocks; the following THREE event
types; media settlement already in media blocks; separately authenticated
finality proofs. Offense findings, penalties, promotion/demotion, quota charges,
freeze selections and claim transitions are deterministic outputs, not unsigned
administrative commands or additional discretion-bearing event types.

Every event is exactly `{event_id,body}`. Body has exactly
`domain,event_version,network_id,genesis_hash,parent_height,parent_hash,kind,payload`.
Domain=`zoidbergchain/reviewer-event/v1`, event_version=1, N/G fixed,
parent_height=h-1 and parent_hash=block.previous_hash.
`event_id=D(body)`. No containing block hash, state root, finality signature,
local acceptance flag or receipt timestamp is in body. Parent precedes event;
event precedes state root/block hash; separate finality follows block hash.
Source identity is the signed creator/reviewer for their records, or the
validated ISSUE certificate and source event identities; no new issuer key.
Inclusion/effective height is h, derived from the containing block rather than
a redundant producer field. REGISTER and ISSUE have inclusion epoch h//5;
VOTE acceptance/quota has signed-reference epoch (h-1)//5. Outputs constrain
future votes only after h finalizes. No independent effective-time override is
allowed. REGISTER requires its rights issue/expiry interval to contain the
block timestamp; later ISSUE/mint verifies the historical registration receipt,
not today's clock or an already-expired rights challenge a second time.

Unknown/missing fields, unsupported versions, noncanonical bytes, invalid
signature or context and oversized objects reject. Semantic rejection of a
well-formed signed VOTE is retained as evidence with a derived outcome; a
malformed signature cannot become an objective offense. Retain every event
included in accepted blocks, including rejected observations, indefinitely with
that history. Fetch by block hash/height plus event ordinal; secondary lookup
by event_id is only an index. Proposed per-block event count <=256, depth <=32;
all limits below include JSON quoting and wrappers, not raw message length.

| Kind | Exact payload fields and source | Proposed maximum `len(J(event))` | Duplicates and effective state |
| --- | --- | ---: | --- |
| `REGISTER` | `submission_id,content_hash,creator_wallet,content_type,media,meme_text,technical_evidence,attestation`; caption is required null for no caption/text, otherwise existing bounded image caption; media is the existing closed eight-field descriptor, technical 17 fields and rights 14 fields, all policy/identity/MIME/length/hash/signatures checked | 2,883,584 | Unique submission registration on ancestry. Duplicate same registration is a relay retry, not a second event; conflicting creator/H rejects. Full original bytes are reconstructed and safety validated. Available to votes only from the next finalized snapshot. |
| `VOTE` | `signed_vote`, exactly `{payload,signature_scheme,signature}`; payload is V4 below; scheme personal_sign and Sig65; source is recovered Wallet | 8,192; signed_vote <=4,096, signed message <=2,048 | Exact repeated message/nonce observation does not count/penalize twice; a different signed statement may be a conflict/offense. Acceptance/quota and offense effects are derived in E order. |
| `ISSUE` | `certificate` alone; exact amended certificate C3, <=196,608 bytes, all selected source votes and registration verifiable from P | 200,704 | First valid issue owns H/submission/certificate and relevant claims. Exact already-issued C3 is an off-chain idempotent retry; do not add a second ISSUE. Different C3 for an owned H/submission rejects. Effective after ordered issuance, immutable after finalization. |

All three require inclusion and full block validation before finality can confer
consensus acceptance. REGISTER/ISSUE have no additional producer signature;
their fields must verify against signed sources and deterministic rules. A block
producer cannot authorize eligibility by asserting it. A dropped off-chain vote,
submission, issuance attempt or allegation has NO consensus effect. This is a
precise completeness scope: every INCLUDED transition is available and ordered,
not a claim to know every signature ever made.

REGISTER intentionally retains preliminary media, even if it later fails quorum.
Without it, an accepted unminted participation could depend on unavailable media
or a service's unverifiable assertion that a submission was admissible. This
adds immutable data and storage/abuse costs; approval is required (sections 13,
15). No implication that technical registration is community approval or mint.

### 4.1 Fresh signed vote representation (explicit amendment)

Proposed flat V4 has exactly the Task 7.10 V3 fifteen keys plus
`genesis_hash,reference_finalized_height,reference_finalized_block_hash`:

```text
domain,network_id,vote_version,policy_version,policy_digest,
reviewer_policy_version,reputation_rule_version,wallet_address,submission_id,
content_hash,dimension,choice,nonce,issued_at,expires_at,genesis_hash,
reference_finalized_height,reference_finalized_block_hash
```

Domain=`zoidbergchain/community-review/v4`, vote_version=4,
policy_version=3 (review), reviewer_policy_version=2,
reputation_rule_version=3. Policy digest is the amended immutable review policy.
G is exact; signed reference is a finalized ancestor. Accept a vote for quorum
only when its signed reference equals the containing block's parent. Thus a
peer cannot attach an old signature to a later cooldown or quota rejection.
Retain old-reference signed statements solely for objective equivocation/self
proofs; they cannot earn participation, become rate excess or incur a
penalty-at-receipt offense. Wrong-fork/unverified references are incomplete or
invalid as appropriate, never assumed finalized. They must be authenticated
before any offense is derived.
The target registration must already exist with matching H/creator in the
SIGNED reference snapshot, including for stale offense evidence. A signature
for an unknown/unregistered target cannot manufacture accepted participation,
quota abuse or a later creator binding.

`M=J(V4)`, message_id=`S(M)`, vote_identity=`D({payload:V4,signature:Sig65})`.
Use existing EIP-191 Keccak prefix with byte length and secp256k1 recovery,
including current high-S acceptance. A semantic observation identity is
message_id, so high-S or another valid signature on M never creates another
attempt. Conflict and nonce rules also apply across message IDs.

Issue/expiry remain signed TimeUTC, expiry>issue. Countable inclusion additionally
requires `issued_at <= containing_block.timestamp < expires_at` using the
existing canonical time interpretation and predecessor-time checks; historical
replay never compares to today's clock. Stale evidence can still prove genuine
equivocation/self-vote; expiry is not permission to suppress such a proof. This
replaces unreplayable local challenge receipt/expiry as consensus authority;
it needs explicit policy approval. No maximum lifetime is invented here.
The block timestamp remains the implemented canonical nonnegative decimal
seconds string (<=32 bytes, <=6 fractional digits), not a new TimeUTC wire
field. Compare by exact integer microseconds: parse its integer/fraction
coefficient; convert signed TimeUTC by Gregorian ordinal-day difference from
1970-01-01 plus hours/minutes/seconds/microseconds, with 86,400 seconds per day
and no leap seconds. No float `.timestamp()` or string-lexicographic comparison
is permitted; existing height/predecessor-time validity still applies.

The C3 selected-vote record is the old closed 23-field VOTE_FIELDS plus
`genesis_hash` (24 fields). Versions change as above; `vote_message` is M;
existing reviewer reference fields equal the newly SIGNED reference fields;
status/eligible are derived acceptance metadata, not signer assertions. Every
other duplicate field, identity, nonce, time and choice must equal V4.
Bounds remain 4,096/2,048. Old V3 signatures remain old-format test/archive
records; they are not accepted as V4 or automatically converted.
Creator rights retain the existing N-only submitter-attestation/v2 message;
they do not acquire a directly signed G merely because V4 now signs G. Parent
registration and ancestry scope their use; the existing prohibition on reusing
N across genesis roots remains essential for those rights/finality signatures.
A direct-G creator/finality signature amendment would need its own versioned
fields and vectors, not a changed interpretation of existing signatures.

## 5. One total order and exact phase rules

An authoritative path orders blocks by height and hash-linked parent, then:

1. At h, require approved genesis/context and proof of finality for exactly the
   parent (genesis excepted). Reconstruct S_(h-1), the sole status/clock boundary.
2. Check events appear strictly sorted by `(rank(kind),event_id)`, ranks
   REGISTER=0, VOTE=1, ISSUE=2. Do not reorder received arrays into validity.
   Ordinal is the zero-based array position; equal keys/duplicate IDs reject.
3. REGISTER transitions run first, but current-height registrations are not
   countable vote targets until the next block. VOTE transitions use immutable
   parent statuses and a scratch quota/replay map updated by earlier events.
   No same-height promotion changes the status of the next vote.
4. For each VOTE, derive acceptance/rejection, then every newly proven incident
   and penalty atomically. If several incident outputs exist, use fixed offense
   rank equivocation=0, self=1, rate=2, cooldown=3, suspension=4, then incident_id.
   Earlier same-height penalties affect escalation/output interval calculations,
   but do not change another vote's parent-bound eligibility or punish a vote
   signed before that penalty existed.
5. ISSUE derives its entire selection from the parent prefix, not current-height
   votes or offenses. Check current scratch ownership for conflicting issues.
   A same-height penalty does not retroactively alter the parent snapshot.
6. Validate media settlement and existing reward/native transitions in their
   existing specified order, with replay checks against parent plus current
   ISSUE ownership. A media block must reference a previously issued certificate
   or its own single matching ISSUE. Never credit activity early to qualify
   votes in that block.
7. Derive end-of-block activity, earliest qualification, probation promotion and
   state commitment S_h. Penalty filtering for the NEXT vote epoch uses h//5.
   Hash the complete block only after the state root is determined. Separate
   finality signs that resulting block hash.

The total transition cursor is `(height,phase,event_ordinal,output_rank,output_id)`;
phase order is exactly 1..7 above; genesis precedes all. IDs are lowercase hex
and compare as ASCII (same ordering as their digest bytes). A source locator is
`[height,event_ordinal,event_id]`; h and parent hash establish branch binding.
Do not place h's own block hash into S_h or its events. Current block native
activity uses `[height,tx_id]`; media activity uses `[height,certificate_digest]`.
Same-height sorting is choice-independent at selection, though a signer can
grind message nonces: ordering is deterministic, not a fairness guarantee.

Competing unfinalized sibling blocks each have their own scratch state. Neither
is finalized authority for a child under this profile. Existing selection
authority chooses a provisional winner; this specification adds no new score.
When one sibling finalizes, its events become the authoritative next prefix.
Retain the other for diagnostics if desired; its claims have no global effect.
No finalized ancestor may be detached. Two conflicting valid finality proofs
are a consensus safety failure: halt advancement and surface the contradiction;
never choose one by arrival time, smallest hash or a retroactive exception.

## 6. Freeze, eligibility and prospective offense semantics

The historical eligibility boundary for an accepted vote is its signed finalized
parent snapshot, plus earlier same-height quota/replay transitions ONLY. Store
derived status with its source locator; do not overwrite it with current status.
Certificate selection uses that accepted historical status. It does not recheck
every selected reviewer against certification-time status. Promotion, expiry or
a later penalty cannot make the old vote ineligible. This is the proposed
historical validity contract, not a claim that every existing local callback
already enforces it.

Preserve earned rules: age `(reference_height-first_activity_height)//5 >=3`;
two finalized creator submissions, OR five distinct finalized native activities
spanning >=3 epochs, OR one creator plus two native activities. Existing path
order is creator/native/mixed. Native self-transfers earn no qualification count
(new native format already forbids them). Merely registering media does not
earn creator activity; only validated media settlement does. Probation begins
at the earliest qualifying finalized height, lasts >=3 epochs, and needs ten
distinct accepted probationary submissions including unsure. Expired penalties
restore the independently derived underlying status. Bootstrap is the sole
explicit exemption from earning initial status; it is still penalizable.

For vote inclusion at h, quota epoch e=(h-1)//5, limit 5/25 from parent status.
Check used distinct submissions in e, including earlier same-height accepted
votes. A second dimension on the same submission/e is free; a first dimension
in another epoch consumes that epoch's participation. It does not earn a second
promotion count. No promotion raises a quota limit mid-block; next-block
promotion can raise it from 5 to 25 without resetting already-used submissions.
Epoch rollover creates a new logical namespace; never delete old evidence.
ISSUE and mint neither charge again nor refund usage. Failed certification
still leaves previously accepted participation. These rules explicitly replace
Task 7.16's off-chain issuance reservations as consensus usage.

### 6.1 Complete objective offense outputs

Incident IDs use `D({domain:"zoidbergchain/reviewer-incident/v1",network_id:N,
genesis_hash:G,kind:<fixed offense type>,identity:<array below>})`. Penalty ID
equals incident_id. Count prior distinct incidents of the same escalating type
for that Wallet in E order. Derive every provable incident; producer cannot
elect to omit its output. Do not punish a negative/unsure choice or analytics.

| Type | Proof and closed incident identity array | Effect |
| --- | --- | --- |
| `SIGNED_VOTE_EQUIVOCATION` | Two authenticated V4 observations for same Wallet/submission/H/dimension, different choices; signed references both valid ancestors; identity `[wallet,submission_id,content_hash,dimension]` | One incident per tuple; cooldowns 3 then 10 epochs, third onward suspension 25 |
| `CREATOR_SELF_VOTE` | Authenticated observation and parent registration creator==Wallet; `[wallet,message_id]` | Cooldowns 1 then 3, third onward suspension 25 |
| `RATE_LIMIT_ABUSE` | Three distinct message IDs rejected specifically for exhausted epoch quota after parent-status/self/conflict checks; quota source is actual ordered accepted receipts, not a supplied count; `[wallet,epoch]` | Cooldowns 1 then 3, third distinct epoch onward suspension 25 |
| `VOTE_DURING_COOLDOWN` | Signed reference snapshot itself has active cooldown and points to deterministically selected active penalty; `[wallet,active_penalty_id,message_id]` | Extension below |
| `VOTE_DURING_SUSPENSION` | Same, suspension; `[wallet,active_penalty_id,message_id]` | Record only, keep existing suspension |

For counting acceptance use the source path's precedence: exact semantic retry,
previous accepted same-dimension conflict, self-vote, parent active penalty,
unqualified status, exhausted quota, acceptance. Only a different choice proves
equivocation; same-choice second message does not. Conflicting observations are
retained but never replace the first accepted vote. An accepted voice is not
removed because a later conflicting signature appears. A signed nonce reused
for a different message rejects counting, but is not itself a sixth offense.
More precisely, first verify signature/context/registered target and ancestor
reference; bad structure is invalid. Next handle already-observed message as
duplicate without changing its first observation leaf. Then apply accepted-tuple
conflict and self-vote checks. Before penalty/status/quota checks, reject stale
reference, then expired/not-yet-issued interval, then signer nonce conflict, in
that order. These outcomes are respectively stale, expired and nonce_conflict.
Only then evaluate parent penalty, unqualified status, quota and acceptance.
All well-formed new observations are retained, regardless of outcome. Infer
equivocation/self from the full observation prefix independently of which
acceptance rejection won; penalty/rate incidents require their named rejection.
For equivocation use the earliest prior observation with a different choice as
source_a and the triggering observation as source_b; other single-source
incidents use the triggering source_a and null source_b. Rate source_a is the
third excess receipt and source_b the first, with the second reproducible from
the ordered prefix. Store at most the earliest three excess leaves per epoch;
later rejected attempts remain ordinary observations, not more excess leaves.
Self/equivocation facts can still be objectively proven by rejected/stale signed
statements. Penalty-vote/rate outputs need the specified parent-bound status and
receipt conditions; no late relay can manufacture them at a new reference.

If an incident is first proven in block h, use activation reference h and
start_epoch=h//5. It becomes usable only after h finalizes, first for votes in
h+1. Its interval is `[start_epoch,start_epoch+duration)`; existing half-open
epoch conventions mean the first epoch can be partial. Never backdate activation
to the underlying signed statement. Retain its original signed source reference
separately for proof. For escalating offenses while suspended retain the new
incident/sequence but do not create/shorten a penalty, as existing code does.
Overlaps use suspension precedence and maximum active end epoch. Choose active
penalty by highest end_epoch then penalty_id within that status, preserving
existing deterministic tie-break.

Cooldown attempt extensions activate prospectively at h: derive the active
penalty at the vote's signed snapshot; new end is
`max(current_effective_end, h//5 + source_penalty_duration)`; retain source ID
and duration. Never shorten a still-active interval; an already expired penalty
can produce a prospective interval if the signed snapshot proved the attempt
occurred during it. Suspension attempts remain record-only. Multiple new
same-height intervals combine with the same precedence/max-end rule.

Late proofs do NOT invalidate finalized certificates, votes, media or rewards.
They constrain future snapshots only. A provisional certificate frozen at an
unchanged finalized parent remains valid historical evidence despite a current
penalty; parent selection/ownership changes require revalidation, not silent
rewriting. An unissued selection retry at a NEW parent recomputes its cutoff;
a finalized ISSUE freezes its original bytes permanently. There is no
retroactive finality exception, reputation-only reorg or post-mint deletion.

This changes finding-time authority and some prospective extension behavior
from local Reputation Rule 2; use proposed Rule 3, Reviewer Policy 2 and Review
Policy 3. Preserve schedules, objective offense grouping, unsure, quotas and
earned paths unless a separately approved amendment states otherwise. Legacy
offense parser's `protocol_version==1` cannot be relaxed as an implicit migration.

## 7. Deterministic bounded evidence selection

An ISSUE at h has one exact cutoff: **all finalized history through parent
h-1, end of block**, including its event count/root, identified in C3. There
is no caller-selected older cutoff. Candidate inventory for a dimension is
every accepted V4 receipt for that registered submission/H/dimension in that
prefix. Each Wallet has at most one accepted vote in that dimension on that
ancestry. Invalid/rejected observations and current-height votes are excluded;
negative and unsure ACCEPTED votes remain candidates. Already-charged quota
is not tested a second time at certification. Otherwise two nodes could differ
merely because certification was delayed into another epoch.

For each dimension independently, order candidates by source locator
`(height,ordinal,event_id)`. Choose the earliest historically established vote
as mandatory seat; if absent the dimension is incomplete. Fill with the first
15 other candidates, or all remaining if fewer. This yields at most 16, never
drops a negative/unsure to pass, and preserves an established seat even when
16 earlier probationary Wallets exist. No special favorable choice is used.
Serialize the resulting union by the EXISTING certificate order
`(dimension,voter_wallet_address,vote_identity)`, admissibility before originality.
All selected source records must be present; an oversized selected record or
certificate fails size/admission, never causes substitution of the next vote.
This is a newly proposed selection rule, bound in Review Policy 3.

Both dimensions retain >=5 eligible voices, >=1 established, `d=p+n>0`,
`p*10000 >= d*7000`. Unsure counts in quorum and participation, not d. Derive
every existing tally counter/bool/outcome/digest independently. Reduced rational
objects use gcd and positive denominator; 5/7 remains exactly 5/7, 2 positive
plus 3 unsure gives 1/1 with quorum, all unsure is unresolved. Top-level block
summaries continue to be the reduced originality fraction, not a new combined
dimension score. Votes are equal weight.

Duplicate semantic observation/message/nonce can neither claim another seat
nor create rate abuse; same-choice repeats do not replace the original. An
actual conflicting choice cannot replace the accepted vote, but produces the
objective incident. New accepted votes after an ISSUE cutoff cannot change
that issued certificate; before issuance, they enter the next parent's candidate
inventory. Off-chain lateness has no ordering meaning.

C3 has exactly the existing 18 certificate fields plus
`genesis_hash,history_parent_height,history_parent_hash,history_parent_state_root,
history_policy_version,history_policy_digest` (24 fields). certificate_version=3,
review_policy_version=3, history_policy_version=1; both policy digests must match
the genesis registry, as must reviewer/reputation versions within votes.
Historical fields equal the ISSUE parent and its recomputed root. Certificate
identity is still `D(C3 without certificate_digest)`; no containing block hash
or event_id enters it. The certificate's ordered full selected vote records,
technical data, rights and tallies remain embedded, <=196,608 bytes.

An unissued identical attempt at the same parent produces identical C3. Once
ISSUE is finalized, identical retries return those exact bytes regardless of
newer candidates; a different digest for its owned original/submission is a
conflict. Alternate media encoding or candidate block hash may use that same
certificate but can settle its media/reward only once. Replay claims are
network/G/protocol-scoped and exclude policy digests and encoding, as today.
Vote acceptance claims are owned by observations, not exclusively locked to
ISSUE; ISSUE verifies prior ownership rather than double-consuming its inputs.

A certificate proves validity of this deterministically selected bounded set
and completeness of selection FROM THE AUTHENTICATED PREFIX. It does not
prove completeness of all off-chain votes. Validators need that entire prefix
(or a future separately reviewed proof covering the relevant range), not just
the included favorable signatures. A state root alone is not that proof.

## 8. Canonical logical state and commitments

Propose a 256-level sparse binary Merkle map so roots and individual updates
are bounded independently of the number of historical Wallets/events. Do not
hash a SQLite file or repeatedly duplicate full database snapshots per issue.
All maps below are logical derived records, fully replayable from sources.

A leaf fact is exactly `{kind,identity,value}`. Identity arrays use exactly the
types/order below, and value objects have EXACTLY the named keys. Pos is the
three-item source locator; no current block hash is a leaf value. Nullable
derived heights use explicit null only where indicated; absent facts are absent
leaves. All counters are exact UInt and overflow rejects the transition; no
saturation/rounding. Total state is unbounded with chain length; each fact is
bounded, with no unbounded per-Wallet arrays. Max leaf serialization is
262,144 bytes (large source bytes remain in canonical blocks, referenced by
source digest/Pos). Historical snapshots are replayed/persistent-tree versions,
not new authority.

| kind | Exact identity array | Exact value keys/meaning |
| --- | --- | --- |
| `bootstrap` | `[]` | `bootstrap_digest`; fixed B0 authority |
| `submission` | `[submission_id]` | `content_hash,creator_wallet,registration_pos`; registration bytes remain in its source |
| `observation` | `[message_id]` | `vote_identity,pos,outcome`; outcome is exactly accepted, duplicate, conflict, self, penalty, unqualified, quota, stale, nonce_conflict or expired under section 6 precedence; first observation only |
| `accepted_vote` | `[wallet,submission_id,dimension]` | `message_id,pos,status,epoch`; frozen status and acceptance source |
| `nonce` | `[purpose,wallet,nonce]` | `message_id,pos`; purpose exactly review or rights |
| `participation` | `[wallet,epoch,submission_id]` | `first_pos,status`; one charge per pair of dimensions |
| `probation_receipt` | `[wallet,submission_id]` | `first_pos`; first accepted probationary participation only |
| `reviewer` | `[wallet]` | `origin_height,qualification_height,probation_start_height,underlying_status,probation_count`; first three nullable, statuses NEW/PROBATIONARY_REVIEWER/ESTABLISHED_REVIEWER; bootstrap exemption sets underlying only |
| `activity` | `[wallet,activity_kind,identity]` | `height`; activity_kind creator/native, identity submission ID/tx ID; deduplicate exactly |
| `incident` | `[incident_id]` | `wallet,offense_type,pos,source_a,source_b,sequence`; source_a/source_b are Pos or required null where unused; rate incident's sources are the third receipt and earliest excess receipt; its intervening receipts derive from prefix |
| `penalty` | `[penalty_id]` | `wallet,status,start_epoch,end_epoch,duration,activation_height,source_penalty_id`; status COOLDOWN/SUSPENDED, source_penalty_id nullable |
| `excess` | `[wallet,epoch,message_id]` | `pos`; only the three qualifying earliest excesses are needed to prove an incident; further records still retained as observations |
| `issued` | `[certificate_digest]` | `pos,submission_id,content_hash`; full C3 in ISSUE |
| `claim` | `[claim_kind,claim_digest]` | `owner_kind,owner_id,pos`; allowed kinds and owners below |
| `minted` | `[content_hash]` | `height,submission_id,certificate_digest`; once per original on ancestry |

Materialize reviewer facts for bootstrap Wallets, registered creators, native
participants and observed reviewers only, not every possible address; an absent
Wallet has NEW/zero/no-activity semantics. At each block end derive earliest
qualification from retained activity; probation receipts are distinct and status
is derived from receipt count/time. Effective penalty is a QUERY at a specified
snapshot/epoch, never a mutable current label leaf. Canonical serialization of
a full snapshot is the sorted stream of these leaf facts by K below; hash/map
verification and reconstruction never depend on stream arrival or SQL order.

Claims use the existing Task 7.15 preimage
`D({network_id:N,genesis_hash:G,protocol_version:2,kind,identity:[...]})`.
Allowed kinds/identity arrays are: original `[H]`, submission `[ID32]`,
certificate `[C_digest]`; attestation_nonce `[wallet,nonce]`,
attestation_message `[message_id]`, attestation_signature `[Sig65]`;
review `[submission_id,dimension,wallet]`, vote_nonce `[wallet,nonce]`,
vote_message `[message_id]`, vote_signature `[Sig65]`.
`claim_kind` is that literal kind; `claim_digest` is its recomputed hash.
Owner_kind is registration, observation or issuance; owner_id is its event_id.
Registration owns rights claims; first observation owns review message/nonce/
signature, accepted observation owns review tuple, ISSUE owns original/submission/
certificate. An exact semantic repeat never adds another signature claim and
cannot change its first owner. Same signer nonce/different message is a
nonce_conflict, never acceptance. Rejected statements still support objective
offenses if their signatures and sources verify. Policies cannot reset claims.
If a nonce is already owned by a different message, retain its first owner;
record the new observation/message/signature without overwriting that nonce
leaf/claim. Derived outcomes never require two owners for a unique claim.

```text
K = SHA256(J({"domain":"zoidbergchain/reviewer-state-key/v1",
              "identity":identity,"kind":kind}))           # raw 32 bytes
V = SHA256(J(fact))                                        # raw 32 bytes
empty[256] = SHA256(0x02)
empty[d] = SHA256(0x01 || empty[d+1] || empty[d+1])           # d=255..0
leaf(K,V) = SHA256(0x00 || K || V)
node(left,right) = SHA256(0x01 || left || right)
```

Use K bits most significant first, depth 0..255; left is bit 0. A single key at
depth 256 stores leaf(K,V); absent paths use empty[d]. Different facts colliding
on K are an explicit cryptographic collision error, never overwrite. `tree_root`
is lowercase hex of the depth-0 root. Domain/type prefixes use literal binary
bytes, not ASCII characters `"00"`, `"01"` or hex-encoded child strings.

Logical state commitment is D of EXACTLY:

```text
{domain:"zoidbergchain/reviewer-state/v1",network_id:N,genesis_hash:G,
 protocol_version:2,history_policy_version:1,history_policy_digest:HP,
 bootstrap_digest:BD,height:h,previous_hash:parent_hash,tree_root:T}
```

At h=0, previous_hash is the exact approved genesis previous-hash value; compute
the post-genesis S_0 commitment AFTER G is known, never insert it into genesis.
S_0 facts are bootstrap and derived reviewer facts, plus actual genesis activity
ONLY if the approved genesis schema explicitly defines such activity; allocation
does not silently count as native transactions. Bootstrap reviewers' nullable
age/qualification fields do not fabricate earned paths.

S_h commits all executed reviewer transitions through h, including issuance and
settlement, with N/G and policy authority. It excludes block h's hash, proof,
local finality receipt time, database revision and its own digest. Parent root
is verified by replay, not accepted from a producer. Changing insertion order,
page layout, WAL/rollback journal or caches cannot change any preimage. A Merkle
proof establishes an entry/nonentry only against an independently authenticated
root; it does not replace transition or availability verification.

## 9. Anchoring and exact schema impact

**No change to the implemented block 3, vote 3 or certificate 2 parsers/bytes is
authorized here.** Recommend a distinct prelaunch block_version=4 profile,
reviewer-history version 1, certificate 3 and vote 4. Protocol_version remains
2 only if explicitly approved as a preactivation amendment; otherwise assign
a new protocol version and update ALL domains/vectors consistently. An
implementation must not support two different meanings under block_version=3.

Every amended block payload has a required `reviewer_history` object with
EXACT keys `history_version,history_policy_digest,parent_state_root,events,
post_state_root`. history_version=1; HP must match genesis registry;
parent_state_root=S_(h-1), post_state_root=S_h. Both roots H64. Events exactly
the section 4 array. History/event list is part of the block's existing
envelope hash preimage, so the whole inventory, length/order and resulting
state are authenticated. No separate event Merkle root/count is necessary:
the canonical array commits both. Its source hash/parent provides coverage.
Parent finality is a separately retrieved proof of that exact parent hash;
proof variants cannot change history or state bytes.

Amended media P is the old exact PAYLOAD_FIELDS plus `reviewer_history` and
`block_kind`, with block_version=4, block_kind=`media`; old optional image
caption remains. C3 replaces its embedded C2; references bind C3's ISSUE
cutoff, which may precede the media parent if previously issued. H/media/reward/
native identity/ledger/rational rules otherwise remain. Total R cap stays
3,145,728 bytes. No history root is hidden in policy_id, nonce or existing vote_hash.
Media content_type/caption/creator/technical/rights must equal its registered
submission, with REGISTER's null no-caption mapped solely to absent optional
media meme_text. Decode both descriptors to the same original H/length/MIME;
different permitted encodings do not change the registered identity.

The new `block_kind="history"` payload is exactly:

```text
block_version,block_kind,index,previous_hash,timestamp,miner,
native_transactions,transactions_hash,reviewer_history
```

It has no creator reward, transactions array, minted_at, media, submission,
certificate, approval or reward fields. Native transfers use the SAME U10/T18,
order/aggregate/balance rules, including existing caps. History blocks may be
empty to permit logical height/epoch progress but need ordinary block-production
authorization and finality, not a reviewer/admin bypass. REGISTER's full media
is confined to its event; history-only does not mean off-chain media. Separate
finality and 3 MiB record cap apply to both kinds.

Versioned budget amendment: history blocks use complete R<=3 MiB, individual
event caps, <=256 events, native<=98,304 and a 32,768-byte cap on residual R
after subtracting the complete event array and native array. Media blocks keep
certificate<=196,608, native<=98,304, encoded/original caps and existing 32,768
residual cap measured after ALSO subtracting the complete `reviewer_history`
value; history value<=262,144. These disjoint accounting changes are required
because old S_rest has no room for events. All simultaneous child/parent/total
caps apply; there is NO new guarantee every maximum-sized media plus maximum
history fits. Reserve exact mandatory identity-format bytes before ISSUE/mint,
defer optional native/history data to another block if necessary, never omit
required selection/evidence to fit. Put a large ISSUE in an earlier history
block to avoid copying it twice in one media block.

An unchanged block-3 path would need a separate fully available consensus journal
and authenticated ordering/coverage/finality linkage. Neither current v3 field
slots nor existing sidecar proof authenticate that journal. That is a more
complex alternative, not a way to resume without a schema decision.

## 10. Finality authority and the critical remaining gate

The finalized-parent rule avoids local “latest finalized” ambiguity and gives
every vote one exact signed state boundary. It serializes block progress behind
quorum finality. Sibling candidates may compete, but no accepted descendant can
extend either until its parent finalizes. This is stricter than current isolated
storage, which supports deeper provisional branches. It may reduce throughput
and availability; no measured improvement is claimed. Alternative: an approved
pipelined finalized-cursor protocol in each block with explicit lag, advancement,
pending effects and expiry rules. Selecting arbitrary lag/confirmation values
here would be an unjustified new consensus rule. **Approve finalized-parent
semantics or specify that alternative before implementation.**

New genesis must authenticate a fixed sorted validator Wallet set (<=128) and
the immutable quorum/finality policy. Allocation as reviewer does not confer
validator membership. Existing quorum is `(2*n+2)//3`; retain separate bounded
proofs/attestation signing and no finalized rollback. No dynamic validator
membership events are allowed in this candidate inventory.

There is an additional source-level BLOCKER: existing finality verification takes
externally supplied `equivocators`, while the application excludes locally known
same-height equivocations from proof counts. Equal blocks plus different local
knowledge can therefore differ in available finality decisions. A fixed trusted
set does not by itself resolve that completeness problem. Alternatives requiring
approval are (a) a precisely authenticated, frozen validator-equivocation
inventory/cutoff with proof availability and no finality backdating, or (b) a
versioned self-contained quorum-proof rule that never retroactively discounts
previously counted signatures and defines conflicting proofs as safety failure.
The latter is simpler for fresh sync but changes existing exclusion semantics.
This report does not silently choose it, invent a validator-offense signing
authority, or claim the three reviewer event types solve validator consensus.
Until this is resolved, the candidate recovery algorithm has an explicit
missing trust/rule input and Task 7.17 cannot safely resume.

## 11. Forks, issuance ownership and crash boundaries

A local proposal/certificate produced without an on-chain ISSUE is an inert
draft. It may reserve local service resources, but cannot consume another
validator's global nonce/quota/original claim. All pre-finality block effects
are owned by that candidate branch. Persist candidate R/provisional projections
atomically, acknowledge only after commit, and preserve sources for revalidation.
On provisional unselection, discard/rebuild its projections and release its
branch-owned consensus claims; retain local draft/audit data separately.

After ISSUE finalization, ownership remains permanent even if its media is
never minted, is not selected for later minting, or another encoding is chosen.
Finalized votes/rights/nonces/participation are permanent independently of
issuance. A descendant cannot reissue the same original under another policy,
submission, signature variant or encoding. Reward/media settlement claims arise
only on the settling path; finalized settlement is immutable.

This deliberately amends Task 7.16's permanence of locally issued-but-unselected
claims. Preserving that behavior across independent nodes would instead require
a globally accepted issuance log outside the chain and its own fork/finality
authority. It cannot be reconstructed from an absent off-chain issuance. Old
isolated stores remain historical laboratories; no automatic migration of their
claims, signatures, snapshots or arbitrary root is permitted.

One future database transaction must persist verified R, sources/proofs,
projection delta/root, claims, selected cursor and ledger/reviewer changes
together. On crash, SQLite recovers local atomic state, then verify the retained
cursor/root against authenticated history before serving decisions. Use the
already documented safe journal/runtime rules; no WAL upgrade is performed.
Lost acknowledgements retry by block/event/certificate identity, never generate
another authoritative issuance. Full image snapshots can be local backups but
cannot replace event authority or define logical hashes.

## 12. Independent bootstrap, sync and replay algorithm

1. Obtain approved genesis/profile through the approved release/trust channel,
   pin N/W/G, reserialize genesis, recompute G and validate its allocations,
   policy/statement bytes, bootstrap list/digest and validator authority. Refuse
   a peer-selected replacement. Compute S_0 after G. Missing launch artifact is
   incomplete; contradictory artifact is invalid.
2. Request canonical R and separate required finality proofs in height/hash
   order from genesis onward. Bound both per-record and aggregate response:
   keep existing 64-record/16 MiB transport ceilings, with proof/JSON overhead
   included; split pages sooner as necessary. Never trust a peer's tip/root as
   finality, skip intermediate history blocks or accept a hash-only event URL.
3. For each h verify strict canonical bytes, version/kind/schema/caps, envelope
   hash, N/G context, index and previous hash, predecessor time, authenticated
   parent finality and its approved validator-equivocation semantics. Do not
   consult local latest-finalized receipt time. Missing proof waits/fetches;
   contradictory finalized ancestry stops advancement.
4. Reconstruct and safety-validate every REGISTER/media original byte sequence
   using existing identity/1 or isolated zstd/1 decoding; recheck SHA-256, MIME,
   length, closed technical evidence and creator signatures. Validate new vote
   signatures and signed references; verify rights against their on-chain
   registration time/context. Decoder outage remains local failure, never a
   false invalid-media verdict or accepted prefix.
5. Verify parent_state_root against the replayed map. Execute phases/E order,
   derive every receipt, offense, interval, claim, quota and activity fact.
   Check ISSUE C3 selection against the entire parent inventory and historical
   vote status. Recompute tallies, exact ratios and certificate digest. Never
   accept a producer-supplied status, penalty count or selection as an oracle.
6. Validate ledger/reward/settlement/native rules and single-use originals;
   compute end state and sparse root; compare post_state_root. A bad root,
   missing event, duplicate, invalid order, signature or ownership contradicts
   the authenticated record and rejects it. Complete event bytes make omissions
   within the committed array detectable; signatures never prove unbroadcast
   activity existed.
7. Persist the verified provisional candidate atomically. Selection follows the
   separately approved existing consensus authority; finality proof of h
   promotes its prefix. Maintain each competing sibling's own state. Reject
   selection that detaches finalized ancestry. Discard losing provisional
   deltas without deleting finalized evidence or issuing refunds.
8. On restart read the locally committed cursor, verify schema/integrity and
   source/root linkage; replay from genesis or a previously fully verified local
   checkpoint. Rebuild corrupt projections from sources. If canonical sources
   or required proofs are absent, fetch and verify them; if no peer/archive can
   supply them, report INCOMPLETE and withhold eligibility/certification. Never
   assume zero usage/offenses, an empty bootstrap or a trusted root-shaped hash.
9. For backup/import and fresh sync perform the same staged verification before
   publishing state. An optional downloaded snapshot is acceleration only after
   replay/source verification; no new checkpoint trust or fast-sync proof is
   authorized. Compare source cursor, all logical facts and root, not database
   images. A later separately reviewed succinct proof may be a verifiable
   equivalent; none exists in current source.

Authoritative retained records: exact approved genesis/registry/B0, canonical
block R including all events and original reconstructions, and required separate
finality evidence with authenticated validator context. Rebuildable indexes:
submission/vote/observation/offense/penalty/participation/claim tables, sparse-tree
nodes, selected-branch indexes, current reviewer labels and UI caches. Derived
table corruption never authorizes editing source bytes. SQLite's existing
`durable_vote_records`, penalties or Task 7.16 images are not a substitute for
any lost canonical sources. Different insertion/physical orders must produce
identical facts/root/status/certificate results; this is a future test obligation.

## 13. Security, resource bounds and three-year economics

| Threat | Required result / limit |
| --- | --- |
| Forged bootstrap / identity replay | Recompute approved G/B0 and policy bytes; recover signatures and match N/G/reference; no runtime grant or cross-root reputation mapping |
| Missing signed events / selective omission | Missing committed event bytes or skipped ancestor prevents replay; an omitted off-chain signature has no effect. Block/finality authenticates inventory, not universal receipt |
| Vote replay / high-S / nonce bypass | Semantic message and signer nonce plus accepted dimension tuple; no new participation, attempt or seat from signature variants |
| Penalty suppression | Once proof observations are on chain, derive incident mandatorily; a producer may censor unpublished evidence. No claim this removes censorship; relay through other peers/producers and expose availability failure |
| Quota bypass / concurrent ISSUE | Ordered accepted receipts charge before selection; no certification-only counter, no policy reset, scratch claims serialize same-block conflicts |
| Conflicting certificates | First finalized ISSUE owns H/submission; incompatible same-block ISSUE invalid; competing candidates isolated, conflicting finalized proofs halt |
| History censorship / cheap data spam | REGISTER/VOTE consume real bounded block bytes and verification work. Admission fees/producer selection and incentives are not specified by current history rules; review before deployment, no arbitrary new bounty or compression scheme |
| State-root tampering | Recompute every transition and sparse map from full sources; root supplied with its own snapshot is insufficient authority |
| Finality rollback / malicious sync | Authenticated validator context/proofs and pinned finalized prefix; stop on contradictions, never roll back finality for a late offense |
| Incomplete archive / unavailable event body | Remain incomplete, request another peer; no pruning exemption for old rejected observations, unminted submissions or unused finalized ISSUE |
| Oversize/corrupt/local failures | Enforce child/count/depth/total bounds before expensive work; worker/I/O/storage failures withhold verdict, never certify partial history |

Added canonical bytes are exact event bytes plus array/wrapper/root keys.
VOTE includes one full signed payload/signature (<=4,096) plus event wrapper
(event<=8,192). For 10 minimum voices across dimensions the event-cap envelope
is <=81,920 plus list/wrappers; same five Wallets in both dimensions still need
ten dimension signatures. At full 32 selected voices it is <=262,144 BEFORE
list/wrappers, so full maxima cannot all fit a 262,144 media history value:
use history blocks. ISSUE event<=200,704 contains a full C3 that the eventual
media block also embeds. REGISTER<=2,883,584 contains preliminary original
media; mint retains that original again in its own descriptor to preserve
existing MODEL A per-media-block semantics. This can roughly double payload
retention for a registered-and-minted original, depending on encoding, plus
certificates/vote observations. Unminted registrations also remain forever.
No “small root overhead” claim hides these bytes.

The old analytic 3,058,797-byte block-3 ceiling does NOT prove amended blocks
fit. It leaves 86,931 bytes before new fields/events; complete C3/history
accounting and mandatory identity reservations need new golden vectors. Enforce
the 3 MiB cap in every case; do not silently raise it or exclude history from R.

SQLite must retain canonical source BLOBs once per source block, derived indexes,
tree nodes/deltas and proofs. Avoid per-issue full DB image copies. Sparse map
updates need at most 256 internal path hashes per changed key before shared-path
reuse; signature verification, media reconstruction and safety validation add
work. No measured storage amplification, hashes/sec, replay throughput, network
latency or savings for this design exists. Bound per-block work by <=256 events,
all size/signature limits, existing native caps and independently validated
media-worker limits; benchmark worst-case signatures and tree mutations before
activation. Absolute CPU/peak-memory ceilings remain a resource-review gate.

For defensible planning let delta be incremental canonical bytes/day including
extra history blocks, not just media-block count. Three-year raw history addition
is `1095*delta`; physical storage multiplies measured DB amplification a, backup
retention and proof/index overhead. Example ASSUMPTIONS only: 1,000 media/day,
100,000 extra bytes per media equivalent (all control history amortized),
365-day years, no growth, no compression of backups. Added raw history is
109,500,000,000 bytes = 101.980 GiB. At assumed a=1.25 primary addition is
127.475 GiB, excluding separately modeled proofs; one complete sync needs at
least raw bytes plus proof/transport overhead. Outbound p full copies would
be at least p times those bytes; normal gossip/retries vary. At the proposed
maximum REGISTER cap alone, 1,000 registrations/day for 1095 days is
2,883,584*1,095,000 = 3,157,524,480,000 bytes (2,940.674 GiB), even before
minting, observation/ISSUE, proofs or DB overhead. These are capacity scenarios,
not measured workloads, pricing or benefits.

The [Task 7.8 model](milestone-7-node-economics.md) must be rerun later with
observed history bytes, block rate (control blocks count), DB/tree amplification,
replication/backups and replay CPU. Its old affordability thresholds cannot be
reused as evidence that this design meets a three-year node budget. Preliminary
on-chain media is a significant economic/abuse tradeoff requiring approval.

## 14. Byte examples, future vectors and acceptance tests

The following are test-only primitive oracles, not launch identities, valid
certificates, complete state snapshots or a new accepted fixture manifest.
No signatures/keys are generated for this documentation task. All text inside
the code fences is the exact preimage (no final LF); hash binary prefixes as
specified, not the Markdown fence. Standard-library reproduction follows.

```json
[]
```

`S(J([]))=4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945`.
This is also the existing empty native array aggregate; an empty event array
alone is not a complete history commitment.

```json
{"denominator":7,"numerator":5}
```

The exact 31-byte reduced-ratio oracle and sparse-tree empty/key/leaf examples
below are checked independently with Python and .NET SHA-256. `example` and
empty identity are test strings for the key hash primitive, not a permitted
state-kind record. The complete reproducible equations are:

```python
import hashlib, json
def J(x):
    return json.dumps(x, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=False, allow_nan=False).encode('utf-8')
def H(b): return hashlib.sha256(b).digest()
ratio = J({'numerator':5, 'denominator':7})
key_bytes = J({'domain':'zoidbergchain/reviewer-state-key/v1',
               'kind':'example', 'identity':[]})
K = H(key_bytes)
fact_bytes = J({'kind':'example','identity':[], 'value':{}})
V = H(fact_bytes)
leaf = H(b'\x00' + K + V)
empty = H(b'\x02')
for depth in range(255, -1, -1):
    empty = H(b'\x01' + empty + empty)
for name, data in [('ratio',ratio), ('key',key_bytes),
                   ('fact',fact_bytes)]:
    print(name, len(data), data.decode(), H(data).hex())
print('leaf',leaf.hex())
print('empty_root',empty.hex())
```

Verified primitive outputs:

| Preimage/output | Bytes | SHA-256 / digest |
| --- | ---: | --- |
| ratio J | 31 | `dc8dc4b48ae383b7b5077c7a78b3de8822afc8e16b675d35e9a98accb9b9f678` |
| key J | 79 | `a91f9824fb08b9fbe3903a0f163cab14fee82551a87af49b24d96f684b2d6bd4` |
| fact J | 43 | `485042912fe041589b27d8055185900472bd58a257aba659360fa8b373df63a1` |
| example leaf preimage | 65 | `235e47e9b63286193f9e52dc2297f57e21c40979faaf481d3097e918d5ca99af` |
| empty leaf preimage `02` hex | 1 | `dbc1b4c900ffe48d575b5da5c638040125f65db0fe3e24494b76ea986457d986` |
| empty root after 256 node levels | 65 at final level | `9b97517f25140762b9e187bae23a31ab78a4230354dece720bbbefcfce8de5a0` |

The next commitment examples reuse ONLY the existing symbolic Task 7.10C
fixture context, never approved launch identities/values. Empty B0 is deliberate
for a minimal hashing example; it FAILS the startup liveness requirement.
Its b/c digests are symbolic, not newly registered policies. G=a*64 is the
existing symbolic fixture, not claimed to hash this bootstrap. These examples
establish preimage arithmetic, not a valid new genesis or accepted block.

```python
from pathlib import Path
root = Path('tests/fixtures/milestone_7_v3_v1')
source = (root / 'block-identity.json').read_bytes()
assert len(source) == 34588
assert H(source).hex() == 'aed15a42772a97f4fd200274dbfaf574b8dd8d0cfbd3dacb030bc06e17b1f21a'
p = json.loads(source)['envelope']['payload']
ctx = json.loads((root / 'manifest.json').read_bytes())['context']
B0 = dict(bootstrap_version=1, network_id=ctx['network_id'],
          reviewer_policy_digest=ctx['media_policy_digest'],
          reputation_rule_digest=ctx['review_policy_digest'], reviewers=[])
boot = dict(domain='zoidbergchain/reviewer-bootstrap/v1',
            network_id=ctx['network_id'], payload=B0,
            protocol='zoidbergchain', protocol_version=2)
BD = H(J(boot)).hex()
fact = dict(kind='bootstrap', identity=[], value=dict(bootstrap_digest=BD))
K = H(J(dict(domain='zoidbergchain/reviewer-state-key/v1',
             kind='bootstrap', identity=[])))
T = H(b'\x00' + K + H(J(fact)))
empty = H(b'\x02')
for bit in range(255, -1, -1):
    right = (K[bit//8] >> (7-bit%8)) & 1
    T = H(b'\x01' + (empty+T if right else T+empty))
    empty = H(b'\x01' + empty + empty)
state = dict(domain='zoidbergchain/reviewer-state/v1',
             network_id=ctx['network_id'], genesis_hash=ctx['genesis_hash'],
             protocol_version=2, history_policy_version=1,
             history_policy_digest=ctx['review_policy_digest'],
             bootstrap_digest=BD, height=0, previous_hash='0'*64,
             tree_root=T.hex())
payload = {k:p[k] for k in ('submission_id','creator_wallet','content_type','media')}
payload.update(content_hash=p['media']['original_sha256'],
               meme_text=p.get('meme_text'),
               technical_evidence=p['admission_certificate']['technical_evidence'],
               attestation=p['admission_certificate']['attestation'])
body = dict(domain='zoidbergchain/reviewer-event/v1', event_version=1,
            network_id=ctx['network_id'], genesis_hash=ctx['genesis_hash'],
            parent_height=0, parent_hash=ctx['genesis_hash'],
            kind='REGISTER', payload=payload)
event = dict(event_id=H(J(body)).hex(), body=body)
for name,obj in [('bootstrap',boot),('bootstrap_fact',fact),
                 ('state',state),('register_body',body),('register_event',event)]:
    print(name, len(J(obj)), H(J(obj)).hex())
print('bootstrap_tree_root',T.hex())
```

| Example | J bytes | Expected SHA-256 |
| --- | ---: | --- |
| bootstrap domain envelope / BD | 413 | `54c806886d13f1bea28d8c33457d1b4f0ae60dccffe146386aa2fa860caf37c0` |
| bootstrap fact | 130 | `ca8fd56ac957f862ee167380eae9caa77f2fd79925b189d649460b4ac2818a7b` |
| state commitment preimage | 566 | `ac1c157774d22cd905a1e16da183b199781fc2ffc75f85d811018b0329eb20b2` |
| REGISTER body / event_id | 5,079 | `68fb72c115fb6217fd95fd07010a8417c90d4bc68a6b31a5a94c885cab0637a6` |
| complete REGISTER event | 5,166 | `5988bc40e887265cff305053a85d9658beac395540ba285cfd63fe4f2eb11afb` |

Bootstrap-only tree root is
`1c449ef8134e36e19d8fd1385fe66d9bdac37bf9d5e184062f2aedcff36b822d`;
its K is `dc2350a2bb087b3ef77d18a7094d9e94fbe94366e104bb5b777568802d883cde`.
Python and an independent Node serializer/source projection/tree calculation
agree; .NET independently agrees on all five exact preimage lengths/hashes.
There is no future containing hash in either event or state preimage. All
intermediate example files are disposable under ignored `temp/task717a-runtime`;
the recipe and expected bytes/hashes above are the durable documentation.

Future golden fixtures
must additionally freeze complete B0/genesis, signed V4 and REGISTER/VOTE/ISSUE
event J bytes, source positions, every fact mutation, tree roots, S_0/S_h,
C3 selection/body/digest, amended R hash and separate finality proof. Use only
published fixture identities, clearly segregated from launch; independently
author expected preimages and a second-language verifier BEFORE using an
implementation as oracle. Include one real nonempty tree with inclusion and
absence proofs, key-bit boundaries, two keys sharing a path, empty/full branch
cases, and an end-to-end registration-to-vote-to-issue-to-mint transcript.

| Future test / vector | Exact acceptance assertion |
| --- | --- |
| Genesis/B0 authority | Same full approved genesis reproduces B0 digest/G/S_0; one grant/policy/validator mutation rejects; G-dependent preimage cycle forbidden; no grants from env/legacy SQLite |
| Established bootstrap/liveness | Empty grant set cannot satisfy first dimension; one signer cannot fill five seats; creator excluded; five noncreator grants plus ten valid dimensional votes can qualify via control history; test offline/nonindependent population operational gate separately |
| Historical eligibility | All creator/native/mixed thresholds and earliest heights; age 14/15/16 blocks; probation time/receipt 9/10 boundaries; current promotion/penalty never rewrites historic vote status |
| Late penalties | Offense source older than finalized ISSUE; proof included at h affects h+1 only, no old root/cert/reward changes; cooldown 3/10, self/rate 1/3, third 25, half-open expiry, overlap/max-end/ties and extension rules |
| Same-height order | Shuffle wire events -> reject; shuffle DB insertion -> same replay; two votes at last quota slot choose earlier event_id; tenth probation receipt never promotes another same-height vote; ISSUE cannot use same-height vote |
| Repeat/conflicting votes | Exact/high-S semantic replay is nonpenalizing; same-choice different message no equivocation; different choice grouped once per dimension; nonce collision never counts; first accepted vote remains |
| Rate/penalty abuse | Distinct submissions and both dimensions; first two quota rejections no rate incident, third one; old-reference relay cannot create penalty-at-receipt or rate offense; rejected unknown/malformed submission never earns usage |
| Missing/contradictory sources | Remove included event, alter event count/order/source or omit registration/proof/ancestor -> no state/certificate; no absent-history=>zero fallback |
| Wrong context | Mutate N then G independently, policy/version/domain/reference, same network label/different root -> reject at every signing/history/import boundary |
| Evidence completeness | Required established seat then first fifteen others; negative/unsure inclusion, cap16/32, omission of selected unfavorable vote rejects; excluded 17th or unbroadcast vote does not invalidate bounded-set proof |
| Exact tally | 5/7, 1/1 with unsure, all-unsure unresolved, 7/10 pass, 6/9 fail; every tally field and reduced-ratio bool/nonreduced/zero-denominator mutation rejects |
| Certification retries | Same cutoff -> identical C3; later parent before ISSUE recomputes; after finalized ISSUE retry returns old bytes; conflicting original/submission/policy/encoding cannot reissue or double mint |
| Forks/finality | Two sibling candidates isolate claims; no accepted child before parent finality; select/unselect rollback provisional changes; no finalized detach; contradictory proofs stop; execute approved validator-equivocation alternative explicitly |
| Independent databases | Separate genesis+source-only imports in randomized physical/insertion orders, different cache state, restart points and supported journal layouts -> equal facts/S_h/status/usage/selection/C3; compare logical bytes, not DB files |
| Canonical-only recovery | Delete ALL derived indexes/tree/labels/claims; rebuild from genesis/R/proofs, reproduce every root and cert; lost canonical event cannot be “rebuilt” from summaries |
| Fresh sync | Two independent configured nodes fetch from adversarial paginated peers; verify every signature/root/proof and same results without trusted local app snapshots; withholding a page prevents completion |
| Crash/concurrency | Terminate pre/post transaction commit, lost acknowledgement; either complete sources+claims+cursor+root or none; no quota double spend; same event/cert retry idempotent |
| Tampering | Single event/body/Pos/root/leaf/path/policy/height/bootstrap mutation changes expected commitment or rejects; producer supplies snapshot+hash without source authority -> reject |
| Resource/capacity | At/one-over each exact field/record/event/list/depth/count/proof/page budget; 3 MiB total for both kinds; mandatory identity reservation; two large REGISTERs cannot evade total cap; many tiny signatures/keys worst work; local worker/I/O failure no false verdict |
| Economic/security regression | Measure registration duplication, unminted spam, tree/index bytes, proof and replay CPU, history-only pacing/liveness; preserve original reconstruction, codecs, active v1 fixtures and no activation |

## 15. Required amendments, approval gates and handoff

The seven Task 7.17 gaps now have explicit proposed contracts: canonical
inventory, E ordering, genesis B0 origin, prospective penalties, deterministic
bounded selection, fresh signed V4/history facts and source-only recovery.
They are design resolutions for review, not completed consensus implementations.

| Gate | Disposition / what must be approved or supplied |
| --- | --- |
| Bootstrap strategy | B recommended. Approve exception/maximum/distribution and later actual grants, genesis data and release authority. No legacy score silently discarded/imported. New-chain reset/state disposition must be approved separately. |
| Block/schema/availability | Approve block 4/history-kind/event field additions, C3/V4/policy versions and budgets; preliminary media permanence/duplication versus a separately designed availability alternative. Frozen v3 cannot accommodate this silently. |
| Finality boundary | BLOCKED pending finalized-parent profile approval (throughput/liveness impact) or an equally precise pipelined alternative. No arbitrary lag chosen. |
| Validator proof authority | BLOCKED: choose/fully specify authenticated equivocation inventory or versioned self-contained prospective proof semantics; genesis trusted set alone is insufficient under current local exclusions. |
| Penalties/eligibility/quota | Approve Rules 3/Reviewer 2/Review 3 historical freeze, prospective late finding, signed reference and acceptance-time usage; retain established earned/schedule/quorum semantics. |
| Admission scope | Approve on-chain timestamp/nonce replacing local challenge/daily/allowlist authority; otherwise specify authenticated global admission inputs before implementation. |
| Selection/replay ownership | Approve earliest established plus earliest fifteen, parent cutoff, finalized ISSUE ownership and rollback of candidate-only claims; no permanent local off-chain consensus reservations. |
| Resources/economics | Proposed event/bootstrap/list caps need review and complete amended size vectors; CPU/memory/registration-spam/producer incentives and three-year model need measurement before activation. No economic promise or new fee/reward chosen. |
| Independent recovery | Procedure specified, not implemented/tested; canonical event/proof archival retention and authenticated launch distribution must exist. No snapshot-only trust fallback. |

After those protocol choices and independent byte/vector review, a separately
authorized implementation task may implement the nonactivating amended schema,
journal/replay and independent tests. Actual launch N/W/G/identities are not
needed for inert tests using explicit fixture contexts; they remain mandatory
before a real launch. Decoder/platform safety, live ledger/queue/consensus,
networking and storage integrations remain existing activation gates.

**Task 7.17 cannot safely resume now.** In particular, no history-journal code
should be built against the unchanged v3 schema while finality/replay/admission
authority choices are unresolved. This task neither begins that implementation
nor resets, migrates, signs launch data or deploys a chain.

## 16. Focused verification record

Existing focused tests ran using the project Windows environment, with
`TEMP/TMP` and basetemp confined to ignored `temp/task717a-*`:

| Selection | Result |
| --- | --- |
| v1 protocol, frozen golden vectors, native transfers and pure finality quorum arithmetic | 73 passed |
| Task 7.10C frozen inventory and 65 golden vectors, portable preimages, exact ratio comparisons, size accounting and nonactivation | 70 passed |
| Existing reviewer/reputation policy constants and preserved version/digest tests | 2 passed |
| Combined selection | **145 passed in 3.20 s**, no failures or skips |

JUnit is disposable `temp/task717a-focused.xml`. These selectors use published
signatures/fixture scalars and pure policy checks; no random signing-key creation
or live database occurs. No existing test or fixture was edited. Reproduce with:

```powershell
.\.venv\Scripts\python.exe -B -m pytest tests/test_protocol_v1.py tests/test_protocol_v1_golden_vectors.py tests/test_protocol_v1_native_transfers.py tests/blockchain/test_task_3_5_validator_quorum_finality.py::test_validator_quorum_is_ceiling_of_two_thirds tests/test_milestone_7_task_7_10c_v3.py::test_frozen_inventory_and_published_oracles tests/test_milestone_7_task_7_10c_v3.py::test_versioned_golden_vectors tests/test_milestone_7_task_7_10c_v3.py::test_portable_canonical_preimages_without_crypto_dependencies tests/test_milestone_7_task_7_10c_v3.py::test_all_ratio_inputs_and_pairwise_comparisons tests/test_milestone_7_task_7_10c_v3.py::test_size_formula_complete_limit_and_child_budgets tests/test_milestone_7_task_7_10c_v3.py::test_active_runtime_does_not_import_isolated_package tests/test_milestone_5_task_5_5_earned_reviewer_eligibility.py::test_policy_v1_constants_serialization_digest_and_epoch_boundaries tests/test_milestone_5_task_5_7_reviewer_reputation.py::test_reputation_rule_v1_is_preserved_and_v2_is_active_and_deterministic -q --tb=short -p no:cacheprovider --basetemp=temp/task717a-repeat
```

Independent Python/Node/.NET byte/hash checks reproduced section 14 and the
capacity arithmetic in section 13. Documentation UTF-8/no BOM, final newline,
fence balance, local links, trailing whitespace and tracked/untracked diff
checks passed. Final branch/HEAD unchanged; only the two intended documentation
files are modified/untracked and nothing is staged. These checks verify this
specification and unchanged baseline only. They do
not implement or establish independent-node recovery, amended-schema validity,
cross-platform interoperability or measured performance.
