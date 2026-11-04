"""Task 7.17I's closed ASCII wire profile; no legacy signature fallback."""
from copy import deepcopy
from dataclasses import dataclass
import hashlib

from eth_keys import keys
from eth_keys.exceptions import BadSignature
from eth_utils import keccak, ValidationError

from canonical_v3.primitives import (
    canonical, parse as strict_json, closed, require, uint, h64, wallet,
    pattern, signature, V3Error, MAX_UINT, CURVE_ORDER,
)

MAX_ROUND = 2147483647
COMMON = ('agreement_profile_digest block_height genesis_hash message_version '
          'parent_hash round validator_epoch validator_id validator_set_commitment')
LIMITS = dict(agreement_bytes=4096, block_bytes=3145728, commit_proof_bytes=16384,
    envelope_bytes=2048, manifest_bytes=8192, max_depth=32, max_round=MAX_ROUND,
    max_uint=MAX_UINT, prevote_certificate_bytes=12288, proposal_bundle_bytes=3160400,
    round_evidence_bytes=8192, signed_bytes=2304)


def ascii_tree(value):
    if type(value) is dict:
        for k, v in value.items():
            ascii_tree(k)
            ascii_tree(v)
    elif type(value) is list:
        for v in value:
            ascii_tree(v)
    elif type(value) is str:
        require(all(32 <= ord(c) <= 126 for c in value), 'ascii_string')


def J(value):
    ascii_tree(value)
    return canonical(value)


def parse(raw, limit=16384):
    value = strict_json(raw, limit=limit)
    require(J(value) == raw, 'ascii_json')
    return value


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def descriptor(policy_digest):
    h64(policy_digest)
    return dict(agreement_version=1, application_policy_digest=policy_digest,
        authority_profile='static-genesis-n4-f1-q3-v1', domain='zoidbergchain/bft-agreement/v1',
        limits=deepcopy(LIMITS), parent_profile='immediate-finalized-v1',
        proposer_profile='height-minus-one-plus-round-mod-four-v1', protocol='zoidbergchain',
        protocol_version=2, reference='arxiv:1807.04938v3/Algorithm1',
        rule_selection='printed-lines-1-67', signer_profile='reserve-sign-store-release-v1',
        timeout_profile='linear-1000ms-plus-1000ms-per-round-v1', wire_profile='bft-ascii-json-v1')


def public_key(raw):
    pattern(raw, r'0[23][0-9a-f]{64}')
    # eth_keys decompression alone does not check x<p or curve membership.
    x = int(raw[2:], 16)
    p = 2**256 - 2**32 - 977
    require(x < p and pow((x*x*x+7) % p, (p-1)//2, p) == 1, 'public_key_point')
    return keys.PublicKey.from_compressed_bytes(bytes.fromhex(raw))


def identity(pub):
    return public_key(pub).to_checksum_address().lower()


@dataclass(frozen=True)
class Context:
    """Explicit synthetic context, pinned by fixtures, never genesis discovery."""
    manifest_bytes: bytes
    agreement_bytes: bytes
    genesis_hash: str

    def __post_init__(self):
        m = parse(self.manifest_bytes, 8192)
        closed(m, 'domain membership_version protocol protocol_version network_id '
            'authority_profile validator_epoch byzantine_fault_budget required_quorum validator_public_keys')
        pattern(m['network_id'], r'[a-z0-9][a-z0-9-]{2,63}')
        require(m == dict(domain='zoidbergchain/validator-set/v1', membership_version=1,
            protocol='zoidbergchain', protocol_version=2, network_id=m['network_id'],
            authority_profile='static-genesis-v1', validator_epoch=0,
            byzantine_fault_budget=1, required_quorum=3,
            validator_public_keys=m['validator_public_keys']), 'manifest_constants')
        for k in ('membership_version', 'protocol_version', 'validator_epoch',
                  'byzantine_fault_budget', 'required_quorum'):
            uint(m[k])
        pubs = m['validator_public_keys']
        require(type(pubs) is list and len(pubs) == 4, 'manifest_count')
        ids = [identity(k) for k in pubs]
        require(pubs == sorted(set(pubs)) and len(set(ids)) == 4, 'manifest_order')
        d = parse(self.agreement_bytes, 4096)
        require(type(d) is dict and 'application_policy_digest' in d, 'agreement_schema')
        require(J(d) == J(descriptor(d['application_policy_digest'])), 'agreement_profile')
        h64(self.genesis_hash)

    @property
    def manifest(self):
        return parse(self.manifest_bytes, 8192)

    @property
    def network(self):
        return self.manifest['network_id']

    @property
    def C(self):
        return sha(self.manifest_bytes)

    @property
    def A(self):
        return sha(self.agreement_bytes)

    @property
    def members(self):
        return {identity(k): k for k in self.manifest['validator_public_keys']}

    def proposer(self, height, round):
        return self.manifest['validator_public_keys'][((height-1) % 4 + round % 4) % 4]

    def namespace(self, pub):
        require(pub in self.members.values(), 'not_member')
        return dict(protocol='zoidbergchain', protocol_version=2, network_id=self.network,
            genesis_hash=self.genesis_hash, agreement_profile_digest=self.A,
            validator_epoch=0, validator_set_commitment=self.C,
            validator_public_key=pub, validator_id=identity(pub))


def envelope(raw, ctx):
    e = parse(raw, 2048)
    closed(e, 'domain network_id object_type payload protocol protocol_version')
    p = e['payload']
    require(type(p) is dict and p.get('step') in ('propose', 'prevote', 'precommit'), 'purpose')
    proposal = p['step'] == 'propose'
    closed(p, COMMON + ' block_hash step' + (' valid_round' if proposal else ''))
    kind = 'bft-proposal' if proposal else 'bft-vote'
    require(e['domain'] == 'zoidbergchain/' + kind + '/v1' and e['object_type'] == kind,
            'domain')
    require(e['protocol'] == 'zoidbergchain' and uint(e['protocol_version']) == 2 and
            uint(p['message_version']) == 1, 'version')
    require(e['network_id'] == ctx.network and p['genesis_hash'] == ctx.genesis_hash and
            p['agreement_profile_digest'] == ctx.A and p['validator_set_commitment'] == ctx.C,
            'context')
    require(uint(p['validator_epoch']) == 0, 'epoch')
    uint(p['block_height'], 1)
    uint(p['round'], 0, MAX_ROUND)
    for field in ('genesis_hash', 'parent_hash', 'agreement_profile_digest', 'validator_set_commitment'):
        h64(p[field])
    wallet(p['validator_id'])
    require(p['validator_id'] in ctx.members, 'not_member')
    if p['block_height'] == 1:
        require(p['parent_hash'] == ctx.genesis_hash, 'parent')
    if p['block_hash'] is not None:
        h64(p['block_hash'])
    if proposal:
        require(p['block_hash'] is not None, 'nil_proposal')
        uint(p['valid_round'], -1, p['round']-1)
        require(ctx.members[p['validator_id']] == ctx.proposer(p['block_height'], p['round']),
                'proposer')
    return e


def prefix(raw):
    return b'\x19Ethereum Signed Message:\n' + str(len(raw)).encode('ascii')


def signing_digest(raw):
    return keccak(prefix(raw) + raw)


def signed(raw, ctx):
    s = parse(raw, 2304)
    closed(s, 'envelope signature signature_scheme')
    require(s['signature_scheme'] == 'personal_sign', 'signature_scheme')
    m = J(s['envelope'])
    e = envelope(m, ctx)
    signature(s['signature'])
    sig = bytes.fromhex(s['signature'][2:])
    try:
        recovered = keys.Signature(sig[:64] + bytes([sig[64]-27])).recover_public_key_from_msg_hash(
            signing_digest(m)).to_compressed_bytes().hex()
    except (BadSignature, ValidationError, ValueError, OverflowError):
        raise V3Error('signature_recovery') from None
    require(recovered == ctx.members[e['payload']['validator_id']], 'signature_key')
    return s


def slot_key(e):
    p = e['payload']
    return dict(height=p['block_height'], round=p['round'], purpose=p['step'])


def commitment(e):
    return {k: v for k, v in e['payload'].items() if k != 'validator_id'}


def proof(raw, ctx, kind):
    limits = dict(pv=12288, q4=16384, re=8192)
    require(kind in limits, 'proof_kind')
    obj = parse(raw, limits[kind])
    if kind == 're':
        closed(obj, 'evidence_version messages')
        require(uint(obj['evidence_version']) == 1, 'evidence_version')
        votes = obj['messages']
        require(type(votes) is list and len(votes) == 2, 'evidence_count')
    else:
        version, count_key, number = ('certificate_version', 'votes', 1) if kind == 'pv' else (
            'proof_version', 'precommits', 4)
        closed(obj, version + ' commitment ' + count_key + (' proposal' if kind == 'q4' else ''))
        require(uint(obj[version]) == number, 'proof_version')
        votes = obj[count_key]
        require(type(votes) is list and 3 <= len(votes) <= 4, 'quorum_count')
    for v in votes:
        signed(J(v), ctx)
    ids = [v['envelope']['payload']['validator_id'] for v in votes]
    require(ids == sorted(set(ids)), 'proof_order')
    if kind == 're':
        def context(v):
            return {k: v['envelope']['payload'][k] for k in COMMON.split() if k != 'validator_id'}
        require(context(votes[0]) == context(votes[1]), 'evidence_context')
    else:
        t = obj['commitment']
        require(all(commitment(v['envelope']) == t for v in votes), 'proof_commitment')
        require(t['step'] == ('prevote' if kind == 'pv' else 'precommit'), 'proof_step')
        if kind == 'q4':
            p = signed(J(obj['proposal']), ctx)['envelope']
            require(p['payload']['step'] == 'propose' and t['block_hash'] is not None, 'proof_proposal')
            pp = {k: v for k, v in commitment(p).items() if k not in ('step', 'valid_round')}
            require(pp == {k: v for k, v in t.items() if k != 'step'}, 'proof_proposal_context')
    return obj
