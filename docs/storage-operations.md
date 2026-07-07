# Storage Operations

Task 5.6 adds operator-facing tools for backup, export, and import.

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

## Notes

- Exports exclude private keys by default.
- Dev exports that include private keys should be treated as highly sensitive.
- Always back up before import with `--overwrite`.
