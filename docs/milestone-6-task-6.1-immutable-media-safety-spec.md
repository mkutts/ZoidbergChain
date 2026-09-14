# Milestone 6 Task 6.1 — Immutable-media admission audit and Public Testnet v1 safety specification

Status: Task 6.1 audit/specification only  
Audit date: 2026-09-13  
Audited branch: `main`  
Audited HEAD: `f5893cc4e6a74d5f44a4ec422e0993fd1a6c53bb`  
Protocol behavior changed by this task: **none**

## 1. Decision and scope

This document is the implementation contract for later Milestone 6 tasks. It is
not an assertion that the current node already satisfies the target contract.
Tasks 6.2 and later must implement and activate the contract through an explicit,
versioned Public Testnet v1 transition. Task 6.1 changes no API, consensus,
storage, validation, moderation, or finality behavior.

The following project decisions are fixed:

1. ZoidbergChain is an independent Layer 1 and ZOID is its native coin. ZOID is
   not an ERC-20 token.
2. MetaMask `personal_sign` / Ethereum-style `0x` signatures establish user
   identity and intent; they do not make ZOID or media operations Ethereum
   transactions.
3. Certified Meme Proof of Originality content earns blocks.
4. One accepted media submission creates exactly one blockchain block.
5. Model A is mandatory: the complete accepted media byte sequence is part of
   immutable blockchain state.
6. Hostile-content risk is handled before minting. Once finalized, a block and
   its media are never deleted, pruned, rewritten, replaced, or redacted.

The audit follows every current path by which content can become, or influence,
permanent chain state:

`upload -> temporary storage -> authentication/signature -> technical media processing -> OCR/hash/originality -> community review -> certification -> mint queue -> candidate construction -> validation -> commit -> persistence -> peer sync/import/recovery -> finality`

It also covers public serving and browser preview because unsafe rendering can
turn a correctly preserved hostile payload into an endpoint or reviewer risk.

## 2. Repository and baseline verification

Before editing, the repository was on `main` at
`f5893cc4e6a74d5f44a4ec422e0993fd1a6c53bb`, tracking `origin/main`, with no
staged, modified, or untracked files. The expected Milestone 5 sequence was
committed:

| Commit | Recorded purpose |
| --- | --- |
| `f5893cc` | Milestone 5 completion/release readiness |
| `b6cd456` | Task 5.8 |
| `b16bc63` | Task 5.7 |
| `4ae367f` | Task 5.6 |
| `711830b` and `5ec94a9` | Task 5.5 / preceding reviewer-policy work |
| `5b84776` | Task 5.3 |
| `0b53f84` | Tasks 5.1 and 5.2 |

The Milestone 5 release report says all twenty Milestone 5 criteria pass and the
current full suite contains 1,152 tests. This audit reproduced that baseline:

| Command | Result |
| --- | --- |
| `python -m pytest` | 1,118 passed; 34 setup errors after Windows denied pytest access to the system temp root. No assertion failed. |
| `python -m pytest --basetemp .pytest_task61_baseline` | **1,152 passed in 283.67 s**. The audit-created temp directory was then removed. |
| Originality runtime inspection | Pillow 12.3.0; `Image.MAX_IMAGE_PIXELS=89,478,485`; ImageHash 4.3.1; pytesseract 0.3.13. |

## 3. Current media acceptance profile

### 3.1 Types actually accepted

The normal upload-first API accepts these media MIME types:

| Media kind | MIME | Current hash/stored-byte rule |
| --- | --- | --- |
| JPEG image | `image/jpeg` | SHA-256 of the original uploaded bytes |
| PNG image | `image/png` | SHA-256 of the original uploaded bytes |
| GIF image | `image/gif` | SHA-256 of the original uploaded bytes |
| WebP image | `image/webp` | SHA-256 of the original uploaded bytes |
| Plain text | `text/plain` | UTF-8, line endings normalized to LF and outer whitespace trimmed; SHA-256 of those canonical bytes |

`image`, `text`, and `mixed` are content classifications, not additional media
formats. `mixed` currently means binary image bytes plus text/caption metadata;
the binary bytes alone determine `content_hash`.

The primary frontend upload picker advertises `.jpg`, `.jpeg`, `.png`, `.webp`,
`.gif`, and `.txt`. Its optional image picker advertises only `.jpg`, `.jpeg`,
`.png`, and `.webp`, even though the backend image allowlist includes GIF. The
development-only direct-submission error text also omits GIF. Browser file
`accept` filters are advisory and are not security controls.

Legacy and compatibility records broaden the effective input surface:

- old content objects can use `legacy` or `unknown` hash schemes;
- legacy submission construction can infer MIME from a filename extension or
  fall back to `image/jpeg` / `application/octet-stream` metadata;
- development-only `/add_block` can create a non-certified legacy block;
- chain validation retains legacy block compatibility rather than requiring all
  non-genesis blocks to carry Protocol v1 media and admission evidence.

### 3.2 Sources of MIME and type assumptions

| Source | Current use | Trust/problem |
| --- | --- | --- |
| Browser multipart `UploadFile.content_type` | Declared MIME at upload | Client-controlled. `application/octet-stream` becomes no declaration. |
| Magic-prefix sniffer in `content.py` | Detects JPEG, PNG, GIF, and WebP; otherwise accepts valid UTF-8 without NUL as text | Header-level identification only; it does not prove the complete file decodes or is one well-formed container. |
| `mimetypes.guess_type(filename)` | Candidate construction and legacy reconstruction | Extension/host mapping assumption, not byte evidence. |
| `SUPPORTED_*_MIME_TYPES` copied from `config.py` | API, content storage, and validation allowlists | Values are imported as process-local configuration rather than frozen network policy data. |
| `ENABLE_STRICT_MIME_VALIDATION` | Controls declared/detected mismatch rejection | Environment-configurable; differing validators can disagree. |
| `content_type_hint` | Allows `image`, `text`, or `mixed` metadata | Client-controlled classification; only a narrow image/text correction is applied. |
| Peer content metadata | Creates remote/missing content references | Authenticated peer input, but still untrusted. Local path is intentionally ignored. |
| Protocol v1 block fields | `mime_type` and `content_type` are rechecked against embedded bytes | Recheck uses the same configurable allowlist/header sniffer, not a full decoder. |

### 3.3 Current limits and enforcement points

| Limit | Current value/default | Enforced at | Gaps |
| --- | --- | --- | --- |
| General content payload | 5 MiB (`5,242,880` bytes), environment-configurable | `validate_content_size`, storage, normal upload after `UploadFile.read()`, peer content after download, Protocol v1 media validation | Upload/peer/base64 bodies are fully materialized before rejection. Because this value participates in block acceptance, operator overrides can split consensus. |
| Plain-text content | 256 KiB (`262,144` bytes), environment-configurable | Canonical text validation/storage when MIME is known as text | JSON request is parsed before the byte limit. Peer or legacy metadata can delay correct classification. |
| Candidate block estimate | 500 KB by default, call-parameter configurable | Local `BlockProductionService` only | Approximate sum of base64 character count, text and transaction estimates. It is not canonical serialized size and is not checked by block validation. A 5 MiB image cannot normally fit. |
| Submission `text_content` | 4,096 characters | Multipart form schema | Character, not byte, cap. It is not the same as the text-media byte cap and is not fully bound by the current submission signature. |
| Caption | 1,000 characters, environment-configurable | API schema and content validation | Character, not byte, cap; existing content-object metadata can be updated. |
| Original filename metadata | 255 sanitized ASCII characters, environment-configurable | Filename sanitizer | Display metadata only. The normal store correctly derives paths from hash. |
| Signature/message fields | 4,096 characters | Submission/vote form schemas | No complete request-body cap. |
| Peer/block/snapshot aggregate | None | Not enforced | Full base64 media, whole chain pages, and snapshot files can allocate unbounded aggregate memory before per-media validation. |
| Image width/height | None explicit | Not enforced | Pillow's installed default pixel guard is library-global, warning-based below its error threshold, and not network policy. |
| Image decoded pixels | None explicit | Not enforced | Current Pillow default is 89,478,485 pixels, but it is neither pinned in protocol data nor consistently promoted from warning to rejection. |
| Animation frames/duration/aggregate decoded pixels | None | Not enforced | Hash/OCR paths generally inspect the first frame while the public browser can render the complete animation. |
| Decode/OCR CPU, wall time, or memory | None | Not enforced | Pillow and Tesseract run without an admission sandbox or hard timeout. |

No current reverse proxy/body-size setting is a protocol guarantee. Operational
limits may reduce exposure, but every node must enforce the consensus-relevant
limits itself.

## 4. Current path audit

### 4.1 Upload and initial storage

`POST /content/upload` reads the complete multipart file before checking the
5 MiB cap. `POST /content/text` lets request parsing allocate the complete JSON
string before applying the 256 KiB canonical-text cap. Both routes rate-limit
requests, but neither route requires a verified wallet session or checks that
`submitted_by` belongs to the caller. Any syntactically valid `0x` address can
therefore be attributed to content already written into the durable content
cache.

Normal storage is content-addressed and uses a temp file, `fsync`, and atomic
replace under `DATA_DIR/content`. That is a useful integrity boundary, but it is
not a quarantine: untrusted bytes immediately enter the durable cache and can be
served back. A SHA-256 sidecar detects later file corruption. User filenames are
sanitized and are not used for normal storage paths.

The development-only direct submission path writes to `SUBMISSIONS_DIR` under a
sanitized user filename, not a unique hash-derived name. Concurrent equal names
can collide or overwrite before the `finally` cleanup. This route is disabled
outside development, but its service-level compatibility methods remain inputs
to tests, imports, and maintenance code.

### 4.2 Authentication and signed intent

The supported submission route does require a verified wallet session, beta
submission eligibility, and a MetaMask `personal_sign` signature. The challenge
binds wallet, network name, content hash, content ID, caption, nonce, and expiry.
It does not bind all later user-visible/chain metadata: notably the separately
posted `text_content`, an admission policy identity, byte length, canonical MIME,
technical evidence, safety decision, or a rights/safety attestation.

Upload occurs before this signature and can be called directly without the UI's
wallet checks. Challenges and sessions are in process memory. Peer submission
normalization verifies that a supplied signature recovers the submitter, but it
does not reconstruct and validate the complete canonical challenge binding; it
also accepts an unsigned submission from an authenticated peer.

### 4.3 Technical processing, hashes, OCR, and originality

Positive controls already present are SHA-256 content addressing, byte/hash
verification, supported-MIME allowlists, exact duplicate detection against the
canonical minted corpus, deterministic aHash/dHash review signals, and pinned
Pillow/ImageHash dependencies for certificate consensus.

The technical safety gaps are material:

- image admission checks a short signature only; corrupt/truncated files and
  polyglots can reach the decoder and durable cache;
- there is no explicit width, height, decoded-pixel, frame, metadata, CPU, wall
  time, or memory limit;
- `Image.open`, perceptual hashing, and Tesseract execute in the API/node process;
- OCR has no timeout and catches failures as missing text; raw paths/text can be
  logged;
- animated GIF/WebP content is not reviewed equivalently to what browsers render;
- certificate-consensus OCR is deliberately disabled for determinism, so OCR is
  `UNAVAILABLE` and only a review signal;
- local non-consensus OCR is platform-dependent;
- a client can label image bytes `mixed`, and caption/text metadata are not part
  of the binary `content_hash`;
- integrity verification proves hash equality, not safe decodability or policy
  admissibility;
- legacy/unknown objects can be reported as `legacy_unverifiable` without an
  immediate hard stop at every compatibility boundary.

Exact SHA-256 duplicates of minted media hard-reject before voting. Fuzzy image
or OCR similarity only flags the submission for review and never hard-rejects.
This is the correct Milestone 5 originality rule, but it is not a hostile-content
admission rule.

### 4.4 Community review and certification

The community currently votes only `original`, `not_original`, or `unsure`.
There is no independent vote/report for malformed, illegal, abusive, private,
malware-bearing, incorrectly classified, or otherwise prohibited content.
Reviewers and public clients receive the original media URL and the frontend
renders image media directly.

Certificate v3 correctly binds originality evidence, a finalized-chain reviewer
snapshot, fixed quorum (at least 5 valid votes including at least 1 established
reviewer), and a 70% ORIGINAL share of decisive votes. `UNSURE` counts toward the
five valid votes but not the decisive denominator. No certificate field binds a
media-admission rule version, full technical report, safety-policy decision,
reviewed preview digest, or submitter attestation.

`POST /submissions/{id}/evaluate` has no wallet or operator authorization. A
caller can trigger evaluation, and an explicit false
`automated_originality_passed` can force rejection. Approval/certificate/queue
writes are multiple saves rather than one atomic state transition, leaving crash
and race windows before the later atomic mint boundary.

### 4.5 Mint queue, candidate, validation, and commit

The queue requires approval and a certificate and blocks known hard-rejected or
manually mint-blocked submissions. Compatibility evaluation can still describe
legacy-unverifiable media as mintable. Manual mint blocking is local mutable app
state, not consensus evidence, so it cannot stop another validator from
accepting an otherwise valid peer block.

The public mint endpoints have rate limits but no verified-wallet or operator
authorization. Any caller can ask the node to mint an already queued item. The
atomic certified commit is nevertheless a strong current control: it reloads
durable state under a compare-and-swap/transaction boundary, rechecks the head,
certificate, queue, and media, and atomically appends the block, consumes the
submission/certificate, applies rewards/transactions, marks the submission
minted, and removes it from the queue.

Protocol v1 candidates re-read the source bytes and require the resulting
canonical content hash to equal the certificate hash. The full bytes are encoded
in `media_bytes`, included in the block's canonical hash payload, and checked as
`media_hash == content_hash == SHA-256(embedded accepted bytes)`. This is the
current Model A foundation.

Candidate construction can still run unbounded OCR and image hashing. Its
500 KB estimate is local and approximate. Candidate/chain validation checks
declared MIME, current configured size limits, content classification, hash,
certificate metadata, transactions, linkage, and block hash. It does not fully
decode the image, apply explicit resource limits, enforce a safety policy, or
require an admission certificate. The configurable size and strict-MIME values
are consensus inputs without being frozen network data.

Legacy non-genesis blocks do not require Protocol v1 embedded-media/certificate
fields. The direct legacy block endpoint is development-gated, but import and
peer chain compatibility can still present legacy history to the validator.

### 4.6 Persistence, sync, import, recovery, and finality

Accepted Protocol v1 media live inside each block record, so JSON, SQLite section
storage, backup, and export preserve the complete base64-wrapped bytes. Pending
content files remain separate under `DATA_DIR/content`; portable export does not
copy them. Import normalizes missing content objects accordingly.

JSON storage uses temp/`fsync`/replace plus a backup; SQLite uses transactions,
canonical uniqueness claims, and backup support. Startup reconstructs blocks and
runs full chain validation, so corrupt protocol media eventually fails closed.
The standalone JSON-to-SQLite migration and portable import validate shape,
genesis/network metadata, counts/references, and storage integrity, but do not
fully validate every block/media object before writing the target. A bad import
can therefore be acknowledged/written before a later node startup rejects it.
Snapshot files have no aggregate size cap and are loaded as complete JSON.

Authenticated peer content sync downloads `response.content` completely before
checking the payload cap. Peer evidence and block routes decode base64 before
enforcing decoded-size limits. Chain sync requests full media and can receive an
unbounded aggregate page. Certificate/originality evidence can be persisted
before the candidate chain is fully validated, leaving orphan auxiliary state
when adoption fails. The peer originality-evidence GET route currently has its
success return indented after the unavailable-media exception, so the success
case returns no payload.

For Protocol v1 blocks, embedded media are authoritative. Recovery falls back to
the content cache only for older/non-embedded records. External content-path
resolution accepts an absolute local path from persisted local metadata; the
hash check limits content substitution but the path is not confined to the
content root.

Finality is validator-quorum evidence, not deletion or content moderation. Once
a quorum-finalized `(height, block_hash)` exists, fork choice/replacement must
preserve that block at that height. Current public media endpoints still serve
finalized raw media with its declared MIME, and the frontend can render it. There
is no post-finality dispute/presentation-suppression record. Under Model A, such
a record may hide or warn in products, but can never remove or alter chain bytes.

## 5. Threat and bypass matrix

Severity is relative to a public node carrying immutable media. “Required gate”
describes later Milestone 6 work, not current behavior.

| ID | Boundary | Entry/bypass | Impact | Current control | Required gate | Severity |
| --- | --- | --- | --- | --- | --- | --- | --- |
| M6-T01 | Multipart upload | Oversized body is read before size check | Memory/worker exhaustion | 5 MiB post-read check, rate limit | Streaming byte counter and total request cap before buffering | Critical |
| M6-T02 | Text upload | Huge JSON string parsed before canonical byte check | Memory exhaustion | 256 KiB post-parse check | Request cap plus incremental/early validation | High |
| M6-T03 | Upload identity | Arbitrary syntactically valid `0x` submitter | Spoofed attribution, cache spam | UI asks for verified wallet | Backend session ownership check before accepting bytes | High |
| M6-T04 | Initial storage | Unscanned bytes enter durable served cache | Hostile retention/exposure before submission | Atomic hash-addressed store | Non-public quarantine with TTL and atomic promotion only after admission | Critical |
| M6-T05 | Dev temp storage | Filename collision/overwrite | Cross-request mutation or wrong bytes processed | Sanitization and final cleanup | Unique server-generated quarantine name | Medium (dev-gated) |
| M6-T06 | MIME | Valid prefix plus corrupt/trailing/polyglot payload | Decoder exploit or misclassification | Magic-prefix sniffer | Pinned full-container parser; reject trailing/embedded active payloads | Critical |
| M6-T07 | Validator config | Different size/strict-MIME env values | Honest nodes disagree on block validity | Shared deployment convention | Frozen policy ID/digest and startup mismatch refusal | Critical |
| M6-T08 | Image decode | Pixel/decompression bomb | CPU/RAM exhaustion | Pillow library default only | Explicit dimensions, decoded budget, sandbox, timeout | Critical |
| M6-T09 | Animation | Harm appears after frame 1 or frame bomb | Reviewer bypass/resource abuse | Full-byte exact hash | Validate every frame and review a deterministic contact sheet/animation | High |
| M6-T10 | OCR/hash | Unbounded in-process Pillow/Tesseract | Node crash/hang; sensitive logs | Exceptions become failure/review | Isolated bounded worker; no raw content logging | High |
| M6-T11 | Type hint/metadata | Image labeled mixed/text metadata differs | Review/signature semantics diverge | Small normalization rules | Derive type from bytes; sign canonical metadata digest | High |
| M6-T12 | Signed submission | Posted `text_content` and safety policy not signed | Altered meaning after signature | Hash/content ID/caption challenge | Sign exact bytes hash, byte count, MIME/type, metadata and policy digests | Critical |
| M6-T13 | Peer submission | Unsigned or incompletely rebound signed record | Bypass local user-auth/intention checks | Active peer authentication | Reconstruct exact signed intent; reject unsigned Public Testnet submissions | Critical |
| M6-T14 | Originality | Exact/fuzzy checks mistaken for safety checks | Prohibited original content can pass | Exact hard reject; review signals | Separate admissibility decision before originality | Critical |
| M6-T15 | Reviewer UI | Raw original rendered directly | Reviewer/browser exposure | MIME response and normal browser sandboxing | Safe derived preview, click-through warning, no raw auto-render | Critical |
| M6-T16 | Community vote | Only originality choices exist | No safety report/rejection path | `UNSURE` option | Separate report/admissibility states and authorized policy review | Critical |
| M6-T17 | Evaluation API | Unauthenticated evaluation/false override | Premature or forced rejection | Rate limit and state checks | Authorized/idempotent admission+originality command; no client verdict override | High |
| M6-T18 | Certificate | No admission-policy/evidence binding | Valid originality certificate can certify unsafe media | v3 evidence/reviewer binding | Admission certificate/digest required by originality cert and block | Critical |
| M6-T19 | Mint queue | Local `mint_blocked` and legacy compatibility | Another node can ignore local stop; compatibility ambiguity | Local queue checks | Consensus-verifiable admission status; no legacy admission after activation | Critical |
| M6-T20 | Mint API | Anyone can trigger queued mint | Timing/operational abuse | Only queued certified item can mint | Validator/operator authorization or deterministic scheduler | Medium |
| M6-T21 | Candidate size | 500 KB approximation differs from actual block | Unbounded/oversized accepted block or inconsistent production | Local estimate | Canonical serialized block/media limits validated by every node | Critical |
| M6-T22 | Candidate source | File changes between review and read | Wrong reviewed bytes attempted | Certificate hash mismatch stops local mint | Immutable quarantine object and recheck at every transition | High |
| M6-T23 | Block validation | Header-valid hostile image passes | Permanent hostile bytes | SHA/MIME/size/hash checks | Full technical admission evidence and policy certificate | Critical |
| M6-T24 | Legacy block | Non-Protocol-v1 block omits Model A/admission fields | Bypass one-submission/one-block policy | Dev API gate; historical compatibility | Activation-height rule; reject newly introduced legacy blocks | Critical |
| M6-T25 | Persistence/import | Shape-valid invalid chain is written first | Corrupt target/unavailable restart | Startup full validation | Stream and fully validate staged snapshot before atomic replacement | High |
| M6-T26 | Peer content | Complete response/base64 decoded before cap | Memory exhaustion | Post-download size/hash/MIME checks | Encoded and decoded streaming caps | High |
| M6-T27 | Chain sync | Unbounded page with full media | Memory/disk exhaustion | Request timeout and later chain validation | Paginated byte budget; per-block validation before staging | Critical |
| M6-T28 | Sync ordering | Evidence/certs persisted before chain adoption | Orphan/conflicting auxiliary state | Conflict checks | One staged/atomic adoption transaction | High |
| M6-T29 | Recovery path | Absolute persisted local path accepted | Reads outside managed content root | Hash equality required | Confine paths; Protocol v1 recovery from block bytes only | Medium |
| M6-T30 | Public serving | Raw accepted bytes served/rendered by MIME | Exploit, shock content, browser sniffing | Hash verification | Safe derivatives, `nosniff`, CSP/download isolation, presentation policy | Critical |
| M6-T31 | Finalized dispute | No hide/warn/report state | Ongoing public exposure | None | Non-destructive presentation suppression and audit trail | High |
| M6-T32 | Content metadata | Existing object fields can be updated by later upload | Attribution/caption drift | Byte hash remains stable | Immutable signed metadata version; append-only corrections | High |

## 6. Normative Public Testnet v1 immutable-media safety contract

The terms **MUST**, **MUST NOT**, **SHOULD**, and **MAY** are normative for Tasks
6.2–6.11. This contract is inactive until an explicit activation height and
policy digest are implemented and agreed by Public Testnet validators.

### 6.1 Canonical accepted media

1. “Uploaded bytes” are untrusted, temporary input. “Accepted media bytes” are
   the exact post-technical-admission bytes presented to the submitter and
   reviewers, signed by the submitter, certified, embedded in the block, hashed
   by the block, persisted, synchronized, recovered, and finalized.
2. A service MAY create a normalized safe candidate from uploaded bytes. It MUST
   never silently substitute it. The resulting bytes get a new SHA-256 hash and
   require explicit user preview and signature.
3. Images use `SHA-256(accepted_media_bytes)`. Plain text first undergoes the
   existing LF/outer-whitespace canonicalization; the resulting UTF-8 sequence
   is the accepted media byte sequence and is hashed directly.
4. A `mixed` submission consists of accepted image bytes plus separately
   canonicalized signed text metadata. The image hash alone MUST NOT be treated
   as proof of the mixed submission's complete meaning. A canonical metadata
   digest MUST bind the caption/text into signed intent, admission evidence,
   certificate, and block.
5. No mutable file path, filename, URL, MIME claim, caption, or database row can
   be an authority for bytes. SHA-256 plus the embedded canonical byte wrapper is
   authoritative.

### 6.2 Frozen admission profile

Public Testnet v1 MUST activate a single network-data object named
`zoidberg-public-testnet-v1/media-admission/1`, with a canonical digest embedded
in admission evidence, certificates, and Protocol v1 media blocks. Environment
variables may be stricter for local upload protection but MUST NOT relax or
reinterpret consensus acceptance.

The initial profile is:

| Rule | Normative value |
| --- | --- |
| Staged uploaded payload | At most 5 MiB (`5,242,880` bytes); never public or mintable |
| Multipart request body | At most 5 MiB + 64 KiB (`5,308,416` bytes) before/during streaming |
| Text-upload JSON body | At most 320 KiB (`327,680` bytes) before parsing |
| Accepted immutable image bytes | At most 256 KiB (`262,144` bytes) |
| Accepted immutable plain-text bytes | At most 256 KiB (`262,144` bytes) after canonicalization |
| Accepted MIME types | Exactly JPEG, PNG, GIF, WebP, and plain UTF-8 text as listed in section 3.1 |
| Image width or height | Each at most 4,096 pixels and at least 1 pixel |
| Image frame count | At most 60; every frame must validate |
| Aggregate decoded pixels | `sum(width * height for every frame) <= 16,777,216` |
| Decoded color model | Convertible to RGB/RGBA by the pinned decoder without error |
| Caption | At most 1,000 Unicode scalar values and 4,096 UTF-8 bytes |
| Submission text metadata | At most 4,096 Unicode scalar values and 16,384 UTF-8 bytes |
| Sanitized display filename | At most 255 ASCII bytes; never hashed as media or used as a path |
| Canonical serialized non-genesis block | At most 512 KiB (`524,288` bytes), checked by producer and validator |
| Peer single encoded media field | Base64 length must be checked before decode and decode to no more than the applicable accepted-media limit |
| Peer chain page | At most 64 blocks and 16 MiB encoded response, whichever is reached first |

Decoder and OCR workers MUST run outside the node/API process with a hard
wall-clock timeout, CPU quota, memory quota, no network, an empty working
directory, and no inherited secrets. Initial operational ceilings are 2 seconds
for structural decode and 5 seconds for OCR, with 256 MiB worker memory. Timeout
or resource-limit termination is a failed admission, never a pass. These
operational ceilings are denial-of-service controls; deterministic technical
evidence comes from structural results and the pinned decoder identity, not from
whether a particular machine was fast enough.

All frames and container structures MUST be parsed to end-of-stream. Truncated
input, parser warnings, unexpected trailing payloads, embedded active content,
archive/polyglot structures, invalid frame tables, or unsupported metadata MUST
fail closed. The pinned decoder/library build and its rule identity MUST be
startup-verified. A deterministic safe preview/contact sheet gets its own hash
and can be regenerated; it never replaces accepted media in Model A.

### 6.3 Admission evidence and signed intent

An admission record MUST be canonical, append-only, and contain at least:

- network ID, protocol version, admission policy ID and digest;
- accepted media hash, exact byte length, MIME, content type, and canonical
  metadata digest;
- decoder/rule identities, dimensions, frame count, aggregate decoded pixels,
  full-parse result, and safe-preview hash;
- denylist version/digest and automated scan results with explicit disposition;
- human/policy review decision and evidence identity where required;
- submitter wallet, rights/safety attestation version, signature message hash,
  nonce, and expiry;
- final outcome and immutable reason code.

The MetaMask message MUST bind the exact accepted-media hash, length, MIME,
content type, metadata digest, admission-policy digest, preview hash, network ID,
protocol version, content/submission IDs, attestation text version, nonce, and
expiry. Peer receivers MUST reconstruct this message and validate every field;
recovering the correct wallet from arbitrary text is insufficient.

The submitter attestation MUST plainly state that the exact previewed bytes will
be permanently replicated in ZoidbergChain if accepted, cannot be deleted after
finality, and that the submitter asserts the necessary rights and absence of
prohibited/private material. Final wording requires the policy/legal owner
decision in section 10.

### 6.4 Separate safety and originality decisions

Technical admissibility, prohibited-content review, and originality are three
different gates and MUST have separate evidence and status:

1. Deterministic technical checks reject malformed, unsupported, oversized,
   incorrectly classified, or resource-exhausting media.
2. Versioned safety policy checks reject prohibited media. Exact matches against
   a signed denylist may hard-reject. Probabilistic classifiers MAY flag but MUST
   NOT silently mint or make consensus depend on nondeterministic output.
3. Only technically and policy-admissible media enter community originality
   voting. Originality votes MUST NOT double as safety votes.

At minimum, policy must address material illegal to possess or distribute in the
deployment jurisdiction, child sexual abuse material, non-consensual intimate
imagery, malware/exploit payloads, exposed authentication secrets, targeted
private identifying information, credible threats, and content submitted
without the asserted rights. Exact definitions, appeals, reviewer exposure
controls, and authority are open owner/legal decisions; until resolved, public
minting MUST remain disabled rather than assuming permissive defaults.

### 6.5 Lifecycle and state machine

The target lifecycle is append-only in meaning. Rejections never transition back
without creating a new upload/submission under current policy.

```text
RECEIVING
  -> QUARANTINED_UNTRUSTED
  -> TECHNICAL_CHECK_PENDING
      -> TECHNICAL_REJECTED (terminal; temporary bytes may be deleted)
      -> TECHNICALLY_ADMISSIBLE
  -> SUBMITTER_SIGNATURE_PENDING
      -> SIGNATURE_REJECTED / EXPIRED (terminal for this intent)
      -> SIGNED_EXACT_BYTES
  -> POLICY_CHECK_PENDING
      -> POLICY_REJECTED (terminal; temporary bytes may be deleted)
      -> POLICY_REVIEW_REQUIRED
          -> POLICY_REJECTED
          -> ADMISSIBLE
      -> ADMISSIBLE
  -> ORIGINALITY_REVIEW_PENDING
      -> ORIGINALITY_REJECTED (terminal)
      -> CERTIFIED
  -> MINT_QUEUED
  -> CANDIDATE_BUILT
  -> CANONICAL_ACCEPTED
  -> CONFIRMED
  -> FINALIZED
  -> FINALIZED_DISPUTED / PRESENTATION_SUPPRESSED (bytes and block unchanged)
```

`ADMISSIBLE`, `CERTIFIED`, and `MINT_QUEUED` require the same accepted-media
hash, policy digest, and metadata digest. A change creates a new content object
and submission. There is no “unblock” that mutates a rejected record.

### 6.6 Certification, queue, and block validation

1. An originality certificate MUST reference a valid immutable admission record
   and bind its policy/evidence digest.
2. Queue admission and selection MUST fail closed if bytes, MIME, lengths,
   metadata digest, policy, signature, technical evidence, safety decision,
   originality evidence, or certificate disagree.
3. Candidate construction MUST read the immutable admitted object, not a mutable
   path, and recheck its byte hash and canonical size.
4. Every validator MUST apply the frozen media/block limits and validate the
   admission and originality certificate bindings. Validators MUST NOT re-run a
   nondeterministic classifier or OCR as consensus.
5. At the activation height, every new non-genesis media block MUST use the
   activated format. Historical legacy blocks remain readable, but a new legacy
   block cannot extend the activated chain.
6. The atomic commit must consume one admission record, one submission, and one
   originality certificate exactly once and create exactly one block. Replay,
   concurrent mint, and alternate-miner attempts return the existing result or
   fail without a partial state change.

### 6.7 Storage, transport, import, and recovery

- Quarantine bytes are never returned by public endpoints and have a bounded
  retention/garbage-collection policy. Promotion to admitted storage is an
  atomic rename/state commit after successful checks and signature.
- The admitted object is immutable and content-addressed. Accepted block bytes
  are also embedded in canonical chain state; external files are caches only.
- All HTTP, peer, base64, JSON, backup, import, and migration readers must enforce
  encoded and decoded budgets before allocation where practical and while
  streaming otherwise.
- Peer submissions without complete signed intent and admission evidence are
  rejected after activation. Peer blocks are fully validated in staged state
  before any certificate/evidence/cache side effects become durable.
- Import/migration validates every block, embedded media object, certificate,
  finality record, and aggregate resource budget before atomic replacement.
- Recovery of an activated Protocol v1 block uses embedded block bytes only and
  verifies the hash. Local cache paths must resolve beneath the managed content
  root.
- Sync must be byte-budgeted and paginated. A node may stop a page before its
  block-count cap when the encoded byte cap is reached, then resume by height.

### 6.8 Serving, disputes, and finality

Untrusted/quarantined originals MUST never be auto-rendered. Review uses a
deterministic safe derivative, explicit warnings, and least-privilege access.
Raw accepted media downloads SHOULD be isolated on a non-credential origin and
MUST use `X-Content-Type-Options: nosniff`, a restrictive content security
policy, safe content disposition, and no ambient authorization secrets.

A report/dispute can be filed before or after minting. Before mint, a credible
report blocks queue selection until resolved. After canonical acceptance but
before finality, protocol fork/finality rules—not ad hoc deletion—govern chain
selection. After finality, the only permitted actions are append-only dispute
records, warnings, search/index exclusion, and presentation/API suppression.
The original block and accepted media bytes remain retrievable by a validating
node and are never rewritten or deleted.

## 7. Required invariants

1. No untrusted byte is public, review-rendered, certified, queued, or minted
   before the required preceding admission state.
2. A byte sequence has one canonical SHA-256 identity; accepted bytes never
   change identity or path target.
3. The user signature, admission record, originality certificate, block fields,
   and embedded bytes all bind the same network, policy, media hash, byte length,
   MIME/type, and metadata digest.
4. A validator's environment cannot relax or reinterpret media validity.
5. Format parsing covers the complete container and every frame within explicit
   resource budgets.
6. Probabilistic/local tooling can flag or assist review but cannot independently
   create consensus acceptance.
7. Safety decision and originality decision are independent and both must pass.
8. An accepted submission and its certificate can be consumed by exactly one
   canonical block.
9. Candidate construction and peer validation enforce the same canonical block
   byte limit.
10. No peer, import, migration, compatibility, recovery, dev, or admin route can
    introduce a post-activation block lacking required admission evidence.
11. Import, chain adoption, and mint are all-or-nothing durable operations.
12. Model A bytes survive JSON/SQLite persistence, backup/export/import, peer
    sync, restart, and cache loss.
13. Finalized `(height, hash, media bytes)` never changes. Dispute and hiding are
    presentation metadata only.
14. Logs, errors, and metrics never contain raw media, OCR text, signature,
    private path, credential, or other sensitive payload data.

## 8. Likely implementation impact for Tasks 6.2–6.11

The current repository contains no checked-in description mapping the new
Milestone 6 Tasks 6.2–6.11 to individual topics. The list below is therefore an
impact forecast, not an invented task assignment.

| Area | Existing files likely to change | Likely additions |
| --- | --- | --- |
| Frozen policy and canonical models | `config.py`, `protocol_v1.py`, `content.py`, `submission.py`, `originality_certificate.py`, `block.py` | `protocol_v1_media_admission.py`, admission record/certificate model |
| Upload, auth, and quarantine | `api_runtime.py`, `api_routers/content.py`, `wallet_auth.py`, `services/content_coordination_service.py` | bounded upload reader, quarantine/admission service, worker protocol |
| Media decode/OCR and policy checks | `utils.py`, `originality.py`, `requirements-originality.txt`, pinned lock/CI files | isolated decoder/OCR worker, safe-preview service, denylist/policy service |
| Review, reporting, certification | `review_policy.py`, `milestone5_policy.py`, `services/submission_originality_service.py`, `services/reviewer_eligibility_service.py`, `reviewer_reputation.py` | safety-report/admissibility review service and schemas |
| Queue, production, validation, commit | `services/mint_queue_service.py`, `services/block_production_service.py`, `services/block_validation_service.py`, `blockchain.py` | activation-height migration/compatibility guard |
| Peer sync and transport | `peer_sync.py`, `api_routers/peer.py`, `services/peer_content_sync_service.py`, `services/peer_chain_sync_service.py`, peer message protocol files | bounded streaming/page utilities and staged adoption command |
| Storage/import/recovery | `storage.py`, `storage_tools.py`, `storage_migration.py`, migration scripts | quarantine/admission tables, immutable claims/indexes, schema migration |
| Public serving and frontend | `api_routers/public_chain.py`, `api_routers/content.py`, `zoidbergcoin-ui/src/pages/Dashboard.vue`, `zoidbergcoin-ui/src/pages/WhyZoidbergCoin.vue`, `zoidbergcoin-ui/src/utils/protocolV1Ui.js` | safe-preview/report UI and client tests |
| Operations/documentation | `.env.example`, `README.md`, `docs/roadmap.md`, `docs/task-roadmap.md`, `docs/content-object-model.md`, `docs/protocol-v1*.md`, `docs/storage-operations.md`, deployment runbooks, CI workflows | media policy/runbook and incident-response documentation |
| Tests | current content/API/submission/blockchain/storage/peer/finality suites | adversarial fixtures, admission-policy golden vectors, cross-node/fault-injection/end-to-end Milestone 6 suites |

No later task should update the old off-chain roadmap text piecemeal. Model A and
the activation/migration rules must be made consistent across every protocol,
storage, operations, and user-facing document in one reviewed change set.

## 9. Milestone 6 acceptance criteria and mapped test plan

Because the repository does not yet contain a new Milestone 6 roadmap or an
authoritative 6.2–6.11 acceptance list, the following criteria are the testable
acceptance contract derived from the fixed decisions and requested audit. “Now”
records existing evidence only; Milestone 6 does not pass until every future
test is implemented and green on two independently configured nodes.

| Criterion | Acceptance test plan | Current evidence/status |
| --- | --- | --- |
| M6-AC01 Pre-mint gate | Attempt every API/service/peer/import/dev route with a technically or policy-rejected object; assert no certificate, queue row, block, reward, or public original exists. | Missing; **future fail** |
| M6-AC02 Exact signed bytes | Golden-vector signature binds hash, length, MIME/type, metadata/policy/preview digests; mutate each field independently and reject locally and on peer. | Current signature/hash tests are partial; **future fail** |
| M6-AC03 Type and complete decode | Corpus for valid JPEG/PNG/GIF/WebP/text plus truncated, forged-prefix, trailing/polyglot, malformed frame and mislabeled inputs on two platforms. | Header/MIME tests pass; complete decode missing |
| M6-AC04 Resource bounds | Boundary tests at byte, request, width, height, frame, decoded-pixel, block, peer-page and snapshot limits; one-unit-over rejects before large allocation. Timeout/memory bomb worker tests. | File/text boundary tests pass; other bounds missing |
| M6-AC05 Quarantine | Crash/restart/fault injection at receive, temp write, scan, signature and promotion; unadmitted bytes never publicly resolve and expired objects are recoverably removed. | Atomic content-store tests pass; quarantine missing |
| M6-AC06 Authenticated admission | Direct calls with spoofed wallet, missing/expired/wrong session, wrong signer/network/nonce and peer replay all reject before durable promotion. | Signed submission tests pass; upload ownership missing |
| M6-AC07 Separate decisions | State-transition/property tests prove safety rejection cannot become originality pending and originality approval cannot override safety rejection. | No safety states; **future fail** |
| M6-AC08 Admission-bound certificate | Golden vectors and negative tests for policy/evidence/media/metadata mismatch, missing admission record, stale policy, malformed vote set and replay. | Originality v3 binding passes; admission binding missing |
| M6-AC09 Queue/candidate/validator equivalence | Generate valid/invalid admitted submissions; producer and two validators return identical results under deliberately different environment variables. | Current block hash/media tests pass; env independence missing |
| M6-AC10 One submission, one block | 100-way concurrent mint, replay, alternate miner/node and crash injection; exactly one block/creator reward/certificate consumption. | Existing concurrent/atomic tests pass for current cert flow; extend with admission claims |
| M6-AC11 Model A durability | Mint unique bytes; delete all external caches; restart JSON and SQLite, export/import to fresh node, sync to peer and recover exact byte equality/hash. | Current Protocol v1 and Milestone 5 reconstruction tests substantially cover this; extend with admission evidence |
| M6-AC12 Bounded peer/import | Oversized encoded field, decoded payload, chain page, nested JSON and snapshot stream fail before commit; valid paginated resume converges. | Per-content post-download tests pass; early/aggregate bounds missing |
| M6-AC13 Atomic sync/import | Inject failure after each evidence/certificate/block/cache stage; durable target remains wholly old or wholly adopted with no orphan/conflict. | Atomic local mint/storage tests pass; peer/import adoption missing |
| M6-AC14 Legacy activation barrier | Pre-activation fixtures remain readable; every post-activation legacy/non-admission extension is rejected locally, by peer, import, and recovery. | Legacy compatibility passes but barrier missing |
| M6-AC15 Safe review/serving | Browser/API tests prove quarantine never serves, review uses derivative, raw response has isolation headers, animation/contact sheet matches admitted frames, and report blocks mint. | Direct original rendering exists; **future fail** |
| M6-AC16 Immutable finality | Finalize admitted media, submit dispute/hide action, attempt fork/import/admin deletion, and prove block hash/bytes/evidence unchanged while public presentation follows policy. | Validator-quorum preservation tests pass; dispute layer missing |
| M6-AC17 Privacy/observability | Capture logs/errors/metrics across malformed, OCR, rejection and crash paths; assert no raw bytes/text/signatures/paths/secrets and stable reason codes/metrics exist. | General safe-error tests exist; media-specific coverage missing |
| M6-AC18 End-to-end adversarial release gate | Two-node JSON/SQLite scenarios covering all formats and attack classes, restart/recovery, policy-version mismatch startup refusal, finalized byte identity, full backend/frontend suites, dependency audit and golden vectors. | M5 two-node/full suite passes; Milestone 6 scenario missing |

Tasks 6.2–6.11 must add criterion IDs to test names or test metadata so the
release report can prove coverage without relying on narrative inference.

## 10. Unresolved owner decisions

These decisions require product/security/legal authority and must be closed
before public minting is enabled. The technical implementation must fail closed
while a required value is absent.

1. The exact prohibited-content policy, controlling jurisdiction, review/appeal
   process, retention period for rejected temporary bytes, and emergency contact.
2. Who signs/curates the high-confidence denylist, how updates activate, and how
   nodes obtain it without making nondeterministic network calls during
   validation.
3. Who makes a safety-review decision: a distinct eligible community quorum,
   designated moderators/validators, or a hybrid; plus quorum, conflicts,
   recusals, reviewer welfare, and audit rules.
4. The exact plain-language permanent-publication and rights attestation text,
   with legal review.
5. Whether animated GIF/WebP remains supported at activation. The profile above
   permits it only within all-frame limits; disabling animation is a simpler
   alternative but must be a reviewed policy-version decision.
6. Safe-preview encoding identity and whether review requires animated playback
   in addition to a deterministic all-frame contact sheet.
7. Raw-media access after presentation suppression: validating-node RPC only,
   isolated download origin, or both. None may delete chain bytes.
8. Activation height and treatment of already-pending, approved, queued, or
   canonical legacy submissions at activation.
9. Operational ownership and capacity for the isolated media worker, malware
   signatures, incident response, abuse reports, and monitoring.

The numerical profile in section 6.2 is the Task 6.1 recommended initial Public
Testnet v1 contract. Changing a value before activation requires updating its
canonical policy object and tests; changing it after activation requires a new
policy version and explicit activation rule, never an environment-only edit.

## 11. Current mismatches with the Milestone 6 direction

1. `docs/roadmap.md` Task 12 says large content should be off-chain, hashes rather
   than raw media should be on-chain, and pruning should exist. That contradicts
   mandatory Model A.
2. `docs/content-object-model.md` says raw binary is not embedded in portable
   state and missing/remote media need not invalidate certificate/block linkage.
   Protocol v1 now embeds accepted media in blocks; the document reflects an
   older task state and is not a safe Milestone 6 authority.
3. The repository has no checked-in new Milestone 6 / Tasks 6.2–6.11 roadmap or
   acceptance list. Section 9 supplies a proposed authoritative test contract,
   but task ownership still needs to be recorded.
4. Current 5 MiB upload acceptance conflicts with the approximate 500 KB local
   candidate limit and the absence of a validator-enforced canonical block cap.
5. Consensus media validity depends on environment-configurable size and strict
   MIME settings.
6. Current admission is MIME/header/hash validation, not safe full decode,
   resource-bomb protection, malware/prohibited-content screening, or separate
   safety review.
7. Upload attribution, evaluation, and mint-trigger authorization do not match
   the stronger authenticated frontend expectations.
8. Submission signatures and peer verification do not bind the complete media,
   metadata, policy, and attestation intent required for immutable publication.
9. Legacy/unknown records and post-activation legacy block acceptance are not yet
   closed as bypasses.
10. Public endpoints and the frontend serve/render original bytes without a
    quarantine boundary, safe derivative, raw-origin isolation, or post-finality
    presentation-suppression state.

## 12. Task 6.1 acceptance result

**PASS for Task 6.1 audit and specification only.** The complete admission path,
current types and assumptions, limits, technical and policy bypasses, target
state machine, immutable Model A invariants, anticipated file impact, acceptance
criteria, mapped test plan, and unresolved owner decisions are documented.

**Milestone 6 is not complete.** The current implementation does not satisfy the
future safety gates in section 9, and this task intentionally changed no
production or protocol behavior.
