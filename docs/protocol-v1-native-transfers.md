# Protocol v1 Native ZOID Transfers

Authoritative note: [docs/protocol-v1.md](/C:/Users/mattk/ZoidbergChain/docs/protocol-v1.md) is the primary Public Testnet v1 protocol specification. If this document conflicts with it or with [docs/protocol-v1-freeze-report.json](/C:/Users/mattk/ZoidbergChain/docs/protocol-v1-freeze-report.json), the authoritative spec and freeze report win.

Native ZOID transfers are ZoidbergChain Layer 1 transactions. They are not Ethereum transactions and ZOID is not an ERC-20 token.

Task 5 freezes the Protocol v1 native-transfer representation, signing semantics, and transaction ID algorithm. Task 6 freezes peer-message transport separately. Genesis remains outside Task 5.

## 1. Transaction version

Protocol v1 native transfers are identified explicitly with:

- `transaction_version = 1`

Legacy transfers are versionless and remain explicit legacy objects.

## 2. Protocol version

Protocol v1 native-transfer envelopes bind:

- `protocol = "zoidbergchain"`
- `protocol_version = 1`

## 3. Native-transfer domain

Protocol v1 transfer signing uses the Task 2 native-transfer domain:

- `zoidbergchain/native-transfer/v1`

This domain is distinct from:

- votes
- wallet login challenges
- submission challenges
- peer HMAC messages

## 4. Network binding

Every Protocol v1 native transfer is signed against one explicit canonical `network_id`.

For Public Testnet v1 the canonical value is:

- `zoidberg-public-testnet-v1`

The runtime compatibility alias `NETWORK_NAME="zoidberg-testnet"` is resolved before signing or verification. Cryptographic verification uses the canonical `network_id`, not the display alias.

## 5. Transfer canonical schema

### Signed inner payload

The canonical inner transfer payload contains exactly:

- `transaction_version`
- `from_address`
- `to_address`
- `amount`
- `fee`
- `nonce`
- `timestamp`
- `memo`

### Signed envelope fields

The outer signed envelope also binds:

- `domain`
- `network_id`
- `object_type = "native-transfer"`
- `protocol`
- `protocol_version`
- `payload`

### Persisted but not signed separately

The persisted transaction record also stores:

- `network`
- `signature`
- `signature_scheme`
- `signed_message`
- `signed_message_hash`
- `status`
- `created_at`
- `updated_at`
- local settlement metadata such as `admitted_at`, `included_block_hash`, `included_block_height`, `settled_at`, and `rejection_reason`

### Derived/cache-only

- `tx_id`
- balance summaries
- transfer-history direction labels

### Legacy-only

- the versionless human-readable transfer message format
- versionless tx ID calculation that includes signature-bearing fields

## 6. Signed fields

Protocol v1 signatures bind:

- protocol identity
- protocol version
- object domain
- canonical network ID
- sender wallet
- recipient wallet
- amount
- fee
- nonce
- timestamp
- memo after the existing trim-to-canonical behavior

## 7. Transaction-ID fields

Protocol v1 transaction IDs are identity hashes over the same canonical transfer intent:

- `transaction_version`
- `from_address`
- `to_address`
- `amount`
- `fee`
- `nonce`
- `timestamp`
- `memo`
- plus the envelope-bound `network_id`, `object_type`, `protocol`, and `protocol_version`

The tx ID does not include signature bytes or local status metadata.

## 8. MetaMask `personal_sign` behavior

The backend returns the exact MetaMask `personal_sign` message as canonical JSON text of the Task 2 domain envelope:

`canonical_domain_bytes(transfer_payload, object_type="native-transfer", network_id=network_id).decode("utf-8")`

The frontend signs that exact canonical string. The backend reconstructs the same canonical string during verification and requires exact equality.

## 9. Sender recovery

Protocol v1 preserves the existing MetaMask / Ethereum signed-message recovery model:

- the signer is recovered from the signed message and signature
- the recovered wallet is normalized to lowercase `0x...`
- the recovered wallet must match the declared `from_address`

Recovery alone is not sufficient. The message must also match the reconstructed Protocol v1 transfer payload for the local network.

## 10. Recipient validation

Current recipient rules are preserved:

- recipient must be an Ethereum-style `0x` address with 40 hex characters
- address casing is normalized to lowercase
- malformed addresses are rejected
- `from_address == to_address` is rejected
- the zero address is not specially blocked today if it passes the existing address-format validation

## 11. Amount representation

Protocol v1 uses strict normalized decimal strings for amounts.

Rules:

- no raw Python floats in the signed payload or tx-ID payload
- no scientific notation
- no `NaN` or `Infinity`
- no negative values
- amount must be greater than zero
- up to 6 decimal places
- trailing zeroes are removed
- `1`, `1.0`, and `1.00` normalize to the same canonical value

## 12. Fee representation

Protocol v1 uses the same strict normalized decimal-string rules for `fee`.

Current fee semantics are unchanged:

- fee is signed
- fee is tx-ID-critical
- fee may be `0`
- negative fees are rejected
- nonzero fees are still rejected by the current policy during submission/admission and block validation

## 13. Nonce semantics

Task 5 makes no nonce-model change.

Current rules remain:

- initial nonce is `1`
- nonce is per sender wallet
- expected next nonce is strict sequential
- pending accepted transactions reserve nonces
- settled transactions consume nonces durably from chain state
- a rejected submission does not advance nonce state
- wallet A nonce state does not affect wallet B
- peer-synced transactions are revalidated against the same sender-nonce rules

## 14. Replay protection

Task 5 preserves the durable replay model:

- the signed nonce is part of the Protocol v1 transfer payload
- duplicate tx IDs are rejected where applicable
- nonce reservation prevents conflicting pending transactions
- chain-derived nonce state prevents replay after settlement
- network binding prevents replay onto another network

The durable anti-replay mechanism is ledger nonce state, not only in-memory challenge state.

## 15. Timestamp semantics

`timestamp` remains part of the signed payload and tx-ID payload.

Current rules are frozen as:

- ISO 8601 string input is required
- a timezone offset is required
- values are normalized to UTC `datetime.isoformat()` text
- `Z` input normalizes to `+00:00`
- no Python `datetime` objects appear in canonical signed or tx-ID payloads

## 16. Memo semantics

`memo` remains signed and tx-ID-critical.

Current normalization behavior is preserved:

- `None` stays absent
- leading/trailing whitespace is trimmed
- blank-after-trim becomes `null`
- maximum length is 280 characters
- the resulting canonical string is significant byte-for-byte

No Unicode normalization beyond the existing trim/string coercion behavior is added.

## 17. Transaction ID algorithm

Protocol v1 transaction IDs are:

`SHA-256(canonical_domain_bytes(transfer_identity_payload, object_type="native-transfer", network_id=network_id))`

In the current implementation, the Protocol v1 `signed_message_hash` and Protocol v1 `tx_id` are identical because both hash the same canonical domain-separated transfer intent.

## 18. Signature malleability decision

Protocol v1 keeps tx IDs independent of signature encoding.

Why:

- the transaction identity is the signed transfer intent, not a particular signature byte encoding
- excluding signature bytes avoids tx ID drift if multiple valid encodings of the same authorization ever appear
- sender recovery is still enforced separately before admission, inclusion, or settlement

## 19. Persistence

Protocol v1 transfer state persists through:

- `transfer_intents`
- `native_transactions`
- JSON storage
- SQLite storage
- export/import snapshots

Persisted Protocol v1 records retain:

- `transaction_version`
- `protocol_version`
- `network_id`
- exact `signed_message`
- `signed_message_hash`
- signature bytes
- nonce/timestamp/memo and other transfer fields

## 20. Block inclusion

Task 3 Protocol v1 blocks now carry explicit Task 5 native-transfer version metadata when present:

- `transaction_version`
- `protocol_version`
- `network_id`

Rules:

- transaction order remains consensus-significant
- Protocol v1 blocks revalidate native transaction signature, tx ID, nonce, balance, and fee policy before settlement
- Protocol v1 blocks do not silently reinterpret legacy native transactions
- versionless legacy native transactions are not eligible for new Protocol v1 block inclusion

## 21. Settlement

Task 5 makes no settlement-model change.

Current behavior remains:

- validation happens before balance mutation
- invalid signature does not debit
- wrong nonce does not debit
- insufficient balance does not debit
- duplicate/replayed settlement does not debit twice
- successful block inclusion settles exactly once

## 22. Peer sync

Peer transaction sync now preserves the explicit native-transfer version tuple.

Rules:

- peer transaction objects transmit `transaction_version`, `protocol_version`, and `network_id` when present
- Task 6 peer transport authenticates transaction sync with explicit `message_type = "native-transaction"`
- received Protocol v1 transactions are revalidated locally before mempool admission
- wrong-network Protocol v1 transactions are rejected
- tampered sender/recipient/amount/fee/nonce/timestamp/memo fail revalidation
- versionless legacy peer transactions remain readable as data, but they are rejected for Protocol v1 mempool admission
- peer authentication does not bypass transfer signature or nonce validation

Peer-message transport details are documented in [docs/protocol-v1-peer-messages.md](/C:/Users/mattk/ZoidbergChain/docs/protocol-v1-peer-messages.md).

## 23. Legacy compatibility

Legacy compatibility is explicit:

- legacy transfers remain versionless
- legacy human-readable signatures still verify only through the explicit legacy path
- Protocol v1 transactions never fall back to legacy verification
- stored legacy tx IDs are not silently recomputed
- existing dev/test data remains loadable where practical
- legacy pending transfers are not admitted into the live Protocol v1 mempool or new Protocol v1 blocks

Public Testnet reset policy is now frozen separately in [docs/protocol-v1-genesis-reset.md](/C:/Users/mattk/ZoidbergChain/docs/protocol-v1-genesis-reset.md). Operationally, pending legacy native-transaction state should still be reviewed or purged before a node joins the canonical Public Testnet v1 chain.

## 24. Known limitations

Task 5 intentionally does not itself freeze or migrate launch-time legacy cleanup:

- pending legacy native-transaction state

Task 7 freezes lifecycle and operational finality semantics in [docs/protocol-v1-lifecycle-finality.md](/C:/Users/mattk/ZoidbergChain/docs/protocol-v1-lifecycle-finality.md).
