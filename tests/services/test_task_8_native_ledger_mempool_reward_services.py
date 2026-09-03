"""Direct Task 8 service characterization without a Blockchain dependency."""

from decimal import Decimal

from services import NativeLedgerService, NativeLedgerState, RewardService


def test_native_ledger_state_view_rebinds_to_current_authoritative_collections():
    service = NativeLedgerService()
    first = NativeLedgerState([], [{"tx_id": "first", "from_address": "0x0000000000000000000000000000000000000001", "to_address": "0x0000000000000000000000000000000000000002"}], [])
    second = NativeLedgerState([], [{"tx_id": "second", "from_address": "0x0000000000000000000000000000000000000001", "to_address": "0x0000000000000000000000000000000000000003"}], [])

    assert [item["tx_id"] for item in service.get_transfer_intents_for_wallet(first, "0x0000000000000000000000000000000000000001")] == ["first"]
    assert [item["tx_id"] for item in service.get_transfer_intents_for_wallet(second, "0x0000000000000000000000000000000000000001")] == ["second"]


def test_native_block_transaction_hash_uses_canonical_key_order():
    service = NativeLedgerService()
    transactions = [{"tx_id": "b", "amount": "1"}, {"amount": "2", "tx_id": "a"}]

    assert service.compute_block_native_transactions_hash(transactions) == service.compute_block_native_transactions_hash([
        {"amount": "1", "tx_id": "b"}, {"tx_id": "a", "amount": "2"}
    ])


def test_reward_unit_conversion_is_exact_and_stable():
    service = RewardService()

    assert service.reward_units_from_decimal(Decimal("0.000001")) == 1
    assert service.normalize_reward_amount(1) == "0.000001"
