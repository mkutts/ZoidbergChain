# Milestone 7 Task 7.17H — Executable Tendermint model verification

Date: 2026-10-24, America/New_York. **Isolated bounded verification only.**

The executable reference model passes the retained bounded searches and selected
adversarial schedules with provisional **N=4, f=1, q=3**. Removing its lock guard
or deliberately forgetting private safety state produces conflicting decisions.
This is a model-level result, not a proof of unbounded agreement, a future
implementation, real cryptography, durable signing, or release readiness.

Implementation **design/specification** can proceed against this precise
contract in a separately authorized task. Production consensus implementation
remains gated on owner decisions, complete frozen schemas, independent model
review and implementation-route review. Reviewer-history Task 7.17 remains
**BLOCKED**. Nothing is activated, deployed, committed, pushed or merged here.

## 1. Repository verification and isolation

| Initial check | Result |
| --- | --- |
| Branch | `Compression-State-Bloat-and-Node-Economics`, expected |
| HEAD | `c9be176dc09ebf4ab1c76b73e1df4bb7c3318493` |
| Worktree/index | Clean, including untracked files |
| Separate 7.17G commit | HEAD, `Milestone 7 Task 7.17G: select reference BFT finality protocol`; two documentation files |
| Separate 7.17F/E commits | `56110fd` / `82f8a49`; specifications and current durability tests present |
| Applicable AGENTS.md | None found in repository or applicable ancestors; no delegation |
| Formal checker availability | No `java`, `tlc` or `apalache` command available; no TLC jar found in the inspected Codex tree. No tooling installed. |

Read the [7.17G protocol decision](milestone-7-distributed-finality-protocol-decision.md),
[7.17F authority/quorum decision](milestone-7-validator-authority-and-quorum-decision.md),
[7.17D remediation decision](milestone-7-finality-safety-and-remediation-decision.md)
and [7.17E durability report](milestone-7-finality-durability-implementation.md).
Historical defect descriptions in D are superseded by E where specified.

Inspected `services/finality_service.py`, `protocol_v1_finality.py` and
`canonical_v3/{block,media,construction,admission,finality}.py` at their validation
and persistence boundaries. The current one-phase tally is not this model's
agreement engine. No production signer exists to certify through this exercise.
All executable additions are under [verification/tendermint717h](../verification/tendermint717h/)
and one new model test file. They import no production node, codec or signer.
Existing sources, diagnostics, schemas and vectors are untouched. Regression
tests use disposable test databases/accounts; no operational keys are created.

Final branch/HEAD equal the initial values. The index remains unchanged. Final
changes are exclusively new, unstaged files: this document; the model package's
`__init__.py`, `model.py`, `scenarios.py`, `check.py`, `replay.py`; its `results/`
JSON evidence; and
[`tests/test_milestone_7_task_7_17h_tendermint_model.py`](../tests/test_milestone_7_task_7_17h_tendermint_model.py).
Disposable pytest/reproduction outputs are ignored under `temp/task717h-*`.

## 2. Exact reference and assumptions

Primary reference: Buchman, Kwon, Milosevic,
[_The latest gossip on BFT consensus_, arXiv:1807.04938v3](https://arxiv.org/pdf/1807.04938v3),
Algorithm 1, printed page 6, lines 1–67. The pinned v3 PDF, rather than a
different Tendermint/CometBFT variant, supplies the transition rules.
Section II-A and Section III supply authenticated sender identity, common
membership/voting power, `n=3f+1`, at most f faulty power, injective value IDs,
local message logs containing sent and received messages, and atomic upon rules.
When several guards hold, their order is arbitrary (page 5, footnote 7).

Safety does not require prompt delivery. The paper's termination argument also
requires eventual synchrony with unknown GST and finite delivery bound Delta,
including redistribution of messages already sent or received by correct nodes,
clocks, increasing per-round waits, fair processing/proposer opportunities and
available valid input. Unit power and static membership specialize the paper's
weighted setting. Application determinism, media availability, crash refinement,
genesis authority and real signature unforgeability are additional obligations.

The model uses genesis-anchored height 1 for the paper's first height-0 instance.
`proposer(h,r)=(h-1+r) mod 4` follows 7.17G's equal-power schedule. IDs 0/1/2/3
stand for four distinct registered authorities; 3 is Byzantine in the primary
searches. No test enumerates every placement of a faulty authority. Proposer
crash/ordinary outage schedules instead use four honest identities.

### Reference-to-model traceability

All numbers in this table are **Algorithm 1 printed line numbers**. Corresponding
`L...` action labels and comments occur in [model.py](../verification/tendermint717h/model.py).

| Paper lines | Executable correspondence |
| --- | --- |
| 1–10 | `Node`, `Model.initial`, `L10/start`: empty decisions/log, propose, round 0, nil lock/valid values, lock/valid rounds -1 |
| 11–21 | `Model.start`: set round/propose; proposer chooses retained validValue or a valid getValue candidate and broadcasts its validRound; only the non-proposer branch arms propose timeout |
| 22–27 | `L22/prevote`: fresh proposal requires validity and either no lock or identical locked value; rejection signs nil; move once to prevote |
| 28–33 | `L28/prevote`: actual q prevotes for the proposed ID at vr, `0<=vr<r`, then the exact `lockedRound<=vr OR lockedValue=v` predicate |
| 34–35 | `L34/arm`: q distinct senders' current-round prevotes, any values; arm prevote wait only once while prevote |
| 36–43 | `L36/polka`: proposal plus current q same-value prevotes and valid data; in prevote atomically lock then emit precommit and change phase; in either prevote/precommit learn validValue/validRound once |
| 44–46 | `L44/nil`: q nil prevotes while prevote yield nil precommit and precommit phase, with lock retained |
| 47–48 | `L47/arm`: q distinct current-round precommit senders, any values, arm precommit wait once, independent of phase |
| 49–51 | `L49/decide`: matching scheduled signed proposal plus q same-round value precommits, complete locally valid value; any round at current height is eligible |
| 52–54 | Same atomic decision action records proof and parent, advances height, clears log/once flags and lock/valid variables, starts round 0; the configured terminal boundary stops further-height processing |
| 55–56 | `L55/catchup`: f+1 distinct senders at one common higher round, across message kinds; StartRound preserves locks/valid values |
| 57–60 | `L57/timeout`: armed current-height/current-round propose timeout while propose emits nil prevote |
| 61–64 | `L61/timeout`: armed current-height/current-round prevote timeout while prevote emits nil precommit |
| 65–67 | `L65/timeout`: armed current-height/current-round precommit timeout starts next round; no timeout changes a lock |
| Section III / page 7 | Symbolic injective `Block.id`, separate proposal versus vote IDs, sender-set weight, sent-and-received log |
| Section II-A / III | `authenticated`, `relevant`, arbitrary `successors` ordering, explicit delivery, immutable atomic state replacement |

No 7.17G lock/valid-round guard contradicting Algorithm 1 was found. Two source
details must stay visible: the informal page-8 discussion uses a strict `>` when
describing newer justification, whereas line 29 prints `<=`; the executable
model follows **line 29**, including equality. The prose describes a general
propose wait, whereas line 21 schedules it in StartRound's non-proposer branch;
the model follows **line 21**. Tests cover equality, late learning and the timer
guards. These are recorded source discrepancies, not new unlock rules.

7.17G's signed network/genesis/membership/profile/epoch/parent admission, proposal
grammar, complete-media check and finalized-parent restriction are application
adapters. The paper does not specify their bytes. The model filters malformed
context before reference processing and holds incomplete data pending; it does
not claim to validate 7.17G's proposed JSON/EIP-191/Q4 wire formats. Proposal
valid-round proofs are actual logged prevotes; a claimed integer never suffices.
Nil never clears a lock. Only the current-round line-36 transition replaces it;
successful height advancement resets it.

## 3. State, inputs, scheduling and abstraction boundaries

`World` comprises immutable honest `Node` records and the set of ever-released
symbolic messages. Node state is identity, height, round, phase, startup flag,
lock/value round, valid/value round, local log, armed `(h,r,kind)` timers,
once-only markers, locally available data and an ordered decision/proof history.
The last verified decision determines the finalized parent. `Decision` retains
the complete proposal and precommit set used to decide. Log messages are also
the backing evidence for validValue/validRound; the checker verifies that fact.

`Block` has an injective ID, height, parent, and deterministic Boolean facts for
protocol/network/genesis conformity, canonical record, original-media commitment,
admission certificate, transaction signatures and resource limits. Membership is
the fixed `range(4)`. Authentication is a symbolic unforgeability assumption,
not ECDSA or a trusted-roster discovery implementation. `CONTEXT` binds abstract
network, genesis, membership, policy, epoch and message version. Different kinds
represent signed purpose/step separation. Byzantine messages cannot write an
honest local state or generate authentic honest messages through `successors`.

Initial state has all configured full data except explicitly missing `(node,ID)`
pairs. Honest getValue branches over available valid candidates; it must reuse
validValue when set. With no valid available input, the environment cannot
fulfill getValue: the model records a quiescent proposer without fabricating a
block or adding a proposer timer. This is outside the paper's valid-input
termination premise and is labeled as such in the no-input schedules.

Each reference rule is one enabled transition; enabling another rule never runs
it automatically. Sending appends to the global released set and own log in the
same atomic transition. Delivery may select **any** previously released message
for **any** online honest recipient at the relevant height/parent, in any order.
Withholding is indefinite non-delivery. Global retained messages abstract gossip,
including eventual availability of old-height decisions after another node has
advanced; future-height messages can be delivered when the recipient catches up.
Clearing a node's log does not delete the network's archived messages.

Exact deliveries deduplicate into a set. Different Byzantine values coexist as
evidence; quorum and wildcard counts always use distinct sender identities.
An equivocator can count once for X and once for Y in separate predicates, but
never twice in either predicate or an any-value/future-round threshold. The
model does not exclude a static member after observing equivocation.
Duplicate delivery, rejected authentication and intact restart are exact state
stutters; BFS omits these loops. Scenario traces retain some duplicate/self
deliveries to exercise the identity behavior explicitly.

The finite adversary alphabet enumerates proposals when identity 3 is scheduled,
all catalog values at the target height, valid-round claims -1..r-1, and
prevote/precommit X/Y/nil independently in every bounded round and current
honest parent context. Arbitrary subsets can be released, delayed, split or
gossiped. Withholding needs no explicit transition. Invalid catalog values are
included in the invalid-proposer schedule. Unauthorized identities, wrong
contexts and conflicting parents are additional receiver-guard tests, not an
exhaustive malicious-byte parser search. Arbitrary payloads outside this alphabet,
weighted/dynamic membership, arbitrary heights/rounds and real hash collisions
are outside the search claim.

Timers abstract enabled expiration, without a physical clock, Delta, GST or
numeric deadlines. Safety exploration permits arbitrary ordering of expirations
and upon rules after arming; stale expirations are stutters. It imposes no
fairness. Controlled progress schedules instead drain permitted messages and
rules before allowing waits to expire. No timeout bound or duration is proved.

## 4. Safety properties and independent checks

The retained correct-model runs check all enabled edges they generate and the
decision/history invariants of resulting states. Guard tests additionally target
authentication, counting, availability, evidence and timing. The checker's tests
deliberately corrupt proofs/decisions and confirm errors are detected.

| ID | Checked property | Classification / executable evidence |
| --- | --- | --- |
| A | No different honest decisions at one height | Paper agreement property; `invariant_errors` compares all retained node decisions |
| B | Every decided value satisfies stable deterministic valid() | Paper validity property, with application's abstract predicate; decision checker and each invalid component test |
| C | No honest conflicting proposal/prevote/precommit within an h/r/kind slot | Reference phase/sender discipline; global released history, including signatures whose local logs were cleared |
| D | Consecutive decisions and every next-height signature extend an actually finalized parent | ZoidbergChain adapter; decision sequence and signature-parent checks, two-height schedule and wrong-parent tests |
| E | Only authentic static members in the exact context count | Paper authentication premise plus application genesis/profile binding; receiver filtering and retained-proof verification |
| F | A QC alone cannot decide unknown/unavailable contents | Reference requires proposal and valid(v); application requires complete media/evidence; reachable missing-proposal/data schedule plus decoder tests |
| G | Nil and timers cannot authorize an incompatible unlock | Exact reference state preservation; edge checker disallows any same-height lock change except L36; nil/timeout and intact restart traces |
| H | Duplicates/equivocation do not inflate q | Sender-set counting, retained-proof unique sender check, duplicate/contradictory-message tests |

Auxiliary checks require validValue's supporting proposal/prevotes and atomic
lock update before a non-nil precommit appears. Cross-round votes for different
values can be **legal** when justified; C does not invent sign-once-per-height,
or prohibit nil prevote followed by a legitimate value precommit. Tests use
synthetic local fixtures for isolated unreachable guard cases; only replayed
scenario prefixes are used as reachable BFS seeds.

## 5. Search method, bounds and retained results

[check.py](../verification/tendermint717h/check.py) uses deterministic breadth-first
enumeration of the executable transition system with exact immutable-state
deduplication. It is neither TLC/TLA+ nor Apalache, SMT verification, an
inductiveness proof or an independently authored second implementation.
There is no partial-order/symmetry reduction, automatic rule priority, sleep-set
pruning or weakened lock predicate in the correct model. Stutter removal is
explained above. Python 3.13.5 and the standard library suffice for the checker.

The default BFS bound is **four additional transitions per seed**, **50,000
retained states per search**. Depth counts individual send/delivery/atomic-rule
events; it is not four complete protocol rounds. Seeds are initial state or
reachable replayed prefixes of 20–102 events. Each retained seed JSON includes
the exact full state, configuration, prefix actions and SHA-256 digests. The
longer complete schedules exercise decisions and multiple rounds that a shallow
initial-state BFS alone would not reach.

| Search seed | Height ceiling | Inclusive round ceiling | Retained states | Generated edges checked | Depth completed? |
| --- | ---: | ---: | ---: | ---: | --- |
| Initial state | 1 | 1 | 9,322 | 27,710 | Yes, 4 |
| Hidden X decision | 1 | 2 | 30,004 | 103,011 | Yes, 4 |
| Different honest locks | 1 | 3 | 50,000 | 132,289 | No, state cap |
| Justified proposal ready | 1 | 3 | 50,000 | 134,364 | No, state cap |
| Byzantine proposer round 3 | 1 | 4 | 50,000 | 132,888 | No, state cap |
| Old-round commit after advancement | 1 | 1 | 14,534 | 46,640 | Yes, 4 |

Total **203,860 retained states (sum across searches, with overlap)** and
**576,902 generated edges checked**, no correct-model invariant violation.
The retained checker run took **24.413189 s**; its 18 positive schedules recorded
845 transitions, with a further 150 transitions across the two negative controls.
State counts include seeds, exclude an unretained next state at a cap, and are
not globally distinct state counts. Edge counts include different enabled events
leading to the same successor. Capped searches explicitly report unexpanded
frontiers; they do not claim exhaustive coverage through depth four. Height 2
is covered by the separate consecutive-height execution, not these BFS bounds.
The exact runtimes, prefix lengths, frontier sizes, complete scenario metrics,
source hashes and limits are in [results/summary.json](../verification/tendermint717h/results/summary.json).
Wall time is environmental; state/edge counts and digests are deterministic.

The correct model is not weakened to finish. Caps are search cutoffs. Absence of
a counterexample within these prefixes/bounds is limited evidence, especially
for farther-round lock chains, larger value alphabets, other fault placements
and arbitrary cross-height schedules. Independent consensus review and stronger
exploration/induction remain implementation/release acceptance requirements.

## 6. Adversarial scenarios and negative controls

There are 18 retained positive schedules and two negative-control schedules.
Every action can be recomputed using [replay.py](../verification/tendermint717h/replay.py);
each event includes action, resulting digest, compact local state and invariant
errors. Negative executions require explicit replay opt-in.

| Requested scenario | Retained schedule or focused test and observation |
| --- | --- |
| 1. Competing proposals | `competing_proposals_byzantine_equivocation_reordering`: reach r3, faulty proposer sends X/Y, honest local views differ |
| 2. Byzantine equivocation | Same run sends contradictory prevotes and a competing precommit; q is unchanged |
| 3. One offline | `one_offline`: three correct online identities decide without the fourth |
| 4. Two offline | `two_offline_no_quorum`: no q3 and no decision |
| 5. Different delivery order | Local X/Y split, hidden commit and partial proof delivery; BFS enumerates alternate recipient/order choices |
| 6. Delayed precommits | `delayed_old_round_precommits`: node advances r0 to r1 before learning/deciding r0 proof |
| 7. Proposer crash | `proposer_crash_then_synchronous`: r0 proposer offline; armed nil waits allow honest r1 progress |
| 8. Different honest locks | `different_locks_valid_round_late_valid_learning`: A locks X@0, B locks Y@1; no X decision existed; later justify Y |
| 9. Valid-round proposal | Same run: missing old prevotes prevent acceptance; delivery enables line 28; prevote does not itself replace A's lock |
| 10. Invalid proposal | `invalid_byzantine_proposal_rejected`: actual faulty scheduled proposer offers BAD@3; all honest prevote nil |
| 11. Nil prevote/precommit | Hidden-commit and r3-prefix rounds retain locks; pure nil QC cannot decide |
| 12. Multiple round advances | Reach rounds 0–3 through actual quorum-triggered waits; bounded alphabet permits up to r5 in full schedules |
| 13. Late old-round messages | Old-round decision remains enabled; obsolete timer guard tests do not advance/sign |
| 14. Duplicate signatures | Symbolic same-authenticated-message retries are state stutters; equivocated sender counts once per predicate; real signature-byte variants are outside model scope |
| 15. Wrong network/membership | Parameterized sender/authentication/context mutations cannot enter counted logs; genesis, policy, epoch and message-version mismatches also covered |
| 16. Conflicting finalized parent | Wrong-parent messages reject; two-height signature/decision ancestry checker; tampered parent/proof tests are detected |
| 17. Intact restart | Hidden-commit execution includes identity transition on complete safety state; later conflicting proposal still yields nil. No physical crash durability is claimed |
| 18. Lost signer state | Explicit fault injection below exceeds honest-process premises; flagged immediately and later yields disagreement |

The invalid-media/no-input, incomplete-data, missing-admission-source,
decoder-unavailable, partition/healing and two-height schedules supplement these.
Permanent-partition/no-input executions are finite witnesses to lack of progress,
not infinite liveness counterproofs.

### Concrete counterexamples

Both negative traces start with real enabled reference transitions and keep
N4/q3 and one explicitly Byzantine identity D. A/B/D prevote X at r0. A/B lock
and precommit X; only A receives all A/B/D precommits and decides X. B has not
learned that decision. C remains uncommitted. Nil and timeout rounds then lead
to r2, where C's validValue is unset and C proposes fresh Y.

1. **Removed locking guard:** `broken_locking=True` bypasses the acceptance lock
   predicate in the deliberately wrong model. B accepts Y without justification;
   B/C/D form its prevote/precommit quorums and C decides Y at the same height.
   `A:honest_disagreement` is reported. Exact trace:
   [trace-removed_lock_check.json](../verification/tendermint717h/results/trace-removed_lock_check.json).
2. **Lost private state:** B forgets its lock **and** valid-value fields at the
   marked `FAULT/lost_signer_lock_and_valid/1` event, then follows the ordinary
   guards from that corrupt state. It helps C/D decide Y. The edge checker reports
   `G:unsupported_lock_change` at the injected fault and later A disagreement.
   [trace-lost_signer_state.json](../verification/tendermint717h/results/trace-lost_signer_state.json).

Each negative control has 75 recorded transitions. The correct run with intact
state retains B's X lock, prevotes nil for Y@2 and cannot form its quorum.
Neither negative trace is a counterexample to the paper: the first changes the
protocol; the second introduces another faulty signing identity besides D and
is explicitly **not** an honest execution with f<=1. Ordinary public chain/QC
recovery cannot prove that B's privately released old signatures never existed.

## 7. Safety versus liveness

Selected controlled eventually synchronous schedules demonstrate progress with
one Byzantine withholding, one ordinary offline validator, an offline initial
proposer, healed connectivity, different initial locks with later justified
proposals, and two sequential valid candidates/heights. `settle` delivers
released messages to connected correct recipients and drains enabled rules
before firing another armed timer; this is a concrete sufficient schedule.

No progress is asserted with permanent partition, two unavailable identities,
no valid media, required admission evidence unavailable, incomplete proposal data
or a required local decoder unavailable. One Byzantine withholding plus another
offline/blocked validator leaves fewer than q, even though only one is malicious.
No quorum reduction, membership rewrite or fabricated media is permitted.

A formal liveness proof would additionally require an unbounded fair transition
system with eventual reliable Delta-bounded gossip **of earlier received/sent
messages**, eventual CPU/storage/validation service, clocks with increasing waits
large enough for payload/proof delivery and processing, infinitely recurring
honest proposer opportunities, stable deterministic validity, and available valid
getValue input. It would need to show eventual acquisition/dissemination of a
compatible validValue/validRound and satisfaction of the good-round conditions,
then discharge the model-to-implementation refinement. The selected finite
schedules do not establish these conditions universally or prove termination.
No fixed latency, arbitrary-network liveness or per-submission inclusion claim.

## 8. Safety state extracted for a later durable signer

The model makes reference transitions and releases atomic. A production signer
must refine that abstraction across real crashes. This task creates no signer
store and does not test disk fencing, reservation transactions or power loss.

| Required boundary | State/dependency inventory and ordering obligation |
| --- | --- |
| Before any signing request | Pinned protocol/network/G/M/C/agreement policy/epoch and full key identity; exclusive fenced signing ownership, non-rollback safety revision/high-water proof; current finalized prefix and exact parent; current h/r/phase and enabled-rule/replay state |
| Before prevote signature release | Immutable reservation for exact envelope bytes and `(context,key,h,r,prevote)`, nil or value, parent, source validation result; current lock/LR and actual old-round PV sources when line 28 applies; resulting phase/revision |
| Before non-nil precommit release | All preceding state plus exact current proposal/full canonical value, q authenticated current-round prevotes, **new lock/LR and validValue/validRound atomically durable** with the exact reserved precommit; no window exposing the signature before the lock |
| Before nil precommit release | Exact nil reservation and phase plus unchanged prior lock/LR, actual nil quorum or recorded armed/expired prevote wait; nil never erases safety memory |
| Before publishing a proposal | Exact reserved signed proposal envelope, selected value bytes/parent and vr, retained validValue/validRound and actual proposal/PV sources backing it; getValue validation when unset; stable byte identity across re-proposal; publish only durably stored signature/outbox |
| Before round continuation | Authenticated future-round evidence or timer/once-guard replay state; preserve lock/valid data and all released/reserved slots; learned validValue after a nil precommit must survive before a later proposal |
| Before finalization acknowledgement / next-height signing | Exact complete B, signed proposer evidence, matching q precommits, validated finalized parent and sources, monotonic decision/ancestry, authoritative applied/finalized cursors, idempotent publication work. Commit before acknowledgement and before resets/next-height releases can escape |
| All signed slots | Retain exact sign bytes, signature bytes, reservation/sign/release state, before/after safety revision and justification; duplicates return the retained signature. Conflicting bytes for a reserved slot refuse; pruning requires separate proof |
| Performance/recovery convenience only | Parsed roster caches, peer scores/connections, verification caches, transport retries, derived indexes and worker queues can be rebuilt. Their underlying immutable source evidence/signer reservations cannot be discarded. Numeric timers may be conservatively rearmed only with a reviewed safe replay scheme preserving signed slots/once behavior |

Persist/replay **non-signing** state transitions too: validValue learning and
round changes influence future proposal/signing choices. Last h/r/signature or
finalized chain alone is insufficient. Ordinary receiver QCs need not embed the
whole private PV transcript; the private journal must retain its own sufficient
dependencies. Do not claim an atomic transaction across separate signer/chain
databases; specify source ownership and recovery cursors explicitly.

Later crash tests must kill/recover at: before reservation; during reservation
commit; after reservation/before signing; after signature creation/before durable
signature storage; after storage/before outbox publication; after publication/
before acknowledgement; while lock/PV dependencies are persisted; after late
valid-value learning; during round advance; during decision/promotion; between
durable decision and next-height reset/start; during replay/uncertain commit
reread. Exact retries must return identical signatures or fail closed. Include
two-process races, busy/full/I/O/unknown outcomes, stale backup/rollback, cloned
keys and actual enforced fencing. Missing/uncertain private state disables
signing even after public sync. Physical power loss on intended filesystems is
a distinct future acceptance test.

## 9. Canonical v3 validity boundary

Agreement treats valid() as a stable deterministic application predicate over
the complete immutable candidate, approved policies and finalized prefix. The
Boolean abstraction tests agreement independently of media codec cost. It does
not prove the existing canonical implementation refines these flags.

| Model fact | Future production validation obligation / existing reusable boundary |
| --- | --- |
| height/parent | Exact child of a verified finalized parent; preserve all anchors and application state. Current active provisional-parent acceptance needs a new inactive-profile adapter |
| protocol | Independently pinned network/genesis/profile/versions/policies; authenticated static M/C/epoch; no proof-selected roster |
| canonical | Strict canonical parse/hash/schema; `canonical_v3.block.parse_record` and payload checks are useful existing boundaries, not a new-profile parser |
| original | `canonical_v3.media.reconstruct` / `block.reconstruct_record_media`, original hash/length, approved codec profile, exact original bytes and all technical safety requirements; a media hash alone is insufficient |
| admission | Full parent/policy-bound deterministic admission certificate and authenticated source replay; existing `AdmissionAdapter`/construction checks are reusable after the policy freeze |
| transactions | All native transaction signatures, commitments, deterministic ledger/reward rules; reuse canonical transaction validation against exact immutable parent state |
| resources | Complete canonical record cap and array/codec/worker resource limits; new schema overhead must fit the unchanged MODEL A cap |

Run expensive decoding/validation in bounded workers once per immutable input
and bind results to namespace/h/parent/hash/source revision. Completed work for
an obsolete phase cannot sign a second vote. `validity=None` means incomplete
data or local worker unavailability: await/fetch or follow ordinary nil timeout
rules, never declare the media objectively invalid or penalize its creator.
An authenticated bad commitment produces deterministic invalidity instead.
The model's abstract `data` includes required evidence as well as media bytes.

The production adapter must return stable validity for fixed bytes and parent;
local time, changing reviewer caches, arrival order and codec-worker availability
cannot change the underlying consensus predicate. Freeze timestamp/admission/
reviewer rules before implementing it. Feed those verdicts into the reference
guards without changing locking, valid-round checks, nil semantics or q. No
codec worker runs per model transition; no codec, block format, reward or
original reconstruction rule is changed here.

## 10. Reproduction and focused regressions

From repository root; no new dependencies for model/checker/replay:

```powershell
.\.venv\Scripts\python.exe -B -m verification.tendermint717h.check
.\.venv\Scripts\python.exe -B -m verification.tendermint717h.replay verification/tendermint717h/results/trace-hidden_commit_nil_rounds_intact_restart.json
.\.venv\Scripts\python.exe -B -m verification.tendermint717h.replay verification/tendermint717h/results/trace-lost_signer_state.json --allow-negative-controls
.\.venv\Scripts\python.exe -B -m pytest tests/test_milestone_7_task_7_17h_tendermint_model.py -q --tb=short --basetemp=temp/task717h-repeat-model
```

Use `--output temp/task717h-repeat-results` to preserve retained evidence while
rerunning the checker. `--depth` and `--state-limit` are explicit configurable
cutoffs, not changes to consensus guards. Source hashes in `summary.json` bind
the generated evidence; the focused test checks hashes, replays every retained
trace and reconstructs every seed independently of its stored state snapshot.
Durations may vary. A second run with `PYTHONHASHSEED=717` matched **all 27 JSON
evidence files**, excluding only `runtime_seconds`, and took 24.319084 s.
Counts, full seed/trace states, digests and all other fields matched.

The preserved regression selection is exactly:

```powershell
New-Item -ItemType Directory -Force temp/task717h-repeat-runtime | Out-Null
$env:TEMP=(Resolve-Path temp/task717h-repeat-runtime).Path
$env:TMP=$env:TEMP
.\.venv\Scripts\python.exe -B -m pytest tests/test_milestone_7_task_7_17e_finality_durability.py tests/test_milestone_7_task_7_17c_finality_audit.py tests/blockchain/test_task_3_5_validator_quorum_finality.py tests/blockchain/test_task_3_6_public_finality_status.py tests/blockchain/test_protocol_v1_lifecycle_finality.py -q --tb=short --basetemp=temp/task717h-repeat-finality
```

Current model-focused run: **42 passed in 3.21 s**. Preserved regressions:
**73 passed in 19.90 s**, no failures/errors/skips: 36 current E
durability tests, 17 preserved C diagnostics and 20 active finality/status/
lifecycle cases. Historical witnesses still use their pinned unsafe baseline;
their green results are diagnostic reproduction, not BFT safety claims. No
existing assertions or fixtures changed. Model-focused final counts and exact
JUnit runtimes are retained in `results/validation.json`; disposable XML is
under `temp/task717h-{model-tests,finality}.xml`. No full-repository or multi-host
production-engine test is claimed. An early new trace-export test found that a
partition-prefix result held a mutable trace list; snapshotting the list fixed
the evidence export. Seed replay additionally caught inconsistent height-bound
metadata, and the different-hash-seed repeat caught one unsorted message list in
a schedule. The final tests/replays and repeat use corrected exports/bounds and
deterministic ordering; no reference guard was relaxed to resolve these issues.

## 11. Implementation acceptance gates

| Later subsystem | Required implementation-level acceptance before approval |
| --- | --- |
| 1. Genesis-authenticated membership | Owner-approved full G2/M/C/policy/new network, exact full-key/ID binding, order/duplicate/curve/epoch/f/q negatives, pinned release trust, no override/self-authorizing roster; independent golden vectors |
| 2. Versioned proposal/vote messages | Freeze agreement descriptor, full message/Q4/PV/combined media schemas and bounds; independent serializers/verifiers and signed vectors; reject mixed contexts/rounds/steps/parents, old-format relabeling and duplicate QC identities |
| 3. Durable signer | Refinement of atomic reference transitions to reservation/sign/store/release, all section-8 crash points, exact retries, non-rollback state, exclusive enforced key fencing; actual separate-process/stale-disk tests |
| 4. Round/lock engine | Every guard/action mapped to Algorithm 1 and reviewed model; preserve nil locks, actual vr evidence, once guards, late valid learning, catch-up and old-round decisions; replay conformance/adversarial state comparison |
| 5. Proof persistence | Commit complete block/decision/proof/sources and monotonic finalized ancestry before visibility; preserve compatible proof variants and both authentic conflicts with a durable fault latch; uncertain outcome fails closed; no fictional cross-DB atomicity |
| 6. Network propagation | Bounded authenticated message/proposal/PV/Q4 inventory and gossip, fair fetch/retransmit, complete data/source availability, same-tip missing proofs and genesis-to-prefix verification; peer HMAC is not validator authority |
| 7. Multi-node adversarial tests | Four independent processes/stores/fenced signers with real test signatures, deterministic delay/drop/duplicate/reordering, partitions/healing, crashes and data failures; later independent hosts/operators, intended filesystems and independent consensus review |

**Model-level BOUNDED_PASS** means only the finite results above. An
implementation-level PASS requires all relevant acceptance rows and demonstrated
refinement; no implementation is supplied here. Release-level PASS additionally
requires approved operations/custody/support, complete policies/schemas/versions,
capacity accounting, independent security review and explicit activation/launch
authorization. Both implementation and release flags remain false in the JSON.

## 12. Remaining decisions and readiness

Owner approval is still required for independent permissioned/static authority,
N4/f1/q3 and operator independence/cumulative key-compromise assumptions; exact
paper variant and native versus reviewed engine route/review budget; complete
G2/agreement/message/combined media/history schemas and byte registry; network/
genesis/operators/keys/release trust; static-halt/emergency recovery and any future
state disposition; durable signer custody/fencing/rollback operating contract;
finalized-parent/decision-priority behavior and source retention. No approval
is inferred from a passing model or the current proposal documents.

Reviewer bootstrap/history/cohort/all-unsure behavior, clock/admission timestamp
stability, issuance ownership and any no-media/control-history amendment remain
separate blockers. One accepted original media per canonical non-genesis block
and exact original reconstruction stay mandatory; no empty/control blocks or
unreviewed preliminary media are authorized.

**Task 7.17H is ready for review and a later owner-performed commit**, subject to
the disclosed finite scope and independent review. No missing reference guard
blocked faithful bounded modeling. Detailed isolated signer/adapter design can
now use executable rules and counterexamples. The next consensus implementation
step is **not unconditionally unblocked or authorized**: complete owner/schema/
route and review gates above still apply. No next task is begun.
