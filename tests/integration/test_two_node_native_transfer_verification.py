from tests.integration.two_node_native_transfer_harness import run_two_node_native_transfer_verification


def test_two_node_native_transfer_verification():
    summary = run_two_node_native_transfer_verification(verbose=False)

    assert summary["passed"] is True
    assert summary["network_name"] == "zoidberg-testnet"
    assert summary["mempool_status_node_a"] == "mempool"
    assert summary["mempool_status_node_b"] == "mempool"
    assert summary["final_sender_balance_node_a"] == "2"
    assert summary["final_sender_balance_node_b"] == "2"
    assert summary["final_recipient_balance_node_a"] == "3"
    assert summary["final_recipient_balance_node_b"] == "3"
    assert all(summary["negative_checks"].values())
