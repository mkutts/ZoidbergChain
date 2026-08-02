# Task Roadmap

This roadmap captures the current documented task sequence for the native wallet and MetaMask signature identity work.

## Current Status

ZoidbergChain is complete through Task 8 for controlled dev/testnet use.

Completed now:

- Task 1: Coin Rules and Submission Lifecycle
- Task 2: Peer-to-Peer Networking
- Task 3: Meme Proof of Originality Consensus
- Task 4: Security and Key Management
- Task 5: Storage Hardening
- Task 6: Content Storage and Transport
- Task 7: MetaMask Native Wallet Identity
- Task 8: Native Transaction Layer Hardening

Known intentional limitations:

- no replacement policy
- mempools are local, not consensus-wide
- transfer-only blocks are intentionally unsupported
- no wrapped ZOID / ERC-20 behavior
- not production/mainnet ready
- dev/testnet only until later hardening

## Task 7: Native Wallet + MetaMask Signature Identity

- 7.0A Architecture decision worksheet
- 7.0B Document approved architecture decisions
- 7.0C Clean reset + dev test wallet strategy
- 7.1 MetaMask connect/login UI
- 7.2 Backend nonce challenge + signature verification
- 7.3 Verified wallet session model
- 7.4 Signed meme submissions
- 7.5 Signed originality votes
- 7.6 Native reward accounting to MetaMask address
- 7.7 Native transfer message model
- 7.8 MetaMask-signed native transfers
- 7.9 Mempool + transaction inclusion plan
- 7.10 Wallet balance and transaction UI
- 7.12 Wallet/account terminology cleanup + native account view

## Task 8: Native Transaction Hardening

Status: complete for controlled dev/testnet use as of Saturday, August 1, 2026.

- 8.1 Transaction ID + canonical transaction record
- 8.2 Nonce tracking and replay protection
- 8.3 Balance sufficiency / available balance
- 8.4 Mempool storage and validation
- 8.5 Peer transaction gossip
- 8.6 Include validated transfers in meme-mined blocks
- 8.7 Block validation with transfers
- 8.8 Wallet balances and transfer history
- 8.9 Two-node transfer test
- 8.10 Transaction layer validation / reliability / security pass

Task 8 now includes:

- MetaMask-signed native ZOID transfers
- canonical `tx_id` transaction records
- nonce and replay protection
- balance sufficiency and available-balance enforcement
- local mempool lifecycle
- peer transaction gossip
- native transfer inclusion in certified meme-mined blocks
- settlement only inside accepted meme-mined blocks
- peer block validation for transfer-bearing blocks
- two-node native transfer verification
- Task 8.10 validation, reliability, and regression review

Known remaining limitations by design:

- no replacement policy yet
- mempools are local, not consensus-wide
- transfer-only blocks remain intentionally unsupported
- no wrapped ZOID / ERC-20 behavior
- old `/wallets/...` compatibility read endpoints still exist
- appropriate for controlled dev/testnet use, not production-hardening complete

## Stage Definitions

Stage 1:
Public demo / controlled testnet explorer after Task 9.

Stage 2:
Invite-only public testnet after Task 10.

Stage 3:
Open public testnet after Tasks 11-13.

Stage 4:
Mainnet / real value readiness after Tasks 14-18 and external review.

## Next Major Phase

Task 9: Public Demo / Testnet Deployment Readiness.

This phase makes `zoidbergcoin.com` safe to show publicly as a controlled demo/testnet explorer without changing consensus, storage defaults, or the native transaction model.

## Tasks 9-18

- Task 9: Public Demo / Testnet Deployment Readiness
- Task 10: Voting Identity, Anti-Sybil Rules, and Voter Incentives
- Task 11: Multi-Media Original Content Support
- Task 12: Content Compression, Storage Strategy, and Chain Bloat Prevention
- Task 13: Public Content Moderation and Abuse Controls
- Task 14: Production Node and Validator Hardening
- Task 15: Transaction Policy Completion
- Task 16: Token Economics and Reward Policy Finalization
- Task 17: Wrapped ZOID / ERC-20 Bridge Planning
- Task 18: External Review / Audit / Mainnet Launch Checklist

Detailed staged roadmap:

- see [roadmap.md](/C:/Users/mattk/ZoidbergChain/docs/roadmap.md)

## Task 10.1 Status

Task 10.1 adds the voting eligibility foundation for the invite-only public testnet:

- configurable reviewer modes: `open`, `allowlist`, `activity`, and `hybrid`
- a public `/review/policy` explanation endpoint for tester-facing visibility
- wallet denylist support and optional daily vote caps
- activity-based reviewer qualification using current on-chain account history where available

This remains controlled-testnet anti-Sybil friction only. It is not KYC, proof-of-personhood, staking, or a complete solution to multi-wallet abuse.

Task 10.2 is still reserved for voter reward logic tied to the final majority side.
