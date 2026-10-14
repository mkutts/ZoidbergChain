# Milestone 6 Task 6.7 — current pre-mint community reporting

Task 6.7 adds a separate signed `REPORT` action for current, attested Public
Testnet v1 media submissions. A report asks for additional safety review. It is
never an originality vote, an admissibility vote, technical validation, a final
content-policy judgment, or a post-mint dispute decision. ZOID remains native
Layer 1 currency, and accepted Model A media bytes remain immutable in blocks.

## Policy and eligibility

Policy ID `zoidberg-public-testnet-v1/community-report/1`, version `1`, is
hashed with Protocol v1 canonical JSON. Task 6.7A keeps that signed policy
digest unchanged while clarifying how the existing one-accepted-per-wallet
rule resolves conflicting valid observations. The reason enum is:

- `potentially_illegal_content`
- `nonconsensual_or_private_content`
- `exploitation_or_abuse_concern`
- `dangerous_or_harmful_content`
- `impersonation_or_deceptive_manipulation`
- `other_policy_concern`

These are neutral flags, not legal findings. **POLICY TODO — OWNER DECISION
REQUIRED:** exact prohibited-content definitions and jurisdiction.

A reporter must own a verified wallet session, pass the controlled-testnet
access and local review service gates, be distinct from the submitter, and have
an `ESTABLISHED_REVIEWER` or `PROBATIONARY_REVIEWER` status derived from the
existing finalized-chain Milestone 5 reviewer/reputation model. Cooldown,
suspended, and new reporters are ineligible. A probationary reporter counts
once toward the valid-report minimum but not the established-reporter minimum.
The status and finalized block reference are persisted with the signed report;
peers independently resolve that historical status. Finalization builds a durable
qualification-height index from canonical activity. The report path checks its
finalized block hash and looks up the wallet in that index, then applies the
existing accepted-vote promotion and reputation-penalty rules at the referenced
epoch. A missing or stale index fails closed. Startup validates the persisted
index and deterministically rebuilds missing or corrupt snapshots once; new
finality appends snapshots. A reorg cannot replace finalized history, and the
canonical hash check rejects a stale reference. Ordinary report eligibility
does not traverse chain ancestry; index lookup is O(1) in chain length, plus
the wallet's durable vote and reputation queries. Reputation does not weight
the report. Local voting rate limits can refuse service but do not change the
canonical one-wallet-one-report tally.

## Signed action and replay

The distinct signing domain is `zoidbergchain/community-report/v1` using
MetaMask-compatible EIP-191 `personal_sign`. Its compact canonical JSON payload
binds `domain`, `network_id`, `policy_id`, `policy_version`, `policy_digest`,
`reviewer_policy_version`, `reputation_rule_version`, normalized `wallet_address`,
`submission_id`, exact `content_hash`, one enum `reason`, random `nonce`,
`issued_at`, and `expires_at`. The server issues a five-minute report challenge.
It is single use for local submission, and its signature is checked against the
verified session wallet. A report signature cannot replay as a vote,
attestation, or login because those have different canonical messages/domains.

Each submission stores observed valid signed report records independently from `votes`.
The record retains payload, canonical message, signature, report identity, and
finalized reviewer reference. A report identity hashes the canonical payload
and normalized signature. An exact record retry returns `duplicate`. A distinct
valid report from the same wallet is retained as conflict evidence and returns
`conflict_recorded`; it cannot add weight. Observations are stored in canonical
order and retransmitted together. The counted representative has the lowest
signed identity for that wallet; a complete-record digest breaks an identity
tie. This tie-break uses signed/canonical record data, never arrival time, peer
identity, or reputation. If any valid observation for that wallet proves
established status at its finalized reference, the wallet counts once toward
the established minimum. The counted report set carries that canonical
established evidence separately from the representative's reason and reference.
An added conflict therefore cannot undo an already met threshold. One wallet
contributes one report.
Storage serialization preserves these records in JSON and SQLite submission
sections without a schema migration. Existing submissions deserialize with an
empty report set. There is no public report deletion or override endpoint.

## Tally and quarantine

The counted report set is sorted by normalized wallet address. Conflicting raw
observations have their own deterministic count and digest for audit.
Canonical evidence includes policy digest, submission ID, exact media hash, and
for each report its wallet, reason, identity, and finalized reviewer reference.
The SHA-256 Protocol v1 canonical hash of that object is `report_set_digest`.
Reason counts use only counted representatives; different reasons carry equal weight. The
threshold is `valid_count >= 3 AND established_count >= 1`. One or two reports
never quarantine. A threshold hit enters the existing terminal pre-mint
`quarantined` state with reason `community_report_threshold`, removes the item
from the mint queue, and stores policy identity, sorted report set, counts,
digest, and quarantine trigger identity on the submission. The canonical
three-report trigger is the lexicographically first counted three-wallet set
containing an established reporter. Its digest is recomputed from the complete
observed set. No first-arrival snapshot is protocol-visible. Later reports may
still be accepted; current proof and trigger are updated deterministically, so
nodes with the same complete signed set have identical evidence regardless of
delivery order. Quarantine remains terminal after the first threshold hit.

A previously frozen admission certificate remains byte-identical evidence of
the earlier decision. It is not sufficient to mint a quarantined submission.
The atomic mint path rechecks the report threshold as well as certificate and
queue status. The report transaction and block commit use the same durable
storage lock/transaction. If threshold quarantine commits first, mint sees the
quarantine and fails. If block commit wins first, a later Task 6.7 report is
rejected with `Post-mint dispute flow required`; the block is never rewritten
or deleted. Ordinary whole-state saves compare report records and quarantine
against durable state under the storage lock and reject a stale snapshot, so a
stale facade cannot erase the threshold state or requeue the item. The caller
must reload before retrying. Existing votes remain preserved and further review
votes are locked after quarantine. No report adjudication,
unquarantine, appeal, or new review round is defined here.

The report policy refers to the Task 6.6 admission activation boundary; it
does not set a second independent block height. Historical pre-activation
submissions remain readable and are not retroactively report-admitted.

## API, peers, and UI

`GET /reports/policy` exposes policy/digest. `GET
/submissions/{id}/reports/status` exposes counts, thresholds, reason counts,
current report-set digest, and quarantine state. A verified wallet requests a
signed challenge at `POST /submissions/{id}/reports/challenge`, then submits
the report signature at `POST /submissions/{id}/reports`. A finalized
submission receives an explicit post-mint-dispute-flow response. The reviewer
screen has a separate Report reason selector and confirmation text explaining
that a report is not an admissibility vote.

Authenticated peers receive complete report records at `POST
/peers/reports/receive`. Each peer verifies the signature, policy, media and
submission binding, historical reviewer status, and current
pre-mint state under its durable transaction. A peer submission transport may
carry report fields for compatibility, but those fields are ignored on initial
submission ingestion; only the verified report receive path accepts them.
`POST /submissions/{id}/reports/broadcast` requires a verified, access-eligible
wallet and retransmits the stored report set to active peers when earlier
best-effort gossip was missed.
Unknown policy versions/digests fail closed. Report tally touches only the
submission's observed set, and unrelated block validation does not scan reports.

## Remaining decisions and risks

**POLICY TODO — OWNER DECISION REQUIRED:** final prohibited-content definitions
and jurisdiction; appeals; recusal; reviewer welfare; false-report adjudication
and penalties; unquarantine and re-review workflow; post-mint dispute
adjudication. Task 6.8's separate finalized-media dispute protocol is described
in `milestone-6-task-6.8-post-mint-disputes.md`. No automatic penalty is imposed
for an unsubstantiated report.

The threshold protects the mint path after its committed transition. As with
the existing Milestone 5 reviewer model, wallet status depends on finalized
ancestry; peers must synchronize that ancestry before accepting a report.
Peer gossip is best-effort and a temporarily disconnected peer can remain
behind until reports are retransmitted. Once both peers receive the same signed
observations, counted reports, reason counts, digest, and quarantine proof
converge even when a wallet signs conflicting reports. Finalization or a
one-time missing-index recovery traverses ancestry; ordinary report checks do
not. This task does not add report adjudication or finalized-media serving
controls.
