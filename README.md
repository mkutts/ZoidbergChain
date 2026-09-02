# ZoidbergChain

As of Saturday, August 29, 2026, the frozen Public Testnet v1 protocol specification lives in [docs/protocol-v1.md](/C:/Users/mattk/ZoidbergChain/docs/protocol-v1.md).

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

## Installation

Supported repository evidence is Python 3.13.5 and Node.js 24.13.0. Python 3.13 is the tested version; the frontend lockfile supports Node 18 or newer, but Node 24.13.0 is the recorded environment.

Complete node installation (required for the current FastAPI node):

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

`requirements.txt` installs both the core node/API group and the originality group. This is intentional: the current application imports image hashing and OCR through `blockchain.py` during FastAPI import, so `requirements-core.txt` alone is not a runnable node installation.

Test installation:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-test.txt
```

Development-tool installation:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

Frontend installation:

```powershell
cd zoidbergcoin-ui
npm.cmd ci
```

System prerequisites cannot be installed by pip or npm: install the Tesseract OCR executable and make `tesseract` available on `PATH` for OCR features. On Windows, use `npm.cmd` when PowerShell execution policy blocks `npm.ps1`.

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

- build `zoidbergcoin-ui` with same-origin API routing through `/api`
- set `VITE_ENVIRONMENT=testnet`
- set `VITE_PUBLIC_DEMO_MODE=true`
- keep `VITE_ENABLE_DEV_TOOLS=false`
- run `npm run build` inside `zoidbergcoin-ui`
- deploy the generated site from `zoidbergcoin-ui/dist/`
- treat `zoidbergcoin-ui/dist/` as the authoritative frontend artifact
- treat backend `static/index.html` only as a minimal backend info page, not the full maintained app

Reverse proxy:

- terminate HTTPS at Nginx
- proxy API traffic to the backend host and port
- serve `zoidbergcoin-ui/dist/` as the public site root
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

## Local Frontend And Backend

Run the local backend from the repository root:

```powershell
.\.venv\Scripts\python.exe -m uvicorn api:app --host 127.0.0.1 --port 8000
```

Run the local Vue frontend from `zoidbergcoin-ui`:

```powershell
npm run dev
```

Local frontend development opens at `http://localhost:5173` or `http://127.0.0.1:5173`.
The frontend uses the shared `VITE_API_BASE_URL` resolver in `zoidbergcoin-ui/src/utils/runtimeConfig.js`; in Vite development the API base is always `/api`, and the Vite dev server proxies that path to the local FastAPI backend at `http://localhost:8000` while stripping the `/api` prefix before it reaches FastAPI. Production builds also default to `/api`, which the live web server proxies to the production FastAPI backend. A production build may set `VITE_API_BASE_URL` only if the frontend is intentionally hosted on a separate API origin.

Development CORS deliberately allows `http://localhost:5173` and `http://127.0.0.1:5173` with credentials. Testnet and production CORS remain restricted to the configured public frontend origins.

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
- `python scripts/access_admin.py generate-admin-password-hash`
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

## Task 10.4c Admin UI

Task 10.4c adds a deployed operator-only admin dashboard at `/admin`.

Admin auth architecture:

- the admin UI uses a separate backend admin session and does not reuse the normal invite-access session or the MetaMask wallet session
- `POST /admin/login` validates the submitted password or bootstrap token against server-side env configuration only
- successful login creates a short-lived admin session and sets an `HttpOnly`, `SameSite=Lax` cookie
- logout invalidates the session and clears the cookie
- session lifetime is controlled by `ADMIN_SESSION_TTL_SECONDS`
- outside `development`, admin auth cannot be disabled through config

Protected admin endpoints:

- `POST /admin/login`
- `POST /admin/logout`
- `GET /admin/session`
- `GET /admin/access/requests`
- `POST /admin/access/requests/{request_id}/approve`
- `POST /admin/access/requests/{request_id}/reject`
- `POST /admin/access/invites`
- `GET /admin/access/accounts`
- `GET /admin/access/accounts/{access_account_id}`
- `POST /admin/access/accounts/{access_account_id}/suspend`
- `POST /admin/access/accounts/{access_account_id}/reactivate`
- `POST /admin/access/accounts/{access_account_id}/revoke`
- `POST /admin/access/wallet-bindings/{wallet_address}/revoke`

Admin security notes:

- admin credentials must stay in server-side env only
- plaintext invite codes are returned once immediately after approval or direct invite creation
- invite code hashes, peer shared secrets, private keys, and admin secrets are never exposed through admin or public endpoints
- the access gate reduces spam and slows easy multi-wallet abuse, but it is not proof-of-personhood

Recommended admin env values:

- `ADMIN_UI_ENABLED=true`
- `ADMIN_AUTH_ENABLED=true`
- `ADMIN_SESSION_TTL_SECONDS=3600`
- `ADMIN_PASSWORD_HASH=pbkdf2_sha256$...`

Optional early-testing fallback:

- `ADMIN_BOOTSTRAP_TOKEN=<strong-random-secret>`
- rotate or remove the bootstrap token once a password hash is configured

Admin setup and login flow:

1. Generate a password hash locally with `python -m scripts.access_admin generate-admin-password-hash`
2. Add `ADMIN_UI_ENABLED`, `ADMIN_AUTH_ENABLED`, `ADMIN_SESSION_TTL_SECONDS`, and `ADMIN_PASSWORD_HASH` to `/etc/zoidbergchain/zoidbergchain.env`
3. Restart the backend
4. Rebuild and redeploy the frontend
5. Visit `https://zoidbergcoin.com/admin`
6. Sign in with the server-side admin credential
7. Review requests, approve or reject them, copy one-time invite codes, and manage bound wallets

Admin UX warnings that should remain visible:

- `Invite codes are shown once. Copy before leaving this screen.`
- `This gate reduces spam but is not proof-of-personhood.`
- `Test ZOID has no real monetary value.`
- `Do not approve users you do not recognize.`

See the detailed runbooks in:

- [docs/public-demo-deployment-checklist.md](/C:/Users/mattk/ZoidbergChain/docs/public-demo-deployment-checklist.md)
- [docs/backup-restore-runbook.md](/C:/Users/mattk/ZoidbergChain/docs/backup-restore-runbook.md)
- [docs/frontend-test-procedure.md](/C:/Users/mattk/ZoidbergChain/docs/frontend-test-procedure.md)
- [docs/live-domain-deployment-checklist.md](/C:/Users/mattk/ZoidbergChain/docs/live-domain-deployment-checklist.md)
- [docs/testnet-reset-runbook.md](/C:/Users/mattk/ZoidbergChain/docs/testnet-reset-runbook.md)
- [docs/live-domain-deployment-runbook.md](/C:/Users/mattk/ZoidbergChain/docs/live-domain-deployment-runbook.md)

## Task 10.6 Testnet Ops Hardening

As of Friday, August 21, 2026, Task 10.6 adds safer public status visibility, admin-only ops visibility, persistent admin audit logs, and clearer testnet operator runbooks.

New safe status and ops endpoints:

- `GET /health`
- `GET /status`
- `GET /ops/status`
- `GET /admin/ops/status`
- `GET /admin/audit-log`

New safe CLI diagnostics:

- `python -m scripts.ops backup-status`
- `python -m scripts.ops verify-backup`
- `python -m scripts.ops sqlite-integrity-check`
- `python -m scripts.ops env-validate`
- `python -m scripts.ops storage-integrity`

Important scope notes:

- this is still a controlled testnet, not audited mainnet
- deployment is still manual
- audit logging is persistent but intentionally lightweight
- this is safer operator visibility, not full production observability

Task 10.6 docs:

- [docs/task-10-6-testnet-ops-hardening.md](/C:/Users/mattk/ZoidbergChain/docs/task-10-6-testnet-ops-hardening.md)
- [docs/testnet-restart-recovery-checklist.md](/C:/Users/mattk/ZoidbergChain/docs/testnet-restart-recovery-checklist.md)
- [docs/testnet-ops-troubleshooting.md](/C:/Users/mattk/ZoidbergChain/docs/testnet-ops-troubleshooting.md)

## Task 11.1 Admin Allowlist Management and User Override Requests

As of Friday, August 21, 2026, Task 11.1 adds persistent operator-managed allowlists plus user-facing override request flows for the controlled ZoidbergChain beta.

New operator capabilities:

- admin allowlist APIs for access, review, submission, voting, rewards, and all-beta overrides
- persistent override request intake and admin approval/rejection
- audit log coverage for allowlist and override actions
- `/admin` dashboard sections for allowlist management and override request review

New user-facing capabilities:

- `GET /eligibility/status` for safe current-session eligibility visibility
- `POST /eligibility/override-requests` for blocked users to request access or review-related overrides
- controlled-access, wallet-status, and review-area explanations for why the user is blocked

Important Task 11.1 notes:

- access allowlist and review eligibility allowlist remain separate concepts
- admin authentication is still separate and is never bypassed
- suspended or revoked accounts remain blocked until explicitly reactivated
- revoked wallet bindings remain blocked until explicitly rebound or reapproved
- this remains a controlled beta operator tool, not proof-of-personhood

Task 11.1 docs:

- [docs/task-11-1-admin-allowlist-override-requests.md](/C:/Users/mattk/ZoidbergChain/docs/task-11-1-admin-allowlist-override-requests.md)

## Task 11.2 In-App User Feedback System

As of Friday, August 21, 2026, Task 11.2 adds lightweight in-app beta feedback intake plus admin review tooling.

New capabilities:

- `POST /feedback` for user-reported bugs, confusing UI, wallet trouble, mobile issues, access issues, submission issues, voting issues, rewards issues, and suggestions
- optional safe wallet, page, device, and eligibility context on feedback submissions
- persistent feedback storage in the existing backend document model
- `/admin` feedback queue, detail view, status updates, priority updates, and admin notes
- admin ops feedback summary counts and audit coverage for feedback actions

Important Task 11.2 notes:

- feedback submission does not grant access or change eligibility
- admin feedback tools remain admin-auth protected
- private keys, seed phrases, invite codes, and secrets must never be submitted
- this is a controlled-beta feedback queue, not a full helpdesk or CRM
- no email notification is included yet

Task 11.2 docs:

- [docs/task-11-2-in-app-user-feedback-system.md](/C:/Users/mattk/ZoidbergChain/docs/task-11-2-in-app-user-feedback-system.md)

## Task 11.4 Beta Tester Guide and Onboarding Instructions

As of Friday, August 21, 2026, Task 11.4 adds first-tester onboarding docs plus lightweight in-app guide links for the controlled ZoidbergChain beta.

New onboarding docs:

- [docs/beta_tester_guide.md](/C:/Users/mattk/ZoidbergChain/docs/beta_tester_guide.md)
- [docs/beta_invite_message.md](/C:/Users/mattk/ZoidbergChain/docs/beta_invite_message.md)
- [docs/beta_launch_checklist.md](/C:/Users/mattk/ZoidbergChain/docs/beta_launch_checklist.md)
- [docs/first_tester_qa_script.md](/C:/Users/mattk/ZoidbergChain/docs/first_tester_qa_script.md)

Frontend onboarding notes:

- the public beta guide remains available at `/why-zoidbergcoin`
- the access gate, homepage, and main dashboard link testers to the guide
- the guide and gate keep the controlled-beta, no-real-value, wallet-safety, and MetaMask Mobile reminders visible
