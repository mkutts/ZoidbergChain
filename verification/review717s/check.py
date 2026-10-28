"""Reproducible public-vector verification; no private identities or signer."""
from dataclasses import asdict
import json

from eth_utils import keccak

from verification.review717r import wire as w
from .fixtures import load, pins, transcript, ROOT
from .verify import preimage, verify_user, user_bindings, verify_message, verify_clock, recover, member_key
from .history import audit_fixture_history


def verify_row(d, p, row):
    kind, obj, raw = row['kind'], row['object'], bytes.fromhex(row['hex'])
    if kind in ('OPEN', 'VOTE'):
        expected = obj
        if row['expected'] == 'REJECT':
            expected = next(r['object'] for r in d['records'] if r['name'] == 'vote-0-0')
        return verify_user(p, kind, raw, expected=user_bindings(kind, expected))
    if kind == 'MESSAGE':
        return verify_message(p, raw, **{k:obj[k] for k in ('height','parent','round','step','value','nil')},
                              pv_bytes=bytes.fromhex(d['proofs']['pv_hex']))
    time = row['time_context']
    return recover(obj['signature'], keccak(preimage(kind, obj, **time)), member_key(p, obj['validator']))


def check_vectors(d=None):
    d = d or load()
    p = pins(d)
    outcomes = []
    for row in d['records']:
        raw = w.pack(row['kind'], row['object'])
        pre = preimage(row['kind'], row['object'], **row.get('time_context', {}))
        assert raw.hex() == row['hex'] and len(raw) == row['length'] and w.hash_bytes(raw) == row['sha256']
        assert pre.hex() == row['preimage_hex'] and w.hash_bytes(pre) == row['preimage_sha256']
        assert keccak(pre).hex() == row['keccak256']
        try:
            verify_row(d, p, row)
        except ValueError as exc:
            assert row['expected'] == 'REJECT', (row['name'], str(exc))
            outcomes.append(dict(name=row['name'], outcome='REJECT', reason=str(exc)))
        else:
            assert row['expected'] != 'REJECT', row['name']
            outcomes.append(dict(name=row['name'], outcome='ACCEPT_SIGNATURE_ONLY'))
    h = d['history']
    audit = audit_fixture_history(p, transcript(d), bytes.fromhex(h['checkpoint_hex']), bytes.fromhex(h['media_hex']),
        fixture_eligibility=h['fixture_eligibility'], actual_media_parent=tuple(h['actual_media_parent']),
        pending_votes=[bytes.fromhex(h['pending_vote_hex'])])
    audit['verification'] = asdict(audit['verification'])
    return dict(records=len(outcomes), accepted=sum(x['outcome']=='ACCEPT_SIGNATURE_ONLY' for x in outcomes),
                rejected=sum(x['outcome']=='REJECT' for x in outcomes), outcomes=outcomes, history=audit)


if __name__ == '__main__':
    result = check_vectors()
    (ROOT/'verification/review717s/vector-results.json').write_text(
        json.dumps(result,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    print(json.dumps({k:result[k] for k in ('records','accepted','rejected')}))
