"""Explicit fixture authoring only. Does NOT import canonical_v3 or run in tests.

Independent JSON/preimage construction, using public deterministic TEST keys.
Never regenerate to resolve a disagreement: investigate against the A/B contract.
No database, chain, production config or real launch identity is used.
"""
from copy import deepcopy
import base64
import hashlib
import json
from pathlib import Path

from eth_account import Account
from eth_account.messages import encode_defunct

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'tests/fixtures/milestone_7_v3_v1'
N = 'zoidberg-signing-vector-v2'
G = 'a' * 64
MEDIA_POLICY = 'b' * 64
REVIEW_POLICY = 'c' * 64
ISSUE = '2026-10-19T00:00:00+00:00'
EXPIRE = '2026-10-20T00:00:00+00:00'
STATEMENT_ID = 'zoidberg-public-testnet-v1/submitter-rights-permanence/1'
STATEMENT = (
    'I assert that I have the right or authorization to submit this exact content '
    'under the identified ZoidbergChain Public Testnet media-admission policy. '
    'I understand that, if accepted and finalized, the accepted media bytes become '
    'permanently replicated in immutable ZoidbergChain history and cannot be removed '
    'through ordinary moderation. This testnet attestation is my signed assertion; '
    'it is not proof of ownership, a legal determination, a waiver, or a license '
    'beyond this explicit assertion.'
)


def j(value, ascii_only=False):
    return json.dumps(value, ensure_ascii=ascii_only, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def env(payload, purpose):
    return dict(domain=f'zoidbergchain/{purpose}/v2', network_id=N, object_type=purpose,
                payload=payload, protocol='zoidbergchain', protocol_version=2)


def key(number):
    # Published, predictable fixture scalars 0x11..11 through 0x88..88.
    return bytes([number * 17]) * 32


def address(number):
    return Account.from_key(key(number)).address.lower()


def sign(raw, number):
    return '0x' + Account.sign_message(encode_defunct(primitive=raw), key(number)).signature.hex()


def tally(votes, dim):
    selected = sorted((v for v in votes if v['dimension'] == dim), key=lambda v: v['voter_wallet_address'])
    positive = 'original' if dim == 'originality' else 'admissible'
    negative = 'not_original' if dim == 'originality' else 'not_admissible'
    p = sum(v['vote_type'] == positive for v in selected)
    n = sum(v['vote_type'] == negative for v in selected)
    e = sum(v['reviewer_status'] == 'ESTABLISHED_REVIEWER' for v in selected)
    q = len(selected) >= 5 and e >= 1
    resolved = q and p + n > 0
    outcome = (positive if p * 10000 >= (p + n) * 7000 else negative) if resolved else 'unresolved'
    projection = [dict(wallet=v['voter_wallet_address'], choice=v['vote_type'],
                       identity=v['vote_identity'], status=v['reviewer_status']) for v in selected]
    return dict(dimension=dim, policy_version=2, policy_digest=REVIEW_POLICY,
                eligible_valid_votes=len(selected), established_reviewer_votes=e, positive_votes=p,
                negative_votes=n, unsure_votes=len(selected) - p - n, approval_denominator=p + n,
                approval_threshold_bps=7000, quorum_reached=q, resolved=resolved,
                outcome=outcome, vote_set_digest=sha(j(projection)))


def build():
    DEST.mkdir(parents=True, exist_ok=True)
    entries = []

    def add(name, kind, value, expected='valid', code=None, raw=None):
        raw = j(value) if raw is None else raw
        filename = name + '.json'
        (DEST / filename).write_bytes(raw)
        entry = dict(id=name, kind=kind, file=filename, expected=expected,
                     bytes=len(raw), sha256=sha(raw))
        if code:
            entry['code'] = code
        entries.append(entry)

    original = b'a'
    media = dict(codec_id='identity', codec_version=1, encoding_version=1, mime_type='text/plain',
                 original_sha256=sha(original), original_size=1, stored_size=1, payload='YQ==')
    zstd = dict(media, codec_id='zstd', stored_size=14, payload='KLUv/SQBCQAAYVtujKk=')
    add('identity', 'descriptor', media)
    add('zstd', 'descriptor', zstd)
    u = dict(amount='1', fee='0', from_address=address(1), genesis_hash=G, memo=None, nonce='1',
             timestamp=ISSUE, to_address='0x' + '2' * 40, transaction_type='native_transfer', transaction_version=2)

    def native(payload):
        m = j(env(payload, 'native-transfer'))
        return dict(payload, network=N, network_id=N, protocol_version=2, signature=sign(m, 1),
                    signature_scheme='personal_sign', signed_message=m.decode(), signed_message_hash=sha(m), tx_id=sha(m))

    transaction = native(u)
    # Published Task 7.10B oracle is a prerequisite, not overwritten from code.
    assert transaction['tx_id'] == 'e68931c52c88865a0ad5f73edee11b36d57887c1f953898ab0f052d86ac4f425'
    assert sha(j(transaction)) == '6f4133b41f9cc2b9833e6d826baf7578727e5ef9f9bd6db23d9177cf25ea94a7'
    add('native-message', 'preimage', env(u, 'native-transfer'))
    add('native', 'transaction', transaction)
    add('native-aggregate', 'aggregate', [transaction], raw=j([transaction], True))
    unicode_transaction = native(dict(u, memo='é'))
    add('native-unicode', 'transaction', unicode_transaction)
    add('native-unicode-aggregate', 'aggregate', [unicode_transaction], raw=j([unicode_transaction], True))
    high = deepcopy(transaction)
    sig = bytes.fromhex(high['signature'][2:])
    order = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
    high['signature'] = '0x' + (sig[:32] + (order - int.from_bytes(sig[32:64])).to_bytes(32) + bytes([55 - sig[64]])).hex()
    add('native-high-s', 'transaction', high)

    technical = dict(evidence_version=1, validator_id='zoidberg-media-technical-validator/1',
        policy_id=N + '/media-admission/2', policy_version=2, policy_digest=MEDIA_POLICY,
        outcome='ACCEPT', reason_codes=['ACCEPTED_POLICY_METADATA'], detected_media_type='plain_utf8_text',
        detected_mime_type='text/plain', raw_media_byte_length=1, raw_media_sha256=sha(original),
        raw_media_semantics='policy_canonical_utf8_text', width_pixels=None, height_pixels=None,
        frame_count=None, aggregate_decoded_pixels=None)
    technical['evidence_digest'] = sha(j(technical))
    ap = dict(attestation_version=1, statement_id=STATEMENT_ID, statement_version=1, statement=STATEMENT,
        wallet_address=address(1), submission_id='d' * 32, raw_media_sha256=sha(original),
        policy_id=N + '/media-admission/2', policy_version=2, policy_digest=MEDIA_POLICY,
        technical_evidence_version=1, technical_evidence_digest=technical['evidence_digest'],
        nonce='fixture-attestation-1', issued_at=ISSUE, expires_at=EXPIRE, network_id=N)
    am = j(env(ap, 'submitter-attestation'))
    attestation = dict(attestation_version=1, statement_id=STATEMENT_ID, statement_version=1,
        domain='zoidbergchain/submitter-attestation/v2', protocol_version=2, network_id=N,
        signature_scheme='personal_sign', signer_wallet=address(1), signature=sign(am, 1), nonce=ap['nonce'],
        canonical_payload=ap, canonical_payload_digest=sha(am), canonical_message=am.decode(), canonical_message_hash=sha(am))
    votes = []
    for dim in ('admissibility', 'originality'):
        for number in range(2, 9):
            choice = ('not_original' if number >= 7 else 'original') if dim == 'originality' else 'admissible'
            vp = dict(domain='zoidbergchain/community-review/v3', network_id=N, vote_version=3, policy_version=2,
                policy_digest=REVIEW_POLICY, reviewer_policy_version=1, reputation_rule_version=2,
                wallet_address=address(number), submission_id='d' * 32, content_hash=sha(original),
                dimension=dim, choice=choice, nonce=f'fixture-{dim}-{number}', issued_at=ISSUE, expires_at=EXPIRE)
            vm = j(vp)
            vs = sign(vm, number)
            votes.append(dict(submission_id='d' * 32, content_hash=sha(original), voter=address(number),
                voter_wallet_address=address(number), vote_type=choice, dimension=dim, vote_version=3,
                protocol_version=2, network_id=N, signature_scheme='personal_sign', vote_signature=vs,
                vote_message=vm.decode(), vote_nonce=vp['nonce'], signed_message_hash=sha(vm),
                vote_issued_at=ISSUE, vote_expires_at=EXPIRE, vote_identity=sha(j(dict(payload=vp, signature=vs))),
                reviewer_policy_version=1, reputation_rule_version=2,
                reviewer_status='ESTABLISHED_REVIEWER' if number == 2 else 'PROBATIONARY_REVIEWER',
                reviewer_eligible=True, reviewer_status_effective_height=0, reviewer_status_reference_block_hash=G))
    votes.sort(key=lambda v: (v['dimension'], v['voter_wallet_address'], v['vote_identity']))
    certificate = dict(certificate_version=2, network_id=N, submission_id='d' * 32, content_hash=sha(original),
        creator_wallet=address(1), policy_id=N + '/media-admission/2', policy_version=2, policy_digest=MEDIA_POLICY,
        technical_evidence_version=1, technical_evidence=technical, attestation_version=1, attestation=attestation,
        review_policy_version=2, review_policy_digest=REVIEW_POLICY, votes=votes,
        originality=tally(votes, 'originality'), admissibility=tally(votes, 'admissibility'))
    certificate['certificate_digest'] = sha(j(certificate))
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
    miner = ec.derive_private_key(int.from_bytes(key(1)), ec.SECP256K1()).public_key().public_bytes(
        Encoding.X962, PublicFormat.CompressedPoint).hex()
    p = dict(block_version=3, index=1, previous_hash=G, timestamp='1792368000', minted_at='1792368000',
        transactions=[dict(amount='5', payload_size_kb='0', recipient=address(1), sender='REWARD_POOL', tip='0')],
        native_transactions=[transaction], transactions_hash=sha(j([transaction], True)), miner=miner,
        submission_id='d' * 32, certificate_id=certificate['certificate_digest'],
        vote_hash=certificate['originality']['vote_set_digest'], creator_wallet=address(1), content_type='text',
        approval_percentage=dict(numerator=5, denominator=7), originality_score=dict(numerator=5, denominator=7),
        decisive_vote_total=7, minimum_votes_required=5, approved_at=0, reward_type='meme_mining_reward',
        reward_source='reward_pool', reward_recipient=address(1), reward_amount='5', voter_rewards=[],
        admission_certificate=certificate, media=media)

    def record(payload):
        e = env(payload, 'block')
        return dict(envelope=e, hash=sha(j(e)))

    base = record(p)
    add('block-identity', 'record', base)
    add('block-zstd', 'record', record(dict(p, media=zstd)))
    add('block-high-s', 'record', record(dict(p, native_transactions=[high], transactions_hash=sha(j([high], True)))))
    for n, d in ((5, 7), (1, 3), (0, 1), (1, 1), (15, 16)):
        add(f'ratio-{n}-{d}', 'ratio', dict(numerator=n, denominator=d))
    for name, value in [('unreduced', dict(numerator=2, denominator=6)), ('zero-alias', dict(numerator=0, denominator=5)),
                        ('zero-votes', dict(numerator=0, denominator=0)), ('negative', dict(numerator=1, denominator=-3)),
                        ('float', dict(numerator=1.0, denominator=3)), ('bool', dict(numerator=True, denominator=3)),
                        ('too-large', dict(numerator=1, denominator=17))]:
        add('ratio-bad-' + name, 'ratio', value, 'invalid')
    for name, change in [('unsupported', dict(codec_id='gzip')), ('pad-bits', dict(payload='YR==')),
                         ('oversize-text', dict(original_size=262145)), ('size-bool', dict(original_size=True)),
                         ('unknown', dict(extra=1)), ('base64-whitespace', dict(payload='Y Q='))]:
        add('media-bad-' + name, 'descriptor', dict(media, **change), 'invalid')
    corrupt = dict(zstd, payload=base64.b64encode(bytes.fromhex('28b52ffd2401090000615b6e8ca8')).decode())
    add('media-bad-checksum', 'reconstruction', corrupt, 'invalid')
    add('media-bad-hash', 'reconstruction', dict(media, original_sha256='0' * 64), 'invalid')
    for name, changes in [('missing-memo', None), ('wrong-network', dict(network_id='other-network-v2')),
                          ('old-version', dict(transaction_version=1)), ('legacy-signature', dict(signature='YQ==')),
                          ('unsigned', dict(signature=None)), ('wrong-genesis', dict(genesis_hash='b' * 64)),
                          ('tampered-signature', dict(signature='0x3f' + transaction['signature'][4:]))]:
        t = dict(transaction)
        if changes is None:
            del t['memo']
        else:
            t.update(changes)
        add('native-bad-' + name, 'transaction', t, 'invalid')
    mutations = {}
    q = deepcopy(p); q['transactions'].append(deepcopy(q['transactions'][0])); mutations['double-reward'] = q
    q = deepcopy(p); q['transactions'][0]['signature'] = None; mutations['reward-signature'] = q
    q = deepcopy(p); q['transactions'][0]['recipient'] = address(2); mutations['reward-recipient'] = q
    q = deepcopy(p); q['transactions'][0]['sender'] = 'GENESIS'; mutations['genesis-reward'] = q
    q = deepcopy(p); q['admission_certificate']['votes'].reverse(); mutations['vote-order'] = q
    q = deepcopy(p)
    first = q['admission_certificate']['votes'][0]
    first['reviewer_status'] = 'PROBATIONARY_REVIEWER' if first['reviewer_status'] == 'ESTABLISHED_REVIEWER' else 'ESTABLISHED_REVIEWER'
    mutations['status-tamper'] = q
    q = deepcopy(p); q['admission_certificate']['technical_evidence']['extra'] = 1; mutations['evidence-extra'] = q
    q = deepcopy(p); q['admission_certificate']['attestation']['signature'] = transaction['signature']; mutations['attestation-signature'] = q
    q = deepcopy(p); q['approval_percentage'] = dict(numerator=1, denominator=1); mutations['summary-tamper'] = q
    q = deepcopy(p); q['native_transactions'] *= 2; q['transactions_hash'] = sha(j(q['native_transactions'], True)); mutations['native-duplicate'] = q
    q = deepcopy(p); q['meme_text'] = 'caption'; mutations['text-caption'] = q
    q = deepcopy(p); q['finality'] = {}; mutations['circular-finality'] = q
    q = deepcopy(p); q['block_version'] = True; mutations['bool-version'] = q
    for name, q in mutations.items():
        add('block-bad-' + name, 'record', record(q), 'invalid')
    for name, raw in [('duplicate', b'{"x":1,"x":1}'), ('surrogate', b'{"x":"\\ud800"}'),
                      ('negative-zero', b'{"x":-0}'), ('nan', b'{"x":NaN}'),
                      ('unicode-escape', b'{"x":"\\u00e9"}'), ('bom', b'\xef\xbb\xbf{}'),
                      ('depth', b'[' * 33 + b'0' + b']' * 33)]:
        add('json-bad-' + name, 'json', None, 'invalid', raw=raw)
    add('unicode', 'json', {'x': 'é e\u0301 😀 /\u2028\u2029\x00\b\t\n\f\r"\\'})
    fp = dict(attestation_version=2, validator_address=address(1), block_height=1, block_hash=base['hash'])
    fm = j(env(fp, 'finality-attestation'))
    finality = dict(fp, network_id=N, domain='zoidbergchain/finality-attestation/v2',
                    signature_scheme='personal_sign', signature=sign(fm, 1), message=fm.decode())
    add('finality', 'finality', finality)
    proof = dict(block_height=1, block_hash=base['hash'], network_id=N, domain=finality['domain'],
                 attestation_version=2, validator_set=[address(1)], required_quorum=1, attestations=[finality])
    add('finality-proof', 'proof', proof)
    for name, choices in [('zero-votes', []), ('all-unsure', ['unsure'] * 7),
                          ('defined-zero', ['not_original'] * 7),
                          ('one-third', ['original', 'not_original', 'not_original'])]:
        selected = []
        for number, choice in enumerate(choices, 2):
            v = deepcopy(next(v for v in votes if v['dimension'] == 'originality' and v['voter_wallet_address'] == address(number)))
            vp = json.loads(v['vote_message'])
            vp['choice'] = choice
            vm = j(vp)
            vs = sign(vm, number)
            v.update(vote_type=choice, vote_message=vm.decode(), vote_signature=vs,
                     signed_message_hash=sha(vm), vote_identity=sha(j(dict(payload=vp, signature=vs))))
            selected.append(v)
        selected.sort(key=lambda v: (v['dimension'], v['voter_wallet_address'], v['vote_identity']))
        summary = tally(selected, 'originality')
        add('tally-' + name, 'tally-case', dict(votes=selected, tally=summary,
             ratio=None if name in ('zero-votes', 'all-unsure') else
             dict(numerator=0, denominator=1) if name == 'defined-zero' else dict(numerator=1, denominator=3)))
    manifest = dict(format_version='task-7.10c-v1', warning='FORMAT/CRYPTO FIXTURES ONLY; symbolic policies/genesis; no ancestry, ledger or image admission authority',
        context=dict(network_id=N, application=N, genesis_hash=G, media_policy_digest=MEDIA_POLICY, review_policy_digest=REVIEW_POLICY),
        original_hex=original.hex(), vectors=entries)
    (DEST / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    print(f'{len(entries)} frozen vectors authored; compare independent verifier and published A/B oracles before review')


if __name__ == '__main__':
    build()
