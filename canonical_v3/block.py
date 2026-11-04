"""Canonical non-genesis block formats. Format validity does not authorize a block.

No chain/DB/services are imported. Predecessor time/height, ledger transitions,
claim uniqueness, historical reviewer state, media safety and frozen-snapshot
completeness must be verified by later integration, after reconstruction.
"""
from dataclasses import dataclass
import hashlib

from .evidence import certificate_size_bound, fields_equal, fixed, validate_certificate
from .media import validate_descriptor, reconstruct
from .primitives import (
    MAX_RECORD, bounded, canonical, closed, envelope, h64, parse, pattern,
    rational, require, seconds, text, uint, validate_rational, wallet,
)
from .transactions import aggregate_hash, validate_rewards

PAYLOAD_FIELDS = '''block_version index previous_hash timestamp minted_at transactions native_transactions
transactions_hash miner submission_id certificate_id vote_hash creator_wallet content_type approval_percentage
originality_score decisive_vote_total minimum_votes_required approved_at reward_type reward_source
reward_recipient reward_amount voter_rewards admission_certificate media'''.split()


def validate_header(payload):
    fixed(payload['block_version'], 3)
    uint(payload['index'], 1)
    h64(payload['previous_hash'])
    seconds(payload['timestamp'])
    seconds(payload['minted_at'])
    pattern(payload['miner'], r'[0-9a-f]{66}')
    from cryptography.hazmat.primitives.asymmetric import ec
    try:
        ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256K1(), bytes.fromhex(payload['miner']))
    except ValueError:
        require(False, 'miner_public_key')
    pattern(payload['submission_id'], r'[0-9a-f]{32}')
    for name in ('certificate_id', 'vote_hash', 'transactions_hash'):
        h64(payload[name])
    wallet(payload['creator_wallet'])
    wallet(payload['reward_recipient'])
    validate_rational(payload['approval_percentage'])
    validate_rational(payload['originality_score'])
    uint(payload['decisive_vote_total'], 1, 16)
    fields_equal(payload, dict(minimum_votes_required=5, approved_at=0,
                 reward_type='meme_mining_reward', reward_source='reward_pool',
                 reward_recipient=payload['creator_wallet'], reward_amount='5', voter_rewards=[]))


def validate_payload(payload, ctx):
    closed(payload, PAYLOAD_FIELDS, ('meme_text',))
    bounded(payload, MAX_RECORD)
    validate_header(payload)
    validate_descriptor(payload['media'])
    mime = payload['media']['mime_type']
    require(payload['content_type'] in (('text',) if mime == 'text/plain' else ('image', 'mixed')), 'content_type')
    if 'meme_text' in payload:
        require(mime != 'text/plain', 'text_caption')
        text(payload['meme_text'], 1000, 4096)
    validate_rewards(payload['transactions'], payload['creator_wallet'])
    fixed(payload['transactions_hash'], aggregate_hash(payload['native_transactions'], ctx))
    certificate = payload['admission_certificate']
    validate_certificate(certificate, ctx)
    fields_equal(certificate, dict(submission_id=payload['submission_id'],
                 content_hash=payload['media']['original_sha256'], creator_wallet=payload['creator_wallet'],
                 certificate_digest=payload['certificate_id']))
    fields_equal(certificate['technical_evidence'], dict(detected_mime_type=mime,
                 raw_media_byte_length=payload['media']['original_size']))
    tally = certificate['originality']
    summary = rational(tally['positive_votes'], tally['approval_denominator'])
    fields_equal(payload, dict(approval_percentage=summary, originality_score=summary,
                 decisive_vote_total=tally['approval_denominator'], vote_hash=tally['vote_set_digest']))


@dataclass(frozen=True)
class Sizes:
    complete: int
    base64: int
    certificate: int
    native: int
    rest: int


def check_complete_size(raw):
    require(type(raw) is bytes and len(raw) <= MAX_RECORD, 'block_size')


def check_budgets(record, raw):
    check_complete_size(raw)
    payload = record['envelope']['payload']
    cert = len(canonical(payload['admission_certificate']))
    native = len(canonical(payload['native_transactions']))
    content = len(payload['media']['payload'])
    rest = len(raw) - cert - native - content
    require(cert <= 196608 and native <= 98304 and 0 <= rest <= 32768, 'block_component_budget')
    return Sizes(len(raw), content, cert, native, rest)


def encode_record(payload, ctx):
    """Construct an immutable wire copy after format/signature checks; no decode."""
    validate_payload(payload, ctx)
    value = envelope(payload, 'block', ctx)
    preimage = canonical(value)
    record = dict(envelope=value, hash=hashlib.sha256(preimage).hexdigest())
    raw = canonical(record)
    check_budgets(record, raw)
    return raw


def parse_record(raw, ctx):
    """Strict format/hash/signature validation, deliberately separate from media decode."""
    check_complete_size(raw)
    record = parse(raw)
    closed(record, 'envelope hash')
    value = record['envelope']
    closed(value, 'domain network_id object_type payload protocol protocol_version')
    fields_equal(value, dict(domain='zoidbergchain/block/v2', network_id=ctx.network_id,
                            object_type='block', protocol='zoidbergchain', protocol_version=2))
    h64(record['hash'])
    require(record['hash'] == hashlib.sha256(canonical(value)).hexdigest(), 'block_hash')
    # Check parent budgets before expensive signature work.
    require(type(value['payload']) is dict, 'payload_type')
    closed(value['payload'], PAYLOAD_FIELDS, ('meme_text',))
    validate_descriptor(value['payload']['media'])
    check_budgets(record, raw)
    validate_payload(value['payload'], ctx)
    return record


def reconstruct_record_media(raw, ctx, *, decoder=None):
    """Return worker Outcome; VALID still requires later state/media-safety checks."""
    record = parse_record(raw, ctx)
    return reconstruct(record['envelope']['payload']['media'], decoder=decoder)


def conservative_size_bound():
    """Analytic widths, not a fabricated valid record. All quotes/delimiters counted."""
    def obj(widths):
        return 2 + max(0, len(widths) - 1) + sum(len(k) + 3 + v for k, v in widths.items())

    payload = dict(block_version=1, index=16, previous_hash=66, timestamp=34, minted_at=34,
                   transactions=128, native_transactions=10 * 8192 + 11, transactions_hash=66, miner=68,
                   submission_id=34, certificate_id=66, vote_hash=66, creator_wallet=44,
                   content_type=7, approval_percentage=33, originality_score=33,
                   decisive_vote_total=2, minimum_votes_required=2, approved_at=1,
                   reward_type=20, reward_source=13, reward_recipient=44, reward_amount=3,
                   voter_rewards=2, admission_certificate=certificate_size_bound(), media=2796204 + 231, meme_text=6002)
    require(set(payload) == set(PAYLOAD_FIELDS) | {'meme_text'}, 'size_inventory')
    block = obj(dict(domain=24, network_id=66, object_type=7, payload=obj(payload),
                     protocol=15, protocol_version=1))
    return block + 87
