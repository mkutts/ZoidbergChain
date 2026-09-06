# Milestone 4 reliability test coverage

This matrix maps executable coverage to the durable native-transaction acceptance criteria. Task 4.8 adds the cross-component scenarios; focused Task 4.2–4.7 tests remain the authoritative lower-layer coverage.

| Milestone 4 criterion | Test(s) | Layer | Result |
| --- | --- | --- | --- |
| No acknowledged transaction silently disappears | `test_task_4_8_reliability_integration.py::test_pending_sequence_restart_preserves_reservations_and_deterministic_block_order`; `test_native_transfer_api.py::test_task_4_3_lost_response_retry_reads_same_durable_sqlite_record` | restart integration, API | automated |
| Duplicate network delivery cannot duplicate settlement | `test_task_4_6_native_transaction_delivery.py::test_lost_ack_retries_to_durable_idempotent_receiver_admission`; `test_task_4_8_reliability_integration.py::test_receiver_restart_after_lost_ack_returns_idempotent_ack_without_duplicate_reservation` | peer/restart integration | automated |
| Restart preserves accepted pending transactions | `test_task_4_8_reliability_integration.py::test_pending_sequence_restart_preserves_reservations_and_deterministic_block_order` | restart integration | automated |
| Reorg restores canonical state | `test_task_4_7_atomic_reorg_recovery.py::test_sqlite_reorg_atomically_rebuilds_claims_lifecycle_mempool_and_outbox` | reorg integration | automated |
| Reorg requeues still-valid orphaned transactions | `test_task_4_7_canonical_reorg_recovery.py::test_simple_orphan_rebuild_restores_balance_nonce_and_exact_mempool`; `test_task_4_7_atomic_reorg_recovery.py::test_two_nodes_converge_after_winner_adoption_and_requeued_transaction_delivery` | reorg integration | automated |
| Healthy nodes converge after reconnection | `test_task_4_6_native_transaction_delivery.py::test_both_node_restarts_resume_offline_delivery_in_two_simulated_seconds` | peer/restart integration | automated |
| SQLite transaction identity uniqueness | `test_task_4_2_native_transaction_records.py::test_task_4_2_tx_id_identity_is_database_enforced_and_conflicts_fail` | storage | automated |
| Active `(sender, nonce)` uniqueness | `test_task_4_2_native_transaction_records.py::test_task_4_2_active_sender_nonce_constraint_and_release`; `test_task_4_8_reliability_integration.py::test_concurrent_same_nonce_and_overspend_submissions_leave_one_durable_reservation` | storage, concurrency integration | automated |
| Pending balance reservation safety | `test_native_transfer_api.py::test_multiple_pending_transfers_cannot_overcommit_funds`; `test_task_4_8_reliability_integration.py::test_pending_sequence_restart_preserves_reservations_and_deterministic_block_order` | API, restart integration | automated |
| Deterministic validation and strict nonce sequencing | `test_task_4_4_deterministic_native_validation.py`; `test_task_4_8_reliability_integration.py::test_future_nonce_is_rejected_then_succeeds_only_after_predecessor_is_admitted` | service, integration | automated |
| Peer authentication and inner signature validation | `test_peer_transaction_sync_api.py::test_receive_peer_transaction_requires_peer_auth_when_enabled`; `test_peer_transaction_sync_api.py::test_signed_peer_transaction_auth_does_not_bypass_inner_signature_validation` | peer API | automated |
| Durable outbox, lost ACK, retry scheduling, and stale lease | `test_task_4_5_native_transaction_outbox.py::test_claim_is_exclusive_expired_claim_is_recoverable_and_acknowledged_is_not_claimable`; `test_task_4_6_native_transaction_delivery.py::test_backoff_is_persisted_grows_and_caps_without_attempt_limit`; `test_task_4_8_reliability_integration.py::test_receiver_restart_after_lost_ack_returns_idempotent_ack_without_duplicate_reservation` | peer/restart integration | automated |
| New peer and bounded anti-entropy | `test_task_4_6_native_transaction_delivery.py::test_new_peer_gets_only_current_pending_backfill_and_url_change_reuses_row`; `test_task_4_8_reliability_integration.py::test_reconciliation_is_bounded_idempotent_and_does_not_replay_settled_history` | peer integration | automated |
| Canonical claims and rewards are rebuilt | `test_task_4_7_atomic_reorg_recovery.py::test_sqlite_winning_nonce_swap_releases_loser_before_activating_winner`; `test_task_4_7_atomic_reorg_recovery.py::test_sqlite_reward_claims_are_replaced_not_accumulated` | reorg integration | automated |
| Finality/reorg interaction | `test_task_4_7_atomic_reorg_recovery.py::test_finalized_history_mismatch_is_rejected_before_reconstruction`; `test_task_3_5_validator_quorum_finality.py::test_finalized_anchor_cannot_be_replaced_by_a_conflicting_chain` | finality/reorg integration | automated |
| Restart recovery after canonical replacement | `test_task_4_7_atomic_reorg_recovery.py::test_failure_after_durable_commit_keeps_old_memory_and_restart_publishes_winner` | restart/reorg integration | automated |
| Persistence and reorg failure injection | `test_native_transfer_api.py::test_task_4_3_storage_failure_never_acknowledges_or_publishes_a_ghost`; `test_task_4_7_atomic_reorg_recovery.py::test_sqlite_failure_before_commit_leaves_complete_old_state`; `test_task_4_7_atomic_reorg_recovery.py::test_failure_after_durable_commit_keeps_old_memory_and_restart_publishes_winner` | API, reorg integration | automated |
| SQLite lifecycle, outbox, receiver-dedup, and canonical-claim guards | `test_task_4_8_reliability_integration.py::test_sqlite_database_guards_reject_invalid_lifecycle_outbox_claim_and_receiver_dedup`; `test_task_4_2_native_transaction_records.py::test_task_4_2_lifecycle_transitions_are_explicit_and_durable` | storage integration | automated |

## Measured reliability signals

The Task 4.8 focused suite completed in 1.55 seconds on the local test harness. Its receiver-restart/lost-ACK path measures retry-to-acknowledgement with a local monotonic bound of two seconds; the deterministic simulated retry delay is two seconds. These are harness signals for Task 4.9 planning, not production throughput benchmarks.

## Boundaries

The suite intentionally does not run the 10,000-plus transaction burst benchmark. Pull-side summary pagination belongs to the existing peer-sync API contract; Task 4.8 verifies the durable sender-side bounded reconciliation batch and idempotent backfill without introducing an unbounded historical replay path.
