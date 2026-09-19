# Milestone 6 Task 6.4 — signed submitter rights/permanence attestation

Task 6.4 requires every new Public Testnet v1 media submission to carry a
durable MetaMask/EIP-191 submitter assertion before it can enter the existing
originality/review pipeline. It does not prove ownership, determine rights,
grant a license beyond the statement, activate the overall media-admission
policy, or implement Task 6.5 admissibility voting or any later Milestone 6 work.

## Identity and statement

- Attestation schema version: `1`
- Statement ID: `zoidberg-public-testnet-v1/submitter-rights-permanence/1`
- Statement version: `1`
- Protocol/object type: `zoidbergchain` / `submitter-attestation`
- Signing domain: `zoidbergchain/submitter-attestation/v1`
- Network ID: `zoidberg-public-testnet-v1`
- Signature scheme: MetaMask-compatible EIP-191 `personal_sign`

The engineering/testnet statement is:

> I assert that I have the right or authorization to submit this exact content
> under the identified ZoidbergChain Public Testnet media-admission policy. I
> understand that, if accepted and finalized, the accepted media bytes become
> permanently replicated in immutable ZoidbergChain history and cannot be
> removed through ordinary moderation. This testnet attestation is my signed
> assertion; it is not proof of ownership, a legal determination, a waiver, or
> a license beyond this explicit assertion.

**POLICY TODO — OWNER DECISION REQUIRED:** production/legal wording remains
unfrozen. Changing the statement requires a new statement identity/version; it
must not silently reinterpret existing signatures.

## Canonical signed payload

Protocol v1 canonical JSON recursively sorts object keys, uses compact UTF-8
JSON with no insignificant whitespace, and wraps the payload in the domain
envelope. The signed payload fields are:

- `attestation_version`, `statement_id`, `statement_version`, `statement`;
- normalized lowercase `wallet_address`;
- server-generated 128-bit hexadecimal `submission_id`;
- exact `raw_media_sha256`;
- `policy_id`, integer `policy_version`, and `policy_digest`;
- `technical_evidence_version` and `technical_evidence_digest`;
- random challenge `nonce`, UTC `issued_at`, and UTC `expires_at`;
- canonical `network_id`.

Caption, filename, URL, MIME supplied by the client, UI-local IDs, and other
mutable presentation metadata are not signed identity. The durable record also
stores the signature, signer, signature scheme, domain/protocol identity,
canonical payload and message, their hashes/digest, nonce, and verification
time. A fixed golden message-hash vector protects Python canonicalization, and
the frontend reconstructs and compares the canonical message before requesting
the wallet signature.

## Media, policy, evidence, and network binding

For images, `raw_media_sha256` is Task 6.3's SHA-256 of the exact accepted image
bytes. For text, it is the SHA-256 of the frozen canonical UTF-8 bytes after
CRLF/CR-to-LF normalization and outer-whitespace trimming. A one-byte accepted
media change invalidates Task 6.3 evidence and this attestation.

The payload binds media-admission policy
`zoidberg-public-testnet-v1/media-admission/1`, version `1`, and its canonical
digest. It also binds technical-evidence version `1` and its digest. Unknown or
different policy, validator evidence, byte hash, or network identity fails
closed. MetaMask provides a `0x` identity signature; it does not turn ZOID into
an ERC-20 or import Ethereum chain semantics.

## Ordering, recovery, and replay protection

The enforced order is:

1. Task 6.3 validates and stores accepted canonical bytes and evidence.
2. The server generates a unique submission ID, nonce, timestamps, and canonical
   attestation payload.
3. The frontend requires explicit acknowledgment, reconstructs the canonical
   envelope, and requests `personal_sign`.
4. The server finds the live challenge, rejects expiry/reuse/mismatched content,
   recovers the signer, and compares the normalized address to the verified
   wallet session.
5. Under the storage-scoped submission lock, the node reloads durable state,
   rejects any reused signer+nonce, signature, or canonical message hash,
   independently verifies all bindings against stored bytes/evidence, persists
   the submission, and only then runs existing originality/review eligibility.

The in-memory challenge is single-use and lock-protected against concurrent
requests. Durable uniqueness checks cover restart and multiple facades using the
same storage. A signature cannot authorize another submission, media object,
policy, evidence result, network, signature domain, or wallet.

Stable failure codes include `missing_attestation`,
`unsupported_attestation_version`, `malformed_attestation`, `wrong_network`,
`policy_mismatch`, `media_hash_mismatch`, `evidence_digest_mismatch`,
`nonce_invalid`, `nonce_replayed`, `signer_mismatch`, `invalid_signature`,
`submission_mismatch`, and `canonical_message_mismatch`.

## Persistence, activation, and compatibility

The existing submission JSON document stores the versioned attestation, so both
JSON and SQLite backends persist it without a relational schema migration.
Storage projections enforce unique submission IDs and attestation replay claims.
Reload never upgrades a missing, incomplete, or tampered record to valid.

Submission records explicitly distinguish:

- `public_testnet_v1_required`: must verify before originality/review;
- `legacy_pre_activation`: readable historical data with no claimed attestation;
- `development_only_unsigned`: visibly unsigned and eligible only while the
  runtime is in development mode.

Signed `/submit_content` requests and peer-received Public Testnet submissions
must pass the attestation gate. `/content/upload` and `/content/text` remain
staging endpoints: they perform Task 6.3 validation but do not create review
submissions. The unsigned branch of `/submit_content` remains development-only
and is explicitly marked. Historical finalized records remain readable and are
not retroactively labeled as attested.

## Known limitations and remaining owner decisions

- The overall Task 6.2 media-admission policy and production activation height
  remain owner decisions; this task implements the required fail-closed record
  and gate without claiming overall policy activation.
- Final production/legal statement wording, jurisdiction, rights definitions,
  user presentation, and legal review remain **POLICY TODO — OWNER DECISION
  REQUIRED**.
- Challenge state is intentionally process-local and short-lived. A restart
  invalidates unconsumed challenges; consumed records remain durably protected.
- This assertion is evidence of what the recovered wallet signed, not evidence
  that the signer actually owns or controls all relevant rights.
- Task 6.5 dual originality/admissibility voting, quarantine, reporting,
  disputes, later integrity work, review redesign, and release readiness remain
  out of scope.
