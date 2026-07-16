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
- It is intended to be backed 1:1 by native ZOID when that bridge/liquidity model is introduced.
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
- Native transfers will later evolve into full transaction validation, mempool behavior, and block inclusion.
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

Every new meme submission must be signed by the submitting MetaMask wallet after the clean reset and Task `7.4`.

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
- The submission challenge is created by `POST /auth/wallet/submission-challenge` after a verified wallet session already exists.
- The challenge message is signed with MetaMask `personal_sign`.
- Backend verifies the signature before accepting the submission.
- The creator wallet is derived from the verified signer.
- Frontend should not allow arbitrary creator wallet entry after this is implemented.
- The verified wallet session from Task `7.3` is the prerequisite identity layer, but the submission itself still requires a direct per-submission signature.
- Submission nonces are single-use and expiring.
- Replay attempts, modified messages, mismatched content references, and signer/session mismatches are rejected.

Submission challenge request shape:

```json
{
  "wallet_address": "0x...",
  "content_hash": "...",
  "content_id": "...",
  "caption": "..."
}
```

Submission request shape:

```json
{
  "wallet_address": "0x...",
  "content_hash": "...",
  "content_id": "...",
  "message": "...",
  "signature": "..."
}
```

Approved meaning of the signature:

`I, wallet 0xABC..., am submitting content_hash XYZ to ZoidbergChain.`

## Signed Originality Votes

Every originality vote must be signed by the voting MetaMask wallet after the clean reset and Task `7.5`.

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
- The verified wallet session from Task `7.3` is the prerequisite identity layer, but the vote itself still requires a direct per-vote signature.
- Direct signed vote messages become required in Task `7.5` after the clean reset for all new originality votes.
- The voting wallet is the verified MetaMask `0x` session wallet and is not user-editable.
- The vote challenge must bind the wallet, submission, content hash, selected vote, network, issued time, expiry, and nonce into one single-use message.
- Replay attempts, signer mismatches, wallet/session mismatches, submission mismatches, and modified vote messages are rejected.

Approved meaning of the signature:

`I, wallet 0xABC..., vote ORIGINAL / NOT_ORIGINAL / UNSURE on submission XYZ.`

## Native ZOID Rewards

- A certified meme block mints the reward under the existing Meme Proof of Originality flow.
- The reward goes to the submitter's verified `0x` wallet.
- The reward is native ZOID on the ZoidbergChain ledger.
- The current reward remains the current configured block reward, which is `5 ZOID` in [config.py](C:/Users/mattk/ZoidbergChain/config.py:8) unless configuration changes later.
- No ERC-20 or wrapped token minting is part of Task 7.
- Wrapped ZOID, when introduced later, is intended as a bridge/liquidity feature backed 1:1 by native ZOID rather than as a replacement for native rewards.
- The minting user or node operator is not automatically the reward recipient. The reward recipient is the signed submission creator wallet.
- Reward accounting is persisted through the minted block itself, including reward type, reward recipient, reward amount, reward source, and minted timestamp.
- Native wallet balances are read from ZoidbergChain state and explorer APIs rather than from normal MetaMask asset display.

## Native Transfer Model

Task 7.7 defines the canonical native ZOID transfer message model only. It does not execute transfers, mutate balances, include transfers in blocks, or implement mempool behavior yet.

- Native transfers are MetaMask-signed ZoidbergChain messages, not ERC-20 transfers.
- Task 7.8 is the planned transfer-submission step.
- Task 7.9 defines the mempool and inclusion design plan.
- Task 8 is the planned hardening step for balances, replay protection, mempool behavior, fees, and block inclusion.
- The detailed transfer payload, canonical signing message, provisional decimal strategy, and future transfer statuses are documented in [docs/native-transfer-message-model.md](C:/Users/mattk/ZoidbergChain/docs/native-transfer-message-model.md).
- The full transaction lifecycle, nonce strategy, balance model, fee policy, mempool rules, and future inclusion plan are documented in [docs/native-transaction-layer-plan.md](C:/Users/mattk/ZoidbergChain/docs/native-transaction-layer-plan.md).

## Task 7.8 Signed Transfer Intents

- Task 7.8 adds MetaMask-signed native transfer intent submission as a local non-final record.
- `POST /auth/wallet/transfer-challenge` issues the exact transfer-signing message for the verified wallet.
- `POST /transfers/submit` stores the signed result as a `signed_pending` transfer intent.
- `GET /transfers/{transfer_id}` and `GET /wallets/{wallet_address}/transfers` expose safe transfer-intent history.
- Signed transfer intents do not settle funds yet.
- Signed transfer intents do not reduce final native balance yet.
- Signed transfer intents are not yet peer-propagated or block-included.

## Task 7.9 Transaction Layer Plan

- Task 7.9 documents the future path from `signed_pending` transfer intent to `validated_pending`, `mempool`, `included`, and `settled` native transaction states.
- Only included and settled transactions should affect final balances.
- The recommended initial nonce policy is strict sequential sender nonces with no gaps and no replacement policy.
- The recommended initial fee policy is that the `fee` field exists but must remain `0` until explicit fee design is introduced.
- Mempool transactions remain a Task 8 implementation concern, not a Task 7.9 behavior change.
- Transfer inclusion in meme-mined blocks must not change Meme Proof of Originality or originality scoring.
- Wrapped ZOID remains a later bridge or liquidity feature and is not part of this native transaction-settlement plan.

## Task 7.10 Wallet And Transfer UI

- Task 7.10 cleans up the wallet-facing UI without changing settlement behavior.
- The verified wallet panel clearly shows:
  - connected wallet address
  - verified or unverified session state
  - native ZOID balance on ZoidbergChain
  - reward history for meme-mining rewards
  - signed transfer-intent history
- The UI explicitly reminds users that native ZOID does not appear in normal MetaMask yet.
- The UI must not imply that MetaMask stores the native ZOID balance.
- Transfer records are labeled as signed transfer intents with pending transaction processing and not settled yet.
- Pending transfer intents do not reduce the displayed final native balance unless a separate safe available-balance field is provided.
- Submission and voting flows continue to use the verified MetaMask wallet identity rather than old development-wallet assumptions.

## Clean Reset / Legacy Strategy

- Current users and wallets are test artifacts.
- Clean reset is allowed before MetaMask identity becomes standard.
- Old backend or dev wallets do not need to be preserved as a long-term requirement.
- Old backend or dev wallets are disposable test artifacts and do not require long-term compatibility.
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

## Task 7.1 Frontend Scope

- Task 7.1 adds frontend MetaMask connection only.
- A connected MetaMask address is not yet a backend-verified ZoidbergChain identity.
- Task 7.2 will add the nonce challenge and backend signature verification flow.
- Native ZOID balance still appears in the ZoidbergChain app or explorer, not in normal MetaMask.

## Task 7.2 Verified Wallet Login

- Task 7.2 adds backend challenge-response verification for MetaMask wallet login.
- `POST /auth/wallet/challenge` issues a single-use, expiring login challenge for a `0x` wallet address.
- `POST /auth/wallet/verify` verifies an Ethereum `personal_sign` signature against the stored challenge message.
- A successful verification creates an expiring verified wallet session token for that normalized `0x` address.
- Connection alone is still not trusted identity. Verification requires both the challenge and the signed response.
- Signed meme submissions become required in Task `7.4`.
- Signed originality votes become required in Task `7.5`.

## Task 7.3 Verified Wallet Session Identity

- Task 7.3 makes the verified MetaMask wallet session the app's current source of user identity.
- `GET /auth/wallet/session` returns the active verified wallet session for the bearer token and confirms the normalized `0x` address tied to that session.
- `POST /auth/wallet/logout` revokes the current verified wallet session token without affecting chain data.
- The frontend now restores a saved verified session by checking it against the backend instead of trusting browser storage alone.
- If the wallet account changes, the chain changes, or the session expires, the verified identity is cleared and the user must verify again.
- Submission and voting screens may prefill or label the verified wallet identity, but they still use the existing backend fields until direct signed submissions and votes are introduced later.
- This session model is currently in-memory on the backend, so server restarts clear active verified wallet sessions.
- Task `7.3` is the prerequisite identity layer for the direct signed submission and vote requirements that begin in Task `7.4` and Task `7.5`.

## Task 7.4 Signed Submission Flow

- Task `7.4` requires a verified wallet session plus a direct MetaMask signature for each new submission.
- `POST /auth/wallet/submission-challenge` issues an expiring single-use submission challenge bound to:
  - the verified `0x` wallet
  - the current network name
  - the specific `content_hash`
  - the specific `content_id` when provided
  - the submission caption when provided
- `POST /submit_content` now verifies:
  - the bearer token for the verified wallet session
  - the exact signed challenge message
  - the recovered signer address
  - the content reference integrity
  - nonce freshness and single-use replay protection
- The stored submission creator is derived from the verified signer rather than user-entered form data.
- Signed submission audit metadata is stored with the submission record, including:
  - creator wallet address
  - signature scheme
  - submission signature
  - signed message hash
  - submission nonce
  - signed timestamp
  - identity source
- Vote signing is still deferred to Task `7.5`.

## Task 7.5 Signed Originality Vote Flow

- Task `7.5` requires a verified wallet session plus a direct MetaMask signature for each new originality vote.
- `POST /auth/wallet/vote-challenge` issues an expiring single-use vote challenge bound to:
  - the verified `0x` wallet
  - the current network name
  - the specific submission id
  - the specific submission content hash
  - the selected vote value
- `POST /submissions/{submission_id}/vote` now verifies:
  - the bearer token for the verified wallet session
  - the exact signed challenge message
  - the recovered signer address
  - the submission/content reference integrity
  - nonce freshness and single-use replay protection
- The stored voter identity is derived from the verified signer rather than user-entered wallet data.
- One wallet may cast only one vote per submission under the existing originality rules.
- The submission creator may not vote on that same submission.
- Signed vote audit metadata is stored with the vote record, including:
  - voter wallet address
  - content hash
  - signature scheme
  - vote signature
  - vote message
  - signed message hash
  - vote nonce
  - signed timestamp
  - identity source
- Outside development mode, legacy or unsigned vote submission paths are no longer the normal voting path.

## Task 7.6 Native Reward Crediting

- Task `7.6` credits the native meme-mining reward to the signed submission creator wallet when a certified submission is minted into a block.
- The reward recipient is derived from the stored signed submission creator wallet identity rather than from the user who clicked mint.
- `POST /mint/{submission_id}` and `POST /mint-queue/{submission_id}/mint` now return reward metadata including:
  - reward type
  - reward recipient
  - reward amount
  - block hash
  - block height
- Minted certified blocks now persist reward audit metadata including:
  - reward type
  - reward recipient
  - reward amount
  - reward source
  - minted timestamp
- `GET /wallets/{wallet_address}/balance` returns the native ZoidbergChain wallet balance for that identity.
- `GET /wallets/{wallet_address}/rewards` returns the wallet's meme-mining reward history.
- Native ZOID still appears in the ZoidbergChain app or explorer rather than in normal MetaMask asset balances.
- Native transfers, mempool behavior, and wrapped ZOID remain deferred to later tasks.
