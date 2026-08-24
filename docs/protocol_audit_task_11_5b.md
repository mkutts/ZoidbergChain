# Task 11.5b Protocol Audit

## 1. Executive Summary

This audit covered the current blockchain/content path, originality voting rules, allowlist and eligibility rules, and upload/block size handling.

Current behavior is a mixed model:

- Some content is on-chain as block payload data.
- Content metadata and approval metadata are also stored on-chain in the block.
- Uploaded binaries are also stored off-chain in local content storage under `content/`.
- New upload-first content uses a direct SHA-256 payload hash.
- Legacy direct-submission content still uses a legacy submission-derived `content_hash` path.

The strongest confirmed rules:

- Minting requires an originality certificate.
- A block stores `submission_id`, `certificate_id`, `content_hash`, `content_id`, `vote_hash`, approval totals, and reward metadata.
- Creator self-voting is blocked.
- Duplicate voting by the same wallet identity is blocked.
- Approval uses decisive votes only and requires `approval_percentage >= 0.70`.
- Minimum votes are `max(5, ceil(active_users_7d * 0.05))`.
- Invite/access requests and override requests do not grant access by themselves.

Main gaps found:

- Block validation does not re-derive the embedded `meme` payload against `content_hash` or `content_id`.
- Legacy direct-submission image content is not cryptographically committed with the same strong payload hash model used by upload-first content.
- Block size is enforced only by the minting path parameter `max_block_size_kb=500`; it is not a network/config rule in `config.py`.
- There is no separate explicit metadata-size cap beyond field-length validation.
- Compression is not implemented for uploads or blocks.

## 2. Meme/Content On-Chain Representation

### Submission to block path

The current mint path is:

1. User uploads content or submits legacy direct content.
2. A `Submission` is created.
3. A `ContentObject` is linked or created.
4. Votes are recorded.
5. `evaluate_submission()` approves or rejects.
6. Approval creates an `OriginalityCertificate`.
7. `add_to_mint_queue()` requires a valid certificate.
8. `mint_submission()` / `mint_next_queued_submission()` calls `add_block()`.
9. `add_block()` creates a `Block` with meme payload plus certificate/content metadata.
10. `is_chain_valid()` calls `validate_block_with_native_transactions()` and `validate_block_certificate_metadata()`.

Relevant functions:

- `blockchain.submit_content`
- `blockchain.upload_binary_content`
- `blockchain.upload_text_content`
- `blockchain.submit_existing_content`
- `blockchain.evaluate_submission`
- `blockchain.create_originality_certificate`
- `blockchain.add_to_mint_queue`
- `blockchain.mint_submission`
- `blockchain.add_block`
- `blockchain.validate_block_certificate_metadata`

### What is on-chain

The block stores:

- `meme`
  - `encoded_image` for image payloads, base64-encoded
  - `text` for extracted or submitted text
- `submission_id`
- `certificate_id`
- `content_hash`
- `content_id`
- `content_type`
- `mime_type`
- `creator_wallet`
- `vote_hash`
- `approval_percentage`
- `decisive_vote_total`
- `minimum_votes_required`
- `approved_at`
- `originality_score`
- reward fields:
  - `reward_type`
  - `reward_recipient`
  - `reward_amount`
  - `reward_source`
  - `minted_at`
- native transaction fields:
  - `native_transactions`
  - `transaction_ids`
  - `transaction_count`
  - `transactions_hash`
- `voter_rewards`

This means the current chain is not metadata-only. The block really does carry a meme payload in `meme`.

### What is off-chain

Off-chain local storage also exists:

- uploaded files are stored under `content/`
- text payloads are also stored as local content files
- content metadata is persisted in `content_objects`

Legacy direct file submission briefly writes to temp submission storage before the canonical content-store write and cleanup.

### What is cryptographically committed by hash

For upload-first content:

- `content_hash` is a direct SHA-256 of normalized text bytes or uploaded binary bytes.
- `content_id` is derived from `content_hash`.
- verified local content can be rechecked against `content_hash`.

For legacy direct submissions:

- `Submission.content_hash` comes from `calculate_submission_content_hash(image_path, text_content, submitter)`.
- this is not the same as hashing only the image bytes.
- stored content is written under that legacy submission hash using `hash_scheme=legacy`.
- the content object may retain a `byte_hash` in metadata, but that `byte_hash` is not what the block commits to.

### What validation protects this

Confirmed validation:

- block hash covers the block payload, including `meme` and certificate metadata
- block validation checks:
  - certificate exists
  - `submission_id` matches certificate
  - `content_hash` matches certificate
  - `content_id` matches certificate/submission/content object when present
  - `creator_wallet`, `vote_hash`, approval fields, and originality score match the certificate
  - verified local content files still match the stored `content_hash`

### Remaining risks

Important gap:

- validation does not re-derive the block’s embedded `meme` payload into `content_hash`
- as a result, the chain validates the certificate/content reference fields, but not that the embedded base64 payload is the payload those fields describe

Practical consequence:

- if an attacker rewrites block payload bytes and recomputes downstream block hashes, the current validator does not explicitly compare the embedded `meme` data to `content_hash`
- this is a protocol-integrity gap even though normal local file tampering of verified upload-first content is detected

Answering the audit questions directly:

- Actual meme binary/image stored directly inside the block: Yes, as base64 in `block.meme["encoded_image"]` for image blocks.
- Blocks also store content reference fields: Yes.
- Enough information to identify minted content: Usually yes, through `submission_id`, `certificate_id`, `content_hash`, and `content_id`.
- Content hash included: Yes.
- Chain validation verifies content hash/reference/certificate: Partially yes.
- Mint without valid certificate: No, minting requires `validate_certificate_for_submission`.
- Underlying local verified content altered after minting without detection: No for verified upload-first local payloads; chain validation catches it.
- Underlying embedded on-chain `meme` payload altered after chain rewrite without detection against `content_hash`: Not currently checked.
- Legacy submissions handled differently: Yes.
- Uploaded binaries stored off-chain locally while hashes/metadata are on-chain: Yes, and in the current implementation the block also carries the payload.

## 3. Originality Consensus and Minting Rules

### Current quorum rule

The current minimum vote rule is still:

`max(5, ceil(active_users_7d * 0.05))`

Implemented by:

- `blockchain.calculate_minimum_votes_required`
- constants:
  - `MIN_VOTE_FLOOR = 5`
  - `ACTIVE_USER_PERCENT_FOR_MIN_VOTES = 0.05`
  - `ACTIVE_USER_LOOKBACK_DAYS = 7`

### What counts as an active user

`storage.count_active_users()` counts unique wallets seen in the last 7 days from:

- submissions: `submitter`
- votes: `voter`
- pending legacy transactions: `sender`, excluding `GENESIS` and `REWARD_POOL`
- legacy in-block transactions: `sender`, excluding `GENESIS` and `REWARD_POOL`

Notably, this active-user calculation does not use native transaction senders from `native_transactions`.

### Approval rule

Current approval rule is still:

- decisive votes = `original + not_original`
- approval percentage = `original / decisive_votes`
- approve if `approval_percentage >= 0.70`

Implemented by:

- `ORIGINALITY_APPROVAL_THRESHOLD = 0.70`
- `blockchain.get_submission_votes`
- `blockchain.evaluate_submission`

### `UNSURE` handling

- `UNSURE` votes are stored
- `UNSURE` votes do not count toward approval percentage
- `UNSURE` votes do count toward `votes_cast`
- finalization checks `len(votes) >= minimum_votes`, so `UNSURE` votes do count toward quorum/minimum vote count

### Self-vote, duplicate vote, and vote changes

- creator cannot vote own submission: enforced
- same wallet cannot vote more than once: enforced
- vote changes after casting: not supported

Implemented by `blockchain.cast_submission_vote`.

### Finalization and mint eligibility

A pending submission becomes final when:

- voting window expires (`VOTING_WINDOW_HOURS = 24`) or
- minimum votes are reached

Then:

- if automated originality fails: rejected
- else if approval percentage >= 0.70: approved and certificate created
- else: rejected

Certificate creation happens inside approval flow in `evaluate_submission()`.

Minting requires:

- submission status in `{APPROVED, QUEUED}`
- no hard rejection
- valid originality certificate

`add_to_mint_queue()` only accepts approved submissions and immediately requires a valid certificate.

### Rejected submissions

- rejected submissions do not receive a certificate
- rejected submissions cannot mint
- hard-rejected submissions cannot enter mint queue or mint

### Majority-side voter rewards

If voter rewards are enabled:

- approval-side reward choice is `original`
- rejection-side reward choice is `not_original`
- only majority-side decisive voters are eligible
- creator is excluded from voter rewards
- optional access/review eligibility can further exclude voters

### Review/voting allowlist overrides

Review-scoped allowlist overrides can unlock:

- review
- voting
- rewards

These are applied through `find_matching_allowlist_entry(scope=...)`.

### Config/env values controlling rules

Consensus rule knobs:

- `VOTING_WINDOW_HOURS`
- `MIN_VOTE_FLOOR`
- `ACTIVE_USER_PERCENT_FOR_MIN_VOTES`
- `ACTIVE_USER_LOOKBACK_DAYS`
- `ORIGINALITY_APPROVAL_THRESHOLD`

Reviewer/voter eligibility knobs:

- `REVIEW_ELIGIBILITY_MODE`
- `REVIEW_ALLOWLIST_WALLETS`
- `REVIEW_DENYLIST_WALLETS`
- `MIN_REVIEWER_ACCOUNT_AGE_SECONDS`
- `MIN_REVIEWER_SUBMISSION_COUNT`
- `MIN_REVIEWER_VOTE_COUNT`
- `MIN_REVIEWER_REWARD_COUNT`
- `MIN_REVIEWER_SETTLED_BALANCE_ZOID`
- `MIN_REVIEWER_SETTLED_TRANSFER_COUNT`
- `MAX_REVIEW_VOTES_PER_WALLET_PER_DAY`

Voter reward knobs:

- `VOTER_REWARDS_ENABLED`
- `VOTER_REWARD_POOL_PER_DECISION_ZOID`
- `VOTER_REWARD_MAX_PER_WALLET_ZOID`
- `VOTER_REWARD_MIN_DECISIVE_VOTES`
- `VOTER_REWARD_REQUIRE_REVIEW_ELIGIBLE`
- `VOTER_REWARD_APPROVAL_SIDE`
- `VOTER_REWARD_REJECTION_SIDE`

## 4. Allowlist and Eligibility Rules

### Current access gate rules

Access gating is controlled by:

- `ACCESS_CONTROL_MODE`
- `REQUIRE_ACCESS_FOR_APP`
- `REQUIRE_ACCESS_FOR_SUBMISSIONS`
- `REQUIRE_ACCESS_FOR_VOTES`
- `REQUIRE_ACCESS_FOR_REWARDS`
- `REQUIRE_ACCESS_FOR_TRANSFERS`

In `testnet` and `production` defaults:

- mode is `invite_only`
- access is required for app, submissions, votes, rewards, and transfers

### How access is granted now

Non-admin users can:

- submit an access request
- log in with an already-issued invite code
- bind a wallet to an approved access account
- submit an override request

What requires admin action:

- approving an access request
- creating an invite
- creating an allowlist entry
- approving an override request
- reactivating suspended/revoked access records

### Direct answers

- Can a user get onto the allowlist without admin manual action: No.
- Can requesting access automatically allowlist someone: No.
- Can invite-code flow create allowlist/account eligibility: It can create an approved access-account path after admin-issued invite redemption and wallet binding, but it is not self-allowlisting.
- Can override requests automatically approve anything: No.

Plain statement:

Currently, allowlist entry requires admin action; users can request access/override but cannot self-allowlist.

### What “not on allowlist” means now

For app access:

- usually means the wallet is not bound to an active approved access account and does not match an active `access` or `all_beta` allowlist path

For voting/review/rewards:

- means the wallet did not pass the active review policy and does not match a scoped override such as `review` or `rewards`

### Review/voting/reward eligibility

Voting/review/reward eligibility is separate from app access:

- app access can be granted by wallet binding or `access` / `all_beta` override
- review/voting/rewards can still be blocked by review policy mode

Review policy modes:

- `open`
- `allowlist`
- `activity`
- `hybrid`

Activity thresholds are OR-style today:

- meeting any configured threshold returns eligible

Possible thresholds:

- account age
- prior submission count
- prior vote count
- prior reward count
- settled balance
- settled transfer count

Daily vote limit:

- enforced by `MAX_REVIEW_VOTES_PER_WALLET_PER_DAY` when set above zero

### Account standing rules

Hard blocks override stale allowlist paths:

- revoked wallet binding blocks
- suspended access account blocks
- revoked access account blocks

### UI explanations and `rule_checks`

The UI currently consumes:

- `blocked_reasons`
- `allowlist_overrides_applied`
- `rule_checks`

Backend tests already verify:

- blocked reasons line up with failed required checks
- access allowlist and review allowlist failures are separated correctly
- override request submission does not grant access by itself

## 5. Compression and Block/Content Size Limits

### Compression

No compression was found for:

- uploaded files before storage
- uploaded files before block reference
- block payloads
- serialized block storage

Current block payload storage for image content is base64, which increases size instead of compressing it.

### Serialization

- blocks are persisted as JSON documents
- the on-chain meme payload is represented as JSON fields
- native transaction metadata is JSON

### Confirmed size limits

Backend/content limits:

- `MAX_CONTENT_FILE_SIZE_BYTES = 5 * 1024 * 1024` by default
- `MAX_TEXT_CONTENT_BYTES = 256 * 1024` by default
- `MAX_CAPTION_LENGTH = 1000`
- `MAX_FILENAME_LENGTH = 255`
- `MAX_SUBMISSION_TEXT_LENGTH = 4096`
- `MAX_METADATA_FIELD_LENGTH = 256`

Server config:

- `deploy/nginx/zoidbergcoin.com.conf` sets `client_max_body_size 5M`

Native transaction block packing:

- `MAX_TRANSACTIONS_PER_BLOCK = 10`

Mint-time block size:

- `add_block(..., max_block_size_kb=500)` enforces a 500 KB limit by default
- this is a function parameter, not a config/env-backed network rule

### Missing or ambiguous limits

No explicit separate limit found for:

- total block metadata size
- originality certificate count per block
- vote count per block
- number of certificates per block

The current system effectively mints one meme/certificate context per block, but this is structural behavior rather than an explicit generic “certificate count limit” rule.

### DoS / growth risks

Risks:

- no compression means larger stored and propagated blocks
- base64 image payloads increase on-chain JSON size
- block-size enforcement is local mint-time behavior rather than a clearly network-configured protocol rule
- metadata objects do not have a total serialized-size cap

## 6. Tests Added/Updated

Added:

- block validation test confirming a minted block contains:
  - on-chain `meme` payload
  - `submission_id`
  - `certificate_id`
  - `content_hash`
  - `content_id`
- block validation test confirming tampering with verified uploaded local content causes chain validation failure

Existing tests already cover:

- quorum formula
- 70% approval threshold
- `UNSURE` treatment
- creator self-vote prohibition
- duplicate vote blocking
- certificate creation on approval
- mint requiring certificate
- access request / override request not granting access by itself
- upload/text/caption size limits

## 7. Confirmed Behaviors

- Meme binaries can be on-chain in block payloads as base64.
- Uploaded binaries are also stored off-chain locally.
- Upload-first content uses direct SHA-256 payload hashing.
- Legacy direct image submissions use a legacy submission-derived hash.
- Certificates are required before minting.
- `UNSURE` votes count toward minimum vote total but not approval percentage.
- Approval threshold is 70% decisive `ORIGINAL`.
- Current quorum formula remains `max(5, ceil(active_users_7d * 0.05))`.
- Access requests and override requests are informational/pending until admin action.

## 8. Gaps / Risks

1. Embedded block payload is not re-derived against `content_hash`.
2. Legacy direct-submission content hashing is weaker and semantically different from upload-first hashing.
3. Block size limit is local mint logic, not a clearly centralized protocol config.
4. No compression is implemented.
5. No explicit total metadata-size cap was found.
6. Active-user quorum counts legacy transaction senders but not native transaction senders, which may or may not match intended policy.

## 9. Recommended Follow-Up Tasks

1. Add block validation that re-derives the embedded `meme` payload into the expected `content_hash` and rejects mismatches.
2. Decide whether upload-first SHA-256 payload hashing should become the only supported minting path for images.
3. Migrate or retire legacy direct-submission image hashing.
4. Move block-size policy into explicit config/env-backed protocol settings.
5. Add an explicit serialized metadata-size cap.
6. Decide whether native transaction activity should count toward `active_users_7d`.
7. Decide whether on-chain full payload storage is intentional long term, or whether the protocol should become metadata-plus-hash only.
