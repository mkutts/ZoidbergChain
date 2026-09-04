# Protocol v1 Lifecycle And Finality

Authoritative note: [docs/protocol-v1.md](/C:/Users/mattk/ZoidbergChain/docs/protocol-v1.md) is the primary Public Testnet v1 protocol specification. If this document conflicts with it or with [docs/protocol-v1-freeze-report.json](/C:/Users/mattk/ZoidbergChain/docs/protocol-v1-freeze-report.json), the authoritative spec and freeze report win.

As of Saturday, August 29, 2026, Task 7 freezes the Protocol v1 submission lifecycle and block-state semantics for ZoidbergChain Public Testnet v1.

This document defines exact meanings for the lifecycle terms used by the code in `submission.py`, `blockchain.py`, `api.py`, and `peer_sync.py`.

## Task 3.5 Public Testnet v1 quorum finality update

Task 3.5 supersedes the older depth-only definition of `finalized` below. Confirmation depth remains confirmation metadata, but `finalized` now means that the exact canonical block has durable valid attestations from a known validator set meeting `ceil(2N / 3)`, implemented as `(2 * N + 2) // 3`. An empty set never finalizes a block.

Validator identities are normalized Ethereum `0x` addresses and signatures use the established MetaMask `personal_sign` recovery path. They are deliberately distinct from HMAC-authenticated peer node identities. `PUBLIC_TESTNET_V1_VALIDATOR_ADDRESSES` is a comma-separated configured controlled validator set; malformed entries fail startup, duplicates are de-duplicated, and membership plus the quorum threshold are snapshotted in finality evidence.

The signed canonical attestation payload is `attestation_version`, `validator_address`, `block_height`, and `block_hash`, wrapped in the canonical Protocol v1 domain `zoidbergchain/finality-attestation/v1` with the exact `network_id`. It has no local receive time. Each counted signature must recover to a configured validator and match that canonical message, network, height, and hash.

One validator has one vote per height and block hash. Identical attestations are idempotent. Conflicting hashes from one validator at one height are recorded as equivocation evidence and are excluded from live vote counts; no economic penalty or slashing is implemented. Attestations for a nonexistent, invalid-hash, noncanonical, wrong-height, or wrong-network block are rejected.

Attestations and finalized quorum certificates are persisted in deterministic order with the validator-set snapshot, threshold, and signatures, so restart and independently supplied identical evidence converge. A finality certificate never moves backward. Fork choice otherwise remains unchanged, but a candidate chain that would omit or change any finalized height/hash is rejected. Known-validator quorum finality does not replace Meme Proof of Originality: certified original content remains the only block-earning/proposal mechanism.

Threat model: this is controlled-validator Testnet v1 finality, not permissionless staking or a full BFT protocol. It assumes the configured validator set is distributed consistently and that at least a quorum of its signing keys is honest.

Genesis identity and reset policy are frozen separately in [docs/protocol-v1-genesis-reset.md](/C:/Users/mattk/ZoidbergChain/docs/protocol-v1-genesis-reset.md). This document defines how genesis participates in the same canonical/confirmed/finalized depth rules once it is the selected chain root.

## 1. Persisted submission statuses

The repository still persists the existing submission status values:

- `pending`
- `approved`
- `queued`
- `rejected`
- `hard_rejected`
- `minted`

Task 7 does not add a second mutable protocol-status field. Instead, Protocol v1 lifecycle terms are derived deterministically from persisted submission state, the originality certificate set, the selected chain, and the configured confirmation/finality depths.

## 2. Exact Protocol v1 meanings

### Submitted

- The submission record exists.
- Initial content checks have already passed.
- No originality decision is implied by `submitted` alone.

Every stored submission is `submitted=true`.

### Voting

- The submission is still `pending`.
- No certificate exists for it.
- Vote locking has not activated.

In the current implementation, `voting` is a derived phase, not a persisted status string.

### Rejected

- The submission has reached a terminal non-mintable originality outcome.
- This includes `rejected`.
- `hard_rejected` is a stronger privileged rejection/quarantine state and is also treated as rejected for Protocol v1 lifecycle purposes.

Rejected submissions cannot mint and cannot receive new votes.

### Certified

- A valid originality certificate exists for the submission's final vote set.
- The certificate must validate against the stored submission and the local network rules.

Certification locks the vote set. Later votes are rejected.

### Mint-eligible

- The submission is certified.
- It has not already produced a Protocol v1 block on the selected chain.
- It is not mint-blocked.
- The content/media and certificate data are sufficient to construct exactly one Protocol v1 block.

`mint-eligible` is derived. It is not a separate persisted status.

### Block created

- A candidate block object has been constructed locally.
- In code this is the result of `Blockchain.build_block_candidate(...)`.

Block creation alone does not mutate canonical chain state, reward records, or transaction settlement.

### Block accepted

- The candidate block passed local acceptance validation.
- The block extends the expected parent.
- The block hash is valid.
- Protocol v1 media, certificate, reward, and native-transaction validation all pass.
- The block is then appended to the node's current selected chain.

In code this happens through `Blockchain.accept_block_candidate(...)` for local construction and through peer acceptance validation in `peer_sync.py`.

### Canonical

- The block is on the node's currently selected chain after fork choice.
- Canonicality is derived from the selected chain.
- The repository does not persist a mutable `canonical=true` flag.

The current fork-choice order remains:

1. higher cumulative originality score
2. higher chain height
3. lower latest block hash

### Confirmed

- The block is canonical.
- `confirmations = canonical_tip_height - block_height`
- The block is confirmed when `confirmations >= PROTOCOL_V1_CONFIRMATION_DEPTH`

Task 7 freezes the default confirmation rule at:

- `PROTOCOL_V1_CONFIRMATION_DEPTH = 2`

This is a deterministic depth rule, not a wall-clock rule.

### Finalized

Task 3.5 replaces this document's historical confirmation-depth finality rule. A canonical block is finalized only by persisted known-validator quorum evidence as defined in the Task 3.5 update above. `PROTOCOL_V1_FINALITY_DEPTH` is retained as legacy confirmation-policy metadata and is not an alternative meaning of `finalized`.

For genesis at height `0`, the same formula applies:

- `confirmations = canonical_tip_height - 0`
- genesis is confirmed once the canonical tip reaches height `2`
- genesis is finalized once the canonical tip reaches height `6`

## 3. Legal state transitions

The lifecycle concepts progress in this order:

```text
submitted -> voting
voting -> rejected
voting -> certified
certified -> mint-eligible
mint-eligible -> block-created
block-created -> block-accepted
block-accepted -> canonical
canonical -> confirmed
confirmed -> finalized
```

Important frozen rules:

- `submitted -> block-created` is forbidden
- `rejected -> certified` is forbidden
- `rejected -> block-created` is forbidden
- `certified -> voting` is forbidden
- `finalized -> voting` is forbidden
- `finalized -> rejected` is forbidden under normal protocol flow

`approved` and `queued` remain operational persisted statuses:

- `approved` means the submission passed evaluation and has not yet been placed in the mint queue
- `queued` means the approved certified submission is currently in the mint queue
- both can still be `certified=true`
- `mint-eligible` is derived from certificate and content readiness, not only from queue presence

## 4. One submission equals one Protocol v1 block

Task 7 freezes the invariant that one certified accepted submission may create at most one Protocol v1 block on the selected chain.

Durable evidence comes from the chain itself:

- Protocol v1 blocks persist `submission_id`
- Protocol v1 blocks persist `certificate_id`

Minting and block validation both reject duplicates:

- a second Protocol v1 block for the same `submission_id`
- a second Protocol v1 block for the same `certificate_id`
- a second creator reward for the same `submission_id`
- repeated voter reward IDs already settled in prior chain state

This survives restart because the selected chain is persisted and reloaded before duplicate checks run again.

## 5. Certificate and vote locking

Certificate issuance is idempotent:

- reissuing the same final certified submission returns the existing certificate
- it does not append a second certificate record

Vote mutation after certification is rejected:

- `Blockchain.is_submission_voting_locked(...)` locks on any final lifecycle status or certificate presence
- `Blockchain.cast_submission_vote(...)` rejects later votes with the frozen vote-lock rule

## 6. Block creation versus acceptance

Task 7 narrows the local mint flow to this order:

1. construct a candidate block with `Blockchain.build_block_candidate(...)`
2. validate it with `Blockchain.validate_candidate_block_for_local_acceptance(...)`
3. append it only after validation succeeds
4. settle native transactions, recompute reward pool state, and persist

An invalid candidate now fails before chain append, reward mutation, or settlement mutation.

## 7. Canonicality, confirmation, and reorg behavior

The node currently stores only the selected chain, not a durable side-branch block set.

That means:

- local accepted Protocol v1 blocks are appended directly to the selected chain
- canonicality is derived from the selected chain
- a competing valid branch is evaluated during chain comparison or sync, not persisted as a long-lived alternate branch

If canonical chain selection changes:

- canonical/confirmed/finalized status is recalculated from the new selected chain
- reward records are derived from the new selected chain
- native transactions not present on the new chain are downgraded from `settled` back to `validated_pending`
- a submission whose Protocol v1 mint block disappears from the selected chain is reconciled away from `minted`
- if that submission still has a valid certificate, it returns to `approved` unless it is already back in the mint queue, in which case it returns to `queued`

This is why finality is documented as operational depth policy, not irreversible consensus finality.

## 8. Legacy direct block creation

The legacy direct block route still exists:

- API: `POST /add_block`
- blockchain path: `Blockchain.add_block(...)` without certificate metadata

Task 7 freezes these constraints:

- the route is a development-only compatibility path, not the public Protocol v1 mint path
- it returns explicit markers that it is a legacy direct block path
- it does not create a Protocol v1 accepted-media block unless certificate-backed Protocol v1 metadata is provided through the certified mint flow

Protocol v1 public minting remains:

- `POST /mint/{submission_id}`
- `POST /mint-queue/{submission_id}/mint`

## 9. API semantics

Submission responses now expose deterministic lifecycle fields derived from chain state:

- `submission_status`
- `certificate_status`
- `mint_status`
- `block_status`
- `confirmations`
- `confirmed`
- `finalized`
- `protocol_v1_lifecycle`

Block responses now expose:

- `accepted`
- `canonical`
- `confirmations`
- `confirmed`
- `finalized`
- `confirmation_depth`
- `finality_depth`
- `finality_model`
- `finality_scope`

## 10. Limits that remain outside Task 7

Genesis identity and reset policy are frozen separately in [docs/protocol-v1-genesis-reset.md](/C:/Users/mattk/ZoidbergChain/docs/protocol-v1-genesis-reset.md).

Task 7 does not change:

- block hashing
- certificate hashing/signing
- vote signing
- native transfer signing
- peer authentication
- fork-choice policy
- validator-election design

Finality remains an honest operational rule over the current architecture, not a new BFT protocol.
