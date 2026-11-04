"""Test authoring only. Expected golden bytes remain those copied from L."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VECTORS = json.loads((ROOT/'tests/fixtures/g2717m_v1/vectors.json').read_text(encoding='utf-8'))


def encode(obj):
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()


def digest(obj):
    return hashlib.sha256(encode(obj)).hexdigest()


def base():
    return json.loads(VECTORS['objects']['G2']['preimage'])


def wrap(kind, payload, network):
    return dict(domain='zoidbergchain/'+kind+'/v1', network_id=network,
        object_type=kind, payload=payload, protocol='zoidbergchain', protocol_version=2)


def rebind(e):
    """Author internally coherent test variants; never updates golden expected G."""
    e = deepcopy(e)
    p, n = e['payload'], e['network_id']
    for name in ('validator_manifest', 'policy_registry', 'reviewer_bootstrap', 'native_bootstrap'):
        p[name]['network_id'] = n
    p['validator_set_commitment'] = digest(p['validator_manifest'])
    p['policy_registry_digest'] = digest(p['policy_registry'])
    p['agreement_descriptor']['application_policy_digest'] = p['policy_registry_digest']
    p['agreement_profile_digest'] = digest(p['agreement_descriptor'])
    sources = {row['policy_kind']: hashlib.sha256(bytes.fromhex(row['canonical_bytes'])).hexdigest()
        for row in p['policy_registry']['policies']}
    b = p['reviewer_bootstrap']
    b['reviewer_policy_digest'], b['reputation_rule_digest'] = sources['reviewer'], sources['reputation']
    for kind in ('reviewer', 'native'):
        p[kind+'_bootstrap_digest'] = digest(wrap(kind+'-bootstrap', p[kind+'_bootstrap'], n))
    h = p['history_bootstrap']
    h['bootstrap_history_commitment'] = digest(wrap('history-bootstrap',
        dict(history_version=1, bootstrap_events=[]), n))
    h['initial_state'] = dict(state_version=1, policy_registry_digest=p['policy_registry_digest'],
        reviewer_bootstrap_digest=p['reviewer_bootstrap_digest'], native_bootstrap_digest=p['native_bootstrap_digest'],
        bootstrap_history_commitment=h['bootstrap_history_commitment'])
    h['initial_state_commitment'] = digest(wrap('initial-state', h['initial_state'], n))
    return e


def wide():
    e = base()
    p = e['payload']
    p['reviewer_bootstrap']['reviewers'] = ['0x'+format(i, '040x') for i in range(128)]
    p['native_bootstrap'].update(allocations=[dict(wallet_address='0x'+format(i, '040x'),
        balance='0.000001', next_nonce='1') for i in range(4096)], total_supply='0.004096')
    for row in p['policy_registry']['policies'][:3]:
        row['canonical_bytes'] = encode({'x': 'a'*8184}).hex()  # exactly 8192 source bytes
    return rebind(e)
