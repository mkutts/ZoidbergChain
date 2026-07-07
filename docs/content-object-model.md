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
- `hash_scheme`: one of `sha256_bytes`, `sha256_text`, `legacy`, or `unknown`.
- `verified_at`: optional timestamp for the last successful payload verification.
- `verification_error`: optional short verification status such as `missing_file`, `hash_mismatch`, or `legacy_unverifiable`.
- `local_path`: optional local file reference.
- `text_content`: optional text payload.
- `caption`: optional human-readable caption or alt text.
- `submitted_by`: the wallet or actor that submitted the content.
- `created_at`: timestamp for when the object was created.
- `network_name`: the network this content belongs to.
- `metadata`: optional JSON-safe metadata.

## Hash And ID Rules

- `content_hash` remains the canonical payload hash used by the current submission and certificate workflow.
- `content_hash` is consensus-critical for submissions, certificates, and certified blocks, so it is never silently rewritten.
- `content_id` is derived from `content_hash` so the same payload gets the same identifier.
- Local binary files are stored separately under `CONTENT_STORAGE_DIR`.
- For locally stored files, the node also records a raw-byte SHA-256 sidecar so file integrity can be re-verified without changing consensus-facing submission hashes.
- Raw binary data is not embedded in the object or portable storage export yet.

Canonical hash rules:

- Binary content: `content_hash = SHA-256(raw file bytes)` and `hash_scheme = sha256_bytes`
- Text content: `content_hash = SHA-256(canonical UTF-8 text bytes)` and `hash_scheme = sha256_text`
- Text canonicalization uses UTF-8 encoding, normalizes line endings to `\n`, and trims outer whitespace before hashing
- Mixed content keeps the binary payload hash; caption or text metadata does not change the binary `content_hash`
- Older records that do not follow these rules are treated as `legacy` or `unknown` and are not auto-rewritten

## Local Content Storage

- `CONTENT_STORAGE_DIR` defaults to `DATA_DIR/content/`.
- Node A and Node B should use separate `DATA_DIR` values so their content stores stay isolated.
- Stored file paths are derived from `content_hash`, never from user-supplied filenames.
- Supported MIME types in Task 6.2 are `image/jpeg`, `image/png`, `image/gif`, `image/webp`, and `text/plain`.
- `MAX_CONTENT_FILE_SIZE_BYTES` defaults to `5 * 1024 * 1024` bytes for local development and testnet use.

## API Access

Task 6.3 and Task 6.4 add local and peer-safe content access:

- `POST /content/upload`
- `POST /content/text`
- `GET /content/{content_hash}`
- `GET /content/{content_hash}/metadata`
- `GET /peers/content/{content_hash}/metadata`
- `GET /peers/content/{content_hash}`
- `POST /content/{content_hash}/sync`

Rules:

- uploads validate size, MIME type, and submitter identity
- downloads resolve content only through `content_hash`
- peer content endpoints reuse the existing peer auth or signed-message protections
- manual content sync is development-only and fetches from active peers without changing consensus data
- public responses never expose `local_path` or other internal filesystem details
- upload-first then submit-by-`content_hash` is supported for later submission workflows

## Storage Status Meanings

- `missing`: referenced but not available locally.
- `local`: present locally but not verified against the consensus-facing `content_hash`.
- `remote`: known from peer metadata but not local.
- `verified`: present locally and payload verification against `content_hash` has passed under the active `hash_scheme`.

## Peer Sync Behavior

- Peer submissions, certificates, and certified blocks may create remote content references even when the local node does not have the binary yet.
- Missing local binaries do not invalidate otherwise valid peer metadata, certificate sync, or chain sync.
- `sync_missing_content(...)` fetches peer metadata first, then the payload, enforces the size limit, verifies the payload hash, stores the local copy, and marks the content object `verified`.
- Portable storage export and import still include content metadata only. Raw content bytes stay node-local until a later task expands transport or export scope.

## Legacy Notes

- Legacy submissions can still load, evaluate, certify, and mint under the existing consensus rules.
- Legacy or unknown content hashes may remain in `local`, `missing`, or `remote` state even when a file exists, because the file may not be safely provable against `content_hash`.
- A hash mismatch should be diagnosed by checking `hash_scheme`, `verification_error`, and whether the local file was created through the upload-first path or through an older submission flow.
