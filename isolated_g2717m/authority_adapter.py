"""Narrow TEST-ONLY bridge. K's incomplete genesis verdict is never upgraded."""
from dataclasses import dataclass

from isolated_bft717k.authority import TrustedTestAnchor, resolve_authority
from isolated_bft717k.outcomes import AuthorityFailure, Outcome as KOutcome
from isolated_bft717j.wire import sha
from .verifier import Outcome, Result, verify_bytes


@dataclass(frozen=True)
class AuthorityBinding:
    verification: Result
    test_authority: object | None = None

    def __bool__(self):
        raise TypeError('inspect verification and test_authority explicitly')


def bind_test_authority(raw, *, trusted_pin):
    """Always reverify full bytes/pin. Accepts no peer M, result or cache override."""
    result = verify_bytes(raw, trusted_pin=trusted_pin)
    if result.outcome != Outcome.INCOMPLETE_POLICY:
        return AuthorityBinding(result)
    try:
        anchor = TrustedTestAnchor(result.manifest_bytes, result.agreement_bytes, result.genesis_hash)
        authority = resolve_authority(anchor, result.manifest_bytes, result.agreement_bytes,
            network_id=trusted_pin.network_id, genesis_hash=trusted_pin.genesis_hash,
            validator_set_commitment=sha(result.manifest_bytes), agreement_profile_digest=sha(result.agreement_bytes))
    except AuthorityFailure as exc:
        return AuthorityBinding(Result(Outcome.RESOURCE_FAILURE if exc.outcome == KOutcome.RESOURCE_FAILURE
            else Outcome.WRONG_AUTHORITY, exc.detail))
    except (MemoryError, OSError) as exc:
        return AuthorityBinding(Result(Outcome.RESOURCE_FAILURE, type(exc).__name__))
    return AuthorityBinding(result, authority)
