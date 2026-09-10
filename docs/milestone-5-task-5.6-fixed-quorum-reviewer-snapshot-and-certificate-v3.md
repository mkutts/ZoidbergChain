# Milestone 5, Task 5.6: fixed quorum, reviewer snapshots, and certificate v3

Task 5.6 activates deterministic Reviewer Policy v1 eligibility in the
consensus-valid vote and certificate path. It introduces originality
certificate version 3 without changing legacy, certificate-v1, or
certificate-v2 interpretation. Automatic reputation penalties and collusion
analytics remain deferred.

## Fixed certificate-v3 quorum

Public Testnet v1 certificate v3 uses constants that are separate from the
already-active Reviewer Policy v1 canonical object:

- `MIN_VALID_VOTES = 5`
- `MIN_ESTABLISHED_VOTES = 1`
- `APPROVAL_THRESHOLD_BPS = 7000`

The separation preserves Reviewer Policy v1 digest
`ac6140446255e0d2a4f076f0d257a48d6a6a446dde2272a51568e8f020ee90eb`.
Reputation Rule v1 remains unchanged at digest
`9bfdfc196fd6d54796d699b513a550672b6e12d659b9dbb52f1e44b065be17fb`.

All three conditions are mandatory:

```text
total_valid_votes >= 5
established_vote_count >= 1
original_votes * 10000 >=
    (original_votes + not_original_votes) * 7000
```

The approval comparison uses integers only. `UNSURE` has weight 1 and counts
toward `total_valid_votes`, but is excluded from the decisive approval
denominator. Probationary and established votes both have numerical weight 1;
established status only contributes to the separate established minimum.

Voting-window expiry never bypasses any v3 quorum condition. A pending
submission remains pending with `awaiting_fixed_quorum` until both vote
minimums are met. Once they are met, the integer approval comparison determines
approval or rejection. The old active-user calculation remains available for
legacy UI and version-2 compatibility paths only.

## Vote admission and durable proof

New signed votes evaluated against finalized state copy Reviewer Policy v1,
Reputation Rule v1, the derived reviewer status, the finalized reference
height/hash, an independently recomputed eligibility result, and the canonical
signed vote identity. Only `PROBATIONARY_REVIEWER` and
`ESTABLISHED_REVIEWER` are countable for v3. `NEW`, `COOLDOWN`, and
`SUSPENDED` are excluded. Local `open`, `allowlist`, `activity`, and `hybrid`
modes may refuse service but cannot grant v3 consensus eligibility.

Creator and voter are compared after canonical Ethereum-address
normalization. SQLite continues to enforce one accepted wallet vote per
submission. Identical replay resolves to the existing evidence and consumes no
additional quota. Conflicting signed peer votes are now retained through the
same rejected durable-evidence path as public signed conflicts, without any
automatic penalty.

The existing per-epoch limits remain 5 accepted probationary votes and 25
accepted established votes. Rejected conflicts and quota violations do not
count.

## Finalized snapshot semantics

The v3 reviewer snapshot reference is the highest persisted
quorum-finalized canonical block used at certificate issuance. The certificate
reference uses the same finalized state. A snapshot contains the two policy
versions, finalized height/hash, review epoch, and the sorted participating
reviewer list with status and nullable bootstrap provenance. Operational
timestamps are excluded from the canonical digest.

Status reconstruction at a historical reference uses canonical activity,
versioned bootstrap membership, accepted probation vote history, and any
applicable cooldown/suspension transition. It does not infer a historical
status from the node's later current projection. Promotion requires the locked
three-epoch duration and ten accepted probationary votes.

## Certificate-v3 schema and identity

The domain-separated canonical identity binds:

- certificate, protocol, and network versions;
- submission, content, and normalized creator identity;
- complete Task 5.3 originality Rule-v1 decision, reference, and evidence
  digest;
- Reviewer Policy v1 and Reputation Rule v1 versions;
- reviewer snapshot finalized height/hash and digest;
- all three fixed quorum constants;
- total, established, original, not-original, and unsure counts;
- the certificate-v3 vote-set hash;
- finalized certificate reference height/hash; and
- the canonical issued timestamp copied from the reference block.

The v3 vote-set hash is separately versioned. It commits to each sorted voter,
choice, signed vote identity, policy versions, admission status/reference, and
the eligibility assertion that validators must recompute.

The golden certificate-v3 identity is:

```text
602fab0ee3ef97a46c5fa759399636a8ea6729a4fde386c2d8bc3f6ef0b7766e
```

Validation recomputes originality evidence, signed vote identities and
signatures, canonical reviewer status at each vote reference, the bound
snapshot, all tallies, established participation, integer approval, quorum,
vote-set hash, and certificate ID. Stored result or tally fields are never
authoritative on their own.

## Peer validation

Realtime peer vote receipt verifies the signature and canonical vote payload,
then derives reviewer eligibility, status, epoch, and quota locally. Peer
reviewer assertions are not trusted. Version-3 evidence transfer carries the
full signed counted vote records. The receiver validates and durably admits
them before accepting the certificate. Missing reviewer history, finalized
state, media, originality evidence, or votes is a validation failure rather
than a shortcut.

Peer certificate validation uses the receiver's durable accepted-vote set and
reconstructed snapshot. Fake established status, an inflated established
count, an omitted vote, an incorrect policy version, a wrong snapshot digest,
or altered quorum constants invalidate the certificate.

## Historical compatibility

- An absent version retains the original legacy identity and validation.
- Certificate v1 retains Protocol-v1 semantics.
- Certificate v2 retains Task 5.4 evidence binding and requires canonical null
  reviewer/reputation/snapshot/established fields.
- Certificate v3 alone activates reviewer snapshots and fixed quorum.

Development without finalized state retains legacy version-2 issuance for old
fixtures and local tooling. Those null-reviewer votes cannot enter a v3 vote
set.

## Persistence, migration, and reorgs

SQLite adds nullable `reviewer_eligible` durable-vote evidence and expands the
certificate evidence-binding table constraint from version 2 to versions 2 or
3. Startup migration rebuilds only that constrained table, copies every v2
row, and is safe to repeat. Existing votes, reviewer histories, evidence, and
certificates are preserved; no v3 snapshot is fabricated for v2.

Canonical storage validation requires active v3 reviewer and certificate
references to be finalized. Reorg handling now includes the reviewer snapshot
reference. A shallow reorg above unchanged finalized state leaves the snapshot
unchanged. A stale originality, certificate, or reviewer reference marks the
v3 certificate `invalidated_by_reorg` through the existing lifecycle and
removes unminted queue eligibility. No fork-choice rule changes.

## Remaining risks and Task 5.7 boundary

- A node synchronizing a promoted established reviewer needs the relevant
  durable probation-vote history; absence blocks validation by design.
- Snapshot reconstruction currently scans canonical ancestry for the first
  qualifying height. This is deterministic but should be indexed if chain
  length makes repeated validation expensive.
- The canonical bootstrap-established set remains empty, so deployment needs
  at least one earned established reviewer before v3 certificates can issue.
- Task 5.7 must version and activate objective reputation penalties rather than
  editing Reputation Rule v1 in place. Minority votes, identical replay, and
  rate-limit failures remain non-penalized in Task 5.6.
