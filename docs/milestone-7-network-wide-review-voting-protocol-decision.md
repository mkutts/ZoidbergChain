# Milestone 7 Task 7.17O — Network-wide reviewer voting protocol decision

**Task 7.17P verification follow-up (2026-10-27):** The
[journal safety and feasibility report](milestone-7-network-wide-review-journal-feasibility.md)
adds an isolated application model over an explicitly trusted finalized-journal
abstraction, reproducible bounded replay/admission/quota searches, adversarial
schedules, eight detected unsafe controls and a workload calculator. It does not
verify a new BFT implementation or extend J's height1/round0 signer. Mandatory
close-first transitions preserve cutoff safety; +256 guarantees no minimum human
time. The proposed 24-vote/five-second profile caps admission at 288 signed
votes/minute; q3 does not permanently guarantee two online evidence sources, and
media-based quota epochs can stall while journal ticks continue. P is a reviewable
verification artifact, not approval of these settings. Production journal and
Task 7.17 remain **BLOCKED** on owner policy/architecture decisions, complete
two-stream/G2/signing/media schemas, independent implementation/availability
review and measurements. The original O proposal and execution record below
remain historical; no production implementation or activation is authorized.

Date: 2026-10-27 (America/New_York). **Protocol design only; inactive proposal.**

The owner has directed network-wide signed user voting, independent node tallies,
all eligible authoritatively admitted votes counting, and an agreed deterministic
cutoff. This supersedes Task 7.17N's producer-selected subset recommendation.
Originality and admissibility remain separate mandatory dimensions.

Recommend **A: one BFT-ordered reviewer-event log**, with full signed votes in
ordered batches and mandatory CLOSE records at a session's predetermined journal
height. Every accepted vote preceding its CLOSE counts. A media producer supplies
the closed session reference, never a replacement selection. This is the smallest
authority mechanism considered here that avoids a second receipt/reconciliation
consensus protocol. It is still a **new authenticated review-history architecture**:
prefer a separate review journal, subject to explicit owner approval. Without that
approval, or an approved control-record alternative, this requirement remains
blocked. There is no fallback to positive-only certificates or local-mempool union.

No production consensus, network, journal, schema, block type, signer, key,
genesis, database, deployment or activation is implemented or authorized here.
No commit, push, merge, reset, migration, unrelated refactoring or Task 7.17P.
All new domains, fields, limits and transitions below are proposals for approval.

## 1. Verified repository prerequisites and source boundaries

| Check before edits | Result |
| --- | --- |
| Expected/actual branch | `Compression-State-Bloat-and-Node-Economics` |
| HEAD | `03c3f653a0d1ad9c06c872f7d786ec603b3d24df` |
| Separately committed 7.17N | HEAD: `Milestone 7 Task 7.17N: specify bounded reviewer admission policy tradeoffs`; only its decision and 7.17B gate note |
| Complete index/worktree | `git status --porcelain=v1 --untracked-files=all` returned no entries |
| Instructions | No applicable ancestor, root or docs `AGENTS.md`; no delegation |
| Authorized deliverables | This document and a supersession notice/link only in 7.17N |

Read the [7.17N proposal](milestone-7-reviewer-admission-policy-decision.md),
[7.17B amendment](milestone-7-v2-reviewer-history-protocol-amendment.md),
[G2 contract](milestone-7-g2-genesis-and-bootstrap-contract.md),
[Tendermint decision](milestone-7-distributed-finality-protocol-decision.md),
[model report](milestone-7-tendermint-model-verification.md) and
[BFT wire/signer contract](milestone-7-bft-wire-and-signer-contract.md).
Their historical proposals do not approve a review journal or new control blocks.

Source inspection: `canonical_v3/{evidence,issuance,history,atomic,primitives,media,block}.py`,
`dual_review.py`, `milestone5_policy.py`, `review_policy.py`,
`reviewer_reputation.py`, and `services/reviewer_eligibility_service.py`.
The isolated evidence verifier checks the supplied frozen set through trusted
callbacks; `history.py` explicitly trusts application acceptance/local sources;
`atomic.py` permanently reserves laboratory issuance/participation. None already
establishes network-wide offered-vote completeness. Existing vote3 has no direct
G/session binding; 7.17B/N vote4 and combined block4 remain unimplemented drafts.
The G2 envelope verifier does not approve missing application-history semantics.

Preserved code facts: five eligible votes and at least one established reviewer
**per dimension**, unit weight, 7,000 basis points among decisive votes; unsure
counts toward participation/quorum but not the decisive denominator. Reviewer
epochs are finalized media height divided by five; probationary/established caps
are 5/25 distinct submission participations. Existing protocol-1 offense checking
cannot simply verify the new vote payload by relabeling its version.

## 2. Corrected requirement and observable vote states

1. Users sign originality (`original/not_original/unsure`) and admissibility
   (`admissible/not_admissible/unsure`) choices independently.
2. Nodes verify, durably retain and gossip eligible signed votes.
3. Every validating node computes the same count from one authenticated record.
4. Every eligible vote **admitted by that record before CLOSE** counts, including
   negative and unsure votes. There is no 5–16 reviewer ceiling or chosen cohort.
5. Producers cannot select a favorable subset of the authoritative set.
6. A consensus-agreed ordered position, rather than a local receipt time, closes
   review. Five votes is a minimum quorum, never a stop-at-five selection rule.
7. Media needs both passing reviews and independently verified technical safety,
   exact original reconstruction, rights, native-ledger/replay and finality checks.

| State | Exact meaning and force |
| --- | --- |
| Submitted | Wallet attempted delivery; no node receipt or inclusion implied |
| Locally received | A node has bytes; authentication/eligibility may still be pending |
| Acknowledged | Named node signed a durable-store receipt; statement of custody only, no reserved vote position |
| BFT-admitted | A valid decided journal batch, authenticated by its commit proof and full predecessor replay, accepts this vote at one position; only this transition enters the tally |
| Finalized | A node has verified and durably applied that decided batch and evidence; admission is irreversible under the BFT assumptions. A QC lacking data/validity is not an admission |
| Late | First attempted authoritative acceptance is at/after CLOSE, or session is stale/closed; no tally/participation effect. Later authenticated misconduct evidence can still be recorded |

Admission and finalization are not two competing authority thresholds: they
distinguish the proved transition from a particular node's durable knowledge.
A proposed/pre-voted vote is provisional, never BFT-admitted. An ack can remain
pending forever under partition or censorship. Gossip cannot guarantee delivery
of every submitted vote, receipt inclusion, global knowledge, or timely admission.
Completeness here means **the entire defined admitted prefix**, not all signatures
that users might have produced or sent to a disconnected or malicious node.

## 3. Assumptions and comparison of authoritative mechanisms

Provisional test parameters are static **N=4, f=1, q=3**, equal power, epoch zero,
with G2-authorized full keys. Two quorums intersect in at least two validators,
at least one honest. Intersection alone is not a multi-round agreement protocol:
the locking, valid-value, round-change, durable signing and decision rules of
7.17G/I remain essential. Never reduce membership/quorum on local accusations.

Safety assumes common approved genesis/policies, unforgeable signatures,
collision-resistant hashes, deterministic validation and at most one faulty
validator, including stale/cloned/crashed signers that violate their obligations.
Progress additionally requires eventual synchrony, fair service/proposers and
available complete inputs. The primary agreement reference remains
[Buchman, Kwon and Milosevic, arXiv:1807.04938v3, Algorithm 1](https://arxiv.org/pdf/1807.04938v3).
Its agreement result does not establish fairness of client inclusion or the
correctness of this new application/profile adaptation.

| Mechanism | Authority and honest safety invariant | Async/one Byzantine, censorship and withholding | Recovery, evidence and progress | Additional approvals |
| --- | --- | --- | --- | --- |
| **A. BFT-ordered reviewer-event log — preferred** | One decided hash-linked sequence of OPEN, VOTE, CLOSE, evidence and media anchors. Same prefix yields identical accepted slots, quota use, vote root and cutoff; no admitted vote can disappear | Arbitrary delay cannot fork a safe decided prefix. Faulty proposer may omit unadmitted votes; honest proposers can include them later if capacity/window permits. No universal inclusion deadline; withheld proposal data receives no honest value vote | Full contiguous batches, commit proofs and source objects; commit-before-sign retention. Three responsive correct validators can progress without the fourth after synchrony. Two available cannot. Ticks close sessions without media | Separate authoritative journal or explicit control architecture; journal consensus/signing domains; admission, closure, retention, resource budgets and G2 policy changes |
| **B. BFT-certified review batches** | Safe only if every batch extends the unique prior certified batch and BFT chooses among competing successors; CLOSE commits exact batch chain/count. Completeness is all admitted batches, not a producer's batch manifest | Three signatures over unrelated batch roots do not order them or prove no omitted batch. Simultaneous branches need locking/BFT. With one Byzantine, q data custodians include >=2 honest; signed unavailable roots cannot be valid inputs | Retain every batch body, cert and predecessor; fetch contiguous sequence and validate eligibility. With BFT sequencing it becomes A with another packaging layer; unordered standalone certs have no safe closing rule | Batch order/fork resolution, completeness proof, data-custody/retention and closure protocol. No threshold-root shortcut |
| **C. Quorum receipts + BFT closure/reconciliation** | A strong receipt must reserve an inclusion obligation, not just ack storage. Safe closure needs an ordered FREEZE, all pre-freeze obligated receipts and an agreed reconciliation result before CLOSE | Three receipt signers intersect a close quorum in an honest signer, but only if each honest closer refuses omission and freeze makes outstanding obligations finite. Without that invariant, threshold acks prove no completeness. Byzantine-only withheld receipt signature cannot become a hidden obligation after freeze | Possible rigorous design: BFT-order receipt reservations before FREEZE; each reservation binds full vote/data; freeze stops new reservations; CLOSE must enumerate/resolve every reserved ID. This is A plus reservation, freeze and reconciliation stages. Unknown off-log obligations can force indefinite closure or unsafe omission | Exact issuance barrier, whether receipt constitutes admission, finite obligation inventory, unavailable/invalid resolution, recovery and extra round/storage cost. Not selected |

For C, simply collecting three signatures and taking a union of closers' local
mempools is unsafe. If receipts remain local while freeze/close is BFT-ordered,
an honest signer may have issued a receipt not yet known to the proposer; refusing
closure needs a specified globally recoverable obligation and delivery rules.
This document does not approve such an unresolved receipt protocol. A eliminates
that extra authority: ordinary acks promise storage, the BFT log alone admits.

**Guarantees separated:** safety is prefix/tally/cutoff agreement; fairness is
inclusion of every already-admitted eligible vote, not unbiased identities or
all submitted messages; liveness is conditional eventual log progress, not a
wall-clock SLA; availability is replicated retained evidence under stated custody
assumptions, not perpetual availability after enough archives fail.

## 4. Proposed signed user-vote bytes and identity

Use 7.17I's strict sorted-key compact ASCII JSON `J`, with exact received-byte
equality, no BOM/newline, duplicate/unknown keys, floats, bool-as-int, coercion or
normalization. `H64`, `Wallet`, `NID`, `Key`, `UInt` and `Sig65` have I's syntax;
submission ID is 32 lowercase hex; nonce is exactly 32 lowercase hex. Domain
strings below are literal ASCII. UInt overflow/exhaustion rejects; no wrap.

Define the following **closed, complete proposed payload** `V` (all required):

```text
{domain:"zoidbergchain/community-review/network-wide-v1",
 protocol:"zoidbergchain", protocol_version:2, review_protocol_version:1,
 network_id:N, genesis_hash:G, review_policy_digest:RP,
 reviewer_policy_digest:RVP, reputation_policy_digest:REP,
 history_policy_digest:HP, submission_id:S, original_media_sha256:H,
 creator_wallet:Wc, review_session_id:SID,
 dimension:"originality"|"admissibility",
 reviewer_wallet:Wr, reviewer_public_key:Key,
 choice:dimension_positive|dimension_negative|"unsure",
 eligibility_media_height:Fh, eligibility_media_hash:Fhash,
 eligibility_journal_height:Jh, eligibility_journal_hash:Jhash,
 session_close_height:K, vote_sequence:0, vote_nonce:Nonce}
```

This is a candidate new profile, not an existing V3/V4 parser or an assigned
production version. Do not reuse N/B's 19-key vote4 grammar under a second meaning.
Reconcile the complete version registry before any schema freeze or implementation.
`RP/RVP/REP/HP` resolve to full approved source bytes in G2, not peer-supplied
policy. Public key must be a finite compressed secp256k1 point. Recover the full
key from the signature and compare both that key and its derived Wallet to V;
the Wallet cannot be a display name, user database ID or validator credential.

```text
M = J(V)                                      # actual UTF-8 bytes
eip191_preimage = 0x19 || ASCII("Ethereum Signed Message:\n")
                 || ASCII(decimal(byte_length(M))) || M
signing_digest = Keccak256(eip191_preimage)
signed_vote = {payload:V,signature_scheme:"personal_sign",signature:Sig65}
message_id = lowerhex(SHA256(M))
evidence_id = lowerhex(SHA256(J(signed_vote)))
```

The displayed `\n` means one byte 0a; decimal length has no leading zeros.
Sign raw M, not its hexadecimal spelling, its SHA-256, or an extra envelope.
Propose low-S signatures (`1<=s<=floor(n/2)`, `1<=r<n`, v=27/28); unlike I's
historical signature grammar this is an explicit **new user-profile** restriction,
requiring approval and independent vectors. Malformed/high-S forms reject before
relay; semantic duplicate rules remain necessary even with low-S signatures.
Payload <=2,048 bytes; complete signed_vote <=4,096; depth <=16. This is a closed
25-field payload, not the earlier 19-field V4. No private keys
are introduced here. Complete vote size is measured as a schema example below,
not a cryptographically valid vector.

All target, dimension, network/G, session, policy, creator, eligibility references
and closing height are directly signed. Copying a signature to another context
fails recovery/context checking. No local `issued_at/expires_at` decides validity:
the signature is usable only after its exact OPEN and before its K; the session
boundary supplies expiration. Optional UI creation times are unsigned metadata.

The counted slot is `(N,G,SID,dimension,Wr)`, with one immutable accepted choice.
`vote_sequence` is exactly zero; there is **no replace/correct-vote operation**.
Nonce is an unpredictable per-slot signing nonce, scoped to that slot; it cannot
create another seat, lifetime credit or retry permission. Deterministic rules:

| Input at an ordered VOTE position | Transition |
| --- | --- |
| First valid eligible choice for a free slot | ADMIT; retain exact bytes, position, derived historical status and quota source |
| Exact message/evidence replay | DUPLICATE; return first source, no new count, quota, offense or credit |
| Same slot/choice with another nonce/signature | SEMANTIC_DUPLICATE; no replacement or new charge; do not confuse this with a fresh attempt |
| Same slot, different signed choice | CONFLICT; preserve both authenticated messages, first admitted choice stays, derive one grouped prospective equivocation incident |
| Conflict pair with no earlier admission | If both are ordered as observations, process in log order: the first eligible VOTE admits and the second conflicts. An EVIDENCE-only pair does not itself admit either choice |
| New session/submission/dimension | Different signed slot; must meet its own opening, eligibility and quota rules; no replay of an old signature |

Conflict evidence does not retroactively subtract a finalized vote or re-close
media. A penalty affects subsequent admissions, as section 10 specifies. This
explicit first-**BFT-admission** rule never means first local arrival. Reviewer
votes cannot count as validator prevotes/precommits; only G2-authorized validator
messages in their separate agreement namespace can decide a journal/media value.

## 5. Gossip, receipts, storage and bounded resources

Receiving nodes first enforce frame/JSON/depth/count limits, network/G/version,
open-session identity and signed target/reference. Unknown session/history is
PENDING_HISTORY: fetch it without forwarding an unchecked vote as valid. Recover
and verify signatures **before vote relay**. Recompute eligibility from verified
history; local preflight remains provisional because ordered quota/penalties may
change before admission. An ineligible vote is not relayed as countable; verified
objective misconduct can use the separately bounded evidence lane.

Use content-addressed INV(message_id), GET and DATA; inventory announces no
authority. Forward a newly verified message to subscribed peers and the four
validators; do not echo full data to the sender. INV/GET pages <=256 IDs, DATA
frames <=64 KiB, per-peer <=4 in-flight pages. Bind query responses to exact
N/G/HP and SID or journal range. Rate-limit repeated misses/oversized responses.
Do not let a peer's mutable Bloom filter prove absence or completeness.

Proposed local defaults, **not consensus validity inputs**: 8 peer links;
100,000 recently verified IDs (~6.4 MB at assumed 64 B/index entry); 64 MiB total
unadmitted vote queue and 8 MiB/peer share; 1 MiB/s aggregate vote-data relay and
128 KiB/s/peer, burst two seconds; 100 signature checks/s/node with a separate
bounded queue and fair allocation by authenticated Wallet/peer/session. These
are planning values requiring target-host measurements. Backpressure gives
BUSY_RETRY, not a dishonest success receipt. No unlimited negative-signature cache.
Evict/rebuild transient IDs by bounded LRU/session horizon; eviction may cause
another verification, never another authoritative participation. Finalized slot
and replay ownership live on disk and cannot expire with the dedup cache.

Gossip protects scarce verification work with cheap framing/context checks,
bounded connection/INV rates and quarantine of invalid senders. Countable identity
still requires earned eligibility/bootstrap, non-self participation and 5/25 quota.
Peer limits/IP controls are local flood controls, not a Sybil-proof reviewer
identity system or consensus blacklist. Many eligible colluding keys can still
control the human result. Per-choice relay priority is forbidden.

Verified local data is committed to an outbox/store before returning a custody
ack. Proposed receipt is signed under `zoidbergchain/review-storage-receipt/v1`:
closed payload `{domain,protocol_version:2,receipt_version:1,network_id,genesis_hash,
history_policy_digest,review_session_id,message_id,evidence_id,node_public_key,
stored_through_journal_height,promise:"custody-only-not-admission"}`. Apply J and
the same EIP-191 byte rule. Node key proves its statement, **not validator power**.
Propose retention of acked bytes through session closure plus 1,024 journal
heights; preserve admitted/evidence sources for archival lifetime regardless.
No bounded real-time retention guarantee follows if log progress halts. Reject
custody promises beyond provisioned disk; a signed lie is evidence, not admission.

Local restart rebuilds pending outbox from durable bytes, then reconciles both
verified journal ranges and session slot inventories. Pull missing batches/QCs
even at equal media tips. Reconcile a closed session by complete prefix replay,
not by accepting only advertised positives. Unadmitted messages may be retried
before K; after K retain receipt/outcome but do not resurrect their tally effect.
Crash before ack may leave client uncertain; exact resubmission is safe.

| Response | Meaning |
| --- | --- |
| INVALID_FORMAT / INVALID_SIGNATURE / WRONG_CONTEXT | Objective deterministic failure, no admission or favorable default |
| PENDING_HISTORY / PENDING_ORDER | Authentic input awaits dependencies/BFT, not counted |
| ACK_STORED | Custody only; provide receipt and polling/reconciliation target |
| ADMITTED | Verified batch/QC, exact position, derived acceptance and evidence retrieval reference |
| DUPLICATE / CONFLICT / INELIGIBLE / QUOTA_EXHAUSTED | Reproducible existing slot or ordered rejection reason; conflict/rejection evidence retained only when authorized in the log |
| LATE / STALE_SESSION | No acceptance after boundary/parent staleness; no silent move to another session |
| BUSY_RETRY / UNAVAILABLE | Capacity/dependency/local service failure; neither invalid media nor negative vote |

An arbitrary node-signed rejection is diagnostic. Only authenticated ordered
inputs and deterministic transitions may change quota, penalties or history.

## 6. Preferred log authority and deterministic transition order

Proposed separate journal batches `Rj` are **not canonical media blocks**. Approving
them would introduce a second authoritative history with its own storage and
consensus namespace. Use the same authorized static validators and reviewed
Algorithm 1 rules in a separately approved journal profile; **do not feed journal
values to today's media signer or reuse Q4 signatures/slots**. Journal proposal,
prevote/precommit and commit-proof domains must bind stream=`review-journal`,
N/G/HP, journal agreement digest, C/epoch, journal height/parent hash, round,
value/nil and validator identity. Separate persistent H/R/phase/lock/valid/outbox
state and copied-key fencing are required. Their complete closed wire grammar
and independent vectors remain a freeze gate, not supplied by a domain name.

Candidate batch body: `{journal_version:1,network_id:N,genesis_hash:G,
history_policy_digest:HP,journal_height:j,previous_journal_hash:Jprev,
media_anchor_before:{height:Fh,hash:Fhash},events:[event,...]}`.
`Jj=D({domain:"zoidbergchain/review-journal-batch/v1",body:body})`, where
`D(x)=lowerhex(SHA256(J(x)))`. Genesis origin
`J0=D({domain:"zoidbergchain/review-journal-origin/v1",network_id:N,
genesis_hash:G,history_policy_digest:HP,bootstrap_digest:BD})` is computed **after G**,
never inserted into its own genesis preimage. BFT decides Jj; the proof is outside
the body and signs Jj, never part of its own value preimage.

Event source is exactly `{kind,payload}`; event ID is
`D({domain:"zoidbergchain/review-journal-event/v1",network_id:N,genesis_hash:G,
history_policy_digest:HP,kind:kind,payload:payload})`.
Locator `(j,Jj,event_index)` authenticates inclusion only with full batch/proof/
ancestry. Mandatory derived CLOSEs lead in increasing SID order. Optional verified
MEDIA_ANCHOR follows (at most one), then remaining events in proposer-specified
array order. That order becomes authoritative only through BFT. Never sort by
local time, choice or a union of local queues. An input's derived acceptance,
status, quota and offense outputs are mandatory replay results, not trusted flags.

Journal batch body <=262,144 bytes; <=64 events; <=24 VOTE events; <=16 OPEN;
<=16 mandatory CLOSE, each <=2,048 bytes; at most one MEDIA_ANCHOR. VOTE event
<=8,192; EVIDENCE <=16,384. All joint byte/count limits apply simultaneously;
item maxima are not additive permissions. OPEN scheduling reserves its future
close position/capacity: at most 16 opens at any height, fixed W, hence at most
16 closes per later height; reserve 32,768 body bytes plus verified header space
for those closes before optional events. Refuse excess OPENs before admission,
never silently drop a counted vote to make CLOSE fit. All close commitments are
bounded counters/roots, not full vote arrays. Large source objects are external,
content-addressed, fully fetched/verified/retained before an honest value vote.

A VOTE event is `{signed_vote:...}`. Well-formed authenticated but noncountable
attempts may be ordered and derive a reason; unauthenticated garbage is locally
dropped, never permanently journaled. No consensus requirement archives every
invalid packet. A proposer may not mark an eligible pre-close VOTE rejected: the
reducer must ADMIT every free eligible slot in its chosen ordered batch. Limits
bound which attempts enter BFT, not how admitted positives/negatives are selected.
Replays/conflicts cannot use proposer acceptance flags to gain a second count.

Empty journal ticks are permitted in this **conditional proposal** so journal
height/closures can progress without accepted media. This is precisely the new
no-media authority requiring approval; current G2/media-only rules do not allow
it. Fair local scheduling prioritizes due closes, media anchors, source recovery
and diverse pending users. BFT safety does not prove a particular request is
included; honest-proposer queue policy and quotas give conditional service only.
Rejecting every proposal missing one's local queue would make validity depend
on unpublished state and can prevent agreement; this is not a valid shortcut.

## 7. Opening, exact cutoff, duration and retries

An OPEN request binds an immutable submission and complete media/rights source.
Proposed creator-signed request under `zoidbergchain/review-open/v1`, EIP-191/J:
`{domain,protocol_version:2,network_id:N,genesis_hash:G,history_policy_digest:HP,
review_policy_digest:RP,submission_id:S,original_media_sha256:H,creator_wallet:Wc,
media_source_digest:MS,technical_evidence_digest:TE,rights_evidence_digest:RE,
eligibility_media_height:Fh,eligibility_media_hash:Fhash,
eligibility_journal_height:b,eligibility_journal_hash:Jb,opening_nonce:Nonce,
attempt:0|1}`. Its wrapper has `payload,signature_scheme,signature`.
SID=`D({domain:"zoidbergchain/review-session/v1",open_request:request})`, with
`request` the signed payload **without signature**. Signature variants never open
two sessions. OPEN payload is `{request:signed_request,review_session_id:SID}`.

OPEN at height o must cite the immediately preceding verified journal `(o-1,Jprev)`
and its media anchor F. Require authenticated creator/non-reminted original,
full original/source availability, technical/rights verification, resource caps,
and no active session or outstanding passed admission for the same original H
or submission S. Alternate IDs/encodings cannot evade this original lock. No
producer-selected invitation list. A valid OPEN makes S/H/creator immutable,
creates no currency/reward and accepts no media. Anyone may relay a valid creator
request; anonymous peers cannot open another creator's review. Stale open requests
must be freshly signed; old signatures cannot be repaired with unsigned fields.
A batch carrying MEDIA_ANCHOR cannot also carry OPEN: creator requests against
the newly anchored parent use the next batch's predecessor snapshot. This avoids
opening against a superseded parent within the same batch and keeps OPEN's
signed snapshot equal to its actual base state.

The existing rights/technical policy is not waived. In particular, legacy
rights `issued_at/expires_at` cannot be evaluated against a node's current clock
or by treating journal height as seconds. The combined policy freeze must supply
an authenticated deterministic time input for those checks, or an explicitly
approved new session-bound rights schema. This document selects neither and
therefore does not claim complete OPEN/application byte vectors or implementation
readiness. That existing time-policy dependency is distinct from the fully
specified ordered vote cutoff; it cannot justify dropping rights verification.

Freeze base qualification/status at `(F,J_(o-1))`. Every vote signs those exact
references and SID. Use approved G2 B0 grants/earned history, not local registration
labels. Quota is checked **live in ordered journal state** and prospective active
penalties may disqualify future admissions. Promotion after OPEN does not create
an established seat in this session; admitted status never changes retroactively.

Concrete candidate timing policy, **requiring owner approval**:

* W=256 journal heights; `K=o+256`, computed with checked UInt addition at OPEN.
  No votes count in OPEN's batch; admission window is `o<j<K` (255 interior
  heights). There is no early successful close upon reaching five or 70%.
* At the beginning of batch K, include the unique derived CLOSE for every due
  session, sorted by SID, before **any** VOTE at K. Missing/altered/duplicate
  mandatory close makes the batch invalid. CLOSE is exact even with zero votes.
* CLOSE payload is `{review_session_id:SID,open_height:o,close_height:K,
  vote_count:t,ordered_vote_commitment:R,tally_originality:TO,
  tally_admissibility:TA,outcome:OUT}`. OUT is `PASS`, `FAIL` or `UNRESOLVED`;
  each tally contains the section 8 counters, quorum, rational and verdict.
  Close ID is the event ID; source `(K,JK,index)` is authenticated by JK's proof.
* Anyone may ask nodes to process the due close/tick. Nobody, including creator,
  producer or three receipt signers, can close before K, extend K, waive quorum,
  alter choices, or stop voting when a favorable intermediate tally appears.
* Five/one-established quorums constrain **passing review**, not closure progress.
  Lack of quorum or decisive votes produces UNRESOLVED; it never causes an
  indefinitely open session or becomes implied approval. Either resolved negative
  dimension makes combined FAIL; PASS requires both positive.

W measures agreed ordering intervals, **not seconds**. A candidate operational
target is one batch per five seconds, giving about 21 min 20 s for 256 intervals;
local pacing and growing round timeouts are operational controls only. Fast
ticks could provide less human response time; stalls could provide much more.
This proposal does **not** guarantee a minimum real-time voting opportunity or
a bounded wall-clock close under asynchrony. If the owner requires such a promise,
approve and review a consensus-time/beacon and pacing policy before freeze.
No local timer may decide which side of K a vote occupies. Round retry waits grow
as required by the reference protocol; there is no hard timeout that invents q.

A signed vote sent just before K but first ordered at K+1 is LATE. An ack does not
hold K open. A pending custody receipt is reconciled to its admitted locator,
duplicate/conflict/rejection, or CLOSED_WITHOUT_ADMISSION with a verified close;
the receipt plus absence from one page is not a proof of omission. A valid complete
session replay proves which admitted slots exist. Late evidence is not a tally
amendment. An eclipsed client cannot infer the latest close from silence.

If a MEDIA_ANCHOR advances beyond F before a new VOTE, reject that vote as
STALE_SESSION. Earlier admissions still count at the scheduled CLOSE and keep
participation history; the resulting pass can settle media only at its signed F.
A media candidate whose parent has advanced must not use the stale session.
No reinterpretation of historical eligibility or transfer of old signatures.
An outstanding passed-admission lock becomes unusable when a different original's
verified MEDIA_ANCHOR advances past its F; mark that pass STALE_UNSETTLEABLE and
stop treating it as an outstanding admission for the bounded retry check. Keep
its original/retry history and enforce the one-retry limit. If its own original
settles, mark that original permanently consumed instead. Neither action erases
its review history.

Propose terminal FAIL for that original (no automatic retry that shops away
negative judgment). UNRESOLVED, or a passed but unusable stale-parent session,
may get **one** creator-requested fresh retry, attempt=1, no sooner than K+256
and only after the previous session is closed and no admission is outstanding.
For an unusable passed session, the media anchor must actually have advanced;
the creator cannot discard a usable pass to rerun voting. Same S/H/creator,
new nonce/SID/reference/signatures, all old history retained; another retry or
appeal needs an explicitly approved protocol. No local reopen, cancellation or
backdating. These terminal/retry rules and their delay are lifecycle approval
choices, not owner decisions already made. They bound automatic retries but do
not guarantee representative review or eliminate creator timing influence.

After a partition/crash, obtain the unique finalized prefix through OPEN/CLOSE;
replay ordered admissions/claims, never rebuild authority from the recovered
local queue. Two partitions cannot safely finalize competing closes with one
fault and correct signer locking. A partition with <q halts; healing uses normal
late-decision/data recovery. Lost private safety state requires fenced recovery,
not signing as a fresh validator with the same key.

## 8. Deterministic vote-set commitment and tally

For SID, take **every ADMIT transition** in increasing `(journal_height,event_index)`
before its CLOSE. Do not sort into another favorable subset. Rejected observations
and conflicts are evidence, not additional accepted votes. For each admitted vote,
retain its signed bytes, source position and frozen derived status.

```text
R0 = D({domain:"zoidbergchain/review-vote-set-empty/v1",network_id:N,
        genesis_hash:G,review_session_id:SID})
Ri = D({domain:"zoidbergchain/review-vote-set-step/v1",previous:Ri_minus_1,
        ordinal:i,journal_height:j,event_index:e,message_id:m,
        evidence_id:v,reviewer_status:status})       # i starts at 1
R = Rt; t = number of ADMIT transitions in both dimensions
```

The fold binds order, count, signed data identity and derived status; it is not
a sparse Merkle proof or a succinct proof of completeness. Its positions do not
contain Jj, which will hash the batch containing them; this avoids self-reference.
Verified hash-linked batches supply source hashes externally. Full prefix replay
proves coverage and every acceptance decision. A member proof alone cannot prove
no negative slot was omitted. Media may repeat R/t, but cannot redefine them.

Per dimension compute distinct accepted Wallet counts `p,n,u`, established `e`,
`tD=p+n+u`, `d=p+n`. Quorum=`(tD>=5 and e>=1)`; resolved=`quorum and d>0`.
If resolved, approve iff **`10000*p >= 7000*d`**, else reject. Use nonnegative
integer arithmetic with checked sufficiently wide products or arbitrary precision;
no floats, rounded percentages, stake weights, averaging dimensions or unsure
as negative. Store ratio `{numerator:p/gcd(p,d),denominator:d/gcd(p,d)}` when d>0;
for d=0 ratio is explicit null and verdict unresolved (never divide by zero).
Tally object has exactly `dimension,positive,negative,unsure,total,established,
decisive,quorum,resolved,approval_ratio,verdict`. Verdict is the dimension's
positive/negative literal or `unresolved`. Compare the entire derived object.

| Case, one dimension unless stated | (p,n,u;e) | Expected result |
| --- | --- | --- |
| All favorable | (5,0,0;1) | Pass, ratio 1/1 |
| Majority negative | (2,3,0;1) | Reject, 2/5 |
| Exactly 70% | (7,3,0;1) | Pass: 70,000=70,000 |
| Below 70% | (6,3,0;1) | Reject: 60,000<63,000; ratio 2/3 |
| Unsure present | (3,1,1;1) | Pass, 3/4; total five |
| One positive, four unsure | (1,0,4;1) | Pass under preserved decisive policy; no invented minimum decisive count |
| All unsure | (0,0,5;1) | Unresolved, no ratio |
| Insufficient voters | (4,0,0;1) | Unresolved despite 100% decisive approval |
| Missing established | (5,0,0;0) | Unresolved |
| Ten duplicate relays of a positive | Initial (5,0,0;1) | Still five, one participation per Wallet/submission |
| Accepted positive then conflicting negative | Initial (5,0,0;1) | Still five positives; conflict incident prospectively affects later admissions |
| Negative ordered after CLOSE | Initial (7,3,0;1) | Still 7/10 pass; late vote never enters set |
| Eligibility changes after admission | Initial (5,0,0;1) | Prior tally unchanged; cannot strip established seat retroactively |
| Promotion after OPEN before first vote | Five base probationary Wallets | Still no established seat from that promotion in this session |
| Originality passes; admissibility rejects | (7,3,0;1), (2,3,0;1) | Combined FAIL; no media admission |

All-unsure and insufficient participation stay unresolved. A later decisive
choice cannot replace an accepted unsure slot. New attempt rules require owner
approval; no default positive certificate. Same authenticated prefix and policy
must yield byte-identical accepted slots, fold, close, both tallies and outcome
on every honest replay implementation.

## 9. Durable history architecture and media integration

| Record or derived fact | Minimum authenticated durable cause |
| --- | --- |
| Open session | Creator request, OPEN batch/proof, original media/technical/rights sources, exact S/H/creator/F/J snapshot, K/SID/attempt and original lock |
| Admitted vote | Full signed_vote, batch/proof/position, first-slot ownership, derived status/eligibility, quota source, ordered fold contribution |
| Rejection/equivocation | Well-formed signed source plus ordered context and reason derivation; conflict pair or immutable authenticated reference to an earlier fully archived source |
| Closed session | Mandatory CLOSE, exact cutoff/ancestry, count/fold, both complete tally objects and combined outcome |
| Participation/quota | First accepted `(Wallet,submission)` source and its charged epoch; paired-dimension/attempt dedup, live usage, qualification/promotion causes |
| Penalty | Full objective signed proof, incident grouping/sequence, active interval and prospective activation source; no administrator status assertion |
| Media outcome | CLOSE for PASS/FAIL/UNRESOLVED; media bytes/Q4 and later MEDIA_ANCHOR for actual accepted settlement/claims; no media reward on mere PASS |

| Architecture | Completeness/recovery | Trust, storage and owner decision |
| --- | --- | --- |
| **Separate authenticated BFT review journal — preferred** | Contiguous journal batches/proofs plus content-addressed evidence and media anchors independently replay pending, failed, unsure and no-media events | New authoritative history/consensus signing namespace, empty ticks, cross-stream ordering, indefinite sources and proof archive. Must amend G2 policies/release contract; not silently permitted by prior tasks |
| Versioned on-chain control records | One BFT ordering stream interleaves review/control with accepted-media records, with complete byte/type rules; ordinary media records still each carry exactly one accepted original | Explicit new control-record class and amendment of post-genesis media-only-chain rule, clock/height/economics, signer/schema/limits; no reward/accepted-media masquerade. Could simplify dual-stream coordination, but is a separate owner choice |
| Media-only history | Can authenticate votes included in a later accepted block, not prior authoritative admission/closure needed to validate that first block, failed reviews or no-media participation | Existing constraints avoid separate history but cannot meet this task's independent pre-admission/no-media authority requirement without another approved authority. Packing a chosen root/list into media does not repair missing history |

**Dual-stream ordering rule for A:** journal state has exactly one monotonically
advancing finalized media anchor, initially `(0,G)`. MEDIA_ANCHOR includes a
content-addressed reference to full media bytes/Q4 (not just a hash); validators
fetch/validate full sources and immediate media-parent ancestry, then advance
the anchor by one. A media may reference only an already finalized journal
prefix for its CLOSE and eligibility sources. The anchor's journal batch is
strictly later than that prefix. A subsequent OPEN uses the latest anchored media
parent. The next media height cannot be proposed until the prior media decision
has an authenticated journal anchor. Anchoring changes no balances or currency:
it exposes already-finalized media/native facts to review-state replay.

There may be lag between media finality and journal anchoring. Do not relabel
pending anchor-dependent user activity as qualified. A minority cannot assert
another parent from a cached chain tip; use only verified prefixes. Competing
sessions for different originals may share F and compete to settle at F+1; media
BFT chooses one. Losing sessions are not silently reparented; their admitted
work remains authoritative, and they need the approved stale-session retry.
This throughput/fairness cost of minimal immutable-parent coupling is explicit.
A more permissive rebasing/pipelining design needs another reviewed specification.
Each stream durably applies its own complete prefix and publishes its cursor
only after source/transition commit. MEDIA_ANCHOR application is idempotent for
replay of the same verified batch and advances exactly once; a repeated anchor
in a later new batch or a contradictory anchor is invalid. Cross-stream references
are verified in DAG order. Separate database
transactions or BFT decisions are not an atomic distributed transaction; a crash
during anchor lag resumes fetching/applying the missing dependency, never rolls
back finalized media or invents a journal settlement.

Proposed media review binding (inside the existing 3 MiB total, new combined
schema still gated):

```text
{binding_version:1,network_id:N,genesis_hash:G,history_policy_digest:HP,
 submission_id:S,original_media_sha256:H,creator_wallet:Wc,
 review_session_id:SID,open_height:o,close_height:K,
 close_journal_hash:JK,close_event_index:c,close_event_id:CID,
 ordered_vote_commitment:R,admitted_vote_count:t,
 originality:TO,admissibility:TA,
 eligibility_media_height:Fh,eligibility_media_hash:Fhash,
 eligibility_journal_height:b,eligibility_journal_hash:Jb,
 evidence_manifest_digest:EM}
```

EM binds the canonical complete list of source object digests/lengths for this
session through CLOSE, including admitted and rejected signed observations,
conflict evidence, OPEN sources and CLOSE. It aids fetching, not
coverage authority: recompute the list and all accepted slots by full replay.
Do not require the manifest in CLOSE if it includes CLOSE itself. Compute EM
**after CLOSE finalizes**, from archived sources; EM does not enter SID/R/CLOSE.
The manifest is an external archive object, streamed in bounded pages rather
than embedded in media; its exact canonical paging/schema/length ceilings require
freeze. Later misconduct evidence is archived in later journal positions and
cannot mutate EM or that closed session's vote set.
The full media header binds the exact immediate finalized parent F, G2 consensus
context and this binding; creator/technical/rights/native records remain mandatory.
The two session tallies and historical references must equal replay, not supplied
claims. No current media hash or its future Q4 appears in any input it hashes.

Dependency DAG:

```text
approved policy sources/bootstrap/M/D -> G
G -> J0 -> prior journal + anchored media F -> OPEN/SID -> signed votes
-> ordered admissions/R -> CLOSE -> JK/commit proof -> EM/media binding
-> full media hash -> media Q4 -> later journal MEDIA_ANCHOR -> next OPEN
```

G2 must commit the journal agreement descriptor/policy as G-independent source
bytes; never insert G/A/PD/J0 into a source whose digest feeds itself. Reconcile
L's history-policy finality reference (remove old FP reference in favor of the
approved genesis agreement source, or explicitly add a G-independent source).
No new authority is authenticated by a committee's self-declared signed roster.

A fresh node starts with independently pinned G2/full supported policy semantics,
B0/M/authority, then fetches contiguous journal batches/proofs and content-addressed
media/evidence from any archive peers, including at least the obligated validator
archives. Replay in the DAG's order; independently recover user/validator keys,
verify exact bytes/hash/ancestry, all acceptance/rejection transitions, full tally,
media reconstruction/rights/safety/native validity and Q4. Derived SQLite rows,
downloaded snapshots, membership proofs, media producer promises or matching
roots alone cannot replace this work. A trusted locally already-verified checkpoint
can accelerate restart, not authenticate an arbitrary remote state image.

Missing source/coverage => INCOMPLETE_HISTORY; failure to fetch/validate due to
local resource outage => UNAVAILABLE; contradictory bytes or transitions => INVALID.
Do not vote to finalize media as valid until all underlying signed votes and
eligibility/penalty/quota/parent evidence are verified and retained. A well-signed
tally commitment with unavailable sources is insufficient, even with q signers.
Equal media tips still require journal/proof/data inventory reconciliation.
An isolated fresh node cannot prove that a coherent old prefix is the latest.

**Availability obligation proposed for approval:** each honest validator must
durably store the full batch and all referenced sources before a non-nil journal
prevote/precommit, and preserve them through archival lifetime (at least three
years online, with indefinite verifiable archival retention). For q=3/f=1 this
implies at least two honest custodians at certification, assuming honesty includes
storage/retrieval service and fault bound remains valid. Serve range/data fetches
with bounded fair queues and repair lost replicas from peers; audit replicas and
restore redundancy before routine pruning. Finite consensus caches are separate
from the source archive. Three-year retention alone is insufficient for permanent
fresh-node recovery after year three; unapproved pruning is forbidden.
No simultaneous uptime, recovery deadline or survival of enough later archive/key
failures is guaranteed. Extra independent public archives reduce operational
risk but provide no new vote authority. User/producer availability cannot be the
sole custodian. Refusing unavailable data preserves safety at a liveness cost.

## 10. Quotas, reputation, eligibility and no-media behavior

Recommend authoritative participation at first **journal ADMIT**, not at later
media finalization. Failed and unresolved reviews then leave replayable work and
quota history. This is a material amendment to 7.17N, requiring owner approval.

Keep numeric caps 5 probationary /25 established and media epoch
`E=floor(anchored_finalized_media_height/5)`. At ordered admission, require session
F still equals the current anchored media parent. Base status comes from OPEN's
snapshot; prospective penalties are queried at the immediate journal prefix.
For first participation on a submission, charge once to E using that base status's
cap; compare existing distinct charged submissions before incrementing. Different
sessions at different E do not earn another lifetime participation credit for the
same submission. Proposed policy charges each `(Wallet,submission)` **once total**
at its first admission, shared across dimensions and permitted retries, with
its original charged epoch retained. This avoids cross-epoch double charging,
but retries become uncharged work, bounded by the one-retry rule and session
resource limits; accepting this tradeoff is an explicit owner decision.

Before any later-dimension/retry admission still require eligible base status,
no currently active penalty, valid target and session boundary. Existing charge
allows completing that same submission even after quota is otherwise exhausted;
it never admits another submission. A reviewer cannot spend one remaining slot
on two concurrent new targets: ordered first admission consumes it, later target
gets QUOTA_EXHAUSTED. No local receipt reserves a quota slot or refunds one.

| Situation | Proposed journal consequence / preserved limit |
| --- | --- |
| Exact replay/same choice variant | No extra tally, quota, offense, participation or credit |
| Two dimensions on same submission | Separate signed votes/tallies; one charged participation |
| Failed, all-unsure, no-quorum media | Admitted participation remains; no refund for undesirable judgment/outcome |
| Probation credit | One per distinct admitted submission when base status probationary, regardless of media success; explicit proposed change, easy-work farming remains a risk |
| Promotion | Preserve >=10 distinct probation participations and >=3 media epochs after probation qualification; promotion affects future OPEN snapshots only |
| Qualification | Preserve age >=3 epochs, creator 2 finalized minted submissions, or 5 nonself native transactions spanning >=3 epochs, or mixed 1 minted +2 native; canonical creator/native/mixed priority. Journal OPEN/receipt alone earns none |
| User registration | Wallet signature proves key control; UI/account registration alone never grants reviewer eligibility, balance or established status. G2 B0 clean grants and their actual people remain owner-approved bootstrap inputs |
| Reputation credit | Participation/probation source only; no invented scalar score, vote correctness oracle, majority-alignment reward or payment |
| Objective penalties | Retain existing five offense families and schedules; group authenticated incidents once, activate prospectively when ordered. Negative/unsure judgments are never offenses |
| Epoch boundary | New submissions charge new E; prior admitted slots/charged epoch stay fixed. Journal ticks do not advance E, age, penalty expiration or native activity |
| Media settlement/reward | Only actual valid finalized media invokes approved native reserve/reward rules, once. Journal has no reward transactions, fee minting, currency issuance or validator subsidy |

Penalty sources must bind N/G/session/creator and full authenticated context.
Propose existing per-type schedules: equivocation cooldown 3 then 10 epochs;
self-vote and proven quota abuse 1 then 3; third incident suspension 25; cooldown
violation extends to max(existing end,E+active duration), suspension violation
records without extending. Half-open intervals, suspension precedence and
underlying-status restoration remain. New application starts at the first
transition after the ordered evidence, never its claimed old signing time.
Require three distinct verifiable excess attempts for quota-abuse incidents;
duplicates, invalid signatures and mere network retransmissions cannot supply
them. For this proposed profile an excess-attempt identity is the semantic slot
`(SID,dimension,Wallet)`, accepted at most once toward that epoch's excess count;
changed nonces/choices in the same rejected slot do not multiply it. Reproduce
the exhausted-quota prefix for each source. This scope is part of the required
reputation-policy approval, not a silent reuse of protocol-1 evidence identities.
Incident identity for equivocation includes SID/dimension/Wallet, not each
pair of signature variants; reconcile this scope with existing submission-level
grouping before approval. Offense events need both signed choices and replayable
quota/status causes; local bans/analytics are not consensus evidence.

Current penalty masking can block a later vote in an already-open session; earlier
admitted votes/status stay counted. Thus snapshot eligibility is necessary, not
a reservation immune to later misconduct. A penalty after CLOSE cannot change
the closed outcome/media validity. Unknown/unarchived evidence is not silently
treated as a known global offense. Source omission before admission remains a
censorship risk; it does not justify local retroactive tally changes.

**No accepted media:** journal OPEN/VOTE/evidence/ticks/CLOSE continue under A,
so pending/failed reviews acquire authenticated outcomes. Media height/epochs,
new earned native/creator qualifications, minimum probation time, quota renewal
and penalty expiration can still stall indefinitely. If all eligible reviewers
exhaust 5/25 in the frozen epoch, new participation cannot continue even though
the journal can close sessions. B0 reviewer shortage still blocks media. Do not
pretend journal liveness solves this policy deadlock. Replacing E with journal
epochs/consensus time, replenishing quota, issuing grants or changing promotion
would require explicit new clock/bootstrap/economics policy; none is selected
or authorized here. Maintaining media-based E is the conservative candidate;
the owner must accept its halt behavior or approve a fully specified alternative.

## 11. Storage, bandwidth, capacity and latency estimates

These are explicit planning assumptions, not measured throughput, safe deployment
limits, price quotations or reuse of 7.17N's 5–16 capacity estimate. Each Wallet
voting both dimensions emits two signatures; let m be signed messages, not people.
Network-wide count has no per-session reviewer ceiling. There is finite admission
bandwidth and a fixed window, so excess offered votes can remain unadmitted/late.

| Item | Proposed bound / estimate |
| --- | --- |
| User vote | Signature 65 raw bytes /132 JSON characters including `0x`; payload <=2,048, full signed_vote <=4,096. Planning mean 2,048 bytes/vote; example exact width measured below |
| Journal body / source wrapper | <=256 KiB/batch; VOTE event <=8 KiB; <=24 VOTEs/batch and whole-body cap jointly. External original media/rights bytes additional |
| BFT metadata | Planning 1 KiB per validator phase message, two all-to-all phases at N4: 24 KiB/batch; commit proof <=16 KiB candidate cap, full schema measurement/review still required. Proposal/retries/PVs/transport extra |
| Journal admission throughput | At nominal 5 s, 24/5=4.8 signed votes/s across all sessions, before other constraints; no guaranteed rate under contention/faults |
| Window capacity | 255 interior batches *24=6,120 votes across all sessions, at most 3,060 two-dimension reviewers if one session monopolized capacity; honest scheduling must share capacity |
| Hundreds/thousands | 100 reviewers both dimensions: 200 messages, ~0.391 MiB at 2 KiB; 1,000: 2,000 messages, ~3.906 MiB and >=84 full voting batches; 3,000: 6,000, ~11.719 MiB and >=250 batches. 10,000 need >=834 batches and cannot fit this W, even alone |
| Payload gossip | Ideal 4-node dissemination >=3*m*b bytes; for m=2,000,b=2,048: 12,288,000 bytes (~11.72 MiB). Eight-link relay planning allowance 8*m*b=32,768,000 (~31.25 MiB); no topology-wide upper bound without configured peer/rate caps/retry budget |
| Ordering payload replication | Another >=3*m*b if sent independently to three validators; this may overlap cached gossip, so do not blindly double-count measured traffic |
| Closure | Fixed K, not first quorum. Nominal 256*5=1,280 s plus opening/round delays. Votes near close may miss. Three honest nodes cannot guarantee inclusion before K under arbitrary network delay |
| Canonical media bytes | Unchanged <=3,145,728; original image/stored payload <=2,097,152, text <=262,144; maximal binary payload base64=2,796,204 |
| Embedded review binding | Proposed <=8,192 bytes inside media, including both tallies; **no full m-vote array inside media**. Full media certificate/schema must be refactored by a later approved task, not by truncating votes to fit |
| Media finality proof | Retain existing proposed <=16 KiB Q4 outside canonical media record; journal close proof also external <=16 KiB candidate cap. Both are required archives/transport, not free bytes |

After maximal base64, **349,524** canonical bytes remain for descriptor/technical/
rights/caption/native/header/binding and all JSON keys. Reserving 8,192 for review
binding and 98,304 for native aggregate leaves **243,028** for all other fields.
This is a budget identity, **not proof of final combined-block fit**. Full component
enumeration, simultaneous maximum realizable cases, byte/depth vectors and
reconstruction tests are freeze gates. No raised cap, smaller originals or dropped
negative votes is silently allowed. A 1,000-reviewer vote array alone is ~3.9 MiB;
external authenticated evidence is necessary under the retained media cap.

Independent vote-history budget example, per archival node, **1,000 OPENs/day**
and 2,000 votes/session including failed/unresolved sessions, over 365*3=1,095 days:

| Three-year component | Arithmetic / bytes |
| --- | --- |
| Signed vote bytes at 2 KiB mean | 2,190,000,000 messages *2,048 = **4,485,120,000,000** (~4.08 TiB) |
| At 4 KiB signed-vote cap | **8,970,240,000,000** (~8.16 TiB); event wrappers/indexes/proofs extra |
| Nominal 5-second ticks | 17,280/day; **18,921,600** batches in three years |
| Batch metadata at assumed 1 KiB | **19,375,718,400** (~18.04 GiB), not including vote/event bodies |
| Journal commit proofs at 16 KiB cap | **310,011,494,400** (~288.72 GiB); at 4 KiB mean, **77,502,873,600** |
| Entire journal body capacity at 256 KiB/tick | **4,960,183,910,400** (~4.51 TiB), includes votes/wrappers/headers rather than adding them twice |
| Worst 8 KiB VOTE event allowance for this workload | **17,940,480,000,000**; exceeds body/time capacity above: this workload is infeasible at simultaneous maxima |
| Review-only original retention at 2 MiB/OPEN | **2,296,381,440,000** (~2.09 TiB), before rights/technical/alternate encoding copies; shared content-addressed accepted originals need not be stored twice |
| Canonical media at independent 1,000 accepted/day, full cap | **3,444,572,160,000** (~3.13 TiB); accepted/day need not equal OPEN/day |

The 2 KiB vote workload is 2,000,000 messages/day, **~4.82 times the nominal
414,720 messages/day count ceiling**. Therefore the illustrative
high-volume workload is **not serviceable** by this conservative journal profile,
even when its raw byte volume looks near the three-year body budget. At most
207 such 2,000-message sessions/day fit the 24-per-five-second count ceiling
before overhead/fairness, if every session were accepted and adequately scheduled.
The 1,000/day rows expose the independent storage demand, not a throughput claim.
Owner must approve an appropriate budget/rate/window revision after measurement,
or accept explicit queue/backpressure and lower served demand. Do not hide that
conflict by excluding failed reviews or discarding unfavorable votes.

Online archive provisioning needs headroom for wrappers, evidence/OPEN/CLOSE,
source objects, indexes, replicas/repair, backup copies, and future years. At most
the fixed tick/body budget can be admitted at the nominal rate; if actual batches
run faster, both admission capacity and proof/tick storage increase. Three-year
source recovery of 4.485 TB alone at sustained 100 Mbit/s is ~358,809.6 s (~4.15
days); at 10 Mbit/s ~41.53 days, before metadata, originals/media, crypto and disk
replay. Archive/liveness/replay CPU and signature verification require independent
measurements. No voted-byte pruning or untrusted snapshot shortcut is assumed.

## 12. Deterministic security scenarios

Assume A/B/C honest, D Byzantine, approved N4/f1/q3; each example uses the same
verified OPEN and >=1 base-established reviewer per dimension unless specified.

| Scenario | Ordered example / deterministic outcome | Guarantee or limit |
| --- | --- | --- |
| Positive cherry-picking | 5 positive +5 negative originality votes ADMIT before K; close=5/10 rejection. Producer submits only five positives | INVALID binding/set; cannot replace authenticated close |
| Negative omission | Replay R has negative at (20,3); producer's t/R omits it | Mismatch rejects; omitted **unadmitted** negative has no guaranteed inclusion |
| Byzantine censorship | D receives negative, withholds it and proposes ticks | If no honest node gets it before K, cannot count. Relay to A/B/C and honest proposer service may admit before K; no forcible deadline guarantee |
| Different local receipt order | A sees x,y; B sees y,x; decided positions y then x | All replay y,x; conflicts/quota use follow those positions |
| Sent just before close | Client sends negative at local 12:00; first VOTE at K+1 | LATE even if its storage ack predates K; no receipt-clock cutoff |
| Disconnected node | C misses OPEN through CLOSE then returns | Fetch ranges/data, verify and reproduce same result; missing bytes means unavailable, not empty votes |
| Conflicting choices | Wr positive ADMIT at 20, negative observation at 21 | Positive stays; one future-effective incident. Reverse agreed order gives negative first, identically on all nodes |
| Wrong network/genesis | Same N with G' or foreign N in valid signature | WRONG_CONTEXT; cannot add slot or penalty under G |
| Duplicate relay | 100 copies of exact V before/after restart | One accepted slot/charge; disk ownership outlives LRU |
| Malicious early close | D proposes CLOSE at o+1 after five positives | Invalid regardless of favorable quorum; only K=o+256 |
| Data withheld after tally | D sends signed PASS root, no vote bodies; or two archives later fail | Root alone cannot validate media; fetch honest custodians, else UNAVAILABLE. Retention assumption breach can halt recovery |
| Large vote flood | 10,000 eligible two-dimension reviewers offer 20,000 messages | Fixed window/rate cannot admit all. Busy/pending/late responses, bounded queues; every actual eligible admission counts. Never select by choice |
| Validator crash/recovery | A flushes sources/sign state, crashes before reply | Resume stored slot/lock and outbox; public source replay cannot repair lost hidden-signature custody |
| Competing media submissions | X,Y sessions share F, each passes; media BFT finalizes X at F+1 | Only X settles; journal anchors it. Y cannot reparent old votes; recorded work remains, approved stale retry may follow |
| Quota exhaustion | Probationary Wr has four charges; X then Y first VOTEs ordered | X consumes fifth; Y rejects. Reversing local arrival does nothing; reversing decided order swaps the winner |
| Prolonged no media | 100 days of journal ticks, no media anchor advance | Sessions close and evidence persists; media epoch/quota renewal/age stay fixed, may deadlock human review |
| All unsure / penalty timing | Five unsure ADMIT then established reviewer penalized after CLOSE | Unresolved forever for this attempt; neither future penalty nor favorable reinterpretation creates approval |

Safety does not establish social fairness. Wallet Sybils, correlated reviewers,
creator choice of submission timing, proposer pre-admission censorship and network
isolation remain. A Byzantine validator cannot alone finalize an invalid omitted
admitted set, but BFT does not force it to relay any particular client message.

## 13. Verification plan, exact invariants and minimal next task

Required invariants for any later test-only transition model:

* **S1 Prefix:** two honest finalized journal prefixes never disagree at the same
  height; each transition has a verified parent, profile and full source inventory.
* **S2 Slot:** at most one accepted choice per N/G/SID/dimension/Wallet; exact and
  semantic retries cause no new participation or penalty; conflicts do not rewrite.
* **S3 Coverage:** accepted set equals all and only eligible ADMIT transitions
  after OPEN and before mandatory CLOSE; no local queue or producer selection.
* **S4 Cutoff:** K=o+W, all due closes first, unique immutable close/tally/root;
  first attempts at K or later cannot affect this session, even with old acks.
* **S5 Tally:** exact p/n/u/e and rational arithmetic; both independent quorums
  and approvals required; no decisive-zero approval or established-seat bootstrap.
* **S6 Quota:** ordered first distinct submission charge once; no overspend across
  concurrent sessions, retries, restart or dimensions; historical status immutable.
* **S7 History:** every state-changing eligibility/offense/claim/settlement fact
  has a retained authenticated cause; absent data never means zero prior usage.
* **S8 Availability:** no honest value vote/media validation success without full
  checked/retained source bytes; proof-only candidates never pass application checks.
* **S9 Streams:** every media references a prior finalized closed session, exact
  finalized parent/G; journal media anchors reference earlier verified media Q4;
  no dependency cycle, replayed reward or wrong-stream validator signature.
* **S10 Recovery:** crash refines one continuing signer/replica; publication/acks
  follow durable state; stale/private-state loss cannot erase a signing reservation.

Future model outline: four replicas with separate journal/media locked/valid state,
network message multiset, pending/acked votes, complete source custody sets, static
genesis, media anchor, session table and ordered journal. Pure reducer applies
OPEN/VOTE/EVIDENCE/mandatory CLOSE/MEDIA_ANCHOR. Explore delivery permutations,
partitions, proposer equivocation/censorship, missing data, conflicting choices,
simultaneous quota spends, exact K boundaries and crash points. Start with small
W and finite users, then parameterize W=256; bounded exploration is not a proof.
Do not build this model in Task 7.17O.

Honest-node replay equality must compare canonical accepted-slot records and
positions, full source inventory, R/t, both tally objects, CLOSE IDs, participation/
quota/incident/penalty/claim maps and media outcome. Replay two independently
written reducers from G2 over byte-identical sources delivered in different
orders, with empty caches/different SQLite layouts. No shared oracle for both
expected and actual. A coherent prefix at a different height is compared only
after nodes catch up to the same authenticated target.

Negative controls must detect: removing an admitted negative; accepting union
of local queues; threshold acks treated as completeness; wrong G/session/dimension;
duplicate charge; conflict replacement; early close; missing base-established
seat; 69% rounded to 70%; zero decisive approval; media accepted on hash-only
evidence; journal QCs accepted as media Q4; dropped signer lock; remote snapshot
used without replay; post-close penalty rewriting old eligibility. Retain a
counterexample trace for each deliberately broken guard.

Cross-node tests cover every section 12 row, both locations of the Byzantine
validator/proposer where relevant, close under zero quorum, every first/last
admission position, 0/1/24 count and whole-byte/depth boundaries, 16 simultaneous
due closes, active-session/original locks, retry limit/delay, parent advancement,
epoch transitions, native/rights/technical failures and source-only bootstrap.
Retention tests delete each source type independently, corrupt bytes/digests,
serve empty/partial ranges at equal media tips, remove one archive then repair,
and enforce no success on unavailable history. Crash tests before/after source
flush, signing reservation, signature release, ack, batch promotion, CLOSE apply
and media-anchor publication; stale disk/copied-key tests must fence signing.

Independent gates: protocol/cryptography review of application and dual-stream
refinement; adversarial model review with negative controls; two-language signing/
canonical/commitment vectors; archive/recovery/durable signer review; target-host
resource and three-year recovery measurements; complete G2 semantics/bootstrap
and combined media fit review. Existing Tendermint model passes do not test this
new journal application. No production readiness follows from doc arithmetic.

**Smallest next implementation, only after decisions are approved and separately
authorized:** an isolated in-memory pure review-session reducer plus independent
replay fixtures exercising OPEN, ordered VOTE, conflict/quota and mandatory CLOSE,
with symbolic already-authenticated BFT positions. No sockets, production import,
keys, DB, signer, new canonical block or launch. Test evidence availability as
explicit inputs and refuse missing dependencies. First freeze exact policy/byte
contracts and owner choices; do not implement the network/journal adapter first.
This is a recommendation, not the beginning or authorization of Task 7.17P.

## 14. Owner decisions and readiness

| Status | Decision |
| --- | --- |
| **ALREADY DIRECTED** | All eligible authoritatively admitted pre-cutoff votes count; nodes gossip and independently tally; no producer-picked favorable subset; agreed deterministic cutoff |
| Preserved | Separate originality/admissibility, five eligible/one established per dimension, >=70% decisive, unsure excluded from decisive denominator, exact originals/rights/safety, 3 MiB media cap |
| **APPROVAL REQUIRED: architecture** | A's separate BFT review journal with ticks and media anchors versus explicitly versioned on-chain control records. Neither is authorized by previous media-only history proposals |
| Admission/receipts | Ordinary custody acks only; BFT ADMIT alone authoritative; first ordered choice immutable; signature variants/nonce scope, prospective conflicts, no replacement |
| Opening/closing | Creator-bound authenticated original, frozen base qualification plus live quotas/penalties, fixed W=256/K, no early close, zero-quorum unresolved close, human-time promise or explicit absence of one; separate authenticated rights/technical time-input or approved session-bound rights amendment |
| Retry/finality lifecycle | Original-level active lock, terminal negative, one delayed unresolved/stale retry, stale-parent coupling and anchor-before-next-media rule; no silent cancellation/reparenting |
| Storage/availability | Full pre-sign source retention, at least three-year online plus indefinite archive, >=2 honest q custodians, serving/repair obligations, external originals for failed reviews and explicit independent disk/network budget |
| Quota/reputation | ADMIT-time permanent participation including failed/unsure reviews; one lifetime submission charge shared across attempts/dimensions; base status, prospective penalties/incident grouping and promotion credit |
| Eligibility/bootstrap/no-media | Actual independent B0 reviewers/validator operators, earned thresholds retained; accept media-height epoch stalls or approve a separately specified replacement clock/quota policy; no journal grant or currency authority |
| Schemas/signing | Complete new user/open/receipt/journal/proof/history/certificate/media binding and policy registry bytes, low-S rule, descriptor/G2 amendments, version dispatch, independent vectors, no circular hashes |
| Capacity/timing | W/24 votes/256 KiB/5-second planning profile, overload behavior, source limits, pacing/retry/fair-service choices, binding/proof caps and final media fit; demonstrated 1,000-session/day overload must be resolved for that target |
| Security/operations | Static N4/f1/q3 authority and operator independence, key custody/fencing, lifetime key-compromise assumption, recovery/retention audits and independent review gates |
| Launch/production | Complete supported G2 application semantics, authenticated release pin, production-engine route and implementation validation, explicit activation/deployment authorization; none inferred |

Protocol direction is specified for review; authenticated review-history
implementation and production activation remain **BLOCKED** on the decisions and
evidence above. If the owner declines both new history architectures, the requested
pre-media authoritative voting behavior cannot be supplied under current history
constraints. Do not revert to producer-selected subsets, trust a local cache, or
label a quorum of storage receipts globally complete.

## 15. Executed verification and delivery record

Repository preflight and source review above completed before edits. The only
persistent tracked/untracked deliverables are this decision and the historical
proposal's supersession notice; disposable regression files are ignored under
`temp/task717o-regression-final/`. No implementation or test source was added.

| Executed check | Result and limit |
| --- | --- |
| Existing dual-review, earned-eligibility and G2 suites | **212 passed in 2.77 s**, no final failure/error/skip. These verify existing behavior, not this unimplemented profile |
| Python arithmetic | Nine independent tally cases in section 8 passed; three-year storage, 255-interior-height window, throughput and media-budget arithmetic checked |
| Independent Node arithmetic/bytes | Same nine tally results using BigInt products; five large storage totals independently matched; separately constructed canonical vote bytes/hash agree with Python |
| Structural vote example | J(V)=**1,507 bytes**, signed wrapper=**1,701**, EIP-191 preimage=**1,537**; no actual signing/key generation or valid-eligibility claim |
| Illustrative CLOSE event | Separately serialized Node example **862 bytes**, below proposed 2,048 cap; not exhaustive maximum-fit or a valid full-history vector |
| Documentation | Local Markdown links resolve; fenced blocks balance; `git diff --check` passes; historical 7.17N body preserved byte-for-byte after removing the ten-line notice |
| Scope | Branch/HEAD unchanged, index unchanged; only the two requested docs differ. No commits/push/merge or Task 7.17P |

Reproduce the existing regression selection from the repository root using a
fresh in-workspace base directory (do not overwrite an existing test directory):

```powershell
.\.venv\Scripts\python.exe -m pytest -q --tb=short `
  --basetemp=temp/task717o-regression-final `
  tests/test_milestone_6_task_6_5_dual_review.py `
  tests/test_milestone_5_task_5_5_earned_reviewer_eligibility.py `
  tests/test_milestone_7_task_7_17m_g2_genesis.py
```

Initial invocation without an explicit workspace `--basetemp` completed with
207 passes and **five setup errors**: pytest could not create numbered temporary
directories in the host's default temporary location. The fresh workspace path
resolved those errors without modifying tests/application code. Initial passes
are not added to the 212 distinct completed test passes. No API/network tests or
new transition/crash model were run; section 13 is a future verification plan.

Byte-example recipe: populate section 4's V with N=`zoidberg-signing-vector-v2`,
G=`a`*64, RP=`b`*64, RVP=`c`*64, REP=`d`*64, HP=`e`*64, S=`1`*32,
H=`2`*64, Wc=`0x`+`3`*40, SID=`4`*64, dimension=`admissibility`,
Wr=`0x`+`5`*40, key=`02`+`6`*64, choice=`not_admissible`,
Fh=9,007,199,254,740,991, Fhash=`7`*64, Jh=9,007,199,254,740,734,
Jhash=`8`*64, K=9,007,199,254,740,991, sequence=0, nonce=`9`*32.
Here `*` denotes repetition, not literal signed characters. The domain/protocol/
versions are section 4's literals. Wrapper signature is synthetic `0x`+`1`*130.
Sorted compact J yields SHA-256(M)=
`69213dedf3d2aed70609d6ca5ac093bb40a4d475f79662405d174b90e8b87740`.
The key/Wallet/signature are structural placeholders with no asserted key-control,
crypto validity or consensus authority. No Keccak/signature interoperability
vector is claimed; actual cryptographic golden vectors remain a readiness gate.

Proposed network transitions, crash scenarios, data-service guarantees and new
security properties remain **unimplemented and unverified by executable model**.
Documentation/arithmetic and existing regression success support reviewability;
they do not authorize or establish launch readiness.

