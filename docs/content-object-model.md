# Content Object Model

Task 6.1 introduces a first-class content object so meme payloads can be tracked separately from submission records.

## Core Fields

- `content_id`: a deterministic identifier derived from `content_hash`.
- `content_hash`: the canonical hash for the content payload.
- `content_type`: one of `image`, `text`, or `mixed`.
- `mime_type`: the declared MIME type for the payload.
- `file_name`: optional filename metadata.
- `file_size_bytes`: optional size metadata.
- `storage_status`: one of `missing`, `local`, `remote`, or `verified`.
- `local_path`: optional local file reference.
- `text_content`: optional text payload.
- `caption`: optional human-readable caption or alt text.
- `submitted_by`: the wallet or actor that submitted the content.
- `created_at`: timestamp for when the object was created.
- `network_name`: the network this content belongs to.
- `metadata`: optional JSON-safe metadata.

## Hash And ID Rules

- `content_hash` remains the canonical payload hash used by the current submission and certificate workflow.
- `content_id` is derived from `content_hash` so the same payload gets the same identifier.
- Local binary files are stored separately under `CONTENT_STORAGE_DIR`.
- For locally stored files, the node also records a raw-byte SHA-256 sidecar so file integrity can be re-verified without changing consensus-facing submission hashes.
- Raw binary data is not embedded in the object or portable storage export yet.

## Local Content Storage

- `CONTENT_STORAGE_DIR` defaults to `DATA_DIR/content/`.
- Node A and Node B should use separate `DATA_DIR` values so their content stores stay isolated.
- Stored file paths are derived from `content_hash`, never from user-supplied filenames.
- Supported MIME types in Task 6.2 are `image/jpeg`, `image/png`, `image/gif`, `image/webp`, and `text/plain`.
- `MAX_CONTENT_FILE_SIZE_BYTES` defaults to `5 * 1024 * 1024` bytes for local development and testnet use.

## Storage Status Meanings

- `missing`: referenced but not available locally.
- `local`: present locally but not yet fully verified.
- `remote`: known from peer metadata but not local.
- `verified`: present locally and hash validation has passed.

## Scope Note

- API upload/download endpoints are deferred to Task 6.3.
- Peer content sync is deferred to Task 6.4.
