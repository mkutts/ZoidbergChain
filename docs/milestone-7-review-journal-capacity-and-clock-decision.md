# Milestone 7 Task 7.17Q — Review journal capacity, clock and node economics

**Task 7.17R specification follow-up (2026-10-27):** The
[test-only wire and closure contract](milestone-7-review-journal-wire-and-closure-contract.md)
adds closed laboratory binary schemas, an explicit authenticated-time assumption,
logical cutoff before bounded mandatory CLOSE pages, deterministic work/byte
budgets, cross-history verification rules and independently checked structural
vectors. The isolated byte/closure experiment is reviewable; full cryptographic
prototype, production journal, public testnet and reviewer-history Task 7.17 stay
**BLOCKED** on the named policy, clock-trust, source-verifier, G2/media, signing,
agreement, availability and operating approvals/measurements. Q's JSON sizes and
historical findings below remain unchanged; no recommendation is activated.

Date: 2026-10-27, America/New_York. **Focused verification and architecture
recommendations only. Every new parameter below is unapproved.**

The 24-vote limit is an arbitrary conservative application-model cap, not a
derived 256 KiB wire or cryptographic limit. P's archive arithmetic is correct
under its assumptions, but continuous nearly empty ticks dominate its low-load
estimate. Recommend a separately finalized BFT journal, byte and deterministic
work budgets, mandatory close-first transitions, and bounded hybrid advancement
with authenticated time/epoch events. These recommendations require owner
approval and complete schemas before production work. A height cutoff alone
cannot promise human review time. No production throughput has been measured.

## 1. Prerequisites, sources and authority

Before edits: branch `Compression-State-Bloat-and-Node-Economics`, HEAD
`e15c71e0e31afd3cb9a3bb50bc114bcac5922c62`. Index, worktree and untracked files
were completely clean. P is separately committed: `d2f4abd` contains its isolated
model/calculator/evidence and `e15c71e` its report/fixtures/tests. No ancestor or
repository `AGENTS.md` was found, including a hidden-file search. No delegation.

Read/inspected the [O decision](milestone-7-network-wide-review-voting-protocol-decision.md),
[P model/report](milestone-7-network-wide-review-journal-feasibility.md),
[N historical admission decision](milestone-7-reviewer-admission-policy-decision.md),
[I wire/signer contract](milestone-7-bft-wire-and-signer-contract.md),
[G agreement decision](milestone-7-distributed-finality-protocol-decision.md),
[L G2 contract](milestone-7-g2-genesis-and-bootstrap-contract.md),
[7.7 measurements](milestone-7-block-composition.md),
[7.8 economics](milestone-7-node-economics.md), and
[7.9 block/storage budgets](milestone-7-v3-storage-and-capacity-decision.md).
P's model, independent oracle, checker, retained fixtures, calculator and validation
record were inspected. Historical N selected-cohort semantics are superseded by O.

Owner-directed requirements remain: all eligible authoritatively admitted
pre-cutoff votes count; nodes verify/store/broadcast; committed negatives cannot
be omitted; originality and admissibility are separate; one accepted original
per media block and the 3,145,728-byte media-block cap remain. An offered vote or
custody receipt is not authoritative admission. No producer-chosen cohort returns.

Only this report, isolated `verification/review717q/`, its one test module, and a
link/readiness notice in P change. No active schema, production imports, network,
signer, keys, genesis, history integration, store, migration, reset or deployment.
No staging, commit, push, merge or Task 7.17R.

## 2. Where 24 comes from

`verification/review717p/model.py:apply` independently checks VOTE count <=24,
OPEN <=16 and ANCHOR <=1. It does **not** serialize/enforce a 256 KiB batch.
`workload.calculate` separately computes
`floor((262144-33792)/(event_bytes+1))`, then takes `min(24, byte_slots)`.
The 33,792 allowance is 1,024 header +16*2,048 close reservations; the proof is
external. There is no derivation of 24 from CPU, signatures, Merkle paths,
certificate size, independent benchmarks or protocol worst cases.

| Factor | What actually supplies the limit |
| --- | --- |
| A. Signed vote bytes | Sample 1,701, payload 1,507; no 24 relation |
| B. Event overhead | Sample wrapper 42; P adds one comma byte per vote |
| C. Batch header | Assumed 1,024 reserved/stored, no frozen batch header |
| D. Merkle/proofs | Model hashes entire diagnostic objects; no Merkle inclusion-path encoding or per-vote proof cost implemented |
| E. Commit certificate | Symbolic proof in reducer; 4,096 mean/16,384 cap planning, separate from body |
| F. Verification CPU | No measured signature/validation time; no work derivation of 24 |
| G. Count cap | Explicit experiment/safety assumption; primary source of 24 |
| H. Competing events | OPEN, CLOSE, ANCHOR, STATUS, PENALTY/evidence; they consume bytes and work, not a reason 24 is necessary |

P sample ledger: `24*(1507+132+62+42+1)=41,856`; header 1,024;
maximum close reservation 32,768. Accounted/reserved body **75,648**, leaving
**186,496 bytes**. An assumed external 4,096 certificate makes 79,744 accounted
bytes; unused reservation is not actual stored event data. These are exact
arithmetic allowances, **not serialization of an existing valid journal batch**.
P's 130 byte slots follow `228352//1744=130`; an 8,192-byte event gives 27.

## 3. Byte-accurate samples and conditional maximum

[capacity.py](../verification/review717q/capacity.py) recreates P's sample and
independently restricts O's closed 25-field payload using I's primitives. Key and
signature strings are structural placeholders, not cryptographic vectors.

| Serialized component | P sample | Conditional O/I maximum |
| --- | ---: | ---: |
| Payload | 1,507 | 1,545 |
| Signature hex characters, including `0x` | 132 | 132 |
| Remaining signed-wrapper bytes | 62 | 62 |
| Complete signed vote | **1,701** | **1,739** |
| VOTE event wrapper | 42 | 42 |
| Complete VOTE event | 1,743 | 1,781 |
| Q diagnostic length frame | 4 | 4 |
| Framed event | **1,747** | **1,785** |
| Byte slots after 33,792 reserve | **130** | **127** |
| Body with 24 votes, no closes | 42,952 | 43,864 |
| Body with 16 maximum close frames and full byte lane | 260,902 | 260,487 |
| Unused bytes in that last body | 1,242 | 1,657 |

The 38-byte increase is exactly network ID length 26 ->64; all three height
fields already occupy 16 digits in the sample. Heights use U=9,007,199,254,740,991;
other hashes/IDs/wallets/nonce/key are fixed-width ASCII; longest legal dimension
and choice are the sample's admissibility/negative. Versions/domains and sequence
are literals. No escaped or arbitrary Unicode field is permitted by that draft.
Real finite key/low-S signature validity can reduce the accepted set, never enlarge
these fixed string widths. This is a **conditional structural upper bound of
O/I's proposed closed grammar**, not proof that an approved production vote exists.
O's looser 2,048 payload/4,096 signed caps remain unapproved outer ceilings.
They need not be jointly reachable in the closed grammar; outer-allowance
sensitivity rows are accounting ceilings, not legal maximum-shaped votes.
EIP-191 signing preimages are 1,537/1,575 bytes for these payloads; those transient
signing inputs are not another archived copy of the vote.

Q's diagnostic container actually serializes an 80-byte header: magic4 +height8
+parent32 +count4 +ordered digest32; 944 zero reservation bytes make 1,024.
Each event is canonical ASCII JSON preceded by uint32 length. The root covers
all ordered frames; it is **not a Merkle tree**. No per-event Merkle proof is
stored. A proposed production tree must count root/header and optional separately
retained paths once, with an explicit path and hash algorithm bound.

External certificate allowance: proposer +3 precommit signatures =4*132=528 text
bytes (260 decoded bytes). At 4,096, other certificate/envelope/context bytes
are 3,568; at 16,384 they are 15,856. They are not added again as user signatures.
The Q authenticated-clock scenario additionally reserves **1,024 external bytes
per height**, including three 132-byte timestamp signatures and 628 other bytes.
These certificate allowances are estimates, not measured new-stream encodings.
Transport ceiling in this scenario is body262144 +commit16384 +clock1024 =279552,
before frame/proposal/round evidence. Full pre-vote certificate/round traffic is
separate; hostile indefinite rounds have no finite lifetime storage bound.

Unresolved maxima are specific: new journal header/stream signing envelopes;
OPEN eligibility/source inventory and target/rights/technical references;
EVIDENCE proof arrays; STATUS/PENALTY/ANCHOR source payloads; complete CLOSE
commitments/count widths; clock attestations/START/deadline fields; checkpoint
and object-manifest pages. These bodies lack a frozen full grammar. The existing
O vote itself has no undefined string maximum **if** its explicit I imports and
closed shape are adopted. A time cutoff changes its signed `session_close_height`
binding, so a successor vote profile must be specified and remeasured; 1,739
cannot be transplanted to that profile. Worst-event calculations use a proposed
8,192-byte event allowance: `228352//8196=27`. A 4,096 signed vote with exactly
the 42-byte wrapper gives `228352//4142=55`, conditional on that wrapper staying
closed. None of these quotients is a safe production capacity.

## 4. Batching alternatives and adversarial cases

Recommend **bytes + deterministic verification-work tokens** for isolated testing.
Use 262,144 body, 8,192/event, 4,096/signed vote, <=96 vote checks and <=64
control signature checks/batch as **test inputs**. Reserve 16*2,048 framed bytes
for closes plus header; close reservation includes framing. Up to four commit
and three time signatures are additional checks. A deterministic operation budget
must eventually cover hashing, source paging, eligibility lookup, depth and
evidence reconstruction; counting signatures alone does not bound all validation.
No CPU milliseconds or local timeout becomes a consensus-validity predicate.

| Test/concern | Fixed 24 | Byte bounded | Bytes + work (recommended test) |
| --- | --- | --- | --- |
| Exact 256 KiB boundary | Count alone fails for large/control payloads; still needs bytes | Exact <= test, +1 rejects | Same plus work |
| Near-boundary/max encodings | Does not prove vote/event bounds | Enforce every closed field and raw/depth limit before allocation/crypto | Same |
| Mixed OPEN/VOTE/CLOSE/EPOCH | Cannot ignore other events | All frames counted; close lane reserved | Same; count control signatures too |
| Large signatures/identifiers | 24 oversized messages remain unsafe | Wrong widths/unknown extensions reject | Same cheap preflight |
| Simultaneous closes | 24 is unrelated to close capacity | Due closes mandatory first; reserve at OPEN | Same; global post-partition due set needs paging gate below |
| Byzantine malformed flood | Does not bound ingress | Frame/depth/peer queues bounded; invalid garbage need not be archived | Separate bounded ingress verification lane; do not spend all capacity on invalid signatures |
| Ordering/producer choice | Pre-admission ordering still affects quota conflicts | Same | Same; no choice-based filtering permitted |
| Validation time | Unmeasured | Bytes do not bound signature/evidence work | Deterministic cost tokens; operational timeout abstains, never votes success |
| Evidence before agreement | Count does not establish custody | Full checked dependencies persisted before honest value vote | Same; missing data rejects/incomplete, no root-only success |

The diagnostic mixed batch with 16 maximum closes, 96 maximum O/I votes, one
2,048-byte OPEN frame and one 512-byte EPOCH frame is **207,712 bytes**. The
byte-only sample lane allows 130 votes but the recommended test work ceiling
admits 96. Unknown control schemas are opaque bounded test payloads, not validated
production sources. A proposer may omit **unadmitted** offered votes; BFT alone
does not ensure client fairness. Once admitted, full prefix replay counts every
eligible negative/unsure vote. Competing final quota slots follow agreed event
order. Mandatory ordering covers closes/epoch effects; optional total order is
consensus chosen, not inferred from local arrival.

## 5. Independent reconciliation of P storage

[workload.py](../verification/review717q/workload.py) reconstructs these results
without calling P's calculator; tests compare the independent sums to retained P.
Units here are decimal GB; 1 year=365 days, three years=1,095 days. Dimension
messages are votes: a person signing both dimensions generates two messages.

| Votes/min | Votes/day | Signed bytes/day | Frame+event bytes/day (P's comma allowance) | Fixed header+proof/day | Annual total | Three-year total |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 10 | 14,400 | 24,494,400 | 619,200 | 88,473,600 | 41,459,328,000 | **124,377,984,000** |
| 100 | 144,000 | 244,944,000 | 6,192,000 | 88,473,600 | 123,957,504,000 | **371,872,512,000** |
| 1,000 | 1,440,000 | 2,449,440,000 | 61,920,000 | 88,473,600 | 948,939,264,000 | **2,846,817,792,000** |
| 10,000 | 14,400,000 | 24,494,400,000 | 619,200,000 | 88,473,600 | 9,198,756,864,000 | **27,596,270,592,000** |

Last two rows are offered storage demand, infeasible under P's 288/min profile.
Exact annual/per-component values are in `p_reproduced` in the retained JSON.
At 10/min, the exact three-year sum is:

```
payload 14,400*1,507*1,095                         23,762,376,000
user signature text 14,400*132*1,095                2,081,376,000
other signed wrapper 14,400*62*1,095                  977,616,000
event wrapper+comma 14,400*43*1,095                   678,024,000
headers 17,280*1,024*1,095                        19,375,718,400
commit certificates 17,280*4,096*1,095              77,502,873,600
TOTAL                                           124,377,984,000
```

Fixed ticks contribute **96,878,592,000 bytes, 77.89%** of that result. The
1,024+4,096 allowances cost the same for empty/nearly empty batches. At 10/min,
about 0.833 votes arrive per five-second tick. At 100/min, fixed costs are 26.05%.
P adds zero OPEN/CLOSE, idle event bodies, index, backup or database amplification;
zero means **excluded**, not free in production. P stores one complete signed
vote inside its event, not a second full payload copy. Its 194 wrapper bytes
include the signature; counting both again would overstate size. Reservations
are not padded storage. Current media JSON/base64 physical duplicates from 7.7
are unrelated to this hypothetical journal representation.

Per-node logical bytes are one full archive copy. Four validators mean factor4
network storage, not factor4 inside every node. Recommend those four full archives
plus two independently operated archives (six service copies), subject to owner
approval. Backups are **additional**: four full copies at assumed 0.95 compression
give factor3.8 on physical primary; network serving replicas are not backups.
Launch should demonstrate at least two independent online full-evidence sources,
repair after a source loss, and a fresh source-only recovery. A q3/f1 certificate
implies at least two honest custodians only at signing under store-before-vote;
it cannot promise two remain online years later. Serving/retention obligations
and failure response require explicit operational authority and tests.

## 6. Q corrected scenarios, backups and economics

Q adds four-byte frames, estimated indexes96/event +64/height, OPEN/CLOSE
2,048 framed bytes each per **100 signed dimension votes/session**, a 512-byte
epoch event per 300 seconds, and 1,024 clock-proof bytes/height. All are estimates.
OPEN originals, technical/rights evidence, anchors, penalty/status histories,
misconduct sources, private signer WAL/round logs, transport retries and repair
remain **additional unbounded-by-this-workload demands**. Every retained vote is
needed for replay, regardless of media outcome. No eligibility/tally pruning.

Scenario packing is explicit: OPENs in <=16-session cohorts, aligned deadline
grid, vote/control lanes co-packed; checkpoint heights kept separate, two extra
heights/cohort for START/CLOSE. Required sparse heights/day are
`max(ceil(votes/slots),ceil(control_bytes/32768))+288+2*ceil(sessions/16)`.
Arbitrary staggered closures or recovery backlog can cost more; this is not a
universal schedule upper bound. Continuous uses 17,280 heights/day at five
seconds; padded-active hybrid uses their maximum with required sparse heights.
At zero active sessions hybrid uses only 288 checkpoints. Sparse event/checkpoint
mode is the low-storage alternative; active-period duty factor remains unknown.

| Votes/min | Q active hybrid GB/day | GB/year | GB/3yr/node | Sparse event/checkpoint GB/3yr/node |
| ---: | ---: | ---: | ---: | ---: |
| 10 | 0.134606016 | 49.13119584 | **147.39358752** | **33.02807328** |
| 100 | 0.379016064 | 138.34086336 | **415.02259008** | **310.93528896** |
| 1,000 | 2.823116544 | 1,030.43753856 | **3,091.31261568** | **3,090.00744576** |
| 10,000 | 28.201579008 | 10,293.57633792 | **30,880.72901376** | **30,880.72901376** |

10,000/min is offered demand requiring more heights than available, not an
admitted archive prediction. Q estimates may exceed P because omitted components
are now counted. No-session idle growth: continuous **117.65703168 GB/3yr**,
hybrid/checkpoint-only **2.14949376 GB/3yr**. Pure inactivity could store no events,
but then there is no authenticated epoch progress. Neither idle figure contains
media or sources. Four-validator and two-extra-archive byte totals, every additive
daily component, annual growth, primary1.25 and backup3.8 are retained per row.
Using 16 KiB rather than 4 KiB commit certificates adds **232.5086208 GB/3yr**
at 17,280 heights/day, independently of user workload. Clock-proof size also
needs measurement; the 1 KiB allowance cannot establish production fit.

For 10–100/min at constant active hybrid duty, journal logical primary is
147–415 GB; estimated physical primary is **184–519 GB**, retained backups
**700–1,971 GB**. Six service archives store 884–2,490 GB logical network-wide,
before backups. Sparse policy offers 33–311 GB logical, conditional on batching
latency/window choices. A **0.5–1 TB journal primary provisioning envelope** is
a reasonable owner budget proposal for this narrow workload, with separate
backup/snapshot/maintenance and media/source capacity; it is not a total node
budget. At 1,000/min journal alone grows ~3.09 TB logical. Failed-review originals
can dominate: at 144/1,440 sessions/day retaining 2 MiB per OPEN adds
**330.67892736 GB /3.3067892736 TB** in three years. Accepted originals shared
by content address must not be counted twice, while source-only replay cannot
depend on a disposable cache. Launch needs an explicit source-retention budget.

Economics reuse **historical 2026-10-18 Task 7.8 illustrative input prices**;
no current quote or purchase recommendation. Whole-node examples add this Q
journal to independent **1,000 representative media/day**, 211,172 bytes/media,
one compute charge, 1.25 physical amplification, 1 GiB base, four retained
0.95 full backups, four full backup uploads/month and eight peers. Egress is
logical writes*8*1.44 plus a conservative per-validator phase allowance
24,576 bytes/height*3 peers. No hidden replica multiplier inside one node.
Bandwidth/egress use archive writes including estimated local indexes as a
conservative proxy; actual wire need not transmit derived indexes. The1.25
physical factor applies after explicit index bytes as an unmeasured residual
page/fragmentation margin, not another independent copy of those index rows.

| Votes/min, active hybrid | Three-year USD: budget / mainstream / storage-focused | Month36 USD, same order |
| ---: | --- | --- |
| 10 | **1,456.04 / 6,758.53 / 2,187.25** | 63.35 / 324.82 / 74.26 |
| 100 | **2,112.82 / 10,715.84 / 2,610.57** | 99.31 / 534.65 / 99.71 |
| 1,000 | **8,868.29 / 50,664.21 / 7,567.76** | 458.88 / 2,632.96 / 365.81 |
| 10,000, unserviceable demand | **79,376.21 / 466,989.57 / 60,129.81** | 4,195.71 / 24,449.79 / 3,132.10 |

Compare 7.8 media-only 1,000/day: three-year USD 1,102.64/4,504.76/1,959.38
and month36 43.18/205.95/62.67. Sparse 10/min Q+media gives three-year
1,176.10/4,980.36/2,007.87; sparse100 gives 1,843.33/9,068.05/2,425.43.
The media-only measurement basis is a 36-fixture corpus, not a production upload
forecast. Physical/index assumptions are estimates, not observed journal DB
measurements. Snapshots/temporary/VACUUM space need provisioning separately;
pricing does not double-charge a new compute node for the journal. Omitted
original/source archives, CPU saturation, disk IOPS, repair and provider bundle
limits can materially raise cost; the near-$100 examples are not affordability
guarantees. Full node+source retention has no definitive cost until those inputs
and real workload are bounded. Three-year costs are node examples, not network
totals; six archives and their operating profiles must be priced separately.

## 7. Cadence comparison and the agreement reference

The selected reference remains [Buchman/Kwon/Milosevic v3, Algorithm 1](https://arxiv.org/pdf/1807.04938v3).
Its valid-value/lock/round rules and eventual-synchrony assumptions remain;
local timeout clocks drive round progress, not an authoritative application
cutoff. Sequential instances can order journal events, but this application,
clock proof, durability and data-availability adaptation needs separate review.

| Policy | Review opportunity and idle periods | CLOSE / epochs / resources | Failure, censorship and compatibility |
| --- | --- | --- | --- |
| A. Short continuous ticks | Height windows shorten when ticks accelerate; no human-time minimum. Empty ticks throughout inactivity | Deterministic height closes progress with quorum; high proof/storage/phase cost | No quorum stops ticks. Faulty proposer can delay rounds or censor unadmitted votes. Clock-free height validity can stay stable under reference rules |
| B. Event-driven | Event count alone provides no minimum time; no-vote session can remain open indefinitely | Must generate a mandatory close/clock control value even with no user input. Trigger-only local timer is insufficient | After synchrony honest proposers must service due transitions. Infinite client silence cannot prevent a valid control proposal; frozen authenticated inputs preserve reference validity |
| C. Periodic authenticated epochs/checkpoints | A minimum number of epochs implies time only if the epoch clock has an authenticated rate/real-time rule | 300-second sample reduces idle proofs; gives bounded intended wake-ups and no-media quota progress. Coarse review boundaries/renewal | Missed checkpoints do not finalize during partition. Catch-up must have explicit jump/sequence semantics. New timestamp schema/clock assumption outside existing reference |
| D. Bounded hybrid — prefer for design | Batch events under maximum body/work and target latency while active; sparse authenticated checkpoints while idle. Opportunity uses committed START/deadline, not tick count | Mandatory closes/freeze first, reserved control service; disable gratuitous empty fast ticks when no active session. 5s/300s are test examples | Active duty, backlog, exact pacing and recovery close pages require freeze. Same BFT rules, no timer unlock or mutable local-time validity |

All policies share finite capacity across sessions and quotas. Event bursts do
not create reviewer eligibility or currency. New reviewers need authenticated
history/bootstrap; sending a message never grants status. A partition can deny
most users the entire review window; a surviving q can close without them.
No cadence policy supplies universal inclusion fairness. No-quorum periods have
no guaranteed wall-clock maximum; proposer rotation helps only under the full
liveness assumptions and complete available inputs.

## 8. Cutoff candidates and recommended deterministic semantics

P's K=o+256 has 255 interior heights. It gives reproducible closure and close-first
classification; it provides **zero real-time minimum**, and an unbounded real-time
maximum during stalls. At nominal five seconds it is 21m20s, an illustrative
conversion only. A minimum height count, quorum-of-reviewers threshold or local
timer cannot supply a human-time guarantee. Early positive quorum never closes.

Candidates: (1) retain height-only and explicitly disclaim human opportunity;
(2) approved consensus timestamps with an authenticated manipulation/error rule;
(3) explicit BFT-authoritative time/epoch proofs with mandatory closure; (4) an
authenticated connected-service/grace protocol, materially more complex. Prefer
(3) with owner-chosen minimum/window/error tolerances; keep duration symbolic.

Concrete candidate for specification, **not approved or implemented**:

1. Finalize OPEN with exact target, parent, full source inventory and reserved
   control capacity. No same-height votes. Then finalize START with q3 distinct
   static-validator attestations taken **after observing the finalized OPEN**.
   Each attestation binds N/G/journal/profile, exact parent/checkpoint, SID and
   sequence. All source bytes must already be durable and available. No circular
   signature over the containing batch's own final hash.
2. Assume every honest clock's absolute error <=epsilon, authenticated sampling
   rules and persistent monotonic behavior. With <=1 Byzantine among three,
   median lies between honest samples. Let U=median(START)+epsilon and choose
   approved W>=minimum human interval. U is an upper bound on real OPEN time
   under the stated observation/error assumptions. Deadline D=U+W is immutable.
3. Later q3 time proof has L=median(samples)-epsilon, nondecreasing, bound to the
   prior finalized checkpoint. A proof reaching L>=D cannot have been completed
   before real OPEN+W if honest sampling/error assumptions hold. Old replayed
   proofs cannot move time backward or to a different checkpoint. Real-time
   correctness is an extra oracle/clock assumption, not implied by signatures.
4. At the first agreed boundary whose proof reaches D, derive all due sessions
   from the prior state; freeze admission to **all** of them before optional
   votes. CLOSE summaries use the complete previously admitted prefix, sorted
   by SID. No producer-chosen omitted close, extension or favorable early close.
   Time attestation inputs are immutable once proposed; replay never reads its
   own wall clock. A timer only prompts honest proposers to seek such a proof.
5. After a partition, use the approved fresh proof and same rule. An already
   expired session freezes/closes before any newly admitted vote. No backdating
   from a client signature/receipt. If owner wants connected-time grace instead,
   approve a separate RESUME/extension rule and fresh signed cutoff binding.

The minimum is elapsed opportunity, **not guaranteed connectivity, data reach to
every user or inclusion**. The maximum intended W plus checkpoint batching/round
latency is conditional on clocks/quorum/service; no asynchronous upper bound.
Byzantine extreme readings cannot alone move a q3 median beyond honest readings,
but selecting old honest samples can delay it. Bind sample acquisition to parent,
sequence, START and stable protocol rules; eventual fresh honest service is a
liveness obligation. Drift, reboot/NTP corrections, attestation lifetime,
monotonic/exhaustion and catch-up/jump rules need a complete schema and review.
This task does not establish a deployable authenticated-clock implementation.

**Post-partition closure capacity gate:** 16 OPENs/height with fixed height W
limited P to 16 simultaneous closes. Time deadlines or stalled recovery can make
many opening cohorts due at once. One cannot require arbitrarily many full
2 KiB CLOSE events in a 256 KiB body. The smallest candidate amendment is an
implicit deterministic freeze for all due sessions plus a persisted ordered
close-work queue with <=16 materialized summaries/height; mandatory pages precede
optional work. All due votes remain LATE even before their summary page. An
alternative is a provable global due-capacity reservation restricting OPENs.
Neither is implemented here; the clock probe tests small full-close sets only.
Queue completeness, bounded derivation/index work, checkpoint recovery and
starvation must be frozen and tested before selecting this design. With N due
and pages16, summaries require ceil(N/16) successful heights; actual seconds
remain unbounded without quorum. A 1,000-session recovery needs >=63 heights,
nominal315s at5s, and no new votes in already-frozen sessions.

| Boundary case | Deterministic result / guarantee |
| --- | --- |
| Vote admitted in last prior batch | Counts, including negative or unsure |
| Vote first admitted at freeze boundary | LATE, no charge, regardless of old custody receipt |
| Missing/delayed receipt | Receipt affects custody evidence only; query finalized position/history |
| Withheld vote source | Incomplete validation; no positive vote/agreement based on hash-only data |
| Empty / fewer than five / no established | Close UNDECIDED; no fabricated approval or automatic extension |
| All unsure | Quorum may exist, decisive denominator zero: UNDECIDED in that dimension |
| No quorum | No new authoritative clock/admission/close; old state preserved |
| Passing session, stale media parent | Cannot reparent votes; follow separately approved retry/lifecycle policy |

Safety is agreed prefix/complete tally/mandatory boundary. Conditional liveness
is eventual progress with quorum, synchrony and bounded full validation. Fairness
of pre-admission service and real user opportunity is a separate owner policy.

## 9. Quotas, epochs and no-media behavior

Preserve 5 probationary/25 established **distinct submission** participations.
ADMIT charges once across dimensions and allowed retries; rejected/unresolved
submissions retain the charge. No later negative judgment refunds quota, no
expired cache permits replay, no epoch reset deletes lifetime claims. Live
ordered quotas/penalties coexist with frozen historical base qualification.

| Clock | No accepted media for days/months | Amendment/cost |
| --- | --- | --- |
| Media height//5 | Indefinite usage, age and penalty freeze; review may stop after 5/25 charges | Existing meaning; unacceptable if owner requires continuing participation |
| Journal height//E | Renews only if ticks advance; producer-fast heights can accelerate resets/penalties, pure idle event mode freezes | Simple deterministic rule, no human-rate guarantee; height pacing needs authority |
| Explicit BFT epoch transitions | Advances without media when valid mandatory epoch controls finalize | Freeze exact trigger, order, retention and catch-up; arbitrary optional epoch transaction is censorable/manipulable |
| Calendar-like epochs | Can follow elapsed time independently of media | Needs authenticated clock/origin/error/rollback policy, not verifier local date |

Smallest recommended policy amendment: use a **review-service epoch**, derived
from approved BFT time/epoch events, for participation quota renewal and duration
of reviewer cooldown/suspension. Keep numeric 5/25 and existing penalty epoch
counts pending owner approval; changing their real-time duration must be explicit.
Retain complete charges with their original epoch and future-effective penalty
intervals; process epoch transition/freeze/close before optional admissions.
Clock catch-up may expire an interval, but cannot reclassify old votes or grant
multiple retrospective allowances for unused epochs.

Keep native transfers, creator rewards, supply/issuance, media count and validator
epoch0 untouched by review-service epochs. Do **not** silently change earned
wallet age or probation-promotion age from media epochs. Under this smallest
amendment a NEW reviewer still cannot earn media/native activity or complete
media-based age during a no-media month. Existing qualified/bootstrap reviewers
can renew participation and finish penalties. If owner also requires new earned
reviewer progress during such a stall, age/probation's separate clock amendment
is an additional decision, not an inferred reward/event authorization.

## 10. Workloads, bursts, recovery and CPU

All 132 retained configurations span 10/100/1,000/10,000/min, fixed24/byte/byte+CPU,
sample/conditional O maximum/8KiB allowance, three cadence policies at5s; extra
1s/10s sensitivities for sample byte+CPU. Results include every additive daily
archive component, annual/three-year bytes, costs, per-validator bandwidth,
signature demand, backlog and closure limitations. Invalid overload rows are
explicit offered demand, including rows whose required heights exceed budget.

| Five-second profile | Max votes/batch | Full vote lane incl close reserve/header | Vote ceiling/min | Required vote heights/hour at 10 /100 /1k /10k |
| --- | ---: | ---: | ---: | --- |
| Fixed24, sample | 24 | 75,720 | 288 | 25 /250 /2,500 /25,000 |
| Byte only, sample | 130 | 260,902 | 1,560 | 5 /47 /462 /4,616 |
| Byte only, conditional O max | 127 | 260,487 | 1,524 | 5 /48 /473 /4,725 |
| Bytes+CPU, sample | 96 | 201,504 | **1,152** | 7 /63 /625 /6,250 |
| Bytes+CPU, conditional O max | 96 | 205,152 | **1,152** | 7 /63 /625 /6,250 |
| 8KiB event allowance, byte or bytes+CPU | 27 | 255,084 | **324** | 23 /223 /2,223 /22,223 |

Available heights=720/hour. Control and deadlines also need space/work. Maximum
vote ceilings are mathematical lane bounds, **not sustainable measured BFT
throughput**; 1,000/min fits only the narrow small-event, coalesced-control
scenario with little recovery margin. 10,000/min cannot fit any of these5s
profiles. Sample96 at1s=5,760/min, at10s=576/min; even1s fails10k. Bytes-only
sample would require >=1.2821 vote heights/s to serve10k, plus controls; new
latency/CPU/round/retention benchmarks and owner decisions would be required.

| Active hybrid sample96 | 10/min | 100/min | 1,000/min | 10,000/min demand |
| --- | ---: | ---: | ---: | ---: |
| Vote signature checks/s/validator | 0.167 | 1.667 | 16.667 | 166.667 |
| Checks/s incl 4 commit+3 clock/height, 2/session | 1.57 | 3.10 | 18.40 | 183.63 |
| Estimated ingress bytes/s | 16,896 | 20,799 | 59,837 | 594,048 |
| Estimated egress bytes/s | 32,693 | 65,281 | 391,161 | 3,903,816 |
| Backlog growth votes/hour | 0 | 0 | 0 | **530,880** |
| Six-hour outage offered votes | 3,600 | 36,000 | 360,000 | 3,600,000 |
| Ideal clearance with continued load, minutes | 3.15 | 34.22 | 2,368.42 | Never |
| 10k extra burst clearance, minutes | 8.76 | 9.51 | 65.79 | Never |

Clearance uses `backlog/(capacity-arrival)` without closure expirations or
competing recovery traffic. Votes from expired sessions are late instead of
eventually admitted. P's 24 profile clears a10k burst over100/min in53.19min;
byte130 gives6.85min; byte+CPU96 gives9.51min. At allowance27/324, that burst
takes44.64min. Sample96's P-style255-height window holds at most24,480 votes;
that does not promise a10k burst will fit an aged/concurrent session. The
discrete trace admits a10k isolated burst over105 successful96-vote heights,
and close-first at height4 admits only288, making9,712 late. Three stalled
service ticks build288 queued votes; three spare96-vote ticks clear that queue
after arrivals stop. No-quorum time contributes zero successful heights.

At1/5/10ms/check, sample1k's18.4checks/s consumes1.84/9.2/18.4% of one core,
before parsing/hash/disk/eligibility/media. These are hypothetical CPU inputs,
not measured EIP-191 or end-to-end validation. Worst batch work96+64+7=167
checks; at10ms this is1.67 CPU seconds, unbenchmarked. Malformed floods have
no finite offered-load bound: cap bytes/depth/connections/queues before crypto,
reserve honest control service, reject unknown-width signatures cheaply, and
rate-limit expensive invalid recoveries. A local100checks/s assumption is not
validity or an SLA; eligible bot/Sybil floods and client fairness need separate
policy. Unauthenticated garbage need not be retained as canonical history.

Concurrent1,000 sessions need >=63 OPEN batches at16/batch;100 two-dimensional
reviewers/session offer200,000 signed votes, >=2,084 sample96 vote batches,
nominal2.89hours before control and competing traffic. They cannot all complete
within P's255-interior-height window. Post-partition summary paging has the
separate mandatory freeze/close backlog above. Every validator recovering needs
full history, durable signer fencing and data, not merely enough bandwidth.

## 11. Cross-ledger authentication and noncircular order

Minimum authenticated dependency DAG:

```
G-independent policy sources + stream descriptors + M -> C / profile digests
full G2 binds those bytes -> independently pinned G -> derived journal J0
finalized media F + prior finalized journal checkpoint -> OPEN -> START
ordered admitted votes + epoch/eligibility causes -> freeze/CLOSE/checkpoint
closed PASS + full evidence + exact F + media bytes -> media B/F+1 and Qmedia
already-finalized B/Qmedia -> later journal ANCHOR -> next usable media context
```

Journal checkpoint must name N/G/stream/profile/C/validator epoch, height/hash,
parent and authenticated commit proof under the pinned roster; full contiguous
ancestry/data are necessary. Session commits SID/submission/original hash/creator,
OPEN/START/cutoff policy and exact finalized F, all admitted evidence positions,
count/root and both complete tallies. Evidence inventory includes every vote,
historical eligibility/quota/penalty cause, source bytes, source indexes and
proof dependencies. A commitment alone proves neither completeness of an offered
unadmitted pool nor evidence availability.

Media binds exact closed-session checkpoint/CLOSE locator and complete derived
outcome, exact submission/original/creator and unchanged finalized parent F.
No replay across genesis, stream, session, dimension, epoch/profile or parent.
Two passing sessions on F cannot both settle the same child; losing/stale work
remains retained and follows approved retry rules. Journal cannot require a
future media block to authenticate its own OPEN/epoch; media cannot depend on
an ANCHOR that itself requires this media's future finality. Anchor-before-next
usable-media discipline and recovery reconciliation must be specified explicitly.
No reparenting of a passed result to a later media parent is inferred.

Use provisionally the same **G2-authorized static N4/f1/q3 equal-power set** for
both streams, subject to owner approval, with separate stream descriptors,
message domains, durable signer namespaces, locks/rounds/checkpoints and genesis
derivation. Reviewer-service epochs are not validator membership changes.
J's isolated height1/round0 signer does not support this adaptation; K/M trust
and envelope verifiers do not approve missing application/clock semantics.
No signer expansion or signing is performed here.

Fresh nodes pin G independently, resolve both authorized stream origins/profiles,
verify contiguous prefixes/evidence and replay epoch/eligibility transitions at
their exact positions, then reproduce media settlements. A snapshot carrying its
own root is not an independent trust anchor. Do not hide a later-key-compromise
history problem behind unsigned checkpoints; static keys require explicit custody
and archival trust assumptions. Missing media/journal/source history refuses
validation, never means an empty vote set or unpenalized reviewer.

The 3 MiB media format is not redesigned. O's base64/media-reference/native
budget leaves243,028 bytes for other required fields; complete combined maximal
schema fit remains a gate. A bounded authenticated reference keeps arbitrary
vote arrays external while requiring their archive; it does not discard votes.

## 12. Owner decision package and implementation gates

The requirements in section1 are owner-directed. The following are engineering
recommendations awaiting decisions; no row silently approves a launch setting.

| Owner decision | Recommendation / required choice |
| --- | --- |
| 1. Separate BFT review journal | Approve in principle as pre-media authority, subject to full protocol review; no cohort fallback |
| 2. Authority | Same provisionally pinned static N4/f1/q3, separate stream/signing state; approve actual independent operators/bootstrap separately |
| 3. Cadence | Bounded hybrid, event batching plus sparse authenticated idle epochs; measure duty/latency before choosing5s/300s |
| 4. Review window | Approve minimum human interval, intended W, clock error/authority and post-partition treatment. Prefer START plus authenticated deadline/freeze; +256 remains provisional |
| 5. Batching | Primarily bytes plus deterministic work; approve finite field/event/control/proof limits. 96/64 are test budgets only |
| 6. Quota epochs | Retain5/25 and all ADMIT charges incl rejected media; separate service epoch for quota/penalty progress. Explicit additional decision for earned age/promotion clocks |
| 7. Archival/availability | Complete evidence before honest value votes, all4 validators plus2 independent serving archives, verified repair/source-only recovery and backups; approve indefinite historical retention and source duties |
| 8. Initial throughput | 10–100 signed dimension votes/min as benchmark workload, not launch promise. 1k conditional;10k outside tested arithmetic profiles |
| 9. Node storage | Budget at least0.5–1TB journal primary for constant-active10–100/min sample planning, separate backups/media/failed originals. Approve complete source workload and measured physical/IOPS budget before launch |
| 10. Schemas to freeze | Closed vote successor, OPEN/START/time/epoch/freeze/CLOSE pages, all evidence/control events, headers/proofs/checkpoints/manifests, signing domains, G2 policies/clock origin, media binding/hash and recovery dispatch |

Additional readiness gates: deterministic bounded-cost expiry indexing/closure
pages; OPEN scheduling/reservations; monotonic clock and partition catch-up
proofs; replay-bound timestamp crypto vectors; rights/technical time reconciliation;
complete qualification/offense/history semantics; combined media maximum-fit
vectors; full agreement engine/refinement review and nonrollbackable two-stream
signer custody; independent source-only node interoperability; measured validation,
network/round/flood/disk/recovery behavior on target hosts; archive operators and
restore/repair duties; final independent protocol/security review. Launch needs
separately authorized genesis/activation/deployment after these gates.

Smallest safe subsequent task: **owner policy/architecture specification pass**
settling clock/minimum opportunity, partition closure paging/reservations, epoch
scope and archive duties, then freeze those inert byte contracts and independent
vectors under separate authorization. No production consensus/journal or Task
7.17R begins. Missing wire/clock bounds lead to conditional findings, not invented
production guarantees.

## 13. Verification and disposition

[Focused tests](../tests/test_milestone_7_task_7_17q_capacity_clock.py) cover exact
batch -1/at/+1 bytes, oversized votes/keys/signatures/IDs, mixed16-closes batches,
24 versus bytes/work, idle growth, idle mandatory closes, partition recovery,
last-admitting/first-late boundary, close omission/order, no-quorum authority,
concurrent quota exhaustion, no-media epoch/penalty progress, malformed floods,
withholding/incomplete evidence, foreign genesis/checkpoint and cross-ledger replay.
The clock experiment is symbolic with supplied authenticated samples, not a real
clock, signer, BFT integration, full slot/tally reducer or partition proof. P's
unchanged reducer supplies slot/tally/omission tests and all eight unsafe controls.
The fluid/discrete queue arithmetic does not simulate actual Tendermint rounds.

Retained [inputs](../verification/review717q/inputs.json),
[results](../verification/review717q/results.json), and
[validation](../verification/review717q/validation.json) separate structural
measurement, modeled estimates, executed tests, and exclusions. Commands:

```powershell
.\.venv\Scripts\python.exe -B -m verification.review717q.workload
.\.venv\Scripts\python.exe -B -m pytest tests/test_milestone_7_task_7_17q_capacity_clock.py tests/test_milestone_7_task_7_17p_review_journal.py -q --tb=short --basetemp=temp/task717q-focused-delivery --junitxml=temp/task717q-focused-delivery.xml
.\.venv\Scripts\python.exe -B -m verification.review717q.audit --junit temp/task717q-focused-delivery.xml --junit temp/task717q-regression-final.xml
```

The regression module inventory and executed results are recorded in validation.
Use workspace TEMP/TMP and a fresh workspace pytest basetemp, as in P, for the
durable signer/SQLite subprocess regressions. Old tests may use their unchanged
disposable test keys/stores; no production keys/stores are created. Source hashes
and isolation checks establish P code/fixtures/negative traces unchanged, all
active code unchanged, index empty, HEAD/branch unchanged, and only Q deliverables.

Release verification: **120 focused passes (40 Q +80 unchanged P)** and
**777 regression passes**, **897 total**, zero failures/errors/skips/timeouts.
The regression selection is P's17 historical modules plus7.8 economics; its exact
module inventory is retained in validation. All eight P unsafe controls still
produce their exact retained counterexamples. The new economics cross-check
independently reproduces7.8 media-only costs on all three historical profiles.
Documentation links, whitespace/encoding, constrained file inventory, preserved P
artifacts/history and unchanged HEAD/branch/index pass the delivery audit.
Early Q idle-growth assertion expectations were corrected to
the independently itemized sum after the first focused run (35 passes/1 failure);
that failed run is not added to successful release counts. No skipped or timed-out
test is counted as a pass. Whole-repository, live/multi-host BFT, production crypto
for new profiles, physical crash/clock, full close paging and target-host capacity
benchmarks are excluded, not claimed.

**Task 7.17Q is ready for review and a later authorized commit** as a conditional
verification/decision artifact after the recorded release checks. Task 7.17 and
production journal implementation remain **BLOCKED**. This task makes none of
the missing owner decisions and activates nothing.
