"""Public INSECURE 7.17I scalars only; symbolic hashes are not real blocks/G2.

These evidence producers can equivocate deliberately. Never use as an honest
signer or import into a node. The actual signer integration uses random TestKey.
"""
from copy import deepcopy
import json
from pathlib import Path

from eth_account import Account
from eth_account.messages import encode_defunct

from isolated_bft717j.wire import Context, J, commitment, identity, parse
from isolated_bft717k.authority import TrustedTestAnchor, resolve_authority

ROOT = Path(__file__).resolve().parents[2]
VECTORS = json.loads((ROOT / 'tests/fixtures/bft717j/vectors.json').read_text(encoding='utf-8'))


def context(network=None):
    m = deepcopy(VECTORS['manifest'])
    if network is not None:
        m['network_id'] = network
    return Context(J(m), J(VECTORS['agreement']), '11'*32)


def authority(ctx=None):
    ctx = ctx or context()
    anchor = TrustedTestAnchor(ctx.manifest_bytes, ctx.agreement_bytes, ctx.genesis_hash)
    return resolve_authority(anchor, ctx.manifest_bytes, ctx.agreement_bytes,
        network_id=ctx.network, genesis_hash=ctx.genesis_hash,
        validator_set_commitment=ctx.C, agreement_profile_digest=ctx.A)


def sign(envelope, scalar):
    raw = J(envelope)
    sig = Account.sign_message(encode_defunct(primitive=raw), scalar.to_bytes(32, 'big')).signature
    return dict(envelope=envelope, signature='0x'+bytes(sig).hex(), signature_scheme='personal_sign')


def message(ctx, scalar=1, step='precommit', value='aa'*32, height=1, round=0, vr=-1, parent=None):
    key = next(k for k in VECTORS['keys'] if k['scalar'] == scalar)
    proposal = step == 'propose'
    purpose = 'bft-proposal' if proposal else 'bft-vote'
    p = dict(agreement_profile_digest=ctx.A, block_height=height, genesis_hash=ctx.genesis_hash,
        message_version=1, parent_hash=ctx.genesis_hash if parent is None else parent,
        round=round, validator_epoch=0, validator_id=identity(key['public_key']),
        validator_set_commitment=ctx.C, block_hash=value, step=step)
    if proposal:
        p['valid_round'] = vr
    return dict(domain='zoidbergchain/'+purpose+'/v1', network_id=ctx.network,
        object_type=purpose, payload=p, protocol='zoidbergchain', protocol_version=2)


def certificate(ctx, kind='q4', scalars=(1, 2, 3), **coordinates):
    step = 'prevote' if kind == 'pv' else 'precommit'
    votes = [sign(message(ctx, i, step=step, **coordinates), i) for i in scalars]
    votes.sort(key=lambda v: v['envelope']['payload']['validator_id'])
    t = commitment(votes[0]['envelope'])
    if kind == 'pv':
        return dict(certificate_version=1, commitment=t, votes=votes)
    h, r = coordinates.get('height', 1), coordinates.get('round', 0)
    proposer = ctx.proposer(h, r)
    scalar = next(k['scalar'] for k in VECTORS['keys'] if k['public_key'] == proposer)
    return dict(proof_version=4, commitment=t, precommits=votes,
                proposal=sign(message(ctx, scalar, step='propose', **coordinates), scalar))


def frozen_proof(name='q4-x'):
    return J(VECTORS['proofs'][name]['value'])
