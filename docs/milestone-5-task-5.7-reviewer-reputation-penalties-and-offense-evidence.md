# Milestone 5 Task 5.7: Reviewer reputation penalties and offense evidence

## Versioned policy

Reputation Rule v1 remains the historical, inactive rule. Its digest is
`9bfdfc196fd6d54796d699b513a550672b6e12d659b9dbb52f1e44b065be17fb`.
Task 5.7 activates Reputation Rule v2, whose digest is
`0605b0cbd81ee7f7dade23651f44d88473d752661470de0035925fdc5a1c7c12`.
Both definitions remain retrievable and unknown versions fail deterministically.
Reviewer Policy v1 is unchanged, including digest
`ac6140446255e0d2a4f076f0d257a48d6a6a446dde2272a51568e8f020ee90eb`.

Rule v2 contains every escalation threshold, duration, grouping rule, status
precedence rule, and the finalized-height epoch source in canonical network
data. Collusion remains alert-only. Vote weight remains one.

## Objective offenses

Only a valid, attributable Protocol v1 `personal_sign` vote can support an
automatic penalty. Signature recovery, signed-message reconstruction, network,
submission, content hash, vote choice, and signed vote identity are independently
checked.

- `SIGNED_VOTE_EQUIVOCATION` requires different signed choices by the same
  normalized wallet for the same submission and content hash. All such votes
  form one incident keyed by reviewer, submission, and content. A third choice
  or retransmission cannot create another incident for that submission.
- `CREATOR_SELF_VOTE` requires the valid signed voter and canonical submission
  creator to normalize to the same `0x` address. The incident is keyed by signed
  vote identity.
- `RATE_LIMIT_ABUSE` counts unique valid signed excess attempts by reviewer and
  finalized review epoch. Accepted votes are not excess attempts. Attempts one
  and two are reject-only; attempt three creates the epoch incident. Invalid,
  malformed, or identical replayed requests do not increase the count. Its
  canonical evidence carries the complete signed quota-consuming vote set and
  the three unique excess attempts, so peers prove quota exhaustion rather than
  trusting a sender's label or local arrival order.
- `VOTE_DURING_COOLDOWN` and `VOTE_DURING_SUSPENSION` require a valid signed
  attempt and reference the active penalty. They never make the attempted vote
  countable.

Minority votes, `NOT_ORIGINAL`, `UNSURE`, disagreement, ordinary reviewer
ineligibility, and identical retransmission are not offenses. Node-local IP,
device, browser, cookie, fingerprint, timing-correlation, funding, geolocation,
and Sybil heuristics are excluded from reputation consensus.

## Canonical offense identity

Offense evidence version 1 contains the normalized reviewer, offense type,
submission and content binding, sorted signed-vote evidence, Reputation Rule
version, finalized reference height and block hash, review epoch, creator where
applicable, and active penalty reference where applicable. Signatures have a
single lowercase `0x` representation. The evidence digest is the canonical hash
of that payload.

The offense ID is a separate canonical incident hash:

- equivocation: reviewer + submission + content;
- self-vote: signed vote identity;
- rate-limit abuse: reviewer + review epoch;
- in-penalty attempt: offense type + active penalty ID + signed vote identity.

Operational observation timestamps and node IDs are excluded. Repeated offense
IDs and evidence digests are idempotent.

### Hardened rate-limit proof

A rate-limit offense contains a `rate_limit_context` with the applicable quota
(`5` for a probationary reviewer or `25` for an established reviewer) and
exactly that many canonical accepted signed votes. The vote set is selected
from durable SQLite accepted-vote history for the reviewer and finalized epoch,
then sorted by vote identity. Every accepted proof vote has a distinct vote
identity and submission, an eligible historical reviewer snapshot, and active
Reviewer Policy v1/Reputation Rule v2 bindings.

The offense also carries exactly the three canonical signed excess attempts
that established the threshold. Those identities are unique, disjoint from the
accepted set, bound to the same reviewer and epoch, and marked quota-ineligible.
Signature recovery and canonical message/identity reconstruction are repeated
for every accepted and excess vote. Identical retries therefore cannot increase
the threshold or manufacture three identities.

Peer verification is set-based, not request-order-based. The receiver sorts and
recomputes the proof, confirms each claimed quota vote has the identical signed
identity and payload in its own durable `accepted` history, reconstructs the
historical underlying reviewer status at each finalized vote reference, and
checks each canonical submission creator. Only then can it derive
`accepted_quota_count == applicable_epoch_limit` and
`unique_excess_attempt_count >= 3`. Three otherwise valid signatures without
the local canonical accepted quota history are insufficient and are rejected.

## Escalation and penalty timing

Escalation is per offense type and comes from durable offense history:

| Offense | First | Second | Third and later |
| --- | --- | --- | --- |
| Signed equivocation | 3-epoch cooldown | 10-epoch cooldown | 25-epoch suspension |
| Creator self-vote | 1-epoch cooldown | 3-epoch cooldown | 25-epoch suspension |
| Rate-limit abuse | 1-epoch cooldown | 3-epoch cooldown | 25-epoch suspension |

Further equivocation or self-vote evidence observed while suspended is retained,
but it does not reset or shorten the active suspension. There is no permanent
ban and no economic slashing.

The authoritative epoch is always
`finalized_canonical_height // 5`. Wall-clock time and the unfinalized head are
irrelevant. Penalties are active for `start_epoch <= epoch < end_epoch`.
Cooldown voting extends with:

`max(existing_effective_end_epoch, offense_epoch + active_cooldown_duration)`

Suspension outranks cooldown. Otherwise the effective ineligible end is the
maximum end among active penalties. An expired penalty restores the latest
underlying `NEW`, `PROBATIONARY_REVIEWER`, or `ESTABLISHED_REVIEWER` state.
Existing probation start and accepted-vote history are retained, so expiry does
not promote or restart probation.

## Storage and recovery

SQLite adds three idempotently created tables:

- `reviewer_offense_records` stores canonical evidence, digest, incident ID,
  canonical reference, before/result state, sequence, and penalty outcome;
- `reviewer_penalties` stores each cooldown or suspension and its restoration
  class;
- `reviewer_rate_limit_excess_attempts` stores unique signed excess attempts.

The existing reviewer state and transition tables retain the effective-state
audit trail. Opening an older Task 5.6 database performs a non-destructive,
repeatable schema migration and fabricates no offenses. SQLite physical backup
includes the new tables. Portable backup/export/import includes all three record
sets and restores offenses before penalties. JSON remains development-only and
does not claim consensus-equivalent reputation durability; JSON-to-SQLite
conversion creates empty reputation tables without inventing history.

## Public and peer behavior

The public signed-vote and authenticated peer-vote paths verify the signature
before offense handling, retain conflicting or otherwise rejected valid signed
votes, apply identical grouping and escalation, and leave identical replay
non-penalizing.

Authenticated peers can transfer an offense through
`POST /peers/reviewer-offenses/receive`. The receiving node recomputes signed
vote identities, signatures, evidence digest, offense ID, canonical creator, and
finalized reference. For rate abuse it additionally matches every quota vote
against local durable accepted history and reconstructs its historical reviewer
status. A peer cannot submit a state or penalty command; local state changes
occur only after evidence verification. Unsupported rules, missing or fabricated
quota context, duplicate excess identities, tampered evidence, fake creators,
wrong epochs/statuses, and non-final references are rejected.

Read-only visibility is available from:

- `GET /reviewers/{wallet_address}/reputation`;
- `GET /reviewers/{wallet_address}/offenses`.

The status response reports underlying and effective status, active penalty,
start/end, remaining epochs, per-type counts, latest offense, and active rule
version. There is no public reputation mutation endpoint.

## Certificate v3 and finality

New certificate-v3 votes and snapshots bind Reputation Rule v2. Penalized
reviewers cannot contribute at a snapshot where the penalty is active.
Certificate validation dispatches the reputation rule carried by the historical
certificate and reconstructs status at its bound finalized reference. A later
penalty therefore does not invalidate a vote or v3 certificate that was valid at
its earlier reference. Certificate v1/v2 and the v3 quorum constants remain
unchanged.

Shallow unfinalized reorganization cannot change penalty timing. Exceptional
finalized rollback continues to use the existing recovery architecture; Task
5.7 introduces no new fork-choice or rollback rule.

## Remaining risks and Task 5.8 boundary

Nodes must exchange the canonical offense records they have observed; a node
cannot infer a valid signed excess attempt it never received. A peer also cannot
apply a rate-abuse offense until its canonical accepted-vote history contains the
quota votes in the proof, so normal vote synchronization must precede or be
retried before offense synchronization. Operational monitoring should alert on
these delivery/order gaps. Task 5.8 may consume offense-independent collusion
signals for analytics, but must keep them alert-only and must not feed them into
these tables, reviewer eligibility, voting weight, or certificates.
