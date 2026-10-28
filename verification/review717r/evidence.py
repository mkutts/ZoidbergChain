"""Byte custody checks only; returned bytes never imply supported source policy."""
from .wire import pack, tagged

MAX_SOURCE = 3145728
MAX_NEW_BYTES = 67108864


def inventory_bytes(inventory, objects, *, verified_locators=frozenset()):
    pack('INVENTORY', inventory)
    refs = inventory['entries']
    keys = [(r['kind'], r['object_id']) for r in refs]
    if keys != sorted(set(keys)) or len({r['object_id'] for r in refs}) != len(refs):
        raise ValueError('inventory order/duplicate')
    total, result = 0, {}
    for ref in refs:
        if not 1 <= ref['length'] <= MAX_SOURCE:
            raise ValueError('source length bound')
        locator = ref['height'], ref['batch'], ref['index']
        if ref['height'] == 0:
            if locator != (0, '00'*32, 0):
                raise ValueError('source locator sentinel')
        elif locator not in verified_locators:
            raise ValueError('INCOMPLETE_HISTORY')
        raw = objects.get(ref['object_id'])
        if raw is None:
            raise ValueError('INCOMPLETE_EVIDENCE')
        if type(raw) is not bytes or len(raw) != ref['length']:
            raise ValueError('source length mismatch')
        if tagged('source-'+str(ref['kind']), raw) != ref['object_id']:
            raise ValueError('source commitment mismatch')
        total += len(raw)
        if total > MAX_NEW_BYTES:
            raise ValueError('source aggregate budget')
        result[ref['object_id']] = raw
    return result  # Custody bytes only. Semantic source verifiers remain required.


def assemble(ref, pages):
    if not 1 <= ref['length'] <= MAX_SOURCE:
        raise ValueError('source length bound')
    offset, result = 0, []
    for p in pages:
        pack('DATA', p)
        chunk = bytes.fromhex(p['chunk'])
        if (p['object_id'] != ref['object_id'] or p['total'] != ref['length']
                or p['offset'] != offset or offset+len(chunk) > ref['length']):
            raise ValueError('source page coverage/binding')
        result.append(chunk)
        offset += len(chunk)
    if offset != ref['length']:
        raise ValueError('INCOMPLETE_EVIDENCE')
    raw = b''.join(result)
    if tagged('source-'+str(ref['kind']), raw) != ref['object_id']:
        raise ValueError('source commitment mismatch')
    return raw
