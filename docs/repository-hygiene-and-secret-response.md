# Repository Hygiene and Secret Response

## Scope

Milestone 2 Task 2 removes generated and mutable files from the current Git tree only. It does not change Protocol v1 serialization, hashes, genesis, signing, replay protection, nonce rules, certificates, fork choice, finality, source dependencies, deployment configuration, or Git history.

## Removed From Tracking

The current tree no longer tracks local `.env` data, mutable blockchain/peer/wallet state, `.bak` state copies, SQLite runtime data, uploaded-content caches, temporary media, a generated Python virtual environment, diagnostics, or local patch artifacts. These files can change while a node runs and must be stored as operator-owned state, not source code.

Model A remains unchanged: accepted media bytes belong in the immutable block record. This is distinct from `content/`, which is a mutable node cache used to store submitted or retrieved content. The canonical public-testnet genesis media is retained in `public_testnet_v1_genesis_meme_base64.txt`, validated by `protocol_v1_genesis.py`; it is not a runtime cache.

## Intentionally Retained Assets

Protocol v1 modules, `protocol_v1_genesis.py`, the canonical genesis base64 fixture, `tests/fixtures/protocol_v1_golden_vectors.json`, intentional test fixtures, static website/whitepaper assets, deployment examples, documentation, and `.env.example` remain tracked. They are reproducible source, test, documentation, or explicitly canonical protocol material.

## Secret Response Required From Owners

The previously tracked root environment file contained concrete API credentials. Treat that credential category as exposed and revoke or rotate every affected API credential.

Previously tracked blockchain state contained private-key material. Treat affected wallet and signing identities as potentially compromised; owners must identify them and replace/move any non-disposable funds or identities. Peer and wallet state may also expose operational identities or credentials and requires owner review.

Deleting files from the current tree does not remove prior commits. Owners must decide whether to use an approved Git-history cleanup process, such as `git filter-repo` or BFG followed by coordinated force-push and fresh clones, or to retain history with the exposure documented. This task deliberately does not rewrite history, rotate credentials, reset servers, or alter deployments.

## Clean Clone Expectations

Create a local `.env` from `.env.example`, then replace every public-node placeholder using a secret manager or platform-managed configuration. Public nodes must use `ENVIRONMENT=testnet` or `production`, set a unique peer secret, keep signed peer messages and peer authentication enabled, and leave development wallet export/reset/insecure-peer settings disabled. Keep admin password hashes and bootstrap tokens server-side; never place them in frontend environment files.

Configure `NODE_DATA_DIR` (and, when applicable, SQLite, content, and log paths) outside the repository. Store node state, backups/exports, wallets/private keys, peer secrets, API credentials, and admin credentials in access-controlled operator storage with a tested recovery procedure. Do not copy them into Git.

## Verification Limitation

The inherited Windows frontend limitation remains: `npm ci` cannot unlink the existing `esbuild.exe`, leaving required frontend modules unavailable. Frontend source and dependencies were not changed in this task; frontend tests/build should be retried after the local lock or permission problem is resolved.
