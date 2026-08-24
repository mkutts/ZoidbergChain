# Portable Wallet Requirements

Last updated: August 24, 2026

## Policy

A wallet or login method is acceptable for ZoidbergChain only if it preserves real wallet control.

Alternative login is acceptable.

Alternative custody lock-in is not acceptable.

## Required Capabilities

A supported wallet path must:

- produce a stable ZoidbergChain-compatible wallet address
- let the user sign wallet verification challenges
- let the user sign native ZOID transaction intents, or clearly disable that action until supported
- support user control, export, or migration before mainnet-value use
- clearly disclose any custody or migration limits
- avoid requiring the ZoidbergChain server to hold user private keys

## Clarifications

- MetaMask-created wallets are not required.
- A portable wallet is required.
- "Portable" means the user can control the signing identity outside an app-locked experience or move to an equivalent supported wallet path before real-value use.
- The app must never ask for or store seed phrases or private keys.
- Public app IDs in frontend env are acceptable. Provider secrets in frontend env are not.

## Current Beta Position

As of August 24, 2026:

- MetaMask remains a supported external-wallet path.
- Privy embedded wallets are allowed as a beta onboarding path.
- Privy is acceptable only because the product direction still requires export, recovery, or migration guidance before any mainnet-value use.
- The ZoidbergChain backend must not custody embedded-wallet private keys.

## Embedded Wallet Acceptance Rules

An embedded wallet provider is acceptable for beta only if:

- the provider yields a stable EVM address
- the app still performs the normal backend challenge and signature verification
- the provider can sign the same kinds of app messages used by the existing wallet flow
- the provider offers a credible export, recovery, or migration path
- the app explains portability in plain English
- users are not promised sale or liquidity outcomes

## Mainnet Readiness Rule

Before any mainnet or real-value ZOID launch, every supported onboarding method must have a documented answer for:

- how the user exports or migrates wallet control
- how the user signs native ZOID transfers
- what happens if the provider disappears
- how the user can continue controlling ZOID without trusting the ZoidbergChain server
- how the team will communicate any migration deadline or portability requirement to users

## Acceptable User Promise

The correct promise is:

"Users should be able to control and transfer their ZOID with their wallet."

The app should not promise:

"Users will be able to sell ZOID."

Selling later depends on future conditions outside wallet onboarding alone, including:

- final mainnet design
- supported transfer model
- bridge design if needed
- liquidity
- exchange or DEX support

## Disallowed Patterns

Do not ship:

- server-custodied wallets for ordinary users
- hidden app-only wallets with no export or migration path
- localStorage-only pseudo-unlock behavior
- provider metadata that bypasses wallet verification
- copy that implies alternative login is live before it works
- copy that implies users can sell ZOID just because a wallet path exists

## UX Disclosure Requirements

Every onboarding path should explain:

- wallets control the user’s ZoidbergChain identity
- test ZOID has no real monetary value today
- users must never share seed phrases or private keys
- easier login does not remove wallet-based control
- mainnet-value use requires portable wallet control or a migration path
- liquidity, bridges, exchanges, and real sale paths are future questions, not present guarantees

## Release Gate

No embedded wallet provider should be launched broadly until ZoidbergChain can answer "yes" to each of these:

1. Can the user prove wallet ownership with a standard signed challenge?
2. Can the user sign native ZOID transfer intents, or is the action explicitly disabled with clear explanation?
3. Can the user export or migrate control?
4. Can the app explain custody and portability in plain English?
5. Can the user avoid being trapped if the provider relationship ends?
