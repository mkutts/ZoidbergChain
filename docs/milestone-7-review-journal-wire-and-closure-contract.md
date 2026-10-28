# Milestone 7 Task 7.17R — Test-only review journal wire and closure contract

Date: 2026-10-27, America/New_York. **Inactive specification and verification only.**

**Task 7.17S follow-up (2026-10-28):** The
[isolated cryptographic verification report](milestone-7-review-journal-cryptographic-verification.md)
adds real disposable public OPEN/VOTE, time and consensus signatures for this
laboratory profile, independent Python/JavaScript verification and static test
membership/quorum checks. Its complete laboratory transcript still returns
INCOMPLETE_HISTORY; signature validity does not establish authoritative finalized
history, physical-clock trust or Tendermint execution. This closes the isolated
new-domain signature-vector gap only. Production G2 journal authority, source
policies, schema approval, clock trust and two-stream agreement/custody remain
blocked. R's historical fixtures and placeholder signatures are unchanged.

R717 is a proposed, closed **laboratory binary profile**, not a production version
assignment or permission to activate a journal. It specifies a separate BFT review
history, authenticated-time deadlines, bounded mandatory closure pages, and exact
cross-history references. The numeric profile is an explicit test selection.
Physical time trust, application source policies, G2 amendments, real new-domain
signature vectors, two-stream agreement/signing refinement, and combined media
serialization remain production blockers. Unresolved policy returns UNSUPPORTED;
it is never replaced with a successful default.

All finalized eligible admissions before the agreed cutoff count, including
negative and unsure votes. Producers cannot select a replacement subset.
Originality and admissibility remain independent, with five eligible participants,
one established participant and the exact 70% decisive threshold **per dimension**.
The producer-selected cohort in historical 7.17N is superseded, not reinstated.

## 1. Repository prerequisites, scope and reconciliation

| Before edits | Observed result |
| --- | --- |
| Branch | `Compression-State-Bloat-and-Node-Economics` |
| HEAD | `768f0d460eab1def068a14ba5666e9e7aa625ba0` |
| Separately committed Q | `c1af685` contains Q verification; HEAD `768f0d4` contains Q report/tests and gate notice |
| Complete index/worktree, including untracked files | Empty `git status --porcelain=v1 --untracked-files=all` |
| Q report/test/verification | Tracked; checked with `git ls-files` |
| Instructions | No applicable ancestor or repository `AGENTS.md`; no delegation |

Reconciled [O](milestone-7-network-wide-review-voting-protocol-decision.md),
[P](milestone-7-network-wide-review-journal-feasibility.md),
[Q](milestone-7-review-journal-capacity-and-clock-decision.md),
[I](milestone-7-bft-wire-and-signer-contract.md),
[G](milestone-7-distributed-finality-protocol-decision.md),
[L](milestone-7-g2-genesis-and-bootstrap-contract.md),
[M](milestone-7-g2-genesis-verifier-implementation.md), and
[N](milestone-7-reviewer-admission-policy-decision.md). Inspected P/Q models,
`dual_review.py`, `milestone5_policy.py`, `reviewer_reputation.py`,
`services/reviewer_eligibility_service.py`, `canonical_v3/evidence.py`,
`isolated_bft717k/verifier.py`, and M's authority adapter. Their existing authority
boundaries are preserved: K authenticates an isolated envelope/proof, M can return
`VALID_ENVELOPE_INCOMPLETE_POLICY`, and neither proves journal application policy.
Existing local reviewer records are not authenticated global history.

Changes are limited to this report, a Q link/gate notice, R717 verification tools,
fixtures and one focused test module. No production code/schema, signer, keys,
network, active finality, genesis, database, chain history, economics constants,
compression or bounty rule changes. No staging, commit, push, merge, migration,
reset, deployment, protocol activation or Task 7.17S. No signing is performed.

## 2. Authority, identities and durable signer separation

Provisionally use the same G2-authorized four validators, static epoch **0**,
equal weight, f=1, q=3. R717 needs **its own Tendermint instance** with the locking,
valid-value, round and durable-safety obligations in G/I; it is independent of the
accepted-media sequence. Three matching precommits authenticate a decision only
under those obligations, complete validity checks and the independently pinned
membership. This task does not implement or verify that new agreement engine.

Define context `Ctxt` in the exact order below. The full network string and G2
hash are directly present, not inferred from a peer or a user database:

```text
Ctxt = network:NID, genesis:B32, protocol:V1, instance:B32,
       validators:B32, membership:ZERO64, policy:B32
```

`instance` is SHA256 of the G-independent journal descriptor; `validators` is I's
manifest commitment C; `policy` is SHA256 of the complete, G-independent R717
policy/limits descriptor. G2 must authenticate their full source bytes, manifest,
bootstrap and both stream descriptors before either stream has production
authority. Today's closed L/M envelope has no such complete journal amendment;
do not insert unknown fields into it and claim semantic acceptance.

After independently authenticating G, derive
`J0=T("origin", encode(Ctxt)||BD)` where BD is the authenticated 32-byte reviewer
bootstrap digest. Neither G2 nor its descriptor contains resulting J0. Journal
height starts at 1 with parent J0. Every consensus message binds Ctxt, height,
round, finalized journal parent, phase and value/nil. The value commits the entire
batch header and ordered event commitment. Round belongs to consensus messages,
not the batch value: the same valid value may be reproposed in a later round.

Signature purpose domains are `ZCRJ717R\0user-OPEN\0`,
`ZCRJ717R\0user-VOTE\0`, `ZCRJ717R\0time\0`, and
`ZCRJ717R\0consensus\0` (literal NUL bytes). None accepts a media-chain signature.
The consensus step byte further separates proposal, prevote and precommit.

| Durable material | Sharing rule |
| --- | --- |
| Independently pinned G2 bytes, manifest, read-only policy sources, verified content-addressed source bytes | May be shared, with explicit complete context and verified content IDs |
| Physical key custody infrastructure | May be shared only under a separately reviewed common exclusive-custody/fencing mechanism; key reuse is not signing authority |
| H/R/step slots, locks/valid rounds/values, decided parent, WAL/revisions, signed outbox and replay acknowledgments | Independent per stream and context; atomically durable before release; media height never advances a journal slot |
| Time-attestation sequence, selected sample, monotonic reading, reboot/error state | Independent journal namespace, durable before release; separate from consensus and user-vote slots |
| Journals, database recovery positions and fencing generations | Separate logical namespaces even on one device; one-stream rollback cannot authorize either signer |

An intact shared device failure can halt both streams. Lost/rolled-back private
safety state requires fencing and an approved recovery path; public history is
not permission to recreate a signer from empty state. **Do not extend or call J's
height1/round0 signer.** Separate domains alone do not implement durable custody.
Consensus slot uniqueness is `(authorized stream namespace,height,round,step)`;
parent, value, valid_round and proof are never added to that uniqueness key.
Time slots are `(authorized journal-time namespace,height,sequence)`; a changed
parent never permits a second selected reading in the same slot.

## 3. Exact canonical byte grammar

The normative inert encoder is [wire.py](../verification/review717r/wire.py);
the complete machine-readable ordered field registry is
[schema.json](../tests/fixtures/review717r_v1/schema.json). This section gives its
complete fields, not an open-ended JSON schema. JSON fixture objects are a display
notation; **binary bytes are the proposed R717 wire**. This deliberately differs
from O/I's JSON vote proposal and requires owner approval and new version dispatch.
It does not change the meaning or measured sizes of any O/P/Q object.

Primitive rules:

* `B<n>` is exactly n raw bytes; fixture notation is exactly 2n lowercase hex
  characters. Hashes are B32, submission/nonce B16, Wallet B20, compressed key B33,
  signature B65. No ASCII hex or `0x` appears on wire. A key must additionally be
  a finite valid secp256k1 compressed point. Wallet is the last20 bytes of
  Keccak256(uncompressed x32||y32), exactly as the existing family.
* `U8/U16/U32/U64` are fixed-width unsigned big-endian integers. U64 values are
  restricted to 0..9,007,199,254,740,991. `ROUND` is U32 <=2,147,483,647; `VR` is
  signed big-endian int32, -1 or a prior round. No bool, wrap, saturation, integer
  coercion or field omission. Overflow/exhaustion halts the transition.
* `V1` is U16 exactly 1; ZERO8/ZERO64 are integer zero in their named widths.
  `NID` is U8 length 3..64, that many ASCII bytes matching
  `[a-z0-9][a-z0-9-]{2,63}`, then zeros to exactly 64 bytes: 65 bytes total.
  Nonzero padding, unknown enum/version/type and trailing bytes reject.
* Arrays have a U8 count followed by exact records, in listed order. Count bounds
  are checked before allocation. CLOCK and proof arrays have exactly three
  members; no duplicate signer, padding member or implicit fourth member.
* No strings, optional fields, Unicode, null, extensions, maps or recursive wire
  containers exist beyond the specified NID and DATA bytes. Schema nesting is
  acyclic and <=4 record levels; an implementation may enforce a larger defensive
  parser-depth ceiling but cannot accept another grammar.
* Event framing is `kind:U8 || version:V1 || payload_length:U32 || payload`.
  Payload <=8,192 bytes, frame <=8,199. Only journal event kinds listed in section4
  may occur in a batch. Typed auxiliary objects are not automatically events.
* `T(tag,b)=SHA256(ASCII("ZCRJ717R")||00||ASCII(tag)||00||b)`.
  Hash text in this document is lowercase display only. `event_id=T("event",frame)`;
  `source_id=T("source-"||decimal(kind),raw_source_bytes)` for sourcekind 0..6.
  An INVENTORY object uses `T("inventory",encode(INVENTORY))`. Generic fixture
  `object_id=T(lowercase(record-name),record-bytes)` is a diagnostic ID; use the
  specified purpose ID, rather than this generic ID, for protocol references.

All required fields below are in exact wire order; concatenation has no separators.
`+Ctxt` means prepend its seven fields, not embed an untyped object.

| Record / payload maximum | Complete ordered fields |
| --- | --- |
| OPEN / 530 | +Ctxt; submission:B16, original:B32, creator:B20, key:B33, media_height:U64, media_hash:B32, base_height:U64, base_hash:B32, eligibility_root:B32, inventory:B32, nonce:B16, attempt:ZERO8, signature:B65 |
| START / 80 | sid:B32, open_height:U64, deadline:U64, time_id:B32 |
| VOTE / 508 | +Ctxt; sid:B32, submission:B16, original:B32, creator:B20, key:B33, media_height:U64, media_hash:B32, base_height:U64, base_hash:B32, deadline:U64, dimension:U8(0..1), choice:U8(0..2), nonce:B16, sequence:ZERO8, signature:B65 |
| ADMISSION / 528 | vote:VOTE, result:U8(0..9), first_height:U64, first_index:U16, status:U8(0..2), charged_epoch:U64 |
| CLOSE / 219 | sid:B32, deadline:U64, freeze_height:U64, count:U64, fold:B32, originality:TALLY, admissibility:TALLY, outcome:U8(0..2) |
| TALLY / 65 | positive:U64, negative:U64, unsure:U64, established:U64, total:U64, decisive:U64, numerator:U64, denominator:U64, outcome:U8(0..2) |
| PARTICIPATION / 88 | wallet:B20, submission:B16, epoch:U64, status:U8(0..2), first_height:U64, first_index:U16, used_after:U8, cause:B32 |
| EPOCH / 56 | previous:U64, current:U64, lower:U64, time_id:B32 |
| POLICY / 65 | old:B32, new:B32, result:U8 exactly255 |
| DATA / 8,182 | object_id:B32, total:U32, offset:U32, chunk_length:U16 then chunk:1..8,140 raw bytes |
| REFERENCE / 79 | kind:U8(0..6), object_id:B32, length:U32, height:U64, batch:B32, index:U16 |
| TIME_SAMPLE / 74 | validator:U8(0..3), reading:U64, signature:B65 |
| CLOCK / 231 | sequence:U64, samples:array[3] of TIME_SAMPLE |
| HEADER / 544 | +Ctxt; height:U64, parent:B32, previous_state:B32, events_root:B32, event_count:U16, event_bytes:U32, clock:CLOCK |
| MESSAGE / 383 | +Ctxt; height:U64, parent:B32, round:ROUND, value:B32, nil:U8(0..1), step:U8(0..2), validator:U8(0..3), valid_round:VR, justification:B32, signature:B65 |
| PV / 1,150 | votes:array[3] of MESSAGE |
| PROOF / 1,533 | proposal:MESSAGE, precommits:array[3] of MESSAGE |
| CHECKPOINT / 275 | +Ctxt; height:U64, batch:B32, proof:B32 |
| MEDIA / 862 | +Ctxt; checkpoint:CHECKPOINT, sid:B32, close_height:U64, close_batch:B32, close_index:U16, close_id:B32, submission:B16, original:B32, creator:B20, media_height:U64, media_parent:B32, count:U64, fold:B32, originality:TALLY, admissibility:TALLY |
| MEDIA_ANCHOR / 104 | height:U64, media_hash:B32, parent:B32, proof:B32 |
| INVENTORY / 2,529 | entries:array[1..32] of REFERENCE |

Except DATA and INVENTORY, every listed size is fixed, not merely a loose outer
bound. Event kind codes are OPEN1, START2, VOTE3, ADMISSION4, CLOSE5,
PARTICIPATION6, EPOCH7, POLICY8, DATA9, REFERENCE10, TIME_SAMPLE11, CLOCK12,
HEADER13, MESSAGE14, PV15, PROOF16, CHECKPOINT17, MEDIA18, TALLY19,
MEDIA_ANCHOR20, INVENTORY21. Standalone VOTE is a signed user object; only
ADMISSION4 embeds it into journal history. Auxiliary codes identify typed
transport objects; HEADER/MESSAGE/etc. cannot appear as arbitrary journal events.

## 4. Signing, object validity, ordering and evidence locations

For OPEN or VOTE let `unsigned` be its exact record bytes **excluding** the final
65 signature bytes. Let `M=purpose-prefix||unsigned`, with the corresponding
user-purpose prefix in section2. The signature digest is
`Keccak256(19||ASCII("Ethereum Signed Message:\n")||ASCII(decimal(len(M)))||M)`;
19 here denotes byte **0x19**, and `\n` denotes one **0x0a**. Decimal length has no
leading zero. Sign raw M using personal_sign; do not sign hex text or SHA256(M).
Require r in [1,n), s in [1,floor(n/2)], v exactly27/28, full recovered key equal
to key and derived Wallet equal to claimed creator for OPEN. A VOTE's reviewer
Wallet is derived from its signed key, not a caller-supplied address. R717's
low-S restriction is a proposed new-profile rule, not a change to I's old parser.

Time digest is Keccak256 of
`"ZCRJ717R\0time\0"||encode(Ctxt)||height:U64||parent:B32||sequence:U64||validator:U8||reading:U64`.
Consensus digest is Keccak256 of
`"ZCRJ717R\0consensus\0"||encode(MESSAGE without its final signature)`.
These two validator purposes use the raw digest, **without** an additional
personal_sign wrapper. The same low-S/recovery/registered-key checks apply.
This new raw-digest API is a custody/integration blocker; it is not supported by
relabeling J's personal_sign messages. No time sample signs its containing batch.

`sid=T("session",unsigned OPEN)` excludes signature variants. A vote-message ID is
`T("vote-message",unsigned VOTE)` and evidence ID is
`T("vote-evidence",complete VOTE)`. A batch ID is `T("batch",complete batch bytes)`;
a time ID is `T("clock",encode(CLOCK))` interpreted together with its authenticated
header Ctxt/height/parent. A proof ID is `T("proof",encode(PROOF))` or
`T("pv",encode(PV))`. Context checks are mandatory even when a content ID matches.

| Record | Validation predicate, canonical order and storage/retrieval |
| --- | --- |
| OPEN | Authenticated creator and complete inventory; base=(immediate finalized journal parent), media reference=current anchored finalized F; eligibility_root=prior replay commitment; attempt=0; no active/outstanding/consumed lock on submission or original. Full sources must pass approved technical, rights and qualification policies. Persist all bytes and source causes; fetch by SID, inventory and journal range. Unsupported source policy blocks OPEN, never sources_valid=true in a real verifier. |
| START | Unique mandatory record for every OPEN at exactly the following height, in SID order, using this header's fresh CLOCK; no source or creator approval shortcut. Derived deadline=median+epsilon+W. Retain OPEN/START and their headers/proofs. No same-START-height votes. |
| Signed VOTE | Exact context, SID, immutable submission/original/creator/F/base/deadline and dimension; valid eligible noncreator key; sequence0. No replacement. Locally pending bytes have no authority; retain complete VOTE inside its ADMISSION once ordered. |
| ADMISSION | One authenticated attempt, with exact replay-derived result/status/first locator/charged_epoch. Reject invalid signatures/foreign context at batch validity, rather than claim admission. No claimed acceptance flag can override replay. Locate by h/event-index; no containing batch hash inside itself. |
| Duplicate/equivocation outcome | Result1 duplicates first admitted same-choice slot, result2 conflicts with a different signed choice. Both retain the first admission's h/index/status/charged epoch; no new charge/count. Preserve both source messages for conflict. Group incident by SID/dimension/Wallet, not nonce or signature pair; penalty activation is UNSUPPORTED until its full source policy is approved. |
| CLOSE + TALLY | Mandatory unique next page, exact incremental count/fold/two tallies and earliest logical freeze height. No caller vote list or external tally authority. First page events; retain every CLOSE, all admissions and their prefix. Index by SID and (h,batch,index); full range replay supplies completeness. |
| PARTICIPATION | Mandatory immediately after the ADMISSION that first charges (Wallet,submission); cause=that ADMISSION event ID, locator=its actual h/index, status/epoch/used_after are derived. No separate signed grant. Never emit for duplicates, rejections or a later dimension. No new reward/issuance. Retain forever with charge causes; used_after <=5 or25 by frozen status. |
| EPOCH | If floor(L/300) changes, exactly one mandatory transition after CLOSEs/STARTs, before optional work; previous=prior epoch, current=floor(L/300), lower=L, time_id=this CLOCK. Skip unused epochs in one event; no bulk quota awards. Retain and retrieve by epoch/range. |
| POLICY | Only result255 (UNSUPPORTED_POLICY), old=current policy; new must differ; no state mutation. Membership/policy cannot change through this record. A successful transition needs a new approved governance/version contract and vectors. |
| MEDIA_ANCHOR | At most one, first optional event; no OPEN in that batch. Must verify the next already-finalized media block and its parent/proof against current anchor, canonical media checks and complete sources. It cannot reference media awaiting this batch. Retain full media/proof sources and anchor; unsupported block grammar blocks it. |
| DATA / REFERENCE / INVENTORY | Auxiliary evidence transport, not autonomous state transitions. sourcekind0=media,1=rights,2=technical,3=qualification/history,4=offense,5=journal proof,6=policy. Inventory entries ordered strictly by (kind,object_id), no duplicate ID. Fully resolve exact length and source_id. Non-journal source locator=(0,zero32,0); positive h requires a verified journal batch/event locator. DATA pages have matching total, offset>=0, contiguous nonoverlapping exact coverage and matching whole-object commitment. Gaps, corruption, extra bytes and cycles fail closed. |
| HEADER | Exact predecessor/height/context, event bytes/count/root, correct prior replay commitment and CLOCK. events_root=T("events",concatenated frames). Retain complete body, not just header/root. |
| CLOCK | Exactly three distinct sorted validator indices, correct signatures/context/next height/parent, sequence=height, authenticated monotonic samples and median/pacing rules in section6. Retain samples and complete header with proof. |
| MESSAGE/PV/PROOF | Exact context, height/parent/round/value/phase; proposal is scheduled `(h-1+r)%4` in manifest-key order. PV contains three sorted distinct matching prevotes. PROOF contains scheduled proposal plus three sorted distinct matching nonnil precommits; all bind the batch ID. Nonnegative proposal valid_round must be <round and reference complete matching PV; -1 requires zero justification. Votes require valid_round=-1/zero justification. nil=1 requires zero value and nonproposal; nil=0 never means missing data. Full validity/ancestry/refinement checks remain necessary. |
| CHECKPOINT / MEDIA | Authenticate complete ancestry from pinned J0 to checkpoint; CHECKPOINT proof ID must match its actual batch proof. MEDIA repeats exact materialized PASS source, target, parent and derived dual tallies/fold/count. Retain full dependency prefixes; MEDIA alone is not proof of completeness or retrieval. |

Admission results are exactly: 0 ADMIT, 1 DUPLICATE, 2 CONFLICT, 3 LATE (including
not started), 4 WRONG_SESSION, 5 WRONG_BINDING, 6 INELIGIBLE, 7 PENALIZED,
8 QUOTA_EXHAUSTED, 9 STALE_SESSION. Outcome0=UNDECIDED,1=PASS,2=FAIL;
status0=none,1=probationary,2=established. Reject a zero status for ADMIT.
For a rejection without a prior admission set first_height/index/status/charged_epoch
to zero; zero does not denote a real first admission. Duplicates/conflicts use
their actual prior locator. Every containing header binds the omitted context of
derived control records. No control has an independent signing authority.

Global transition order is: verify CLOCK and logical cutoff; exact CLOSE page;
exact prior-OPEN START list; EPOCH if due; optional MEDIA_ANCHOR if present;
then optional OPEN/ADMISSION/POLICY in decided array order, with each required
PARTICIPATION adjacent to its ADMISSION. At most16 new OPENs; live OPENs awaiting
START plus unmaterialized sessions <=4,096. A valid OPEN cannot be left unstarted.
New OPENs cannot take votes in their own or their START batch.

Unresolved semantics have explicit outcomes: UNSUPPORTED_RIGHTS_POLICY,
UNSUPPORTED_TECHNICAL_POLICY, UNSUPPORTED_QUALIFICATION_SOURCE,
UNSUPPORTED_REPUTATION_TRANSITION, UNSUPPORTED_RETRY, UNSUPPORTED_G2_POLICY,
UNSUPPORTED_MEDIA_SCHEMA. These are verifier failures/readiness gates, not new
positive ADMISSION codes. Tests supply named trusted facts for these layers;
those facts must never become a production boolean bypass.

## 5. Authoritative admission and complete tally

A user creating/signing a vote, one node receiving it, peer relay, local pending
pool acceptance and batch proposal are all **pre-admission** states. Only an
eligible ADMIT transition in a valid BFT-finalized batch consumes quota or adds a
tally slot. A proof without complete body/source validation does not establish
such a transition. Counted means that immutable admission falls before the
logical boundary in the complete verified session prefix.

The signed object and admission are distinct: VOTE authenticates the user's exact
choice; ADMISSION binds that complete object into one authoritative ordered
history and records the uniquely derived disposition. The counted slot is
`(Ctxt,SID,dimension,derived reviewer Wallet)`. First finalized eligible admission
wins; subsequent same-choice variants are duplicates, different choices conflicts.
Neither replaces a previously admitted unsure/negative/positive. A wrong session
or target cannot borrow an earlier signature; foreign N/G/instance/version rejects.
At/after cutoff, classify LATE before duplicate handling; prior counts are immutable.

For every ADMIT in order (h,event_index), increment exact counters and fold:

```text
R0 = T("empty-votes",SID)
Ri = T("vote-step", R(i-1):B32 || ordinal:U64 || h:U64 || event_index:U16
        || vote_message_id:B32 || vote_evidence_id:B32 || derived_status:U8)
```

Ordinal starts1. It includes **all** admitted dimensions, with no chosen list.
Own batch hash/proof is absent, avoiding circularity. Full authenticated prefix
replay establishes completeness; the fold is not a Merkle inclusion/absence proof.

For each dimension p,n,u,e are admitted positive/negative/unsure/established counts.
`total=p+n+u`, `decisive=p+n`. Quorum requires total>=5 and e>=1.
Quorum plus decisive>0 resolves PASS iff `10000*p>=7000*decisive`, otherwise FAIL.
No quorum or decisive0 means UNDECIDED. Reduced ratio is p/decisive using gcd;
when decisive0, numerator=denominator=0 explicitly denotes no ratio. An actual
zero approval with decisive>0 is 0/1. Combined FAIL if either dimension FAIL;
PASS only if both PASS; otherwise UNDECIDED. Thus (7,3,0;1) passes exactly,
(6,3,0;1) fails, (1,0,4;1) passes under the preserved decisive rule, and all-unsure
never approves. Checked products must not overflow. Frozen established status is
never retrospectively promoted or removed from admitted votes.

## 6. Clock selection, hybrid cadence and trust boundary

| Minimum clock | What it solves | Limitation |
| --- | --- | --- |
| A. Heights + periodic service | Replay, ordered cutoff, idle closure if consensus advances | +256 gives **no minimum real duration**; hostile fast progress can renew quotas/expire penalties too quickly. Periodic intent is not a consensus time authority. |
| B. Heights + authenticated timestamps | Elapsed-time cutoff and bounded intended cadence under explicit trusted-clock assumptions | Requires clock error, fresh sampling, durable monotonicity and oracle review beyond BFT signatures. |
| C. Explicit service epochs | No-media quota/penalty progress and deterministic catch-up | An optional epoch record is censorable; without an authenticated rate it has A's timing weakness. |

Select **B plus mandatory C transitions** for the test contract. Test units are
integer seconds, epsilon=1, window W=1,200, epoch span300. Their absolute origin
is an owner-approved G-independent Unix-seconds convention/origin in the future
policy descriptor; laboratory inputs deliberately use small synthetic integers,
not claimed current timestamps. Active minimum median increment5; idle increment300.
The launch origin, epsilon, W, period and pause/grace policy require owner approval.

Every honest time signer must have a justified absolute-error bound <=epsilon,
observe the exact finalized parent **before sampling**, bind next height/parent/
sequence, and durably issue one selected sample per slot before releasing it.
It must wait for the active/idle pacing interval, maintain monotonic readings
across reboot, and abstain on uncertainty, rollback, broken synchronization or
overflow. Fresh honest service after synchrony is a liveness assumption. No verifier
uses its own receipt time, current date or clock to reinterpret old samples.

For a CLOCK, m=median(three readings), L=m-epsilon. Require m>=epsilon,
m>=prior_m+5 if the prior state has pending START or unmaterialized sessions;
otherwise m>=prior_m+300. Require L nondecreasing, checked W/epsilon arithmetic,
and matching sorted authorized signers. No upper time-jump limit is imposed:
after outage the fresh quorum may legitimately jump far ahead. Do not invent one
event for each missed second/epoch. An event-driven OPEN waits for the next valid
idle checkpoint; the selected test policy explicitly permits up to300 seconds
of intended idle batching delay. Active service aims to propose each5 seconds,
idle each300, with byte/work-full batches subject to the same authenticated pace.
No wall-clock upper latency bound exists without available quorum and synchrony.

At the height following OPEN, mandatory START uses that height's fresh m and
sets D=m+epsilon+W. Sampling occurs after its parent containing OPEN finalized.
With two honest samples among three, their median is between honest samples;
therefore D cannot precede real OPEN+W under the absolute-error/observation
assumptions. A later proof whose L>=D cannot complete before D in real time under
those same assumptions. It freezes every due session **before optional events**.
Extremely fast/slow Byzantine readings alone cannot move the median outside
honest readings, although stale selected honest inputs can delay progress.

No consensus means no new authoritative clock, votes, epochs or closes. After
temporary unavailability the first fresh proof freezes expired sessions before
new votes; there is no receipt backdating or automatic connected-time grace.
Elapsed opportunity does not guarantee user connectivity or admission fairness.
Clock-error trust is **not established by this task**, so production remains
BLOCKED even though identical finalized inputs replay deterministically.

## 7. Mandatory closure, bounded derivation and capacity argument

Logical closure is the predicate `started && D<=current_L`. It applies to **all**
sessions immediately at the first crossing, whether or not CLOSE is materialized.
It needs one session lookup and comparison; no global freeze-event enumeration.
No vote, duplicate replacement, grace or retry can mutate that session afterward.

Maintain an authenticated replay-derived expiry index of unmaterialized sessions
ordered by **(D,SID)**. Its total size including pending STARTs is <=4,096, enforced
at OPEN. At every height choose exactly the first min(16, number_due) entries,
where number_due means D<=this header's L. All their CLOSE records must lead the
batch, byte-identical to replay. Missing, duplicated, reordered, extra or fabricated
CLOSE invalidates the batch. Materialization removes the index entry and stores
the immutable CLOSE locator. A proposer cannot legally substitute optional work.

The proposed deterministic implementation uses an ordered radix index over the
53 significant deadline bits plus256 SID bits (<=310 node visits per keyed
access), or an equivalently reviewed bounded index. Examine at most17 entries
to determine the next page; do not scan
all historical sessions or their votes. OPEN/START update <=16 entries each;
admissions update cached counters/fold immediately. CLOSE reads constant-size
counters, never rehashes arbitrary vote arrays. Compute freeze_height as the
first finalized L>=D by binary search of retained monotonic clock-height records,
at most53 probes over the U64 range per close. Earlier boundaries need complete
verified retained ancestry. The model's list/deepcopy/history search is a small
reference experiment, **not** a measured or bounded database implementation.

All records use fixed bounded metadata. Mandatory byte reservation is:

```text
batch prefix + header               12 + 544                 =   556
16 CLOSE frames                     16 * (7+219)             = 3,616
16 mandatory START frames           16 * (7+80)              = 1,392
one EPOCH frame                      7+56                    =    63
TOTAL mandatory reservation                                  5,627
96 ADMISSION +96 new PARTICIPATION   96*(535+95)              =60,480
16 OPEN frames                      16*(7+530)              = 8,592
one MEDIA_ANCHOR frame (not with OPEN) 7+104                  =   111
```

The compatible mandatory+96-vote/charge+16-OPEN mix is **74,699 bytes**, 241
events; it fits 256 KiB and the256-event ceiling. The incompatible anchor/OPEN
pair is never counted as simultaneously permissible. Source/work constraints
still apply; maximum-shaped independent records are not an entitlement to a mix.

Why paging is safe: all due sessions are already logically frozen; full prior
admissions determine their stable counters/fold. Each valid successful height
removes up to16 of the earliest due entries. New starts have D>current L and
cannot jump ahead of an already-due entry, even after a later time jump. Thus a
given backlog of N due sessions is represented within ceil(N/16) successful
heights under continuing valid journal progress and available evidence. At most
4,096 live entries require256 heights. 1,000 require63;33 require3 (16,16,1).
No finite wall-clock completion bound exists during absent quorum or evidence.
All due votes stay LATE throughout those pages. SID/deadline and finalized clock
history decide order/freeze height; local insertion, receipt and restart order do not.

OPEN capacity can recover as pages materialize, but fresh sessions cannot starve
the due prefix. All bounds hold before optional work; compulsory metadata can
never exceed the body cap. This solution requires approval of implicit logical
freeze, START/EPOCH controls and CLOSE paging. Without those controls, **journal
implementation is BLOCKED**; silently dropping closures is not an alternative.

## 8. Batch format, deterministic work and Q size reconciliation

Batch bytes are exactly:
`ASCII("R717B001") || version:U16=1 || header_length:U16=544 || HEADER || frames`.
No reserved padding. <=256 events, <=262,144 total bytes including the12-byte
prefix and header. Header event_count and event_bytes are exact, events_root
covers every ordered length frame. Only OPEN, START, ADMISSION, CLOSE,
PARTICIPATION, EPOCH, POLICY and MEDIA_ANCHOR are application events. DATA and
inventories are separately bounded auxiliary evidence. The cap test intentionally
uses typed DATA frames to exercise generic transport framing **only**; such a
container is not thereby a valid application proposal.

The post-batch replay commitment is `T("state",previous_state||batch_id)`;
initial replay commitment is `T("initial-state",J0||BD)`. HEADER.previous_state
is that value from the preceding finalized batch. It authenticates a replay
transcript, **not** a succinct state/eligibility proof. OPEN.eligibility_root is
the same prior commitment. Full replay still derives actual qualification.
Own resulting batch ID, post-state and finality proof are never hashed into the
same batch. A PROOF is external, exactly1,533 bytes; a finalized transport unit
`batch || PROOF` has maximum **263,677 bytes**, with batch framing giving the
split. Any valid-round PV reference brings its separately retained1,150-byte
object/dependencies; round traffic and arbitrary unsuccessful rounds are additional.

| Q concept | Preserved fact / R717 proposal |
| --- | --- |
| 1,701-byte example /1,739 conditional bound | Exact sizes of O/P/Q's signed **JSON** vote; remain correct |
| 1,747 /1,785 framed events | Q JSON wrapper +4-byte length; not the new binary envelope |
| R717 signed vote | Exactly508 raw bytes; ADMISSION535 framed, or630 with a first-participation record |
| Q256KiB | Retained as a proposed test total-body ceiling, now every field is counted |
| Q96-vote/64-control checks | Retained **only as unapproved work inputs**; not inferred from bytes, CPU or production throughput |
| Q16*2KiB close allowance | Replaced for this new test format by16*226 bytes plus explicit START/EPOCH/header reservations |
| Q8KiB media review binding | MEDIA is862 bytes (869 if auxiliary-framed), below8,192; complete combined3MiB media schema/hash and maximum-fit vector are still BLOCKED |

Charge at most96 user-vote authentications and64 control-signature checks per
batch, plus3 time and4 finality-message checks: at most167. R717 currently has
only16 OPEN signatures in its directly embedded control lane, giving119 checks
before any external source or referenced PV signatures. Those additional checks
consume the same64-control budget; they are not free or unbounded. The
unused allowance does **not** authorize a new signed control type. Every
rejected/duplicate ADMISSION consumes a vote check. No declared `checks` field
can hide work. <=256 events and <=32 distinct new source objects/dependency
nodes per batch, each <=3,145,728 bytes (original media <=2,097,152), total new
source bytes <=67,108,864; dependency depth<=8, acyclic, and no duplicate source
count exemptions. Policies retain L's <=8,192 decoded bytes/source bound.

Conservative proposed execution ceilings are1,048,576 authenticated state-index
node visits,848 clock-history probes and source hashing <=64MiB plus batch and
proof bytes per batch. Keyed state is maintained incrementally; a sparse256-bit
index with at most3,000 keyed read/write operations consumes <=768,000 visits,
leaving room for expiry bookkeeping. These are deterministic **test limits to
validate/refine**, not a demonstrated implementation bound. Source technical
decoding, rights and reputation evaluation cannot claim this bound until their
approved interpreters/accounting are specified. An unsupported interpreter
blocks validation; a local CPU timeout never changes a consensus result to valid.
Native-host benchmarking, worst-case refinement and denial-of-service tests are
prerequisites before owner adoption of these limits.
The inert `preflight_work` helper enforces embedded counts only; complete source/
PV signature accounting and execution-visit metering are specified gates, not
implemented or measured by that helper.

Exact cap-1/cap/cap+1, field bounds, unknown versions/padding, truncated bodies,
wrong roots, event counts and work limits are exercised by the focused suite.
Transport structural acceptance is kept distinct from semantic authority.
With the presently supported small application records and work/count limits,
the256KiB limit need not be reachable by a semantically valid application batch;
no cap-sized valid application/finality vector is claimed. These exact-cap
transport cases establish the outer byte boundary, not missing source semantics.

## 9. Reviewer replay, quotas, epochs and retry blockers

Replay qualification from G2 B0 and complete finalized creator/native/reviewer
history, frozen at OPEN's `(F,prior journal prefix)`. Preserve existing age>=3
media epochs; creator2, native5 nonself spanning3 epochs, mixed1 minted+2 native;
creator/native/mixed priority; earned established requires10 distinct probation
participations plus3 media epochs. Explicit clean B0 grants are the only bootstrap
exception. NEW, self, cooldown and suspended reviewers cannot newly count.
Promotion after OPEN cannot add an established seat to its frozen snapshot.

Propose Q's narrow service-epoch amendment: E=floor(L/300) governs **only quota
renewal and penalty expiry**, independent of media progress. It does not advance
native/creator qualification age or probation duration, issue funds, change
validator membership or mint media. At the first ADMIT for (Wallet,submission),
charge E once for lifetime, across dimensions and any future approved retry;
caps remain5 probationary/25 established using the frozen status. Maintain exact
per-Wallet/epoch usage indexes and complete original charge records. Two concurrent
new targets compete in finalized order for the last slot. An existing submission
charge permits its second dimension only if other eligibility/penalty/cutoff
conditions pass. Failed/all-unsure/expired/stale reviews never refund a charge.
Local pending votes and gossip cannot create participation credit.

At EPOCH, jump directly to the new epoch. Unused allowances do not accumulate;
no retrospective admissions/credits. Historical epoch/charge/counters remain
immutable. Existing qualified reviewers can renew during no-media periods;
NEW reviewers still cannot invent earned media/native activity or age.

Preserve existing objective offense families and schedules as required policy:
equivocation cooldown3 then10; self-vote/quota abuse1 then3; third escalating
incident suspension25; cooldown violation extends to max(existing end,E+duration),
suspension violation does not extend; half-open intervals and suspension precedence.
Activation must be prospective at finalized authenticated evidence, without
subtracting old votes. Exact R717 evidence-to-incident grouping, qualification
source registry, cross-epoch lifetime probation credit, and the existing protocol1
offense-verifier adaptation remain **UNSUPPORTED** until approved source schemas
and vectors exist. The model supplies frozen eligibility and penalty-end facts;
it verifies arithmetic/ordering, not those missing cause verifiers.

R717 attempt=0 is the only supported OPEN. Expiration always produces CLOSE with
the actual tally. There is no automatic positive outcome, cancellation or reopen.
Terminal failure/history cannot be shopped away under a new submission ID for the
same original. An unresolved or stale-parent result cannot be reused at another
parent. Owner must select retry eligibility/count/delay and a freshly signed
successor session before retry implementation; R717 returns UNSUPPORTED_RETRY.
This intentionally leaves O's proposed one-retry/+256 delay unadopted rather than
silently convert heights to seconds. Full reviewer-history Task7.17 remains BLOCKED.

## 10. Availability, archival obligations and recovery

Before an honest value prevote/precommit, validate and durably retain the complete
batch, admitted signed votes, OPEN inventories, originals/rights/technical sources,
qualification/penalty causes, clock samples, required media/journal ancestors,
proposal/justification proofs and all dependency bytes. Verify canonical type,
length, source-to-commitment match and full ordered coverage before agreement.
Content roots and a signature set never establish retrieval of omitted bytes.

| Failure / operation | Required behavior |
| --- | --- |
| Storage full/error before signing | No successful custody claim or value vote; refuse/abstain and recover storage. Never promise source availability based on RAM-only data. |
| Crash after signing | Persist sources, signer slot/outbox and dependency indexes before release; on intact restart reverify sources and replay unique finalized prefix. A signed vote may survive without this node learning the decision. |
| Corrupted data | Hash/type/length mismatch quarantines it; fetch exact bytes from independent sources, verify again, halt dependent validation meanwhile. Never rebuild an empty vote set. |
| Missing range | Return INCOMPLETE_HISTORY/EVIDENCE, request bounded contiguous header/body/proof/source pages. Missing CLOSE cannot mean an open or approved session. |
| Proof sync | <=256 requested IDs/page, <=64KiB response frame, <=4 in-flight pages/peer; these are transport/resource proposals. Chunk full large objects; verify complete bytes before use. A proof-only response is incomplete application evidence. |
| Fresh node | Independently pin G, authenticate complete descriptors/membership, derive J0, replay all required contiguous journal/media histories and source causes. An archive's self-signed snapshot/root is not a new trust anchor. |
| Archive duties | All4 validators retain full application history plus at least2 independently operated full-evidence serving archives; source-only restore and repair after loss must be demonstrated. No eligibility/tally/source pruning rule is authorized. |
| Backups | Verified independent backups, antirollback signer custody, restore drills, operator retention/availability contracts and source repair are separate requirements. Serving replicas are not backups. |
| Unavailable authoritative evidence | Refuse media validation/finalization; recover or halt. Do not infer absence, no penalty, no negative votes or PASS. |

With store-before-value-sign and <=1 Byzantine, q3 includes >=2 honest validators
that checked/retained dependencies **at signing**. It proves neither perpetual
retention, two online sources in the future, correct backup independence nor
survival of correlated disk/operator loss. Archive availability and long-term
key-compromise/rewrite assumptions must be reviewed independently. Permanent
source loss can make an otherwise signed history permanently unverifiable.
No bounded finite lifetime storage claim covers unlimited hostile round attempts.

## 11. Journal-to-media boundary and allowed checkpoints

The dependency graph is acyclic:
`G-independent descriptors -> pinned G -> J0 -> finalized OPEN -> START ->
admissions -> logical cutoff -> materialized CLOSE/checkpoint -> media child ->
later MEDIA_ANCHOR`. The anchor of that media child cannot be its own prerequisite.

Complete proposed media verification order:

1. Authenticate full G2 against an independent release pin, including supported
   source policies and both stream origins. M's incomplete-policy verdict cannot
   be upgraded to success.
2. Authenticate the journal manifest/commitment/static epoch0 from that genesis.
3. Verify complete finalized journal header/body ancestry and consensus proofs,
   all domains, scheduled proposers, round justifications and parent bindings.
4. Retrieve/reverify complete admitted user-vote objects and dependency evidence.
5. Replay OPEN eligibility snapshots, live ordered quotas/penalties, epochs,
   every admission/disposition and all mandatory START/CLOSE transitions.
6. Confirm materialized CLOSE and exact deterministic dual PASS, full count/fold,
   source locator and first logical cutoff. A pending logical freeze alone is
   insufficient for media acceptance.
7. Compare exact submission, original SHA256 and creator to candidate source bytes.
8. Compare the MEDIA binding's exact Ctxt, checkpoint, CLOSE ID/locator, counts,
   fold, both complete tallies and parent. There is no producer replacement array.
9. Authenticate the candidate's immediate finalized **media** parent F and require
   it equals the OPEN/vote/media-reference F. Journal height is not media height.
10. Apply all existing canonical media/codec/rights/native transaction and reward
    checks under the future approved combined schema/hash. No journal-only pass
    bypasses them.
11. Reject an original identity already consumed in finalized media history and
    conflicting submission claims as required by the approved media policy.
12. Refuse finalization on missing/unsupported authoritative data at any step.

The permitted checkpoint is **exactly the batch that materialized this CLOSE**,
with that batch's real proof and verified ancestry. It is already finalized before
the media candidate is built. Later journal progress does not invalidate this
immutable result or require chasing a moving latest tip. Later penalties never
reclassify earlier admissions. The actual current finalized media parent must
still equal F; a sibling media win makes the result stale and unusable. Two passing
sessions cannot both authorize different children of a finalized parent under
safe media BFT. A later journal anchor records an already-finalized media child;
the next usable media context is opened only after that anchor. No atomic commit
between independent BFT instances is required or claimed.

The R model checks exact references, old-finalized-checkpoint stability, stale
media parent, consumed original, missing evidence and unsupported G2. It does not
implement combined media canonical checks or MEDIA_ANCHOR verification.

## 12. Canonical examples, independent checking and test scope

[vectors.json](../tests/fixtures/review717r_v1/vectors.json) contains literal full
hex, byte counts and SHA256 for OPEN, positive/negative/unsure VOTE, duplicate,
invalid signature, ADMISSION, CLOSE, TALLY, quota exhaustion, EPOCH, CHECKPOINT,
MEDIA binding, wrong-network replay, missing evidence reference, conflicting-proof
shape and unsupported policy. User signing preimages are also literal hex with
SHA256 checksums; SHA256 is **not** their Keccak signature digest.
[results.json](../verification/review717r/results.json) retains same-boundary
33-session CLOSE pages with full record objects, exact frame hex and page hashes.

These are **illustrative independent structural examples**, not one internally
valid complete production history: e.g. TALLY demonstrates7/10 while the CLOSE
fold demonstrates one admission; MEDIA separately demonstrates dual PASS.
All signature fields are deliberately invalid zero placeholders. No new key or
signature is produced. Positive/negative/unsure denotes the signed-choice field,
not successful authentication. Invalid-signature and conflicting-proof expected
results explicitly reject under real verification. Successful cryptographic
OPEN/VOTE/time/finality vectors are a BLOCKED readiness gate, not passed tests.
The fixture context uses network `r717-laboratory`, G=`11` repeated32 bytes,
instance=`22` repeated32, validator commitment=`33` repeated32 and policy=`44`
repeated32. These are named synthetic markers, **not** computed/pinned launch
genesis, descriptor, roster or policy hashes. Descriptor/G2 source freeze and
their real independently checked identity vectors remain prerequisites.

[oracle.cjs](../verification/review717r/oracle.cjs) independently serializes the
ordered schema with Node buffers and BigInt, checks every byte/hash, independently
rebuilds the batch/event commitment, user/time preimages, vote fold and all three
CLOSE pages. It imports no Python encoder. Shared machine-readable field order is
the specified grammar, not a second source of semantic authority. This is an
independent SHA256/encoding check, not independent policy/BFT/crypto verification.

[focused tests](../tests/test_milestone_7_task_7_17r_wire_closure.py) cover closed
shape/version/bounds, exact cap and cap+1, malformed frames, immutable finalized
admission, dual tally/quorum/unsure/70%, duplicates/conflicts, concurrent quota
exhaustion and no-media renewal/expiry, wrong network/session/context, missing
evidence, conflicting proof facts, closure omission/order, logical freeze before
materialization,1/16/17/33/1,000 due sessions,4,096 capacity, replay/restart,
partition catch-up, failed review/unsupported retry, media subset/replay/stale
parent attacks, and Q historical cost-unit cross-checks. P's eight exact retained
unsafe controls are maintained without edits. None proves client inclusion fairness.

The model uses **explicitly supplied authentication/finality/source facts**;
its diagnostic JSON tip/fold, list index and deepcopy are not R717 wire/state
commitments or a production implementation. Wire-fold and encoding are separately
checked. Application state tests establish conditional safety for the modeled
transition rules, not a complete refinement proof of all schemas or sources.

## 13. Resources, recovery and three-year implications

All figures are arithmetic, **not demonstrated BFT throughput**. The new binary
profile has a535-byte framed ADMISSION, optional95-byte new charge,556-byte
batch prefix/header,1,533-byte commit proof and862-byte media binding. Clock
samples are already inside the header; do not add Q's1KiB allowance a second time.
Max raw event allowance remains8,192, but actual CLOSE219/OPEN530 are smaller.

At five-second successful heights the96-check vote lane gives1,152 signed
dimension votes/minute; body bytes leave substantial unused room. 10/100 fit this
arithmetic envelope,1,000 leaves limited recovery margin,10,000 exceeds it by8,848
votes/minute. An embedded maximal vote/OPEN mix uses119 signature checks;
167 is the ceiling including any referenced source/PV signatures. At100 votes/min plus active finality/time
overhead, about3.07 checks/s plus OPEN checks are required. Millisecond/core/disk
throughput is unknown until measured. A10,000-vote burst needs at least105 full
vote heights, excluding other work and expired sessions.

The retained calculator assumes100 signed dimension votes/session, constant active
5s heights (17,280/day), 288 epoch transitions/day, one worst-case new charge per
vote,96-byte per-event and64-byte per-height index estimates, no compression,
1,095 days. Per-session OPEN/START/CLOSE are included. Separate sources, technical
data, unsuccessful round logs and complete qualification/offense inputs remain
additional: this is **not** a full archive upper bound. Fewer participation charges
reduce these figures; unapproved source-retention duties can dominate them.

| Signed votes/min | Logical GB/3yr per archive | Four validators GB | Two extra archives GB | Physical primary GB (1.25x) | Backup GB/copy (3.8x physical) | Full logical transfer days at100Mbps |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 10 | 53.929083 | 215.716332 | 107.858166 | 67.411 | 256.163 | 0.050 |
| 100 | 172.195705 | 688.782822 | 344.391411 | 215.245 | 817.930 | 0.159 |
| 1,000 | 1,354.861931 | 5,419.447724 | 2,709.723862 | 1,693.577 | 6,435.594 | 1.255 |
| 10,000 offered, unserviceable | 13,181.524187 | 52,726.096748 | 26,363.048374 | 16,476.905 | 62,612.240 | 12.205 |

Idle hybrid checkpoints cost **729,112,320 bytes/3yr** under the same header/proof/
index/epoch assumptions. This excludes real synchronization/backup/media overhead.
All six serving archives store6x the per-copy logical result; backups are separate.
The transfer column is bytes/bandwidth only, without parsing, signatures, source
retrieval, contention or repair; it is not a restore-time promise. Failed originals
at2MiB each add330.679GB at10/min and3.307TB at100/min over3yr under this session
assumption, before independent backups/replication. Retaining them is an owner
availability/budget decision; deleting required replay evidence is not permitted.

For comparison only, reusing Q/7.8's **historical2026-10-18 input prices**, one
whole node with1,000 representative media/day plus this R journal costs over3yr:

| Votes/min | Budget VPS USD | Mainstream cloud USD | Storage-focused USD |
| ---: | ---: | ---: | ---: |
| 10 | 1,236.26 | 5,395.70 | 2,050.99 |
| 100 | 1,515.75 | 7,122.96 | 2,223.41 |
| 1,000 | 4,475.66 | 24,725.62 | 4,314.52 |
| 10,000 unserviceable demand | 34,426.59 | 201,455.88 | 26,600.79 |

These are reproducible historical scenario sums, not current price quotations,
purchase recommendations or complete public-testnet budgets. Q's formula includes
one compute charge, eight-peer relay proxy, phase traffic, physical amplification
and four0.95 full backups. Network budget needs four independently operated
validators plus archive operators, backups, originals, custody and recovery costs.
Launch hardware selection requires native-host signature/decode/CPU/IOPS/round
latency, peak pending-pool/flood, snapshot/headroom and source-only restore tests.

## 14. Owner decisions, readiness and execution record

| Authority status | Decision / effect |
| --- | --- |
| ALREADY DIRECTED | Users determine outcomes; nodes gossip/verify signed votes; all finalized eligible pre-cutoff admissions count; no producer subset; independent replay agrees. Preserve separate dimensions and70%. |
| PROPOSED: prototype assumptions | Separate BFT journal; same static roster; R717 binary schemas/domains; epsilon1/W1200/5s-active/300s-idle clock; implicit freeze/16-CLOSE pages/4096-live;5/25 service epochs;96/64 work; source/retention limits. These are explicit test selections, not approvals. |
| REQUIRES OWNER APPROVAL | Architecture/authority and actual operators; real clock source/error/origin/window/partition policy; quota/penalty epoch scope; participation/promotion/retry policy; batch/work ceilings; indefinite archive/source responsibilities and independent copies; signing APIs; G2 and combined media amendments; public-testnet hardware/operating budget. |

| Readiness target | Status and prerequisites |
| --- | --- |
| Isolated byte/clock/closure application experiment | **READY FOR REVIEW** under named supplied facts; no production authority. Deterministic paging/bounds/serialization and retained independent encoding checks are available. |
| Isolated full cryptographic journal prototype | **BLOCKED** until separately authorized signing, exact supported source-policy contracts, new-domain crypto interoperability vectors and reviewed two-stream signer/agreement refinement. Model assumptions cannot fill these fields. |
| Production review journal | **BLOCKED** on owner architecture/clock/epoch/retention choices, physical time trust, G2/policy/media source semantics and full canonical integration, custody/data availability and independent safety review. |
| Public testnet | **BLOCKED** on all production gates plus actual membership/bootstrap approvals, benchmarks, storage/archive/restore demonstrations, operating budget and separately authorized launch. |
| Reviewer-history Task7.17 | **BLOCKED**; no integration/activation and no selected-cohort fallback. |

Prototype arithmetic/ordering work can proceed under these explicitly named
synthetic assumptions. Real identity grants/operators, final numeric launch
parameters, hardware purchase and deployment can remain unresolved for such an
experiment. A full crypto or application integration prototype cannot leave its
own signing/source semantics undefined and claim readiness. Owner decisions and
implementation readiness are separate gates even after approval.

Reproduce without signing or network access:

```powershell
python -B -m verification.review717r.vectors
python -B -m verification.review717r.report
node verification/review717r/oracle.cjs
python -B -m pytest tests/test_milestone_7_task_7_17r_wire_closure.py tests/test_milestone_7_task_7_17q_capacity_clock.py tests/test_milestone_7_task_7_17p_review_journal.py -q --tb=short --basetemp=temp/task717r-release-final --junitxml=temp/task717r-release-final.xml
python -B -m verification.review717r.audit --junit temp/task717r-release-final.xml
```

Final exact counts, interpreter versions, source/artifact hashes, preserved P/Q
files, independent-oracle output, constrained Git inventory and JUnit checks are
retained in [validation.json](../verification/review717r/validation.json). The
release run passed **204 tests:84 R +40 unchanged Q +80 unchanged P**, with zero
failures, errors, skips or timeouts. The independent oracle matched17 structural
vectors, the batch/time/user preimages, vote fold and three CLOSE pages. No
signatures were generated. The15-file constrained-delivery audit passed.
The
release suite is deliberately focused on R plus the complete unchanged P/Q
verification suites; no whole-repository, physical clock, new-domain crypto,
live/multi-host BFT, crash-custody, native-node throughput or archival restore
success is claimed. P's eight negative controls remain byte-for-byte unchanged.

Branch/HEAD/index remain at the initial values. Final worktree contains only the
named R deliverables and Q readiness/link notice, unstaged, including the new
untracked files. **Task7.17R is ready for review and a later owner-authorized
commit as an inert conditional contract/verification package.** No protocol
change is activated, production readiness is not claimed, and Task7.17S is not begun.
