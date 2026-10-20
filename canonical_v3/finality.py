"""Separate finality commitments. No finality material enters a block preimage."""
from .evidence import fields_equal, fixed
from .primitives import (
    bounded, canonical, closed, envelope, h64, require, uint, verify_signature, wallet,
)

ATTESTATION_FIELDS = '''attestation_version validator_address block_height block_hash network_id
domain signature_scheme signature message'''.split()
PROOF_FIELDS = '''block_height block_hash network_id domain attestation_version validator_set
required_quorum attestations'''.split()


def finality_bytes(payload, ctx):
    closed(payload, 'attestation_version validator_address block_height block_hash')
    fixed(payload['attestation_version'], 2)
    wallet(payload['validator_address'])
    uint(payload['block_height'])
    h64(payload['block_hash'])
    result = canonical(envelope(payload, 'finality-attestation', ctx))
    require(len(result) <= 1024, 'finality_message_size')
    return result


def validate_attestation(value, ctx):
    closed(value, ATTESTATION_FIELDS)
    bounded(value, 1536)
    fields_equal(value, dict(attestation_version=2, network_id=ctx.network_id,
                            domain='zoidbergchain/finality-attestation/v2', signature_scheme='personal_sign'))
    payload = {k: value[k] for k in ('attestation_version', 'validator_address', 'block_height', 'block_hash')}
    message = finality_bytes(payload, ctx)
    fixed(value['message'], message.decode('utf-8'))
    verify_signature(message, value['signature'], value['validator_address'])


def validate_proof(value, ctx, *, trusted_validators, equivocators, block_height, block_hash):
    """Caller supplies authenticated ancestry set/target and known equivocation state."""
    closed(value, PROOF_FIELDS)
    bounded(value, 262144)
    uint(block_height)
    h64(block_hash)
    require(type(trusted_validators) is tuple and 1 <= len(trusted_validators) <= 128, 'trusted_validators')
    for address in trusted_validators:
        wallet(address)
    require(list(trusted_validators) == sorted(set(trusted_validators)), 'trusted_validator_order')
    require(type(equivocators) is frozenset, 'equivocation_context')
    for address in equivocators:
        wallet(address)
    quorum = (2 * len(trusted_validators) + 2) // 3
    fields_equal(value, dict(block_height=block_height, block_hash=block_hash, network_id=ctx.network_id,
                            domain='zoidbergchain/finality-attestation/v2', attestation_version=2,
                            validator_set=list(trusted_validators), required_quorum=quorum))
    attestations = value['attestations']
    require(type(attestations) is list and quorum <= len(attestations) <= len(trusted_validators), 'finality_count')
    for attestation in attestations:
        validate_attestation(attestation, ctx)
        fields_equal(attestation, dict(block_height=block_height, block_hash=block_hash))
        require(attestation['validator_address'] in trusted_validators and
                attestation['validator_address'] not in equivocators, 'finality_membership')
    order = [a['validator_address'] for a in attestations]
    require(order == sorted(set(order)), 'finality_order')
