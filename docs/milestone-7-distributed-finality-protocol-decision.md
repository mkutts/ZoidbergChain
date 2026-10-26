# Milestone 7 Task 7.17G — Distributed BFT finality protocol decision

**Task 7.17I follow-up (2026-10-26):** The
[BFT wire and signer contract](milestone-7-bft-wire-and-signer-contract.md)
specifies closed versioned proposal/prevote/precommit/nil, PV/Q4 and future-round
evidence formats; exact EIP-191 signing bytes and typed hashes; Algorithm 1/model
correspondence; durable slots, reservation/sign/store/release ordering and
external fencing requirements. Independent Python/JavaScript synthetic vectors
and capacity calculations support **PASS for the parameterized wire contract
and specification readiness of an isolated test-identity signer prototype**.
Neither prototype implementation nor subsequent tasks begin here. Production
signer, production BFT engine, public-testnet activation and Task 7.17 reviewer
history remain **BLOCKED** on implementation/adversarial review, enforceable
nonrollbackable custody, full approved G2/policy/combined block schema and owner
decisions. No launch membership, keys, genesis or activation is approved; bounded
model success is not a formal proof. Earlier proposal/gate snapshots below are
historical; the 7.17I matrix separates current specification and production gates.

Date: 2026-10-24 (America/New_York). **Documentation proposal only; no protocol
or launch approval, implementation, activation or subsequent task.**

Recommend **single-height Tendermint, specifically Algorithm 1 of _The latest
gossip on BFT consensus_, arXiv:1807.04938v3**, with its `validValue/validRound`
termination mechanism, equal static voting power, and sequential finalized
parents. Each decision is exactly one fully admitted media block. A decision
does not need later blocks. Keep genesis-authenticated `N=4,f=1,q=3` as the
preferred working configuration, subject to owner approval.

This is a substantial consensus subsystem replacement around reusable application
validation and durability components, not a repair to the existing tally loop.
Published results cover the reference algorithm under its assumptions; they do
not certify our proposed serialization, crash recovery, gossip, media validation
or reviewer integration. Those adaptations require conformance/model work and
independent review before activation. Task 7.17 remains **BLOCKED**.

## 1. Repository verification and evidence

| Prerequisite, checked before edits | Observation |
| --- | --- |
| Branch | `Compression-State-Bloat-and-Node-Economics`, expected |
| HEAD | `56110fdb04fbd50d15e6b912a97c6d5b99915641` |
| Worktree/index | Clean, including untracked files; no unexpected Git state |
| Separate 7.17F commit | HEAD, `Milestone 7 Task 7.17F: specify validator authority and quorum safety`; two documentation files |
| Separate 7.17E repair | `82f8a49efe1c9f1bb7ec5f69e3e5562f7dddecd8`; production durability code and current regression tests present |
| Earlier specifications | 7.17D `f025e60`, 7.17C `3b8bbce`, 7.17B `d075cb2` |
| Instructions | No applicable ancestor/repository `AGENTS.md` found; no delegation |
| Authorized edits | This new document; reference/current gate summary only in 7.17D |

Read the [dependency audit](milestone-7-finality-and-history-dependency-audit.md),
[safety/remediation decision](milestone-7-finality-safety-and-remediation-decision.md),
[durability report](milestone-7-finality-durability-implementation.md),
[authority/quorum decision](milestone-7-validator-authority-and-quorum-decision.md)
and [reviewer-history amendment](milestone-7-v2-reviewer-history-protocol-amendment.md).
Their proposals are not approvals. Historical pre-7.17E defect descriptions must
not be mistaken for current persistence behavior. Source/tests take precedence.

| Source inspected | Actual boundary and reuse decision |
| --- | --- |
| [block production](../services/block_production_service.py), [validation](../services/block_validation_service.py), `Blockchain.commit_certified_submission` in [blockchain.py](../blockchain.py) | Application builds/validates media, certificate, parent, hash, ledger and rewards. No elected proposer. Current selected parent need not be finalized. Reuse validators through an immutable-parent adapter; replace immediate canonical mint/settlement with provisional validation followed by consensus promotion. Consensus proposer is separate from creator/reward recipient. |
| [finality service](../services/finality_service.py), [v1 bytes](../protocol_v1_finality.py) | Configured addresses; `ceil(2N/3)`; one-phase signed height/hash; first QC. No signer, lock, round or failover. Proof's embedded set supplies historical authority. Preserve historical verification, replace new-profile agreement/counting/authority paths. |
| `submit_validator_finality_attestations`, `_validate_persisted_finality_state`, `_check_finality_cache_transition`, `_publish_finality_cache` | 7.17E now rereads/mutates under a durable transaction, publishes after commit, rereads uncertain outcomes and withholds unavailable finality. Reuse this discipline, not its old message/schema assumptions. |
| [_preserve_finality and storage](../storage.py) | Every guarded writer preserves first QCs and finalized ancestry; canonical vote union; explicit unfinalized-reorg exception. SQLite `BEGIN IMMEDIATE`, DELETE/EXTRA, 30-second busy timeout and owned/closed connections exist. No durable signer state or permanent off-branch evidence ledger. New-profile signer evidence must never use vote-deletion semantics. |
| [fork choice](../services/fork_choice_service.py), [reorg](../services/canonical_reorg_service.py) | Originality score/height/hash chooses provisional paths; finality anchors protected locally. New-profile verified decision must outrank a conflicting unfinalized suffix. Score can prioritize fresh proposals only when reference locking permits it. |
| [peer sync](../services/peer_chain_sync_service.py), [peer messages](../protocol_v1_peer_message.py) | Blocks/certificates/originality evidence transferred; summary preference gates fetching, including same-tip skip. No finality/lock-proof synchronization. Peer HMAC identity is not validator authority. Reuse bounded transport facilities, add distinct authenticated consensus and independent proof inventory. |
| [isolated finality](../canonical_v3/finality.py), [store](../canonical_v3/storage.py) | Caller-supplied trusted roster/equivocators; observer-dependent verdicts. Immutable bytes/branch CAS useful, not authenticated agreement. Do not mutate these frozen modules. |
| [history](../canonical_v3/history.py), [atomic certification](../canonical_v3/atomic.py) | Trusted local snapshots/observation order and local permanent issuance; no distributed historical source authority. Local transactions do not span separate databases. |
| [7.17E tests](../tests/test_milestone_7_task_7_17e_finality_durability.py), [7.17C diagnostics](../tests/test_milestone_7_task_7_17c_finality_audit.py), [frozen baseline](../tests/finality_717c_baseline.py) | Repair regressions include races, failed/ambiguous commits, full/busy/corrupt stores, independent processes and kills. Historical defect witnesses deliberately run pre-repair methods. Their passing results prove neither current defects nor BFT agreement. |

No live store, operational key, network membership or active protocol is touched.

## 2. Established designs and concrete engine feasibility

Primary references, retrieved for this task:

- [T1: Tendermint paper, v3, Algorithm 1 and its proofs](https://arxiv.org/pdf/1807.04938v3).
- [T2: CometBFT v0.38.17 consensus specification](https://github.com/cometbft/cometbft/blob/v0.38.17/spec/consensus/consensus.md).
- [T3: CometBFT v0.38.17 state machine](https://github.com/cometbft/cometbft/blob/v0.38.17/consensus/state.go).
- [T4: CometBFT v0.38.17 private-validator persistence](https://github.com/cometbft/cometbft/blob/v0.38.17/privval/file.go).
- [T5: CometBFT v0.38.17 configuration](https://github.com/cometbft/cometbft/blob/v0.38.17/config/config.go).
- [T6: CometBFT v0.38.17 ABCI methods](https://github.com/cometbft/cometbft/blob/v0.38.17/spec/abci/abci%2B%2B_methods.md).
- [H1: HotStuff paper, v6, Basic/Chained HotStuff and Pacemaker](https://arxiv.org/pdf/1803.05069v6).

Pinned CometBFT tag is an inspectable comparison baseline, **not** a claim that
this version is currently recommended, audited for this application or approved
for installation. Select a supported release and review advisories/dependencies
separately if its engine route is pursued. No dependency is installed here.

| Criterion | A. Reference Tendermint single height | B. Chained HotStuff | C. Existing CometBFT engine + application adapter | D. Repair current signature tally |
| --- | --- | --- | --- | --- |
| Published model | T1 authenticated Byzantine agreement, `N=3f+1`, deterministic validity predicate, eventual synchrony for termination | H1 authenticated partial synchrony; safe-node/QC/lock rules and a separate functioning pacemaker | T2/T3 implementation plus T6 application determinism; faithful integration still necessary | No complete published protocol corresponds to present behavior |
| N4/f1 | q3 prevotes and q3 precommits; tolerate one Byzantine identity | q3 QCs; tolerate one under full protocol | Equal voting power can express N4; genesis/key mapping must be explicit | Arithmetic q3 alone does not establish tolerance |
| Progress/failover | Rotating proposer, retained valid value, increasing waits and future-round catch-up | QC-driven leader replacement plus pacemaker; responsiveness benefit after stabilization | Existing transport/round handling reduces custom core code | Sign-once can halt on split votes; timeout revoting can break safety |
| Signer/restart | Persist signed slots AND lock/valid state and supporting messages; section 5 | Persist last vote/view, locked/high QC, ancestry and recovery pacemaker state | T4 keeps H/R/step, sign bytes and signature; engine WAL/replay also needed. That file alone is not a complete lock store or stale-disk defense | Receiver durability is available; private signing state absent |
| Complexity | Two voting phases at one height; no descendant commit pipeline | Three-chain ancestry/commit conditions, highQC/lockedQC and pacemaker integration | Larger Go service/ABCI/engine block lifecycle and two-store handshake | A complete defensible repair becomes A or another full protocol |
| Certificates/crypto | q individual signatures/phase; no threshold key ceremony | Compact threshold QC possible; individual-signature QC has O(N) size and changes byte claims | Native engine sign bytes/keys/proofs differ from current EIP-191 API | Small one-phase certificate, insufficient semantics |
| Network | All-to-all vote delivery O(N²); payload gossip separate | O(N) logical leader exchanges with compact QCs; without threshold aggregation QC bytes can be O(N²); payload still dominates here | Engine gossip/state transfer replaces substantial networking; extra block/commit bytes | Cheap tally receipt, no safe split recovery |
| Latency / sparse media | Proposal + prevote + precommit; current media can finalize alone | Pipelined commitment depends on later certified nodes; last media needs drain/dummy/control work unless another complete variant is selected | Same-height decision possible, but default engine block production is a compatibility issue | No conditional eventual agreement guarantee |
| Historical proof | Current-round proposer signature + same-round commit votes + exact media/ancestry; section 6 | Certified descendant links/three-chain proof and authority; one QC is not finality | Retain engine headers, commits, validator mapping and application-byte inclusion; cannot translate by relabeling signatures | Historical roster self-assertion/sync gaps remain |
| Fit / burden | Best semantic fit, **high** custom implementation/testing/review burden | Additional sparse-stream/pipeline complexity without useful four-node scaling gain | Credible way to reduce custom consensus; **high integration redesign** burden | Not acceptable independently live BFT |
| Maintenance/security | Permanent reference-conformance ownership, independent review and adversarial tests | Same plus pacemaker/aggregation/key lifecycle review | Track upstream security/support, pin binaries/config/ABCI, audit adapter and recovery | Continuing bespoke rule invention is an unacceptable maintenance risk |

HotStuff's linear communication and responsiveness results rely on its full
construction and pacemaker; no such benefit is claimed for a custom EIP-191
substitution. Basic HotStuff can decide without a media pipeline, but needs its
complete additional phases/view-change protocol and would be a distinct choice.
Chained HotStuff's sparse-stream tail is a material incompatibility, not a reason
to quietly authorize empty media blocks. [H1](https://arxiv.org/pdf/1803.05069v6)

**Engine assessment:** CometBFT is feasible as a separate process serving a
deterministic Python application. T6 provides proposal processing, finalized
execution, commit and startup application height/hash reconciliation. However,
its engine blocks/headers/last commits, mempool behavior, native signature
formats, application-hash timing and recovery must be mapped explicitly. The
adapter must reject invalid proposals in proposal processing; marking a media
transaction failed only after block commitment does not preserve this design.
[T6](https://github.com/cometbft/cometbft/blob/v0.38.17/spec/abci/abci%2B%2B_methods.md)

Turning `create_empty_blocks` off is insufficient evidence of strict one-media
history: T3 includes a `needProofBlock` path after an application hash changes,
and T5's empty-block/wait-for-transactions configuration is not an application
validity proof. Hiding engine empty blocks in an uncounted side history would
still introduce retained consensus records and a media-to-engine-height mapping.
It needs an explicit owner gate and cost model. Do not patch engine locking or
signing to make this fit. [T3](https://github.com/cometbft/cometbft/blob/v0.38.17/consensus/state.go),
[T5](https://github.com/cometbft/cometbft/blob/v0.38.17/config/config.go)

Recommend the **T1 protocol contract** now; native implementation versus a
conforming reviewed engine adapter is a separate implementation-route gate.
Do not write a custom engine merely because this document describes its rules.
If strict media history cannot be retained by an existing engine and the owner
does not fund independent review of a faithful native implementation, activation
stays **BLOCKED**. No off-the-shelf drop-in is established by this investigation.

## 3. Formal assumptions and adaptation boundary

Let ordered V be the four full secp256k1 keys authenticated by approved G2, using
7.17F's canonical M/C and derived validator IDs. Every member has weight one;
epoch is zero for the entire network. `N=4, f=1, q=3`; membership never changes
on timeout, restart, reviewer epoch, evidence discovery or administrative edit.
Genesis itself is a pinned trusted anchor, not a self-authorizing quorum proof.

Safety assumes unforgeable context-bound signatures, collision-resistant hashes,
common pinned genesis/policies, at most one faulty identity over the relevant
historical signing lifetime, and correct deterministic validation and crash-safe
signing by every remaining validator. Cloned/stale/compromised honest keys count
as faulty. Different addresses under one operator do not provide independence.
Ordinary signatures are not forward secure: later accumulation of enough static
keys can forge history. No checkpoint or automatic slashing fixes that here.

Safety needs no timely network. Liveness needs eventual bounded delivery and
gossip among all three correct responsive validators, fair processing/proposer
opportunities, bounded full validation/storage service, and an available value
satisfying the same immutable-parent validity predicate. Fault budget includes
withholding and outages; one Byzantine plus another offline can prevent progress.
There is no permanent-partition/asynchronous termination promise.

Application-specific obligations outside the reference theorem:

1. `valid(B,F)` must be identical across correct nodes and stable for the entire
   height. Use only B, full finalized prefix F, genesis/policy and authenticated
   included inputs. A wall clock, local reviewer labels, unpublished mempool,
   challenge cache or changing off-chain issuance ownership cannot decide it.
2. Validate/retain full canonical original-reconstructable media and admission
   sources before voting for B. Local worker/storage unavailability means abstain
   or nil via normal rules, not an objective invalidity or reviewer penalty.
3. Only a verified durable decision at h-1 authorizes voting at h; no pipelining.
   Genesis is the h1 exception. Candidate timestamp and certificate expiry are
   frozen inputs, not rechecked against time of round/retransmission. A complete
   timestamp/admission policy is an application approval gate, section 8.
4. Round envelope changes must not change a re-proposed block. Consensus proposer
   identity is in the signed proposal, not rewritten into the media's miner,
   creator, reward or timestamp. No new proposer reward is specified.
5. Crash recovery refines one continuing reference process; losing lock state
   cannot be modeled as a fresh honest process with the same key.

Changing any lock predicate, accepting a certificate without its actual votes,
dropping valid-value gossip, lowering q, unlocking on timers/nil, using mutable
validity, speculative-parent voting, truncating necessary safety logs, or changing
the engine lifecycle requires a new proof/review. Neither T1 nor this proposal
certifies such changes.

## 4. Agreement state machine — one precise reference

The normative transition relation is **T1 Algorithm 1, lines 1–67**, including
its once-only guards and asynchronous event rules; incorporate that complete
listing by reference. The compact mathematical mapping below identifies the
required predicates without reproducing another algorithm. The T2 prose and T3
implementation are comparison material, not interchangeable transition tables.
In particular, **do not import T2's nil-polka unlock into this T1 profile**.
[T1](https://arxiv.org/pdf/1807.04938v3),
[T2](https://github.com/cometbft/cometbft/blob/v0.38.17/spec/consensus/consensus.md)

### 4.1 Application mapping

| Symbol | Required interpretation |
| --- | --- |
| h | Next media height, immediately after unique finalized F; >=1 |
| r / step | Round >=0; propose, prevote, precommit; decision is not an extra signed vote phase |
| proposer(h,r) | `V[((h-1) mod N + r mod N) mod N]`, V in M's strict compressed-key byte order. Equal-power deterministic round robin; three honest proposer opportunities in every four rounds. New proposal envelope each round, same locked/valid block bytes where required. |
| v / id(v) | Complete canonical media record B / its canonical block hash H; validated hash binds actual parent, media, certificate, ledger and all application commitments |
| parent | Exact `(h-1,F.hash)` plus verified parent proof, except pinned genesis. All messages include F.hash, C, G and policy A as section 5 defines. |
| L/LR, W/WR | `lockedValue/lockedRound`, `validValue/validRound`; unset value=null and round=-1. W is a possible decision value backed by actual q prevotes and proposer evidence; it is not an admission certificate. |
| PV(r,H) / PC(r,H) | Three distinct authorized prevotes / precommits, same full context, same round and value. `null` is nil, never a zero-hash media block. |

### 4.2 Required reference predicates

| Reference guard | Effect (otherwise obey the complete reference guard/step ordering) |
| --- | --- |
| StartRound(r) | Proposer uses W if set; otherwise application supplies valid v. Propose `(v,WR)`. Preserve L/LR/W/WR across rounds. |
| Fresh proposal, vr=-1 | Prevote H iff `valid(v,F) AND (LR=-1 OR L=v)`; else nil. |
| Justified proposal, 0<=vr<r | Require actual `PV(vr,H)`; prevote H iff `valid(v,F) AND (LR<=vr OR L=v)`; else nil. Missing justification is awaited/fetched, never trusted from vr alone. |
| Current proposal + PV(r,H) | In prevote: set `(L,LR)=(v,r)`, precommit H; record `(W,WR)=(v,r)` also when reference permits late valid-value learning after the step. |
| PV(r,nil), or prevote timeout | Precommit nil; retain L/LR. Nil does not decide or unlock. |
| Current-round q prevotes, any values | Arm reference prevote wait once. |
| Current-round q precommits, any values | Arm reference precommit wait once; its expiry starts r+1. |
| Propose timeout | Prevote nil, once; preserve prior safety state. |
| f+1 distinct senders at a common future round | Reference catch-up starts that round; no lock release. Count identities, not phases/messages. |
| Proposer evidence for `(h,s,v)` + PC(s,H) | Decide valid v even if local r>s; transactionally promote, then start h+1/r0. Reset lock/valid state only at that durable height transition. |

The table is a reference binding, not permission to implement only the happy
path. Event handlers must preserve single-step signatures, first-trigger flags,
late evidence, future-round catch-up and gossip/replay equivalence.

**Safe change of preferred value:** a justified proposal permits a prevote for
another value only through the stated reference predicate. The old lock remains
until the reference current-round non-nil locking transition replaces it. There
is no standalone UNLOCK, TIMEOUT-QC, new-view signature or wall-time lock expiry.
Round progress uses ordinary authenticated proposal/vote evidence, not a new
commit certificate. A stale PV cannot override a newer lock; an equal-round
conflicting PV would itself violate within-round quorum safety under the model.

Timeout families must grow without a fixed operational cap while a height is
undecided, e.g. positive `baseX + r*deltaX` consistent with T1. Base/delta values
are operational tuning after full-size validation measurements; record them in
diagnostics. Trigger conditions, not elapsed real timestamps, are protocol rules.
Timers can cause nil votes/round retries, never a historical commit verdict.
Stale timer callbacks check exact height/round/step and become no-ops.

Invalid/wrong-proposer proposals cannot authorize a value vote. Malformed or
forged votes are discarded before quorum/catch-up accounting. Equivocation is
retained as two signed messages for one proposal or vote slot. An honest node
signs at most one proposal and one vote per phase/height/round; cross-round
different votes can be legitimate. Count a validator once per value/phase/round,
never remove its weight globally based on a local evidence list. Conflicting
signed messages are evidence, not authority to choose a branch.

### 4.3 Sparse input and resource limits

No valid application value means no value can be decided. Do not make the
reference `getValue()` return an empty media block. Its implementation must
remain responsive to protocol input while application input is unavailable;
absence supplies no new proposal or permission to reset locks. Nil rounds and
ordinary catch-up may continue, with no chain height, reward or epoch change.
When a valid value becomes available, an eligible proposer can use it through
the reference transition. If it already signed in that slot, wait for a later
round; never replace its signed message. A scheduler that resumes application
input and continues fair reference event handling needs explicit refinement
testing; unconditional termination from the paper is not claimed without input.

Do not add a new quorum-based wakeup/idle-reset protocol here. Optimizing away
all idle rounds while retaining termination after input arrives is a separate
pacemaking refinement, **BLOCKED** until modeled/reviewed. The unoptimized
profile can consume control traffic during indefinite media absence.

Proposed wire integers: height 1..`2^53-1`, round 0..`2^31-1`, justification
round -1..r-1. Exhaustion stops safely, never wraps; infinite-run termination is
therefore a mathematical abstraction, not a promise past finite field/storage
limits. Memory quotas must not silently discard lock/valid/commit dependencies.
Future evidence is streamed/spooled with bounded parsing and fair processing;
one Byzantine identity cannot trigger a future-round jump alone. Final numerical
buffer/retention policy and denial-of-service measurements remain activation gates.

## 5. Signing preimages and crash-safe signer contract

### 5.1 Proposed closed agreement messages

Keep 7.17F M/C membership encoding. Its **A3/Q3 was an authority-only draft** with
step `commit`, not a Tendermint precommit. Explicitly propose **agreement message
version 1 and finality proof version 4 (Q4)** below, under new domains. Do not
reinterpret A3, v1 or inert v2 signatures. These are proposed review interfaces,
not changes to existing parsers or an approved registry assignment.

`J` is strict canonical UTF-8 JSON: sorted keys, comma/colon without whitespace,
no final newline/BOM, ASCII strings in these consensus structures, JSON integers
only (no bool/float), duplicate/unknown keys rejected. All H64 values are exactly
64 lowercase hex; IDs are 7.17F canonical derived addresses. Bounds below apply
to serialized bytes before crypto. Other application formats retain their own
versioned canonicalization. Let common payload fields be exactly:

```text
K = {agreement_profile_digest:A, block_height:h, genesis_hash:G,
     message_version:1, parent_hash:F.hash, round:r, validator_epoch:0,
     validator_id:ID, validator_set_commitment:C}

vote payload = K + {block_hash:H_or_null, step:"prevote"|"precommit"}
proposal payload = K + {block_hash:H, step:"propose", valid_round:vr}

E = {domain:D, network_id:NID, object_type:O, payload:payload,
     protocol:"zoidbergchain", protocol_version:2}

D/O for proposal = "zoidbergchain/bft-proposal/v1" / "bft-proposal"
D/O for vote     = "zoidbergchain/bft-vote/v1" / "bft-vote"
Signed = {envelope:E, signature:Sig65, signature_scheme:"personal_sign"}

sign_digest = Keccak-256(0x19 || ASCII("Ethereum Signed Message:\n")
                       || ASCII(decimal(byte_length(J(E)))) || J(E))
message_id = lowerhex(SHA-256(J(E)))
```

The displayed `\n` is one 0a byte. No UTF-8 hex conversion, extra prefix, JSON
string wrapper or signing of the SHA-256 diagnostic ID. Sig65/r/s/v/full-key
recovery follow 7.17F, including valid high-S acceptance without extra weight;
signer retries return the exact first retained signature. Recover/check the
registered full public key and derived ID. Direct G/C/A/epoch/NID/protocol/step
binding prevents cross-genesis/network/purpose replay. Nil uses actual JSON
`null`, with real parent/context and signature; H is never nullable in a proposal
or commit proof. No signed wall-clock timestamp or transport nonce is needed.

Proposal transport is exactly `{proposal:Signed, block:B, valid_round_proof:P}`;
P=null iff vr=-1, otherwise the verified prevote certificate for vr/H/context.
H must equal B's canonical hash, actual parent and height. This bundle is not
the canonical block record. Proposal message ID binds r/vr/H/proposer; the value
ID H remains constant across honest reproposals. Different sufficient P signer
subsets do not change the proposed value or require another proposer signature.

Proposed PV certificate is exactly `{certificate_version:1, commitment:T,
votes:[Signed,...]}`, T=vote payload minus validator_id with step="prevote".
Every entry equals T plus its ID, sorted strictly by ID, length q..N, no repeated
ID. It can prove a value or nil for reference processing; only non-nil P backs
a re-proposal. An offered malformed certificate rejects as a whole; an aggregator
may independently collect verified votes before constructing a new certificate.

Proposed finality Q4 is exactly `{proof_version:4, commitment:T,
proposal:Signed, precommits:[Signed,...]}`. T=vote payload minus validator_id,
step="precommit", H non-null. Proposal matches h/r/H/context and the scheduled
proposer; its vr is -1 or 0..r-1. Precommits have q..N strictly ID-ordered unique
entries matching T. The complete block and parent proofs are fetched separately.
Q4 need not embed every historic PV/unlock transcript: the reference commit
criterion is proposer evidence plus q precommits. Such transcripts are required
for signer correctness/recovery/accountability, not recursively nested inside
every historical decision proof. Q4 signatures alone do not prove that each
signer followed the protocol; the bounded-fault premise supplies that guarantee.

Suggested new-profile parsing ceilings for N4 only: J(E)<=2,048 bytes,
Signed<=2,304, PV<=12,288, Q4<=16,384, JSON depth<=32. Each bounded transport
proposal carries B<=3,145,728 plus separate bounded metadata/P; no cap is an
addition to B's canonical capacity. Enforce lengths/counts/contexts before
recovery work. Recalculate exact worst-width vectors before freezing these caps.
No arbitrary nested justification chains or caller-supplied validator roster.

**Remaining byte freeze gates:** complete G2 layout/policy registry, canonical
agreement descriptor A and the combined media/history block schema are not yet
approved. A must authenticate the exact T1 variant, static equal-power schedule,
message/proof grammars, validity/parent/version rules, numeric/cap profile and
recovery contract, without including resulting G. Compute M->C and descriptor->A,
then complete genesis->G; all signed messages bind G/C/A. Registry registration,
full signed golden vectors and independent cross-language serialization/recovery
checks must precede a signer API freeze. This section supplies exact candidate
message preimages, not a fabricated approved genesis hash or signed fixture.

### 5.2 Required private safety state

Persist under `(protocol,NID,G,A,epoch,C,full-key-ID)`:

- Immutable authority/policy bytes or verified content-addressed references;
  exclusive signing authority ID/fencing generation; monotonically increasing
  safety revision and rollback-protected external high-water knowledge.
- Current h/r/step, completed decision/parent proof and application applied
  cursor; first-trigger flags or sufficient replay log to reconstruct them.
- Locked H/LR plus exact B and its verified PV/proposer sources; valid H/WR plus
  exact B/PV/proposer sources. Distinguish these from the highest finalized Q4.
- Highest known verified parent/current decision certificate and round evidence
  needed for safe resumption; received/sent message log supporting all unreleased
  and released transitions. No unsigned "highest round" can authorize anything.
- One immutable decision reservation per `(namespace,h,r,step)` for propose,
  prevote and precommit, containing **exact J(E)**, hash/null, parent, vr where
  applicable, validation/source identity, safety before/after revision and
  justification. Retain exact signature/release state and last-signed message.
  Initially retain all local signed slots; pruning needs a separate proof.

State transitions that learn W or advance rounds can affect later proposal
choice even without signing; durably journal/replay them. Ordering messages in
one reference event loop is necessary but insufficient if disk state is stale.
All lock state and dependencies must survive before the corresponding precommit
is exposed. Do not restore only h/r/last-signature and discard same-height locks.

T4 illustrates persistent H/R/step, exact sign bytes and signature reuse, including
special native timestamp handling. Our proposed bytes have no timestamp; do not
copy that exception. T4 is not a distributed key fence or replacement for the
consensus WAL. [T4](https://github.com/cometbft/cometbft/blob/v0.38.17/privval/file.go)

### 5.3 Exact release/restart sequence

1. Fence exclusive key access; verify namespace, authority, parent, target sources
   and reference transition. Under serialized durable state, reread revision and
   reserve exact bytes AND resulting lock/valid/progress changes. Commit with
   supported durability before signature generation/release can proceed.
2. Generate only the reserved signature; durably store exact signature and an
   idempotent release/outbox record. Commit before returning any signature bytes
   to caller, peer, log subscriber or external consumer.
3. Exact duplicate request returns retained signature even if the node is now
   later in the protocol. New bytes for an already reserved slot reject. A new
   older slot rejects; a new later slot still requires full reference predicates.
   A changed policy/domain/context cannot erase past reservations.
4. Crash before reservation leaves no released signature. Crash after reservation
   permits only those bytes. Crash after signing/before release returns the saved
   signature on retry; crash after release/before acknowledgement also returns it.
   Unknown commit outcome must be reread; if uncertain/unavailable, stop signing.
5. Recover latest signer journal and receiver history; verify locks/PVs/B/parent
   and durable namespace/high-water/fence before enabling the key. Replay must
   not cause a second signature or replace a previously reserved nil vote.
   A learned Q4 cannot reconstruct unpublished votes or lost private locks.

Use a dedicated small safety journal, not whole-chain replacement per vote.
The local SQLite DELETE/EXTRA discipline is reusable, contingent on target
filesystem/VFS flush/locking tests. A durable signer store and a chain store need
no fictional cross-database transaction: the signer must retain its own sufficient
immutable safety dependencies; chain/application promotion has the distinct
boundary in section 6. An external signer must enforce reservation/fencing, not
trust an arbitrary caller to request only safe signatures.

One local DB lock can serialize two processes sharing that exact DB, not two
machines with copied keys/disks. A single remote signing authority or physically
exclusive hardware custody is required; expiring leases without enforced key
fencing are insufficient. Stale disk, lost safety state, cloned image or missing
high-water proof disables signing. Full public sync cannot prove an old private
vote was never released. If no safe recovery exists, preserve the static halt
and seek separately approved authority recovery; never delete-and-resign.

Testnet reset requires separate explicit authorization, new NID and G, isolated
stores and preserved old verification. Prefer new keys; reuse requires reviewed
custody/context isolation and fence retirement. No reset, key creation or reuse
is performed here.

## 6. Finality, ancestry, synchronization and adversarial safety

### 6.1 Deterministic independent verification

From independently pinned approved G2, validate full M/C/A/policies and exact
profile/version. For every h>=1, obtain complete canonical B, its Q4, all media/
certificate/history inputs, and complete finalized parent prefix. Verify:

1. Strict shapes/limits/versions and actual canonical hash/height/parent;
   exactly one fully admitted original-reconstructable media, no empty/control
   substitute. Verify application state transitions from the exact parent.
2. Epoch0/C/A/G/NID/protocol match genesis, scheduled proposer signature matches
   Q4's round/H, and all precommits are authentic unique members with identical
   non-nil T. Require three; no mixed steps/rounds or proof-declared roster.
3. Parent is the verified finalized h-1, preserving every known anchor. Genesis
   exception is explicit. No skipped height, score-based ancestry substitution,
   or fabricated parent QC inferred from a descendant's signature.
4. Treat same H alternate signer subsets/signatures/legitimate rounds as compatible
   decisions. Do not put the proof bytes/digest in B's own hash or make child
   validity depend on one unique encoding of the parent's sufficient proof.
5. Missing B/proof/original/policy/reviewer source => INCOMPLETE; bad authenticated
   bytes => INVALID; local disk/worker failure => UNAVAILABLE. Local timers and
   evidence exclusion lists never enter historical proof validity.

Store exact first proof plus compatible extra evidence, ordered source inventory
and verified finalized/application cursors. A historical verifier need not replay
every timer/prevote to verify Q4; it must still validate the complete application
prefix. An approved-engine route requires its native proof/inclusion verifier,
not a conversion into this proposed EIP-191 Q4.

### 6.2 Promotion transaction and recovery

Expensive validation may occur against immutable sources before the write, but
the transaction must recheck their exact parent/state/authority revision. One
authoritative transaction promotes B + Q4 + immutable source references + finalized
head + ledger/claims/reviewer source cursor (where enabled), and records idempotent
application/relay work. Publish finality/reward/status only after confirmed commit.
An independently stored projection advances its own applied cursor only after
successful ordered application; source commit alone cannot claim it is current.

Every writer/import/restore/reorg uses monotonic ancestry guards. Compatible
concurrent promotions converge; stale parent retries revalidate. An accepted
provisional higher-score fork cannot override a verified decision; discard its
scratch effects and adopt the committed child. This requires versioned changes
to existing score-first adoption and canonical vote-deletion behavior.

Two fully verified incompatible Q4 histories cause a durable evidence/fault
transaction retaining **both** proofs/branches, preserving the previous anchor
and stopping new authoritative promotion/signing. Do not roll back the only fault
evidence with the rejected promotion. Unverified claims cannot latch a fault.
If evidence persistence fails, stop locally. This is fault handling beyond the
premises, not a recovery proof or a rule selecting the first proof as truth.

### 6.3 Concrete traces (A,B,C honest; D Byzantine)

| Attack / trace | Why the proposed protocol prevents conflict within f, or fails closed |
| --- | --- |
| Hidden commit | Round0 A/B/D precommit X after its PV; D shows PC(X) only to A. A/B retain locks even if B never sees the commit. A later proposer offers Y. A/B cannot prevote Y merely on timeout. At the first later conflicting PV, its quorum would need one of these honest lock holders without any earlier permissible conflicting justification: contradiction. C/D alone supply only two votes. |
| Split first proposals | D equivocates: A sees X, B sees Y, C sees one or times out. If no q PV exists, no value precommit/lock is created; nil precommits/round catch-up allow an honest proposer later. If a PV exists, its honest recipients retain W and disseminate it. Choosing a different value based only on latest score is forbidden. |
| Only one honest lock | PV(X) reaches A alone before waits expire; B/C/D may have prevoted X without locking. PC(X) lacks q. A later PV(Y) without A can exist. A can prevote Y in a higher round when the justified proposal satisfies LR<=vr, then replace its lock only on current PV(Y). Never-sign-another-value would stall this legitimate recovery. |
| Cross-height hidden branch | A has Q4(X@h), B is shown Y@h then Z@h+1. Before voting Z, B must verify Q4(Y), not just Y's hash chain. Unique same-height decision rules exclude Q4(Y) alongside Q4(X). Induct from pinned genesis to forbid incompatible descendants; signing once per height alone would not. |
| Stale/counterfeit progress | A locked X@r4 receives PV(Y@r2) in proposal r5, or D merely claims valid_round=6. First cannot satisfy its lock predicate; second lacks actual authenticated q PV and valid round bounds. Future-round catch-up changes r, not L. |
| Delayed decision | Node moved to r7 after r2 failed locally, then receives valid proposal/PC(X@r2). Verify and commit X, retain released r7 votes as evidence; do not reject a real decision because local timer advanced. |
| Crash/clone | B releases precommit X, restarts from a stale unlocked backup and signs Y. This violates honest-signer premises; correct recovery refuses key use. If another identity is already Byzantine, safety budget can be exceeded. Receiver QCs cannot repair this private rollback. |
| Race/provisional fork | Promotion of Q4(X) races generic save/reorg favoring Y. Transaction reread/anchor guards make Y's replacement fail after X wins; if provisional Y was stored first, verified X can replace only its unfinalized suffix. No score tiebreak on conflicting finality. |
| Beyond bound | A/B honest and C/D Byzantine can produce PC(X)={A,C,D}, PC(Y)={B,C,D} after divergent justifications. Both look authentic. Retain/halt when both histories are verified; do not claim protection from two Byzantine keys. |

The hidden-commit trace uses locking across all subsequent rounds, not only the
fact that two size-three sets intersect in two. This is the missing argument in
the existing one-phase finality mechanism.

### 6.4 Proof/source synchronization

Add capability/version negotiation, pinned-context summaries, finalized height/
hash and available proof-range inventory independent of provisional tip score.
Fetch missing Q4 by `(G,A,C,h,H)` even with equal tips; fetch contiguous canonical
blocks/media/sources with bounded pages and resumable hashes. Validate from G;
neither peer labels, proof roots nor a database backup are authority.

Consensus gossip must also fetch proposal B, signed proposer evidence, missing
PV votes for vr, current/future votes and retained decisions; an unsigned round
number or HMAC peer session cannot replace signatures. Deduplicate exact logical
messages/signers; preserve conflicting evidence separately. Use authenticated
content identities, bounded chunk counts/lengths and fair retransmission to all
correct nodes. Never require a proof of global offered-pool completeness.

A fresh observer can reproduce a supplied verified prefix, not prove it is the
globally latest tip. A receiver may replay immutable public history after loss;
a validator with missing private signing history stays disabled. Independent
archive availability remains an operational assumption; q signatures are not
an eternal media-serving guarantee.

## 7. Liveness and failure matrix

Safety below always assumes common authenticated authority, at most one faulty
identity and intact honest signing state. Availability losses do not themselves
authorize conflicting decisions; compound outages can exceed liveness capacity
without invalidating the safety argument.

| Required scenario | Safety / exact progress condition |
| --- | --- |
| One Byzantine validator | Its equivocation/withholding cannot decide conflicting values. All three honest validators, valid media, fair rounds and post-GST bounded gossip/validation/durability suffice for protocol progress. |
| One offline, other three honest | Three can progress after stabilization without the offline proposer, using later honest proposer rounds. Offline node verifies decisions/parent and restores private state before rejoining. |
| Two offline | Remaining two cannot reach q3; pause decisions. Never lower q, extend with fake media or discard locks. Read/sync/diagnostic work can continue. |
| Proposer crash | Propose timeout/nil votes, reference quorum-triggered waits and later rounds permit failover within the combined fault budget. A timeout alone is not a vote or unlock certificate. |
| 2+2 partition | Neither component has three; no new decision quorum. A preexisting withheld decision can be learned, but no new conflicting one can form within assumptions. Safety persists indefinitely; progress waits for connectivity. |
| 3+1 partition | A three-honest component can progress under local eventual synchrony. A component with one Byzantine and two honest may stall if the Byzantine withholds. Quorum capacity alone does not force cooperation. |
| Split proposals | No permanent first-vote rule. Missing polka leads through reference nil/round behavior; any acquired lock/valid value survives and is justified to later proposers. Do not select a local score winner then freely revote. |
| Delayed quorum messages | Do not mix rounds. Late PV supports the reference valid-value/reproposal behavior; late valid PC can finalize its exact old-round value. Timers do not expire historical proofs. |
| Reconnection | Reconcile decisions/parents before next-height signing, gossip highest necessary valid-value evidence, catch up through authenticated reference messages. With retained safety state and restored liveness premises, eventual decisions resume. Verified conflicting finality instead halts. |
| Round change during 3 MiB validation | Jobs are tagged by G/A/h/parent/H and source-state revision. Completion after the vote slot passed cannot cause a second vote. Retain validated immutable B for later proposals; fetch missing justifications. Eventually waits must exceed full dissemination/validation/flush bounds. Worker starvation/unbounded processing violates liveness premises. |
| New proposer after finalization | First verify/apply latest finalized prefix and Q4. Build h+1 on that exact parent. Do not use the old selected provisional tip or transplant an unissued parent-bound certificate. |
| Validator restart | Restore journal, reservations, locks/W/PVs, fence and parent proof; reconcile with committed history. Missing/rolled-back private safety state disables key use even after observer sync. Restart alone never clears a lock. |
| Byzantine proposer censorship | Rotation gives honest proposers opportunities. Gossip the complete valid media/certificate to them; if an admissible value remains available, consensus can decide a value. Eventual inclusion of every particular submission needs an additional fair application queue/admission policy; the reference agreement theorem does not supply censorship-free media selection. |

No fixed block-time SLA follows. For a good round after stabilization, illustrative
critical path is payload transfer/validation + two vote propagation stages +
durable signing/promotion, plus configured waits where triggered. Failed proposers
and rounds add waits; no finite unconditional worst-case latency is asserted.
Four equal proposers limit consecutive Byzantine proposer slots, not total
pre-GST rounds or per-submission censorship delay.

## 8. One-media-per-block, clocks and reviewer-history reconciliation

### 8.1 Preserve the media rule

For this recommendation **every new canonical non-genesis block has exactly
one accepted media submission**, with exact original reconstructable bytes,
technical/rights checks, both community review dimensions and unchanged reward
binding. No empty media, history-kind block, timer block, duplicate reward or
unreviewed preliminary full-media record is authorized. Consensus proposals,
votes, PVs, retransmissions and round changes are messages; Q4s are retained
proof records for actual media blocks, not extra chain heights.

| Need with no accepted media | Consequence in the recommended strict profile |
| --- | --- |
| No submission / pending certification | Await admissible input; nil/retry messages can continue. No media decision/height/reward occurs. Consensus cannot approve media on reviewers' behalf. |
| Finalizing a pending media block | It can finalize at its own height without another media arrival. No descendant pipeline/drain block is needed. |
| Static membership emergency | Restore the same safely fenced authority or halt; no control chain required for unchanged membership. Live replacement/rotation is excluded. More than one unavailable can halt permanently. |
| Reviewer updates/penalties | Updates whose authenticated inputs are included in a future admitted media block take prospective effect on its finalization. Off-chain reports do not become ordered state solely by gossip. |
| Reviewer epochs/quotas/cooldowns | Finalized-height clock stops without media. All-reviewer cooldown/quota exhaustion can deadlock media availability. BFT round count is not an epoch clock. |
| Time-based progress | Local consensus timers only drive agreement retries. They cannot restore eligibility, clear penalties, create quorum, waive review or mint canonical time. |
| Stalled consensus recovery | Replay/gossip/Q4 synchronization and correct round recovery need no new canonical block. Missing private signer safety state cannot be fixed by an empty block. |

**Separate control history is not necessary for BFT finality itself.** It becomes
necessary, or another separately approved policy redesign becomes necessary, if
the owner requires all of 7.17B's unminted-event permanence and epoch recovery
without available admitted media. These goals cannot all be satisfied by strict
media-only, height-clock history without acknowledging that dependency.

If demanded later, a control mechanism needs its own closed type/domain, full
source bytes, explicit capacity/count/rate bounds, consensus authorization,
unique order and connection to the media prefix, atomic applied cursor, pacing,
clock/epoch effects and incentives. An auxiliary sequence is still permanent
consensus history and needs a cross-sequence safety proof; calling it off-chain
does not eliminate it. Raw extra capacity is `control_count*(record_bytes +
proof_bytes)` plus indexes, backups and sync. 7.17B's proposed caps (up to 3 MiB
per history block) are not approved here. No fee, reward or governance authority
is introduced. This **control/clock gate stays BLOCKED**, not silently solved.

### 8.2 Noncircular reviewer timeline

| Stage | Authenticated input / result |
| --- | --- |
| Finalized F=k | Approved reviewer bootstrap/policies and complete included source history derive S_F, quotas, eligibility, penalties and issuance claims. Finality roster is separate from reviewer identity/status. |
| Before a proposal | Reviewers sign creator/target/dimension/choice/reference-bound votes; creator supplies original and rights. Relay/gossip/pull makes raw bytes available. Signature verification authenticates offered statements, not consensus acceptance or a globally complete pool. |
| Candidate at k+1 | Extract media registration, offered signed votes and issuance from bounded canonical sources. Verify from S_F on scratch state, order all candidate inputs deterministically, derive quotas/selection/tallies/claims. Verify C before prevoting B; C needs no future B finality/hash. |
| Agreement at k+1 | Propose/prevote/precommit choose one exact already-valid B. Reproposals preserve those B bytes, parent and certificate; repeated validation uses canonical inclusion timestamp, never today's local clock. Losing siblings consume no global quota/issuance/reward. |
| Durable decision | Finality authenticates included event acceptance/order. Apply mandatory reviewer effects prospectively; no retroactive invalidation of earlier media/certificates. Child k+2 uses S_(k+1). |

This is the dependency direction: genesis/policies + finalized parent + signed
inputs -> deterministic admission/certificate -> canonical B -> agreement/Q4 ->
accepted event history -> next state. Requiring k+1 finalized vote receipts to
validate k+1's certificate would be circular and is rejected.

Authenticated offered evidence requires exact signed original payload/signature,
signed context and creator, registration/rights/media source, and verified
reference ancestry. HMAC peer identity, local receipt timestamp, an unsigned
"accepted" flag, a snapshot hash or a validator assertion cannot substitute.
Maintain completeness of the **included parent prefix and candidate inventory**,
not every privately offered vote worldwide. Finalized negative/unsure receipts
must remain in the approved deterministic selection inputs; unpublished votes
cannot be proven absent. Different offered pools may make different valid
candidates; agreement selects one rather than forcing identical local mempools.

Eligibility/status/age use exactly S_F. Earlier sorted candidate receipts can
consume quota; same-candidate activity must not promote another voter. New
penalties become effective only at the approved post-finalization boundary.
Quota deduplication across two dimensions and prospective penalty schedules need
complete replayable sources; current local rejection/observation order is not
consensus evidence. BFT locking does not settle those reviewer-policy choices.

If another media sibling finalizes and advances F, rebuild an **unissued** C3
against the new parent; newly counted V4 votes require the new signed reference
under 7.17B, whereas already accepted historic receipts retain their original
context. A finalized ISSUE, if that feature is approved, remains immutable and
can settle later without recertification. Mere off-chain issuance is a draft,
not permanent global ownership. Within one undecided height, do not expire or
rewrite locked B on elapsed local time; a different candidate must follow normal
safe reference reproposal rules.

Required independent historical inputs are full approved genesis/reviewer grants,
policy bodies, every canonical media/source record, all selected and extra included
votes/receipts/offense causes, issuance/settlement sources, and every required
Q4/parent proof. Fetch/replay from genesis into separate fresh databases. Missing
inputs mean incomplete; never zero usage, no penalties or assumed eligibility.

### 8.3 Necessary amendments / unresolved policy gates

7.17B is **not approved** by this analysis. A later reconciliation must:

1. Replace its retained one-phase finality/v2 FP contract with the selected full
   agreement/authority/signature/proof/parent contract and versioned vectors.
2. Reconcile exact score-first fork choice with decision-first authority. Exact
   rational score may rank admissible fresh proposals; it cannot override locks
   or finalized media. Current float code remains unchanged.
3. Remove or separately approve history-kind/empty blocks and preliminary REGISTER
   permanently carrying media before both review dimensions approve it. Its
   technical validity/no reward is not community admissibility approval.
4. Explicitly choose whether to defer unminted participation/issuance credit,
   carry fully authenticated extra evidence only alongside admitted media, or
   approve separate control history. Narrowing the lifecycle changes promotion,
   quota and recovery semantics and needs owner approval.
5. Resolve exact earliest-established-plus-fifteen cohort policy: sixteen unsure
   votes can permanently prevent that submission's decisive approval. A later
   favorable subset, new submission ID or validator quorum is not a safe implicit
   escape. Other admissible media may still progress; if none exists, pause.
6. Freeze deterministic timestamp/admission semantics, local service controls
   versus consensus validity, bootstrap grants and complete source retention.
   Increasing local round time must not change `valid(B,F)`. Any required global
   wall-time freshness bound needs a complete compatible clock design first.

These gates block reviewer-history implementation even if the BFT core is later
correctly implemented. They are not reasons to invent an unlock or weaken media.

## 9. Canonical schemas, version boundaries and capacity

Proposed changes below are a future schema specification backlog. No existing
canonical_v3 code, golden vector or historical signature is modified.

| Surface | Required versioned fields/rules |
| --- | --- |
| Genesis G2 | Full M/C (7.17F), epoch0/f1/q3, full agreement descriptor and digest A, complete deterministic application/policy registry, media limit, historical dispatch and release identity. Numeric versions/profile registry must be frozen together. No G self-reference in M/A. Actual NID/G/operators/keys/allocations pending. |
| Validator authority | Full compressed keys, canonical order/derived ID, equal weight, no dynamic updates; config overrides/epoch1 reject. Proof does not declare its own membership. |
| Proposals | Exact signed section 5 envelope, r/vr/H/parent/context/scheduled proposer; B plus actual PV justification outside B. Transport chunk/page identities/lengths separately bounded. |
| Votes | Explicit nil/hash, phase, h/r, full G/C/A/epoch/NID/protocol/validator identity and new domain. Prevote != precommit != proposal; old "commit" cannot be relabeled. |
| PV certificate | Version1/T/q..N unique ordered exact prevotes; actual verified vr proof; no unsigned timeout or local evidence exclusions. |
| Finality Q4 | Version4/T, signed scheduled proposal and q..N exact same-round precommits. External to own B; independently retained/retrievable. No recursive ancestry/PV blob in every proof. |
| Canonical media block | Existing exact media/certificate/native/reward/hash bindings; proposed required `consensus_context={agreement_profile_digest:A,validator_epoch:0,validator_set_commitment:C}` in a distinct new closed block payload. Parent/hash/height already present. **No current r/proposer/vr/Q4/proof digest in B**; those would break stable reproposal or create circularity. |
| Combined block version | Candidate block_version4 must be explicitly reconciled with 7.17B's unimplemented P4/C3/V4 proposal, including `block_kind="media"` only for this strict profile and approved history fields. No two incompatible block4 grammars under one profile. Final combined layout/digest registration is **BLOCKED** pending schema/history decisions. No assertion that frozen block3 accepts new fields. |
| Canonical history/proofs | Q4 and original source BLOBs are required protocol archives even though proof bytes are outside the media cap. Local indexes are derived; proof inventory/apply cursors need context/version binding. |
| Peer synchronization | New capabilities/message types for proposal/PV/votes/Q4, proof ranges and same-tip missing proofs; independently validate full context, ancestry and source availability. Legacy peers remain incomplete/refuse the new profile. |
| Recovery metadata | Private signer reservations/revisions/fences/locks/W and source refs; separate receiver finalized/application/proof cursors and durable conflict latch. Never advertise private signer rows as historical proof. |

The new consensus_context's fixed-width fields add bounded hundreds of bytes
inside B; exact escaping/member/comma accounting must be part of combined-schema
vectors. Reserve that overhead **inside** the unchanged `3,145,728`-byte complete
canonical media record. Selected votes, certificates, captions and native arrays
also remain inside that total. A max-size old-format record may need less optional
payload under the new format; no automatic cap increase is justified.

Do not reuse 7.17B's 86,077-byte analytic margin as proof of final fit. Recompute
all maxima, full-size records and source-event counts after combined schema
freeze. Media-bearing transport overhead/PV/Q4 bytes are additional network
bytes; calling them messages does not make bandwidth, proof archive or signer
storage free. Transport base64/JSON encoding must avoid double-encoding B when
measuring payload cost.

Historical dispatch must preserve v1 active and isolated v2/block3 meanings,
7.17F authority-only draft status, and any subsequently approved new profile.
No retrospective BFT guarantee for old history. Launch/new-network versus an
explicit trusted activation checkpoint/state disposition is an owner decision;
this task chooses neither a reset nor an activation anchor.

## 10. Resource/cost assumptions — estimates, not benchmarks

For N4 and one successful round, every validator signs two votes; the proposer
also signs one proposal: **9 signatures total**, 2 or 3 per node. Simple directed
all-to-all voting delivers `2*N*(N-1)=24` signed vote messages, plus 3 proposal
deliveries. At q3 a verifier checks 3 precommits and 1 proposer signature per
archived Q4 (5 if four precommits retained), plus full application validation.
A validator may verify three peers per phase, proposal and justified old PV;
duplicate verification caching must be keyed by authenticated bytes/context and
cannot trust a claimed ID/hash. Reviewer/native/rights verification is additional.

Assume, illustratively, 1 KiB mean signed vote/proposal metadata, 4 KiB mean
Q4, one round/media, 1,000 media/day, three 365-day years. These are assumed
means **below proposed caps**, not measured widths or latency claims:

| Quantity | Arithmetic / implication |
| --- | --- |
| Vote traffic, network-wide | 24 KiB/media; 26,910,720,000 bytes over 1,095,000 media, about 25.06 GiB; proposal metadata/justifications/retries/invalid traffic extra |
| Full-size payload replication | 3 MiB to each of three peers: 9 MiB/media network-wide minimum for that direct dissemination; 10,333,716,480,000 bytes (~9.40 TiB) in that full-size workload, before relay/retries/sync |
| Payload archive per node | 3 MiB * 1,095,000 = 3,444,572,160,000 bytes (~3.13 TiB), before DB/index/backups/proofs; max-size workload, not average forecast |
| Proof archive per node | 4 KiB mean Q4: 4,485,120,000 bytes (~4.18 GiB). At 16 KiB cap: 17,940,480,000 (~16.71 GiB), one retained proof/media; compatible extra proofs/evidence add bytes |
| Local signer journal | Assume 2 KiB/retained reservation including signature plus associated state references: about `(2+1/4)*2 KiB=4.5 KiB/media` average per validator for one round, ~4.70 GiB over three years, excluding full B/PV logs, indexes, fsync amplification and backups |
| Payload time example | A 3 MiB copy on an assumed effective 10 Mbit/s path takes ~2.52 s ignoring overhead; proposer sending 9 MiB over one shared 10 Mbit/s uplink takes ~7.55 s. Parallel peers do not triple uplink capacity. Add validation, votes and flushes; no fixed latency target inferred. |

At mean r rounds, vote traffic/signing/journal volume grows roughly with r;
payload need not be retransmitted if durably cached by exact H, but different
proposals or evictions cost more. Before GST/under attack there is no finite
global round/traffic bound. Idle nil rounds also incur network/signature/disk
cost without media; per-media formulas exclude that potentially large workload.
Bound implementation queues and measure idle pacing before public activation.

Node RAM/CPU must include bounded original decompression/image safety workers,
3 MiB candidate copies, competing candidate cache, signed vote/PV buffers, SQLite
flushes and replay indexes. A canonical cap is not a peak RAM/validation-time
bound. Reuse existing worker isolation and original reconstruction checks; do
not decode in unbounded gossip handlers. Whole-chain document rewriting per
vote would amplify I/O severely; a small safety journal is a design requirement.
Measure CPU, p95/p99 validation/sign/flush time, full-node catch-up, bandwidth,
physical power-loss/backup behavior and disk amplification on intended platforms.
No new provider prices, throughput promise, compression savings or mainnet/node
economics approval follows from these arithmetic estimates.

## 11. Security, formal verification and interoperability plan

All requirements here are **future acceptance gates**, not tests claimed run
against a new engine. Preserve old diagnostics as historical witnesses.

Before public-testnet activation, require a small executable state model (e.g.
TLA+/PlusCal with TLC or Apalache) binding every implementation guard to T1,
plus written induction for unbounded height/round safety. Explore N4/f1, at least
two heights and enough rounds for old/new lock changes, nil, hidden PC, delayed
PV, simultaneous transitions and crashes. Bounded model checking is counterexample
search, not an unbounded proof. Model private reservation/release/restart and
application parent/cursor state, not just quorum counts. Fair post-GST schedules
must reach a decision given valid input; no-input schedules need not terminate.
Check that serialization/domain changes and recovery are faithful refinements.
Have an independent consensus reviewer assess model, code mapping and adversarial
traces; selecting a library does not waive integration review.

| Test family | Required oracle |
| --- | --- |
| Same-height conflicting finalization | Honest nodes never promote X and Y at h within f1, across multiple rounds, including hidden first commit; assert actual released signatures and durable decisions. |
| Cross-height fork | Q4(X@h) excludes descendant of Y@h; no child vote without verified finalized parent. Synthetic hash chains alone are insufficient. |
| Byzantine equivocation | One faulty proposer/voter splits messages; honest slots remain single-valued; retain conflicting evidence without observer-dependent QC revocation. Beyond-f conflicting valid Q4s latch and preserve both, no score winner. |
| Honest locking / valid state | PV->lock before release; nil/timeouts retain lock; W can update late under reference rules; re-propose byte-identical value; old/lower PV cannot authorize conflicting vote. |
| Safe round change | Test f+1 distinct future senders, one-Byzantine jump attempts, stale timer no-ops, nil quorums, valid proposer unaware of newest PV then learns it, and delayed old-round PC commitment. |
| Conflicting proposals | Different proposals same slot, wrong proposer/schedule/key order, correct H with changed vr, hidden/forged PV, nil/non-nil vote conflict; no double vote. |
| Proposer failure / partitions | Kill proposer; 2+2 halts, three-honest partition progresses, one Byzantine plus one offline may halt; heal and require convergence without lock reset. |
| Crash-before/after-sign | Kill before reservation, after reservation, after signature storage, after release/before ack, during lock/W update and promotion; replay exact signature or refuse, never forbidden signing. Inject real full/busy/I/O and ambiguous commits. |
| Stale signer recovery | Restore old disks/key clones/outdated safety state; fence/key service must refuse. Public Q4 sync does not clear the private-state failure. Race independent processes/key clients. |
| Historical/missing proofs | Bad signatures/order/duplicates/phase/round/proposer/context reject; missing proof/original/policy is incomplete. Same-tip proof fetch works; two authentic incompatible histories retain both and halt. |
| New-node genesis sync | Independent databases, different page/insertion order and restarts derive identical verified prefix/state/certificates from approved genesis plus complete sources, without trusted copied snapshots. |
| Static membership forgery | Embedded fake roster, epoch1, wrong C, altered full point/ID, admin local override or threshold downgrade cannot grant authority. |
| Domain/interoperability | Two independently authored serializers/verifiers agree exact J(E), EIP-191 digest/signatures, null, all field widths and signed golden transcripts; mutate NID/G/A/C/epoch/phase/parent/h/r/H individually. Old v1/v2/A3 cannot be relabeled. |
| Invalid/full-size media | One/over-cap complete records, malformed codecs, original-hash mismatch, invalid rights/reviewer quorum/negative/unsure outcome, worker failure; never vote non-nil for invalid media. Delay full-size validation across rounds without second vote. |
| Original/certification preservation | Re-propose identity/zstd candidates with exact respective block hashes and unchanged original/certificate commitments; no remint, timestamp/miner mutation or reward on provisional/losing candidate. |
| No media / reviewer integration | Long idle run, later certified input, frozen height/epoch, all-unsure and all-penalized deadlock explicitly observed; no fabricated media/control record. Candidate certificate validated before its own finality. |
| Reorg/promotion/recovery races | Generic stale save, import, reorg, Q4 promotion and downstream application cursors preserve anchors and complete durable sources; failed transaction exposes no finality; postcommit lost ack is idempotent. |

Require **four independently operated node processes with separate databases and
fenced signing authorities**, controlled network delay/drop/reorder/duplication,
real signatures from published test-only fixtures, process termination and
restart. At least one campaign must use separate hosts/operators and target
filesystems, not one process counting synthetic votes or shared-file two-node
fixtures. Native/engine adapter historical verifier interoperability is tested
against the approved route; they are not presumed wire compatible. Retain signed
transcripts, source bytes, model/version/config and deterministic replay results.

## 12. Bounded implementation roadmap — none begun

Every row is a separately authorized, reviewable/committable task, split further
if necessary. E1..E11 are new roadmap labels, not approval to execute. Local 7.17E
received-finality repair is already committed and is not reopened here.

| Task and prerequisites | Likely files | Expected tests / safety invariant | Version boundary / active behavior |
| --- | --- | --- | --- |
| E1. Owner trust/protocol/route approval; prerequisite this report and 7.17F | Decision docs, release/security specification | Approve independent N4/f1/q3, T1 exact variant, static emergency halt, finalized-parent/decision priority, native versus engine route and review budget; recorded authority cannot be inferred from this document | Documentation only; no active change |
| E2. Freeze G2/agreement/message/media schema; E1 and explicit application/history scope | New isolated profile/schema/fixture paths; `protocol_v1_genesis.py` only through version dispatcher later; frozen `canonical_v3` untouched | Independent complete genesis/preimage/Q4/negative vectors, no circular G/proof hashes, cap accounting, historical dispatch; identical bytes/context | New inactive G2/profile, agreement1/Q4/new block grammar; no active change |
| E3. Durable anti-equivocation journal/key authority; E2 exact bytes + transition model, fenced custody/rollback operating contract | New isolated signer/journal module and tests, storage adapter; reuse `storage.py` durability patterns | All reservation/sign/release crash windows, duplicate/conflict races, stale disks/clones, lock/W/PV replay; no released signature without durable permitted state | Inert new namespace only; no operational signer or key generation, no active change |
| E4. Authenticated static membership; E2 | New authority verifier, future config/genesis dispatch, full-key recovery adapter | M/C/G binding, order/point/ID/epoch/f/q forgery and wrong network; only genesis keys authorize | New inactive profile only; no live roster/config changes |
| E5. Exact proposal/vote/lock/round state machine; E3/E4 + reference conformance/model review | New consensus service/event log and proposal adapter; future `services/block_production_service.py`/validation adapters | Hidden commits, split proposals, lock transitions, nil, future rounds, old decision, full-size delay and input unavailability; one reference process across crashes | Isolated harness initially; integrating callbacks later changes behavior only at approved profile boundary |
| E6. Transactional decision promotion/proof/fault persistence; E5 + approved deterministic application predicate | `blockchain.py`, `storage.py`, finality/fork-choice/reorg adapters, new proof store | Concurrent promotion/reorg/stale writers, incomplete source/cursor, unknown outcome, retained contradictions; one monotonic finalized ancestry | New-profile paths inert until activation; active old-family semantics retained |
| E7. Consensus and proof/source sync; E4–E6 interfaces | `services/peer_chain_sync_service.py`, peer transport/message schemas, `peer_sync.py`, new consensus gossip | Bounded malformed/flood handling, actual PV fetch, same-tip proofs, genesis sync, missing originals, mixed-version refusal | Versioned capabilities; test-only initially, no production enablement |
| E8. Independent adversarial/security campaign; E3–E7 | Model and integration/process/network test harnesses, signed fixture transcripts, security report | Section 11 including four processes/hosts, crashes, partitions, independent verifier, resource/physical durability; no conflicting honest decisions and conditional convergence | No activation; external review/signoff gate |
| E9. Reviewer-history reconciliation specification; E1–E2 finality contract and owner policy choices, can precede E5 development | Explicit successor to 7.17B/7.17A, history/admission/clock/capacity specs | Noncircular timeline, exact selection/unsure, source completeness, bootstrap, stale-parent refresh, strict-media/control decision; same prefix -> same reviewer state | Documentation only; no automatic approval/implementation of P4/C3/V4 |
| E10. Implement/replay approved history integration; E6–E9 and separate authorization | New isolated history/replay/claims adapters, promotion and source sync; `canonical_v3/history.py` only as frozen reference | Separate fresh DB source-only replay, quota/penalty/issuance/races and one-media limits; no local labels as historical authority | New inactive combined profile; no active behavior before gate E11 |
| E11. Controlled activation/recovery release; E8/E10 plus owner-approved launch/state disposition and supported dependency/security review | Release/genesis manifests, config dispatch, operator/recovery/rollback runbooks, separately authorized deployment tools | Version refusal, dry-run observer sync, signer fence restore, lost-key/stalled-quorum/fault drills, finality vs application cursor; retain historical meanings | **Changes active behavior only with explicit separate launch approval**; no activation/reset/migration/deployment in this task |

If an external engine is selected, E2–E8 use its native formats/state/WAL and an
explicit media/application inclusion/recovery mapping instead of implementing
the candidate EIP-191 wire format. Reopen schema review; do not ship two engines
or translate signatures heuristically. Approve any non-media engine history
first. No row treats engine selection as automatic closure of review gates.

## 13. Decisions and readiness

| Owner/security decision | Current status |
| --- | --- |
| Trust/fault model | Recommend independent static permissioned N4/f1/q3, cumulative historical key/custody assumptions and no live rotation; **PENDING owner approval** |
| Agreement | T1 Algorithm1 is the concrete recommendation; full reference binding supplied. **PENDING owner/independent review**, no claim of implemented BFT |
| Implementation route | Native faithful implementation needs substantial new consensus/security work; reviewed engine feasible subject to lifecycle/proof/recovery compatibility. **BLOCKED for implementation-route freeze** |
| Authority/signed-byte schema | Candidate M/C + proposal/vote/PV/Q4 bytes specified; complete G2/A registry and combined block/application schema/vectors still **BLOCKED for API freeze** |
| Parent/fork choice | Recommend unique immediate finalized parent and decision priority over provisional score; substantive behavior/availability choice **PENDING approval** |
| No media | Preserve media-only canonical blocks and acknowledge stalled reviewer height clock. Control-history, idle optimization and global clock policy remain separate **BLOCKED** gates |
| Private safety / operating contract | Logical state and release sequence now specified against a concrete protocol; exclusive key fencing, rollback defense and physical durability must be selected/tested before signing |
| Reviewer history | Bootstrap, exact cohort/all-unsure, preliminary admission, source/issuance, local-control scope and clock semantics still **BLOCKED**; 7.17B not approved |
| Launch | Actual keys/operators/NID/G, release distribution, state disposition/activation boundary and deployment all **PENDING and outside this task** |

**Can durable signer implementation now be safely specified? Yes:** this proposal
identifies the exact private logical state, reference transition predicates,
candidate signing preimages and reservation/release/restart contract. A separately
requested specification/vector task can use them without inventing an unlock.
**Can a production or engine-specific signer be implemented now? No:** owner/route
approval, complete G2/A/application schema and independently checked signed byte
vectors, modeled transition conformance, fenced key ownership and stale-disk
operating contract remain prerequisites. No next task is begun. An inert journal
implementation would likewise need its explicitly frozen contract and separate
authorization; this document does not implicitly grant either.

**Can Task 7.17 resume? No.** Protocol selection work advances the agreement
specification gate, not the authority/signer/agreement/sync implementation,
adversarial verification or reviewer-policy/clock gates. Local 7.17E durability
is reusable within its tested scope. The distributed foundation and reconciled
reviewer history are not yet implemented or approved.

## 14. Focused verification and final scope

Existing tests only; no new consensus tests, signer APIs, keys or state-machine
implementation were added. The selected 7.17C diagnostics use public identities/
synthetic authentication and retained fixtures; v1/v3 golden/conformance cases
use published fixtures/fixed test scalars. The 7.17E suite's `Account.create()`
vote fixture was deliberately not invoked under this task's no-new-signing-key
constraint. Its regression source was inspected; only its key-free SQLite
settings/connection/nested-transaction test was rerun. This is not a rerun of the
full 7.17E crash/concurrency suite.

```powershell
New-Item -ItemType Directory -Force temp/task717g-runtime | Out-Null
$env:TEMP=(Resolve-Path temp/task717g-runtime).Path
$env:TMP=$env:TEMP
.\.venv\Scripts\python.exe -B -m pytest tests/test_milestone_7_task_7_17c_finality_audit.py tests/test_milestone_7_task_7_17e_finality_durability.py::test_settings_connection_ownership_and_nested_begin tests/test_protocol_v1_golden_vectors.py tests/test_milestone_7_task_7_10c_v3.py -q --tb=short --basetemp=temp/task717g-focused --junitxml=temp/task717g-focused.xml
```

**145 passed in 47.73 seconds; no failures, errors or skips.** Disposable output:
`temp/task717g-focused.log` and `.xml`; CPython **3.13.5**, SQLite **3.49.1**.
No full suite, actual BFT engine,
independent Byzantine node campaign, performance benchmark or new-profile
interoperability is claimed. Historical unsafe-behavior diagnostics remain
historical witnesses, not BFT acceptance tests.

Final changes are limited to this new document and a reference/status paragraph
in 7.17D. Branch/HEAD/index stay unchanged. No production code, test, frozen
canonical schema/vector, live database, validator authority, activation, chain
reset, deployment, bounty, commit, push or merge is changed/performed.

Final checks: UTF-8/no BOM, final newlines, balanced code fences, no trailing
whitespace and all local links pass. Removing the 17-line 7.17G follow-up from
7.17D reproduces its HEAD body exactly after line-ending normalization. JUnit
independently confirms 145 tests, zero failures/errors/skips; resource arithmetic
was recalculated. `git diff --check` passes, index has no staged changes, and
the only worktree changes are this new untracked file and the unstaged 7.17D
follow-up. Branch/full HEAD remain those in section 1. No new-protocol safety
proof or BFT readiness claim follows from documentation checks.
