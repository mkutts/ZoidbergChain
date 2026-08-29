# Protocol v1 Peer Messages

Authoritative note: [docs/protocol-v1.md](/C:/Users/mattk/ZoidbergChain/docs/protocol-v1.md) is the primary Public Testnet v1 protocol specification. If this document conflicts with it or with [docs/protocol-v1-freeze-report.json](/C:/Users/mattk/ZoidbergChain/docs/protocol-v1-freeze-report.json), the authoritative spec and freeze report win.

Task 6 freezes the Protocol v1 peer-message envelope, shared-secret authentication semantics, replay protection, and explicit legacy-vs-v1 dispatch for Public Testnet v1.

Genesis behavior and reset policy are frozen separately in [docs/protocol-v1-genesis-reset.md](/C:/Users/mattk/ZoidbergChain/docs/protocol-v1-genesis-reset.md). Lifecycle and operational finality semantics are frozen separately in [docs/protocol-v1-lifecycle-finality.md](/C:/Users/mattk/ZoidbergChain/docs/protocol-v1-lifecycle-finality.md).

## 1. Peer protocol version

Protocol v1 peer messages use two explicit version fields:

- `peer_message_version = 1`
- `protocol_version = 1`

The transport headers carry both values:

- `X-ZOID-Peer-Message-Version`
- `X-ZOID-Protocol-Version`

Both values are authenticated and both must equal `1`.

## 2. Peer-message domain

Protocol v1 peer-message authentication uses the Task 2 peer-message domain:

- `zoidbergchain/peer-message/v1`

This domain is distinct from:

- blocks
- votes
- originality certificates
- native transfers
- wallet login/submission messages

## 3. Network binding

Every explicit v1 peer message binds one canonical `network_id`.

For Public Testnet v1 the canonical value is:

- `zoidberg-public-testnet-v1`

The runtime alias `NETWORK_NAME="zoidberg-testnet"` is resolved before signing or verification. Explicit v1 messages are verified against the canonical `network_id`, not against the display alias.

## 4. Sender/node identity

Protocol v1 binds the sending node identity with:

- `sender_node_id`
- `X-ZOID-Node-Id`

Rules:

- the sender node ID must pass the existing node ID validator
- the authenticated sender must match the claimed body sender on POST routes
- peer-only GET routes require the authenticated sender to already be a registered active peer on the local network
- a peer cannot modify `origin_node_id` or `node_id` without failing authentication or the post-auth claim checks

Task 6 does not introduce wallet-based peer identities or a new validator identity scheme.

## 5. Message types

Protocol v1 uses a finite, explicit message-type set derived from the actual peer routes:

- `peer-registration`
- `submission`
- `vote`
- `certificate`
- `block`
- `native-transaction`
- `transaction-fetch`
- `mempool-summary`
- `content-metadata`
- `content-download`
- `chain-summary`
- `chain-blocks`

Unknown peer message types are rejected.

## 6. Canonical envelope

The canonical authenticated peer envelope is:

```json
{
  "domain": "zoidbergchain/peer-message/v1",
  "message_type": "...",
  "network_id": "zoidberg-public-testnet-v1",
  "nonce": "...",
  "object_type": "peer-message",
  "payload": {...},
  "peer_message_version": 1,
  "protocol": "zoidbergchain",
  "protocol_version": 1,
  "sender_node_id": "...",
  "timestamp": 1724760000
}
```

Field classification:

- Authenticated and signed:
  - `domain`
  - `message_type`
  - `network_id`
  - `nonce`
  - `object_type`
  - `payload`
  - `peer_message_version`
  - `protocol`
  - `protocol_version`
  - `sender_node_id`
  - `timestamp`
- Message-ID critical:
  - every authenticated envelope field above
- Routing/transport metadata only:
  - HTTP headers carrying the same explicit values
  - the final `X-ZOID-Signature`
- Persisted replay state:
  - `sender_node_id`
  - `nonce`
  - `message_id`
  - `timestamp`
  - `expires_at`
- Legacy-only:
  - `X-ZOID-Peer-Secret`

HTTP method and path are not HMAC input directly. They are used only to:

- bind the request to one explicit peer `message_type`
- extract protocol-relevant path/query payload fields such as `content_hash`, `tx_id`, `from_height`, and `include_media_bytes`

## 7. Canonical payload

Protocol v1 peer payloads use Task 2 canonical JSON normalization.

Rules:

- POST routes sign the JSON body object
- GET routes sign only the protocol-relevant route/query payload
- floats are normalized to deterministic decimal strings before canonical serialization
- canonical bytes objects are rehydrated safely so embedded `media_bytes` can be authenticated without weakening the Task 2 bytes-tag reservation
- unsupported value types, malformed route identifiers, and invalid query values are rejected

Current GET payload shapes are:

- `content-metadata`: `{ "content_hash": "<hash>" }`
- `content-download`: `{ "content_hash": "<hash>" }`
- `transaction-fetch`: `{ "tx_id": "<tx_id>" }`
- `mempool-summary`: `{}`
- `chain-summary`: `{}`
- `chain-blocks`: `{ "from_height": <int>, "include_media_bytes": <bool> }`

## 8. Message ID

Protocol v1 `message_id` is:

- `SHA-256(canonical peer envelope bytes without the signature field)`

In the code this is produced by:

- `calculate_protocol_v1_peer_message_id(...)`

The message ID binds:

- protocol identity
- protocol version
- peer-message domain
- canonical network ID
- message type
- sender node ID
- timestamp
- nonce
- canonical payload

The signature itself is not part of message identity.

## 9. Authentication algorithm

Protocol v1 peer authentication uses:

- `HMAC-SHA256`

The HMAC input is:

- the canonical peer envelope bytes from `protocol_v1_peer_envelope_bytes(...)`

The result is transmitted in:

- `X-ZOID-Signature`

Comparison uses `hmac.compare_digest(...)`.

## 10. Shared-secret/HMAC behavior

The signing key source is:

- `PEER_SHARED_SECRET`

Rules:

- signed peer messages require the shared secret to be configured
- non-default placeholder secrets are rejected by the configuration checks in non-development signed modes
- the secret is never returned in API errors
- the same shared secret is currently used for every peer on a node

Current operational limitation:

- Task 6 does not add a per-peer secret store or a coordinated key-rotation protocol

## 11. Signature behavior

There is no separate asymmetric peer-signature path today.

Task 6 preserves the existing peer shared-secret/HMAC model and does not introduce wallet-signed peer transport messages.

## 12. Nonce rules

Protocol v1 peer nonces are:

- authenticated
- sender-scoped
- distinct from native transaction nonces

Validation rules:

- regex: `^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$`
- empty nonce rejected
- malformed nonce rejected

Outbound helpers currently generate a random default nonce with:

- `secrets.token_hex(16)`

## 13. Replay prevention

Replay protection uses both:

- `message_id`
- `(sender_node_id, nonce)`

If replay protection is enabled, the receiver rejects:

- an already accepted `message_id`
- a duplicate nonce from the same sender inside the active retention window

Replay protection is not timestamp-only. Timestamp freshness and replay state are both required.

## 14. Replay-state persistence

Accepted peer replay state is persisted in:

- `peer_message_replay_state.json`

Location:

- the peer store data directory for the active node

Format:

- `replay_state_version`
- `retention_window_seconds`
- sorted `entries`

Each entry persists:

- `sender_node_id`
- `nonce`
- `message_id`
- `timestamp`
- `expires_at`

Behavior:

- atomic JSON writes with backup
- expired entries are pruned on load/list/update
- corrupted replay state fails closed with a `503` on protected endpoints instead of silently disabling replay checks

This is dedicated security/transport state, not blockchain consensus state.

## 15. Timestamp and freshness rules

Protocol v1 peer timestamps use:

- integer Unix seconds
- UTC semantics

The timestamp is authenticated and must be inside the configured freshness window.

Current configuration:

- `PEER_SIGNATURE_WINDOW_SECONDS`
- default value: `300`

## 16. Allowed clock skew

The current implementation uses the same `300` second window in both directions.

That means:

- slightly old messages inside the window are accepted
- slightly future messages inside the window are accepted
- older than `now - 300` seconds is rejected
- newer than `now + 300` seconds is rejected

Task 6 keeps the window symmetric and timezone-independent.

## 17. Legacy compatibility

Legacy and v1 dispatch is explicit.

When `ENABLE_SIGNED_PEER_MESSAGES` is enabled:

- Protocol v1 peer headers are required on peer endpoints
- explicit v1 requests do not fall back to legacy shared-secret auth
- missing v1 headers fail with `401`

When signed peer messages are disabled:

- the legacy `X-ZOID-Peer-Secret` path may still be used where peer auth is required

Important compatibility rule:

- a single node does not silently accept both schemes for the same request path

For local development, legacy-only nodes and v1-only nodes can exist as separate configurations, but there is no automatic negotiation or downgrade path between them.

Public Testnet v1 should run with signed peer messages enabled.

## 18. Peer registration

Peer registration is an explicit Protocol v1 peer message type:

- `peer-registration`

Rules preserved by Task 6:

- registration still uses the existing peer store model
- the claimed body `node_id` must match the authenticated sender
- the claimed body `network_name` must resolve to the authenticated `network_id`
- unregistered or inactive peers are still blocked from protected peer-only read routes
- existing local-node/self-registration protections remain intact

Task 6 does not redesign validator enrollment.

## 19. Block sync

Protocol v1 block sync uses:

- `message_type = "block"`

The signed peer payload carries the block object, including embedded `media_bytes` when present.

Receiving block rules remain:

1. authenticate the peer envelope
2. reject replay
3. normalize the block payload
4. validate block version/network/hash/linkage
5. validate embedded media and content hashes
6. validate certificate and transaction semantics
7. only then append or treat as duplicate/sync-needed

Authenticated blocks are not blindly trusted.

## 20. Content sync

Protocol v1 content sync uses:

- `message_type = "content-metadata"`
- `message_type = "content-download"`

Task 6 authenticates the peer requests, but content bytes still undergo local verification:

- size limits
- MIME validation
- payload hash verification
- safe storage rules

Auxiliary content sync does not outrank authoritative block `media_bytes`.

## 21. Vote sync

Protocol v1 vote sync uses:

- `message_type = "vote"`

After peer authentication, the receiver still validates:

- vote version
- protocol version
- canonical network binding
- canonical signed message reconstruction
- wallet signature recovery
- voter eligibility
- duplicate/conflict rules

Authenticated vote transport does not bypass vote signature validation.

## 22. Certificate sync

Protocol v1 certificate sync uses:

- `message_type = "certificate"`

After peer authentication, the receiver still validates:

- certificate version/network
- certificate ID and vote-hash consistency
- vote totals and originality score consistency
- related submission/content linkage
- local vote-set consistency when the submission already exists locally

Authenticated certificate transport does not make the certificate trusted by itself.

## 23. Native transaction sync

Protocol v1 native transaction sync uses:

- `message_type = "native-transaction"`
- `message_type = "transaction-fetch"`
- `message_type = "mempool-summary"`

After peer authentication, the receiver still validates:

- transaction version
- protocol version
- canonical network binding
- tx ID
- transfer signature
- sender nonce rules
- available balance and current admission policy

Legacy transactions remain distinguishable and are not admitted into the live Protocol v1 mempool.

## 24. Chain sync

Protocol v1 chain sync uses:

- `message_type = "chain-summary"`
- `message_type = "chain-blocks"`

Authenticated request payloads bind:

- summary intent
- `from_height`
- `include_media_bytes`

Authenticated chain sync does not bypass normal chain evaluation. Received blocks still validate individually, and chain selection still checks:

- peer `network_id`
- peer `protocol_version`
- genesis hash
- best-chain comparison
- block-by-block validity

## 25. Inner-object revalidation

> Peer authentication does not make a protocol object trusted. Every received block, vote, certificate, native transaction, and content object must still pass its own Protocol v1 validation rules.

Task 6 keeps that rule explicit in code and tests:

- signed block transport still fails tampered embedded media
- signed vote transport still fails inner vote-message tampering
- signed certificate transport still fails inconsistent vote totals
- signed native transaction transport still fails invalid transfer signatures
- signed content sync still fails content hash mismatches

## 26. Error handling

Current explicit peer-auth error behavior:

- `401`: missing Protocol v1 peer headers
- `400`: unsupported peer message version
- `400`: unsupported peer protocol version
- `400`: wrong network
- `400`: invalid message type
- `403`: invalid sender node ID
- `400`: invalid nonce
- `401`: invalid or expired timestamp window
- `403`: invalid message ID
- `403`: invalid signature
- `409`: replayed nonce or message
- `503`: replay state unavailable/corrupt

Inner-object validation errors remain object-specific and are returned by the existing block, vote, certificate, transfer, and content validation paths.

## 27. Known limitations

Task 6 intentionally does not freeze or redesign:

- validator decentralization
- a per-peer secret-rotation protocol

Genesis and reset policy are now frozen separately in [docs/protocol-v1-genesis-reset.md](/C:/Users/mattk/ZoidbergChain/docs/protocol-v1-genesis-reset.md).

Residual transport limitations:

- replay state is bounded to the configured retention window rather than retained forever
- replay persistence is stored in a dedicated JSON security file, not in the blockchain document or SQLite chain tables
- restoring an old node snapshot without its current replay-state file can reopen the replay window for messages that are still inside the active time window
