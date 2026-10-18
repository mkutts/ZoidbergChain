# Milestone 6 Task 6.8 — finalized-media disputes

**POST-MINT DISPUTE DOES NOT DELETE, REWRITE, OR DE-FINALIZE MEDIA.**

This task adds signed, independently verifiable dispute observations about a
canonical finalized Public Testnet v1 media block. The original block, embedded
Model A media bytes, admission certificate, native transactions, rewards, block
hash, and finality evidence remain unchanged. A node without dispute metadata
still validates the same blockchain. Nodes may temporarily show different
dispute overlays while gossip is incomplete; the same valid observations produce
the same overlay regardless of arrival order.

## Policy and signed action

The separate policy is `zoidberg-public-testnet-v1/post-mint-dispute/1`, version
`1`. Its digest is the Protocol v1 canonical JSON SHA-256 hash of
`post_mint_dispute.dispute_policy()`:
`2cc347de4f0895d50b60a0631d83c46fbbc069ef0b04e473173145bad5172ed7`.
It fixes one-wallet-one-dispute weight,
eligibility, a finite reason enum, the lowest-signed-identity conflict rule,
and the 3-valid-plus-1-established threshold. Reason values are:

- `potentially_illegal_content`
- `nonconsensual_or_private_content`
- `exploitation_or_abuse_concern`
- `dangerous_or_harmful_content`
- `impersonation_or_deceptive_manipulation`
- `post_mint_provenance_or_originality_challenge`
- `other_policy_concern`

The EIP-191 `personal_sign` domain is
`zoidbergchain/post-mint-dispute/v1`. The canonical JSON payload binds
`domain`, `network_id`, `policy_id`, `policy_version`, `policy_digest`,
`reviewer_policy_version`, `reputation_rule_version`, normalized
`wallet_address`, `submission_id`, exact canonical `block_height` and
`block_hash`, exact immutable `media_hash`, enum `reason`, random `nonce`,
`issued_at`, and `expires_at`. The local challenge lasts five minutes and is
single-use. An exact stored retry returns `duplicate`. Different signing
domains prevent a report, either vote dimension, attestation, or wallet login
signature from authenticating a dispute. Peers verify the signed payload and
historical reviewer reference independently; they do not apply their current
clock to an already signed observation.

## Finalized identity and eligibility

The block is located by a canonical submission-to-height index built at startup
and incrementally extended for later blocks.
The node checks the block's submission ID and canonical height/hash against
durable finality records, then hashes the actual embedded media bytes and
requires `SHA-256(media_bytes) == media_hash == content_hash`. A mutable or
missing submission document is not the authority: a provable finalized block
is sufficient. Unfinalized and noncanonical blocks fail. The media creator
cannot dispute their own block.

The Task 6.7A finalized reviewer qualification index supplies bounded
historical eligibility. Established and probationary reviewers each count
once; only established reviewers count toward the established minimum.
New, cooldown, suspended, and other ineligible wallets do not count.
Reputation never multiplies weight. No false-dispute penalty exists because
adjudication is outside this task.

## Evidence, tally, and persistence

The `post_mint_disputes` storage section is separate from `chain`, admission
certificates, votes, and pre-mint community reports. JSON and SQLite load the
section as an optional additive migration with an empty-map default. It maps
submission ID to all valid signed observations. Records include the exact
payload, canonical message, signature, signed identity, and finalized reviewer
reference. An exact duplicate is not stored again. A distinct valid signed
observation from the same wallet remains durable equivocation evidence but
adds no weight.

Observations sort by normalized wallet, signed identity, and complete-record
digest. The first observation per wallet is the counted representative, so
the lowest signed identity wins independent of delivery order. An established
historical reference in any valid observation for that wallet establishes its
single established qualification without changing its representative reason.
JSON-to-SQLite migration and portable export/import preserve the observations;
older snapshots without the section load with an empty map. Reason counts use
only representatives. The counted dispute-set digest hashes
the policy digest, submission ID, finalized height/hash, media hash, and
ordered counted evidence. The observed-set digest separately commits to all
signed observations. Count, reasons, digests, and threshold reconstruct after
restart from those observations.

`threshold_met` means at least three distinct valid wallets **and** at least
one established disputer. It changes the additive `post_mint_status` from
`finalized` to `disputed`; `finalized` and `media_immutable` remain true.
There is no deletion, finality override, consensus effect, reward clawback,
or change to the frozen Task 6.6 admission certificate. Task 6.7 `REPORT`
remains pre-mint; its finalized path rejects and directs clients to disputes.
Reports are never automatically converted into disputes.

## API, peer sync, and UI

`GET /disputes/policy` returns the policy and digest.
`GET /submissions/{id}/disputes/status` returns the additive overlay.
`POST /submissions/{id}/disputes/challenge` and
`POST /submissions/{id}/disputes` require a verified access-eligible wallet;
the challenge also applies the existing review service gate. The signed
submission is checked again against durable canonical finality under the
storage transaction. The finalized block list shows a distinct **Dispute**
reason selector, immutable-media explanation, count, and threshold state.

Authenticated peers send signed records to `POST /peers/disputes/receive`.
The verified-wallet `POST /submissions/{id}/disputes/broadcast` endpoint
retransmits all observations after missed best-effort gossip. Peers reject an
unknown policy identity/version/digest and verify the block/media binding,
signature, and reviewer reference. They converge after receiving the same
observations. Ordinary dispute checks use the incremental submission index
and Task 6.7A reviewer projection rather than whole-chain ancestry traversal.
SQLite durable accepted-vote history is queried by an indexed reviewer wallet,
so unrelated wallets' vote rows are not loaded for a dispute.
Unrelated block validation does not tally disputes.

**POLICY TODO — OWNER DECISION REQUIRED:** exact prohibited-content definitions
and jurisdiction; appeals, legal adjudication, resolution, recusal, reviewer
welfare, presentation suppression, and false-dispute treatment. Conflicting
signed observations are retained for audit and deterministic convergence;
their durable storage can grow without a policy bound. A retention/abuse limit
requires an owner decision that preserves cryptographic evidence.
