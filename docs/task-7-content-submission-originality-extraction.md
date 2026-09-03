# Task 7 Content, Submission, and Originality Extraction

`ContentCoordinationService` owns content uniqueness, content-object lookup and
registration, binary/text upload coordination, storage status refresh, and
block-media recovery. `SubmissionOriginalityService` owns submission status
changes, hard rejection, voting, vote summaries/locks, certificate lookup and
linking, threshold calculation, and certificate construction.
`MintQueueService` owns admission, queue eligibility records, manual holds,
unblocking, and invalid-entry cleanup.

The authoritative persisted collections remain `Blockchain.submissions`,
`content_objects`, `votes`, `originality_certificates`, and `mint_queue`.
Services receive short-lived explicit state views that reference those exact
lists and never persist independently. A reload replaces facade lists as it did
before, and subsequent calls construct new state views, avoiding stale refs.

The services depend only on existing domain helpers plus injected storage
lookups and narrowly scoped facade callbacks for active-user counts, content
promotion, certificate validation, persistence, and block lookup. No service
imports `Blockchain`, `api`, or FastAPI.

Block construction, block acceptance, chain validation, fork choice, finality,
peer sync, native transactions, balances, and rewards remain in `Blockchain`.
`mint_submission` and `mint_next_queued_submission` remain there because their
existing atomic flow couples queue selection to `add_block`, rewards, canonical
reconciliation, and persistence. Model A is unchanged: immutable Protocol v1
blocks remain the authority for full media bytes, and the local content store
remains a cache. Existing helpers retain content hash/ID, MIME, filename, text,
certificate, and vote-ordering determinism with unchanged JSON/SQLite sections.
