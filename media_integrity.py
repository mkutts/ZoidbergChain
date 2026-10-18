"""Independent Model A byte-integrity verification for immutable media blocks.

The blockchain-embedded byte sequence is authoritative.  This module never
loads submission state, a content-object cache, or an upload path.
"""

from __future__ import annotations

from typing import Any, Callable, Iterable

from admission_certificate import validate_admission_certificate
from block import ADMISSION_BLOCK_VERSION, PROTOCOL_V1_BLOCK_VERSION, Block
from content import TEXT_MIME_TYPE, canonicalize_text_content, resolve_declared_payload_hash


MEDIA_INTEGRITY_CONTRACT_VERSION = 1
MEDIA_INTEGRITY_CONTRACT_ID = "zoidberg-public-testnet-v1/model-a-byte-integrity/1"
MEDIA_INTEGRITY_HASH_ALGORITHM = "sha256"
CURRENT_MEDIA_BLOCK_VERSIONS = frozenset({PROTOCOL_V1_BLOCK_VERSION, ADMISSION_BLOCK_VERSION})


class MediaIntegrityError(ValueError):
    """A current media block failed the byte-integrity contract."""


def _field(block: Block | dict[str, Any], name: str, default: Any = None) -> Any:
    return block.get(name, default) if isinstance(block, dict) else getattr(block, name, default)


def _block_record(block: Block | dict[str, Any]) -> dict[str, Any]:
    if isinstance(block, Block):
        return block.to_dict(include_media_bytes=True)
    if not isinstance(block, dict):
        raise MediaIntegrityError("Media block must be a Block or dictionary.")
    return block


def reconstruct_media_bytes(block: Block | dict[str, Any]) -> bytes:
    """Return only the exact bytes embedded in a current media block."""
    version = _field(block, "block_version")
    if version not in CURRENT_MEDIA_BLOCK_VERSIONS:
        raise MediaIntegrityError("Block does not use a supported current media block version.")
    encoded = _field(block, "media_bytes")
    if encoded is None:
        raise MediaIntegrityError("Current media block does not embed media_bytes.")
    try:
        return Block._coerce_media_bytes(encoded)
    except (TypeError, ValueError) as exc:
        raise MediaIntegrityError("Current media block contains malformed media_bytes encoding.") from exc


def _certificate_snapshot_resolver(certificate: dict[str, Any]) -> Callable[[str, int, str], str | None]:
    """Resolve only the immutable reviewer snapshot frozen into the certificate.

    Full chain admission validates these references against chain state.  This
    resolver is intentionally limited to independently rechecking the media,
    certificate digest, signatures, and frozen snapshot's internal consistency.
    """
    statuses: dict[tuple[str, int, str], str] = {}
    for vote in certificate.get("votes", []) if isinstance(certificate, dict) else []:
        key = (
            str(vote.get("voter_wallet_address") or vote.get("voter") or "").lower(),
            vote.get("reviewer_status_effective_height"),
            str(vote.get("reviewer_status_reference_block_hash") or "").lower(),
        )
        status = vote.get("reviewer_status")
        if key in statuses and statuses[key] != status:
            raise MediaIntegrityError("Admission certificate contains conflicting reviewer snapshots.")
        statuses[key] = status

    def resolve(wallet: str, height: int, block_hash: str) -> str | None:
        return statuses.get((str(wallet).lower(), height, str(block_hash).lower()))

    return resolve


def verify_media_block(
    block: Block | dict[str, Any],
    *,
    reviewer_status_resolver: Callable[[str, int, str], str | None] | None = None,
    expected_block_hash: str | None = None,
    expected_block_height: int | None = None,
) -> dict[str, Any]:
    """Verify exact embedded bytes and every media binding available in a block.

    Version-2 admission blocks additionally verify their embedded admission
    certificate, technical evidence, attestation, vote signatures, and frozen
    reviewer snapshot.  Version-1 blocks retain their historical external
    originality-certificate semantics while receiving the same exact-byte and
    block-hash checks.
    """
    record = _block_record(block)
    version = record.get("block_version")
    if version not in CURRENT_MEDIA_BLOCK_VERSIONS:
        raise MediaIntegrityError("Unsupported or missing current media block version.")

    raw = reconstruct_media_bytes(record)
    media_hash = record.get("media_hash")
    content_hash = record.get("content_hash")
    mime_type = record.get("mime_type")
    if not isinstance(mime_type, str) or not mime_type.strip():
        raise MediaIntegrityError("Current media block is missing mime_type.")
    try:
        resolved = resolve_declared_payload_hash(raw, mime_type)
    except (UnicodeDecodeError, ValueError) as exc:
        raise MediaIntegrityError("Embedded media bytes do not satisfy their declared media type.") from exc
    if resolved["stored_bytes"] != raw:
        raise MediaIntegrityError("Embedded text media is not the canonical accepted byte sequence.")
    actual_hash = resolved["content_hash"]
    if media_hash != actual_hash:
        raise MediaIntegrityError("media_hash does not match the exact embedded media bytes.")
    if content_hash != actual_hash:
        raise MediaIntegrityError("content_hash does not match the exact embedded media bytes.")
    if mime_type == TEXT_MIME_TYPE:
        try:
            decoded = raw.decode("utf-8")
            if canonicalize_text_content(decoded).encode("utf-8") != raw:
                raise MediaIntegrityError("Embedded text media is not canonical UTF-8 text.")
        except UnicodeDecodeError as exc:
            raise MediaIntegrityError("Embedded text media is not valid UTF-8.") from exc

    stored_hash = record.get("hash")
    try:
        calculated_hash = Block.calculate_hash_v1_from_dict(record)
    except (TypeError, ValueError) as exc:
        raise MediaIntegrityError("Block canonical structure is invalid.") from exc
    if stored_hash != calculated_hash:
        raise MediaIntegrityError("Block hash does not commit to the supplied block and media bytes.")
    if expected_block_hash is not None and stored_hash != expected_block_hash:
        raise MediaIntegrityError("Block hash does not match the requested finalized identity.")
    if expected_block_height is not None and record.get("index") != expected_block_height:
        raise MediaIntegrityError("Block height does not match the requested finalized identity.")

    admission_binding = "legacy_external_certificate"
    technical_evidence_binding = "legacy_external_certificate"
    if version == ADMISSION_BLOCK_VERSION:
        certificate = record.get("admission_certificate")
        if not isinstance(certificate, dict):
            raise MediaIntegrityError("Admission media block is missing its frozen certificate.")
        resolver = reviewer_status_resolver or _certificate_snapshot_resolver(certificate)
        try:
            validate_admission_certificate(
                certificate,
                media_bytes=raw,
                reviewer_status_resolver=resolver,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise MediaIntegrityError("Admission certificate does not bind these exact media bytes.") from exc
        certificate_id = certificate.get("certificate_digest")
        expected = {
            "submission_id": certificate.get("submission_id"),
            "certificate_id": certificate_id,
            "content_hash": certificate.get("content_hash"),
        }
        for field_name, value in expected.items():
            if record.get(field_name) != value:
                raise MediaIntegrityError(f"Block {field_name} does not match the admission certificate.")
        evidence = certificate.get("technical_evidence", {})
        if evidence.get("raw_media_sha256") != actual_hash or evidence.get("raw_media_byte_length") != len(raw):
            raise MediaIntegrityError("Technical-validation evidence does not identify these exact bytes.")
        admission_binding = "verified"
        technical_evidence_binding = "verified"

    return {
        "verified": True,
        "integrity_status": "verified",
        "integrity_contract_id": MEDIA_INTEGRITY_CONTRACT_ID,
        "integrity_contract_version": MEDIA_INTEGRITY_CONTRACT_VERSION,
        "hash_algorithm": MEDIA_INTEGRITY_HASH_ALGORITHM,
        "hash_input": "exact embedded accepted media_bytes",
        "block_version": version,
        "block_height": record.get("index"),
        "block_hash": stored_hash,
        "submission_id": record.get("submission_id"),
        "media_hash": media_hash,
        "content_hash": content_hash,
        "media_hash_equals_content_hash": media_hash == content_hash,
        "media_length": len(raw),
        "mime_type": mime_type,
        "media_bytes_embedded": True,
        "block_hash_binding": "verified",
        "admission_certificate_binding": admission_binding,
        "technical_evidence_binding": technical_evidence_binding,
    }


def validate_current_media_chain_records(chain: Iterable[Block | dict[str, Any]]) -> int:
    """Fail closed on corrupt current media records without touching legacy blocks."""
    verified = 0
    for block in chain:
        if _field(block, "index") == 0:
            continue
        if _field(block, "block_version") in CURRENT_MEDIA_BLOCK_VERSIONS:
            verify_media_block(block)
            verified += 1
    return verified
