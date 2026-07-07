# Storage Operations

Task 5 storage hardening keeps JSON as the default backend while preparing the project for SQLite.

## Supported Backends

Set the backend with `STORAGE_BACKEND`.

- `STORAGE_BACKEND=json` keeps the current JSON-file storage format and remains the default.
- `STORAGE_BACKEND=sqlite` enables the SQLite backend for nodes that are ready to opt in.

Any other value fails fast with a clear startup error.

## Data Directory Isolation

All node state lives under `DATA_DIR`.

- `DATA_DIR=data` uses the default local node directory.
- `DATA_DIR=data\node-a` and `DATA_DIR=data\node-b` keep two local nodes isolated during testing.
- The active backend reads and writes only inside its own `DATA_DIR`.
- Task 6.2 also stores local content files under `CONTENT_STORAGE_DIR`, which defaults to `DATA_DIR/content`.

Task 5.7 keeps this behavior unchanged so existing local JSON data still loads without migration.

## Content Files

Task 6.2 adds node-local content-file storage without changing consensus.

- `CONTENT_STORAGE_DIR` defaults to `DATA_DIR/content`.
- `MAX_CONTENT_FILE_SIZE_BYTES` defaults to `5 MB`.
- Supported MIME types are `image/jpeg`, `image/png`, `image/gif`, `image/webp`, and `text/plain`.
- Stored file paths are derived from `content_hash`, not from the uploaded filename.
- `storage_status` moves through `missing`, `local`, `verified`, and `remote` depending on whether metadata exists, the file is present, and hash verification has succeeded.
- Portable exports and imports still include content metadata only. Raw content binaries stay in the local node store for now.
- Upload/download API endpoints are available in Task 6.3.
- Peer content sync is deferred to Task 6.4.

## Content API

Task 6.3 adds safe node-local content upload and retrieval:

- `POST /content/upload` accepts multipart file uploads with `submitted_by` and optional `caption`
- `POST /content/text` accepts JSON text content uploads
- `GET /content/{content_hash}` returns verified local content
- `GET /content/{content_hash}/metadata` returns safe metadata only

Security rules:

- uploads enforce `MAX_CONTENT_FILE_SIZE_BYTES`
- only supported MIME types are accepted
- downloads validate `content_hash` format before lookup
- files are always resolved from `CONTENT_STORAGE_DIR`, never from user-supplied filenames or paths
- API responses do not expose `local_path` or internal filesystem details

Recommended upload-first flow:

1. upload content with `/content/upload` or `/content/text`
2. keep the returned `content_hash` and `content_id`
3. create a later submission that references that uploaded content

Peer content sync is still deferred to Task 6.4.

## Backup

Backups write a safe snapshot into the node's `backups/` directory.

JSON backend:

```powershell
.\.venv\Scripts\python.exe .\scripts\storage_backup.py --data-dir data\node-a
```

SQLite backend:

```powershell
.\.venv\Scripts\python.exe .\scripts\storage_backup.py --data-dir data\node-a --storage-backend sqlite
```

Use `--dry-run` to see the target path without writing anything.

## Export

Exports create a portable JSON snapshot of node state.

By default, exports omit private keys and other sensitive fields.

```powershell
.\.venv\Scripts\python.exe .\scripts\storage_export.py --data-dir data\node-a --output data\node-a\exports\node-a-export.json
```

Development-only private key export requires all of the following:

- `ENVIRONMENT=development`
- `PUBLIC_API_MODE=false`
- `ALLOW_DEV_WALLET_PRIVATE_KEY_EXPORT=true`
- `--include-private-keys`

```powershell
.\.venv\Scripts\python.exe .\scripts\storage_export.py --data-dir data\node-a --output data\node-a\exports\node-a-dev-export.json --include-private-keys
```

Never share a dev export that includes private keys.

## Import

Imports accept a portable JSON snapshot.

Overwrite is refused by default. Use `--overwrite` only after creating a backup.

```powershell
.\.venv\Scripts\python.exe .\scripts\storage_import.py --data-dir data\node-b --input data\node-a\exports\node-a-export.json --overwrite
```

If the snapshot came from a different network, import will fail unless you pass `--allow-network-override`.

## Dry Run

All three tools support `--dry-run` where it makes sense.

```powershell
.\.venv\Scripts\python.exe .\scripts\storage_backup.py --data-dir data\node-a --dry-run
.\.venv\Scripts\python.exe .\scripts\storage_export.py --data-dir data\node-a --output data\node-a\exports\node-a-export.json --dry-run
.\.venv\Scripts\python.exe .\scripts\storage_import.py --data-dir data\node-b --input data\node-a\exports\node-a-export.json --dry-run
```

## Restore

Safe restore process:

1. Create or locate a backup or export file.
2. Restore JSON or SQLite-backed node state with the import tool.
3. Verify storage integrity.
4. Start the node again.

Examples:

```powershell
.\.venv\Scripts\python.exe .\scripts\storage_import.py --data-dir data\node-a --input data\node-a\backups\zoidberg-node-a-json-2026-07-06T120000Z.json --overwrite
.\.venv\Scripts\python.exe .\scripts\storage_import.py --data-dir data\node-a --input data\node-a\exports\node-a-export.json --overwrite
.\.venv\Scripts\python.exe -c "from storage import check_storage_integrity; print(check_storage_integrity())"
```

The import tool performs an integrity check automatically after a real import. The manual integrity check above is still useful after copying files by hand.

## Integrity Checks

Run a manual integrity check at any time:

```powershell
.\.venv\Scripts\python.exe -c "from storage import check_storage_integrity; print(check_storage_integrity())"
```

You can also target a specific backend and data directory:

```powershell
$env:DATA_DIR = "data\node-a"
$env:STORAGE_BACKEND = "sqlite"
.\.venv\Scripts\python.exe -c "from storage import create_storage_backend, check_storage_integrity; backend = create_storage_backend(); print(check_storage_integrity(backend))"
```

Check integrity before and after:

1. importing with `--overwrite`
2. switching a node from JSON to SQLite
3. restoring from backups
4. copying node data manually between machines

## JSON To SQLite Migration

Task 5.3 adds JSON-to-SQLite migration without changing the default backend.

Recommended operator workflow:

1. Stop the node.
2. Create a JSON backup.
3. Export a portable snapshot if you want an extra rollback artifact.
4. Run the JSON-to-SQLite migration into the same `DATA_DIR`.
5. Run an integrity check against the SQLite backend.
6. Start the node with `STORAGE_BACKEND=sqlite`.
7. Keep the JSON backup until the SQLite node has been verified after restart.

Example migration flow:

```powershell
.\.venv\Scripts\python.exe .\scripts\storage_backup.py --data-dir data\node-a --storage-backend json
.\.venv\Scripts\python.exe .\scripts\storage_export.py --data-dir data\node-a --output data\node-a\exports\node-a-before-sqlite.json
.\.venv\Scripts\python.exe -c "from storage_migration import migrate_json_to_sqlite; print(migrate_json_to_sqlite(source_json_path='data/node-a/blockchain.json', sqlite_db_path='data/node-a/zoidbergchain.db'))"
$env:DATA_DIR = "data\node-a"
$env:STORAGE_BACKEND = "sqlite"
.\.venv\Scripts\python.exe -c "from storage import create_storage_backend, check_storage_integrity; backend = create_storage_backend(); print(check_storage_integrity(backend))"
```

Migration refuses malformed source snapshots and refuses to overwrite existing SQLite data unless overwrite is explicitly requested.

## Recommended Workflow

For local operators and test environments:

1. Use `DATA_DIR` per node.
2. Keep `STORAGE_BACKEND=json` unless you are actively validating SQLite.
3. Back up before imports, overwrites, or backend migration.
4. Run integrity checks after any storage operation that changes persisted state.
5. Verify a restart before deleting older backups.

## Known Limitations

- Exports exclude private keys by default.
- Dev exports that include private keys should be treated as highly sensitive.
- Always back up before import with `--overwrite`.
- SQLite is available for opt-in validation, but JSON remains the default backend until a later task changes rollout guidance.
- The migration path currently copies whole persisted sections as-is; schema normalization is intentionally deferred.
- Backup, export, and import work at the storage snapshot level and do not change consensus or peer-authentication behavior.
