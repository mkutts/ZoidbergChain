"""Validator-quorum finality for the selected Public Testnet v1 chain."""

from dataclasses import dataclass
from typing import Callable, Iterable

from native_transfer import NATIVE_TRANSFER_SIGNATURE_SCHEME, normalize_wallet_address
from protocol_v1 import normalize_network_id
from protocol_v1_finality import PROTOCOL_V1_FINALITY_ATTESTATION_DOMAIN, PROTOCOL_V1_FINALITY_ATTESTATION_VERSION, build_protocol_v1_finality_attestation_message
from wallet_auth import recover_signed_wallet_address


class FinalityAttestationError(ValueError):
    pass


def normalize_validator_set(identities) -> tuple[str, ...]:
    if identities is None:
        return ()
    if isinstance(identities, (str, bytes)):
        raise FinalityAttestationError("Validator set must be an iterable of Ethereum addresses.")
    try:
        values = list(identities)
    except TypeError as exc:
        raise FinalityAttestationError("Validator set must be an iterable of Ethereum addresses.") from exc
    normalized = []
    for identity in values:
        address = normalize_wallet_address(identity)
        if address is None:
            raise FinalityAttestationError("Validator set contains an invalid Ethereum-style 0x address.")
        normalized.append(address)
    return tuple(sorted(set(normalized)))


def required_quorum(validator_count: int) -> int:
    if isinstance(validator_count, bool) or not isinstance(validator_count, int) or validator_count < 0:
        raise ValueError("validator_count must be a non-negative integer.")
    return (2 * validator_count + 2) // 3


@dataclass(frozen=True)
class FinalityPolicy:
    confirmation_depth: int
    finality_depth: int
    finality_model: str = "validator_quorum"
    finality_scope: str = "known_validator_set"


class FinalityService:
    _ATTESTATION_FIELDS = frozenset({"attestation_version", "validator_address", "block_height", "block_hash", "network_id", "domain", "signature_scheme", "signature", "message"})

    @staticmethod
    def policy(policy: FinalityPolicy, validator_set=()) -> dict[str, object]:
        validators = normalize_validator_set(validator_set)
        return {"confirmation_depth": int(policy.confirmation_depth), "finality_depth": int(policy.finality_depth), "finality_model": policy.finality_model, "finality_scope": policy.finality_scope, "validator_count": len(validators), "required_quorum": required_quorum(len(validators))}

    @staticmethod
    def block_field(block, field_name, default=None):
        return block.get(field_name, default) if isinstance(block, dict) else getattr(block, field_name, default)

    def find_protocol_block(self, chain: Iterable, *, field_name: str, value, is_protocol_block: Callable[[object], bool]):
        target = str(value or "").strip()
        return next((block for block in chain if target and is_protocol_block(block) and str(self.block_field(block, field_name) or "").strip() == target), None)

    @staticmethod
    def _height(value) -> int:
        if isinstance(value, bool):
            raise FinalityAttestationError("block_height must be a non-negative integer.")
        try:
            height = int(value)
        except (TypeError, ValueError) as exc:
            raise FinalityAttestationError("block_height must be a non-negative integer.") from exc
        if height < 0 or str(value).strip() != str(height):
            raise FinalityAttestationError("block_height must be a non-negative integer.")
        return height

    def validate_attestation(self, attestation, *, validator_set, expected_network_id) -> dict:
        if not isinstance(attestation, dict) or set(attestation) != self._ATTESTATION_FIELDS:
            raise FinalityAttestationError("Finality attestation has an invalid canonical shape.")
        validators = normalize_validator_set(validator_set)
        try:
            validator = normalize_wallet_address(attestation["validator_address"])
            height = self._height(attestation["block_height"])
            block_hash = str(attestation["block_hash"] or "").strip().lower()
            network_id = normalize_network_id(attestation["network_id"])
        except (KeyError, ValueError) as exc:
            raise FinalityAttestationError(str(exc)) from exc
        if validator is None:
            raise FinalityAttestationError("validator_address must be a valid Ethereum-style 0x address.")
        if validator not in validators:
            raise FinalityAttestationError("Attestation signer is not in the configured validator set.")
        if network_id != normalize_network_id(expected_network_id):
            raise FinalityAttestationError("Finality attestation network_id does not match this network.")
        if attestation["attestation_version"] != PROTOCOL_V1_FINALITY_ATTESTATION_VERSION or attestation["domain"] != PROTOCOL_V1_FINALITY_ATTESTATION_DOMAIN:
            raise FinalityAttestationError("Unsupported finality attestation domain or version.")
        if attestation["signature_scheme"] != NATIVE_TRANSFER_SIGNATURE_SCHEME or not isinstance(attestation["signature"], str) or not attestation["signature"].strip():
            raise FinalityAttestationError("Finality attestation must have a personal_sign signature.")
        try:
            expected_message = build_protocol_v1_finality_attestation_message(validator_address=validator, block_height=height, block_hash=block_hash, network_id=network_id)
        except ValueError as exc:
            raise FinalityAttestationError(str(exc)) from exc
        if attestation["message"] != expected_message:
            raise FinalityAttestationError("Finality attestation message is not canonical or does not match its fields.")
        try:
            recovered = recover_signed_wallet_address(expected_message, attestation["signature"].strip())
        except ValueError as exc:
            raise FinalityAttestationError("Finality attestation signature is invalid.") from exc
        if recovered != validator:
            raise FinalityAttestationError("Finality attestation signature does not match validator_address.")
        return {"attestation_version": PROTOCOL_V1_FINALITY_ATTESTATION_VERSION, "validator_address": validator, "block_height": height, "block_hash": block_hash, "network_id": network_id, "domain": PROTOCOL_V1_FINALITY_ATTESTATION_DOMAIN, "signature_scheme": NATIVE_TRANSFER_SIGNATURE_SCHEME, "signature": attestation["signature"].strip(), "message": expected_message}

    def votes_for_block(self, attestations, *, validator_set, expected_network_id, block_height, block_hash) -> tuple[list[dict], set[str]]:
        by_validator: dict[tuple[str, int], dict[str, dict]] = {}
        for candidate in attestations or []:
            try:
                checked = self.validate_attestation(candidate, validator_set=validator_set, expected_network_id=expected_network_id)
            except FinalityAttestationError:
                continue
            by_validator.setdefault((checked["validator_address"], checked["block_height"]), {})[checked["block_hash"]] = checked
        equivocations = {validator for (validator, height), hashes in by_validator.items() if height == block_height and len(hashes) > 1}
        votes = [hashes[block_hash] for (validator, height), hashes in by_validator.items() if height == block_height and validator not in equivocations and block_hash in hashes]
        return sorted(votes, key=lambda vote: vote["validator_address"]), equivocations

    @staticmethod
    def _finalized_match(finalized_blocks, height, block_hash):
        for record in finalized_blocks or []:
            if isinstance(record, dict) and record.get("block_height") == height:
                return record if record.get("block_hash") == block_hash else False
        return None

    def process_attestation(self, attestation, *, validator_set, expected_network_id, canonical_block, existing_attestations, finalized_blocks) -> dict:
        checked = self.validate_attestation(attestation, validator_set=validator_set, expected_network_id=expected_network_id)
        if not isinstance(canonical_block, dict):
            raise FinalityAttestationError("Finality target must be an existing canonical block.")
        expected_height, expected_hash = self._height(canonical_block.get("index")), str(canonical_block.get("hash") or "").strip().lower()
        if checked["block_height"] != expected_height or checked["block_hash"] != expected_hash:
            raise FinalityAttestationError("Finality attestation does not reference the exact canonical block.")
        locked = self._finalized_match(finalized_blocks, expected_height, expected_hash)
        if locked is False:
            raise FinalityAttestationError("A conflicting block is already finalized at this height.")
        if any(candidate == checked for candidate in existing_attestations or []):
            return {"attestation": checked, "status": "duplicate", "finalization": locked or None}
        updated = list(existing_attestations or []) + [checked]
        votes, equivocations = self.votes_for_block(updated, validator_set=validator_set, expected_network_id=expected_network_id, block_height=expected_height, block_hash=expected_hash)
        validators = normalize_validator_set(validator_set)
        quorum = required_quorum(len(validators))
        finalization = None
        if locked is None and validators and len(votes) >= quorum:
            finalization = {"block_height": expected_height, "block_hash": expected_hash, "network_id": normalize_network_id(expected_network_id), "domain": PROTOCOL_V1_FINALITY_ATTESTATION_DOMAIN, "attestation_version": PROTOCOL_V1_FINALITY_ATTESTATION_VERSION, "validator_set": list(validators), "required_quorum": quorum, "attestations": votes}
        return {"attestation": checked, "status": "equivocation" if checked["validator_address"] in equivocations else "accepted", "finalization": finalization, "vote_count": len(votes), "required_quorum": quorum, "equivocating_validators": sorted(equivocations)}

    def validate_finalization_evidence(self, record, *, expected_network_id) -> dict:
        required = {"block_height", "block_hash", "network_id", "domain", "attestation_version", "validator_set", "required_quorum", "attestations"}
        if not isinstance(record, dict) or set(record) != required:
            raise FinalityAttestationError("Finality evidence has an invalid canonical shape.")
        validators = normalize_validator_set(record["validator_set"])
        height = self._height(record["block_height"])
        block_hash = str(record["block_hash"] or "").strip().lower()
        if not validators or record["required_quorum"] != required_quorum(len(validators)):
            raise FinalityAttestationError("Finality evidence has an invalid validator-set quorum.")
        if record["network_id"] != normalize_network_id(expected_network_id) or record["domain"] != PROTOCOL_V1_FINALITY_ATTESTATION_DOMAIN or record["attestation_version"] != PROTOCOL_V1_FINALITY_ATTESTATION_VERSION:
            raise FinalityAttestationError("Finality evidence has the wrong Protocol v1 domain.")
        if not isinstance(record["attestations"], list):
            raise FinalityAttestationError("Finality evidence attestations must be a list.")
        votes, equivocations = self.votes_for_block(record["attestations"], validator_set=validators, expected_network_id=expected_network_id, block_height=height, block_hash=block_hash)
        if equivocations or len(votes) < record["required_quorum"]:
            raise FinalityAttestationError("Finality evidence does not prove validator quorum.")
        if votes != record["attestations"]:
            raise FinalityAttestationError("Finality evidence attestations are not deterministically ordered and unique.")
        return record

    def block_chain_state(self, block_or_hash, chain_dicts, policy: FinalityPolicy, *, finalized_blocks=(), validator_set=(), attestations=(), expected_network_id=None) -> dict[str, object]:
        policy_dict = self.policy(policy, validator_set)
        target_hash = str(block_or_hash or "").strip() if isinstance(block_or_hash, str) else str(self.block_field(block_or_hash, "hash") or "").strip()
        state = {"accepted": False, "block_created": False, "block_accepted": False, "canonical": False, "confirmations": None, "confirmed": False, "finalized": False, "valid_attestation_count": 0, "attesting_validators": [], "validator_set_size": policy_dict["validator_count"], "quorum_required": policy_dict["required_quorum"], "finalized_at": None, **policy_dict, "block_hash": target_hash or None, "block_height": None, "phase": "none", "lifecycle_state": "unknown", "finality_evidence": None}
        if not target_hash:
            return state
        target_block = next((block for block in chain_dicts if str(block.get("hash") or "").strip() == target_hash), None)
        if target_block is None:
            return state
        confirmations = int(chain_dicts[-1]["index"]) - int(target_block["index"])
        height = int(target_block["index"])
        evidence = self._finalized_match(finalized_blocks, height, target_hash)
        finalized = bool(evidence)
        effective_validators = normalize_validator_set(evidence["validator_set"]) if evidence else normalize_validator_set(validator_set)
        effective_quorum = int(evidence["required_quorum"]) if evidence else required_quorum(len(effective_validators))
        if evidence:
            counted = list(evidence.get("attestations", []))
        elif expected_network_id is not None:
            counted, _ = self.votes_for_block(attestations, validator_set=effective_validators, expected_network_id=expected_network_id, block_height=height, block_hash=target_hash)
        else:
            counted = []
        attesting_validators = [vote["validator_address"] for vote in counted]
        state.update({"accepted": True, "block_created": True, "block_accepted": True, "canonical": True, "confirmations": confirmations, "confirmed": confirmations >= policy.confirmation_depth, "finalized": finalized, "block_height": height, "phase": "finalized" if finalized else ("confirmed" if confirmations >= policy.confirmation_depth else "canonical"), "lifecycle_state": "finalized" if finalized else "accepted", "valid_attestation_count": len(counted), "attesting_validators": attesting_validators, "validator_set_size": len(effective_validators), "quorum_required": effective_quorum, "finalized_at": evidence.get("finalized_at") if evidence else None, "finality_evidence": {"block_height": height, "block_hash": target_hash, "valid_attestation_count": len(counted), "attesting_validators": attesting_validators, "validator_set_size": len(effective_validators), "quorum_required": effective_quorum, "attestation_domain": evidence.get("domain") if evidence else PROTOCOL_V1_FINALITY_ATTESTATION_DOMAIN, "attestation_version": evidence.get("attestation_version") if evidence else PROTOCOL_V1_FINALITY_ATTESTATION_VERSION, "finalized": finalized, "finalized_at": evidence.get("finalized_at") if evidence else None}})
        return state
