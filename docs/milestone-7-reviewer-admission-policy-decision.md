# Milestone 7 Task 7.17N — Reviewer admission and history-completeness decision

Date: 2026-10-27 (America/New_York). **Specification for owner review only.**

Recommend **A: a bounded, explicitly included signed certification cohort**, with
eligibility evaluated at the immediate finalized parent and permanent participation
only upon finalization of its one media block. No complete global offered-vote
inventory, pre-vote roster, lottery, control block or preliminary media copy is
required. Keep both five-vote/one-established quorums and the exact existing 70%
decisive threshold. Zero decisive votes remain unresolved.

This is a permissioned attestation policy: it proves what the included eligible
signers approved, **not unbiased community review**. A producer can select positive
reviewers and suppress negative or unsure offers. Accepting that limitation, and
discarding unminted participation as consensus credit, are substantive owner
decisions. If either is unacceptable, do not implement A: the specific fallback is
B, an authenticated pre-vote roster with complete responses and authenticated
retry accounting, whose additional history/liveness authority needs approval.
There is no implicit fallback to the unapproved earliest-sixteen rule.

The decisions below narrow the blockers; they do not approve them. **Task 7.17N
is a reviewable decision package. Reviewer-history Task 7.17 remains BLOCKED.**
Full G2 application authentication also remains incomplete.

## 1. Repository verification and scope

| Prerequisite before edits | Verified result |
| --- | --- |
| Branch | `Compression-State-Bloat-and-Node-Economics`, expected |
| HEAD | `0b7b4100afbfe625b585fbc38c115aae1f3c2910` |
| Worktree/index | Clean, including untracked files: `git status --porcelain=v1 --untracked-files=all` returned no entries |
| Separate Task 7.17M commits | `678a06a` contains report/verification artifacts; `0b7b410` contains isolated verifier/adapter, fixtures and tests, plus two earlier test-reference adjustments. Neither contains this policy decision. |
| Tracked prerequisites | `isolated_g2717m/verifier.py`, its authority adapter, `canonical_v3/issuance.py`, `history.py`, `atomic.py`, and Task 7.14/7.15/7.17M tests are tracked |
| Instructions | No applicable ancestor, repository-root or docs `AGENTS.md` found; no delegation |
| Authorized changes | This new document and a link/current-gate note in the 7.17B amendment only |

Read the required [7.17A decision](milestone-7-v2-reviewer-history-consensus-decision.md),
[7.17B amendment](milestone-7-v2-reviewer-history-protocol-amendment.md),
[freeze blocker](milestone-7-v2-history-freeze-and-recovery.md),
[issuance](milestone-7-v2-evidence-issuance.md),
[history integration](milestone-7-v2-authenticated-evidence-integration.md),
[atomic certification](milestone-7-v3-atomic-certification.md),
[G2 contract](milestone-7-g2-genesis-and-bootstrap-contract.md),
[G2 verifier report](milestone-7-g2-genesis-verifier-implementation.md) and
[distributed finality decision](milestone-7-distributed-finality-protocol-decision.md).
Their older gate snapshots are historical, not current implementation claims.

Source inspection included `Blockchain.cast_signed_submission_vote_operation`,
`dual_review`, `admission_certificate`, `milestone5_policy`, `wallet_auth`,
`review_policy`, reviewer eligibility/reputation services, and the isolated
evidence/issuance/history/atomic/block/media/primitives and G2 verifier modules.
No production code, canonical schema, signer, agreement engine, live database,
identity, validator authority or deployment was changed. No commit/push/merge,
reset, migration, activation, journal implementation or subsequent task.

## 2. Preserved semantics versus explicit amendments

Existing active v1 rules and isolated protocol-2 laboratory rules are distinct.
In particular, the active dual-review signature is V2, the isolated signature is
V3, and 7.17B's V4/C3/block4 are unimplemented proposals. Version numbers alone
do not make their proposed source authority approved.

| Subject | Authoritative implemented behavior | Recommendation / status |
| --- | --- | --- |
| Who reviews | `dual_review.review_policy`, eligibility service: probationary or established; NEW/COOLDOWN/SUSPENDED cannot count | Preserve eligible statuses; derive them from authenticated parent history |
| Identity | `wallet_auth`, `dual_review.verify_vote_record`, `evidence.validate_vote`: exact personal-sign message and recovered Wallet; no display-name authority | Preserve recovery; directly sign G, creator and finalized reference in proposed V4 |
| Qualification | `milestone5_policy`, `qualification`: wallet age `floor((F.height-origin_height)/5)>=3`; creator path 2 distinct finalized minted submissions, native path 5 distinct nonself transactions spanning >=3 epochs, mixed path 1 minted +2 native | Preserve values and creator/native/mixed priority; origin includes self-transfers for age but they do not earn transaction count |
| Established | Explicit bootstrap grant, or earliest earned qualification plus >=3 probation epochs and >=10 distinct accepted probationary submissions | Preserve thresholds; **amend accepted participation to finalized selected certificate votes only**; clean G2 grants are a launch approval, not current legacy grants |
| Dimensions | Originality: original/not_original/unsure; admissibility: admissible/not_admissible/unsure; separately signed, separately tallied | Preserve; same Wallet may vote in both, never fill two seats in one dimension |
| Self-vote | Blockchain rejects creator Wallet, retains authenticated attempt for objective offense; certificate validators reject self-votes | Preserve; require signed creator binding plus actual authenticated media/rights, not producer assignment |
| Limits | Policy 5 probationary /25 established participations per five-finalized-height epoch; two dimensions share one submission participation | Preserve numeric caps; **change authority/lifetime** as below; finalized-only counting makes these caps nonbinding in ordinary media-only operation |
| Implementation nuance | `ReviewerEligibilityService._accepted_votes` collapses by submission across dimensions; `vote_decision` counts that deduplicated history. Atomic reservations explicitly key `(wallet,submission,epoch)` | Do not describe the code as already a complete cross-epoch event protocol. Chosen cohort has one common F and both dimensions finalize together; no later participation on that target is accepted. |
| Unsure | Both tallies include unsure in quorum/participation, exclude it from decisive denominator | Preserve; no penalty for uncertainty or negative judgment |
| Replacement/conflict | Exact accepted retry returns existing record; another counted same-dimension vote rejects; different choice supports grouped equivocation | Preserve after canonical acceptance; no global first-off-chain-arrival rule exists. Before finalization offers are drafts, as explicitly amended. |
| Historical status | `status_at_reference` reconstructs earliest qualification and penalties rather than trusting current labels, but accepted observations/negative transitions still come from local storage | Preserve historical query; replace local authority with complete finalized sources |
| Penalties | Five objective families, per-type escalation, half-open epoch intervals, suspension precedence, underlying-status restoration; analytics alert only | Preserve schedules; **approve prospective canonical-inclusion activation**, not local discovery/backdating; source scope narrowed in section 8 |
| Quorum | `dual_review.tally`, `evidence._derive_tally`: >=5 eligible and >=1 established **per dimension** | Preserve independently; establishment is at F, not produced by this candidate |
| Approval/rejection | With quorum and `d=p+n>0`, approve iff `10000*p>=7000*d`; otherwise resolved negative. No decisive votes => unresolved | Preserve exactly; rejection tally exists, but an admission certificate requires both positive outcomes |
| Fractions | Isolated block uses reduced integer `p/d`; block approval/originality ratios describe originality | Preserve gcd reduction, no floats, rounding, weighting or combined-dimension score |
| Rights | Creator attestation binds original SHA, submission, creator, policy and technical evidence; it is an assertion, not an independent ownership adjudication | Preserve exact statement/signing family and technical/media checks; keep N unique across roots |
| Evidence selection | Issuer requires byte equality with the entire frozen selected snapshot; it never defines the production selection policy | **Amend source of freeze** to exact candidate-included cohort; every member of that chosen set must appear, but it need not contain every offered vote |
| Issuance/replay | Atomic laboratory permanently reserves off-chain issuance and participation in its own trusted DB | **Amend global authority**: only finalized canonical inclusion makes claims permanent; drafts/failed siblings do not reserve global history |
| Service controls | Runtime allow/deny lists, daily controls, challenges, queue/manual blocks and wall-clock receipts affect local admission | Explicitly classify as relay controls; no environment/cache/local receipt may alter consensus validity. Global equivalents would need another approved authenticated protocol. |

The current issuer's incomplete-review branch returns `IncompleteEvidence`;
its verifier rejects a *present complete certificate* claiming inadequate review.
Its trusted history callback cannot prove distributed completeness. The G2
verifier always withholds full semantic approval and can return
`VALID_ENVELOPE_INCOMPLETE_POLICY`; this document does not change that code.
Also, `reviewer_reputation.canonical_signed_vote_evidence` explicitly requires
protocol 1 today. Its existing verifier cannot simply authenticate proposed V4
observations; the approved Reputation 3 source/verifier and independent context
vectors are necessary before this policy can be implemented.

## 3. Authoritative evidence alternatives

Here, completeness means all records that the approved state machine permits to
change consensus state. It need not mean every statement ever made off-chain.

| Criterion | A. Included bounded signed set — preferred | B. Roster committed before voting | C. Global authenticated offered-vote inventory |
| --- | --- | --- | --- |
| Independent verification | Recover included signers; replay F; count exact included set | Verify prior finalized manifest, member eligibility and all required response/timeout sources | Replay full ordered inventory and selection over its complete prefix |
| Cherry-picking | Producer may select supporters; no unbiased-sampling claim | Prevents dropping required negative responses within a fixed roster; discretionary roster choice/retry can still select supporters | Cannot omit a vote already accepted into inventory; can censor offers before acceptance and manipulate candidate timing |
| Omission/censorship | Unincluded negative/unsure votes have no tally force, even if locally known | Missing response must block/expire, not become approval; inclusion of roster/response can be censored | Inclusion censorship remains; signatures alone cannot prove that every offered vote was received |
| Influence/independence | Equal weight among chosen Wallets; common control remains possible | Equal influence within committed roster; roster source must establish distribution if independence is claimed | Inventory participation remains vulnerable to Sybils, early-seat capture and withheld offers |
| Determinism | Same candidate+F => same verdict; different producers may choose different valid certificates | Same manifest+complete responses => same outcome; not necessarily same manifest choice | Same committed cutoff+complete prefix => same selected set |
| Replay/counting | Signed target/context, one Wallet/dimension, finalized claims | Also manifest ID, one active attempt per original, seat/response claims | Also ordered admission receipts and first-acceptance identities |
| Quotas | Finalized selected participation only; failed/off-chain offers consume no lasting slots | Reservations/response credit require authenticated accounting, including failed rosters | Every accepted unminted vote can consume slots; the complete receipt history is mandatory |
| Off-chain availability | Needed for preparing a candidate; finalized source bytes all in archive | Precommit manifest and responses must stay available, including failed/expired attempts | All committed accepted/rejected/unselected sources and coverage proofs must stay available |
| Bytes/size | <=32 selected records; no roster; bounded optional misconduct observations | Manifest plus complete bounded responses and prior inclusion proofs; history for failures | Potentially unbounded total inventory; per-block batching/backpressure, lookup proofs and retention needed |
| Latency | Can admit first media directly against G2 | At least one authenticated pre-vote commitment stage; canonical precommit may wait for another media | Admission into inventory before cutoff; either extra finalization stage or producer-chosen current pool |
| Bootstrap/recovery | G2 grants + full media/proof archive; cannot earn on failed media | Need live precommit authority before first media or approved genesis roster for specific targets | Need genesis inventory origin and authenticated range/count completeness from that origin |
| Complexity | Smallest; substantive lifecycle narrowing | More state, deadlines/retries and liveness authority | Largest; global admission, availability, completeness, resource and censorship protocol |

**Choose A only with permissioned attestor trust explicitly accepted.** Technical
originality duplicate checks, byte identity and media safety still apply, but
signatures cannot ensure the underlying human judgment is honest. If the goal is
instead a binding community-wide negative veto or a representative unbiased
sample, A fails that requirement. B is the targeted alternative; C is unnecessary
unless accepted-vote inventory itself is a required product/consensus feature.

For B, the minimum additional owner decisions are: who selects the roster from
S_F, exact size (five vs up to sixteen per dimension), established seats, prior
canonical manifest inclusion, response deadline in finalized heights, complete
responses vs separately approved missing-response threshold, and one active
attempt per original with finalized expiration/replacement history. Recommend
complete responses if B is chosen; do not treat nonresponse as positive. A
manifest signed by a producer or all invited Wallets can prove roster agreement,
but cannot prove it is the only attempted roster. An off-chain co-signature
scheme therefore does not remove authenticated retry/claim history requirements.

If C is required, a fresh node must verify genesis-authorized empty initial
inventory, every contiguous canonical block's complete bounded inventory array,
source bytes, deterministic acceptance outcomes and authenticated cutoff/ordering.
A root requires full replay or a separately approved proof of **range coverage and
absence**, not just membership proofs for chosen positives. Completeness is only
of consensus-accepted entries; universal off-chain completeness additionally needs
a specified broadcast/receipt and availability authority, currently absent. Do
not freeze C on a producer-supplied list, digest or assertion of completeness.

## 4. Exact included-cohort policy and 7.17B assessment

This section defines proposed Review 3 semantics, conditional on approval.

1. Candidate population is every Wallet with probationary/established status in
   S_F, no active penalty, not the authenticated creator, and sufficient quota.
   No invitation registry, local allowlist or new enrollment authority.
2. A certificate explicitly chooses **5..16 distinct Wallets per dimension**,
   each with a signature for that dimension, including >=1 established at F.
   Up to 32 signatures and 32 distinct Wallets across both dimensions;
   the two populations may overlap. No mandatory designated established seat.
3. Count **all** members of that included dimension. There is no second filter
   that discards negative, unsure or oversized members after commitment.
   Before freezing a draft, a builder can choose another subset; that discretion
   is the A trust tradeoff, not an authenticated earliest or random selection.
4. Serialize the union by `(dimension,canonical_wallet,vote_identity)` as today.
   Ordering is byte/ASCII lexical order of these canonical strings; it is not
   receipt order, influence ranking or a lottery. No verifiable randomness is
   proposed. All eligibility references must equal the exact immediate F.
5. V4 signature authenticates participation offer, target, creator, dimension,
   choice, N/G, policy and F. It does not promise that all offers will be counted.
   There are no separately authenticated invitations under A.
6. A repeated `(dimension,wallet)` in the certificate invalidates it, including
   identical/high-S/same-choice variants. Exact relay of a whole candidate is
   idempotent. A signed message/nonce cannot earn multiple participation claims.
7. Different signed choices from one Wallet are equivocation evidence when both
   are retained with verifiable target/context. There is no replace-vote operation.
   A certificate containing both as counted votes is invalid. A contradictory
   observation can accompany one selected statement, causing a **prospective**
   penalty; it does not retroactively remove that first finalized acceptance.
   A hidden conflicting statement cannot be detected from the disclosed signature.
8. Wrong dimension, wrong choice vocabulary, creator, target, network, G, parent,
   policy, signature or claimed status makes that counted evidence invalid.
   A vote on originality never fills an admissibility seat. Unsure counts as one
   seat/participation, contributes zero to d, and needs no replacement privilege.
9. No global arrival cutoff is claimed. The candidate's included list closes when
   its exact bytes are proposed. Later off-chain votes do not mutate those bytes;
   an unfinalized candidate can be rebuilt and fully revalidated. A finalized
   certificate never reopens or acquires more participation on its target.
10. There is no permanent pending cohort, cohort ID, cohort expiration event or
    reservation under A. Draft validity ends when F changes or its signed time
    interval no longer covers the candidate timestamp. Local drafts may expire.
    New signatures/nonces referencing the new F are required after advancement.
11. Failed/undecided review may be retried for the **same submission/H/creator**,
    with no global quota claim. The same Wallet may not use a conflicting choice
    as a legitimate correction. New submission IDs/encodings cannot remint an
    already finalized original. A does **not** provide a permanent veto from an
    unfinalized negative cohort; if that is required, choose B and commit failures.
12. Certificate <=196,608 J bytes, vote <=4,096, message <=2,048; no favorable
    substitution during verification to make an oversized frozen certificate fit.

7.17B's earliest-established-plus-fifteen rule is unapproved. Its “earliest” is
verifiable only relative to finalized canonical receipt locators and disclosed
candidate events, not the first off-chain offer. Event-ID sorting authenticates
a deterministic order for disclosed input; it does not prove first publication,
and nonce/input choices can influence that order. Selective withholding defeats
its intended coverage before inclusion. If sixteen early receipts are unsure,
later decisive votes cannot enter; negative early receipts can likewise lock the
target. Never recover supposed earlier order from time fields, SQLite insertion
or local receipt clocks. A abandons this exact-inventory selection requirement
openly; it retains exact equality with the **chosen** frozen set at verification.

## 5. All-unsure, rejection, pending and failure outcomes

For each dimension let p/n/u be positive/negative/unsure counts, t=p+n+u,
e the established count, d=p+n. Quorum is `t>=5 && e>=1`. Resolved requires
quorum AND `d>0`. Approval requires resolved AND `10000*p>=7000*d`.

| Outcome | Deterministic handling |
| --- | --- |
| A. Certified admission | Both dimensions approved; rights/media/replay/ledger and complete evidence valid. Certificate is a provisional admission until its block finalizes. |
| B. Certified rejection | Current tally supports resolved negative judgment; the admission certificate format **does not certify rejection**. Recommend no new rejection wire object or lasting rejection/claim under A. A signed negative tally can be displayed as a local result, not global finality. |
| C. Incomplete/undecided | Fewer than five, no established, d=0, one dimension unresolved, or not enough responses: keep locally pending or expire the draft; no canonical acceptance/credit. A negative dimension suffices to prevent admission even if the other is unresolved. |
| D. Invalid evidence | Bad signature/context, duplicates, false historical eligibility/tally/hash or a supplied complete admission certificate asserting insufficient/negative approval: reject that evidence/candidate; no writes/claims. |
| E. Locally unavailable | Missing authenticated history/proof/source or unavailable decoder/storage/verification resources: incomplete or local failure, never positive approval or a fabricated invalid-media verdict. |

Both dimensions with five unsure votes have quorum and **d=0, unresolved**.
One positive dimension and one all-unsure dimension still cannot admit. Never
construct p/0, call it 1/1, or add a new minimum-positive/majority threshold.
Conversely, **one positive plus four unsure with one established passes under
existing semantics**: d=1 and p/d=1/1. This integrity limitation is preserved and
must be acknowledged, not quietly strengthened to solve uncertainty.

A 2/2 decisive split plus one unsure resolves negative (50% <70%); 7/3 passes
exactly; 5/2 reduces to 5/7 and passes. A reviewer who disappears cannot be counted
without a valid signature, but a previously supplied valid signature can be used
without that reviewer staying online. A builder may gather other eligible signers
under A. Retry churn costs local resources, but cannot repeatedly consume permanent
quota because unsuccessful attempts never create canonical participation. Authentic
misconduct can still be recorded later under section 8; choosing a new draft does
not erase signed equivocation proof. Conditional progress means eventually enough
eligible signers make both dimensions positive and live validators finalize that
fully valid media. Technical validity alone cannot guarantee favorable judgments.

## 6. Finalized-parent application timeline and concurrency

| Stage | Data and state boundary |
| --- | --- |
| Trusted genesis | Independently pin G2/N and supported full policy sources; verify grants/native bootstrap/static authority and clean history. Compute J0 **after G**. M's envelope-only result is insufficient for this future semantic step. |
| Finalized F at k | Have complete R/proof ancestry and replayed S_F, J_F; review epoch `k//5`. Genesis `(0,G)` is the special initial anchor. |
| Submission | Validate exact original media/technical evidence and fresh creator rights locally. No chain registration, media duplication, quota charge or original ownership yet. |
| Evidence offers | Signers obtain/verify target+creator and sign V4 against `(k,hash_F)` and this review policy; no current block hash/own certificate/finality is signed. |
| Proposal preparation | Choose bounded included set; rederive status/quotas at S_F and tallies; prepare optional observations, input digest, C3 and implicit event IDs. All provisional. |
| Candidate at k+1 | One canonical media, C3, native/reward and bounded history bytes. Validate intrinsic inputs, parent finality, all application transitions on scratch state; calculate delta/J_(k+1), then block envelope/hash. |
| Tendermint proposal validation | Evaluate the same deterministic `valid(B,F)` before prevoting; respect the separately specified lock/valid-round rules. No quorum signature can waive application validity. Q4 remains outside B. |
| Finality | Verify exact scheduled proposal and q3-of-N4 precommits under authenticated G/N/A/C/epoch0 and all required application checks; persist complete sources/proof/transitions atomically. No authority roster/engine change in this task. |
| Committed transitions | Selected participation, ISSUE and replay ownership, media/native activity and prospective incident penalties become authoritative. Query new status from S_(k+1) for the next child. |

The dependency order is policies/B0 -> G -> J0 -> media/rights/V4 -> raw events
and selected-cohort validation -> C3 -> ISSUE ID -> delta/Jh -> block hash -> Q4.
No vote needs its own future containing block hash. Current media/native activity,
promotion credit or penalties cannot establish its own parent eligibility.

An **unfinalized** C3 pins F and cannot be carried forward after another media
finalizes. Rebuild at the new parent and collect fresh V4 context/nonces; old
unaccepted signatures cannot be relabeled. Under A there are no finalized
issued-but-unminted certificates to settle later: ISSUE and media settlement are
atomic in the same media block. Already finalized C3 is retained unchanged solely
as historical evidence, never minted a second time.

Competing media blocks at k+1 independently use S_F; a shared reviewer may sign
different submissions (not equivocation) and occur in several provisional cohorts.
No sibling consumes another's global quota or original claim. Only one can
finalize. Losers discard branch projections and rebuild at the winner's parent;
their off-chain certificates/signatures remain operational audit data. Exact
reproposal of the same B in a later Tendermint round retains B/C3 bytes; round
changes are outside B. Canonical interval checks use the candidate's timestamp,
not the verifier's clock; verify monotonic parent time and signed
`issued_at<=timestamp<expires_at` with exact integer UTC microseconds as in B.
This is not a wall-clock freshness guarantee; a live time-admission policy remains
a separate combined-profile freeze issue if stricter freshness is desired.

## 7. Complete history and quota authority

Classes below: **A** finalized canonical record; **B** retained signed source with
authenticated availability/coverage; **C** genesis-authenticated initial state;
**D** local operational metadata. B authenticates a statement but changes state
only when A includes it and the approved transition authorizes its effect.

| Consensus fact | Required source / reconstruction |
| --- | --- |
| Initial eligibility | C: clean B0 grants and approved reviewer/reputation sources; no imported legacy score/usage/penalty |
| Identity, rights, target | B signed bytes included in A media/certificate; reconstruct original SHA and creator/technical/rights binding |
| Earned qualification | A finalized distinct creator/native activity; recompute earliest qualifying height and age/path priority |
| Promotion | A selected votes with probationary status derived at their exact F; ten distinct submissions, >=3 epochs; count both dimensions once |
| Demotion/penalties | B verifiable observations retained in A; mandatory objective incident derivation and ordered prospective schedules (section 8) |
| Epoch usage | A selected accepted `(wallet,submission,epoch)`; epoch is signed F.height//5, once across dimensions; no usage reset by relabeling/policy/encoding |
| Issued certificates | A embedded C3 only; complete certificate bytes, not a local issuer response or operation row |
| Selected reviews | A exact C3 union; no parent source can contain prior accepted votes for this unminted target under A |
| Replay ownership | A rights/review/nonce/message/signature and original/submission/certificate claims; optional observations retain proof identities as below |
| Failed/unminted participation/issuance | D drafts; no lasting eligibility, promotion, quota or global issuance claims |
| Receipt time, DB status, daily controls, pending queues | D; cannot decide any peer's historical eligibility |
| Finality | A exact block plus separately retained Q4/authority source, checked under G2; local knowledge does not alter validator membership/quorum |

**Completeness rule:** start with clean C; accept changes only from the closed
implicit/explicit source inventory in every contiguous finalized media R. All
source bytes are in R or the required external Q4 archive. The canonical array
length/order, block hash links, replay commitments and Q4 authenticate this exact
prefix. Dropping a record/observation or changing a vote after finalization changes
authenticated bytes. Missing any required bytes means incomplete history, never
zero offenses/usage. No off-chain acceptance can create a missing consensus event
by definition of the proposed amendment. No remote snapshot's self-declared root
substitutes for replay. This proves completeness of the *defined state machine*,
not completeness of human review or absence of censored misconduct.

Keep limits 5/25 and epoch `F.height//5`, with quota checked at S_F before accepting
the selected set. Both dimensions in this one certificate charge once. Promotions
and penalties discovered here constrain children only; do not use same-block
promotion to raise the current limit. Query status from genesis/earliest
qualification/participation and active intervals, without local NEW/established
labels or a node-local unminted-vote inventory.

**Material quota consequence:** clean A permits only one new accepted submission
participation per Wallet per media block. Each epoch contains at most five child
admissions with that signed reference epoch (parents 5e..5e+4). Thus usage is <=5;
the probationary cap is just reached, the established cap 25 is unreachable, and
canonical rate-limit excess cannot occur in this profile. There is no independent
unminted work-rate throttle. Preserve the constants but do not advertise their old
protection. Retaining meaningful unminted quotas requires authenticated acceptance
of that work (B/C or an additional approved history model), not local counters.

Before finality all claims are branch-owned and reversible; validation failure
creates none. After finality retain original `[H]`, submission `[ID]`, certificate
`[digest]`, creator nonce/message/signature and review/nonce/message/signature
claims using the existing N/G/protocol-2 replay namespace. Original identity
excludes submission, policy and encoding. No finalized replay claim is refunded;
policy changes cannot remint. Exact relay/restart is idempotent. Reorganization of
provisional state releases its provisional claims and preserves finalized ancestry.
This explicitly replaces laboratory off-chain permanent ownership, without
migrating or editing that laboratory.

## 8. Observations, offenses and prospective penalties

Minimal additional history consists of optional bounded **VOTE observations**
alongside an admitted media block, using B's raw `{payload,signature_scheme,signature}`
and event body/ID. No explicit REGISTER, unminted VOTE acceptance, standalone ISSUE,
administrator penalty command or fourth event kind is allowed under A. An extra
observation can prove misconduct but **never** earns participation, qualification
or a selected tally seat. Selected bytes occur once in C3, with implicit sources.

Observation target must be this admitted media or an earlier finalized media on
the verified branch, so full original/creator/technical/rights context is already
available. Its signed reference must be a verifiable ancestor or current F, and
its signed creator must match that target. A pending-target claim without such
authenticated context stays local/incomplete; no full preliminary media is stored
just to punish it. This restricts which old off-chain offenses become authoritative
and requires explicit owner acceptance. No accusation or isolated stale signature
may stand in for an authenticated quota rejection or penalty-bearing reference.

Deterministic phases are: validate target/registration and every raw signed source;
validate selected votes/status/quota at S_F, accepting only the certificate set;
classify the extra observations and proof identities; derive incidents from the
whole disclosed transcript; then ISSUE/settlement and end-state changes. Within
each phase use canonical event IDs/order, never local receipt times. A failed
selected vote invalidates the candidate; do not downgrade it to an observation.
Extra observations may be valid negative/unsure/unselected, duplicates or objective
rejected attempts; their classification never promotes them into the selected set.

For proof processing retain B's precedence where applicable: semantic duplicate,
already accepted tuple conflict, self-vote, stale reference, invalid interval,
nonce conflict, active parent penalty, unqualified, closed target, exhausted quota,
otherwise **unselected observation** (instead of B's accepted participation).
Selected tuples and nonces are fixed before optional observations, so an extra
cannot displace a selected acceptance. Old-target attempts are closed except for
cryptographically provable misconduct. A stale record cannot earn participation
or manufacture an earlier quota-rejection receipt. Invalid source signatures,
wrong creator/context or unavailable ancestry cannot create an incident.

| Existing offense | Retained effect and authoritative proof limitation |
| --- | --- |
| SIGNED_VOTE_EQUIVOCATION | Same Wallet/submission/H/dimension and authenticated creator, two valid distinct signed choices; group once by that tuple. Cooldown 3 then 10 epochs, third distinct incident onward suspension 25. Same-choice signatures/high-S do not prove it. |
| CREATOR_SELF_VOTE | Signed creator=reviewer plus authenticated actual target; once per semantic signed message. Cooldown 1 then 3; third onward suspension 25. |
| RATE_LIMIT_ABUSE | Needs three distinct canonical quota-rejected observations in the same epoch with complete accepted usage causes; cooldown 1 then 3, third distinct epoch onward suspension 25. **Unreachable in clean A's one-participation-per-media history**, as proved above; local rejected work cannot activate it. No fake excess receipt is accepted. |
| VOTE_DURING_COOLDOWN | Signature directly pins an actually penalized reference. Extend prospectively without shortening, using the signed-reference source interval's duration as in B; old pre-penalty signatures cannot prove this offense. |
| VOTE_DURING_SUSPENSION | Same authenticated source requirement; record only, do not shorten/release suspension. |

Use B's incident preimage/domain, grouped identities and penalty-ID=incident-ID;
idempotence is by semantic message/incident, not variant signature. Process
triggers by logical observation position, then offense rank
equivocation/self/rate/cooldown/suspension and incident ID. Derive incidents
mandatorily when their proof enters the transcript; no unsigned outcome flag.
The first current observation that completes a pair triggers the incident; earlier
finalized observations are already in replayed state. No already finalized
incident is charged twice. A known included proof cannot be silently omitted from
the derived penalty state.

For incident first proven at h, activation is after h finalizes, start epoch
`h//5`; interval `[start,start+duration)`, first constraining children of h.
Do not backdate to old signed reference. Overlaps use suspension precedence and
maximum active end, then deterministic source choice (greatest end, then penalty
ID). Cooldown attempts use B's prospective
`max(current_cooldown_end_or_start, h//5+source_duration)`; while suspended record
only. On expiry restore underlying earned/granted status. Finalized certificates,
media and rewards never change because of later proof. No subjective plagiarism,
negative judgment, collusion alert, validator discipline or grant revocation is
automatically a reviewer offense.

Included observation messages claim their semantic identity once; first unowned
signer nonce is recorded, conflicting ownership is a rejected attempt, never an
overwrite of selected/prior ownership. Preserve full signed sources and outcomes
for replay. New high-S variants of an observed message create no fresh attempt,
quota charge or incident. Optional observations can be censored before inclusion;
there is no promise that every objective offense becomes a canonical penalty.

## 9. No-media progress and the explicit liveness choice

| During no accepted media | Can progress? |
| --- | --- |
| Registration/contact/relay queues | Operationally yes; no new authoritative grant, activity or enrollment state |
| Review collection/certificate preparation | Yes against fixed F and candidate timestamps; no lasting participation/claims |
| Penalty evidence collection | Yes locally; global penalty waits for an admitted media carrying it |
| Validator rounds/timeouts/nil messages | Yes under the separately approved agreement contract; no new application block/epoch; validator epoch remains static zero |
| Reviewer epoch, wallet age, probation duration | No finalized height advance, so no advance |
| Quota expiration/penalty expiry | No clock advance; wall time cannot clear them. In A, quota exhaustion alone is not reachable from clean history, but penalties/unavailability can stall. |
| Promotion/native qualification | Queries can recognize already finalized causes; new causes cannot finalize without admitted media |

With adequate eligible noncreator bootstrap reviewers, the first media can carry
its own full signed certificate directly, without prior registration. Select no
real identities here. Empty or insufficient grants cannot bootstrap an established
seat; five total grant members cannot review a creator among those five without
another eligible noncreator. Grants need common-control and availability review.

If every usable established reviewer is unavailable/penalized, and no other media
can meet quorum, height-based restoration can deadlock. Never use empty media,
dummy approvals, arbitrary minting, wall-clock expiry, local replacement grants or
validator votes as a reviewer waiver. Preferred strict-media choice is to **accept
this halt** pending a separately approved change. A valid future submission can
progress while enough unpenalized eligible reviewers and validators remain; no
unconditional recovery guarantee exists.

The minimal *alternative* for independent clock/evidence progress is a new
consensus-authenticated **CONTROL history record**: no media or creator reward,
parent/context/time, bounded events/native payload if approved, replay commitment
and normal finality. Even an event-free instance would be a non-media clock tick,
not a media block. Approving it requires block-kind/schema, height/epoch mapping,
pacing/anti-spam/incentives, archival/CPU costs and safe authority review. It also
changes the strict media-only G2/agreement application-validity profile. It is
**not adopted, implemented or approved here**; B may need this authority to commit
its first roster and retries when no media can otherwise advance.

## 10. Threat model and protection boundaries

| Threat | Protection / remaining limitation |
| --- | --- |
| Producer selects positive signers, omits negative offers | A permits it; neither signatures, canonical ordering nor input digest proves balanced selection. Owner must accept permissioned attestor trust or choose B. |
| Reviewer collusion/Sybils | Signature recovery prevents impersonation, not common ownership. Earned activity and grants are permissioned/economic assumptions, not proof of independent humans. No new Sybil oracle. |
| Established capture | >=1 at F per dimension is cryptographically checked from history; a captured established group can collude or refuse service. Additional independence/governance needs separate rules. |
| Replay across submission/encoding | Signed ID/H/dimension/creator and permanent original/nonce/message claims; encoding never changes H. Draft retries do not bypass a finalized original claim. |
| Cross-network/genesis | V4 directly signs N/G/policy/F; imported history must match pinned G2. Existing rights still bind N rather than G directly: retain prohibition on N reuse across roots. |
| Equivocation | Disclosed signed conflicting choices give objective grouped proof; hidden conflicts remain undetectable. No receipt-time first choice or retrospective certificate revocation. |
| Duplicate cohort retry | No persistent cohort/claim before finality under A, so repeated drafts consume no global quota. They can seek favorable subsets; this is an integrity cost, not cryptographic prevention. Finalized replay rejected. |
| Penalty suppression | Included valid proof mandatorily changes future state. Optional proof inclusion can be censored, and pending-target offenses may never acquire canonical target context. No global evidence delivery guarantee. |
| Quota bypass | Finalized participation cannot be doubled or reset; unminted work is deliberately outside quota. Existing 5/25 values do not throttle it. Local throttles do not alter peer validity. |
| Valid-media censorship | Reviewers/producers can withhold; Tendermint can converge only on available valid proposals under its assumptions. No content-inclusion guarantee follows from BFT safety. |
| Manipulated all-unsure | d=0 always unresolved; adding a genuine positive changes d and can pass under preserved threshold. Selecting that signer is allowed by A; no invented unsure-discount rule. |
| Divergent node eligibility | Same verified G2, full prefix and exact candidate yield same status/tally/claims; node-local off-chain facts cannot enter. Production independent replay remains unimplemented. |
| Missing history/evidence | Stop at last complete verified prefix; hash/root/eligible flag cannot replace bytes. Eclipse may hide a newer prefix; G alone cannot prove freshness. |
| Unavailable decoder | Local verification failure; do not prevote positive or assert invalid bytes solely from worker outage. Original bytes/safety still must verify. |
| Admission-dependent stall | Strict media epochs and prospective penalties can halt restoration. Accept explicitly or separately approve CONTROL/history/clock redesign. |

Cryptography supplies attribution, immutable binding, replay detection and
finality evidence under the specified validator fault/custody assumptions.
Initial reviewer independence, honest judgments, evidence relay and availability
rely on the permissioned network. Grant changes, subjective disputes, appeals,
Sybil control, censorship remedies and stalled-chain recovery remain governance
decisions; no new acceptance authority is invented.

## 11. Capacity, resources and three-year growth

Retain 3,145,728 bytes for complete canonical media R; encoded image payload
2,097,152 gives base64 **2,796,204** bytes. Selected signed records remain <=16
per dimension /32 total, <=4,096 each and <=196,608 whole certificate. No roster,
global inventory list or preliminary original-media duplication under A.

Reuse B's conservative C3 bound **173,418**, which retains 32 full vote caps,
technical/rights/tallies and all seven new members (517 bytes). B's analytic
mandatory MEDIA bound **3,059,651** is an estimate for its draft grammar, **not**
proof of the final combined format. The required consensus_context object adds
**230** serialized bytes including its comma/key, giving **3,059,881** under the
same width assumptions. A removes control/preliminary paths, not mandatory media
limits. The final schema must enumerate every member and recheck child/depth caps.

Recommend explicit observation array `X<=65,536` J bytes (rather than B's 262,144
media extras), <=32 explicit observations, each <=8,192 including wrapper; raw
signed_vote<=4,096. All 32 entries cannot be maximal simultaneously; joint array
and whole limits govern. Selected records remain only in C3. Combined implicit
REGISTER + up to32 selected VOTEs + ISSUE +32 extras gives <=66 logical events,
within B's 256 ceiling. No second REGISTER or ISSUE source can appear explicitly.

With B's empty array already included, substituting X at 65,536 adds 65,534:
analytic total **3,125,415**, margin **20,313** under 3 MiB. This includes B's
maximal caption/native assumptions plus consensus_context, but is still a
conservative grammar-width calculation, not a jointly realizable signed block or
measured capacity result. The final component check must reserve enough Rest for
context/history keys, and require C<=196,608, native<=98,304, X<=65,536,
Rest<=32,768 and complete R<=3,145,728 **simultaneously**. Component caps alone
allow `2,796,204+196,608+98,304+65,536+32,768=3,189,420`, which exceeds the cap
by **43,692**; they are not additive permissions. Measure actual bytes before
freeze. If full optional observations/native transfers do not fit, defer optional
extras or rebuild the draft; never remove a counted negative vote at validation.
There is no mandatory-evidence conflict established by these bounds for a 2 MiB
payload. A future larger manifest/mandatory history needs a new exact fit proof;
bounded alternatives are fewer optional extras/transfers or a separately approved
smaller cohort ceiling >=5, **not** silently smaller media or a raised block cap.

Illustration only: 1,000 finalized media/day *365*3 =1,095,000 media. At full caps,
per-node canonical R is **3,444,572,160,000 bytes**; certificate component allowance
**215,285,760,000**, optional array allowance **71,761,920,000** (already inside R,
not added again); one 16,384-byte Q4 per media adds **17,940,480,000** bytes outside
R. Failed drafts have no mandatory consensus archive; local retention is separate.
Indexes, reconstructed-original caches, extra compatible proofs, backups, retries
and transport add costs. These are arithmetic bounds/scenarios, not throughput,
average storage, price, compression savings or measured three-year growth.

Per candidate/replay there are 10..32 selected secp256k1 recoveries, one creator
rights verification, up to32 optional source recoveries (<=65 application signature
checks before caching), native signatures and Q4's additional 4..5 recoveries.
Media decode/safety still dominates some workloads; no new CPU timing is claimed.
Use bounded source bytes, depth, count, concurrency and exact-context caching;
history replay should be linear in retained sources with derived indexes, not a
fresh full-prefix rescan for every vote. Independent resource measurements remain
an activation gate. No fee, reward, bounty, codec or economics change is approved.

## 12. Minimal versioned schema and commitment amendment

No existing schema file/module changes in this task. Reuse **unimplemented**
prelaunch block4/C3/V4, Review3/Reviewer2/Reputation3/History1/Issuance1 slots;
do not create block5/vote5 merely to distinguish two unapproved draft policies.
Require one exact approved profile/digest at launch; never two block4 meanings.
Protocol2 and technical/rights/encoding/native versions stay as previously
specified. If the prelaunch premise fails, stop for a real activation/version plan.

| Surface | Exact proposed impact relative to implemented isolated code |
| --- | --- |
| G2 / policy registry | Keep M's outer envelope and ten-entry registry. Freeze full closed policy source bodies with A's selected-only authority, no-control rule and source bounds. Replace B HP's old `finality_policy_digest` member with **no such member**, using genesis-bound agreement descriptor as sole agreement authority (L option b). Do not put A/PD/G or descendant hashes in their own policy source preimages. No eleventh FP policy. |
| Review/reviewer/reputation/issuance | Existing sources lack approved selection/history authority. Review3: 5..16 included, no global earliest/inventory; all-unsure unresolved. Reviewer2: bootstrap from B0 and finalized selected-only participation. Reputation3: closed objective source scope/prospective penalties. Issuance1: only atomic media+ISSUE finalization owns claims. Approve source bytes/digests together. |
| Vote V4 | Reuse B's 19-key flat payload: old isolated15 plus `genesis_hash,reference_finalized_height,reference_finalized_block_hash,creator_wallet`; domain `zoidbergchain/community-review/v4`, vote_version4, review3/reviewer2/reputation3. Selected record is old23 plus G/creator=25 fields. Status/reference metadata must match signed context and replayed F. No cohort ID or invitation/lottery fields. |
| C3 | Reuse old18 plus B's seven `genesis_hash,history_parent_height,history_parent_hash,history_parent_commitment,history_policy_version,history_policy_digest,selection_input_digest`=25 keys. Whole list is chosen cohort; input digest commits disclosed raw pool, **not** complete offers or earliest selection. No new certificate signer. |
| Media block4 | Old MEDIA fields plus required `block_kind="media"`, `reviewer_history` and `consensus_context` from I/G; reconcile one closed combined payload/hash preimage. C3 replaces C2. No history block grammar. Current consensus round/proposer/Q4 remain outside B. |
| History object | Retain B's exact five keys `history_version,history_policy_digest,parent_commitment,post_commitment,events`. Explicit array contains only optional VOTE observations; implicit REGISTER/current selected VOTEs/ISSUE extracted once from this admitted media/C3. Events never have an unsigned accepted/eligible/penalty field. |
| History policy HP | Exact keys `history_policy_version,rule_set,review_policy_digest,reviewer_policy_digest,reputation_rule_digest,state_commitment_version,limits`; version1/state1, rule_set=`zoidbergchain/reviewer-history/7.17n-finalized-cohort`. Limits explicitly fix whole3MiB, selected32/dimension16, vote4096/message2048/event8192/cert196608, explicit count32/array65536, logical count66, native10/array98304/record8192, rest32768, depth32. Other technical/bootstrap limits come from their registered closed source schemas. No CONTROL or unminted acceptance parameters. Final closed source serialization/vectors remain a separate freeze gate. |
| Bootstrap | Keep G2 B0 shape/clean history/defaults; no new people/launch values/import. Compute J0 after G; current M envelope result cannot authorize new semantic sources. |
| Replay/journal | Keep B's incident/replay and J0/Jh preimage families with changed approved HP digest. Replace laboratory local permanent issuance with finalized source ownership. No sparse state tree, extra checkpoint signer or new journal chain. |

Define J/S/D as the existing strict compact sorted-key UTF-8 canonical JSON,
lowercase SHA-256 hex and `D(x)=S(J(x))`. No normalization, floats, bool-as-int,
duplicate keys or local timestamps; retain native aggregate's distinct ASCII
serializer. V4 personal-sign uses EIP-191 byte length and Keccak, **not** SHA-256.

Retain B's closed event `{event_id,body}`, body exactly
`domain,event_version,network_id,genesis_hash,parent_height,parent_hash,kind,payload`;
domain `zoidbergchain/reviewer-event/v1`, event_version1, inclusion parent=F,
event_id=D(body). VOTE payload=`{signed_vote:{payload:V4,signature_scheme,signature}}`.
Implicit REGISTER/ISSUE retain B's payload definitions, only for this media;
raw selected signatures derive implicit VOTE bodies. Explicit/implicit exact
duplicates reject. Sort combined logical events by `(REGISTER=0,VOTE=1,ISSUE=2,
event_id)` to derive source locators and journal event order; phases in section 8
determine transitions, so an unselected low-ID observation never displaces a seat.

`selection_input_digest` retains B's exact preimage: domain
`zoidbergchain/reviewer-selection-input/v1`, N/G, parent height/hash, submission/H,
and `vote_event_ids` containing ascending IDs of **all current selected implicit
and optional explicit VOTE events**. It authenticates disclosed membership; it is
not a roster, quorum certificate, freeze authority or proof of non-omission.
C3 digest remains D(C3 without certificate_digest).

Retain B's formulas:

```text
J0 = D({domain:"zoidbergchain/reviewer-journal-genesis/v1",protocol_version:2,
        network_id:N,genesis_hash:G,history_policy_digest:HP,bootstrap_digest:BD})
delta_h = {block_timestamp:P.timestamp,events:[logical event IDs in rank/id order],
           native_transactions_hash:P.transactions_hash,
           settlement:{submission_id,content_hash,creator_wallet,certificate_digest}}
DD_h = D(delta_h)
Jh = D({domain:"zoidbergchain/reviewer-journal/v1",protocol_version:2,
        network_id:N,genesis_hash:G,history_policy_digest:HP,bootstrap_digest:BD,
        height:h,parent_hash:F.hash,previous_commitment:J_(h-1),delta_digest:DD_h})
```

Settlement is never null in an accepted post-genesis A block. Journal commitment
is an authenticated replay checksum, not a state-membership or succinct snapshot
proof; it cannot establish correctness without replay. Block envelope hashing
retains the existing block/v2 family with the exact approved P4 payload. Q4 follows
its resulting hash. No circular certificate/event/journal/block/finality dependency.

## 13. Worked adversarial cases

Unless stated otherwise use one F, valid noncreator signatures, >=1 established
per dimension and valid media/rights/ledger. Tuples are `(p,n,u)` per dimension.

| Case | Result and independently checkable reason |
| --- | --- |
| 1. Legitimate mixed review | Originality (5,2,1), admissibility (4,1,0): quorums, d=7/5; 5/7 and 4/5 pass. Unsure counted once in participation, outside d. |
| 2. Both pass | Same five Wallets in both, (4,1,0) each: ten signatures, five participation records, one media reward/ISSUE, both ratios 4/5 for these matching results. |
| 3. One fails quorum | Originality (4,0,0), admissibility (5,0,0): originality incomplete; no certificate, finalization or claims. |
| 4. Missing established | Five probationary positives in either dimension: incomplete, despite 100% decisive approval. Current activity cannot promote its own established seat. |
| 5. Zero decisive | (0,0,5) in one dimension: d=0 unresolved; never approval or p/0. Other dimension's approval cannot substitute. |
| 6. Both all unsure | (0,0,5) each: no admission, no rejection certificate, no lasting quota. Later eligible decisive signatures may form a new unfinalized A set; no signed choice is overwritten. |
| 7. Split choices | (2,2,1) fails 70%; (7,3,0) passes exactly. Neither all-unsure nor a tie adds a new threshold. |
| 8. Late vote | Negative offer arrives after B proposed: B unchanged. Rebuild unfinalized B if desired; after B finalizes it cannot acquire a new seat or participation. Optional later misconduct proof remains possible. |
| 9. Omitted negative | Producer has five positives and five negatives, includes only positives: **valid under A**, assuming both dimensions pass. Including an unselected negative observation also does not force its tally inclusion. This is the explicit selection-risk counterexample, not a fairness guarantee. |
| 10. Conflicting signatures | Same Wallet/target/dimension signs positive and negative: both counted => invalid duplicate. One counted plus one retained observation => one prospective equivocation incident; hidden second signature cannot be detected. |
| 11. Parent advances | C3/V4 pin k; another media finalizes k+1: old draft stale, regenerate C3 and collect new V4 references/nonces at k+1. No old unminted participation credit or permanent issuance. |
| 12. Competing media | Bx and By at k+1 share a signer or original H: both can be retained provisionally; only winner's claims/participation finalize. Losing same-H attempt cannot reissue at the new parent. |
| 13. Source-only restart | G2+every R+Q4+supported sources reproduce grants, activity, selected participation, observations/incidents, J and claims. Empty DB labels/cache are irrelevant; missing a needed R or proof stops replay. |
| 14. Provisional reorg | Drop Bx scratch quota/claims; select/finalize By against the same F. Never detach F or let Bx's local issuer reservation constrain By. |
| 15. Quota and penalty | Same reviewer signs both dimensions: one `(wallet,submission,F//5)` receipt. Equivocation first proven in h adds incident after finality, interval start h//5, constraining h's children; old acceptance immutable. At epoch boundary restore expired underlying status by query. |
| 16. Wrong network | Foreign N or G or same N/different G in V4 fails exact signed context; rehashing a foreign certificate does not repair signatures or its independent genesis pin. |

All examples are specification outcomes, not executed full-profile interoperability
tests. A counterexample that is valid under A cannot be reclassified as invalid by
a validator's local knowledge of omitted votes.

## 14. Byte examples and independent verification plan

The following are **commitment-only oracles** using existing public fixture context:
N=`zoidberg-signing-vector-v2`, G=`a` repeated64, HP=`c` repeated64 (symbolic,
not this new source's computed digest), BD=`54c806886d13f1bea28d8c33457d1b4f0ae60dccffe146386aa2fa860caf37c0`.
BD is the old empty-bootstrap fixture, deliberately insufficient for admission.
Event IDs `1`/`2`/`3` repeated64 and certificate `e` repeated64 are synthetic
placeholders, not real signed events. These vectors cannot authenticate genesis,
create a valid cohort or show a fully valid media block. Exact preimages have no
BOM, whitespace or trailing newline.

Literal selection-input preimage (563 UTF-8 bytes):

```json
{"content_hash":"ca978112ca1bbdcafac231b39a23dc4da786eff8147c4e72b9807785afee48bb","domain":"zoidbergchain/reviewer-selection-input/v1","genesis_hash":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","network_id":"zoidberg-signing-vector-v2","parent_hash":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","parent_height":0,"submission_id":"dddddddddddddddddddddddddddddddd","vote_event_ids":["1111111111111111111111111111111111111111111111111111111111111111","2222222222222222222222222222222222222222222222222222222222222222"]}
```

SHA-256=`2c9462f29884391ee1f79bac0c774c707b21e0013970edcec6969d6447cf1cc6`.
Literal media delta (636 bytes):

```json
{"block_timestamp":"1792368000","events":["1111111111111111111111111111111111111111111111111111111111111111","2222222222222222222222222222222222222222222222222222222222222222","3333333333333333333333333333333333333333333333333333333333333333"],"native_transactions_hash":"4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945","settlement":{"certificate_digest":"eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee","content_hash":"ca978112ca1bbdcafac231b39a23dc4da786eff8147c4e72b9807785afee48bb","creator_wallet":"0x19e7e376e7c213b7e7e7e46cc70a5dd086daff2a","submission_id":"dddddddddddddddddddddddddddddddd"}}
```

DD1=`7983eee130dcfa3f7a52f391a340c709d4a3994c76f80eeee7efc66868956d4d`.
J0 with the exact section12 preimage/parameters is 376 bytes and
`5a277480a466018d68b952d834e6f554c3a77c6273e7be8dd11983129aca507c`.
J1 preimage uses domain reviewer-journal/v1, same N/G/HP/BD, height1,
parent_hash=G, previous_commitment=that J0 and delta_digest=DD1; 631 bytes,
J1=`d77074b9e7bba2588bd43bf2ea9a4709af4a09eab77efaf04b049ba22e7bf2e3`.
Member order follows J, not prose order. Altering selected input membership,
event order, timestamp, settlement, parent or N/G changes bound bytes. The B
unsigned V4 example remains its 19-key/898-byte primitive; no old signature is
claimed valid on amended V4. No new signing identity/signature is created here.

Future independent verifier acceptance plan, after owner decisions/source freeze:

1. Independently pin/validate full G2 semantics and all ten sources; initialize
   clean grants/claims/clock; reject a peer-chosen trust pin or unsupported policy.
2. Obtain contiguous canonical R and external Q4; require full bytes, exact hashes,
   immediate parent proof and static authority. Reconstruct/safety-check original,
   rights/technical/native/reward and existing replay constraints.
3. Recover selected V4 signers, exact context and 25-field metadata; query S_F for
   eligibility/established/quota; require full chosen C3 membership and recompute
   both tallies/fractions. No local offered pool or acceptance flag enters.
4. Extract implicit sources and bounded observations once; check event IDs/order,
   duplicates, selection_input_digest, prospective incident schedules and claims;
   recompute J0/Jh and all C3/block hashes before validating full Q4 authority.
5. Persist sources, finality cursor and transitions atomically; compare two
   independently implemented replay engines across different insertion orders,
   restart, discarded siblings, delayed proofs and absent decoders. Verify all
   sixteen cases above, one-positive/four-unsure, signature variants, rate
   unreachability, exact epoch/penalty boundaries and source-unavailability classes.
6. Add independent full-policy/full-media positive and negative vectors, canonical
   parsing/byte/depth/cap boundaries, fault/crash/concurrency checks and target-host
   CPU/replay measurements. Check EIP-191 Keccak/recovery independently. A shared
   implementation generating its own expected hashes is insufficient.

## 15. Owner decisions and current gates

| Category / decision | Preferred concrete choice | Approval/evidence still needed |
| --- | --- | --- |
| Established rules | Two independent five/one-established quorums, equal weights, 70% decisive, unsure semantics, self exclusion, exact fractions, original SHA, full media and 3MiB cap | Preserve; no new positive threshold or media-limit authority requested |
| Evidence authority | A, exact bounded included signed set, no global offered inventory | **Owner approve selection/censorship trust**, including valid-positive-subset counterexample. If rejected, choose B and fund its prior roster/complete-response/retry authority; do not drift into C. |
| Cohort lifecycle | 5..16 each, no first-arrival order/lottery; pending drafts have no global lock/expiration; retries cannot rewrite a signed choice | **Owner approve** abandoning B's earliest-sixteen and any permanent off-chain negative-cohort veto |
| Undecided/rejection | d=0 unresolved; negative blocks admission; no new rejection certificate or failed-attempt consensus quota | Mostly preserved tally; **approve lifecycle** of failed/unminted reviews and explicit one-positive/four-unsure consequence |
| Participation/quotas | Only finalized selected votes; paired dimensions count once; no unminted promotion/issuance reservations | **Owner approve material semantics narrowing and largely inactive 5/25 caps / unreachable canonical rate abuse**. Preserving old unminted work credit needs additional authenticated history. |
| Historical/offense authority | Exact parent S_F, signed reference, canonical target, bounded observations, prospective incident inclusion | **Owner approve** limited offense coverage, censorship and no local blacklist/challenge/daily-policy authority |
| Finalized-parent timeline | Fresh unaccepted signatures after parent advancement; one media+ISSUE atomic; provisional branch claims reversible | **Owner approve** lifecycle; finality implementation/refinement and full independent replay still missing |
| No-media recovery | Strict media-only, accept halt if eligibility/finality insufficient | **Owner approve liveness limitation**; CONTROL/pacing/clock/governance is a separate alternative, not implicitly authorized |
| Schema/policy freeze | One combined block4/C3/V4 profile; HP removes FP reference and uses G2 agreement authority; existing draft commitment families | Approve exact closed source bodies/limits and new full vectors before implementation; current M envelope verifier must remain incomplete meanwhile |
| Launch/resource authority | Clean B0 and existing static validator profile; no real values chosen | Actual reviewers/operators/allocations, independence/custody, native reward ordering/time policy, registry fit, full byte/depth/CPU/availability review and activation all remain separate gates |

**Reviewer-policy portion of Task 7.17 is not unblocked by this document alone.**
It can be unblocked as a specification dependency only after the owner accepts
the preferred rows (or explicitly chooses fully specified B instead) and the
combined source/schema profile is frozen with independent vectors. Full journal
implementation also depends on finality/authority integration, source-only replay,
durability/recovery, complete native/time rules and a separately authorized task.
No implicit acceptance authority, approval or production readiness follows from
successful documentation verification.

## 16. Executed verification and delivery status

All completed focused checks passed, using the existing Windows project `.venv`:

| Completed selection | Result |
| --- | --- |
| Task 7.17M G2, Milestone 6 dual review, earned eligibility and reviewer reputation, excluding the two API cases below | **225 passed, 2 deselected**, 5.56 seconds |
| Task 7.14 issuance and Task 7.15 authenticated-history suites | **137 passed**, 47.60 seconds |
| Independent Python/Node byte/hash construction | Four exact J0/selection/delta/J1 preimages agree byte-for-byte, including lengths/SHA-256; changed-input hashes differ; .NET independently checked the four lengths/hashes |
| Independent Node arithmetic checks | Seven C3 members=517 bytes; consensus_context=230; bounded extra array total=3,125,415; component-cap excess=43,692; 100 reference positions verify the finalized-only quota bound; decisive boundary cases agree |

There are **362 distinct final test passes**, no final failures/errors/skips, and
two deliberately unverified API cases: `test_peer_rate_offense_is_independently_verified_and_duplicate_is_idempotent`
and `test_read_only_reputation_api_exposes_effective_state_and_history`. An initial
broader run and a narrower diagnostic run stalled in the API-bearing selection
and were interrupted without final summaries; their partial output is **not**
added to the passing totals. The completed final selection explicitly excludes
both API cases. No HTTP/worker assertion or source code was changed to make a test
pass. The API behavior and cause of the stall were not resolved in this
documentation-only task. Issuance/history suites, including their existing isolated
worker paths, completed successfully.

Disposable logs/JUnit are `temp/task717n-policy-final-verification.log`,
`temp/task717n-policy-final-results.xml`, `temp/task717n-history-verification.log`
and `temp/task717n-history-results.xml`; byte/arithmetic checks are under ignored
`temp/task717n*`. They are verification scratch, not additional deliverables or a
new accepted fixture/profile. Existing tests remain unchanged. Final checks cover
UTF-8/no BOM, final newline/whitespace, balanced fences, relative-link targets,
literal JSON byte/hash reproduction, unstaged-only scope and unchanged protected
source/schema/test paths. No full-repository, cross-platform, full-profile
interoperability, production G2, performance or liveness verification is claimed.

Branch/HEAD remain as section 1. The final worktree has exactly the new decision
and the 7.17B current-gate/link note; index remains clean. **Task 7.17N is ready
for review and a later authorized commit**, with no commit made here. Owner
approvals and combined-policy/schema/verification prerequisites in section 15
keep reviewer-history Task 7.17 **BLOCKED**. No journal or Task 7.17O was begun.
