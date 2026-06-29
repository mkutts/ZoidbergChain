import pytest

from config import ACTIVE_USER_PERCENT_FOR_MIN_VOTES, MIN_VOTE_FLOOR


@pytest.mark.parametrize(
    ("active_users", "expected_threshold"),
    [
        (0, 5),
        (10, 5),
        (50, 5),
        (100, 5),
        (500, 25),
        (1000, 50),
    ],
)
def test_minimum_voting_threshold_formula(blockchain, active_users, expected_threshold):
    assert blockchain.calculate_minimum_votes_required(active_users) == expected_threshold


def test_voting_threshold_response_uses_active_users(blockchain, wallets):
    now = 1_000_000
    blockchain.record_vote(voter=wallets["owner"].public_key, created_at=now)
    blockchain.record_vote(voter=wallets["contributor_one"].public_key, created_at=now)

    assert blockchain.get_voting_threshold(now=now) == {
        "active_users": 2,
        "minimum_votes": MIN_VOTE_FLOOR,
        "vote_floor": MIN_VOTE_FLOOR,
        "active_percentage": ACTIVE_USER_PERCENT_FOR_MIN_VOTES,
    }
