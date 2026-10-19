"""Private, bounded binary IPC for the offline decoder worker; never pickle."""
from __future__ import annotations

import json
import re
import struct

MAX_OUTPUT = 2 * 1024 * 1024
MAX_REQUEST = 4 * ((MAX_OUTPUT + 2) // 3) + 2048
MAX_HEADER = 1024
PREFIX = struct.Struct("!4sII")
MAGIC = b"ZCW1"
ID = re.compile(r"[0-9a-f]{32}\Z")
DIGEST = re.compile(r"[0-9a-f]{64}\Z")


class IPCError(ValueError):
    pass


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def read_exact(stream, size):
    # The caller checks the length BEFORE this allocation. No growing read().
    data = bytearray(size)
    target = memoryview(data)
    offset = 0
    while offset < size:
        count = stream.readinto(target[offset:])
        if not count:
            raise IPCError("truncated")
        offset += count
    return bytes(data)


def read_message(stream, max_body):
    magic, header_size, body_size = PREFIX.unpack(read_exact(stream, PREFIX.size))
    if magic != MAGIC or not 1 <= header_size <= MAX_HEADER or body_size > max_body:
        raise IPCError("message_size_or_magic")
    raw = read_exact(stream, header_size)
    # Metadata is flat and small, so nesting and pathological JSON never reach
    # the JSON parser. Require exact scalar types at each protocol boundary.
    if any(c in raw[1:-1] for c in (b"[", b"]", b"\\", b"{", b"}")):
        raise IPCError("metadata_shape")
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise IPCError("duplicate_metadata_key")
            result[key] = value
        return result
    try:
        meta = json.loads(raw.decode("ascii"), object_pairs_hook=pairs)
        if type(meta) is not dict or any(type(v) not in (str, int) for v in meta.values()):
            raise IPCError("metadata_shape")
        if canonical(meta) != raw:
            raise IPCError("noncanonical_metadata")
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise IPCError("metadata_json") from exc
    return meta, read_exact(stream, body_size)


def write_message(stream, meta, body=b"", max_body=MAX_OUTPUT):
    header = canonical(meta)
    if not 1 <= len(header) <= MAX_HEADER or len(body) > max_body:
        raise IPCError("message_size")
    # Write-all works with raw pipes and does not concatenate/copy body+header.
    for part in (PREFIX.pack(MAGIC, len(header), len(body)), header, body):
        remaining = memoryview(part)
        while remaining:
            count = stream.write(remaining)
            if not count:
                raise IPCError("broken_pipe")
            remaining = remaining[count:]
    stream.flush()


def request_identity(meta):
    if (set(meta) != {"v", "kind", "id", "request_sha256"}
            or type(meta["v"]) is not int or meta["v"] != 1 or meta["kind"] != "request"
            or type(meta["id"]) is not str or not ID.fullmatch(meta["id"])
            or type(meta["request_sha256"]) is not str or not DIGEST.fullmatch(meta["request_sha256"])):
        raise IPCError("request_metadata")


def result_header(request, status, **fields):
    return dict(v=1, kind="result", id=request["id"],
                request_sha256=request["request_sha256"], status=status, **fields)
