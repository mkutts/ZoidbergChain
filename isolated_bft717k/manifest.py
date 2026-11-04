"""The isolated 7.17I ten-field M, not the older N7/A3/Q3 proposal."""
from dataclasses import dataclass

from canonical_v3.primitives import closed, pattern, require, uint, V3Error
from isolated_bft717j.wire import J, parse, sha, identity
from .outcomes import AuthorityFailure, Outcome

FIELDS = ('domain membership_version protocol protocol_version network_id '
          'authority_profile validator_epoch byzantine_fault_budget required_quorum '
          'validator_public_keys')


def _validate(raw):
    m = parse(raw, 8192)
    closed(m, FIELDS)
    pattern(m['network_id'], r'[a-z0-9][a-z0-9-]{2,63}')
    for name, value in dict(membership_version=1, protocol_version=2,
                            validator_epoch=0, byzantine_fault_budget=1,
                            required_quorum=3).items():
        require(uint(m[name]) == value, 'manifest_' + name)
    require(m['domain'] == 'zoidbergchain/validator-set/v1' and
            m['protocol'] == 'zoidbergchain' and
            m['authority_profile'] == 'static-genesis-v1', 'manifest_profile')
    pubs = m['validator_public_keys']
    require(type(pubs) is list and len(pubs) == 4, 'manifest_count')
    ids = [identity(k) for k in pubs]  # strict SEC1/curve check before ordering
    require(len(set(pubs)) == 4, 'duplicate_public_key')
    require(len(set(ids)) == 4, 'duplicate_validator_identity')
    require(pubs == sorted(pubs), 'manifest_order')
    return m


@dataclass(frozen=True)
class Manifest:
    raw: bytes

    def __post_init__(self):
        try:
            _validate(self.raw)
        except V3Error as exc:
            raise AuthorityFailure(Outcome.INVALID_MANIFEST, exc.code) from exc
        except MemoryError as exc:
            raise AuthorityFailure(Outcome.RESOURCE_FAILURE, 'manifest_memory') from exc

    @property
    def commitment(self):
        # Domain is inside J(M); no prefix, genesis identity, salt or delimiter.
        return sha(self.raw)

    @property
    def value(self):
        return parse(self.raw, 8192)  # fresh copy; mutations cannot change authority

    @property
    def members(self):
        return tuple((identity(k), k) for k in self.value['validator_public_keys'])


def construct_manifest(network_id, public_keys):
    """Local authoring only: sort unique keys; received bytes are never repaired."""
    try:
        require(type(public_keys) in (list, tuple) and len(public_keys) == 4, 'manifest_count')
        for key in public_keys:
            identity(key)
        # Do not deduplicate. Manifest independently rejects duplicate keys/IDs.
        return Manifest(J(dict(domain='zoidbergchain/validator-set/v1', membership_version=1,
            protocol='zoidbergchain', protocol_version=2, network_id=network_id,
            authority_profile='static-genesis-v1', validator_epoch=0,
            byzantine_fault_budget=1, required_quorum=3,
            validator_public_keys=sorted(public_keys))))
    except V3Error as exc:
        raise AuthorityFailure(Outcome.INVALID_MANIFEST, exc.code) from exc
