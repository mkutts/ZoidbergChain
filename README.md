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
- voter rewards are testnet-only, node-configurable, and still conservative by default
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
- delayed rejected-side settlement does not block the currently minted approved-original submission from finalizing its own majority-voter rewards
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

## Task 10.3 QA Coverage

Task 10.3 adds an end-to-end QA pass for public testnet voting eligibility and majority-side voter rewards.

- integration flow coverage lives in `tests/integration/test_task_10_3_voting_rewards.py`
- approved-original majority-side rewards are expected to remain pending before mint and become final in the accepted mint block
- rejected-side `NOT_ORIGINAL` rewards are expected to remain pending until a later accepted certified block settles them
- review eligibility still gates vote admission even when voter rewards are enabled
- `VOTER_REWARD_REQUIRE_REVIEW_ELIGIBLE=true` can further exclude already-cast but now-ineligible voters from payout
- frontend smoke coverage for banner, voter reward copy, and wallet reward labeling lives in `zoidbergcoin-ui/src/utils/runtimeConfig.test.js`, `zoidbergcoin-ui/src/utils/voterRewards.test.js`, and `zoidbergcoin-ui/src/utils/nativeWalletUi.test.js`

## Task 10.4 Controlled Testnet Access

Task 10.4 adds a simple operator-controlled access gate for a semi-private public demo/testnet.

Important honesty note:

- this is not proof-of-personhood, KYC, or real Sybil resistance
- it is a controlled access and wallet-binding layer that reduces spam and slows easy multi-wallet abuse
- one real person can still control more than one real MetaMask wallet outside the operator flow

Core flow:

- unapproved visitors can see a controlled-testnet access screen before the main app when `REQUIRE_ACCESS_FOR_APP=true`
- visitors can submit an access request with name, email, optional handle, reason, and notes
- operators can review requests locally with `scripts/access_admin.py`
- approved testers receive a one-time invite/access code
- the tester enters the invite code, then connects and verifies MetaMask, then binds the first approved wallet
- restricted actions can then require that bound active access account

Session model:

- invite login creates a short-lived access session used only for the bind flow
- MetaMask verification creates the existing verified wallet session
- binding requires both sessions at the same time
- a valid invite session alone does not unlock the app
- a bound verified wallet can recover access later through wallet identity even after invite redemption

Invite lifecycle:

- newly approved access accounts store `invite_code_hash`, start with no bound wallets, and do not expose plaintext invite codes except at approval/create time
- first successful wallet bind moves the code into redeemed state and clears the live invite hash
- a redeemed code cannot be used for a fresh login again
- the already-bound wallet can still recover access later through the verified wallet session without needing the invite code again

Wallet behavior:

- access follows the verified wallet identity, not browser local storage alone
- switching MetaMask from Wallet A to Wallet B does not inherit Wallet A access
- if `MAX_WALLETS_PER_ACCESS_ACCOUNT=1`, Wallet B cannot be added to the same account
- switching back to Wallet A and verifying again restores access

Backend enforcement:

- `GET /access/status` returns public non-secret access mode information
- `POST /access/request` stores pending access requests
- `POST /access/login` accepts an invite/access code and issues a short-lived access session
- `POST /access/bind-wallet` binds the verified MetaMask wallet to the approved access account
- `GET /access/me` returns safe current access-account, wallet-binding, invite-session, and capability status
- signed submissions, originality votes, gated voter rewards, and native transfer submission can all require a bound active access account

Local developer safety:

- in `development`, the default access mode is `open`
- in `development`, `ACCESS_DEV_BYPASS_ENABLED=true` by default so normal local testing is not locked out
- in `testnet` and `production`, the bypass is off and ignored outside development
- invite-only local testing is still possible by explicitly setting `ACCESS_CONTROL_MODE=invite_only` and turning the bypass off

Recommended controlled testnet settings:

- `ACCESS_CONTROL_MODE=invite_only`
- `ACCESS_REQUESTS_ENABLED=true`
- `ACCESS_DEV_BYPASS_ENABLED=false`
- `REQUIRE_ACCESS_FOR_APP=true`
- `REQUIRE_ACCESS_FOR_SUBMISSIONS=true`
- `REQUIRE_ACCESS_FOR_VOTES=true`
- `REQUIRE_ACCESS_FOR_REWARDS=true`
- `REQUIRE_ACCESS_FOR_TRANSFERS=true`
- `MAX_WALLETS_PER_ACCESS_ACCOUNT=1`
- `ACCESS_PUBLIC_LABEL=Controlled invite-only testnet`

Operator CLI examples:

- `python scripts/access_admin.py list-requests`
- `python -m scripts.access_admin list-requests`
- `python scripts/access_admin.py approve REQUEST_ID`
- `python scripts/access_admin.py reject REQUEST_ID`
- `python scripts/access_admin.py create-invite --name "Local Developer" --email "local@example.test"`
- `python scripts/access_admin.py show-account ACCESS_ACCOUNT_ID`
- `python scripts/access_admin.py suspend ACCESS_ACCOUNT_ID`
- `python scripts/access_admin.py revoke-wallet 0xabc...`
- `python scripts/access_admin.py doctor`

Safe CLI notes:

- `list-accounts` shows wallet counts, bound wallets, invite redemption state, approval time, and last login time
- `show-account` prints one safe account view without invite hashes or secrets
- `doctor` reports access mode, storage backend, data paths, account counts, and the fact that access sessions are memory-only for the current process

Manual QA runbook:

- A. Start the local backend in invite-only mode.
- B. Submit Request Access.
- C. Use the CLI to approve the request.
- D. Record the one-time invite code.
- E. Enter the invite code in the UI.
- F. Confirm the invite is accepted.
- G. Connect MetaMask Wallet A.
- H. Verify Wallet A.
- I. Bind Wallet A.
- J. Confirm the app unlocks.
- K. Run the CLI `list-accounts` command and confirm Wallet A is bound.
- L. Refresh the browser and confirm Wallet A access can be recovered appropriately.
- M. Switch MetaMask to Wallet B.
- N. Confirm Wallet B does not inherit access.
- O. Try binding Wallet B.
- P. Confirm it is rejected because `MAX_WALLETS_PER_ACCESS_ACCOUNT=1`.
- Q. Switch back to Wallet A.
- R. Verify again if required.
- S. Confirm access is restored.
- T. Restart the backend.
- U. Confirm wallet binding persists.

See the detailed runbooks in:

- [docs/public-demo-deployment-checklist.md](/C:/Users/mattk/ZoidbergChain/docs/public-demo-deployment-checklist.md)
- [docs/backup-restore-runbook.md](/C:/Users/mattk/ZoidbergChain/docs/backup-restore-runbook.md)
- [docs/frontend-test-procedure.md](/C:/Users/mattk/ZoidbergChain/docs/frontend-test-procedure.md)
- [docs/live-domain-deployment-checklist.md](/C:/Users/mattk/ZoidbergChain/docs/live-domain-deployment-checklist.md)
- [docs/testnet-reset-runbook.md](/C:/Users/mattk/ZoidbergChain/docs/testnet-reset-runbook.md)
- [docs/live-domain-deployment-runbook.md](/C:/Users/mattk/ZoidbergChain/docs/live-domain-deployment-runbook.md)
