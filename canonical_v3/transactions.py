"""U10/T18 signing bytes and immutable aggregate; no mempool or ledger wiring."""
import hashlib
from .primitives import (
    bounded, canonical, closed, decimal_units, envelope, h64, nonce,
    require, text, time_utc, verify_signature, wallet,
)

PAYLOAD_FIELDS = 'amount fee from_address genesis_hash memo nonce timestamp to_address transaction_type transaction_version'.split()
RECORD_FIELDS = PAYLOAD_FIELDS + 'network network_id protocol_version signature signature_scheme signed_message signed_message_hash tx_id'.split()


def signing_bytes(payload, ctx):
    from .primitives import EDGE_SPACE
    closed(payload, PAYLOAD_FIELDS)
    require(type(payload['transaction_version']) is int and payload['transaction_version'] == 2, 'transaction_version')
    require(payload['transaction_type'] == 'native_transfer', 'transaction_type')
    h64(payload['genesis_hash'])
    require(payload['genesis_hash'] == ctx.genesis_hash, 'genesis_context')
    wallet(payload['from_address'])
    wallet(payload['to_address'])
    require(payload['from_address'] != payload['to_address'], 'self_transfer')
    decimal_units(payload['amount'], positive=True, maximum=1000000000 * 1000000)
    require(payload['fee'] == '0', 'fee')
    nonce(payload['nonce'])
    time_utc(payload['timestamp'])
    memo = payload['memo']
    if memo is not None:
        text(memo, 280, 1120)
        require(memo.strip(EDGE_SPACE) == memo, 'memo_edges')
    result = canonical(envelope(payload, 'native-transfer', ctx))
    require(len(result) <= 4096, 'signing_message_size')
    return result


def validate_transaction(record, ctx):
    closed(record, RECORD_FIELDS)
    bounded(record, 8192)
    require(type(record['protocol_version']) is int and record['protocol_version'] == 2, 'protocol_version')
    require(record['network_id'] == ctx.network_id and record['network'] == ctx.application, 'network_context')
    require(record['signature_scheme'] == 'personal_sign', 'signature_scheme')
    message = signing_bytes({key: record[key] for key in PAYLOAD_FIELDS}, ctx)
    text(record['signed_message'], 4096, 4096)
    h64(record['tx_id'])
    h64(record['signed_message_hash'])
    tx_id = hashlib.sha256(message).hexdigest()
    require(record['signed_message'] == message.decode('utf-8') and
            record['tx_id'] == record['signed_message_hash'] == tx_id, 'transaction_commitment')
    verify_signature(message, record['signature'], record['from_address'])


def validate_transactions(records, ctx):
    require(type(records) is list and len(records) <= 10, 'native_count')
    bounded(records, 98304)
    for record in records:
        validate_transaction(record, ctx)
    order = [(r['from_address'], int(r['nonce']), r['tx_id']) for r in records]
    require(order == sorted(order), 'native_order')
    require(len({r['tx_id'] for r in records}) == len(records) and
            len({(r['from_address'], r['nonce']) for r in records}) == len(records), 'native_duplicate')
    for left, right in zip(records, records[1:]):
        if left['from_address'] == right['from_address']:
            require(int(right['nonce']) == int(left['nonce']) + 1, 'native_nonce_gap')


def aggregate_bytes(records, ctx):
    validate_transactions(records, ctx)
    return canonical(records, ascii_only=True)


def aggregate_hash(records, ctx):
    return hashlib.sha256(aggregate_bytes(records, ctx)).hexdigest()


def reward(creator):
    wallet(creator)
    return dict(amount='5', payload_size_kb='0', recipient=creator, sender='REWARD_POOL', tip='0')


def validate_rewards(records, creator):
    require(type(records) is list and len(records) == 1, 'reward_count')
    closed(records[0], 'amount payload_size_kb recipient sender tip')
    require(canonical(records[0]) == canonical(reward(creator)), 'reward_rule')
