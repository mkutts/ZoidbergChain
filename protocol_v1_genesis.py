from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from protocol_v1 import (
    OBJECT_TYPE_GENESIS,
    PROTOCOL_VERSION,
    PUBLIC_TESTNET_V1_NETWORK_ID,
    canonical_domain_bytes,
    canonical_domain_hash,
    normalize_network_id,
)


PUBLIC_TESTNET_V1_GENESIS_VERSION = 1
PUBLIC_TESTNET_V1_GENESIS_TIMESTAMP = 1785542400
PUBLIC_TESTNET_V1_GENESIS_TIMESTAMP_ISO = "2026-08-01T00:00:00+00:00"
PUBLIC_TESTNET_V1_GENESIS_PREVIOUS_HASH = "0" * 64
PUBLIC_TESTNET_V1_GENESIS_MINER = "GENESIS"
PUBLIC_TESTNET_V1_GENESIS_TEXT = "ZoidbergChain Public Testnet v1 Genesis"
PUBLIC_TESTNET_V1_TOTAL_SUPPLY = 1_000_000_000
PUBLIC_TESTNET_V1_INITIAL_REWARD_POOL = 100_000_000

PUBLIC_TESTNET_V1_BOOTSTRAP_ALLOCATIONS = (
    {
        "role": "project_owner",
        "recipient": "034f355bdcb7cc0af728ef3cceb9615d90684bb5b2ca5f859ab0f0b704075871aa",
        "amount": 790_000_000,
    },
    {
        "role": "contributor_one",
        "recipient": "02466d7fcae563e5cb09a0d1870bb580344804617879a14949cf22285f1bae3f27",
        "amount": 100_000_000,
    },
    {
        "role": "contributor_two",
        "recipient": "023c72addb4fdf09af94f0c94d7fe92a386a7e70cf8a1d85916386bb2535c7b1b1",
        "amount": 10_000_000,
    },
)

_GENESIS_ALLOWED_FIELDS = frozenset(
    {
        "genesis_version",
        "protocol_version",
        "network_id",
        "index",
        "previous_hash",
        "timestamp",
        "transactions",
        "miner",
        "meme",
        "hash",
        "total_supply",
        "initial_reward_pool",
    }
)


class GenesisValidationError(ValueError):
    def __init__(self, code: str, message: str, *, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = str(code or "invalid_genesis").strip() or "invalid_genesis"
        self.details = dict(details or {})

    def to_detail(self) -> dict[str, Any]:
        detail = {"code": self.code, "message": str(self)}
        detail.update(self.details)
        return detail


def canonical_public_testnet_v1_genesis_transactions() -> list[dict[str, Any]]:
    return [
        {
            "sender": PUBLIC_TESTNET_V1_GENESIS_MINER,
            "recipient": allocation["recipient"],
            "amount": allocation["amount"],
            "tip": 0,
            "signature": None,
            "payload_size_kb": 0,
            "created_at": PUBLIC_TESTNET_V1_GENESIS_TIMESTAMP,
        }
        for allocation in PUBLIC_TESTNET_V1_BOOTSTRAP_ALLOCATIONS
    ]


def canonical_public_testnet_v1_genesis_payload() -> dict[str, Any]:
    return {
        "genesis_version": PUBLIC_TESTNET_V1_GENESIS_VERSION,
        "index": 0,
        "previous_hash": PUBLIC_TESTNET_V1_GENESIS_PREVIOUS_HASH,
        "timestamp": PUBLIC_TESTNET_V1_GENESIS_TIMESTAMP,
        "transactions": canonical_public_testnet_v1_genesis_transactions(),
        "miner": PUBLIC_TESTNET_V1_GENESIS_MINER,
        "meme_text": PUBLIC_TESTNET_V1_GENESIS_TEXT,
        "total_supply": PUBLIC_TESTNET_V1_TOTAL_SUPPLY,
        "initial_reward_pool": PUBLIC_TESTNET_V1_INITIAL_REWARD_POOL,
    }


def canonical_public_testnet_v1_genesis_bytes() -> bytes:
    return canonical_domain_bytes(
        canonical_public_testnet_v1_genesis_payload(),
        object_type=OBJECT_TYPE_GENESIS,
        network_id=PUBLIC_TESTNET_V1_NETWORK_ID,
    )


def _compute_public_testnet_v1_genesis_hash() -> str:
    return canonical_domain_hash(
        canonical_public_testnet_v1_genesis_payload(),
        object_type=OBJECT_TYPE_GENESIS,
        network_id=PUBLIC_TESTNET_V1_NETWORK_ID,
    )


PUBLIC_TESTNET_V1_CANONICAL_GENESIS_HASH = "585474a5164f0afb811b624ae342d537dbef5f68337b3e64bb0ebcf8ca0dc49c"


def canonical_public_testnet_v1_genesis_hash() -> str:
    computed = _compute_public_testnet_v1_genesis_hash()
    if computed != PUBLIC_TESTNET_V1_CANONICAL_GENESIS_HASH:
        raise RuntimeError(
            "Frozen Public Testnet v1 genesis hash constant does not match the canonical genesis payload."
        )
    return computed


def canonical_public_testnet_v1_genesis_record() -> dict[str, Any]:
    return {
        "genesis_version": PUBLIC_TESTNET_V1_GENESIS_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "network_id": PUBLIC_TESTNET_V1_NETWORK_ID,
        "index": 0,
        "previous_hash": PUBLIC_TESTNET_V1_GENESIS_PREVIOUS_HASH,
        "timestamp": PUBLIC_TESTNET_V1_GENESIS_TIMESTAMP,
        "transactions": canonical_public_testnet_v1_genesis_transactions(),
        "miner": PUBLIC_TESTNET_V1_GENESIS_MINER,
        "meme": {"text": PUBLIC_TESTNET_V1_GENESIS_TEXT},
        "hash": canonical_public_testnet_v1_genesis_hash(),
        "total_supply": PUBLIC_TESTNET_V1_TOTAL_SUPPLY,
        "initial_reward_pool": PUBLIC_TESTNET_V1_INITIAL_REWARD_POOL,
    }


def is_public_testnet_v1_genesis_record(record: Any) -> bool:
    return bool(
        isinstance(record, Mapping)
        and record.get("index") == 0
        and record.get("genesis_version") == PUBLIC_TESTNET_V1_GENESIS_VERSION
    )


def _require_non_negative_int(value: Any, *, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise GenesisValidationError(
            "genesis_mismatch",
            f"Genesis {field_name} must be a non-negative integer.",
            details={"field_name": field_name},
        )
    return value


def _normalize_transaction_payload(payload: Any, *, index: int) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise GenesisValidationError(
            "genesis_mismatch",
            "Genesis transactions must be objects.",
            details={"transaction_index": index},
        )

    allowed_fields = {"sender", "recipient", "amount", "tip", "signature", "payload_size_kb", "created_at"}
    extra_fields = sorted(set(payload.keys()) - allowed_fields)
    if extra_fields:
        raise GenesisValidationError(
            "genesis_mismatch",
            "Genesis transaction contains unexpected fields.",
            details={"transaction_index": index, "unexpected_fields": extra_fields},
        )

    sender = payload.get("sender")
    recipient = payload.get("recipient")
    signature = payload.get("signature")
    if sender != PUBLIC_TESTNET_V1_GENESIS_MINER:
        raise GenesisValidationError(
            "genesis_mismatch",
            "Genesis transaction sender must be GENESIS.",
            details={"transaction_index": index},
        )
    if not isinstance(recipient, str) or not recipient.strip():
        raise GenesisValidationError(
            "genesis_mismatch",
            "Genesis transaction recipient must be a non-empty string.",
            details={"transaction_index": index},
        )
    if signature is not None:
        raise GenesisValidationError(
            "genesis_mismatch",
            "Genesis transactions must not include signatures.",
            details={"transaction_index": index},
        )

    return {
        "sender": sender,
        "recipient": recipient.strip(),
        "amount": _require_non_negative_int(payload.get("amount"), field_name=f"transactions[{index}].amount"),
        "tip": _require_non_negative_int(payload.get("tip"), field_name=f"transactions[{index}].tip"),
        "signature": None,
        "payload_size_kb": _require_non_negative_int(
            payload.get("payload_size_kb"),
            field_name=f"transactions[{index}].payload_size_kb",
        ),
        "created_at": _require_non_negative_int(
            payload.get("created_at"),
            field_name=f"transactions[{index}].created_at",
        ),
    }


def canonical_public_testnet_v1_genesis_payload_from_record(record: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(record, Mapping):
        raise GenesisValidationError("missing_genesis", "Genesis record must be an object.")

    extra_fields = sorted(set(record.keys()) - _GENESIS_ALLOWED_FIELDS)
    if extra_fields:
        raise GenesisValidationError(
            "genesis_mismatch",
            "Genesis record contains unexpected fields.",
            details={"unexpected_fields": extra_fields},
        )

    if record.get("genesis_version") is None:
        raise GenesisValidationError(
            "legacy_chain_reset_required",
            "Existing chain uses a legacy runtime-generated genesis and must be reset before joining Public Testnet v1.",
        )

    protocol_version = record.get("protocol_version")
    if protocol_version != PROTOCOL_VERSION:
        raise GenesisValidationError(
            "genesis_mismatch",
            "Genesis protocol_version does not match Protocol v1.",
            details={"protocol_version": protocol_version, "expected_protocol_version": PROTOCOL_VERSION},
        )

    try:
        normalized_network_id = normalize_network_id(record.get("network_id"))
    except ValueError as exc:
        raise GenesisValidationError(
            "genesis_mismatch",
            "Genesis network_id is invalid.",
            details={"network_id": record.get("network_id")},
        ) from exc
    if normalized_network_id != PUBLIC_TESTNET_V1_NETWORK_ID:
        raise GenesisValidationError(
            "genesis_mismatch",
            "Genesis network_id does not match Public Testnet v1.",
            details={"network_id": normalized_network_id, "expected_network_id": PUBLIC_TESTNET_V1_NETWORK_ID},
        )

    if "block_version" in record and record.get("block_version") is not None:
        raise GenesisValidationError(
            "genesis_mismatch",
            "Canonical Public Testnet v1 genesis is not a normal accepted-media Protocol v1 block.",
        )

    meme = record.get("meme")
    if not isinstance(meme, Mapping) or set(meme.keys()) != {"text"}:
        raise GenesisValidationError(
            "genesis_mismatch",
            "Genesis meme field must contain exactly the frozen text marker.",
        )

    transactions = record.get("transactions")
    if not isinstance(transactions, list):
        raise GenesisValidationError("genesis_mismatch", "Genesis transactions must be a list.")

    return {
        "genesis_version": _require_non_negative_int(record.get("genesis_version"), field_name="genesis_version"),
        "index": _require_non_negative_int(record.get("index"), field_name="index"),
        "previous_hash": str(record.get("previous_hash") or "").strip(),
        "timestamp": _require_non_negative_int(record.get("timestamp"), field_name="timestamp"),
        "transactions": [
            _normalize_transaction_payload(transaction_payload, index=index)
            for index, transaction_payload in enumerate(transactions)
        ],
        "miner": str(record.get("miner") or "").strip(),
        "meme_text": str(meme.get("text") or "").strip(),
        "total_supply": _require_non_negative_int(record.get("total_supply"), field_name="total_supply"),
        "initial_reward_pool": _require_non_negative_int(
            record.get("initial_reward_pool"),
            field_name="initial_reward_pool",
        ),
    }


def validate_public_testnet_v1_genesis_record(record: Mapping[str, Any]) -> bool:
    payload = canonical_public_testnet_v1_genesis_payload_from_record(record)
    expected_payload = canonical_public_testnet_v1_genesis_payload()
    if payload != expected_payload:
        raise GenesisValidationError(
            "genesis_mismatch",
            "Genesis payload does not match the frozen Public Testnet v1 genesis definition.",
            details={
                "expected_genesis_hash": canonical_public_testnet_v1_genesis_hash(),
                "actual_genesis_hash": canonical_domain_hash(
                    payload,
                    object_type=OBJECT_TYPE_GENESIS,
                    network_id=PUBLIC_TESTNET_V1_NETWORK_ID,
                ),
            },
        )

    if str(record.get("hash") or "").strip() != canonical_public_testnet_v1_genesis_hash():
        raise GenesisValidationError(
            "genesis_mismatch",
            "Genesis hash does not match the frozen Public Testnet v1 genesis hash.",
            details={
                "expected_genesis_hash": canonical_public_testnet_v1_genesis_hash(),
                "actual_genesis_hash": str(record.get("hash") or "").strip() or None,
            },
        )
    return True


def inspect_public_testnet_v1_genesis_chain(chain: Any) -> dict[str, Any]:
    if not isinstance(chain, list):
        return {
            "canonical": False,
            "status": "invalid_chain_state",
            "genesis_hash": None,
            "error_code": "invalid_chain_state",
            "error_message": "Chain payload must be a list.",
            "details": None,
        }

    if not chain:
        return {
            "canonical": False,
            "status": "empty",
            "genesis_hash": None,
            "error_code": None,
            "error_message": None,
            "details": None,
        }

    first_block = chain[0]
    if not isinstance(first_block, Mapping):
        return {
            "canonical": False,
            "status": "invalid_chain_state",
            "genesis_hash": None,
            "error_code": "invalid_chain_state",
            "error_message": "Genesis record must be an object.",
            "details": None,
        }

    actual_genesis_hash = str(first_block.get("hash") or "").strip() or None
    try:
        validate_public_testnet_v1_genesis_record(first_block)
    except GenesisValidationError as exc:
        return {
            "canonical": False,
            "status": exc.code,
            "genesis_hash": actual_genesis_hash,
            "error_code": exc.code,
            "error_message": str(exc),
            "details": exc.to_detail(),
        }

    return {
        "canonical": True,
        "status": "canonical_public_testnet_v1",
        "genesis_hash": canonical_public_testnet_v1_genesis_hash(),
        "error_code": None,
        "error_message": None,
        "details": None,
    }


def require_public_testnet_v1_genesis_chain(
    chain: Any,
    *,
    label: str,
    allow_empty: bool = False,
) -> str | None:
    inspection = inspect_public_testnet_v1_genesis_chain(chain)
    if inspection["status"] == "empty":
        if allow_empty:
            return None
        raise GenesisValidationError(
            "missing_genesis",
            f"{label} does not contain a genesis block.",
        )
    if inspection["canonical"]:
        return inspection["genesis_hash"]

    details = dict(inspection.get("details") or {})
    details.setdefault("expected_genesis_hash", canonical_public_testnet_v1_genesis_hash())
    if inspection.get("genesis_hash"):
        details.setdefault("actual_genesis_hash", inspection["genesis_hash"])
    raise GenesisValidationError(
        inspection.get("error_code") or "genesis_mismatch",
        f"{label} does not contain the frozen Public Testnet v1 genesis. "
        f"{inspection.get('error_message') or 'Genesis validation failed.'}",
        details=details or None,
    )
