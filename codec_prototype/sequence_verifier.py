"""Bounded zstd/1 sequence verification, not a media decompressor.

Implements the sequence grammar in Zstandard format 0.4.3 (zstd v1.5.7).
Skips Huffman payloads; never reconstructs literals or executes match copies.
libzstd remains responsible for full decoding, Huffman validity and checksum.
New security-sensitive prototype code: independent review is still required.
"""
from dataclasses import dataclass


class VerificationReject(ValueError):
    pass


def invalid(code="invalid_stream"):
    raise VerificationReject(code)


LL_BITS = (0,) * 16 + (1, 1, 1, 1, 2, 2, 3, 3, 4, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16)
ML_BITS = (0,) * 32 + (1, 1, 1, 1, 2, 2, 3, 3, 4, 4, 5, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16)


def baselines(widths, start):
    result = []
    for width in widths:
        result.append(start)
        start += 1 << width
    return tuple(result)


LL_BASE, ML_BASE = baselines(LL_BITS, 0), baselines(ML_BITS, 3)
LL_NORM = (4, 3) + (2,) * 11 + (1,) * 3 + (2,) * 9 + (3, 2) + (1,) * 5 + (-1,) * 4
ML_NORM = (1, 4, 3) + (2,) * 6 + (1,) * 37 + (-1,) * 7
OF_NORM = (1,) * 6 + (2,) * 3 + (1,) * 15 + (-1,) * 5


@dataclass(frozen=True)
class Table:
    log: int
    rows: tuple  # (symbol, next-state bit width, next-state baseline)


def build_table(norm, log):
    """At most 512 rows; spread traversal visits at most one full permutation."""
    size = 1 << log
    if not 5 <= log <= 9 or sum(abs(n) for n in norm) != size or sum(n != 0 for n in norm) < 2:
        invalid()
    symbols, following = [-1] * size, []
    high = size - 1
    for symbol, count in enumerate(norm):
        if count < -1:
            invalid()
        following.append(1 if count == -1 else count)
        if count == -1:
            symbols[high] = symbol
            high -= 1
    position = steps = 0
    step = (size >> 1) + (size >> 3) + 3
    for symbol, count in enumerate(norm):
        for _ in range(max(0, count)):
            symbols[position] = symbol
            position = (position + step) & (size - 1)
            steps += 1
            while position > high:
                position = (position + step) & (size - 1)
                steps += 1
                if steps > size:
                    invalid()
    if position != 0:
        invalid()
    rows = []
    for symbol in symbols:
        if symbol < 0 or following[symbol] == 0:
            invalid()
        state = following[symbol]
        following[symbol] += 1
        width = log - (state.bit_length() - 1)
        rows.append((symbol, width, (state << width) - size))
    return Table(log, tuple(rows))


DEFAULTS = (build_table(LL_NORM, 6), build_table(OF_NORM, 5), build_table(ML_NORM, 6))


class ForwardBits:
    def __init__(self, data, offset):
        self.data, self.bit = data, offset * 8

    def peek(self, width):
        if self.bit + width > len(self.data) * 8:
            invalid()
        start = self.bit // 8
        return (int.from_bytes(self.data[start:start + 3], "little") >> (self.bit % 8)) & ((1 << width) - 1)

    def read(self, width):
        value = self.peek(width)
        self.bit += width
        return value


class ReverseBits:
    def __init__(self, data):
        if not data or data[-1] == 0:
            invalid()
        self.data = data
        self.bit = (len(data) - 1) * 8 + data[-1].bit_length() - 1

    def read(self, width):
        if not 0 <= width <= 31 or width > self.bit:
            invalid()
        self.bit -= width
        start = self.bit // 8
        # At most five bytes / 31 bits per operation. Never build a frame-sized int.
        return (int.from_bytes(self.data[start:start + 5], "little") >> (self.bit % 8)) & ((1 << width) - 1)


def read_table(data, offset, max_symbol, max_log):
    bits = ForwardBits(data, offset)
    log = bits.read(4) + 5
    if log > max_log:
        invalid()
    remaining, threshold, width = (1 << log) + 1, 1 << log, log + 1
    norm = []
    zero = False
    while remaining > 1:
        if zero:
            while True:
                run = bits.read(2)
                if len(norm) + run > max_symbol:
                    invalid()
                norm.extend([0] * run)
                if run != 3:
                    break
        if len(norm) > max_symbol:
            invalid()
        small = 2 * threshold - 1 - remaining
        if bits.peek(width - 1) < small:
            count = bits.read(width - 1)
        else:
            count = bits.read(width)
            if count >= threshold:
                count -= small
        count -= 1
        remaining -= abs(count)
        if remaining < 1:
            invalid()
        norm.append(count)
        zero = count == 0
        while remaining < threshold:
            threshold >>= 1
            width -= 1
    norm.extend([0] * (max_symbol + 1 - len(norm)))
    return build_table(norm, log), (bits.bit + 7) // 8


@dataclass(frozen=True)
class WorkStats:
    blocks: int
    compressed_blocks: int
    sequences: int
    literal_bytes: int
    raw_rle_bytes: int
    decoded_bytes: int
    fse_tables: int
    fse_cells: int
    max_offset: int
    sequence_bits: int
    block_output_sizes: tuple[int, ...]


def literals_header(body):
    """Return literal count and sequence-section offset; no Huffman decoding."""
    if not body:
        invalid()
    kind, fmt = body[0] & 3, (body[0] >> 2) & 3
    if kind <= 1:
        width = 1 if fmt in (0, 2) else (2 if fmt == 1 else 3)
        if len(body) < width:
            invalid()
        value = int.from_bytes(body[:width], "little")
        size = value >> (3 if width == 1 else 4)
        end = width + (size if kind == 0 else 1)
    else:
        width = 3 if fmt < 2 else fmt + 2
        if len(body) < width:
            invalid()
        value = int.from_bytes(body[:width], "little") >> 4
        count_bits = (10, 10, 14, 18)[fmt]
        size = value & ((1 << count_bits) - 1)
        compressed = value >> count_bits
        if compressed == 0 or (fmt and (size < 6 or compressed < 10)):
            invalid()
        end = width + compressed
    if end >= len(body):  # At least the sequence-count byte remains.
        invalid()
    return size, end


def verify_sequences(encoded, info):
    """Consume preflighted framing; verify every sequence distance and output count.

    The fixed A/B/W/block grammar bounds all loops and table allocations. Header
    sequence counts are rejected against remaining output BEFORE sequence loops.
    Tables and repeat offsets persist across blocks only within this one call.
    """
    if not (1 <= info.content_size <= 2097152 and 1 <= len(encoded) <= 2097152
            and 1 <= info.window <= 262144 and 1 <= info.block_count <= 64):
        invalid()
    tables = [None, None, None]
    repeats = [1, 4, 8]
    offset = info.header_size
    produced = sequences = literals = raw_rle = compressed_blocks = table_count = cells = max_offset = sequence_bits = 0
    block_outputs = []
    for _ in range(info.block_count):
        header = int.from_bytes(encoded[offset:offset + 3], "little")
        kind, size = (header >> 1) & 3, header >> 3
        offset += 3
        body = memoryview(encoded)[offset:offset + (1 if kind == 1 else size)]
        offset += len(body)
        block_max = min(info.window, 131072, info.content_size - produced)
        if kind in (0, 1):
            if size > block_max:
                invalid()
            produced += size
            raw_rle += size
            block_outputs.append(size)
            continue
        if kind != 2:
            invalid()
        compressed_blocks += 1
        literal_count, cursor = literals_header(body)
        first = body[cursor]
        cursor += 1
        if first < 128:
            count = first
        elif first < 255:
            if cursor >= len(body):
                invalid()
            count = ((first - 128) << 8) + body[cursor]
            cursor += 1
        else:
            if cursor + 2 > len(body):
                invalid()
            count = int.from_bytes(body[cursor:cursor + 2], "little") + 0x7F00
            cursor += 2
        if literal_count + 3 * count > block_max:
            invalid()  # Includes per-frame floor(A/3) and literal-byte ceilings.
        literals += literal_count
        sequences += count
        if count == 0:
            if cursor != len(body):
                invalid()
            produced += literal_count
            block_outputs.append(literal_count)
            continue
        if cursor >= len(body) or body[cursor] & 3:
            invalid()
        modes = body[cursor]
        cursor += 1
        for i, max_symbol, max_log in ((0, 35, 9), (1, 31, 8), (2, 52, 9)):
            mode = (modes >> (6 - 2 * i)) & 3
            if mode == 0:
                tables[i] = DEFAULTS[i]
            elif mode == 1:
                if cursor >= len(body) or body[cursor] > max_symbol:
                    invalid()
                tables[i] = Table(0, ((body[cursor], 0, 0),))
                cursor += 1
            elif mode == 2:
                tables[i], cursor = read_table(body, cursor, max_symbol, max_log)
            elif tables[i] is None:
                invalid()
            if mode != 3:
                table_count += 1
                cells += len(tables[i].rows)
        bits = ReverseBits(body[cursor:])
        initial_bits = bits.bit
        states = [bits.read(table.log) for table in tables]
        block_output = used_literals = 0
        for index in range(count):
            ll, of, ml = [table.rows[state] for table, state in zip(tables, states)]
            value = (1 << of[0]) + bits.read(of[0])
            match = ML_BASE[ml[0]] + bits.read(ML_BITS[ml[0]])
            literal = LL_BASE[ll[0]] + bits.read(LL_BITS[ll[0]])
            if value > 3:
                distance = value - 3
                repeats = [distance, repeats[0], repeats[1]]
            elif literal == 0 and value == 3:
                distance = repeats[0] - 1
                repeats = [distance, repeats[0], repeats[1]]
            else:
                rep = value - 1 + (literal == 0)
                distance = repeats[rep]
                repeats = [distance] + repeats[:rep] + repeats[rep + 1:]
            used_literals += literal
            if used_literals > literal_count or block_output + literal + match > block_max:
                invalid()
            if distance <= 0 or distance > produced + block_output + literal:
                invalid()
            if distance > info.window:
                invalid("window_offset")
            max_offset = max(max_offset, distance)
            block_output += literal + match
            if index + 1 < count:
                # Update LL, ML, OF after reading extras OF, ML, LL.
                for i, row in ((0, ll), (2, ml), (1, of)):
                    states[i] = row[2] + bits.read(row[1])
        if bits.bit != 0:
            invalid()
        sequence_bits += initial_bits
        block_output += literal_count - used_literals
        if block_output > block_max:
            invalid()
        produced += block_output
        block_outputs.append(block_output)
    if produced != info.content_size or offset + 4 != len(encoded):
        invalid()
    return WorkStats(info.block_count, compressed_blocks, sequences, literals, raw_rle,
                     produced, table_count, cells, max_offset, sequence_bits, tuple(block_outputs))
