# Protocol v1 Originality Certificates and Votes

## 1. Vote object version

Protocol v1 votes are identified explicitly with:

- `vote_version = 1`

Legacy signed votes are versionless and remain legacy objects. A vote is never treated as Protocol v1 only because it happens to contain similar fields.

## 2. Certificate object version

Protocol v1 originality certificates are identified explicitly with:

- `certificate_version = 1`

Legacy certificates are versionless and remain legacy objects.

## 3. Vote domain

Protocol v1 vote signing uses the Task 2 vote domain:

- `zoidbergchain/vote/v1`

The signed envelope is distinct from:

- native transfers
- wallet login challenges
- submission challenges
- originality certificates
- peer HMAC messages

## 4. Network binding

Every Protocol v1 vote is signed against one explicit canonical `network_id`.

For Public Testnet v1 the canonical value is:

- `zoidberg-public-testnet-v1`

The runtime compatibility alias `NETWORK_NAME="zoidberg-testnet"` is resolved at the configuration boundary. Cryptographic verification uses the canonical network ID, not the legacy display name.

## 5. Protocol version binding

Protocol v1 vote and certificate envelopes bind:

- `protocol = "zoidbergchain"`
- `protocol_version = 1`

A hypothetical Protocol v2 vote or certificate cannot produce the same canonical envelope hash.

## 6. Vote canonical fields

### ID-critical signed vote payload

The inner Protocol v1 vote payload contains exactly:

- `vote_version`
- `submission_id`
- `content_hash`
- `voter_wallet_address`
- `vote_type`
- `nonce`
- `issued_at`
- `expires_at`

### Envelope fields

The signed envelope also binds:

- `domain`
- `network_id`
- `object_type = "vote"`
- `protocol`
- `protocol_version`
- `payload`

## 7. Vote signing format

The backend returns the exact MetaMask `personal_sign` message as canonical JSON text of the Task 2 domain envelope:

`canonical_domain_bytes(vote_payload, object_type="vote", network_id=network_id).decode("utf-8")`

Protocol v1 vote verification reconstructs that exact canonical message and requires byte-for-byte equality after newline normalization.

## 8. MetaMask signing and recovery

Protocol v1 preserves the existing MetaMask / Ethereum signed-message model:

- the client signs the canonical vote envelope with `personal_sign`
- the server recovers the Ethereum-style `0x` address from the signed message
- the recovered address must match the expected voter wallet

Recovery alone is not sufficient. The recovered wallet must match the declared voter and the reconstructed Protocol v1 payload.

## 9. Vote-choice normalization

The consensus vote values remain:

- `original`
- `not_original`
- `unsure`

Normalization rules:

- values are case-sensitive
- unknown values are rejected
- display labels are not consensus values

## 10. Replay protections

Protocol v1 vote replay resistance comes from explicit object binding plus the existing duplicate-vote rules.

Each signed vote is bound to:

- vote domain
- protocol version
- canonical network ID
- submission ID
- content hash
- voter wallet
- vote choice
- challenge nonce
- issued/expires timestamps

That means a valid vote signature cannot be replayed:

- on another network
- on another submission
- for another vote choice
- for another voter wallet
- as a native transfer
- as another object domain

Existing duplicate-vote behavior is unchanged:

- one wallet may cast only one vote for a submission
- finalized or certified submissions do not accept more votes

## 11. Vote persistence

Protocol v1 signed votes persist enough data to reconstruct the signed payload exactly:

- `vote_version`
- `protocol_version`
- `network_id`
- `submission_id`
- `content_hash`
- `voter`
- `voter_wallet_address`
- `vote_type`
- `vote_message`
- `vote_signature`
- `signed_message_hash`
- `vote_nonce`
- `vote_issued_at`
- `vote_expires_at`
- `signed_at`
- `identity_source`

Legacy signed votes remain distinguishable because they do not carry the explicit Protocol v1 version tuple and they keep the legacy human-readable message format.

## 12. Certificate canonical schema

Protocol v1 certificate identity uses a smaller deterministic payload than the persisted certificate record.

### Certificate-ID critical fields

- `certificate_version`
- `submission_id`
- `content_hash`
- `creator_wallet`
- `vote_hash`
- `vote_total`
- `decisive_vote_total`
- `original_votes`
- `not_original_votes`
- `unsure_votes`
- `minimum_votes_required`
- `approval_threshold`
- `approval_percentage`
- `originality_score`

### Persisted but not certificate-ID critical

- `protocol_version`
- `network_id`
- `approved_at`
- `network_name`
- `issuing_node_id`
- `content_id`

`protocol_version` and `network_id` are still cryptographically bound, but they are bound by the outer Task 2 domain envelope rather than duplicated inside the certificate identity payload.

### Derived

- `certificate_id`

### Legacy-only identity fields

- versionless legacy certificates use `network_name` and `issuing_node_id` inside the legacy ID payload

## 13. Certificate ID algorithm

Protocol v1 certificate IDs are:

`SHA-256(canonical_domain_bytes(certificate_identity_payload, object_type="originality-certificate", network_id=network_id))`

The identity payload is first normalized with the Task 2 canonical serializer.

## 14. Vote-set hash algorithm

Protocol v1 `vote_hash` represents the final eligible vote set for the certified submission.

The vote-set payload contains:

- `vote_set_version`
- `submission_id`
- `content_hash`
- ordered `votes`

Each ordered vote contributes:

- `voter`
- `vote_type`

The hash is:

`SHA-256(canonical_domain_bytes(vote_set_payload, object_type="vote", network_id=network_id))`

## 15. Vote ordering rules

Protocol v1 vote-set hashing:

- normalizes each voter identity
- rejects duplicate voters
- sorts the final set by `(voter, vote_type)`
- does not depend on database row order
- does not depend on peer arrival order
- does not sort by timestamp

Current duplicate-vote rules already prevent multiple final votes from the same wallet on one submission, so duplicate voters are treated as invalid when building a Protocol v1 vote-set hash.

## 16. Numeric representation

No raw floats enter the Protocol v1 certificate hash payload.

Consensus-critical non-integer certificate values are normalized to plain decimal strings:

- `approval_threshold`
- `approval_percentage`
- `originality_score`

Normalization rules:

- no exponent notation
- no trailing zeroes
- `0` instead of `-0`
- finite numeric values only

## 17. Timestamp treatment

Vote challenge timestamps are signed and persisted:

- `issued_at`
- `expires_at`

Certificate issuance timestamps are persisted but are not part of the Protocol v1 certificate ID payload:

- `approved_at`

This keeps the certificate ID deterministic across honest nodes with the same eligible vote set and submission state. `issuing_node_id`, `network_name`, and `content_id` are also persisted metadata and are not part of the Protocol v1 certificate identity hash.

## 18. Certificate issuance

New certificates created through the normal `Blockchain.create_originality_certificate(...)` flow are Protocol v1 certificates by default.

Before issuance:

- the submission is promoted onto the canonical accepted-media content hash used by Protocol v1 blocks
- the final vote set is hashed deterministically
- the certificate is validated against the submission

For the same final eligible vote set and canonical submission content, honest nodes derive the same Protocol v1 certificate ID.

## 19. Certificate and block linkage

Task 4 does not change the Protocol v1 block field layout, but it freezes how the referenced certificate is interpreted.

Current rules:

- blocks reference `certificate_id`
- blocks also carry certificate-derived metadata such as `submission_id`, `content_hash`, `creator_wallet`, `vote_hash`, `approval_percentage`, `decisive_vote_total`, `minimum_votes_required`, `approved_at`, and `originality_score`
- block validation resolves the referenced certificate record and validates it through explicit legacy-vs-v1 dispatch

Compatibility rule:

- a Protocol v1 block may reference either an explicit legacy certificate record or an explicit Protocol v1 certificate record
- legacy certificate IDs are not silently reinterpreted as Protocol v1 IDs
- new certificates created after Task 4 use Protocol v1 certificate semantics by default

## 20. Legacy compatibility

### Legacy votes

- legacy human-readable vote messages remain valid only through explicit legacy verification paths
- new Protocol v1 votes use only the canonical Protocol v1 vote envelope
- a vote explicitly marked Protocol v1 never falls back to legacy verification
- a canonical Protocol v1 vote envelope without the explicit version marker is rejected rather than accepted as legacy

### Legacy certificates

- legacy certificates remain versionless
- stored legacy certificate IDs are not recalculated under Protocol v1 rules
- existing dev data remains loadable
- Protocol v1 block validation can still follow explicit legacy certificate records during the transition

Public Testnet launch will likely require a clean recertification/reset policy for legacy dev data, but that policy is not implemented here.

## 21. Peer sync behavior

Peer sync preserves explicit object versions:

- Protocol v1 votes retain `vote_version`, `protocol_version`, and `network_id`
- Protocol v1 certificates retain `certificate_version`, `protocol_version`, `network_id`, and `approval_threshold`
- legacy peer votes and certificates remain legacy objects
- Task 6 peer transport authenticates these routes with explicit `message_type = "vote"` and `message_type = "certificate"`

Additional receive-time checks:

- a Protocol v1 peer vote must carry the explicit Protocol v1 signature metadata
- the inner vote `network_id` must match the local canonical network ID
- the signed message must match the reconstructed Protocol v1 vote envelope exactly
- a related local submission must match the certificate creator and content hash
- when the related submission and vote set already exist locally, the incoming certificate vote totals and `vote_hash` must match the local finalized vote set
- peer authentication does not bypass vote or certificate validation

## 22. Known limitations

Task 4 intentionally does not yet migrate:

- native transfer signing domains
- native transaction ID domains
- genesis semantics
- lifecycle/finality semantics
- final reset/recertification policy for legacy chain data

Task 6 freezes peer-message transport in [docs/protocol-v1-peer-messages.md](/C:/Users/mattk/ZoidbergChain/docs/protocol-v1-peer-messages.md).

Operational note:

- a node that already has a submission locally now expects matching local vote data before accepting a peer certificate for that submission
