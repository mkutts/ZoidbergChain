"""Keep protocol rejection, missing authority/data and local failures distinct."""
from dataclasses import dataclass
from enum import Enum


class Outcome(str, Enum):
    INVALID_MANIFEST = 'INVALID_MEMBERSHIP_MANIFEST'
    WRONG_CONTEXT = 'WRONG_TRUSTED_GENESIS_OR_NETWORK'
    INVALID_PROOF = 'INVALID_CRYPTOGRAPHIC_PROOF'
    INSUFFICIENT_QUORUM = 'INSUFFICIENT_QUORUM'
    INCOMPLETE_AUTHORITY = 'INCOMPLETE_AUTHORITY'
    INCOMPLETE_DATA = 'INCOMPLETE_PROPOSAL_OR_ANCESTRY_DATA'
    STORAGE_FAILURE = 'LOCAL_STORAGE_FAILURE'
    RESOURCE_FAILURE = 'LOCAL_VERIFICATION_RESOURCE_FAILURE'
    VALID_MESSAGE = 'VALID_AUTHENTICATED_TEST_MESSAGE'
    VALID_QUORUM = 'VALID_AUTHENTICATED_TEST_QUORUM_PROOF'
    EQUIVOCATION = 'AUTHENTICATED_TEST_EQUIVOCATION'
    RETRANSMISSION = 'AUTHENTICATED_TEST_RETRANSMISSION'
    CONFLICT = 'CONFLICTING_AUTHENTICATED_TEST_QUORUMS'
    COMPATIBLE = 'COMPATIBLE_AUTHENTICATED_TEST_QUORUMS'


class AuthorityFailure(ValueError):
    def __init__(self, outcome, detail):
        self.outcome, self.detail = outcome, detail
        super().__init__(f'{outcome.value}: {detail}')


@dataclass(frozen=True)
class Verification:
    outcome: Outcome
    detail: str
    fixture_membership_authenticated: bool = False
    signatures_valid: bool = False
    quorum_structure_valid: bool = False
    genesis_authenticated: bool = False
    block_parent_identity_authenticated: bool = False
    full_finalized_ancestry_verified: bool = False
    complete_consensus_execution_verified: bool = False
    # Work actually attempted, including failures. These are not vote weights.
    signature_checks: int = 0
    distinct_signers: int = 0
    proof_id: str | None = None

    def __bool__(self):
        raise TypeError('inspect outcome and individual guarantees explicitly')
