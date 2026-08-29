from __future__ import annotations

from block import Block
from transaction import Transaction


def fund_native_wallet_with_block(
    blockchain,
    wallet_address: str,
    amount: str | float = "25",
    *,
    persist: bool = False,
    text_prefix: str = "Test funding block",
):
    """Add a post-genesis reward-pool funding block without mutating canonical genesis."""
    latest_block = blockchain.get_latest_block()
    latest_timestamp = float(getattr(latest_block, "timestamp", 0) or 0)
    funding_timestamp = max(latest_timestamp + 1.0, float(latest_block.index + 1))
    normalized_wallet = str(wallet_address or "").strip().lower()
    funding_block = Block(
        index=latest_block.index + 1,
        previous_hash=latest_block.hash,
        timestamp=funding_timestamp,
        transactions=[
            Transaction(
                sender="REWARD_POOL",
                recipient=normalized_wallet,
                amount=float(amount),
                tip=0,
                created_at=funding_timestamp,
            )
        ],
        miner=normalized_wallet or "REWARD_POOL",
        meme={
            "encoded_image": "test-funding-block",
            "text": f"{text_prefix} {latest_block.index + 1}",
        },
    )
    funding_block.hash = funding_block.calculate_hash()
    blockchain.chain.append(funding_block)
    blockchain.recompute_reward_pool_balance(chain=blockchain.chain)
    if persist:
        blockchain.save_blockchain()
    return funding_block
