"""Offline v2 evidence assembly. No keys, routes, persistence or activation.

Fresh signatures are inputs, never generated or converted from legacy records.
Trusted dependencies must pin the complete frozen selection and historical
eligibility (including quota/penalties) to the configured test chain context.
"""
from dataclasses import dataclass
from typing import Callable

from . import evidence
from .admission import AdmissionAdapter, Failure, IntegrationError
from .primitives import Context, V3Error, canonical, digest, envelope, parse, rational, require

MISSING = object()


@dataclass(frozen=True)
class ReviewerDecision:
    status: str
    eligible: bool


@dataclass(frozen=True)
class IssuanceDependencies:
    # (Context, submission_id, original_hash) -> canonical full selected vote array
    # bytes, or None when the authoritative frozen snapshot is unavailable.
    frozen_votes: Callable
    # (Context, closed_vote) -> ReviewerDecision or None for missing history.
    # Must establish ancestry, status, penalties and accepted quota participation;
    # both dimensions of one submission consume one participation, as today.
    reviewer_decision: Callable


@dataclass(frozen=True)
class IncompleteEvidence:
    missing: tuple[str, ...]
    classification: Failure = Failure.INCOMPLETE
    certificate_bytes: None = None


@dataclass(frozen=True)
class VerifiedCertificate:
    """Immutable verification result, not mint/finality/selection authority."""
    context: Context
    certificate_bytes: bytes

    @property
    def certificate(self):
        return parse(self.certificate_bytes, limit=196608)

    @property
    def originality_ratio(self):
        tally = self.certificate['originality']
        return rational(tally['positive_votes'], tally['approval_denominator'])


class EvidenceIssuer:
    def __init__(self, adapter, dependencies):
        require(type(adapter) is AdmissionAdapter and adapter.config.test_only is True,
                'test_only_admission_adapter_required')
        require(type(dependencies) is IssuanceDependencies and
                callable(dependencies.frozen_votes) and callable(dependencies.reviewer_decision),
                'issuance_dependencies_required')
        self.adapter, self.dependencies = adapter, dependencies

    @property
    def context(self):
        return self.adapter.config.context

    def technical_for(self, prepared):
        """Derive the v2 technical preimage BEFORE collecting new signatures.

        Source observations/bytes already passed the unchanged admission adapter.
        Only policy context and its digest change; no v1 signature is reused.
        """
        self.adapter.verify_prepared(prepared)
        technical = prepared.certificate['technical_evidence']
        technical.update(evidence.policy_fields(self.context))
        technical.pop('evidence_digest')
        technical['evidence_digest'] = digest(technical)
        evidence.validate_technical(technical, self.context)
        return technical

    def _lookup(self, name, *args):
        try:
            return getattr(self.dependencies, name)(self.context, *args)
        except Exception as exc:
            raise IntegrationError(Failure.LOCAL_FAILURE, name + '_unavailable') from exc

    def _history(self, certificate):
        votes = certificate['votes']
        snapshot = self._lookup('frozen_votes', certificate['submission_id'], certificate['content_hash'])
        if snapshot is None:
            raise IntegrationError(Failure.INCOMPLETE, 'frozen_vote_snapshot')
        try:
            selected = parse(snapshot, limit=196608)
            evidence.validate_votes(selected, self.context)
        except (ValueError, TypeError, KeyError) as exc:
            raise IntegrationError(Failure.LOCAL_FAILURE, 'invalid_frozen_snapshot_contract') from exc
        require(canonical(votes) == snapshot, 'frozen_vote_set_mismatch')
        for vote in votes:
            self._reviewer(vote)

    def _reviewer(self, vote):
        # Pass a detached object: callbacks cannot mutate verified inputs.
        decision = self._lookup('reviewer_decision', parse(canonical(vote)))
        if decision is None:
            raise IntegrationError(Failure.INCOMPLETE, 'historical_reviewer_eligibility')
        if (type(decision) is not ReviewerDecision or type(decision.eligible) is not bool
                or type(decision.status) is not str):
            raise IntegrationError(Failure.LOCAL_FAILURE, 'invalid_reviewer_decision_contract')
        require(decision.eligible and decision.status == vote['reviewer_status'],
                'reviewer_ineligible_or_snapshot_mismatch')

    def _bindings(self, prepared, certificate):
        app = prepared.certificate
        evidence.fields_equal(certificate, {key: app[key] for key in
                              ('submission_id', 'content_hash', 'creator_wallet')})
        evidence.fixed(certificate['technical_evidence'], self.technical_for(prepared))

    def _result(self, operation):
        try:
            return operation()
        except IntegrationError as exc:
            if exc.classification == Failure.INCOMPLETE:
                return IncompleteEvidence((exc.code,))
            raise
        except (V3Error, ValueError, TypeError, KeyError) as exc:
            raise IntegrationError(Failure.INVALID_CANONICAL,
                                   getattr(exc, 'code', 'invalid_v2_evidence')) from exc
        except Exception as exc:
            raise IntegrationError(Failure.LOCAL_FAILURE, 'evidence_operation_unavailable') from exc

    def attestation_from_signature(self, prepared, *, payload, signature):
        """Produce the closed attestation from a supplied fresh signed payload."""
        def operation():
            technical = self.technical_for(prepared)
            payload_copy = parse(canonical(payload), limit=8192)
            message = evidence.attestation_bytes(payload_copy, self.context)
            app = prepared.certificate
            evidence.fields_equal(payload_copy, dict(submission_id=app['submission_id'],
                wallet_address=app['creator_wallet'], raw_media_sha256=app['content_hash'],
                technical_evidence_digest=technical['evidence_digest']))
            identity = digest(envelope(payload_copy, 'submitter-attestation', self.context))
            record = dict(attestation_version=1, statement_id=evidence.STATEMENT_ID, statement_version=1,
                domain='zoidbergchain/submitter-attestation/v2', protocol_version=2,
                network_id=self.context.network_id, signature_scheme='personal_sign',
                signer_wallet=payload_copy['wallet_address'], signature=signature, nonce=payload_copy['nonce'],
                canonical_payload=payload_copy, canonical_payload_digest=identity,
                canonical_message=message.decode('utf-8'), canonical_message_hash=identity)
            evidence.validate_attestation(record, self.context)
            return record
        return self._result(operation)

    def vote_from_signature(self, prepared, *, message, signature, reviewer_status,
                            reference_height, reference_hash):
        """Produce a closed vote from exact signed V bytes and checked history.

        The reference/status are not secretly added to the signing payload.
        Their authority is independently resolved before returning the record.
        """
        def operation():
            self.adapter.verify_prepared(prepared)
            payload = parse(message, limit=2048)
            record = dict(submission_id=payload['submission_id'], content_hash=payload['content_hash'],
                voter=payload['wallet_address'], voter_wallet_address=payload['wallet_address'],
                vote_type=payload['choice'], dimension=payload['dimension'], vote_version=3,
                protocol_version=2, network_id=self.context.network_id, signature_scheme='personal_sign',
                vote_signature=signature, vote_message=message.decode('utf-8'), vote_nonce=payload['nonce'],
                signed_message_hash=digest(payload), vote_issued_at=payload['issued_at'],
                vote_expires_at=payload['expires_at'], vote_identity=digest(dict(payload=payload, signature=signature)),
                reviewer_policy_version=1, reputation_rule_version=2, reviewer_status=reviewer_status,
                reviewer_eligible=True, reviewer_status_effective_height=reference_height,
                reviewer_status_reference_block_hash=reference_hash)
            evidence.validate_vote(record, self.context)
            app = prepared.certificate
            evidence.fields_equal(record, dict(submission_id=app['submission_id'], content_hash=app['content_hash']))
            require(record['voter_wallet_address'] != app['creator_wallet'], 'self_vote')
            self._reviewer(record)
            return record
        return self._result(operation)

    def issue(self, prepared, *, attestation=MISSING, votes=MISSING):
        """Assemble all supplied fresh signed inputs; never select a favorable subset."""
        def operation():
            self.adapter.verify_prepared(prepared)
            app = prepared.certificate
            technical = self.technical_for(prepared)
            # Validate present inputs before reporting absence of another input.
            if attestation is not MISSING:
                evidence.validate_attestation(attestation, self.context)
                evidence.fields_equal(attestation['canonical_payload'], dict(
                    submission_id=app['submission_id'], wallet_address=app['creator_wallet'],
                    raw_media_sha256=app['content_hash'], technical_evidence_digest=technical['evidence_digest']))
            if votes is not MISSING:
                require(type(votes) is list and len(votes) <= 32, 'vote_count')
                ordered = parse(canonical(votes), limit=196608)
                for vote in ordered:
                    evidence.validate_vote(vote, self.context)
                    evidence.fields_equal(vote, dict(submission_id=app['submission_id'], content_hash=app['content_hash']))
                    require(vote['voter_wallet_address'] != app['creator_wallet'], 'self_vote')
                ordered.sort(key=lambda v: (v['dimension'], v['voter_wallet_address'], v['vote_identity']))
                evidence.validate_votes(ordered, self.context)
            missing = tuple(name for name, value in (('v2_attestation', attestation),
                            ('v2_votes', votes)) if value is MISSING)
            if missing:
                return IncompleteEvidence(missing)
            body = dict(certificate_version=2, network_id=self.context.network_id,
                submission_id=app['submission_id'], content_hash=app['content_hash'],
                creator_wallet=app['creator_wallet'], **evidence.policy_fields(self.context),
                technical_evidence_version=1, technical_evidence=technical,
                attestation_version=1, attestation=parse(canonical(attestation)),
                review_policy_version=2, review_policy_digest=self.context.review_policy_digest,
                votes=ordered)
            self._history(body)
            unresolved = []
            for dimension in evidence.POSITIVE:
                tally = evidence.derive_tally(ordered, dimension, self.context)
                body[dimension] = tally
                if not tally['resolved']:
                    unresolved.append(dimension + '_review')
                else:
                    require(tally['outcome'] == evidence.POSITIVE[dimension], 'review_rejected')
            if unresolved:
                return IncompleteEvidence(tuple(unresolved))
            body['certificate_digest'] = digest(body)
            evidence.validate_certificate(body, self.context)
            return VerifiedCertificate(self.context, canonical(body))
        return self._result(operation)

    def verify(self, prepared, raw):
        """Verify canonical certificate bytes, original bindings and trusted history.

        A present complete certificate claiming insufficient review is invalid;
        missing trusted history is incomplete. Operational failures never downgrade.
        """
        def operation():
            self.adapter.verify_prepared(prepared)
            certificate = parse(raw, limit=196608)
            evidence.validate_certificate(certificate, self.context)
            self._bindings(prepared, certificate)
            self._history(certificate)
            return VerifiedCertificate(self.context, raw)
        return self._result(operation)
