"""Closed R717 laboratory binary grammar. No crypto signing or consensus.

Hex strings represent exact raw bytes, never ASCII hex on wire. Field order is
normative. Decoding is bounded and re-encoding must reproduce received bytes.
Semantic authority, finite EC points and signature recovery remain separate gates.
"""
from hashlib import sha256
import re
import struct

CAP = 262144
EVENT_CAP = 8192
MAX_EVENTS = 256
CTX = [('network', 'nid'), ('genesis', 32), ('protocol', 'v1'),
       ('instance', 32), ('validators', 32), ('membership', 'zero64'), ('policy', 32)]
TALLY = [(k, 'u64') for k in ('positive', 'negative', 'unsure', 'established',
                             'total', 'decisive', 'numerator', 'denominator')] + [('outcome', 'outcome')]
SCHEMAS = {
    'OPEN': CTX + [('submission', 16), ('original', 32), ('creator', 20), ('key', 33),
        ('media_height', 'u64'), ('media_hash', 32), ('base_height', 'u64'), ('base_hash', 32),
        ('eligibility_root', 32), ('inventory', 32), ('nonce', 16), ('attempt', 'zero8'), ('signature', 65)],
    'START': [('sid', 32), ('open_height', 'u64'), ('deadline', 'u64'), ('time_id', 32)],
    'VOTE': CTX + [('sid', 32), ('submission', 16), ('original', 32), ('creator', 20),
        ('key', 33), ('media_height', 'u64'), ('media_hash', 32), ('base_height', 'u64'),
        ('base_hash', 32), ('deadline', 'u64'), ('dimension', 'dimension'), ('choice', 'choice'),
        ('nonce', 16), ('sequence', 'zero8'), ('signature', 65)],
    'ADMISSION': [('vote', 'VOTE'), ('result', 'result'), ('first_height', 'u64'),
        ('first_index', 'u16'), ('status', 'status'), ('charged_epoch', 'u64')],
    'CLOSE': [('sid', 32), ('deadline', 'u64'), ('freeze_height', 'u64'), ('count', 'u64'),
        ('fold', 32), ('originality', 'TALLY'), ('admissibility', 'TALLY'), ('outcome', 'outcome')],
    'PARTICIPATION': [('wallet', 20), ('submission', 16), ('epoch', 'u64'), ('status', 'status'),
        ('first_height', 'u64'), ('first_index', 'u16'), ('used_after', 'u8'), ('cause', 32)],
    'EPOCH': [('previous', 'u64'), ('current', 'u64'), ('lower', 'u64'), ('time_id', 32)],
    # Only frozen policies: an attempted transition is explicitly unsupported.
    'POLICY': [('old', 32), ('new', 32), ('result', 'unsupported')],
    'DATA': [('object_id', 32), ('total', 'u32'), ('offset', 'u32'), ('chunk', 'chunk')],
    'REFERENCE': [('kind', 'sourcekind'), ('object_id', 32), ('length', 'u32'),
        ('height', 'u64'), ('batch', 32), ('index', 'u16')],
    'TIME_SAMPLE': [('validator', 'validator'), ('reading', 'u64'), ('signature', 65)],
    'CLOCK': [('sequence', 'u64'), ('samples', ('array', 'TIME_SAMPLE', 3, 3))],
    'HEADER': CTX + [('height', 'u64'), ('parent', 32), ('previous_state', 32),
        ('events_root', 32), ('event_count', 'u16'), ('event_bytes', 'u32'), ('clock', 'CLOCK')],
    'MESSAGE': CTX + [('height', 'u64'), ('parent', 32), ('round', 'round'), ('value', 32),
        ('nil', 'bit'), ('step', 'step'), ('validator', 'validator'), ('valid_round', 'vr'),
        ('justification', 32), ('signature', 65)],
    'PV': [('votes', ('array', 'MESSAGE', 3, 3))],
    'PROOF': [('proposal', 'MESSAGE'), ('precommits', ('array', 'MESSAGE', 3, 3))],
    'CHECKPOINT': CTX + [('height', 'u64'), ('batch', 32), ('proof', 32)],
    'MEDIA': CTX + [('checkpoint', 'CHECKPOINT'), ('sid', 32), ('close_height', 'u64'),
        ('close_batch', 32), ('close_index', 'u16'), ('close_id', 32), ('submission', 16),
        ('original', 32), ('creator', 20), ('media_height', 'u64'), ('media_parent', 32),
        ('count', 'u64'), ('fold', 32), ('originality', 'TALLY'), ('admissibility', 'TALLY')],
    'TALLY': TALLY,
    'MEDIA_ANCHOR': [('height', 'u64'), ('media_hash', 32), ('parent', 32), ('proof', 32)],
    'INVENTORY': [('entries', ('array', 'REFERENCE', 1, 32))],
}
KINDS = {name: i + 1 for i, name in enumerate(SCHEMAS)}
ENUM = {'v1': (2, 1, 1), 'zero64': (8, 0, 0), 'zero8': (1, 0, 0),
        'dimension': (1, 0, 1), 'choice': (1, 0, 2), 'outcome': (1, 0, 2),
        'status': (1, 0, 2), 'result': (1, 0, 9), 'unsupported': (1, 255, 255),
        'sourcekind': (1, 0, 6), 'validator': (1, 0, 3), 'step': (1, 0, 2),
        'bit': (1, 0, 1), 'round': (4, 0, 2147483647), 'vr': (4, -1, 2147483647),
        **{f'u{w}': (w // 8, 0, min(2 ** w - 1, 9007199254740991)) for w in (8, 16, 32, 64)}}


def hash_bytes(raw):
    return sha256(raw).hexdigest()


def tagged(tag, raw):
    return hash_bytes(b'ZCRJ717R\x00' + tag.encode('ascii') + b'\x00' + raw)


def encode_type(t, value):
    if isinstance(t, int):
        if type(value) is not str or not re.fullmatch('[0-9a-f]{%d}' % (2*t), value):
            raise ValueError('raw width/case')
        return bytes.fromhex(value)
    if isinstance(t, tuple):
        _, name, lo, hi = t
        if type(value) is not list or not lo <= len(value) <= hi:
            raise ValueError('array bound')
        return bytes([len(value)]) + b''.join(pack(name, x) for x in value)
    if t in SCHEMAS:
        return pack(t, value)
    if t == 'nid':
        if type(value) is not str or not re.fullmatch('[a-z0-9][a-z0-9-]{2,63}', value):
            raise ValueError('network')
        raw = value.encode('ascii')
        return bytes([len(raw)]) + raw + bytes(64-len(raw))
    if t == 'chunk':
        if type(value) is not str or not re.fullmatch('(?:[0-9a-f]{2}){1,8140}', value):
            raise ValueError('chunk bound')
        raw = bytes.fromhex(value)
        return struct.pack('>H', len(raw)) + raw
    width, lo, hi = ENUM[t]
    if type(value) is not int or not lo <= value <= hi:
        raise ValueError('integer/enum bound ' + t)
    return value.to_bytes(width, 'big', signed=t == 'vr')


def pack(name, obj):
    if type(obj) is not dict or set(obj) != {k for k, _ in SCHEMAS[name]}:
        raise ValueError('closed shape ' + name)
    return b''.join(encode_type(t, obj[k]) for k, t in SCHEMAS[name])


def unpack(name, raw):
    if type(raw) is not bytes or len(raw) > CAP:
        raise ValueError('raw bound')
    pos = 0

    def take(n):
        nonlocal pos
        if pos + n > len(raw):
            raise ValueError('truncated')
        b = raw[pos:pos+n]
        pos += n
        return b

    def read(t):
        if isinstance(t, int):
            return take(t).hex()
        if isinstance(t, tuple):
            _, child, lo, hi = t
            n = take(1)[0]
            if not lo <= n <= hi:
                raise ValueError('array bound')
            return [read(child) for _ in range(n)]
        if t in SCHEMAS:
            return {k: read(v) for k, v in SCHEMAS[t]}
        if t == 'nid':
            n, block = take(1)[0], take(64)
            if not 3 <= n <= 64 or any(block[n:]):
                raise ValueError('network padding')
            return block[:n].decode('ascii')
        if t == 'chunk':
            n = int.from_bytes(take(2), 'big')
            if not 1 <= n <= 8140:
                raise ValueError('chunk bound')
            return take(n).hex()
        return int.from_bytes(take(ENUM[t][0]), 'big', signed=t == 'vr')

    obj = read(name)
    if pos != len(raw) or pack(name, obj) != raw:
        raise ValueError('trailing/noncanonical')
    return obj


def frame(name, obj):
    raw = pack(name, obj)
    if len(raw) > EVENT_CAP:
        raise ValueError('event cap')
    return struct.pack('>BHI', KINDS[name], 1, len(raw)) + raw


def unframe(raw):
    if len(raw) < 7:
        raise ValueError('truncated frame')
    kind, version, size = struct.unpack('>BHI', raw[:7])
    names = {v: k for k, v in KINDS.items()}
    if version != 1 or kind not in names or size > EVENT_CAP or size != len(raw)-7:
        raise ValueError('frame version/kind/size')
    return names[kind], unpack(names[kind], raw[7:])


def body(header, events):
    if len(events) > MAX_EVENTS:
        raise ValueError('event count')
    frames = b''.join(frame(k, v) for k, v in events)
    h = dict(header)
    h.update(events_root=tagged('events', frames), event_count=len(events), event_bytes=len(frames))
    encoded = pack('HEADER', h)
    raw = b'R717B001' + struct.pack('>HH', 1, len(encoded)) + encoded + frames
    if len(raw) > CAP:
        raise ValueError('batch cap')
    return raw


def parse_body(raw):
    if type(raw) is not bytes or not 12 <= len(raw) <= CAP or raw[:8] != b'R717B001':
        raise ValueError('batch cap/magic')
    version, length = struct.unpack('>HH', raw[8:12])
    if version != 1:
        raise ValueError('batch version')
    h = unpack('HEADER', raw[12:12+length])
    pos, events = 12+length, []
    if h['event_count'] > MAX_EVENTS or h['event_bytes'] != len(raw)-pos:
        raise ValueError('batch count/length')
    if h['events_root'] != tagged('events', raw[pos:]):
        raise ValueError('events root')
    for _ in range(h['event_count']):
        if pos+7 > len(raw):
            raise ValueError('truncated event')
        size = int.from_bytes(raw[pos+3:pos+7], 'big')
        if size > EVENT_CAP:
            raise ValueError('event cap')
        events.append(unframe(raw[pos:pos+7+size]))
        pos += 7+size
    if pos != len(raw) or body(h, events) != raw:
        raise ValueError('batch trailing/noncanonical')
    return h, events


def preflight_work(events):
    # Every attempted user vote, including duplicates/rejections, consumes work.
    votes = sum(k == 'ADMISSION' for k, _ in events)
    controls = sum(k == 'OPEN' for k, _ in events)
    if votes > 96 or controls > 16 or votes+controls > 160:
        raise ValueError('work budget')
    if sum(k == 'CLOSE' for k, _ in events) > 16 or sum(k == 'START' for k, _ in events) > 16:
        raise ValueError('mandatory lane')
    # DATA pages do not authorize opaque external work; source length/count,
    # policy support and incremental state operations need separate validation.
    return dict(vote_checks=votes, control_checks=controls, time_checks=3, finality_checks=4)


def user_preimage(kind, obj):
    if kind not in ('OPEN', 'VOTE'):
        raise ValueError('user purpose')
    # Signature field is last, so no zero/placeholder signature enters preimage.
    msg = b'ZCRJ717R\x00user-' + kind.encode('ascii') + b'\x00' + pack(kind, obj)[:-65]
    return b'\x19Ethereum Signed Message:\n' + str(len(msg)).encode('ascii') + msg


def time_preimage(context, height, parent, sequence, sample):
    raw = b''.join(encode_type(t, context[k]) for k, t in CTX)
    raw += encode_type('u64', height) + encode_type(32, parent) + encode_type('u64', sequence)
    raw += pack('TIME_SAMPLE', sample)[:-65]
    return b'ZCRJ717R\x00time\x00' + raw
