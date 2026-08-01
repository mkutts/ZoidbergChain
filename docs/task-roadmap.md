# Task Roadmap

This roadmap captures the current documented task sequence for the native wallet and MetaMask signature identity work.

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

## Next Phase

- Task 9 Node identity/open network prep
- Task 10 Public testnet deployment
- Task 11 Wallet UX / MetaMask Snap or custom wallet
- Task 12 Wrapped ZOID bridge planning
- Task 13 Liquidity / exchange readiness
