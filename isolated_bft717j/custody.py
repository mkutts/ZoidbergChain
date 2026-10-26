"""Local OS exclusion and a ROLLBACKABLE witness emulator, for tests only."""
from contextlib import contextmanager
import os
from pathlib import Path
import sqlite3

from eth_account import Account
from eth_account.messages import encode_defunct
from eth_keys import keys

from .wire import J, parse, sha


class Unavailable(RuntimeError):
    pass


class OwnershipConflict(Unavailable):
    pass


class CorruptState(Unavailable):
    pass


class StaleState(Unavailable):
    pass


class CryptoFailure(RuntimeError):
    """Key/signature failure, never an SQLite or objective block-validity error."""


@contextmanager
def connection(path, *, create=False, busy_ms=30000):
    # mode=rw is essential: recovery must never recreate a missing database.
    uri = Path(path).resolve().as_uri() + ('?mode=rwc' if create else '?mode=rw')
    c = sqlite3.connect(uri, uri=True, isolation_level=None, timeout=busy_ms/1000)
    try:
        if c.execute('PRAGMA journal_mode').fetchone()[0].lower() != 'delete':
            raise Unavailable('DELETE journal required; no automatic conversion')
        c.execute('PRAGMA synchronous=EXTRA')
        c.execute('PRAGMA foreign_keys=ON')
        c.execute(f'PRAGMA busy_timeout={int(busy_ms)}')
        if (c.execute('PRAGMA synchronous').fetchone()[0] != 3 or
                c.execute('PRAGMA foreign_keys').fetchone()[0] != 1 or
                c.execute('PRAGMA busy_timeout').fetchone()[0] != busy_ms):
            raise Unavailable('SQLite settings did not apply')
        yield c
    finally:
        # COMMIT busy can leave an active transaction; never share/reuse it.
        try:
            if c.in_transaction:
                c.rollback()
        finally:
            c.close()


class LocalOwner:
    def __init__(self, root, pub):
        root = Path(root).resolve()
        root.mkdir(parents=True, exist_ok=True)
        self.path = root / (pub + '.owner')
        self.handle = open(self.path, 'a+b')
        self.handle.seek(0, 2)
        if self.handle.tell() == 0:
            self.handle.write(b'\0')
            self.handle.flush()
        self.handle.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self.handle.close()
            raise OwnershipConflict('test identity already owned') from exc

    def close(self):
        if self.handle.closed:
            return
        self.handle.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        finally:
            self.handle.close()


class TestKey:
    """Random disposable material held only in memory. No production loader/export API.

    Python privacy is conventional: this is not HSM custody. Test fixtures may send
    this object over a multiprocessing pipe to a child in the same trust boundary.
    """
    __test__ = False

    def __init__(self):
        self._material = bytes(Account.create().key)
        self.public_key = keys.PrivateKey(self._material).public_key.to_compressed_bytes().hex()

    def __repr__(self):
        return f'TestKey(public_key={self.public_key!r})'

    def _sign_reserved(self, raw, grant):
        if grant != sha(raw):
            raise CryptoFailure('no exact reservation authorization')
        try:
            sig = Account.sign_message(encode_defunct(primitive=raw), self._material).signature
            return '0x' + bytes(sig).hex()
        except (ValueError, TypeError, OverflowError) as exc:
            raise CryptoFailure('test key failed') from exc


class TestWitness:
    """Separate durable high-water test double. Both-file rollback defeats it."""
    __test__ = False

    def __init__(self, path, namespace, pub, busy_ms=30000):
        self.path, self.namespace, self.pub, self.busy_ms = Path(path), namespace, pub, busy_ms

    def connect(self, create=False):
        return connection(self.path, create=create, busy_ms=self.busy_ms)

    def create(self, head):
        with self.connect(create=True) as c:
            c.execute('BEGIN IMMEDIATE')
            c.execute('CREATE TABLE witness (singleton INTEGER PRIMARY KEY CHECK(singleton=1), '
                      'namespace TEXT NOT NULL, public_key TEXT NOT NULL, generation INTEGER NOT NULL, '
                      'head BLOB NOT NULL)')
            c.execute('INSERT INTO witness VALUES(1,?,?,1,?)', (self.namespace, self.pub, J(head)))
            c.commit()

    def read(self, c):
        row = c.execute('SELECT namespace,public_key,generation,head FROM witness WHERE singleton=1').fetchone()
        if row is None or row[:2] != (self.namespace, self.pub):
            raise StaleState('witness namespace/key mismatch')
        if type(row[2]) is not int or not 1 <= row[2] <= 9007199254740991:
            raise CorruptState('witness generation')
        return row[2], parse(row[3])

    def reconcile(self, heads):
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            generation, old = self.read(c)
            sequence = old.get('sequence')
            if type(sequence) is not int or sequence < 1 or sequence > len(heads) or heads[sequence-1] != old:
                raise StaleState('signer is behind or diverges from surviving test witness')
            # Complete validated unique continuation only; never trust a larger counter alone.
            c.execute('UPDATE witness SET head=? WHERE singleton=1', (J(heads[-1]),))
            c.commit()
            return generation

    def claim(self):
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            generation, _ = self.read(c)
            if generation == 9007199254740991:
                raise Unavailable('generation exhausted')
            c.execute('UPDATE witness SET generation=generation+1 WHERE singleton=1')
            c.commit()
            return generation + 1

    def authorize(self, head, generation, raw):
        with self.connect() as c:
            current, stored = self.read(c)
            if current != generation or head != stored:
                raise StaleState('fence lost or head not witnessed')
        # Called only by the trusted signer after full reservation/reducer replay.
        return sha(raw)
