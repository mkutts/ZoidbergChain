# ZoidbergCoin UI

This frontend presents native ZOID activity for MetaMask-backed ZoidbergChain accounts.

## Milestone 6 media lifecycle

The Dashboard consumes the additive `lifecycle` object returned by submission
read APIs. It presents technical validation, submitter attestation, originality,
admissibility, pre-mint reporting/quarantine, admission certification,
activation, mint/finality, byte integrity, post-mint disputes, and legacy scope
as separate states. See
`../docs/milestone-6-task-6.10-api-frontend-integration.md` for the schema and
terminology contract.

Staging is not submission or admission. “Media Integrity Verified” means only
that exact bytes match immutable block commitments; it is not a safety,
legality, originality, admissibility, or dispute verdict.

For the Stage 1 public deployment, the UI should visibly say:

- ZoidbergChain controlled testnet
- Test ZOID has no real monetary value
- This network may reset
- Not mainnet
- Native ZOID lives on ZoidbergChain, not Ethereum
- MetaMask signs ZoidbergChain actions

## Native Account UX

- Canonical account reads use `/accounts/{wallet_address}` and related `/accounts/...` endpoints.
- Legacy `/wallets/{wallet_address}/...` reads remain compatibility-only.
- Native ZOID balances are shown as:
  - final native ZOID balance
  - available to spend
  - pending outgoing
  - pending incoming
- Pending outgoing transfers reduce available balance.
- Final balance changes only when a native transfer is settled in a meme-mined block.

## Transaction History UX

- The wallet panel uses canonical native transaction history from `/accounts/{wallet_address}/transactions`.
- User-facing statuses are:
  - signed, not in mempool
  - validated, pending mempool
  - in local mempool
  - included in meme-mined block
  - settled on ZoidbergChain
  - rejected
  - failed
  - expired
- Settled transactions should show their included block height and block hash.

## Wording Rules

- Native ZOID is native to ZoidbergChain.
- Do not describe these balances or transfers as Ethereum balances, ERC-20 balances, or MetaMask token transfers.
- Do not describe the public demo as mainnet, real money, investment, or Ethereum transfer support.
- Transfer-only blocks remain disallowed by design.
- Replacement policy is still not implemented.
