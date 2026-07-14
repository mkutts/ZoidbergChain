# Native Wallet Architecture

Task 7.0B documents the approved wallet and token architecture decisions for ZoidbergChain.

This document records approved architecture direction. It does not implement MetaMask login, wallet generation, transfers, or any consensus changes by itself.

## Project Goal

ZoidbergChain is intended to become its own native Layer 1 network.

The long-term chain identity is:

- ZOID is the native coin of ZoidbergChain.
- Meme Proof of Originality remains the core block and reward mechanism.
- MetaMask is used as a signing wallet and identity tool.
- MetaMask usage does not mean ZOID is an ERC-20 token.
- Wrapped ZOID may be added later for DEX liquidity or exchange pairing.

## Terms And Distinctions

### Native ZOID

- Native ZOID is the balance tracked directly by ZoidbergChain.
- It lives in the ZoidbergChain ledger.
- It is the asset earned from meme-mining rewards in this architecture phase.

### Wrapped ZOID

- Wrapped ZOID is a possible future external representation of ZOID.
- It may later exist for DEX liquidity, exchange pairing, or bridge-based interoperability.
- Wrapped ZOID is not the same thing as the initial native ZOID ledger balance.

### ERC-20 Token

- An ERC-20 token is an Ethereum-compatible smart-contract token standard.
- ZoidbergChain is not launching first as an ERC-20-first project.
- MetaMask support for signatures does not convert native ZOID into an ERC-20.

### MetaMask Identity

- MetaMask is the initial wallet used for identity and signatures.
- Users prove control of a wallet by signing a challenge or action message.
- The signing wallet is the user identity anchor for login, submissions, votes, rewards, and future transfers.

### MetaMask-Formatted ZoidbergChain Wallet

- ZoidbergChain uses Ethereum-style `0x...` wallet addresses as the native account format for users.
- MetaMask holds the private key for that address.
- ZoidbergChain stores the native ZOID balance associated with that address.
- In this architecture, a MetaMask-style `0x` address functions as a ZoidbergChain wallet address even though native ZOID is not initially shown inside normal MetaMask.

## Architecture Invariants

- ZOID is native to ZoidbergChain.
- ZoidbergChain is not launching first as an ERC-20.
- Meme Proof of Originality remains the core block/reward mechanism.
- MetaMask is initially used for identity and signing.
- MetaMask `0x` addresses are the native account format for ZoidbergChain users.
- MetaMask holds the private key.
- ZoidbergChain stores native ZOID balances.
- Backend must not hold normal users' private keys.
- New submissions must be signed by the submitting wallet.
- New votes must be signed by the voting wallet.
- Mining rewards are credited to the verified submitter wallet address.
- Native transfers will be MetaMask-signed.
- Wrapped ZOID is a later bridge/liquidity feature.
- Old dev wallets/test records may be reset.

## Native Account Model

The native account model for ZoidbergChain users is:

1. User connects MetaMask.
2. User signs a login challenge or action message.
3. Backend or node verifies the signature.
4. The recovered `0x` address becomes the ZoidbergChain wallet address for that user action.
5. The address is normalized consistently before persistence and comparison.

That normalized `0x` address is used for:

- login
- submissions
- votes
- rewards
- future transfers
- future anti-Sybil or reputation rules

Normal MetaMask does not initially show the native ZOID balance. The balance lives on ZoidbergChain first and is shown in the ZoidbergChain app or explorer.

## Signed Meme Submissions

Every new meme submission must be signed by the submitting MetaMask wallet.

Draft message shape:

```json
{
  "action": "submit_content",
  "network": "zoidberg-testnet-1",
  "wallet_address": "0x...",
  "content_hash": "...",
  "content_id": "...",
  "timestamp": "...",
  "nonce": "..."
}
```

Submission signing rules:

- The signature proves the wallet submitted a specific `content_hash`.
- Backend verifies the signature before accepting the submission.
- The creator wallet is derived from the verified signer.
- Frontend should not allow arbitrary creator wallet entry after this is implemented.

Approved meaning of the signature:

`I, wallet 0xABC..., am submitting content_hash XYZ to ZoidbergChain.`

## Signed Originality Votes

Every vote must be signed by the voting MetaMask wallet.

Draft message shape:

```json
{
  "action": "vote_originality",
  "network": "zoidberg-testnet-1",
  "wallet_address": "0x...",
  "submission_id": "...",
  "content_hash": "...",
  "vote": "original",
  "timestamp": "...",
  "nonce": "..."
}
```

Voting rules:

- Every vote is signed.
- One vote per wallet per submission.
- The signature proves the wallet voted on that specific submission.
- Vote options remain `original`, `not_original`, or `unsure`.

Approved meaning of the signature:

`I, wallet 0xABC..., vote ORIGINAL / NOT_ORIGINAL / UNSURE on submission XYZ.`

## Native ZOID Rewards

- A certified meme block mints the reward under the existing Meme Proof of Originality flow.
- The reward goes to the submitter's verified `0x` wallet.
- The reward is native ZOID on the ZoidbergChain ledger.
- The current reward remains the current configured block reward, which is `5 ZOID` in [config.py](C:/Users/mattk/ZoidbergChain/config.py:8) unless configuration changes later.
- No ERC-20 or wrapped token minting is part of Task 7.

## Native Transfer Model

Task 7 defines MetaMask-signed native transfer messages as the initial transfer model. It does not implement full transaction hardening yet.

Draft transfer message shape:

```json
{
  "action": "transfer_zoid",
  "network": "zoidberg-testnet-1",
  "from_address": "0x...",
  "to_address": "0x...",
  "amount": "10",
  "nonce": 1,
  "fee": "0",
  "timestamp": "...",
  "signature": "..."
}
```

Transfer model notes:

- Task 7 introduces and defines MetaMask-signed transfer messages.
- Task 8 hardens balances, nonces, replay protection, fees, mempool behavior, and block inclusion.
- Native ZOID transfers are not ERC-20 transfers.

## Clean Reset / Legacy Strategy

- Current users and wallets are test artifacts.
- Clean reset is allowed before MetaMask identity becomes standard.
- Old backend or dev wallets do not need to be preserved as a long-term requirement.
- Old submissions, old votes, old mint queue records, and bad content records can be discarded if needed.
- Going forward, MetaMask `0x` addresses are the real ZoidbergChain wallet identity.
- Dev reset tools must remain disabled or guarded outside development mode.
- Reset procedure details live in [docs/clean-reset-runbook.md](C:/Users/mattk/ZoidbergChain/docs/clean-reset-runbook.md).

## Dev-Only MetaMask Test Wallets

- The project needs several dev-only wallets for UI testing with multiple votes and user flows.
- These wallets should be importable into MetaMask.
- Their private keys are dev-only and unsafe for real funds.
- Dev wallet private keys must never be exposed through production or public APIs.
- Dev wallet generation must never be enabled in production mode.
- A future task may add dev-only wallet generation, seeding, or faucet tooling if it helps testing.
- Recommended local export path is `data/dev_wallets.json` or a similar ignored file under `data/`.
- Import several of these private keys into a separate browser profile running MetaMask for multi-account UI testing.
- Never use these wallets with real ETH, real ZOID, or public server deployments.

## Near-Term Product Interpretation

- MetaMask is the user's signing wallet.
- The `0x` address is the user's native ZoidbergChain account identifier.
- Native ZOID balances appear in the ZoidbergChain app or explorer first.
- Wrapped ZOID may come later for DEX liquidity, exchange pairing, or bridge-based interoperability.
- A later MetaMask Snap or custom wallet may support native ZOID more directly.
