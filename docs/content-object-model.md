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

- `content_hash` is the canonical payload hash.
- `content_id` is derived from `content_hash` so the same payload gets the same identifier.
- Raw binary data is not stored in the object.

## Storage Status Meanings

- `missing`: referenced but not available locally.
- `local`: present locally but not yet fully verified.
- `remote`: known from peer metadata but not local.
- `verified`: present locally and hash validation has passed.

## Scope Note

Binary file transport, upload/download endpoints, and peer content sync are deferred to later Task 6 work.
