"""Reserve -> witness -> sign -> store -> witness -> release, test identities only."""
from copy import deepcopy
from pathlib import Path
from threading import RLock

from canonical_v3.primitives import require, uint, V3Error
from .wire import J, parse, sha, envelope, signed, slot_key
from .reducer import initial, catalogue, plan, start_nonproposer, ref
from .custody import (connection, LocalOwner, TestKey, TestWitness, Unavailable,
                      CorruptState, StaleState, CryptoFailure)


def refs(deps):
    return sorted([ref(k, raw) for k, raw in set(deps)], key=lambda r: (r['kind'], r['digest']))


def coordinates(ns, slot):
    return ns, slot['height'], slot['round'], slot['purpose']


def slot_record(ns, e, state, deps, bid, vid):
    raw = J(e)
    return dict(slot_version=1, namespace_id=ns, **slot_key(e), payload_hex=raw.hex(),
        message_id=sha(raw), status='reserved', signature=None,
        before_revision=state['revision'], after_revision=state['revision']+1,
        evidence=refs(deps), block_record_id=bid, validation_id=vid,
        fence_generation=state['fence_generation'])


def stored_state(state, slot, ctx):
    raw = J(dict(envelope=parse(bytes.fromhex(slot['payload_hex']), 2048),
                 signature=slot['signature'], signature_scheme='personal_sign'))
    signed(raw, ctx)
    receipt = J(dict(record_version=1, previous=state['inbox_tip'], signed_id=sha(raw)))
    after = deepcopy(state)
    after['inbox_tip'], after['pending_slot'] = sha(receipt), None
    return after, [('signed', raw), ('receipt', receipt)], raw


class Signer:
    """No live integration, key loader, timers, round/height advance or state setter.

    ``test_catalogue`` is trusted fixture input at bootstrap, pinned thereafter.
    ``fault`` is a trusted test harness hook; it never receives signature bytes.
    """
    def __init__(self, path, custody_dir, ctx, key, test_catalogue, *, bootstrap=False,
                 busy_ms=30000, fault=None):
        require(type(key) is TestKey and ctx.network.startswith(('task717i-test', 'task717j-test')),
                'TEST_ONLY')
        self.path, self.ctx, self.key = Path(path).resolve(), ctx, key
        self.pub = key.public_key
        self.namespace = ctx.namespace(self.pub)
        self.ns = sha(J(self.namespace))
        self.catalogue_raw = bytes(test_catalogue)
        catalogue(self.catalogue_raw, ctx)
        require(type(busy_ms) is int and 1 <= busy_ms <= 30000, 'busy_timeout')
        self.busy_ms, self.fault = busy_ms, fault
        self.mutex, self.available, self.closed = RLock(), False, False
        self.owner = LocalOwner(custody_dir, self.pub)
        self.witness = TestWitness(Path(custody_dir).resolve() / (self.pub + '.witness.db'),
                                   self.ns, self.pub, busy_ms)
        try:
            if bootstrap:
                # Explicit initialization only. Never repair or overwrite any existing file.
                require(not self.path.exists() and not self.witness.path.exists(), 'already_initialized')
                with open(self.path, 'xb'):
                    pass
                with self.connect(create=True) as c:
                    c.executescript(Path(__file__).with_name('schema.sql').read_text(encoding='utf-8'))
                    c.execute('BEGIN IMMEDIATE')
                    c.execute('INSERT INTO authority VALUES(1,?,?,?,?)', (J(self.namespace),
                        ctx.manifest_bytes, ctx.agreement_bytes, self.catalogue_raw))
                    base = initial(self.ns, ctx.genesis_hash, 1)
                    deps = [('manifest', ctx.manifest_bytes), ('agreement', ctx.agreement_bytes),
                            ('policy', self.catalogue_raw)]
                    self._append(c, base, deepcopy(base), 'INIT', deps, None, None)
                    c.commit()
                    loaded = self._load(c)
                self.witness.create(loaded['head'])
                self.generation = 1
                self.available = True
            else:
                self._recover(claim=True)
        except BaseException:
            self.owner.close()
            self.closed = True
            raise

    def connect(self, create=False):
        return connection(self.path, create=create, busy_ms=self.busy_ms)

    @property
    def blocks(self):
        # Parsed fixture dictionaries are conveniences, never mutable authority.
        return catalogue(self.catalogue_raw, self.ctx)

    def _hook(self, name, c=None):
        if self.fault is not None:
            self.fault(name, c)

    def _put(self, c, kind, raw):
        digest = sha(raw)
        c.execute('INSERT OR IGNORE INTO blobs VALUES(?,?,?)', (digest, kind, raw))
        require(c.execute('SELECT kind,raw FROM blobs WHERE digest=?', (digest,)).fetchone() ==
                (kind, raw), 'blob_collision')
        return digest

    def _append(self, c, before, after, rule, deps, slot, previous):
        uint(before['revision'], 0, 9007199254740990)
        after['revision'] = before['revision'] + 1
        for kind, raw in deps:
            self._put(c, kind, raw)
        before_id = self._put(c, 'state', J(before))
        after_id = self._put(c, 'state', J(after))
        event = dict(record_version=1, namespace_id=self.ns, sequence=after['revision'],
            previous=previous, rule=rule, before_state=before_id, after_state=after_id,
            evidence=refs(deps), slot=slot)
        eid = self._put(c, 'event', J(event))
        c.execute('INSERT INTO events VALUES(?,?,?)', (after['revision'], eid, after_id))
        head = dict(record_version=1, namespace_id=self.ns, sequence=after['revision'],
                    event_id=eid, state_id=after_id)
        c.execute('INSERT INTO head VALUES(1,?) ON CONFLICT(singleton) DO UPDATE SET record=excluded.record',
                  (J(head),))
        return head

    def _load(self, c):
        """Rebuild all authoritative state/indexes by replay, never trust mutable caches."""
        try:
            return self._replay(c)
        except (V3Error, KeyError, IndexError, TypeError, ValueError) as exc:
            raise CorruptState('signer journal integrity/reducer validation failed') from exc

    def _replay(self, c):
        require(c.execute('PRAGMA quick_check').fetchall() == [('ok',)] and
                not c.execute('PRAGMA foreign_key_check').fetchall(), 'sqlite_integrity')
        require(c.execute('SELECT * FROM authority').fetchall() == [(1, J(self.namespace),
            self.ctx.manifest_bytes, self.ctx.agreement_bytes, self.catalogue_raw)], 'authority')
        blobs = {}
        for digest, kind, raw in c.execute('SELECT digest,kind,raw FROM blobs'):
            require(type(raw) is bytes and len(raw) <= 65536 and sha(raw) == digest, 'blob_digest')
            parse(raw, 65536)
            blobs[digest] = kind, raw

        def get(kind, digest):
            require(digest in blobs and blobs[digest][0] == kind, 'missing_source')
            return blobs[digest][1]

        def deps_for(evidence):
            require(type(evidence) is list and len(evidence) <= 16, 'evidence_bound')
            dep = [(r['kind'], get(r['kind'], r['digest'])) for r in evidence]
            require(refs(dep) == evidence, 'evidence_order')
            return dep

        state, previous = initial(self.ns, self.ctx.genesis_hash, 1), None
        slots, outbox, heads = {}, {}, []
        for seq, eid, sid in c.execute('SELECT sequence,event_id,state_id FROM events ORDER BY sequence'):
            event = parse(get('event', eid), 65536)
            after = parse(get('state', sid), 65536)
            require(seq == state['revision']+1 and event['sequence'] == seq, 'sequence')
            require(event['before_state'] == sha(J(state)) and get('state', event['before_state']) == J(state),
                    'before_state')
            deps = deps_for(event['evidence'])
            rule, slot = event['rule'], event['slot']
            expected = deepcopy(state)
            expected_deps = []
            if rule == 'INIT':
                require(seq == 1 and slot is None, 'init')
                expected_deps = [('manifest', self.ctx.manifest_bytes), ('agreement', self.ctx.agreement_bytes),
                                 ('policy', self.catalogue_raw)]
            elif rule == 'FENCE':
                require(slot is None, 'fence_slot')
                require(uint(after['fence_generation'], 1) > state['fence_generation'], 'fence_generation')
                expected['fence_generation'] = after['fence_generation']
            elif rule == 'START' and slot is None:
                expected, expected_deps = start_nonproposer(state, self.ctx, self.pub)
            elif rule in ('START', 'L22', 'L36', 'L44'):
                slot_deps = [raw for kind, raw in deps if kind == 'slot']
                require(len(slot_deps) == 1, 'reservation_slot')
                row = parse(slot_deps[0])
                coord = coordinates(self.ns, slot)
                require(coord not in slots, 'slot_reuse')
                e = envelope(bytes.fromhex(row['payload_hex']), self.ctx)
                require(slot_key(e) == slot, 'slot_coordinates')
                supporting = deps_for(row['evidence'])
                prop = [raw for kind, raw in supporting if kind == 'signed' and
                        parse(raw)['envelope']['payload']['step'] == 'propose']
                pv = [raw for kind, raw in supporting if kind == 'pv']
                require(len(prop) <= 1 and len(pv) <= 1, 'support_count')
                expected_rule, expected, expected_deps, bid, vid = plan(state, e, self.ctx, self.pub,
                    self.blocks, prop[0] if prop else None, pv[0] if pv else None)
                require(expected_rule == rule and J(row) == J(slot_record(self.ns, e, state,
                        expected_deps, bid, vid)), 'reservation_guard')
                expected_deps = expected_deps + [('slot', J(row))]
                slots[coord] = row
            elif rule == 'SIGN_STORED':
                coord = coordinates(self.ns, slot)
                require(state['pending_slot'] == slot and coord in slots, 'pending_slot')
                old = slots[coord]
                require(old['status'] == 'reserved', 'signature_overwrite')
                slot_deps = [raw for kind, raw in deps if kind == 'slot']
                require(len(slot_deps) == 1, 'signed_slot')
                row = parse(slot_deps[0])
                require(row == {**old, 'status': 'signed', 'signature': row['signature']}, 'signed_row')
                expected, expected_deps, raw = stored_state(state, row, self.ctx)
                expected_deps.append(('slot', J(row)))
                slots[coord], outbox[coord] = row, sha(raw)
            else:
                raise CorruptState('unsupported agreement transition')
            expected['revision'] = seq
            require(J(expected) == J(after) and refs(expected_deps) == event['evidence'], 'transition')
            require(event == dict(record_version=1, namespace_id=self.ns, sequence=seq,
                previous=previous, rule=rule, before_state=sha(J(state)), after_state=sid,
                evidence=refs(expected_deps), slot=slot), 'event_schema')
            state, previous = after, eid
            heads.append(dict(record_version=1, namespace_id=self.ns, sequence=seq, event_id=eid, state_id=sid))
        require(heads and c.execute('SELECT * FROM head').fetchall() == [(1, J(heads[-1]))], 'head')
        require(set(c.execute('SELECT * FROM slots')) ==
                {(*coord, sha(J(row))) for coord, row in slots.items()}, 'slot_index')
        require(set(c.execute('SELECT * FROM outbox')) ==
                {(*coord, digest) for coord, digest in outbox.items()}, 'outbox_index')
        return dict(state=state, head=heads[-1], heads=heads, slots=slots,
                    outbox={coord: get('signed', digest) for coord, digest in outbox.items()})

    def _recover(self, claim=False):
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            loaded = self._load(c)
            generation = self.witness.reconcile(loaded['heads'])
            if loaded['state']['fence_generation'] > generation:
                raise StaleState('journal generation ahead of custody')
            if not claim and hasattr(self, 'generation') and self.generation != generation:
                raise StaleState('existing owner cannot adopt another generation')
            if claim:
                generation = self.witness.claim()
                s = deepcopy(loaded['state'])
                s['fence_generation'] = generation
                self._append(c, loaded['state'], s, 'FENCE', [], None, loaded['head']['event_id'])
                c.commit()
                c.execute('BEGIN IMMEDIATE')
                loaded = self._load(c)
                self.witness.reconcile(loaded['heads'])
            elif loaded['state']['fence_generation'] != generation:
                raise StaleState('generation differs; reopen under exclusive ownership')
        self._hook('after_witness_commit')
        self.generation, self.available = generation, True
        return loaded

    def recover(self):
        with self.mutex:
            if self.closed:
                raise Unavailable('owner closed')
            self.available = False
            return deepcopy(self._recover()['state'])

    def close(self):
        with self.mutex:
            self.available, self.closed = False, True
            self.owner.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def _ready(self):
        if not self.available or self.closed:
            raise Unavailable('signer unavailable; explicit validated recovery required')

    def start(self):
        with self.mutex:
            self._ready()
            try:
                with self.connect() as c:
                    c.execute('BEGIN IMMEDIATE')
                    loaded = self._load(c)
                    self._witness(loaded)
                    s, deps = start_nonproposer(loaded['state'], self.ctx, self.pub)
                    self._append(c, loaded['state'], s, 'START', deps, None, loaded['head']['event_id'])
                    c.commit()
                self._recover()
            except V3Error:
                raise
            except BaseException:
                self.available = False
                raise

    def _witness(self, loaded):
        if self.witness.reconcile(loaded['heads']) != self.generation:
            raise StaleState('owner generation revoked')

    def sign(self, raw, *, proposal=None, pv=None, publish=None):
        # Closed canonical parsing and context verification precede transactions/key use.
        e = envelope(raw, self.ctx)
        require(e['payload']['validator_id'] == self.namespace['validator_id'], 'signer_identity')
        slot = slot_key(e)
        coord = coordinates(self.ns, slot)
        with self.mutex:
            self._ready()
            try:
                with self.connect() as c:
                    c.execute('BEGIN IMMEDIATE')
                    loaded = self._load(c)
                    self._witness(loaded)
                    row = loaded['slots'].get(coord)
                    if row is not None:
                        require(row['payload_hex'] == raw.hex(), 'CONFLICTING_SLOT')
                        if row['status'] == 'signed':
                            result = loaded['outbox'][coord]
                            c.commit()
                            return self._release(result, publish)
                    else:
                        rule, after, deps, bid, vid = plan(loaded['state'], e, self.ctx, self.pub,
                                                         self.blocks, proposal, pv)
                        row = slot_record(self.ns, e, loaded['state'], deps, bid, vid)
                        deps.append(('slot', J(row)))
                        self._append(c, loaded['state'], after, rule, deps, slot, loaded['head']['event_id'])
                        c.execute('INSERT INTO slots VALUES(?,?,?,?,?)', (*coord, sha(J(row))))
                        self._hook('during_lock_update' if rule == 'L36' else 'during_reservation', c)
                        self._hook('before_reservation_commit', c)
                    c.commit()
                    self._hook('after_reservation_commit', c)
                loaded = self._recover()
                grant = self.witness.authorize(loaded['head'], self.generation, raw)
                sig = self.key._sign_reserved(raw, grant)
                self._hook('after_sign')
                newrow = {**row, 'status': 'signed', 'signature': sig}
                try:
                    after, deps, result = stored_state(loaded['state'], newrow, self.ctx)
                except V3Error as exc:
                    raise CryptoFailure('produced signature failed exact-key verification') from exc
                with self.connect() as c:
                    c.execute('BEGIN IMMEDIATE')
                    current = self._load(c)
                    self._witness(current)
                    require(current['head'] == loaded['head'] and current['slots'][coord] == row,
                            'reservation_changed')
                    deps.append(('slot', J(newrow)))
                    self._append(c, current['state'], after, 'SIGN_STORED', deps, slot,
                                 current['head']['event_id'])
                    c.execute('UPDATE slots SET slot_id=? WHERE namespace_id=? AND height=? AND round=? AND purpose=?',
                              (sha(J(newrow)), *coord))
                    c.execute('INSERT INTO outbox VALUES(?,?,?,?,?)', (*coord, sha(result)))
                    self._hook('before_signature_commit', c)
                    c.commit()
                    self._hook('after_signature_commit', c)
                final = self._recover()
                require(final['outbox'][coord] == result, 'outbox_changed')
                return self._release(final['outbox'][coord], publish)
            except V3Error:
                # Request/precondition refusals do not become storage failures.
                raise
            except BaseException:
                self.available = False
                raise

    def _release(self, raw, publish):
        self._hook('before_release')
        if publish is not None:
            publish(raw)
            self._hook('after_publication')
        return raw

    def transition(self, *args, **kwargs):
        """Explicit gate for all future timer/round/height/unlock/late-valid adapters."""
        self._ready()
        raise V3Error('INCOMPLETE_AGREEMENT_CONTEXT')
