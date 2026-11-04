"""Verify R's exact binary preimages. Never authorize signing or finalization.

A = signatures/canonical bytes; B = independently pinned TEST membership;
C = matching quorum structure. D = complete finalized history and E = correct
agreement execution are ALWAYS false, including for a fully supplied transcript.
"""
from dataclasses import dataclass

from eth_keys import keys
from eth_keys.exceptions import BadSignature
from eth_utils import keccak, ValidationError

from canonical_v3.primitives import CURVE_ORDER, require
from isolated_bft717j.wire import J, parse, public_key, identity
from isolated_bft717k.authority import StaticTestAuthority
from verification.review717r import wire as w

ZERO = '00' * 32
MAX_MEDIA = 3145728
SIZES = {'OPEN': 530, 'VOTE': 508, 'MESSAGE': 383, 'TIME_SAMPLE': 74,
         'PV': 1150, 'PROOF': 1533, 'CHECKPOINT': 275, 'MEDIA': 862}


@dataclass(frozen=True)
class Result:
    outcome: str
    signatures_valid: bool = False
    test_membership_authenticated: bool = False
    quorum_structure_valid: bool = False
    complete_finalized_history: bool = False
    agreement_execution_verified: bool = False
    physical_time_trusted: bool = False
    identity: str = ''


@dataclass(frozen=True)
class TestPins:
    """LOCAL immutable laboratory pins; never construct from received messages."""
    authority: StaticTestAuthority
    context_fields: tuple
    bootstrap: str

    def __post_init__(self):
        require(type(self.authority) is StaticTestAuthority, 'local_test_authority')
        require(type(self.context_fields) is tuple and
                tuple(k for k, _ in self.context_fields) == tuple(k for k, _ in w.CTX), 'pin_shape')
        c, a = self.context, self.authority.context
        context_bytes(c)
        require(c['network'] == a.network and c['genesis'] == a.genesis_hash and
                c['validators'] == a.C and c['membership'] == 0, 'authority_context')
        w.encode_type(32, self.bootstrap)

    @property
    def context(self):
        return dict(self.context_fields)

    @property
    def origin(self):
        return w.tagged('origin', context_bytes(self.context) + bytes.fromhex(self.bootstrap))

    @property
    def initial_state(self):
        return w.tagged('initial-state', bytes.fromhex(self.origin + self.bootstrap))


def context_bytes(context):
    require(type(context) is dict and set(context) == {k for k, _ in w.CTX}, 'context_shape')
    return b''.join(w.encode_type(t, context[k]) for k, t in w.CTX)


def record(kind, raw):
    require(kind in SIZES and type(raw) is bytes and len(raw) == SIZES[kind], 'record_size')
    return w.unpack(kind, raw)


def json_record(kind, raw):
    """Strict fixture-display adapter, NOT another signed JSON protocol."""
    obj = parse(raw, 8192)  # duplicate keys/depth/noncanonical JSON rejected before encoding
    encoded = w.pack(kind, obj)  # recursive closed schemas, integer/enumeration bounds
    record(kind, encoded)
    return encoded


def check_context(pins, obj):
    require(type(pins) is TestPins, 'local_test_pins')
    require({k: obj[k] for k, _ in w.CTX} == pins.context, 'signing_context')


def preimage(kind, obj, *, context=None, height=None, parent=None, sequence=None):
    """Return the entire input to Keccak256, including EIP-191 ONLY for users."""
    if kind in ('OPEN', 'VOTE'):
        return w.user_preimage(kind, obj)
    if kind == 'MESSAGE':
        return b'ZCRJ717R\x00consensus\x00' + w.pack(kind, obj)[:-65]
    require(kind == 'TIME_SAMPLE', 'signing_purpose')
    return w.time_preimage(context, height, parent, sequence, obj)


def recover(signature, digest, expected_key):
    public_key(expected_key)  # strict finite compressed point, no address-only match
    raw = bytes.fromhex(signature)
    require(len(raw) == 65 and 1 <= int.from_bytes(raw[:32]) < CURVE_ORDER and
            1 <= int.from_bytes(raw[32:64]) <= CURVE_ORDER // 2 and raw[64] in (27, 28),
            'signature_scalar_low_s_v')
    try:
        key = keys.Signature(raw[:64] + bytes([raw[64] - 27])).recover_public_key_from_msg_hash(digest)
    except (BadSignature, ValidationError, ValueError, OverflowError):
        raise ValueError('signature_recovery') from None
    require(key.to_compressed_bytes().hex() == expected_key, 'signature_key')
    return identity(expected_key)[2:]


def verify_user(pins, kind, raw, *, expected):
    require(kind in ('OPEN', 'VOTE'), 'user_purpose')
    obj = record(kind, raw)
    check_context(pins, obj)
    # A caller must pin ALL immutable review/session fields, not an address alone.
    fields = ('submission', 'original', 'creator', 'media_height', 'media_hash',
              'base_height', 'base_hash')
    fields += ('sid', 'deadline', 'dimension') if kind == 'VOTE' else ('eligibility_root', 'inventory')
    require(type(expected) is dict and set(expected) == set(fields), 'expected_binding_shape')
    require(all(obj[k] == expected[k] and type(obj[k]) is type(expected[k]) for k in fields),
            'user_binding')
    wallet = recover(obj['signature'], keccak(preimage(kind, obj)), obj['key'])
    if kind == 'OPEN':
        require(wallet == obj['creator'], 'creator_key')
    return Result('VALID_USER_SIGNATURE_ONLY', signatures_valid=True, identity=wallet)


def user_bindings(kind, obj):
    names = ['submission', 'original', 'creator', 'media_height', 'media_hash', 'base_height', 'base_hash']
    names += ['sid', 'deadline', 'dimension'] if kind == 'VOTE' else ['eligibility_root', 'inventory']
    return {k: obj[k] for k in names}


def member_key(pins, index):
    pub = pins.authority.context.manifest['validator_public_keys'][index]
    pins.authority.resolve_member(identity(pub), pub, epoch=0)
    return pub


def verify_message(pins, raw, *, height, parent, round, step, value, nil=0, pv_bytes=None):
    obj = record('MESSAGE', raw)
    check_context(pins, obj)
    for name, val, typ in [('height', height, 'u64'), ('parent', parent, 32),
                           ('round', round, 'round'), ('step', step, 'step'),
                           ('value', value, 32), ('nil', nil, 'bit')]:
        w.encode_type(typ, val)
        require(obj[name] == val, 'message_' + name)
    require(height >= 1, 'message_height')
    require(height != 1 or parent == pins.origin, 'journal_origin')
    require(not nil or (value == ZERO and step != 0), 'nil_semantics')
    if step == 0:
        require(not nil and obj['validator'] == ((height - 1) % 4 + round % 4) % 4, 'proposer')
        require(obj['valid_round'] == -1 or 0 <= obj['valid_round'] < round, 'valid_round')
        if obj['valid_round'] >= 0:
            require(pv_bytes is not None, 'INCOMPLETE_HISTORY: missing_prevote_certificate')
            require(w.tagged('pv', pv_bytes) == obj['justification'], 'pv_commitment')
            verify_pv(pins, pv_bytes, height=height, parent=parent, round=obj['valid_round'],
                      value=value, nil=0)
        else:
            require(obj['justification'] == ZERO, 'unexpected_justification')
    else:
        require(obj['valid_round'] == -1 and obj['justification'] == ZERO, 'vote_justification')
    pub = member_key(pins, obj['validator'])
    wallet = recover(obj['signature'], keccak(preimage('MESSAGE', obj)), pub)
    return Result('VALID_MESSAGE_ONLY', True, True, identity=wallet)


def _votes(pins, votes, *, height, parent, round, value, step, nil):
    ids = [v['validator'] for v in votes]
    require(ids == sorted(set(ids)) and len(ids) == 3, 'duplicate_contradictory_or_unsorted_signers')
    for obj in votes:
        verify_message(pins, w.pack('MESSAGE', obj), height=height, parent=parent,
                       round=round, value=value, step=step, nil=nil)


def verify_pv(pins, raw, *, height, parent, round, value, nil=0):
    pv = record('PV', raw)
    _votes(pins, pv['votes'], height=height, parent=parent, round=round, value=value, step=1, nil=nil)
    return Result('VALID_QUORUM_STRUCTURE_ONLY', True, True, True)


def verify_proof(pins, raw, *, batch_bytes, height, parent, round, pv_bytes=None):
    # Proposal MESSAGE is mandatory in the exact PROOF grammar, as is its full body.
    proof = record('PROOF', raw)
    require(batch_bytes is not None, 'INCOMPLETE_HISTORY: missing_proposal_bytes')
    header, events = w.parse_body(batch_bytes)
    check_context(pins, header)
    require(header['height'] == height and header['parent'] == parent, 'batch_height_parent')
    value = w.tagged('batch', batch_bytes)
    verify_message(pins, w.pack('MESSAGE', proof['proposal']), height=height, parent=parent,
                   round=round, value=value, step=0, pv_bytes=pv_bytes)
    _votes(pins, proof['precommits'], height=height, parent=parent, round=round,
           value=value, step=2, nil=0)
    return Result('VALID_QUORUM_STRUCTURE_ONLY', True, True, True)


def verify_clock(pins, header):
    check_context(pins, header)
    clock = header['clock']
    w.pack('CLOCK', clock)
    require(clock['sequence'] == header['height'], 'clock_sequence')
    ids = [s['validator'] for s in clock['samples']]
    require(ids == sorted(set(ids)) and len(ids) == 3, 'clock_signers')
    for sample in clock['samples']:
        pre = preimage('TIME_SAMPLE', sample, context=pins.context, height=header['height'],
                       parent=header['parent'], sequence=clock['sequence'])
        recover(sample['signature'], keccak(pre), member_key(pins, sample['validator']))
    return Result('VALID_TIME_SIGNATURES_ONLY', True, True)


def verify_checkpoint(pins, raw, *, batch_bytes, proof_bytes, round=0):
    cp = record('CHECKPOINT', raw)
    check_context(pins, cp)
    require(batch_bytes is not None and proof_bytes is not None, 'INCOMPLETE_HISTORY: checkpoint_evidence')
    header, _ = w.parse_body(batch_bytes)
    require(cp['batch'] == w.tagged('batch', batch_bytes) and
            cp['proof'] == w.tagged('proof', proof_bytes) and cp['height'] == header['height'],
            'checkpoint_commitment')
    verify_proof(pins, proof_bytes, batch_bytes=batch_bytes, height=cp['height'],
                 parent=header['parent'], round=round)
    return Result('VALID_CHECKPOINT_COMMITMENT_ONLY', True, True, True)
