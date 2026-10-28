"""Read public retained evidence only. No key generation or signing capability."""
import json
from pathlib import Path

from isolated_bft717j.wire import J
from isolated_bft717k.authority import TrustedTestAnchor, resolve_authority
from verification.review717r.wire import CTX
from .verify import TestPins

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / 'tests/fixtures/review717s_v1/vectors.json'


def load():
    return json.loads(PATH.read_text(encoding='utf-8'))


def pins(data=None):
    d = data or load()
    m, a, g = J(d['manifest']), J(d['agreement']), d['context']['genesis']
    anchor = TrustedTestAnchor(m, a, g)
    authority = resolve_authority(anchor, m, a, network_id=d['context']['network'],
        genesis_hash=g, validator_set_commitment=d['context']['validators'],
        agreement_profile_digest=d['agreement_sha256'])
    return TestPins(authority, tuple((k, d['context'][k]) for k, _ in CTX), d['bootstrap'])


def transcript(data=None):
    d = data or load()
    return [dict(batch=bytes.fromhex(u['batch_hex']), proof=bytes.fromhex(u['proof_hex']))
            for u in d['history']['units']]
