# ZoidbergChain

As of Saturday, August 1, 2026, ZoidbergChain is ready for Task 9 public-demo and controlled-testnet hardening on top of the completed Task 1 through Task 8 implementation.

## Stage 1 Goal

Stage 1 is a controlled public demo at `zoidbergcoin.com` with these public labels:

- ZoidbergChain controlled testnet
- Test ZOID has no real monetary value
- This network may reset
- Not mainnet

Current known limitations:

- anti-Sybil behavior is only reduced by reviewer eligibility friction, not solved
- no voter rewards yet
- no replacement policy
- mempools are local, not consensus-wide
- no transfer-only blocks
- no wrapped ZOID / ERC-20 behavior
- not mainnet

## Environment Modes

- `development`: local-only reset/debug tools may be enabled, dev wallet generation may be enabled, localhost CORS is allowed, and rate limits may be relaxed.
- `testnet`: public-demo/testnet mode. Dev-only tools are blocked, private key export is blocked, signed peer messaging and rate limits should be enabled, and CORS should be restricted to expected domains.
- `production`: same lockdown as testnet, with dev tools blocked, private key export blocked, public-safe errors only, and secrets supplied externally.

Disabling dev multi-account tools does not solve anti-Sybil behavior by itself. One real person can still create many real MetaMask wallets. That work remains part of Task 10.

## Deployment Notes

Backend:

- set `ENVIRONMENT=testnet` for the controlled public demo
- configure `PUBLIC_API_MODE=true`
- set `PUBLIC_DEMO_MODE=true`
- configure `NODE_ID`, `NETWORK_NAME`, `PUBLIC_NODE_URL`, `NODE_DATA_DIR`, `CONTENT_STORAGE_DIR`, and `LOG_DIR`
- set a real `PEER_SHARED_SECRET`
- keep `ENABLE_SIGNED_PEER_MESSAGES=true`
- keep rate limits and upload limits enabled

Frontend:

- build `zoidbergcoin-ui` with `VITE_API_BASE_URL` pointing at the HTTPS API origin
- set `VITE_ENVIRONMENT=testnet`
- set `VITE_PUBLIC_DEMO_MODE=true`
- keep `VITE_ENABLE_DEV_TOOLS=false`

Reverse proxy:

- terminate HTTPS at Nginx
- proxy API traffic to the backend host and port
- serve the frontend build output as the public site
- allow only expected public origins through CORS

## Task 10.1 Voting Eligibility Policy

Task 10.1 adds a configurable reviewer eligibility policy layer ahead of originality voting.

- `open`: low-friction mode for local development and simple demos
- `allowlist`: only operator-approved wallets may review
- `activity`: wallets must satisfy one or more configured activity thresholds
- `hybrid`: wallets may qualify through the allowlist or through activity

Important honesty note:

- this is anti-Sybil friction for a controlled testnet
- it is not proof-of-personhood
- it does not stop one real person from creating many MetaMask wallets
- there is still no KYC, staking cost, or external identity proof

Recommended defaults by environment:

- `development`: leave `REVIEW_ELIGIBILITY_MODE=open`
- `testnet`: prefer `allowlist` or `hybrid`
- `production`: prefer `allowlist` or `hybrid` with explicit thresholds and operator review

Example controlled testnet settings:

- `REVIEW_ELIGIBILITY_MODE=allowlist`
- `REVIEW_ALLOWLIST_WALLETS=0xabc...,0xdef...`
- `REVIEW_DENYLIST_WALLETS=0xdead...`
- `MAX_REVIEW_VOTES_PER_WALLET_PER_DAY=10`
- `REVIEW_POLICY_PUBLIC_LABEL=Invite-only testnet reviewer policy`

## Task 10.2 Voter Majority Rewards

As of Sunday, August 2, 2026, Task 10.2 adds native ZOID voter rewards for eligible voters on the final decisive majority side.

Reward rules:

- `UNSURE` votes never receive voter rewards.
- If a submission is approved as original, creator reward behavior stays the same and eligible `ORIGINAL` voters split the voter reward pool.
- If a submission is rejected as not original, the creator receives no creator reward and eligible `NOT_ORIGINAL` voters split the voter reward pool.
- If a submission closes without a decisive approval or rejection outcome, no voter rewards are paid.

Finality and double-pay protection:

- voter rewards follow the existing chain accounting model and become final only when represented inside an accepted certified meme block
- approved-side voter rewards settle in the same mint block as the creator reward
- rejected-side voter rewards stay pending until the next accepted certified meme block settles them
- each payout uses a deterministic reward ID of the form `voter_reward:{submission_id}:{wallet_address}:{final_decision}`
- duplicate reward IDs are rejected during block validation so reruns, sync, and remint-style replay cannot double-pay the same voter

Reward configuration:

- `VOTER_REWARDS_ENABLED`
- `VOTER_REWARD_POOL_PER_DECISION_ZOID`
- `VOTER_REWARD_MAX_PER_WALLET_ZOID`
- `VOTER_REWARD_MIN_DECISIVE_VOTES`
- `VOTER_REWARD_REQUIRE_REVIEW_ELIGIBLE`
- `VOTER_REWARD_APPROVAL_SIDE=original`
- `VOTER_REWARD_REJECTION_SIDE=not_original`

Recommended defaults by environment:

- `development`: small pool is fine for local testing
- `testnet`: keep rewards disabled unless operators explicitly want them on
- `production`: keep rewards disabled unless operators explicitly enable them with deliberate thresholds

Important honesty note:

- voter rewards are testnet ZOID only
- this remains anti-Sybil friction, not proof-of-personhood
- reviewer eligibility can reduce easy abuse but does not stop one real person from controlling many wallets

See the detailed runbooks in:

- [docs/public-demo-deployment-checklist.md](/C:/Users/mattk/ZoidbergChain/docs/public-demo-deployment-checklist.md)
- [docs/backup-restore-runbook.md](/C:/Users/mattk/ZoidbergChain/docs/backup-restore-runbook.md)
- [docs/live-domain-deployment-checklist.md](/C:/Users/mattk/ZoidbergChain/docs/live-domain-deployment-checklist.md)
- [docs/testnet-reset-runbook.md](/C:/Users/mattk/ZoidbergChain/docs/testnet-reset-runbook.md)
- [docs/live-domain-deployment-runbook.md](/C:/Users/mattk/ZoidbergChain/docs/live-domain-deployment-runbook.md)
