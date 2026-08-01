# Roadmap

As of Saturday, August 1, 2026, ZoidbergChain is complete through Task 8 for controlled dev/testnet use.

## Current Status

Completed:

- Task 1: Coin Rules and Submission Lifecycle
- Task 2: Peer-to-Peer Networking
- Task 3: Meme Proof of Originality Consensus
- Task 4: Security and Key Management
- Task 5: Storage Hardening
- Task 6: Content Storage and Transport
- Task 7: MetaMask Native Wallet Identity
- Task 8: Native Transaction Layer Hardening

Current status:

- native ZOID transfers are MetaMask-signed
- transactions use canonical `tx_id` records
- nonce and replay protection exist
- balance sufficiency and available-balance enforcement exist
- local mempool lifecycle exists
- peer transaction gossip exists
- native transfers can be included in certified meme-mined blocks
- transfers settle only inside accepted meme-mined blocks
- peer block validation checks native transfer transactions
- two-node native transfer verification exists
- Task 8.10 validation and reliability review is complete

Known intentional limitations:

- no replacement policy
- mempools are local, not consensus-wide
- transfer-only blocks are intentionally unsupported
- no wrapped ZOID / ERC-20 behavior
- old `/wallets/...` compatibility read endpoints still exist
- appropriate for controlled dev/testnet use, not production/mainnet ready

## Stage Definitions

Stage 1:
Public demo / controlled testnet explorer after Task 9.

Stage 2:
Invite-only public testnet after Task 10.

Stage 3:
Open public testnet after Tasks 11-13.

Stage 4:
Mainnet / real value readiness after Tasks 14-18 and external review.

## Stage 1 - Public Demo Site

Goal:
Make `zoidbergcoin.com` safe to show publicly as a controlled demo/testnet explorer.

Stage 1 public label:

- public demo
- controlled testnet
- no real monetary value
- subject to reset
- not mainnet

### Task 9 - Public Demo / Testnet Deployment Readiness

Scope:

- production/testnet environment configuration
- controlled public-demo labeling
- disable dev-only multi-account tools outside development
- disable dev wallet generation outside development
- disable dev reset endpoints outside development
- disable private key export outside development
- disable signature bypass outside development
- ensure fake/dev voting tools cannot run in production
- CORS/domain configuration
- Nginx/domain deployment cleanup
- health checks
- public explorer readiness
- upload limits
- rate limits
- logging
- safe error handling
- backup/restore runbook
- testnet reset runbook
- documentation that public demo/testnet ZOID has no real monetary value and may reset

Stage 1 deployment expectations:

- `ENVIRONMENT=testnet` for the public demo
- dev-only endpoints return safe `403` responses outside development
- `GET /health`, `GET /node-info`, and `GET /chain/summary` expose safe deployment metadata only
- public CORS defaults target `zoidbergcoin.com` and `www.zoidbergcoin.com`
- frontend labels explicitly say controlled testnet, no real monetary value, may reset, and not mainnet

Important distinction:

- disabling dev multi-account tools does not fully prevent one real person from creating many MetaMask wallets
- that remains an anti-Sybil problem handled later in Task 10

## Stage 2 - Invite-Only Public Testnet

Goal:
Allow limited outside users to submit, vote, earn test rewards, and test native transfers without making the system easy to farm.

### Task 10 - Voting Identity, Anti-Sybil Rules, and Voter Incentives

Scope:

- design voting identity rules
- decide how to reduce multi-wallet voting abuse
- decide whether to use account age, activity requirements, invite/reputation, stake-to-vote, rate limits, or other anti-Sybil mechanisms
- prevent creators from easily farming votes through dev-style tools
- design voter reward model
- reward voters who are in the final majority decision
- handle ORIGINAL majority rewards
- handle NOT_ORIGINAL majority rewards
- decide what happens to UNSURE votes
- decide whether inconclusive votes earn no reward or reputation-only credit
- decide voter reward source
- add tests for voter reward accounting
- document abuse risks and limits

Recommended voter reward principle:

- voters are rewarded for being on the final decisive side, not only for voting ORIGINAL
- if a submission is approved ORIGINAL, the creator receives the meme-mining reward and majority ORIGINAL voters share voter rewards
- if a submission is rejected NOT_ORIGINAL, the creator receives no meme-mining reward and majority NOT_ORIGINAL voters share voter rewards for protecting originality
- if the result is UNSURE or inconclusive, the system should prefer no ZOID reward or reputation-only credit

Important constraint:

- do not implement voter rewards before the anti-Sybil rules are at least designed

## Stage 3 - Open Public Testnet

Goal:
Let a broader public audience use the chain while controlling content abuse, storage growth, and node bloat.

### Task 11 - Multi-Media Original Content Support

Scope:

- expand beyond memes and images
- support additional original content types
- update the content model
- update the originality certificate model for non-image content
- add article metadata
- add video metadata
- update submission UI for content type selection
- update the explorer to display richer content
- preserve the project ethos that ZoidbergChain rewards original content creation, not just memes

### Task 12 - Content Compression, Storage Strategy, and Chain Bloat Prevention

Scope:

- prevent large files from bloating the chain
- define what belongs on-chain versus off-chain
- store hashes, certificates, and metadata on-chain rather than raw large media
- content-addressed storage strategy
- compression rules
- image compression and variants
- video transcoding or preview generation
- article and text compression
- thumbnails and previews
- max file sizes
- max article length
- peer content fetch strategy
- archival node versus lightweight node behavior
- pruning rules
- backup/archive behavior
- optional future IPFS or object-storage integration

Core principle:

- the chain stores proof of content
- the content layer stores the content

### Task 13 - Public Content Moderation and Abuse Controls

Scope:

- reporting and flagging system
- takedown or hide policy for illegal or abusive content
- public upload rate limits
- per-wallet submission limits
- spam prevention
- moderation queue
- banned content hashes
- blocked wallets if needed
- clear policy for content that remains referenced by hash but hidden from public UI
- legal and safety disclaimer for public testnet
- admin and moderator tooling guarded by environment and permissions

## Stage 4 - Mainnet / Real Value Readiness

Goal:
Prepare for a network where users may treat ZOID as having value.

### Task 14 - Production Node and Validator Hardening

Scope:

- validator and node identity model
- stronger peer identity
- node allowlist and testnet bootstrap policy
- validator configuration
- fork-choice hardening
- chain upgrade strategy
- database backup and restore
- disaster recovery
- monitoring and alerts
- deployment runbooks
- node restart and recovery testing
- secure secret handling
- production logging
- public API hardening
- rate-limit review
- data integrity checks
- old dev/testnet reset tools fully blocked

### Task 15 - Transaction Policy Completion

Scope:

- decide replacement policy
- decide whether same-nonce replacement is allowed
- decide fee policy
- decide fee priority if fees are enabled
- decide mempool expiration policy
- decide transaction cancellation behavior, if any
- decide whether mempool remains local or gets stronger sync rules
- preserve the rule that settlement happens only in accepted blocks
- preserve the rule that transfer-only blocks remain unsupported unless intentionally changed later

### Task 16 - Token Economics and Reward Policy Finalization

Scope:

- final supply policy
- reward pool policy
- creator reward policy
- voter reward policy
- NOT_ORIGINAL voter reward policy
- anti-farming controls
- emission schedule if any
- reward halving or decay if any
- treasury or foundation allocation if any
- genesis allocation review
- mainnet reset or migration decision
- public documentation of economics

### Task 17 - Wrapped ZOID / ERC-20 Bridge Planning

Scope:

- decide whether wrapped ZOID is needed
- design a 1:1 backing model
- bridge custody model
- mint and burn rules
- risk disclosure
- DEX and liquidity considerations
- do not implement until the native chain and mainnet economics are stable

Note:

- wrapped ZOID is not required for the native chain to work
- it is a later ecosystem and liquidity feature

### Task 18 - External Review / Audit / Mainnet Launch Checklist

Scope:

- full validation review
- external code review or audit
- testnet bug bounty or closed review if practical
- legal and compliance review if needed
- content moderation review
- terms and disclaimers
- privacy policy if public user accounts or uploads exist
- final mainnet launch runbook
- mainnet genesis procedure
- rollback and disaster plan
- public documentation
- public explorer
- user onboarding guide
- clear statement that mainnet ZOID may have value only once intentionally launched
