"""One test-only constructor gate; signing remains entirely in unchanged 7.17J."""
from isolated_bft717j.signer import Signer
from isolated_bft717j.wire import identity
from .authority import StaticTestAuthority
from .outcomes import AuthorityFailure, Outcome


def open_test_signer(authority, path, custody_dir, key, test_catalogue, *, bootstrap=False):
    if type(authority) is not StaticTestAuthority:
        raise AuthorityFailure(Outcome.WRONG_CONTEXT, 'explicit_local_test_authority_required')
    authority.resolve_member(identity(key.public_key), key.public_key)
    # No context override, membership Boolean, key loader, transition adapter,
    # expiry API or replacement signing path. Original h1/r0 reducer is intact.
    return Signer(path, custody_dir, authority.context, key, test_catalogue, bootstrap=bootstrap)
