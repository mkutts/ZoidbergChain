# MetaMask Connect And Native Account Identity

This note summarizes how MetaMask currently fits into ZoidbergChain after Tasks 7.1 through 7.12.

## Current Role

- MetaMask provides connection, challenge signing, and action signing.
- A verified MetaMask `0x...` address is the user's native ZoidbergChain account identity.
- Native ZOID still lives in ZoidbergChain state rather than appearing in standard MetaMask asset lists.

## Verified Session Flow

1. Connect MetaMask in the browser.
2. Request a backend challenge from `POST /auth/wallet/challenge`.
3. Sign the challenge with MetaMask.
4. Verify the signature with `POST /auth/wallet/verify`.
5. Use the verified bearer session for signed submissions, signed votes, and transfer-intent signing.

## Direct Signed Actions

- Task `7.4` requires each new submission to be directly signed.
- Task `7.5` requires each new originality vote to be directly signed.
- Task `7.8` introduces signed transfer intents, but not final transfer settlement.

## Native Account Read Model

The UI and any future explorer/account views should prefer:

- `GET /accounts/{wallet_address}`
- `GET /accounts/{wallet_address}/submissions`
- `GET /accounts/{wallet_address}/votes`
- `GET /accounts/{wallet_address}/rewards`
- `GET /accounts/{wallet_address}/transfers`

These endpoints describe the native account state for a verified MetaMask-style address.
