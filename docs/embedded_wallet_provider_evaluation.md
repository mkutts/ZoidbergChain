# Embedded Wallet Provider Evaluation

Last updated: August 24, 2026

## Evaluation Standard

ZoidbergChain should prefer wallet providers that maximize:

- portability
- arbitrary message signing support
- stable EVM address behavior
- clear provider survivability
- low lock-in risk

This document is intentionally provider-neutral first. A recommendation is included at the end, but no provider integration is committed here.

## Summary Matrix

### 1. MetaMask Embedded Wallets / social login

- Stable wallet address: yes, but implementation choices must stay consistent because provider configuration can affect addresses.
- Arbitrary message signing: yes for EVM through the provider surface.
- Native ZOID intent signing: likely yes if handled as EVM-style message signing.
- Custody model: described publicly as embedded wallets with non-custodial roots inherited from the former Web3Auth product line.
- Export or migration clarity: weaker public evidence than Privy in the sources reviewed for this task.
- Provider failure concern: portability depends on documented export and migration guarantees being validated in a real spike.
- Desktop support: yes.
- Mobile support: yes.
- Developer complexity: moderate.
- Beta suitability: plausible.
- Mainnet suitability: only after export and migration are proven end to end.
- Lock-in risk: medium until export behavior is explicitly validated.
- Disclosure needed: explain login method, custody model, and migration path before real-value use.

Sources reviewed:

- https://docs.metamask.io/
- https://metamask.io/developer/embedded-wallets
- https://github.com/MetaMask/metamask-docs/blob/main/embedded-wallets/migration-guides/web.mdx

### 2. Privy-style embedded wallets

- Stable wallet address: yes.
- Arbitrary message signing: yes.
- Native ZOID intent signing: likely yes for EVM message signing flows.
- Custody model: configurable; can be non-custodial or custodial depending on setup.
- Export or migration clarity: strong. Privy publicly documents wallet export and explicitly frames export as a self-sovereign escape hatch.
- Provider failure concern: better than most embedded options if export is enabled and tested in the chosen environment.
- Desktop support: yes.
- Mobile support: yes, with documented web-based export flow constraints.
- Developer complexity: moderate.
- Beta suitability: strong candidate.
- Mainnet suitability: possible if configured for portable user control and validated with real export drills.
- Lock-in risk: lower than typical embedded options when export is enabled and disclosed.
- Disclosure needed: explain whether the app is using non-custodial, custodial, or quorum-based controls and what exact export path users have.

Sources reviewed:

- https://docs.privy.io/wallets/overview/embedded
- https://docs.privy.io/wallets/wallets/export
- https://docs.privy.io/recipes/mobile-key-export
- https://docs.privy.io/controls/authorization-keys/owners/overview

### 3. Web3Auth-style embedded wallets

- Stable wallet address: yes, but provider configuration consistency matters.
- Arbitrary message signing: yes through the EVM provider surface.
- Native ZOID intent signing: likely yes.
- Custody model: public material describes non-custodial roots with MPC or split-key design.
- Export or migration clarity: mixed in the public sources reviewed here. There is evidence of provider methods for key-oriented access, but portability needs product-specific validation.
- Provider failure concern: medium until export semantics are tested with the exact deployment mode.
- Desktop support: yes.
- Mobile support: yes.
- Developer complexity: moderate.
- Beta suitability: plausible.
- Mainnet suitability: only with validated migration or export.
- Lock-in risk: medium.
- Disclosure needed: explain whether the deployed mode exports the controlling wallet key or another compatibility key path.

Sources reviewed:

- https://github.com/MetaMask/metamask-docs/blob/main/embedded-wallets/migration-guides/web.mdx
- https://github.com/web3auth

### 4. Passkey-based wallet / account abstraction later

- Stable wallet address: possible, but product architecture matters.
- Arbitrary message signing: possible.
- Native ZOID intent signing: possible.
- Custody model: highly implementation-dependent.
- Export or migration clarity: usually the hardest part and must be designed explicitly.
- Provider failure concern: high if passkey login is treated as the identity while wallet portability is an afterthought.
- Desktop support: good in modern browsers.
- Mobile support: improving, but cross-platform consistency can vary.
- Developer complexity: high.
- Beta suitability: not the first move here.
- Mainnet suitability: only after portability is solved.
- Lock-in risk: medium to high if implemented naively.
- Disclosure needed: explain that passkeys are login factors, not a reason to weaken wallet portability.

Observation:

- Passkeys are best treated as a user-auth factor that unlocks a portable wallet flow, not as a substitute for portability requirements.

### 5. Email magic-link plus embedded wallet

- Stable wallet address: yes if backed by a consistent embedded wallet provider.
- Arbitrary message signing: yes if the embedded wallet exposes standard EVM signing.
- Native ZOID intent signing: likely yes.
- Custody model: depends entirely on the embedded wallet provider.
- Provider failure concern: same as the underlying embedded provider.
- Desktop support: yes.
- Mobile support: yes.
- Developer complexity: moderate.
- Beta suitability: strong if paired with a provider that has real export support.
- Mainnet suitability: possible with portability guarantees.
- Lock-in risk: inherited from the embedded provider.
- Disclosure needed: email login is convenience only; the wallet still controls ZOID.

### 6. WalletConnect as broader external wallet option

- Stable wallet address: yes.
- Arbitrary message signing: yes for EVM sessions supporting `personal_sign`.
- Native ZOID intent signing: yes, assuming the connected wallet supports the requested EVM methods.
- Custody model: user keeps their own external wallet.
- Export or migration clarity: strong, because the wallet is already external.
- Provider failure concern: lower than embedded login options because WalletConnect is a bridge, not the custody layer.
- Desktop support: yes.
- Mobile support: yes.
- Developer complexity: moderate.
- Beta suitability: very strong as a complement to MetaMask.
- Mainnet suitability: strong.
- Lock-in risk: low.
- Disclosure needed: connection method does not itself create custody; the external wallet remains the controller.

Sources reviewed:

- https://docs.walletconnect.network/wallet-sdk/chain-support/evm
- https://docs.walletconnect.network/wallet-sdk/web/usage

## Recommendation

Recommended near-term path:

1. Keep MetaMask as the working beta path.
2. Add WalletConnect later as the safest expansion for users who already have another wallet.
3. For true low-friction onboarding, run a short embedded-wallet spike with a strong preference for providers that already document user export clearly.

Current recommendation for that spike:

- Privy-style embedded wallet onboarding is the strongest candidate for a future beta pilot because the reviewed documentation is the clearest on export and user self-sovereign escape paths.

Important limit on that recommendation:

- This is a planning recommendation, not a production provider decision.
- A real spike must confirm:
  - exact exported key behavior
  - address stability
  - `personal_sign` compatibility
  - mobile export path quality
  - survivability if the provider relationship ends

## Decision Checklist Before Integration

Before choosing an embedded provider, confirm all of the following in a live prototype:

1. The returned wallet address is stable across normal relogins.
2. The provider signs the exact backend challenge text used by ZoidbergChain.
3. The provider can sign native ZOID transfer intent messages without custom trust shortcuts.
4. Export or migration works in the same environments ZoidbergChain supports.
5. The export or migration path can be explained in one short user-facing paragraph.
6. Losing the provider does not strand the user’s wallet control.
