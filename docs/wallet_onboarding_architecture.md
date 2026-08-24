# Wallet Onboarding Architecture

Last updated: August 24, 2026

## Goal

Keep the working MetaMask path while adding a second onboarding path for non-crypto users that still ends in the same trust model:

- verified wallet address
- signed backend challenge
- normal ZoidbergChain wallet session

Alternative login is allowed.

Alternative custody lock-in is not.

## Selected Embedded Wallet Provider

This architecture keeps **MetaMask** as the only live login path today and treats **Privy embedded wallets** as a planned follow-up.

Why Privy is still the leading embedded-wallet candidate:

- supports email and social login
- exposes an embedded EVM wallet address
- supports arbitrary message signing through an EIP-1193-style provider
- supports export and recovery guidance
- does not require the ZoidbergChain backend to custody keys
- has a supported React web SDK that can be isolated later inside a small React island

MetaMask remains the existing external-wallet path.

## Live Frontend Architecture

### Provider adapters

The frontend now routes wallet actions through a provider registry instead of hardcoding MetaMask-only calls.

Current adapters:

- `MetaMaskAdapter`
- `EmbeddedWalletAdapter` placeholder for future Privy onboarding

Primary files:

- `zoidbergcoin-ui/src/services/walletProviderAdapter.js`
- `zoidbergcoin-ui/src/services/wallet.js`
- `zoidbergcoin-ui/src/services/privyEmbeddedWallet.js`
- `zoidbergcoin-ui/src/services/nativeTransfer.js`

Shared adapter contract:

- `provider_id`
- `provider_label`
- `provider_type`
- `isAvailable()`
- `connect()`
- `getAddress()`
- `requestSignature(message, walletAddress)`
- `disconnect()`
- `getConnectionStatus()`

### Access-gate login paths

The access gate now shows two user-facing choices:

1. `Continue with MetaMask`
2. `Continue with Email / Social Wallet`

The second path stays visibly disabled as coming soon, even when frontend Privy env is present, until a supported React-island integration is implemented.

Primary file:

- `zoidbergcoin-ui/src/components/ControlledAccessGate.vue`

### Deferred embedded wallet plan

Selected future implementation path:

1. Mount a small React island only for the Email / Social Wallet flow.
2. Wrap that island in Privy’s supported `PrivyProvider` from `@privy-io/react-auth`.
3. Use Privy’s supported React login hooks for email and social login.
4. Restore or create the user’s embedded EVM wallet inside that island.
5. Pass the wallet address and signing capability back into the existing Vue wallet manager surface.
6. Reuse the same backend wallet challenge and signature verification flow used by MetaMask.

Why the current Vue path was deferred:

- `@privy-io/js-sdk-core` is a low-level SDK
- the attempted Vue/Vite browser integration kept failing at import time on `eventemitter3`
- keeping a broken active login button was worse than clearly marking the feature as coming soon

MetaMask still works the same way, through the existing wallet-manager surface.

## Backend Trust Boundary

No backend trust model change was required for this task.

The backend still authorizes based on:

- normalized wallet address
- valid challenge signature
- verified wallet session

The backend does **not** trust `provider_id` as proof of custody or eligibility.

That means the same wallet session can be used for:

- returning approved-wallet login
- access binding
- submission signing
- vote signing
- native transfer signing
- rewards and balance reads

## Portability Rules

MetaMask wallets are already user-controlled external wallets.

Privy embedded wallets are acceptable for beta onboarding only because the product direction requires a portability path before any mainnet-value use. The app should point users to provider portability and export guidance rather than handling key export directly.

Current frontend portability support:

- provider metadata exposes portability help copy
- the access gate and wallet UI can show portability guidance
- no seed phrase or private key is exposed by the app

## Required Frontend Environment Variables

Use only public frontend IDs here. Never place provider secrets in Vite env.

- `VITE_EMBEDDED_WALLET_PROVIDER=privy`
- `VITE_PRIVY_APP_ID=<public app id>`
- `VITE_PRIVY_SOCIAL_PROVIDER=google`

Even when `VITE_EMBEDDED_WALLET_PROVIDER` and `VITE_PRIVY_APP_ID` are present, MetaMask remains the only active login path until the React-island implementation lands.

## Local Development Setup

1. Install frontend dependencies in `zoidbergcoin-ui`.
2. Add the public Privy app and client IDs to the Vite env.
3. Start the backend normally.
4. Start the frontend normally.
5. Test both access-gate states:
   - MetaMask active
   - Email / Social Wallet visibly coming soon

For mobile testing:

- MetaMask users may still need the MetaMask Mobile browser for injected-wallet flows.
- Embedded-wallet login should be tested in a normal mobile browser as well.

## Deployment Notes

- Do not deploy provider secrets to the frontend.
- Keep MetaMask enabled even when embedded onboarding env is configured.
- If embedded config is omitted or deferred, the second path should remain visibly disabled instead of disappearing.
- Before any broader rollout, verify portability messaging and export guidance on the production deployment.

## Current Limitations

- This task does not ship a live embedded-wallet login yet.
- The current planned embedded provider remains Privy.
- The supported implementation direction is a React island using `@privy-io/react-auth`.
- Some older backend account metadata may still use MetaMask-era labels such as `metamask_native`; those labels do not control authorization.
- Mobile helper copy still includes MetaMask-specific instructions for injected-wallet users.
- No multi-provider account-management UI is required yet.

## Bottom Line

ZoidbergChain now supports:

- the existing MetaMask path
- a clearly deferred email/social wallet path
- the same backend signature-verification model reserved for any future embedded-wallet path

The onboarding surface stays honest and stable today, while wallet verification and account trust still remain wallet-based.
