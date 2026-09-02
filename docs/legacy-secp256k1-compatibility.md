# Legacy SECP256k1 Compatibility

## Scope and safety

Task 4E replaces the legacy `ecdsa` implementation with `cryptography` while
preserving the historical formats and validation behavior recorded here. It
does not alter a protocol, stored data, block hashes, or acceptance policy.

The companion fixture is deliberately generated public test material. Its
private scalar is labelled **TEST ONLY**, **PUBLIC TEST FIXTURE**, and **NEVER
USE FOR FUNDS OR DEPLOYMENT**. It is not copied from runtime state, a server
wallet, user wallet, production/testnet identity, or repository history.

## Legacy surface

`wallet.py` creates and loads legacy server wallets with
`cryptography.ec.SECP256K1`. `transaction.py` signs and verifies legacy
`Transaction` objects. A received
legacy peer block is normalized through `Block.from_dict()` and
`peer_sync._validate_block_transactions()` calls `Transaction.is_valid()`
before chain acceptance. These are the compatibility uses covered here.

This is separate from MetaMask authentication, votes, and submissions, which
use `eth-account` `personal_sign` recovery; native ZOID transfer signatures;
Protocol v1 domain-separated payloads; and peer HMAC / Protocol v1 peer-message
signing. None uses this legacy `ecdsa` signature representation.

## Exact formats and semantics

- Curve: named curve `SECP256k1`.
- Generation: `Wallet.generate_key_pair()` calls
  `ec.generate_private_key(ec.SECP256K1())`, serializes its 32-byte scalar, and
  derives its public point as compressed SEC.
- Private key: valid 32-byte big-endian scalar, stored as lowercase hex in a
  `Wallet`.
- Public key: 33-byte compressed SEC point (`02` or `03` plus 32-byte X), stored
  as lowercase hex.
- Signing input: `f"{sender}{recipient}{amount}{tip}".encode("utf-8")` for a
  `Transaction`; `Wallet.sign_data()` signs the UTF-8 bytes of its supplied
  string. `payload_size_kb` and `created_at` are serialized but not signed.
- Hashing: historical `ecdsa` defaults were SHA-1. The replacement explicitly
  uses `ec.ECDSA(hashes.SHA1())` over original message bytes, not an
  already-calculated digest.
- Signature: default `sigencode_string`, exactly 64 raw bytes `r || s`, each
  32 bytes, represented as standard base64 text. It is neither DER nor
  recoverable.

Before migration, a clean Python 3.13 environment installed the committed
`ecdsa==0.19.2` and `cryptography==50.0.0` pins. Task 4D's 13 compatibility
tests passed there. `ecdsa` is no longer a supported installation dependency.

## Signing and verification

`SigningKey.sign(..., entropy=None)` is randomized. Fresh signatures are not a
byte-stable API contract. The fixed fixture signature was made solely by passing
test-controlled entropy to the library, so it can test historical verification
without imposing determinism on production signing.

Current verification accepts both a low-S signature and the valid high-S
counterpart where `s' = curve_order - s`. This is required for backward
verification compatibility. A future signer may emit low-S signatures only if
the verifier continues accepting both forms until an explicitly versioned
retirement decision. The legacy `Wallet.verify_signature` helper is separately
broken for compressed keys because it strips the SEC prefix before loading; it
returns false even for the valid fixture. Transaction and peer validation use
the working `Transaction.is_valid()` path instead.

Malformed base64, malformed raw signature lengths, altered signatures, altered
messages, and malformed public keys fail safely through boolean validation in
the current transaction/wallet interfaces.

## Serialization, identifiers, and blocks

Legacy `Transaction.to_dict()` persists `sender`, `recipient`, `amount`, `tip`,
`signature`, `payload_size_kb`, and `created_at` in that order. It defines no
`tx_id` and has no standalone legacy transaction identifier calculation. The
Protocol v1 native-transfer `tx_id` is a separate SHA-256 canonical identity and
is not affected by this legacy signature work.

Legacy block hashing concatenates each transaction's sender, recipient, amount,
tip, payload size, and raw base64 signature text before SHA-256 hashing the
legacy block assembly. Therefore signature bytes do affect legacy block hashes.
Replacing a historical high-S encoding with its low-S equivalent changes the
block hash despite equal cryptographic validity. Protocol v1 consensus payloads
also include the legacy transaction signature field when legacy transactions
are present; existing Protocol v1 golden vectors and genesis hashes remain
outside and unchanged by this fixture.

Peer reception requires an active same-network peer, chain extension, block-hash
validity, `Transaction.is_valid()`, and the existing balance policy. The fixture
tests acceptance with balance policy isolated so the legacy signature branch is
directly covered, then rehashes a tampered block to prove the peer path rejects
the invalid signature rather than merely rejecting a stale hash.

## Cross-implementation result

The installed `cryptography` package can derive the fixture's identical
compressed SECP256k1 public key. It verifies the fixture after converting raw
`r || s` to DER using `encode_dss_signature`, with either original bytes and
`ec.ECDSA(hashes.SHA1())`, or the SHA-1 digest and
`ec.ECDSA(utils.Prehashed(hashes.SHA1()))`. Using the digest with non-
`Prehashed` ECDSA would hash twice and is incompatible. `cryptography` signing
with `ec.ECDSA(hashes.SHA1())`, DER-to-raw conversion, and base64 encoding
produces a signature accepted by the current legacy verifier.

Task 4E uses this conversion in production. New signatures remain randomized;
the implementation does not normalize low-S values, while verification accepts
both historical low-S and high-S values. Existing signature text is only read,
never rewritten or normalized.

## Migration constraints and stopping conditions

A future production migration must preserve fixed scalar loading, compressed
SEC derivation/loading, original-message SHA-1 semantics, raw 64-byte `r || s`
base64 storage, historical high-S verification, legacy transaction fields, and
all legacy block/peer validation outcomes. It must not alter current
MetaMask/native/Protocol v1 systems or rewrite historical signature text.

The legacy `Wallet.verify_signature` compressed-key helper remains intentionally
broken and returns false for the fixed compressed-key fixture, matching the
pre-migration behavior. Repairing it, replacing SHA-1, changing malformed-input
behavior, or retiring historical high-S verification requires a separately
approved versioned compatibility change. No stored-data migration, signature
rewrite, block rewrite, or Protocol v1 fixture rewrite is part of Task 4E.
