"""Offline, opt-in v3 persistence. Never imported by the active storage factory.

Format/signature/media verification is NOT full consensus authorization. Callers
must establish ancestry/state/admission validity before selecting or finalizing.
Only explicit disposable paths and an explicit trusted context are accepted.
"""
from contextlib import closing, contextmanager
from dataclasses import asdict
from pathlib import Path
import sqlite3

from .block import parse_record
from .finality import validate_proof
from .media import reconstruct
from .primitives import MAX_RECORD, V3Error, canonical, h64, parse, uint
from codec_prototype.isolated_decoder import Status

APPLICATION_ID = 0x5A563331
SCHEMA_VERSION = 1
SCHEMA = (
    "CREATE TABLE settings (id INTEGER PRIMARY KEY CHECK(id=1), context BLOB NOT NULL, anchor_height INTEGER NOT NULL, anchor_hash TEXT NOT NULL, selected_tip TEXT REFERENCES blocks(hash))",
    f"CREATE TABLE blocks (hash TEXT PRIMARY KEY, canonical BLOB NOT NULL CHECK(typeof(canonical)='blob' AND length(canonical) BETWEEN 1 AND {MAX_RECORD})) WITHOUT ROWID",
    "CREATE TABLE block_index (hash TEXT PRIMARY KEY REFERENCES blocks(hash), height INTEGER NOT NULL, previous_hash TEXT NOT NULL, original_hash TEXT NOT NULL) WITHOUT ROWID",
    "CREATE INDEX block_height_idx ON block_index(height)",
    "CREATE INDEX block_previous_idx ON block_index(previous_hash)",
    "CREATE INDEX block_media_idx ON block_index(original_hash)",
    "CREATE TABLE transaction_index (block_hash TEXT NOT NULL REFERENCES blocks(hash), position INTEGER NOT NULL, tx_id TEXT NOT NULL, PRIMARY KEY(block_hash,position)) WITHOUT ROWID",
    "CREATE INDEX transaction_id_idx ON transaction_index(tx_id)",
    "CREATE TABLE canonical_chain (height INTEGER PRIMARY KEY, hash TEXT NOT NULL UNIQUE REFERENCES blocks(hash))",
    "CREATE TABLE finality (hash TEXT PRIMARY KEY REFERENCES blocks(hash), proof BLOB NOT NULL CHECK(typeof(proof)='blob' AND length(proof)<=262144), trust_context BLOB NOT NULL CHECK(typeof(trust_context)='blob' AND length(trust_context)<=32768)) WITHOUT ROWID",
    "CREATE TRIGGER immutable_blocks_update BEFORE UPDATE ON blocks BEGIN SELECT RAISE(ABORT,'immutable canonical block'); END",
    "CREATE TRIGGER immutable_blocks_delete BEFORE DELETE ON blocks BEGIN SELECT RAISE(ABORT,'immutable canonical block'); END",
    "CREATE TRIGGER immutable_finality_update BEFORE UPDATE ON finality BEGIN SELECT RAISE(ABORT,'immutable finality evidence'); END",
    "CREATE TRIGGER immutable_finality_delete BEFORE DELETE ON finality BEGIN SELECT RAISE(ABORT,'immutable finality evidence'); END",
)


class StorageError(RuntimeError):
    """Local storage problem, never a consensus rejection."""


class StorageCorruption(StorageError):
    pass


class StorageUnavailable(StorageError):
    def __init__(self, message, outcome=None):
        self.outcome = outcome
        super().__init__(message)


class RecordConflict(StorageError):
    pass


class ChainSelectionError(StorageError):
    pass


class MediaRejected(ValueError):
    """Incoming bytes failed deterministic media verification; not chain validity."""
    def __init__(self, outcome):
        self.outcome = outcome
        super().__init__(f'{outcome.stage}: {outcome.code}')


def _schema_objects(connection):
    return connection.execute(
        "SELECT type,name,tbl_name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()


class V3Store:
    """Single-owner connection; SQLite serializes writers across store instances.

    Existing files must already be this exact schema/context. No migration,
    repair-on-open, default path, genesis construction or production imports.
    A nonzero anchor is an externally authenticated snapshot boundary.
    """
    def __init__(self, path, ctx, *, anchor_height=0, anchor_hash=None, decoder=None):
        self.path = Path(path).resolve()
        self.ctx = ctx
        self.decoder = decoder
        self.anchor_height = uint(anchor_height)
        self.anchor_hash = h64(ctx.genesis_hash if anchor_hash is None else anchor_hash)
        if anchor_height == 0 and self.anchor_hash != ctx.genesis_hash:
            raise ValueError('height-zero anchor must match context genesis')
        self.context_bytes = canonical(asdict(ctx))
        self.connection = None
        # Exclusive creation avoids interpreting an existing empty/arbitrary DB
        # as authorization to initialize or migrate it.
        try:
            with self.path.open('xb'):
                pass
            created = True
        except FileExistsError:
            created = False
        try:
            self.connection = sqlite3.connect(self.path, isolation_level=None, timeout=5)
            self.connection.execute('PRAGMA foreign_keys=ON')
            if created:
                with self._transaction(write=True) as connection:
                    for statement in SCHEMA:
                        connection.execute(statement)
                    connection.execute(f'PRAGMA application_id={APPLICATION_ID}')
                    connection.execute(f'PRAGMA user_version={SCHEMA_VERSION}')
                    connection.execute('INSERT INTO settings VALUES(1,?,?,?,NULL)',
                                       (self.context_bytes, anchor_height, self.anchor_hash))
            self._validate_schema()
            if self.connection.execute('PRAGMA journal_mode=WAL').fetchone()[0] != 'wal':
                raise StorageUnavailable('WAL mode unavailable')
            self.connection.execute('PRAGMA synchronous=FULL')
            self.connection.execute('PRAGMA wal_autocheckpoint=0')
        except sqlite3.DatabaseError as exc:
            self.close()
            raise StorageCorruption('cannot open isolated v3 database') from exc
        except BaseException:
            self.close()
            raise

    def close(self):
        if self.connection is not None:
            self.connection.close()
            self.connection = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    @contextmanager
    def _transaction(self, *, write=False):
        connection = self.connection
        try:
            connection.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
            yield connection
            connection.execute('COMMIT')
        except sqlite3.DatabaseError as exc:
            if connection.in_transaction:
                connection.rollback()
            if isinstance(exc, sqlite3.OperationalError) and any(
                    word in str(exc).lower() for word in ('locked', 'busy', 'disk is full', 'readonly', 'i/o')):
                raise StorageUnavailable('local SQLite operation unavailable') from exc
            raise StorageCorruption('local SQLite operation failed') from exc
        except BaseException:
            if connection.in_transaction:
                connection.rollback()
            raise

    def _validate_schema(self):
        connection = self.connection
        with closing(sqlite3.connect(':memory:')) as expected:
            for statement in SCHEMA:
                expected.execute(statement)
            if _schema_objects(connection) != _schema_objects(expected):
                raise StorageCorruption('unknown or damaged isolated v3 schema; no migration attempted')
        if (connection.execute('PRAGMA application_id').fetchone()[0] != APPLICATION_ID or
                connection.execute('PRAGMA user_version').fetchone()[0] != SCHEMA_VERSION):
            raise StorageCorruption('isolated v3 schema version mismatch')
        rows = connection.execute('SELECT id,context,anchor_height,anchor_hash FROM settings').fetchall()
        if rows != [(1, self.context_bytes, self.anchor_height, self.anchor_hash)]:
            raise StorageCorruption('storage context/anchor mismatch')

    def _verify(self, raw, *, stored=False):
        try:
            record = parse_record(raw, self.ctx)
        except V3Error as exc:
            if stored:
                raise StorageCorruption(f'stored canonical record: {exc.code}') from exc
            raise
        outcome = reconstruct(record['envelope']['payload']['media'], decoder=self.decoder)
        if outcome.status == Status.INDETERMINATE_LOCAL_FAILURE:
            raise StorageUnavailable('isolated decoder local failure', outcome)
        if outcome.status != Status.VALID:
            if stored:
                raise StorageCorruption('stored media failed integrity verification')
            raise MediaRejected(outcome)
        return record

    @staticmethod
    def _derived(record):
        payload = record['envelope']['payload']
        return (record['hash'], payload['index'], payload['previous_hash'],
                payload['media']['original_sha256'])

    @staticmethod
    def _transactions(record):
        return [(record['hash'], position, tx['tx_id']) for position, tx in
                enumerate(record['envelope']['payload']['native_transactions'])]

    def _put_indexes(self, connection, record):
        connection.execute('INSERT INTO block_index VALUES(?,?,?,?)', self._derived(record))
        connection.executemany('INSERT INTO transaction_index VALUES(?,?,?)', self._transactions(record))

    def _load(self, connection, block_hash, *, indexes=True):
        # Check length/type before fetching a potentially corrupted oversized BLOB.
        size = connection.execute('SELECT typeof(canonical),length(canonical) FROM blocks WHERE hash=?',
                                  (block_hash,)).fetchone()
        if size is None:
            return None
        if size[0] != 'blob' or not 1 <= size[1] <= MAX_RECORD:
            raise StorageCorruption('stored canonical BLOB type/size')
        raw = connection.execute('SELECT canonical FROM blocks WHERE hash=?', (block_hash,)).fetchone()[0]
        record = self._verify(raw, stored=True)
        if record['hash'] != block_hash:
            raise StorageCorruption('block primary key disagrees with authenticated hash')
        if indexes:
            row = connection.execute('SELECT * FROM block_index WHERE hash=?', (block_hash,)).fetchone()
            txs = connection.execute('SELECT * FROM transaction_index WHERE block_hash=? ORDER BY position',
                                     (block_hash,)).fetchall()
            if row != self._derived(record) or txs != self._transactions(record):
                raise StorageCorruption('derived block/transaction index mismatch')
        return raw, record

    def insert(self, raw):
        """Return True on insertion, False for exact duplicate. Never overwrite.

        Incoming format errors remain V3Error; media outcomes stay three-state.
        All authoritative bytes and derived rows commit together, before ack.
        """
        record = self._verify(raw)
        with self._transaction(write=True) as connection:
            row = connection.execute('SELECT canonical FROM blocks WHERE hash=?', (record['hash'],)).fetchone()
            if row is not None:
                if row[0] != raw:
                    raise RecordConflict('same block hash has different canonical bytes; preserved existing record')
                self._load(connection, record['hash'])
                return False
            connection.execute('INSERT INTO blocks VALUES(?,?)', (record['hash'], raw))
            self._put_indexes(connection, record)
        return True

    def get(self, block_hash):
        h64(block_hash)
        with self._transaction() as connection:
            loaded = self._load(connection, block_hash)
            return loaded[0] if loaded else None

    def _lookup(self, column, value):
        # Column is selected only by the fixed methods below, never user SQL.
        with self._transaction() as connection:
            hashes = [row[0] for row in connection.execute(
                f'SELECT hash FROM block_index WHERE {column}=? ORDER BY hash', (value,))]
            result = []
            for block_hash in hashes:
                loaded = self._load(connection, block_hash)
                if loaded is None:
                    raise StorageCorruption('index points to missing block')
                result.append(loaded[0])
            return result

    def candidates_at_height(self, height):
        return self._lookup('height', uint(height, 1))

    def by_previous_hash(self, previous_hash):
        return self._lookup('previous_hash', h64(previous_hash))

    def by_original_hash(self, original_hash):
        return self._lookup('original_hash', h64(original_hash))

    def by_transaction(self, tx_id):
        h64(tx_id)
        with self._transaction() as connection:
            result = []
            for (block_hash,) in connection.execute(
                    'SELECT DISTINCT block_hash FROM transaction_index WHERE tx_id=? ORDER BY block_hash', (tx_id,)):
                loaded = self._load(connection, block_hash)
                if loaded is None:
                    raise StorageCorruption('transaction index points to missing block')
                result.append(loaded[0])
            return result

    def _tip(self, connection):
        row = connection.execute('SELECT selected_tip FROM settings WHERE id=1').fetchone()
        if row is None:
            raise StorageCorruption('missing selected tip record')
        return row[0]

    def _lineage(self, connection, tip, *, indexes=True):
        chain = []
        seen = set()
        cursor = tip
        while cursor is not None and cursor != self.anchor_hash:
            if cursor in seen:
                raise ChainSelectionError('cyclic candidate lineage')
            seen.add(cursor)
            loaded = self._load(connection, cursor, indexes=indexes)
            if loaded is None:
                raise ChainSelectionError('missing candidate ancestor')
            record = loaded[1]
            _, height, previous, _ = self._derived(record)
            if height <= self.anchor_height or (chain and height != chain[-1][0] - 1):
                raise ChainSelectionError('noncontiguous candidate heights')
            chain.append((height, cursor))
            cursor = previous
        chain.reverse()
        if tip is not None and (not chain or chain[0][0] != self.anchor_height + 1):
            raise ChainSelectionError('candidate does not descend from trusted anchor')
        return chain

    def _proofs(self, connection):
        result = []
        for block_hash, proof_size, trust_size in connection.execute(
                'SELECT hash,length(proof),length(trust_context) FROM finality').fetchall():
            if not 1 <= proof_size <= 262144 or not 1 <= trust_size <= 32768:
                raise StorageCorruption('finality evidence size')
            proof_raw, trust_raw = connection.execute(
                'SELECT proof,trust_context FROM finality WHERE hash=?', (block_hash,)).fetchone()
            try:
                proof = parse(proof_raw, limit=262144)
                trust = parse(trust_raw, limit=32768)
                if set(trust) != {'validators', 'equivocators'}:
                    raise ValueError('trust fields')
                if (type(trust['validators']) is not list or type(trust['equivocators']) is not list or
                        trust['equivocators'] != sorted(set(trust['equivocators']))):
                    raise ValueError('noncanonical retained trust context')
                validate_proof(proof, self.ctx, trusted_validators=tuple(trust['validators']),
                               equivocators=frozenset(trust['equivocators']),
                               block_height=proof['block_height'], block_hash=block_hash)
            except (V3Error, KeyError, TypeError, ValueError) as exc:
                raise StorageCorruption('retained finality evidence is invalid') from exc
            result.append((proof['block_height'], block_hash))
        return result

    def _selected(self, connection, *, indexes=True, compare=True):
        try:
            chain = self._lineage(connection, self._tip(connection), indexes=indexes)
        except ChainSelectionError as exc:
            raise StorageCorruption('selected history is missing or damaged') from exc
        if compare and connection.execute('SELECT height,hash FROM canonical_chain ORDER BY height').fetchall() != chain:
            raise StorageCorruption('canonical membership index mismatch')
        if not set(self._proofs(connection)) <= set(chain):
            raise StorageCorruption('finalized target missing from selected history')
        return chain

    def selected_tip(self):
        with self._transaction() as connection:
            chain = self._selected(connection)
            return chain[-1][1] if chain else None

    def get_by_height(self, height):
        uint(height, 1)
        with self._transaction() as connection:
            chain = dict(self._selected(connection))
            return self._load(connection, chain[height])[0] if height in chain else None

    def select_chain(self, tip, *, expected_tip):
        """Storage-only compare-and-swap. Caller chooses a fully validated winner.

        No work score, longest-chain rule, balances, claims or vote calculation.
        The entire selected path and tip change in one SQLite transaction.
        """
        if tip is not None:
            h64(tip)
        with self._transaction(write=True) as connection:
            old = self._selected(connection)
            if (old[-1][1] if old else None) != expected_tip:
                raise ChainSelectionError('stale selected tip')
            chain = self._lineage(connection, tip)
            if not set(self._proofs(connection)) <= set(chain):
                raise ChainSelectionError('cannot replace finalized history')
            connection.execute('DELETE FROM canonical_chain')
            connection.executemany('INSERT INTO canonical_chain VALUES(?,?)', chain)
            connection.execute('UPDATE settings SET selected_tip=? WHERE id=1', (tip,))

    def finalize(self, proof_raw, *, trusted_validators, equivocators):
        """Retain validated proof plus caller-authenticated historical trust inputs.

        The database cannot authenticate these inputs from a proof's own set.
        Later consensus integration must resolve them from trusted ancestry.
        """
        proof = parse(proof_raw, limit=262144)
        validate_proof(proof, self.ctx, trusted_validators=trusted_validators, equivocators=equivocators,
                       block_height=proof['block_height'], block_hash=proof['block_hash'])
        trust = canonical(dict(validators=list(trusted_validators), equivocators=sorted(equivocators)))
        with self._transaction(write=True) as connection:
            if (proof['block_height'], proof['block_hash']) not in self._selected(connection):
                raise ChainSelectionError('finality target is not selected')
            existing = connection.execute('SELECT proof,trust_context FROM finality WHERE hash=?',
                                          (proof['block_hash'],)).fetchone()
            if existing is not None:
                if existing != (proof_raw, trust):
                    raise RecordConflict('different retained proof/context for finalized target')
                return False
            connection.execute('INSERT INTO finality VALUES(?,?,?)', (proof['block_hash'], proof_raw, trust))
        return True

    def is_finalized(self, block_hash):
        h64(block_hash)
        with self._transaction() as connection:
            chain = self._selected(connection)
            proofs = self._proofs(connection)
            boundary = max((height for height, _ in proofs), default=self.anchor_height)
            return any(h == block_hash and height <= boundary for height, h in chain)

    def _integrity(self, connection):
        self._validate_schema()
        if connection.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
            raise StorageCorruption('SQLite integrity_check failed')
        if connection.execute('PRAGMA foreign_key_check').fetchall():
            raise StorageCorruption('SQLite foreign_key_check failed')
        count = tx_count = 0
        for (block_hash,) in connection.execute('SELECT hash FROM blocks').fetchall():
            loaded = self._load(connection, block_hash)
            count += 1
            tx_count += len(self._transactions(loaded[1]))
        if (connection.execute('SELECT count(*) FROM block_index').fetchone()[0] != count or
                connection.execute('SELECT count(*) FROM transaction_index').fetchone()[0] != tx_count):
            raise StorageCorruption('orphaned derived rows')
        chain = self._selected(connection)
        return dict(blocks=count, native_transaction_references=tx_count,
                    selected_blocks=len(chain), finality_proofs=len(self._proofs(connection)))

    def check_integrity(self):
        """Full snapshot scan: includes omitted index entries and every candidate."""
        with self._transaction() as connection:
            return self._integrity(connection)

    def rebuild_indexes(self):
        """Never chooses a tip or manufactures finality; corrupt bytes abort repair."""
        with self._transaction(write=True) as connection:
            self._validate_schema()
            # Validate retained lineage/evidence without trusting derived tables.
            chain = self._selected(connection, indexes=False, compare=False)
            connection.execute('DELETE FROM transaction_index')
            connection.execute('DELETE FROM block_index')
            for (block_hash,) in connection.execute('SELECT hash FROM blocks').fetchall():
                self._put_indexes(connection, self._load(connection, block_hash, indexes=False)[1])
            connection.execute('DELETE FROM canonical_chain')
            connection.executemany('INSERT INTO canonical_chain VALUES(?,?)', chain)
            return self._integrity(connection)

    def backup(self, target):
        """SQLite online backup, including committed WAL; exclusive new destination.

        Verification and backup share a read snapshot. Never file-copy a WAL DB.
        An interrupted destination is unusable until a subsequent integrity scan.
        """
        target = Path(target).resolve()
        with target.open('xb'):
            pass
        with self._transaction() as connection:
            self._integrity(connection)
            with closing(sqlite3.connect(target)) as destination:
                connection.backup(destination)
        with V3Store(target, self.ctx, anchor_height=self.anchor_height,
                     anchor_hash=self.anchor_hash, decoder=self.decoder) as restored:
            restored.check_integrity()
        return target

    @classmethod
    def restore(cls, source, target, ctx, **kwargs):
        """Restore via the backup API to a new path; never overwrite live state."""
        source = Path(source).resolve()
        if not source.is_file():
            raise FileNotFoundError(source)
        with cls(source, ctx, **kwargs) as store:
            return store.backup(target)

    def checkpoint(self):
        """Offline maintenance; busy result means a reader prevented truncation."""
        return tuple(self.connection.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone())
