"""Strict JSON and the frozen Task 7.10A/B scalar domains."""
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
from math import gcd
import re

MAX_UINT = 9007199254740991
MAX_RECORD = 3145728
MAX_DEPTH = 32
CURVE_ORDER = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
EDGE_SPACE = ''.join(chr(n) for n in (
    *range(9, 14), *range(28, 33), 0x85, 0xa0, 0x1680,
    *range(0x2000, 0x200b), 0x2028, 0x2029, 0x202f, 0x205f, 0x3000))


class V3Error(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def require(ok, code):
    if not ok:
        raise V3Error(code)


def closed(value, required, optional=()):
    require(type(value) is dict, 'object_type')
    keys = set(required.split() if type(required) is str else required)
    require(keys <= value.keys() <= keys | set(optional), 'object_keys')


def uint(value, low=0, high=MAX_UINT):
    require(type(value) is int and low <= value <= high, 'integer_range')
    return value


def text(value, scalars, octets, *, empty=False):
    require(type(value) is str and (empty or bool(value)) and len(value) <= scalars, 'string_length')
    try:
        require(len(value.encode('utf-8')) <= octets, 'string_bytes')
    except UnicodeError:
        raise V3Error('unicode_scalar') from None
    return value


def pattern(value, regex):
    require(type(value) is str and re.fullmatch(regex, value, flags=re.ASCII) is not None, 'string_grammar')
    return value


def h64(value):
    return pattern(value, r'[0-9a-f]{64}')


def wallet(value):
    return pattern(value, r'0x[0-9a-f]{40}')


def nonce(value):
    pattern(value, r'[1-9][0-9]{0,15}')
    require(int(value) <= MAX_UINT, 'nonce_range')


def opaque(value):
    pattern(value, r'[A-Za-z0-9_-]{1,256}')


def decimal_units(value, *, positive=False, maximum=None):
    text(value, 32, 32)
    pattern(value, r'(0|[1-9][0-9]*)(\.[0-9]{0,5}[1-9])?')
    whole, _, fraction = value.partition('.')
    units = int(whole) * 1000000 + int((fraction + '000000')[:6])
    require((units > 0 if positive else units >= 0) and
            (maximum is None or units <= maximum), 'decimal_range')
    return units


def seconds(value):
    decimal_units(value, maximum=MAX_UINT * 1000000 + 999999)


def time_utc(value):
    text(value, 32, 32)
    pattern(value, r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]{0,5}[1-9])?\+00:00')
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        raise V3Error('calendar_time') from None


def expiry(issued, expires):
    require(time_utc(expires) > time_utc(issued), 'expiry_order')


def signature(value):
    pattern(value, r'0x[0-9a-f]{130}')
    raw = bytes.fromhex(value[2:])
    require(1 <= int.from_bytes(raw[:32]) < CURVE_ORDER and
            1 <= int.from_bytes(raw[32:64]) < CURVE_ORDER and raw[64] in (27, 28), 'signature_scalar')


def verify_signature(message, sig, expected):
    signature(sig)
    wallet(expected)
    from eth_account import Account
    from eth_account.messages import encode_defunct
    from eth_keys.exceptions import BadSignature
    from eth_utils import ValidationError
    try:
        recovered = Account.recover_message(encode_defunct(primitive=message), signature=sig)
    except (ValueError, TypeError, OverflowError, BadSignature, ValidationError):
        raise V3Error('signature_recovery') from None
    require(recovered.lower() == expected, 'signature_signer')


def _json_value(value, depth=0):
    if type(value) in (dict, list):
        require(depth < MAX_DEPTH, 'json_depth')
        if type(value) is dict:
            for key, child in value.items():
                require(type(key) is str, 'json_key')
                text(key, MAX_RECORD, MAX_RECORD, empty=True)
                _json_value(child, depth + 1)
        else:
            for child in value:
                _json_value(child, depth + 1)
    elif type(value) is str:
        text(value, MAX_RECORD, MAX_RECORD, empty=True)
    elif type(value) is int:
        require(-MAX_UINT <= value <= MAX_UINT, 'json_integer')
    else:
        require(value is None or type(value) is bool, 'json_type')


def canonical(value, *, ascii_only=False):
    _json_value(value)
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=ascii_only, allow_nan=False).encode('utf-8')


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def without_digest(value, key):
    h64(value[key])
    require(value[key] == digest({k: v for k, v in value.items() if k != key}), 'digest_mismatch')


def bounded(value, limit):
    require(len(canonical(value)) <= limit, 'component_size')


def parse(raw, *, limit=MAX_RECORD):
    require(type(raw) is bytes and len(raw) <= limit, 'json_size')
    # Bound nesting before the JSON parser allocates a container tree.
    quoted = escaped = False
    depth = 0
    for byte in raw:
        if quoted:
            if escaped:
                escaped = False
            elif byte == 92:
                escaped = True
            elif byte == 34:
                quoted = False
        elif byte == 34:
            quoted = True
        elif byte in (91, 123):
            depth += 1
            require(depth <= MAX_DEPTH, 'json_depth')
        elif byte in (93, 125):
            depth -= 1

    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'duplicate_key')
            result[key] = value
        return result

    def integer(token):
        require(len(token) <= 17 and token != '-0', 'json_integer')
        result = int(token)
        require(-MAX_UINT <= result <= MAX_UINT, 'json_integer')
        return result

    def forbidden(_):
        raise V3Error('json_number')

    try:
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=pairs,
                           parse_int=integer, parse_float=forbidden, parse_constant=forbidden)
    except (UnicodeError, ValueError, RecursionError) as exc:
        if isinstance(exc, V3Error):
            raise
        raise V3Error('json_syntax') from None
    require(canonical(value) == raw, 'noncanonical_json')
    return value


@dataclass(frozen=True)
class Context:
    network_id: str
    application: str
    genesis_hash: str
    media_policy_digest: str
    review_policy_digest: str

    def __post_init__(self):
        pattern(self.network_id, r'[a-z0-9][a-z0-9-]{2,63}')
        pattern(self.application, r'[A-Za-z0-9][A-Za-z0-9_.-]{2,63}')
        for value in (self.genesis_hash, self.media_policy_digest, self.review_policy_digest):
            h64(value)

    @property
    def media_policy_id(self):
        return self.network_id + '/media-admission/2'


def envelope(payload, purpose, ctx):
    require(purpose in ('block', 'native-transfer', 'submitter-attestation', 'finality-attestation'), 'purpose')
    return dict(domain='zoidbergchain/' + purpose + '/v2', network_id=ctx.network_id,
                object_type=purpose, payload=payload, protocol='zoidbergchain', protocol_version=2)


def rational(positive, decisive):
    uint(positive, 0, 16)
    uint(decisive, 0, 16)
    require(positive <= decisive, 'ratio_counts')
    require(decisive > 0, 'undefined_ratio')
    divisor = gcd(positive, decisive)
    return dict(numerator=positive // divisor, denominator=decisive // divisor)


def validate_rational(value):
    closed(value, 'numerator denominator')
    n, d = uint(value['numerator'], 0, 15), uint(value['denominator'], 1, 16)
    require(n <= d and gcd(n, d) == 1, 'noncanonical_ratio')


def compare_ratios(left, right):
    validate_rational(left)
    validate_rational(right)
    difference = left['numerator'] * right['denominator'] - right['numerator'] * left['denominator']
    return (difference > 0) - (difference < 0)
