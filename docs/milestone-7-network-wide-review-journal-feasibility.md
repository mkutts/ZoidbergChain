# Milestone 7 Task 7.17P — Network-wide review journal safety and feasibility

Date: 2026-10-27 (America/New_York). **Isolated verification and planning only.**

The proposed ordered journal can make every eligible **authoritatively admitted**
vote count, including negative and unsure votes, with deterministic closure and
reproducible quota accounting. The retained bounded application model satisfies
its checks; eight weakened variants produce counterexamples. This is conditional
on a uniquely finalized authenticated journal, complete evidence, deterministic
policy and a separately reviewed BFT implementation. It does not verify consensus
by assuming consensus. Production journal implementation and Task 7.17 remain
**BLOCKED**. None of the recommendations below is an approved protocol setting.

The largest feasibility constraints are independent of agreement safety:

- `+256` orders a cutoff; it guarantees no minimum human response time.
- The proposed **24 VOTE events per batch** limits a five-second planning cadence
  to **288 signed votes/minute**, before other contention. 1,000 and 10,000/minute
  are infeasible at that profile even when their raw bytes look serviceable.
- A q=3 certificate with f=1 implies at least two honest custodians **at signing**
  only under complete-validation/store-before-sign assumptions. It guarantees
  neither permanent retention nor two online sources later.
- Media-height quota epochs can freeze human participation while journal height
  continues. Separate histories also need explicit cross-history ordering,
  signing domains, durable namespaces, genesis and media-hash amendments.

## 1. Repository prerequisites and scope

| Check before any edit | Result |
| --- | --- |
| Expected and actual branch | `Compression-State-Bloat-and-Node-Economics` |
| HEAD | `a3ea45556308baa3331f5cda724139abb1f993eb` |
| Separate Task 7.17O commit | HEAD, `Milestone 7 Task 7.17O: propose network-wide BFT review voting` |
| Index/worktree/untracked files | `git status --porcelain=v1 --untracked-files=all` empty |
| O decision tracked | `docs/milestone-7-network-wide-review-voting-protocol-decision.md` |
| Available tracked predecessors | H model; I wire contract/vectors; J signer; K authority verifier; M G2 verifier |
| Applicable instructions | No ancestor/root/docs/verification/tests `AGENTS.md` found; no delegation |

Sources consulted: [7.17O](milestone-7-network-wide-review-voting-protocol-decision.md),
[7.17N](milestone-7-reviewer-admission-policy-decision.md),
[7.17B](milestone-7-v2-reviewer-history-protocol-amendment.md),
[7.17G](milestone-7-distributed-finality-protocol-decision.md),
[7.17H](milestone-7-tendermint-model-verification.md),
[7.17I](milestone-7-bft-wire-and-signer-contract.md),
[7.17J](milestone-7-bft-durable-signer-implementation.md),
[7.17K](milestone-7-bft-validator-authority-implementation.md),
[7.17L](milestone-7-g2-genesis-and-bootstrap-contract.md), and
[7.17M](milestone-7-g2-genesis-verifier-implementation.md).
Historical producer-selected cohorts in N/B are superseded by O; no such fallback
is modeled or recommended. Originality and admissibility stay separate.

Inspected [existing vote authentication and tally](../canonical_v3/evidence.py),
[dual review](../dual_review.py), [quota constants](../milestone5_policy.py),
[eligibility](../services/reviewer_eligibility_service.py),
[history](../canonical_v3/history.py), [issuance](../canonical_v3/issuance.py),
[atomic accounting](../canonical_v3/atomic.py), and the isolated J/K/M boundaries.
Existing vote3 validates signatures, dimension/context and a supplied frozen set,
with five/one-established quorums and exact 7,000-basis-point decisive arithmetic.
It does not directly sign the new genesis/session fields or establish a complete
network-wide vote inventory. History trusts application acceptance; local atomic
claims cannot supply distributed admission authority. Active eligibility uses
finalized media height/5 and 5/25 quotas. These sources remain unchanged.

All additions are inert under `verification/review717p/`, one test file and one
fixture directory, plus this report and a reference/gate notice in O. The exact
13-file inventory is:

| Change | Files |
| --- | --- |
| Created report | `docs/milestone-7-network-wide-review-journal-feasibility.md` |
| Modified reference/gates only | `docs/milestone-7-network-wide-review-voting-protocol-decision.md` |
| Created isolated model/checks | `verification/review717p/{__init__,model,oracle,check,workload,audit}.py` |
| Created retained evidence | `verification/review717p/{results,negative-control-traces,validation}.json` |
| Created test and fixture | `tests/test_milestone_7_task_7_17p_review_journal.py`, `tests/fixtures/review717p_v1/cases.json` |

There are
no production imports, sockets, live APIs, consensus changes, new keys, schemas,
stores, genesis activation, migration, reset or deployment. No commit, staging,
push, merge or subsequent task. Final branch/HEAD and index equal their initial
values; the final worktree contains only these unstaged deliverables.

## 2. Two histories and the exact authority boundary

**A: journal height j** orders finalized review-session, vote, evidence and media
anchor events. **B: media height h** counts accepted original media submissions.
Each media block accepts one original. There is no equation j=h; rounds belong
to a particular stream and height. Empty journal ticks may advance j while h=0.

The proposed architecture is **two separately authenticated ledgers**, logically
one application dependency graph. Using the same static genesis-authorized four
validator keys does not combine their agreement instances or their durable state.
The journal needs a separate BFT instance, application state machine and signer
namespace. Media agreement remains a different instance. An interleaved single
consensus history would instead require explicitly approved control-record types
and amendments to the media-only history rule; none exists here.

| Bound input | Required meaning before production integration |
| --- | --- |
| Genesis | Independently authenticated G2 bytes commit both stream profiles, validator manifest, application policies, bootstrap and limits. Media origin `(0,G)`; derive journal J0 after G, binding N/G/history policy/bootstrap and approved journal identity. J0 is not inserted into its own genesis preimage. |
| Validator authority | Full G2-authorized M, commitment C, static epoch0, N4/f1/q3; shared roster is conditional proposal. Different rosters would require separately authenticated manifests and authority histories. A peer-supplied roster is not authority. |
| Journal agreement identity | G-independent descriptor/policy committed by genesis, then stream-specific signing context binds N/G/C/epoch/agreement digest/stream/height/parent/round/value or nil/step/full validator identity. |
| Journal finality proof | Scheduled authenticated proposal plus q distinct matching same-round precommits, exact journal value/parent/context, complete data and verified ancestry. A set of three signatures is not an implemented agreement protocol. |
| Trusted checkpoint | At bootstrap use externally pinned G/J0 derivation; later checkpoint must extend a retained verified prefix or have an explicitly approved independent trust mechanism. A root accompanying its own snapshot is not a new trust anchor. |
| Review reference | SID, submission, original hash, creator, OPEN/snapshot references, K, exact CLOSE locator/hash and complete derived dual tally/count/ordered commitment. No producer replacement subset. |
| Media reference | Session's immediate finalized media parent F is exact; media binding and its new canonical media hash commit the review reference. Both full media and full journal evidence are dependencies. |

J's current signing boundary is **height 1 / round 0 only**. It cannot sign
journal height 2, run round changes or advance media finality merely because its
wire verifier can parse those coordinates. K authenticates test-pinned authority
and proofs, not complete application acceptance. M's best result is
`VALID_ENVELOPE_INCOMPLETE_POLICY`; it does not approve journal policy or provide
launch authority. This task calls none of them to manufacture journal signatures.

## 3. Implemented model and assumptions

[model.py](../verification/review717p/model.py) is a deterministic in-memory reducer.
State contains height/tip, anchored finalized media parent, sessions, immutable
submission/original/creator identities, OPEN eligibility snapshot, ordered admitted
votes and positions, conflict groups, CLOSE/results, permanent quota charges,
prospective penalties, qualification-status facts and settled-original claims.
Votes bind both dimensions' distinct choice alphabets, network/genesis/session,
submission/original/creator, media/journal snapshots and cutoff. A batch carries
ordered events and a separate finalized-certificate abstraction.

**Prominent assumptions and exclusions:**

1. The experiment supplies authenticated, uniquely finalized BFT batches. A
   certificate's authentication Boolean is a symbolic fact, **not cryptography**.
   N/G/C/agreement/stream/epoch, h/parent/value, distinct q signers and round are
   checked inside that abstraction. Model hashes are diagnostic commitments,
   not frozen production encodings. Any caller manufacturing those trusted
   facts has changed the experiment's premises.
2. Signatures are unforgeable symbolic authentication facts over the complete
   displayed vote. Real EIP-191, low-S, keys, parsing and signature interoperability
   are outside this application model. Existing J/K/M regressions retain their
   original, narrower crypto tests; they do not authenticate these new profiles.
3. OPEN creator authorization, complete original/rights/technical source validity,
   earned qualification and objective penalty proof validity are explicit trusted
   oracle inputs. The model tests their effects, not their full source languages,
   signature validity or existing timestamp-policy reconciliation.
4. Full source availability is a content-addressed inventory per event, including
   its dependencies by assumption. Missing an event source or segment refuses
   verification. It does not simulate physical disks, real media downloads,
   object-manifest paging, a Merkle proof scheme or independent archive operators.
5. q=3/f=1/static N4, deterministic complete policies, no hash collisions and
   unique media finality are assumed. Consensus locks, proposer selection and
   rounds are not reverified by this reducer. H's earlier bounded model is not
   integrated into this state machine. Threshold/schedule examples below are
   conditional illustrations, not a new Tendermint liveness proof.
6. There is no trusted fast-sync snapshot. A target checkpoint requires contiguous
   replay from the configured base. Checkpoint rollback/conflict guards retain
   local finality. Both node replicas use this reducer; the separately authored
   oracle independently checks the search alphabet's acceptance/accounting and
   uses rational tally arithmetic. This is not two-language node interoperability.

The model implements O's first-finalized-slot rule, semantic duplicate handling,
one grouped conflicting slot, immutable historical votes, live 5/25 quota check,
paired-dimension/lifetime-submission charge, frozen base status and prospective
penalty masks. Penalty durations are oracle facts rather than a full offense
engine. Retry is limited to one delayed unresolved/stale-parent attempt with
unchanged S/H/creator and new SID; terminal negative and usable PASS cannot be
retried. Economic rewards and earned-qualification derivation are not implemented.
Production byte/depth maxima are capacity assumptions, not a new parser.

## 4. Invariants, bounds and reproducibility

| Invariant tested | Check/evidence |
| --- | --- |
| Same finalized prefix gives same tally/state | Two replays with opposite source-arrival order compare full fingerprints: accepted sources/positions/statuses, roots/tallies/CLOSE, conflicts, observations, quota, penalties/statuses/media claims. Independent oracle compares slots and charges for the bounded alphabet. |
| All eligible admitted pre-close votes count once | Independent acceptance oracle equals the entire ordered admitted list; no positive-only selection or stop-at-five limit. |
| Exact cutoff; no post-close votes | All admitted positions satisfy o<j<K; mandatory derived CLOSE is first at K. Boundary and subsequent votes are LATE. |
| Authentication and all signed bindings | Unauthenticated batch input invalid; foreign N/G/SID/submission/original/creator/snapshots/K/dimension/choice cannot count. |
| No replay/equivocation inflation | First slot immutable, same-choice variants duplicate, conflict retained without changing prior vote or charge. |
| Finalized negatives cannot be removed | Result/root recomputed from every ordered source; altered CLOSE/reference/proof and deleted source refuse. |
| Missing history is not approval | Missing OPEN/VOTE/CLOSE object, skipped segment, missing media or unreplayed checkpoint -> INCOMPLETE_HISTORY. |
| Review/media compatibility | Open/unfinalized/nonpassing/substituted review, wrong stream/parent/original or duplicate settlement refuse. |
| Evidence needed for review finality | Local reducer needs complete sources; q-custody claims additionally require honest pre-sign durable validation/retention. |
| Quota agreement and no concurrent overspend | Same prefix produces same lifetime charge map; competing last-slot admissions consume in finalized order; paired dimension remains one charge. |

The two breadth-first searches retain every ordered prefix, including ticks and
repeated input choices; no histories are merged by tally alone. There are ten
vote symbols: r0 positive/negative/same-choice nonce variant, r1 unsure and
admissibility-positive, foreign N/G/SID/dimension, and unauthenticated vote.
Each height offers a tick or one symbol. Invalid unauthenticated successors are
counted as attempted/rejected transitions, not reachable states. OPEN is the
seed at j=1. Both reviewers are eligible, r0 established, r1 probationary.
This small search cannot reach five-reviewer quorum; independent quorum fixtures
and the selected larger scenarios cover that separate boundary.

| Search | Reachable states | Valid transitions | Attempted transitions | Rejected | Terminal states |
| --- | ---: | ---: | ---: | ---: | ---: |
| W=3, heights 1..4 | 1,111 | 1,110 | 1,221 | 111 | 1,000 |
| W=4, heights 1..5 | 11,111 | 11,110 | 12,221 | 1,111 | 10,000 |
| Delivery: 3 messages x 2 recipients | 280 | 408 | 408 | 0 | 216 |

The journal runs perform **12,222 state invariant checks**, **12,220 valid** and
**13,442 attempted** transitions; the runs overlap and counts are not globally
distinct states. Delivery exploration has 64 distinct two-replica delivery masks,
192 delivery edges, and 216 terminal finalized-subset transitions/states. It
merges order only after identical delivery masks. A proposer can finalize any
subset it has received; other nodes acquire full batch sources before replay.
Uncommitted local votes/receipts never change accepted state.

All three searches finish their stated finite bounds, **truncated=false**. Each
journal search has a 30,000-state fail-on-exceed cap, not an early-success cap.
No unbounded result, arbitrary concurrency exploration, all consensus schedules,
all faulty-validator placements, physical crash proof or fairness theorem follows.
The selected W=256 execution uses o=1, last permitted height 256 and K=257.

Artifacts: [results.json](../verification/review717p/results.json),
[checker/scenarios](../verification/review717p/check.py),
[independent oracle](../verification/review717p/oracle.py),
[manual expected fixtures](../tests/fixtures/review717p_v1/cases.json),
[tests](../tests/test_milestone_7_task_7_17p_review_journal.py).
Reproduce from repository root:

```powershell
.\.venv\Scripts\python.exe -B -m verification.review717p.check
.\.venv\Scripts\python.exe -B -m pytest tests/test_milestone_7_task_7_17p_review_journal.py -q --tb=short --basetemp=temp/task717p-focused-reproduce --junitxml=temp/task717p-focused-reproduce.xml
```

The checker overwrites only its two documented result files; no seeds/randomness,
network, clock, keys or environment-specific timing determine the results.
The test suite reproduces retained search counts, fixtures, adverse scenarios,
counterexamples and workload arithmetic rather than accepting changed outputs.

## 5. Cutoff analysis and closure policy alternatives

O's K=o+256 uses **journal height**, not media height or elapsed seconds. Every
finalized bounded journal batch advances by one, including approved empty ticks.
OPEN's own height accepts no votes. There are **255 interior admitting heights**;
K starts with all due CLOSEs sorted by SID, before optional events or votes.
CLOSE uses the full prior admitted prefix, even with zero votes. There is no
early close on quorum or favorable percentage. The proposer can choose optional
input order before K; that chosen order controls which conflicting first choice
or final quota slot wins. It cannot reorder across already-finalized positions.

No voluntary close transaction is required. Any proposer must supply the unique
derived close prefix or, with an approved implicit-transition encoding, execute
it as part of the validity function. Honest validators reject an absent, changed,
early, duplicate or reordered CLOSE. A faulty proposer can withhold its proposal
and delay progress in its round; it cannot make an omitted-close value valid.
Rotation/round change can restore progress only under the BFT termination and
complete-input assumptions. Receipt signatures cannot waive K or reserve slots.

| Alternative | Safety / opportunity / recommendation |
| --- | --- |
| A. Height closure only | Objectively replayable, progresses through empty ticks, bounded journal window. Does not guarantee minimum human time; fast ticks shorten opportunity. Safe cutoff candidate if owner explicitly accepts this limitation. |
| B. Height plus minimum opportunity | Define the opportunity using an approved authenticated clock/epoch/beacon or clearly measurable finalized service condition. Counting five votes or requiring all reviewers to respond can deadlock; local elapsed time/queue membership is not shared authority. A minimum number of heights alone is already A. |
| C. Approved authenticated time/epoch | Could ensure an agreed minimum interval if timestamp bounds, proposer manipulation, clock drift, stall/recovery, source authenticity and validity rules are specified. This changes policy/G2/signing; no such rule is approved here. |
| D. Scheduled close / mandatory transition | Prefer mandatory derived transitions combined with A or an approved B/C. An explicit CLOSE can be a canonical rendering of that transition. Voluntary inclusion alone is unsafe. Capacity must be reserved at OPEN. |

If height K-1 stalls, the session remains open in the finalized state; gossip may
accumulate but does not backdate admission. If K's proposal lacks data/q, it is
not finalized and nodes do not use its alleged result. After recovery, the next
valid height-K batch closes before new votes. A session opened before a partition
may lose essentially all useful connected review time. No-vote CLOSE is
UNDECIDED, never approval. There is no wall-clock maximum under asynchrony.

At most 16 OPENs per height reserves at most 16 due CLOSEs with fixed W. The
selected model closes all 16 in SID order; a 17th OPEN is rejected. At proposed
2,048 bytes per CLOSE reserve **32,768 bytes plus header space**. Higher volumes
must wait for later OPENs; they are not silently admitted with no close capacity.
Do not enforce many-session limits by truncating votes already admitted.

**Recommendation:** retain W=256 solely as a provisional experiment parameter;
select mandatory deterministic closure, then obtain the owner's minimum human
review-opportunity requirement before freezing W, tick pacing or time authority.

## 6. Concurrency, adverse timing and outcome taxonomy

| Requested situation | Modeled result / boundary |
| --- | --- |
| Many sessions together | 16 simultaneous due CLOSEs, including zero votes; excess OPEN rejected before admission. Shared vote bandwidth, no per-session guarantee. |
| Different arrival times | Exhaustive delivery masks and ordered histories; same finalized prefix gives identical state. |
| Local receipt without commitment | Custody only; zero authoritative votes/charges until ADMIT; can end CLOSED_WITHOUT_ADMISSION. |
| At K / delayed beyond K | LATE; CLOSE precedes VOTE at K. Old receipt/signing time cannot change position. |
| Validator partitions | Two responsive validators cannot supply q3: lack of progress. Three responsive correct validators can conditionally progress; one Byzantine withholding plus one outage can still stop progress. Connectivity/threshold rows are analytical schedule assertions, not a consensus implementation test. |
| One validator equivocates | q unchanged, repeated identity cannot inflate a certificate. Conflicting authenticated finalized checkpoints latch CONFLICTING_FINALITY; with f<=1/full correct BFT they are assumed unreachable. No local member exclusion. |
| Proposer censors negative / rotation | Selected schedule: empty h2, next proposer includes negative at h3, K4 retains it. Permanent delay until K instead leaves it unadmitted: censorship, not permission to rewrite tally. |
| Crash before data persistence | Missing source -> INCOMPLETE_HISTORY; honest pre-sign gate must prevent custody attestation. |
| Intact evidence restart | Same source replay/state fingerprint. This is an in-memory crash abstraction, not fsync/power-loss testing. |
| Finalized evidence unavailable | Recovering node cannot approve or infer zero historical usage; obtain another verified source or remain incomplete. |
| Media proposed while review open | INVALID as a review-admission candidate; no provisional favorable tally can substitute for finalized CLOSE. |
| Two media candidates use same PASS | Both may be provisional siblings at the same parent. Unique media BFT chooses one; only that verified decision can be anchored. Later reuse/stale-parent/duplicate original fails. PASS is not two mint permissions. |
| Competing sessions for same original | Original/submission lock rejects an overlapping session, even with a new SID or encoding. Retry retains identity, history and lifetime quota charge. |
| Journal checkpoint ahead of local media | INCOMPLETE_HISTORY for anchor-dependent validation until the exact required media ancestry is verified. No parent invention or skipping. |

PASS/FAIL are semantic closed-review outcomes only after independent quorum and
decisive rules. UNDECIDED means insufficient quorum/established participation or
zero decisive votes. INVALID means an incompatible/malformed/authentication or
transition claim. INCOMPLETE_HISTORY means required verified sources are absent.
CONFLICTING_FINALITY is a safety-failure latch, not ordinary fork choice. Lack
of progress, censorship and temporary unavailability describe system conditions;
they are not FAIL votes or approval. O's `UNRESOLVED` maps to model `UNDECIDED`;
this report does not assign a new production enum.

## 7. Evidence custody, retention and failure limits

For any three distinct authorized signers among four, at most one Byzantine means
at least two honest. To infer **two honest complete custodians at certification**,
each honest signer must first verify the entire batch and dependencies, durably
retain exact source bytes and authentication/ancestry, atomically bind the
attestation to the value, and have enforceable retention/serving obligations.
No third-party URL, digest, prefetch promise or signature-before-store satisfies
that premise. A q proof can be valid as cryptographic evidence of signing while
still insufficient as application/evidence authority for a missing-data verifier.

The custody model enumerates all **4 q-subsets** and **20 subsets of subsequent
honest-custodian permanent losses**. All start with >=2 honest custodians under
the premise; some end with zero recoverable sources. Honest crash with intact
disk can be temporary unavailability; two independently durable copies may both
be offline. Permanent disk loss/corruption can erase them, selective withholding
can block one recovering node, pruning/retirement can remove future sources, and
independent archive failure can defeat extra replication. Corrupt content is
rejected by commitment; absence remains incomplete. The scenario table is a
failure-set model, not measurement of correlated-failure probabilities.

| Retention policy | What can be guaranteed conditionally / what cannot |
| --- | --- |
| A. Validators retain full evidence indefinitely | Simplest full replay/custody obligation. At certification q-f honest full copies under the premise. No guarantee against later disk loss, outages, retirement or cumulative compromise. Infinite obligations need repair/capacity planning. |
| B. Validator retention plus independent archives | Recommended starting direction: full validator retention, at least two separately operated/failure-domain archives, content verification, regular inventories, restore drills and repair. This lowers modeled single-domain dependency; it proves no perpetual online availability and creates no new consensus authority. |
| C. Certified versioned handoff/checkpoint archive | Potential later pruning path only after separately approved versioned source manifests, authenticated custody acknowledgements for fully retrieved/verified data, overlap before deletion, repair/retirement rules and independent trust/snapshot semantics. A signed handoff is a past custody assertion, not a future availability proof. |

Retain failed, unsure, rejected-authenticated and conflicting sources where replay
depends on them, plus OPEN originals/rights/technical inputs, all journal proofs,
anchors and media proof dependencies. Negative votes receive the same retention
as positive votes. Transient invalid network garbage need not become immutable
history. An 8 KiB media reference cannot preserve or prove availability of its
external evidence. New nodes need a complete authenticated dependency inventory,
full replay or an independently approved checkpoint trust model; equal media tips
do not prove equal journal history. Snapshots/certified handoff remain unimplemented.

## 8. Measured serialization versus projections

[workload.py](../verification/review717p/workload.py) reconstructs O's literal
structural example using compact sorted-key ASCII JSON. Tests pin the prior
independently authored payload hash, not a hash regenerated to match output.

| Item | Finding |
| --- | --- |
| Example user payload | **1,507 bytes**, SHA256 `69213dedf3d2aed70609d6ca5ac093bb40a4d475f79662405d174b90e8b87740` |
| Example signed wrapper | **1,701 bytes**; synthetic invalid key/signature placeholders, not a verified signed vote or exact schema maximum |
| Example VOTE event | **1,743 bytes**, using O's `{kind,payload:{signed_vote}}`; allow one further byte for array separator |
| Proposed payload / signed-vote caps | 2,048 /4,096 bytes; unapproved limits, not measured maxima of a frozen profile |
| Proposed VOTE-event cap | 8,192 bytes; sensitivity assumption |
| Proposed journal batch cap | **262,144 bytes** (256 KiB), not a measured valid maximum body |
| Proposed media binding cap | **8,192 bytes**; complete schema is not frozen/measured, no exact maximum fit claim |
| Existing media-block maximum | **3,145,728 bytes** unchanged. At maximal base64 2,796,204 bytes, reserving binding 8,192 and native 98,304 leaves 243,028 bytes for every other field/key/source. This arithmetic does not prove combined-schema fit. |

The example's Wallet/key/signature and policy/G values have no authority.
There is no new signature-verification benchmark, networking benchmark, disk
throughput benchmark or actual production byte profile in P. All throughput,
replication and storage figures below are **modeled projections**. Workloads count
signed dimension votes, so one person voting both dimensions produces two messages.

## 9. Workload, backlog and three-year resource cost

Primary planning profile: 256 KiB body, 33,792 bytes reserved (16 maximum closes
plus assumed 1 KiB header), 1,743-byte example event plus comma, 24-vote cap,
one commit every **5 seconds**, 1 KiB stored batch metadata and **4 KiB mean**
external proof. Empty ticks continue; 720/hour, 17,280/day. Six-hour outage in
backlog examples, constant arrivals after recovery, 365-day years, no transport
retries/index/backup/compression savings. Capacity is a ceiling before OPEN,
evidence, anchor, CPU, I/O or BFT delays, not a service promise.

```
byte_slots = floor((262144 - 33792)/(event_bytes + 1))
votes_per_batch = min(24, byte_slots)
capacity_votes_per_minute = votes_per_batch * 60 / cadence_seconds
required_batches_per_hour = ceil(arrival_votes_per_minute * 60 / votes_per_batch)
backlog_growth_per_hour = max(0, arrival - capacity) * 60
clear_minutes = outage_backlog / (capacity - ongoing_arrival), only if capacity > arrival
```

Raw 1,701-byte wrappers alone fit at most 154/body; wrapped events without any
reserve fit 150; with the stated reserve, **130 byte slots**. The active planning
count limit still makes **24 votes/full batch**. At the 8 KiB event allowance,
27 byte slots remain, also limited to 24. Actual other event load can reduce this.

| Votes/min | Required batches/s | Required journal blocks/hour | Available/hour | Backlog growth/hour | Six-hour backlog | Clear with ongoing arrivals |
| ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 10 | 0.006944 | 25 | 720 | 0 | 3,600 | 12.95 min |
| 100 | 0.069444 | 250 | 720 | 0 | 36,000 | 191.49 min |
| 1,000 | 0.694444 | 2,500 | 720 | 42,720 | 360,000 | Never at this rate |
| 10,000 | 6.944444 | 25,000 | 720 | 582,720 | 3,600,000 | Never at this rate |

The required rows are full-batch equivalents; idle policy still generates all
720 ticks/hour. A drained network queue is not a guarantee of admission to its
original session: sessions may reach K first. A 10,000-message burst over a
100/min baseline needs **53.19 minutes** to drain at 288/min. One session's whole
255-interior-height window has at most **6,120 messages** at 24/batch, so at least
3,880 of that same-session burst cannot fit, even with sole use of every slot.
Competition, late arrival or an already-aged session worsens this bound.

At 1-second commits count capacity is **1,440/min**; at 10 seconds it is **144/min**.
The calculator retains all four workloads at each cadence. Faster commits shorten
the same W's nominal window to 4m16s and multiply proof/metadata and BFT traffic;
at ten seconds it is 42m40s, with lower throughput. Five seconds gives nominal
21m20s, subject to arbitrary stalls and unapproved pacing. No interval is assumed
to be enforced by current consensus.

Removing the 24-vote cap only as a sensitivity experiment gives 130 example votes
per five-second batch, **1,560/min**. At 1,000/min a six-hour backlog then needs
642.86 minutes to drain; W still limits session eligibility. At maximum 8 KiB
events, byte capacity is only 27/batch or **324/min**. Removing the count cap
therefore does not make 10,000/min feasible or approve higher resource limits.

Concurrent sessions share the same finite slots. 1,000 OPENs require at least
63 batches at 16/batch. 1,000 sessions with 100 two-dimension reviewers require
200,000 messages and at least 8,334 full voting batches, about 11.58 hours at five
seconds before OPEN/CLOSE/anchor overhead. They cannot all complete inside one
256-height review window. Large negative/unsure volume has the same signature,
quota, storage and scheduling costs; no favorable-choice filtering is allowed.
All-unsure consumes participation and closes UNDECIDED.

Decimal GB/TB below; exact byte fields are in results. Vote demand is offered
volume at 1,701 bytes each. The last two rows exceed admission capacity and are
**storage demand scenarios, not achievable admitted histories** at five seconds.

| Votes/min | Vote GB/day | Vote GB/year | Vote TB/3 years | Events + 1 KiB metadata + 4 KiB proof TB/3 years/node | Four validator copies TB/3 years |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 10 | 0.0244944 | 8.940456 | 0.026821368 | 0.124377984 | 0.497511936 |
| 100 | 0.244944 | 89.40456 | 0.268213680 | 0.371872512 | 1.487490048 |
| 1,000 (overload) | 2.44944 | 894.0456 | 2.682136800 | 2.846817792 | 11.387271168 |
| 10,000 (overload) | 24.4944 | 8,940.456 | 26.821368000 | 27.596270592 | 110.385082368 |

Baseline metadata+mean-proofs alone cost **88,473,600 bytes/day** and
**96,878,592,000 bytes/three years** per archive, even with no votes. Event/archive
daily/year/three-year fields are all retained in the calculator results. Constant
full 256 KiB bodies plus 16 KiB cap proofs every five seconds would be
**5,270,195,404,800 bytes/three years per archive**; do not add the contained votes
again. At cap-sized 4 KiB votes and 8 KiB events, the 1,000/min offered scenario
needs 6.459 TB vote-only or 13.016 TB events+baseline per archive in three years,
and remains infeasible at the retained count/cadence profile.

| Votes/min | Ideal dissemination to three additional validators/day | Payload replication bytes/s aggregate | Signature checks/s/node | Across four validators |
| ---: | ---: | ---: | ---: | ---: |
| 10 | 73,483,200 | 850.5 | 0.1667 | 0.6667 |
| 100 | 734,832,000 | 8,505 | 1.6667 | 6.6667 |
| 1,000 | 7,348,320,000 | 85,050 | 16.6667 | 66.6667 |
| 10,000 | 73,483,200,000 | 850,500 | 166.6667 | 666.6667 |

Those lower-bound payload bytes are **3*m*b**, not four transmissions per vote;
gossip/proposal replication can overlap. Do not add them as two measured copies
without a topology/cache model. O's separate BFT planning allowance of 24 KiB
per batch for two all-to-all phases adds **424,673,280 bytes/day aggregate** at
five seconds, before proposals/retries/transport/archives. New-node replay may
verify retained votes again; invalid inputs add bounded but unbenchmarked work.
At 100 checks/s, the 1,000/min three-year offered 1.5768 billion signatures alone
would take 182.5 days on one verifier; this is an assumed rate, not a measurement.
At 100 Mbit/s the 2.682 TB vote-only bytes take at least 2.48 days to transfer,
before proofs, originals, indexes, network overhead and signature replay.

Archives also need original media for **all OPENs**, including failed/unresolved
reviews, rights/technical sources, conflict evidence, media/Q4, repair/backup and
headroom. As a separate independent assumption, 1,000 OPENs/day at 2 MiB original
cap require **2,296,381,440,000 bytes/three years**. Full 3 MiB canonical media at
1,000 accepted/day requires **3,444,572,160,000 bytes**. These are separate workload
examples; shared content-addressed originals should not be charged twice when
embedded in accepted media. Every full independent archive multiplies retained
evidence cost; two archives add two copies beyond four validators. For 100/min
the six-copy event+baseline illustration is **2.231235072 TB**, before all those
other sources. No dollar price, procurement claim or economic/reward change is
inferred; target-host CPU/I/O/recovery and service-cost measurements remain gates.

## 10. Quota, establishment and idle-history consequences

Candidate participation authority is first **finalized VOTE admission**, not
gossip, receipt, intermediate tally, CLOSE success or media issuance. One
`(Wallet,submission)` permanent charge is shared across dimensions and allowed
retry, retaining its original epoch; new submission requires a free 5/25 slot.
The model checks last-slot races, exact/semantic duplicates, failed and undecided
closures, retry delay/limit/identity, and no refunds. An existing charge permits
the other dimension without charging again, but does not waive context, snapshot
eligibility, current penalty or closing rules.

OPEN freezes base qualification/status. Promotion after OPEN cannot manufacture
an established seat in that session. Penalties ordered before a later vote can
block it; earlier admitted status/choices remain counted. Penalty after CLOSE
cannot rewrite review outcome. The model treats objectively proved status and
penalty transitions as oracle inputs; it does not verify a new offense grammar.

Preserved current parameters: media epoch `floor(anchored_media_height/5)`,
probation cap 5, established cap 25, promotion after >=10 distinct probation
participations and >=3 media epochs, plus underlying earned age/creator/native
qualification and existing penalty schedules. Admitting votes on failed/unsure
submissions as probation credit is a **proposed accounting amendment**, with
easy-work farming implications. No payment or vote-correctness reward is added.

Selected runs exhaust both numeric caps, continue journal ticks/closure without
media, and retain the exhausted media epoch. A six-media execution verifies the
fifth media anchor advances E and the sixth submission charges epoch1 without
erasing epoch0 sources. Ten thousand ticks or months of wall time with no media
would still have E unchanged: this follows from the transition rule, not a
simulation of months or an authenticated clock. Penalty expiry and minimum
probation age likewise stall. Starting with too few established reviewers can
still prevent the first media, regardless of available journal throughput.

A quota epoch amendment is **necessary if the owner requires continued new
participation during indefinitely idle media history**. It is not necessary for
agreement safety if the owner accepts that halt behavior. Journal-height epochs
avoid media dependency but let rapid ticks accelerate quotas/promotion/penalty
expiry unless a reviewed opportunity/pacing rule constrains them. An independently
authenticated epoch counter has its own authority, liveness, abuse and G2 policy
requirements. Neither is silently approved here; no quota amounts, economic
rewards or earned thresholds change.

## 11. Media-chain cross-reference, versioning and recovery

The candidate integration must enforce this acyclic dependency order:

```text
G-independent approved policies/manifest/bootstrap/descriptors -> G
G -> J0 -> prior journal + verified anchored media F
-> creator OPEN + frozen eligibility -> admitted signed votes
-> mandatory CLOSE -> finalized JK and proof -> complete evidence manifest
-> media review binding + exact immediate parent F + full media hash
-> media finality proof -> strictly later journal MEDIA_ANCHOR -> next OPEN/media
```

The media validator must obtain and authenticate the complete journal path through
CLOSE, replay it against the exact trusted G/profile, recompute both complete
vote sets/tallies and quota/eligibility causes, and compare the entire binding.
An inclusion proof of one vote, a 70% summary, a root, EM digest or 8 KiB reference
does not prove completeness, ordered closure or availability. If a Merkle scheme
is later chosen, it needs leaf/domain/order/count/tree rules and source inventory;
no Merkle implementation or succinct completeness proof is supplied by P.

Full checkpoint design must bind stream/profile/version/N/G/C/epoch, journal h,
round and finalized value/parent, exact state/closure commitment and proof/source
inventory. This is a **field requirement, not a frozen encoding**. A snapshot is
derived state and must replay to an authenticated target unless a separately
approved trust policy explicitly replaces replay. Restarts retain verified
cursors, check byte commitments, and fetch missing journal/media dependencies in
DAG order. An older offered checkpoint cannot roll back retained state; an
authenticated conflicting checkpoint at retained height is a safety alarm/halt,
not a score-based branch switch. Discovery of the globally latest tip is not
proved by possession of any valid checkpoint.

The journal advances a single media anchor by one only after full media bytes,
proof, immediate ancestry and review/native/technical/rights checks. Next media
height must wait for the previous media's authenticated journal anchor; OPEN
uses the latest anchored parent. Journal media anchors strictly follow their
referenced CLOSE; a batch cannot mix new OPEN with anchor advancement. Source
replay is idempotent; a fresh duplicate anchor is invalid. Separate stream commits
are not an atomic distributed transaction: crash in anchor lag causes recovery
work, never media rollback or invention of an anchor.

Two originals can pass against F and compete for media F+1. Only one can finalize;
the other's old-parent pass remains historical but unusable after the anchor
advances. No automatic reparenting or second settlement. This conservative O
coupling serializes usable media throughput and can strand expensive concurrent
review work. A more permissive parent-independent review/rebasing design would
require a separately reviewed eligibility/quota/rights/duplicate-admission
contract. P does not hide this cost or start that redesign.

G2 must commit the new journal agreement/policies and version registry without
G/A/policy/self-hash cycles. Existing M's incomplete-policy envelope cannot be
reused as proof of these semantics. Journal proposal, prevote, precommit, nil,
commit proofs, receipt, OPEN, vote, evidence and media bindings all require exact
new signing/serialization vectors and domains. Even shared keys need fenced,
separate durable height/round/phase/lock/valid/reservation/outbox namespaces;
media signatures cannot be relabeled as journal signatures or vice versa.

The eventual canonical media preimage must include the binding under an approved
new version. Existing v1/v3 hashes and frozen vectors stay unchanged. Full combined
media format, per-field caps, simultaneous-max fit, journal proofs outside media,
G2 source semantics and release pinning remain approval/implementation gates.
Neither root hashing nor this report adds an active consensus field.

## 12. Negative controls and preserved counterexamples

[negative-control-traces.json](../verification/review717p/negative-control-traces.json)
and the same entries in results retain inputs, expected behavior, weakened output
and detection status. All **8/8** deliberately unsafe controls are detected:

| Weakened variant | Concrete counterexample |
| --- | --- |
| Node-local cutoff | Positive delivered to A/B, negative only to B; local counts [1,2] instead of [2,2] for the common committed set. |
| Count unfinalized gossip | One received message, no finalized position: unsafe 1 vs authoritative 0. |
| Producer selects positive votes | Finalize 5 positive +3 negative: full 62.5% FAIL becomes false PASS after dropping negatives. |
| Duplicate inflation | One admitted reviewer relayed five times: unsafe count5 vs1. |
| Missing evidence accepted | Certificate with deleted VOTE body: unsafe PASS vs INCOMPLETE_HISTORY. |
| Receipt treated as admission | Custody receipt but no ordered VOTE before close: unsafe count1 vs0. |
| Omit CLOSE | OPEN1/K4, ticks2/3, blank4: unsafe advances with open session; safe reducer rejects. |
| Unauthenticated checkpoint substitution | Foreign unauthenticated proof coerced into local context/authentication flags: unsafe advances; safe reducer rejects original input. |

The local/gossip/subset/duplicate/receipt controls are deliberately wrong tally or
authority adapters evaluated on concrete traces. Missing-evidence control skips
the source guard; omission bypasses closure; substitution overwrites trusted
context/authentication facts. They are **not consensus fork counterexamples**
against the trusted unique-prefix abstraction. Correct variants reject or preserve
the expected result. H's separate lock-loss counterexamples remain historical H
tests, not new verification of journal agreement in P.

## 13. Tests, regression and verification record

Focused suite: **80 passed in 10.53 seconds**, no failures/errors/skips. It reproduces
all retained searches/results and tests additional context, proof, source deletion,
corruption, mandatory-close mutation, retry, quota epoch, duplicate settlement,
stale-parent, checkpoint rollback/conflict and nonactivation boundaries. Ten
manual tally fixtures independently agree with rational arithmetic: exactly70,
below70, unsure/no-votes, five votes, missing established, insufficient quorum,
one decisive positive, negative majority and unsure denominator. Duplicate and
conflicting reviewer signatures are symbolic source scenarios, not new crypto
vectors. All-unsure is always UNDECIDED.

Historical regression: **770 passed in 118.11 seconds**, no failures/errors/skips.
The combined final selection is **850 passed**. Results and exact executed test inventory are recorded in
[validation.json](../verification/review717p/validation.json). The selected existing
J/K/M/H, finality durability, canonical v3, dual review, earned eligibility and
v1/native/genesis/block/finality tests preserve their original assertions. No
whole-repository, live-node, multi-host, cross-platform, real network or physical
power-loss result is claimed. Existing regression harnesses may create their
unchanged disposable test keys/stores in ignored temp paths; no production keys
or stores are created. Earlier focused runs preceded the final retry, fixed-window,
typed-signer and source-ownership tests; only the final80 distinct cases count.

The first checker invocation exposed a fixture-construction KeyError for a
deliberately foreign dimension; supplying its explicit test choice fixed the
fixture without weakening the reducer. Review also made the window an explicit
fixed policy input, preventing proposers from concentrating different-window
OPENs at one closing height, and made finalized state own deep copies of its
source objects so later edits to experiment inputs cannot rewrite history.
Model/scenario output was then generated
and reproduced. Validation records source hashes and initial branch/HEAD; retained
results omit timing to keep replay deterministic. Recreate the validation inventory after tests with:

```powershell
.\.venv\Scripts\python.exe -B -m verification.review717p.audit --junit temp/task717p-focused-release.xml --junit temp/task717p-regression.xml
```

The historical regression command selects the existing 17 modules listed by
class name in validation.json: G2, authority, signer, Tendermint, finality
durability, canonical v3, dual review, earned eligibility, and the retained
v1/golden/freeze/native/genesis/block/quorum/public-finality/lifecycle suites.
Use a fresh workspace basetemp and point TEMP/TMP to an ignored workspace runtime
directory, as in M's documented regression recipe; no host-default temp access
is required. `git diff --check`, scoped Git
inspection and local documentation/link checks complete delivery verification.

## 14. Owner decisions and exact remaining gates

These are recommendations for approval, not decisions made by P:

| Owner choice | Recommendation and remaining blocker |
| --- | --- |
| 1. Separate BFT journal | Prefer one globally ordered, separately finalized review journal for pre-media admission/failed/no-media history. Approve architecture and complete review of its application/consensus refinement first. |
| 2. One or two histories | Treat journal and media as separately authenticated ledgers in one application DAG. A single interleaved ledger requires a separately approved control-record alternative. |
| 3. Idle progress | Permit bounded empty journal ticks with mandatory closures and explicit pacing/resource/operating budget. This authorizes no currency reward or media block on a tick. |
| 4. Opportunity/cutoff | Specify minimum human review opportunity and censorship expectations. Keep +256 provisional; height-only cutoff is deterministic but lacks a real-time opportunity guarantee. |
| 5. Closure enforcement | Mandatory derived close prefix/state transition at K, close-first order and OPEN-time capacity reservation. Reject voluntary/omittable closure. |
| 6. Receipts | Ordinary receipts attest custody only; only finalized ordered ADMIT charges/counts. Any stronger inclusion receipt needs a separate freeze/reconciliation protocol. |
| 7. Archive policy | Full validator evidence plus independently operated replicas, regular verified repair/recovery and no pruning until an approved versioned handoff/checkpoint policy exists. Approve retention duties/budgets and failure assumptions. |
| 8. Quota/participation | Approve ADMIT-time lifetime submission charge, shared dimensions/retry and failed/unsure credit semantics. Decide whether to accept idle-media exhaustion or amend the authenticated epoch policy; preserve 5/25 pending approval. |
| 9. Signing/G2/schema | Freeze complete independent stream identities/descriptors, closed bytes/domains/version dispatch, custody/fencing, policy sources, OPEN time/rights reconciliation, full media binding/preimage and independent vectors. J's supported boundary does not suffice. |
| 10. Launch resource expectations | Use 10–100 signed votes/min as planning workloads for measurement under the retained five-second/24-vote ceiling; this is no launch SLA. 1,000–10,000/min needs an approved count/cadence/window/byte/CPU/storage redesign or explicit admission backpressure. Benchmark targets and retention before any launch commitment. |

Additional blockers include static validator/operator/bootstrap approval, full
earned eligibility/objective offense schemas and source inventory, production BFT
engine route/refinement, enforceable nonrollbackable signer custody, independent
protocol/crypto/model review, real independent-node source-only replay, complete
availability/archive recovery, combined-schema fit, and explicit activation/state
disposition authority. Missing launch keys alone does not prevent further inert
verification; the missing approved semantics and implementation evidence do.

**Smallest subsequent task:** a narrowly scoped owner decision/specification pass
to settle idle epoch and minimum opportunity policy together with conservative
cross-parent session lifecycle, then freeze the G-independent two-stream agreement
and checkpoint/evidence/signing contracts. Only after those decisions should a
separately authorized isolated canonical-byte/crypto-vector and independent replay
task begin. Do not start production networking or expand J's signer as the next
step merely because this application model passes.

**Task 7.17P is ready for review and a later authorized commit** as a bounded
verification/feasibility artifact. Production journal implementation, production
consensus integration and reviewer-history Task 7.17 remain **BLOCKED**. This task
approves none of the proposed protocol, quota, resource or launch parameters.
