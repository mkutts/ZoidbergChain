# Task 8 Native Ledger, Mempool, And Rewards Extraction

`NativeLedgerService` owns transfer intents/native transaction records, exact
balances, nonce reservation, canonical native serialization, signature/shape
verification, settlement, and reconciliation. `NativeMempoolService` owns
admission, deterministic listing, revalidation, and block candidate selection.
`RewardService` owns canonical-chain-derived creator/voter records, eligibility,
exact units, deterministic plans/selection, wallet queries, and pool accounting.

Authoritative persisted state remains `Blockchain.transfer_intents` and
`Blockchain.native_transactions`, under unchanged field names. Rewards have no
new persisted state because they derive from canonical blocks. Each facade call
constructs a fresh view, preventing stale references after JSON/SQLite reload.
Services never save independently; `Blockchain` preserves persistence timing.

Services receive only narrow collaborators: record lookup, chain conversion,
submission/certificate/vote/threshold/activity/access lookup, and a timestamp
supplier. They import neither `Blockchain`, `api`, FastAPI, nor networking.

Mempool ordering remains `(admitted_at, from_address, nonce, tx_id)`. Block
candidate ordering remains `(from_address, nonce, tx_id)`. Reward records sort
by descending height/mint time then reward ID; due rewards sort by decision time,
submission ID, then recipient. Pending outgoing statuses reserve balances;
settled balances derive from canonical blocks; nonces remain strict sequential.

Creator amounts and recipient precedence, voter decisive-majority eligibility,
creator exclusion, caps, unit rounding, reward IDs/statuses, reward-pool rules,
and disabled-reward behavior are unchanged. `Blockchain` retains complete block
and chain validation, certificate/block context, metadata/hash validation,
candidate acceptance, fork choice, finality, and replacement for Task 9. It
calls service calculations but remains the sole block/chain validity authority.

`blockchain.py` changed from 4,970 physical lines before Task 8 to approximately
3,313 lines after extraction. The remaining deliberate Task 9 coupling is
facade-level block validation over extracted deterministic transaction state.
