# Mobile Web QA Checklist

This checklist covers Task 10.5 mobile readiness for the controlled ZoidbergChain testnet web app.

## Supported test matrix

- iPhone Safari
- iPhone MetaMask Mobile browser
- Android Chrome
- Android MetaMask Mobile browser
- Desktop Chrome with MetaMask extension

## Important notes

- Mobile browser-level layout and wallet handoff behavior are still verified manually.
- The current frontend test runner covers helper and service logic, not real browser viewport rendering.
- The recommended mobile path is to open the site inside the MetaMask Mobile browser when wallet connection or signing is required.

## Core access-gate checks

1. Open [https://zoidbergcoin.com](https://zoidbergcoin.com) on each target browser.
2. Confirm the controlled access gate appears before the app unlocks.
3. Confirm the gate shows both paths:
   - `New User`
   - `Returning Approved User`
4. On iPhone Safari and Android Chrome without an injected wallet provider:
   - confirm the helper text recommends MetaMask Mobile
   - confirm the no-provider warning appears
   - confirm the `Open in MetaMask` button appears
5. In MetaMask Mobile browser:
   - confirm the helper text still appears
   - confirm the no-provider warning does not appear

## New-user flow

1. Switch to `New User`.
2. Open `Request Access`.
3. Submit a request with valid test data.
4. Confirm the success message is readable on mobile width.
5. Switch back to `Enter Invite Code`.
6. Enter a one-time invite code approved by the operator.
7. Confirm invite acceptance does not unlock the app by itself.
8. Connect MetaMask.
9. Sign the wallet verification challenge.
10. Bind the verified wallet.
11. Confirm the app unlocks.

## Returning-user flow

1. Start with an already approved and previously bound wallet.
2. Disconnect the wallet locally in the UI.
3. Refresh the page.
4. Switch to `Returning Approved User`.
5. Connect the same wallet.
6. Sign the verification challenge.
7. Confirm the app unlocks without asking for the invite code again.
8. Disconnect again, then reconnect a different unapproved wallet.
9. Confirm the app stays locked and shows the unapproved-wallet message.
10. If possible on mobile, begin verification, switch away during wallet handoff, then return.
11. Confirm the gate keeps enough context to show the retry path and does not lose the current flow.

## Wallet panel checks

1. Confirm long wallet addresses wrap cleanly.
2. Confirm connect, verify, refresh, copy, and disconnect actions stack cleanly on narrow screens.
3. Confirm the transfer form fields are readable and tappable on phones.
4. Confirm reward history and transfer history cards fit without horizontal scrolling.

## Submission and voting checks

1. Open the dashboard on each device/browser.
2. Confirm upload, submission, and vote panels stack cleanly on phone widths.
3. Use the mobile file picker to choose an image.
4. Confirm the image preview fits the screen.
5. Submit content and confirm status messages remain readable.
6. Open a pending submission and cast a vote.
7. Confirm vote buttons stay tappable and visible.

## Explorer checks

1. Open `/blockchain`.
2. Confirm block cards fit on phone width.
3. Confirm hashes, wallet IDs, and transfer details wrap instead of overflowing.
4. Confirm content previews fit within the viewport.

## Admin dashboard checks

1. Open `/admin` and sign in with the configured operator credential.
2. Confirm the hero, warning, and session cards stack cleanly on a phone.
3. Confirm pending request cards are readable without horizontal scrolling.
4. Open a request and confirm the request ID can be copied.
5. Approve a request and confirm the one-time invite code fits and the copy button works.
6. Open the approved accounts list and confirm:
   - bound wallets wrap or truncate cleanly
   - each bound wallet can be copied
   - suspend, reactivate, and revoke buttons remain tappable
7. Open account detail and confirm wallet binding rows remain readable on a phone.

## Regression checks

1. Desktop Chrome with MetaMask extension still supports the existing invite, bind, and returning-user flows.
2. Invite codes remain one-time only.
3. Disconnecting the wallet does not remove the server-side wallet binding.
4. Admin auth remains separate from user access sessions.
