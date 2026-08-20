# Frontend Test Procedure

This procedure is for manual and smoke-style testing of the `zoidbergcoin-ui` frontend against the current ZoidbergChain backend.

It covers:

- normal open local development behavior
- controlled invite-only frontend access flow
- MetaMask connect and verification flow
- wallet binding and access recovery flow
- submission, voting, reward, and transfer UI paths
- public demo and controlled-testnet UI warnings

It does not replace the automated test suite. Use it alongside:

- backend: `pytest`
- frontend: `cd zoidbergcoin-ui && npm test`
- frontend production build: `cd zoidbergcoin-ui && npm run build`

## 1. Preconditions

Before starting:

- MetaMask is installed in the browser you will use
- you have at least two test wallets available in MetaMask:
  Wallet A and Wallet B
- the backend is running locally
- the frontend dev server is running locally
- you know whether you are testing:
  open development mode or invite-only controlled mode

Recommended local frontend URL:

- `http://127.0.0.1:5173` or `http://localhost:5173`

Recommended backend API URL:

- `http://127.0.0.1:8000`

## 1.1 Operator CLI Commands

Use these commands during invite-only frontend QA.

Show safe access-system diagnostics:

```powershell
python -m scripts.access_admin doctor
```

List pending and reviewed access requests:

```powershell
python -m scripts.access_admin list-requests
```

Approve an access request:

```powershell
python -m scripts.access_admin approve REQUEST_ID
```

Approve with an explicit wallet limit:

```powershell
python -m scripts.access_admin approve REQUEST_ID --max-wallets 1
```

Reject an access request:

```powershell
python -m scripts.access_admin reject REQUEST_ID
```

Create a direct invite without a prior request:

```powershell
python -m scripts.access_admin create-invite --name "Frontend Tester" --email "tester@example.test" --max-wallets 1
```

List approved access accounts:

```powershell
python -m scripts.access_admin list-accounts
```

Show one access account in detail:

```powershell
python -m scripts.access_admin show-account ACCESS_ACCOUNT_ID
```

Suspend an access account:

```powershell
python -m scripts.access_admin suspend ACCESS_ACCOUNT_ID
```

Revoke a bound wallet:

```powershell
python -m scripts.access_admin revoke-wallet 0xabc123...
```

If you prefer direct script execution, these should also work from the repo root:

```powershell
python scripts/access_admin.py list-requests
python scripts/access_admin.py approve REQUEST_ID
python scripts/access_admin.py list-accounts
```

What to look for in the CLI output:

- `list-requests`: `request_id`, requester details, request status
- `approve`: returned one-time `invite_code`
- `list-accounts`: `access_account_id`, status, `wallet_count`, `bound_wallets`, invite redemption state
- `show-account`: account-specific status, wallet list, approval time, last login time

## 2. Test Modes

### Open local development

Use this when confirming normal developer behavior is still unrestricted.

Recommended settings:

- `ENVIRONMENT=development`
- `ACCESS_CONTROL_MODE=open`
- `ACCESS_DEV_BYPASS_ENABLED=true`
- `REQUIRE_ACCESS_FOR_APP=false`
- `REQUIRE_ACCESS_FOR_SUBMISSIONS=false`
- `REQUIRE_ACCESS_FOR_VOTES=false`
- `REQUIRE_ACCESS_FOR_REWARDS=false`
- `REQUIRE_ACCESS_FOR_TRANSFERS=false`

Expected outcome:

- the app loads directly
- no invite gate blocks the app
- normal MetaMask-based flows still work

### Controlled invite-only local test

Use this when validating the public-demo access gate behavior.

Recommended settings:

- `ENVIRONMENT=development`
- `ACCESS_CONTROL_MODE=invite_only`
- `ACCESS_DEV_BYPASS_ENABLED=false`
- `REQUIRE_ACCESS_FOR_APP=true`
- `REQUIRE_ACCESS_FOR_SUBMISSIONS=true`
- `REQUIRE_ACCESS_FOR_VOTES=true`
- `REQUIRE_ACCESS_FOR_REWARDS=true`
- `REQUIRE_ACCESS_FOR_TRANSFERS=true`
- `MAX_WALLETS_PER_ACCESS_ACCOUNT=1`

Expected outcome:

- the access gate appears before the normal app
- invite login and request-access paths are visible
- app access is granted only after invite login, MetaMask verification, and wallet binding

## 3. Startup Smoke Check

1. Start the backend.
2. Start the frontend dev server.
3. Open the frontend in the browser.
4. Confirm the page loads without a blank screen or console-breaking error.
5. Confirm the controlled-testnet/public-demo banner appears where expected.
6. Confirm the UI is usable on both a desktop-width viewport and a narrow mobile-width viewport.

Pass criteria:

- no fatal render failure
- no broken primary layout
- no missing critical styles

## 4. Open Development Mode Test

1. Run the app in open local development mode.
2. Load the homepage.
3. Confirm the app does not stop at the invite gate.
4. Connect MetaMask.
5. Verify the wallet.
6. Navigate between the main frontend pages.
7. Confirm the wallet panel updates normally.
8. Confirm development-only tools appear only when they are expected to appear.

Pass criteria:

- unrestricted local developer flow still works
- no invite login is required
- no controlled-access error blocks normal testing

## 5. Invite-Only Gate Test

1. Run the app in invite-only controlled mode.
2. Load the frontend.
3. Confirm the controlled access gate appears before the normal app.
4. Confirm these user actions are present:
   `Enter Invite Code / Login`
   `Request Access`
5. Confirm the page explains:
   controlled testnet
   invite-only access
   test ZOID has no real monetary value
   not mainnet

Pass criteria:

- the app remains locked before invite authentication
- public warning copy is visible

## 6. Request Access Form Test

1. Open the `Request Access` view.
2. Submit a valid request with:
   name
   email
   optional handle
   reason
   optional notes
3. Confirm a success message appears.
4. Submit with one required field missing.
5. Confirm the UI blocks submission or shows a clear error.

Pass criteria:

- valid request succeeds
- invalid request does not silently fail
- no secret data is shown

## 7. Invite Login Test

1. Create or approve an invite using the operator CLI.
2. Enter the one-time invite code in the frontend.
3. Submit the invite code.
4. Confirm the UI shows:
   invite accepted
   connect and verify MetaMask to bind
5. Confirm the app is still locked at this point.

Pass criteria:

- invite login succeeds with a valid code
- invalid code shows a clear error
- invite acceptance alone does not unlock the app

## 8. MetaMask Connect and Verify Test

1. After invite acceptance, keep Wallet A selected in MetaMask.
2. Click `Connect MetaMask`.
3. Approve the connection in MetaMask.
4. Confirm the connected wallet address appears in the UI.
5. Click `Verify Wallet`.
6. Sign the verification message in MetaMask.
7. Confirm the UI now shows the wallet as verified.
8. Confirm `Bind Verified Wallet` is now visible.

Pass criteria:

- connect state changes correctly
- verify state changes correctly
- bind button does not appear before verification

## 9. Wallet Binding Test

1. While Wallet A is verified and the invite session is still active, click `Bind Verified Wallet`.
2. Confirm the bind succeeds.
3. Confirm the app unlocks.
4. Confirm the wallet panel shows the controlled-access state as bound and active.
5. Refresh the page.
6. Re-verify Wallet A if required.
7. Confirm access is recovered for Wallet A without needing the redeemed invite code again.

Pass criteria:

- bind succeeds exactly once for the first wallet
- bound wallet appears as the active controlled-access wallet
- app unlocks only after successful bind

## 10. Second Wallet Rejection Test

1. With `MAX_WALLETS_PER_ACCESS_ACCOUNT=1`, switch MetaMask to Wallet B.
2. Connect or refresh state if needed.
3. Verify Wallet B.
4. Confirm Wallet B does not inherit Wallet A access.
5. Attempt to bind Wallet B to the same access account if the UI still presents a valid path.
6. Confirm the UI shows a clear rejection.

Expected message theme:

- wallet limit reached
- this access account already has the maximum wallets

Pass criteria:

- Wallet B does not gain access automatically
- Wallet B cannot be added when the limit is 1

## 11. Wallet Switch Recovery Test

1. Switch back from Wallet B to Wallet A.
2. Re-verify if the wallet session expired during switching.
3. Confirm Wallet A access returns.
4. Confirm Wallet B does not remain treated as approved.

Pass criteria:

- access follows verified wallet identity
- access does not follow stale browser state alone

## 12. Submission Flow Test

Run this in whichever mode should allow signed submissions.

1. Ensure the current verified wallet is allowed to submit.
2. Upload content or provide text content through the UI.
3. Complete the signed submission flow.
4. Confirm success feedback appears.
5. Confirm the submission appears in the dashboard state.

Negative test:

1. Use an unbound wallet in invite-only mode.
2. Attempt the same submission flow.
3. Confirm the frontend shows a clear access-related failure.

Pass criteria:

- bound wallet can submit
- unbound wallet is blocked cleanly

## 13. Voting Flow Test

1. Use a bound, verified eligible wallet.
2. Open a pending submission.
3. Cast a vote.
4. Confirm the vote succeeds and the UI refreshes correctly.

Negative test:

1. Use an unbound verified wallet.
2. Attempt to vote.
3. Confirm access is denied cleanly.

Pass criteria:

- allowed wallet can vote
- unbound wallet cannot vote

## 14. Reward and Wallet Panel Test

1. Use a bound wallet in a setup where voter rewards are enabled.
2. Complete the necessary review and mint flow.
3. Refresh the wallet panel.
4. Confirm reward history appears for the bound eligible wallet when expected.
5. Confirm the access status card still shows the correct bound wallet and access state.

Pass criteria:

- reward UI reflects backend reward results
- access status card remains accurate

## 15. Native Transfer UI Test

1. Use a bound verified wallet when transfer gating is enabled.
2. Open the transfer section in the wallet panel.
3. Submit a valid signed transfer.
4. Confirm success feedback appears.

Negative test:

1. Use an unbound wallet when transfer gating is enabled.
2. Attempt the transfer flow.
3. Confirm the transfer is blocked cleanly.

Pass criteria:

- bound wallet can access transfer flow
- unbound wallet cannot complete restricted transfer submission

## 16. Banner and Safety Copy Test

1. Confirm the public demo or controlled-testnet banner remains visible where expected.
2. Confirm the UI still says:
   test ZOID has no real monetary value
   this is not mainnet
3. Confirm development-only tools are hidden in public-demo style mode.

Pass criteria:

- safety copy remains visible
- dev tools are not shown in controlled/public mode

## 17. Error-Handling Test

Check these failure paths:

- invalid invite code
- expired or stale invite session
- MetaMask connection rejected
- MetaMask signature rejected
- verified wallet mismatch
- max-wallet limit reached
- backend unavailable

Pass criteria:

- each failure shows a clear user-facing message
- no sensitive token, hash, or secret is displayed

## 18. Browser Refresh and SPA Navigation Test

1. Complete a successful Wallet A bind.
2. Navigate across the app.
3. Refresh the page.
4. Confirm the app can recover state appropriately.
5. Confirm invite-session-only state does not incorrectly unlock the app after a refresh.

Pass criteria:

- bound wallet access is recoverable
- unbound invite-only state stays locked

## 19. Automated Frontend Smoke Commands

Run these before or after manual QA:

```powershell
cd zoidbergcoin-ui
npm test
npm run build
```

Expected outcome:

- test suite passes
- production build succeeds

## 20. Suggested Test Record Template

For each run, record:

- date and tester
- frontend commit or working tree state
- backend mode:
  open or invite-only
- browser used
- MetaMask wallets used
- steps executed
- expected result
- actual result
- screenshots if the UI differs from expectation
- any console or network errors

## 21. Minimum Release Gate For Frontend QA

Before treating the frontend as ready for a public demo iteration, confirm:

- open development mode still works
- invite-only gate works end to end
- valid invite does not unlock until verified wallet bind
- bound wallet recovers access after refresh
- second wallet does not inherit access
- submission and voting flows work for the bound wallet
- transfer gating behavior matches backend settings
- frontend automated tests pass
- production build passes
