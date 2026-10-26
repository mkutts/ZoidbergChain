"""Explicit local test pins. A peer/cache never supplies or upgrades the root.

G2's complete hash preimage is missing. Pinning synthetic G/M/D together is an
out-of-band fixture capability, NOT verification that G commits M or D.
"""
from dataclasses import dataclass
import os
from pathlib import Path
import tempfile

from canonical_v3.primitives import closed, h64, pattern, require, uint, V3Error
from isolated_bft717j.wire import Context, J, parse
from .manifest import Manifest
from .outcomes import AuthorityFailure, Outcome, Verification

CACHE_LIMIT = 16384


@dataclass(frozen=True)
class TrustedTestAnchor:
    """Trusted LOCAL configuration, never decoded from a peer or cache.

    Full immutable fixture bytes are pinned independently of synthetic G.
    There is intentionally no constructor from an alleged genesis record,
    no genesis_verified Boolean, and no production-network loading path.
    """
    manifest_bytes: bytes
    agreement_bytes: bytes
    genesis_hash: str

    def __post_init__(self):
        m = Manifest(self.manifest_bytes)
        try:
            pattern(m.value['network_id'], r'task717[ijk]-test(?:-[a-z0-9-]+)?')
            Context(self.manifest_bytes, self.agreement_bytes, self.genesis_hash)
        except V3Error as exc:
            raise AuthorityFailure(Outcome.WRONG_CONTEXT, exc.code) from exc
        except MemoryError as exc:
            raise AuthorityFailure(Outcome.RESOURCE_FAILURE, 'anchor_memory') from exc


@dataclass(frozen=True)
class StaticTestAuthority:
    anchor: TrustedTestAnchor

    def __post_init__(self):
        if type(self.anchor) is not TrustedTestAnchor:
            raise AuthorityFailure(Outcome.WRONG_CONTEXT, 'explicit_local_test_anchor_required')

    @property
    def context(self):
        return Context(self.anchor.manifest_bytes, self.anchor.agreement_bytes,
                       self.anchor.genesis_hash)

    @property
    def genesis_authentication(self):
        return Verification(Outcome.INCOMPLETE_AUTHORITY,
            'G2_SERIALIZATION_AND_RELEASE_AUTHENTICATION_UNSPECIFIED; '
            'membership authorized only by independent local test fixture pins',
            fixture_membership_authenticated=True)

    def resolve_member(self, validator_id, public_key, epoch=0):
        try:
            require(uint(epoch) == 0, 'static_epoch')
            ctx = self.context
            require(ctx.members.get(validator_id) == public_key, 'unauthorized_key_or_identity')
            return ctx.namespace(public_key)
        except V3Error as exc:
            raise AuthorityFailure(Outcome.WRONG_CONTEXT, exc.code) from exc


def resolve_authority(anchor, manifest_bytes, agreement_bytes, *, network_id,
                      genesis_hash, validator_set_commitment, agreement_profile_digest):
    """Validate content, then compare EVERY binding to independent local pins."""
    if type(anchor) is not TrustedTestAnchor:
        raise AuthorityFailure(Outcome.WRONG_CONTEXT, 'explicit_local_test_anchor_required')
    m = Manifest(manifest_bytes)
    try:
        h64(validator_set_commitment)
        h64(agreement_profile_digest)
        require(m.commitment == validator_set_commitment, 'manifest_commitment_mismatch')
        candidate = Context(manifest_bytes, agreement_bytes, genesis_hash)
        pinned = StaticTestAuthority(anchor).context
        require(candidate.network == network_id == pinned.network and
                candidate.genesis_hash == pinned.genesis_hash and
                candidate.C == pinned.C and candidate.A == agreement_profile_digest == pinned.A and
                manifest_bytes == anchor.manifest_bytes and agreement_bytes == anchor.agreement_bytes,
                'independent_test_anchor_mismatch')
    except V3Error as exc:
        raise AuthorityFailure(Outcome.WRONG_CONTEXT, exc.code) from exc
    except MemoryError as exc:
        raise AuthorityFailure(Outcome.RESOURCE_FAILURE, 'authority_memory') from exc
    return StaticTestAuthority(anchor)


def _cache_record(authority):
    ctx = authority.context
    # Local disposable storage format only; never a genesis/hash/signing grammar.
    return dict(cache_version=1, kind='task717k-local-test-authority-cache',
        manifest=ctx.manifest, agreement=parse(ctx.agreement_bytes, 4096),
        network_id=ctx.network, genesis_hash=ctx.genesis_hash, validator_epoch=0,
        validator_set_commitment=ctx.C, agreement_profile_digest=ctx.A)


def save_cache(path, authority):
    """Atomic disposable cache replacement. Not authoritative consensus storage."""
    temporary = None
    try:
        raw = J(_cache_record(authority))
        require(len(raw) <= CACHE_LIMIT, 'cache_size')
        path = Path(path)
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=path.name+'.', delete=False) as f:
            temporary = f.name
            f.write(raw)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporary, path)
    except OSError as exc:
        raise AuthorityFailure(Outcome.STORAGE_FAILURE, 'cache_write') from exc
    except MemoryError as exc:
        raise AuthorityFailure(Outcome.RESOURCE_FAILURE, 'cache_memory') from exc
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass  # successful replace already consumed it
            except OSError as exc:
                raise AuthorityFailure(Outcome.STORAGE_FAILURE, 'cache_temporary_cleanup') from exc


def load_cache(path, anchor):
    """Reauthenticate against separately supplied pins on EVERY reopen; fail closed."""
    try:
        with open(path, 'rb') as f:
            raw = f.read(CACHE_LIMIT + 1)
        c = parse(raw, CACHE_LIMIT)
        closed(c, 'cache_version kind manifest agreement network_id genesis_hash validator_epoch '
               'validator_set_commitment agreement_profile_digest')
        require(uint(c['cache_version']) == 1 and uint(c['validator_epoch']) == 0 and
                c['kind'] == 'task717k-local-test-authority-cache', 'cache_profile')
        return resolve_authority(anchor, J(c['manifest']), J(c['agreement']),
            network_id=c['network_id'], genesis_hash=c['genesis_hash'],
            validator_set_commitment=c['validator_set_commitment'],
            agreement_profile_digest=c['agreement_profile_digest'])
    except MemoryError as exc:
        raise AuthorityFailure(Outcome.RESOURCE_FAILURE, 'cache_memory') from exc
    except AuthorityFailure as exc:
        if exc.outcome == Outcome.RESOURCE_FAILURE:
            raise
        raise AuthorityFailure(Outcome.STORAGE_FAILURE, 'cache_corrupt_or_wrong_anchor') from exc
    except (OSError, V3Error) as exc:
        raise AuthorityFailure(Outcome.STORAGE_FAILURE, 'cache_unreadable_or_corrupt') from exc
