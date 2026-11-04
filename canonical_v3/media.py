"""Descriptor production and reconstruction through the existing isolated worker.

The worker is an offline resource-controlled prototype, not a production sandbox
approval. Image MIME/container safety remains a separate admission boundary.
"""
import base64
import binascii
from dataclasses import dataclass
import hashlib

from codec_prototype.isolated_decoder import IsolatedDecoder, Outcome, Status
from .primitives import V3Error, EDGE_SPACE, canonical, closed, h64, require, uint

MAX_IMAGE = MAX_ENCODED = 2097152
MAX_TEXT = 262144
MIMES = ('text/plain', 'image/jpeg', 'image/png', 'image/gif', 'image/webp')
FIELDS = 'codec_id codec_version encoding_version mime_type original_sha256 original_size payload stored_size'


def validate_descriptor(value):
    closed(value, FIELDS)
    require(type(value['codec_id']) is str and value['codec_id'] in ('identity', 'zstd'), 'codec_profile')
    uint(value['codec_version'], 1, 1)
    uint(value['encoding_version'], 1, 1)
    require(type(value['mime_type']) is str and value['mime_type'] in MIMES, 'mime_type')
    uint(value['original_size'], 1, MAX_TEXT if value['mime_type'] == 'text/plain' else MAX_IMAGE)
    uint(value['stored_size'], 1, MAX_ENCODED)
    h64(value['original_sha256'])
    payload = value['payload']
    require(type(payload) is str and len(payload) == 4 * ((value['stored_size'] + 2) // 3), 'base64_length')
    try:
        encoded = base64.b64decode(payload, validate=True)
    except (ValueError, binascii.Error):
        raise V3Error('base64_syntax') from None
    require(len(encoded) == value['stored_size'] and
            base64.b64encode(encoded).decode('ascii') == payload, 'base64_noncanonical')
    if value['codec_id'] == 'identity':
        require(value['stored_size'] == value['original_size'], 'identity_size')
    return encoded


def canonical_text(original):
    try:
        value = original.decode('utf-8')
    except UnicodeError:
        raise V3Error('text_utf8') from None
    require(value and value.replace('\r\n', '\n').replace('\r', '\n').strip(EDGE_SPACE) == value, 'text_noncanonical')
    require(not any((ord(c) < 32 and c not in '\t\n\r') or 127 <= ord(c) <= 159 for c in value), 'text_control')


def reconstruct(value, *, decoder=None):
    """VALID means codec/hash/canonical-text validity, not image safety/admission."""
    try:
        validate_descriptor(value)
        raw = canonical(value)
    except V3Error as exc:
        return Outcome(Status.INVALID, stage='v3_descriptor', code=exc.code)
    if decoder is None:
        with IsolatedDecoder() as worker:
            result = worker.validate(raw)
    else:
        require(isinstance(decoder, IsolatedDecoder), 'isolated_decoder_required')
        result = decoder.validate(raw)
    if result.status != Status.VALID:
        return result
    original = result.original
    # The coordinator already checks these; keep the format boundary explicit.
    if type(original) is not bytes or len(original) != value['original_size'] or hashlib.sha256(original).hexdigest() != value['original_sha256']:
        return Outcome(Status.INDETERMINATE_LOCAL_FAILURE, reason='coordinator_output_mismatch')
    if value['mime_type'] == 'text/plain':
        try:
            canonical_text(original)
        except V3Error as exc:
            return Outcome(Status.INVALID, stage='v3_text', code=exc.code)
    return result


def descriptor(original, encoded, mime, codec):
    value = dict(codec_id=codec, codec_version=1, encoding_version=1,
                 mime_type=mime, original_sha256=hashlib.sha256(original).hexdigest(),
                 original_size=len(original), payload=base64.b64encode(encoded).decode('ascii'),
                 stored_size=len(encoded))
    validate_descriptor(value)
    return value


@dataclass(frozen=True)
class ProducedMedia:
    descriptor: dict | None
    outcome: Outcome


def _compress_default(original):
    try:
        import zstandard as zstd
    except ImportError:
        return None  # Producer-only inability to encode; identity still verified.
    try:
        parameters = zstd.ZstdCompressionParameters.from_level(
            3, window_log=18, write_checksum=1, write_content_size=1, write_dict_id=0, threads=0)
        return zstd.ZstdCompressor(compression_params=parameters).compress(original)
    except zstd.ZstdError:
        return None


def produce(original, mime, *, decoder=None):
    require(type(original) is bytes and type(mime) is str and mime in MIMES, 'media_input')
    require(1 <= len(original) <= (MAX_TEXT if mime == 'text/plain' else MAX_IMAGE), 'original_size')
    if mime == 'text/plain':
        canonical_text(original)
    identity = descriptor(original, original, mime, 'identity')
    encoded = _compress_default(original)
    selected = identity
    if encoded is not None and 1 <= len(encoded) <= MAX_ENCODED:
        compressed = descriptor(original, encoded, mime, 'zstd')
        if len(canonical(compressed)) < len(canonical(identity)):
            selected = compressed
    result = reconstruct(selected, decoder=decoder)
    if result.status == Status.INVALID and selected['codec_id'] == 'zstd':
        # Local producer selection only: never repair/re-encode a received block.
        # A local worker failure is deliberately NOT retried or masked here.
        selected = identity
        result = reconstruct(identity, decoder=decoder)
    return ProducedMedia(selected if result.status == Status.VALID else None, result)
