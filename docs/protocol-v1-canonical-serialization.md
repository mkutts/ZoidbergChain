# Protocol v1 Canonical Serialization Foundation

## Scope

This document defines the new shared Protocol v1 identity and canonical-serialization foundation introduced in Task 2.

This foundation is not yet wired into legacy block hashes, certificate IDs, vote signatures, native transaction signatures/IDs, peer signatures, or genesis hashing.

## Protocol identity

- Protocol name: `zoidbergchain`
- Protocol version: `1`
- Version tag: `v1`

## Network identity

- Canonical Public Testnet v1 network ID: `zoidberg-public-testnet-v1`
- Current runtime network name remains `zoidberg-testnet`
- The new network ID is distinct from:
  - peer node ID
  - environment name
  - hostname
  - storage directory
  - validator identity

Task 2 adds an explicit mapping layer so later signatures and hashes can bind to a stable network identifier without changing the current runtime behavior yet.

## Domain/object identifiers

Task 2 defines explicit domain identifiers for:

- `zoidbergchain/block/v1`
- `zoidbergchain/originality-certificate/v1`
- `zoidbergchain/submission/v1`
- `zoidbergchain/vote/v1`
- `zoidbergchain/native-transfer/v1`
- `zoidbergchain/peer-message/v1`
- `zoidbergchain/genesis/v1`

## Canonical encoding

The canonical external representation is JSON encoded as UTF-8 bytes.

Rules:

- dictionaries must use string keys only
- dictionary keys are sorted lexicographically
- lists preserve input order
- no insignificant whitespace is emitted
- separators are fixed to `(",", ":")`
- `ensure_ascii=False`
- `allow_nan=False`
- exact Unicode code points are preserved
- no Unicode normalization is performed

This means the exact input string content is consensus-significant.

## Primitive rules

- strings are serialized as JSON strings and UTF-8 encoded
- integers are allowed
- booleans are allowed and are handled separately from integers
- `null` is allowed
- floats are rejected
- `Decimal` values are rejected unless a caller converts them explicitly before serialization

## Byte representation

Bytes are supported through an explicit tagged JSON object:

```json
{
  "$type": "bytes",
  "$encoding": "hex",
  "$value": "00ff"
}
```

Rules:

- lowercase hexadecimal only
- reversible
- no text decoding
- no line wrapping
- no MIME dependence

This makes deterministic binary inclusion possible for later MODEL A block-format work without deciding that final block schema yet.

## Unicode behavior

- UTF-8 is always used
- empty strings are preserved
- whitespace is preserved
- newline characters are preserved exactly as provided
- no NFC/NFD normalization is applied

## Timestamp policy

The generic canonical serializer rejects `datetime`, `date`, and `time` objects.

Callers must supply an explicit scalar timestamp representation before serialization.

## Wallet-address normalization policy

The generic canonical serializer does not rewrite wallet addresses.

Task 2 keeps address normalization as an explicit, separate helper concern so later migrations can opt into that behavior intentionally.

## Hash algorithm

The canonical hash helper uses SHA-256 and returns lowercase hexadecimal output.

## Domain envelope

Task 2 adds a future-facing domain envelope of the form:

```json
{
  "domain": "zoidbergchain/vote/v1",
  "network_id": "zoidberg-public-testnet-v1",
  "object_type": "vote",
  "payload": {
    "submission_id": "abc123"
  },
  "protocol": "zoidbergchain",
  "protocol_version": 1
}
```

This gives later tasks a deterministic way to bind:

- protocol identity
- protocol version
- network identity
- object type/domain
- payload

## Unsupported values

The canonical serializer rejects unsupported or unsafe values rather than falling back to `str(...)`.

Rejected by default:

- `float`
- `NaN`
- `Infinity`
- `-Infinity`
- `Decimal`
- `set`
- `tuple`
- arbitrary class instances
- non-string dictionary keys
- `datetime` / `date` / `time`

## Compatibility statement

Task 2 does not migrate existing runtime consensus objects.

Specifically, this foundation is not yet used for:

- legacy block hashes
- certificate IDs
- vote signing payloads
- submission identifiers
- peer signatures
- genesis hashing

Tasks 4 and 5 now use this foundation for:

- Protocol v1 vote signing payloads
- Protocol v1 certificate IDs
- Protocol v1 native transfer signing payloads
- Protocol v1 native transfer transaction IDs
