# Wallet Onboarding Architecture

Last updated: August 24, 2026

## Goal

Keep the current MetaMask beta path working while separating:

- user-friendly login and onboarding
- wallet ownership and signing identity
- backend authorization based on verified wallet control

The current application already treats the backend trust boundary as "verified wallet address plus signature." The largest coupling is in the frontend, where MetaMask is currently both:

- the only login surface
- the concrete signing provider hardcoded into state, copy, and mobile guidance

## Current Architecture Audit

### Frontend wallet flow

Current live flow:

1. Detect `window.ethereum`.
2. Request accounts with `eth_requestAccounts`.
3. Ask the backend for a wallet login challenge.
4. Request `personal_sign`.
5. Send `wallet_address`, `message`, and `signature` to the backend for verification.
6. Store the verified wallet session token in local storage.
7. Reuse that verified session for:
   - returning approved wallet login
   - submission signing
   - voting signing
   - native transfer signing
   - wallet-bound rewards and balance reads

Primary frontend files:

- `zoidbergcoin-ui/src/services/wallet.js`
- `zoidbergcoin-ui/src/services/nativeTransfer.js`
- `zoidbergcoin-ui/src/components/ControlledAccessGate.vue`
- `zoidbergcoin-ui/src/components/WalletPanel.vue`
- `zoidbergcoin-ui/src/utils/mobileWallet.js`

### Backend wallet flow

Current backend flow:

1. Normalize the submitted EVM wallet address.
2. Issue a nonce-based challenge with a short TTL.
3. Recover the signer from the submitted `personal_sign` signature.
4. Create a verified wallet session token after recovery matches the submitted address.
5. Reuse the verified wallet address as the trust anchor for:
   - access binding
   - submission signature challenges
   - vote signature challenges
   - native transfer challenges
   - account and reward views

Primary backend files:

- `wallet_auth.py`
- `api.py`
- `native_transfer.py`
- `access_control.py`

## Findings

### What is already provider-agnostic

- Backend verification is address-and-signature based, not MetaMask-brand based.
- Login, submission, vote, and transfer verification all recover an EVM signer from the signed message.
- Access binding depends on the verified wallet address and account state.
- The backend challenge and session model can already work with any EIP-1193-compatible EVM signer that supports `personal_sign`.
- Native transfer verification also depends on recovered signer equality, not on MetaMask-specific fields.

### Where MetaMask-specific assumptions exist

Frontend hardcoding exists in:

- direct `window.ethereum` usage
- `eth_requestAccounts` and `personal_sign` calls made inline
- state names such as `isMetaMaskAvailable`
- copy such as "Connect MetaMask", "MetaMask not found", and MetaMask-only mobile guidance
- mobile deep-link behavior targeting MetaMask Mobile

Backend MetaMask labeling exists mostly in descriptive metadata and copy, not in the verification boundary:

- `identity_source` values currently use `metamask_*`
- several account endpoints label native accounts as `metamask_native`
- notes and API descriptions sometimes describe the account as MetaMask-backed

### Risk points for adding another provider

The highest-risk breakpoints are:

- frontend session restoration if a future provider returns a different visible address format or connection lifecycle
- mobile guidance and onboarding copy that currently assume MetaMask is the only path
- future providers that do not cleanly expose raw wallet address plus arbitrary message signing
- future providers that can sign app messages but do not offer a credible export or migration path

### Access and binding implications

The backend access model is compatible with alternative providers if all of the following stay true:

- the provider yields a stable EVM wallet address
- the app verifies a challenge signature before binding or unlocking
- `provider_id` stays metadata only
- account permissions continue to rely on verified wallet ownership and access state

## Safe Refactor Added In This Task

This task adds light frontend scaffolding only:

- `zoidbergcoin-ui/src/services/walletProviderAdapter.js`
- MetaMask is now represented as an adapter rather than an assumption scattered across service code.
- `wallet.js` now tracks provider metadata and an adapter registry while preserving existing behavior.
- `nativeTransfer.js` now signs through the adapter interface instead of calling MetaMask directly.
- accurate "Alternative login coming soon" copy was added without unlocking any new path

No embedded wallet provider was integrated.

## Provider Abstraction

The current safe frontend contract is:

- `providerId`
- `providerLabel`
- `providerType`
- `isAvailable()`
- `getConnectionStatus()`
- `connect()`
- `getAccounts()`
- `getChainId()`
- `requestSignature(message, walletAddress)`
- `on(event, handler)`

This should evolve toward the fuller target interface:

- `provider_id`
- `provider_label`
- `provider_type`
- `isAvailable()`
- `connect()`
- `getAddress()`
- `requestSignature(message)`
- `disconnect()`
- `getConnectionStatus()`
- `supportsExportInfo`
- `supportsNativeTransferSigning`
- `supportsMessageSigning`

## Backend Compatibility Guidance

Recommended backend rule:

- `provider_id` may be stored as metadata only after wallet verification.
- `provider_id` must never bypass challenge verification.
- `provider_id` must never be trusted as proof of custody, portability, or eligibility.

Recommended future backend extension:

- add optional `provider_id` and `provider_type` to wallet-session payloads
- persist only after successful signature verification
- keep authorization keyed to verified wallet address and access state

## Recommended Next Step

Recommended sequence:

1. Keep MetaMask as the only live login path in beta.
2. Add WalletConnect later as an external-wallet expansion, not as a replacement for embedded onboarding.
3. Run a short embedded-wallet spike against providers that explicitly support:
   - stable EVM address output
   - arbitrary message signing
   - clear export or migration path
   - survivable wallet control if the provider relationship changes
4. Only then expose email, social, or passkey login in production UI.

## Bottom Line

The current backend is already close to provider-agnostic for EVM signers.

The current frontend was MetaMask-specific.

This task moves the frontend one layer closer to provider-agnostic architecture without changing the working MetaMask flow.
