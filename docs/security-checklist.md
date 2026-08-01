# Native Transaction Security Checklist

As of Saturday, August 1, 2026, this checklist covers the current Task 8.10 native transaction hardening pass.

## Task 8 Closeout Status

Task 8 is complete for controlled dev/testnet use.

- native ZOID transfers are MetaMask-signed
- transactions persist as canonical records with deterministic `tx_id`
- nonce and replay protection are active
- balance sufficiency and available-balance enforcement are active
- local mempool lifecycle exists
- peer transaction gossip exists
- native transfers can be included in certified meme-mined blocks
- transfers settle only inside accepted meme-mined blocks
- peer block validation checks native transfer transactions
- two-node native transfer verification exists
- Task 8.10 validation, reliability, and regression review is complete

## Threat Model Summary

- native ZOID transfers are signed ZoidbergChain messages, not Ethereum or ERC-20 transfers
- wallet session state is required for local user submit flows only
- peer-delivered transactions must validate by canonical payload and recovered signer without local browser session trust
- mempool state is local and non-final
- settlement happens only inside accepted meme-mined blocks
- backup, export, import, and reload flows must preserve canonical native transaction state without exposing secrets

## Manual Verification Checklist

- connect MetaMask
- verify wallet session
- request a native transfer signing challenge
- confirm the signing message includes action, network, sender, recipient, amount, fee, nonce, timestamp, and memo when present
- reject a tampered transfer message
- reject a duplicate nonce
- reject insufficient available balance
- reject wrong-network transfer payloads
- reject invalid signature payloads
- record a valid signed transfer
- confirm the UI says `Signed native ZOID transfer recorded. Not settled yet.`
- admit a valid transaction to the local mempool
- reject invalid mempool admission
- confirm the UI says `In local mempool. Not settled yet.`
- broadcast a valid transaction to a peer
- reject an invalid peer transaction
- mint a meme-mined block with the transaction
- reject an invalid transfer-bearing block
- sync a valid transfer-bearing block from a peer
- confirm balances match after sync
- confirm no private keys, session tokens, peer secrets, file paths, or stack traces appear in public read responses
- confirm pending UI never says settled, confirmed, payment complete, Ethereum transfer, or ERC-20 transfer

## Automated Coverage Targets

- signature mismatch and malformed signature rejection
- deterministic `tx_id` generation and stable canonical serialization
- strict sequential nonce enforcement and duplicate idempotency
- available-balance enforcement for pending outgoing transfers
- mempool revalidation and safe public serialization
- peer receive and broadcast failure handling
- transfer-bearing block validation against chain-before-block balances and nonces
- storage reload cleanup of malformed native transaction state
- backup/export/import preservation of canonical native transaction records

## Known Intentional Limits

- no replacement policy yet
- mempools are still local, not consensus-wide
- no transfer-only blocks
- no wrapped ZOID or ERC-20 behavior
- no external production security audit yet
- treat the current feature set as controlled dev/testnet only unless hardened further
