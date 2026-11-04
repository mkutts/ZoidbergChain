"""Offline application admission boundary. No routes, signing, or persistence.

An existing v1 certificate is verified as v1, never relabelled as v2 evidence.
Prepared objects are immutable, instance-bound capabilities, not caller assertions.
"""
from dataclasses import dataclass
from enum import Enum
from typing import Callable

from admission_certificate import validate_admission_certificate
from media_technical_validation import (
    MediaValidationUnavailable, TechnicalMediaValidationError, ValidatedMedia,
    technical_evidence_identity, validate_media_bytes,
)
from codec_prototype.isolated_decoder import IsolatedDecoder, Status
from . import block, media
from .primitives import Context, MAX_RECORD, V3Error, canonical, parse, require


class Failure(str, Enum):
    INVALID_ADMISSION = 'invalid_admission'
    INVALID_CANONICAL = 'invalid_canonical'
    INCOMPLETE = 'incomplete'
    LOCAL_FAILURE = 'local_failure'


class IntegrationError(Exception):
    def __init__(self, classification, code, *, outcome=None):
        self.classification = classification
        self.code = code
        self.outcome = outcome
        super().__init__(f'{classification.value}: {code}')


@dataclass(frozen=True)
class TestOnlyConfig:
    __test__ = False
    context: Context
    test_only: bool  # Required; no environment or production activation switch.

    def __post_init__(self):
        require(self.test_only is True and type(self.context) is Context, 'test_only_configuration_required')


@dataclass(frozen=True)
class AdmissionDependencies:
    # Trusted application dependencies, not uploaded/caller-supplied admission flags.
    reviewer_status_resolver: Callable
    original_claimed: Callable  # SHA256(original) -> bool, authoritative selected history/claims.


@dataclass(frozen=True)
class CapacityReservation:
    original_size: int
    identity_payload: int
    descriptor_bound: int
    complete_bound: int
    certificate_cap: int = 196608
    native_array_cap: int = 98304
    native_count: int = 10
    rest_cap: int = 32768


def reserve_identity(original_size, mime):
    require(type(mime) is str and mime in media.MIMES, 'mime_type')
    require(type(original_size) is int and 1 <= original_size <= (
        media.MAX_TEXT if mime == 'text/plain' else media.MAX_IMAGE), 'original_size')
    payload = 4 * ((original_size + 2) // 3)
    # Task 7.10C enumerates every closed field, including max escaped caption,
    # all evidence/signatures, ten max-size native records and portable wrapper.
    total = block.conservative_size_bound() - 4 * ((media.MAX_IMAGE + 2) // 3) + payload
    require(total <= MAX_RECORD, 'identity_reservation_exceeds_block')
    return CapacityReservation(original_size, payload, payload + 231, total)


@dataclass(frozen=True, eq=False)
class PreparedAdmission:
    original: bytes
    descriptor_bytes: bytes
    application_certificate_bytes: bytes
    capacity: CapacityReservation

    @property
    def descriptor(self):
        return parse(self.descriptor_bytes)

    @property
    def certificate(self):
        return parse(self.application_certificate_bytes)


class AdmissionAdapter:
    """Single-owner, disposable harness. Preparation never authorizes minting.

    Current application policy is deliberately retained (images <=256 KiB).
    v3's 2 MiB bound is reserved/tested, but does not relax current admission.
    """
    def __init__(self, config, dependencies, *, decoder):
        require(type(config) is TestOnlyConfig and config.test_only is True, 'test_only_configuration_required')
        require(type(dependencies) is AdmissionDependencies and
                callable(dependencies.reviewer_status_resolver) and callable(dependencies.original_claimed),
                'admission_dependencies_required')
        require(isinstance(decoder, IsolatedDecoder), 'isolated_decoder_required')
        self.config, self.dependencies, self.decoder = config, dependencies, decoder
        self._prepared = {}

    def _claimed(self, original_hash):
        try:
            claimed = self.dependencies.original_claimed(original_hash)
            if type(claimed) is not bool:
                raise TypeError('claim lookup must return bool')
            return claimed
        except Exception as exc:
            raise IntegrationError(Failure.LOCAL_FAILURE, 'original_claim_lookup_unavailable') from exc

    def verify_prepared(self, prepared):
        if type(prepared) is not PreparedAdmission or not any(
                value is prepared for value in self._prepared.values()):
            raise IntegrationError(Failure.INVALID_ADMISSION, 'unissued_admission')
        if self._claimed(prepared.descriptor['original_sha256']):
            raise IntegrationError(Failure.INVALID_ADMISSION, 'duplicate_original')

    def prepare(self, validated, certificate):
        """Revalidate actual bytes, frozen evidence, rights signature and both reviews.

        ValidatedMedia is not a security token: constructing one by hand grants
        nothing. Revalidation runs the existing technical worker and v1 verifier.
        """
        try:
            require(type(validated) is ValidatedMedia and type(validated.raw_media_bytes) is bytes,
                    'validated_media_required')
            if certificate is None:
                raise IntegrationError(Failure.INCOMPLETE, 'application_certificate_required')
            require(type(certificate) is dict, 'application_certificate_required')
            # Freeze before verification; no mutable evidence escapes this boundary.
            frozen = canonical(certificate)
            certificate = parse(frozen)
            original = validated.raw_media_bytes
            mime = validated.result['detected_mime_type']
            reservation = reserve_identity(len(original), mime)
            fresh = validate_media_bytes(original, declared_mime_type=mime)
            require(fresh.raw_media_bytes == original, 'accepted_bytes_not_canonical')
            technical = technical_evidence_identity(fresh.result)
            require(canonical(technical) == canonical(technical_evidence_identity(validated.result)) ==
                    canonical(certificate['technical_evidence']), 'technical_evidence_mismatch')
            # Keep resolver operational exceptions distinct even though the old
            # vote verifier catches ValueError/TypeError from a resolver.
            def resolve(*args):
                try:
                    status = self.dependencies.reviewer_status_resolver(*args)
                except Exception as exc:
                    raise IntegrationError(Failure.LOCAL_FAILURE, 'reviewer_lookup_unavailable') from exc
                if status is None:
                    raise IntegrationError(Failure.INCOMPLETE, 'historical_application_reviewer_state')
                return status
            validate_admission_certificate(certificate, media_bytes=original,
                                           reviewer_status_resolver=resolve)
            original_hash = technical['raw_media_sha256']
            if self._claimed(original_hash) or original_hash in self._prepared:
                raise IntegrationError(Failure.INVALID_ADMISSION, 'duplicate_original')
        except IntegrationError:
            raise
        except MediaValidationUnavailable as exc:
            raise IntegrationError(Failure.LOCAL_FAILURE, 'technical_worker_unavailable') from exc
        except TechnicalMediaValidationError as exc:
            classification = Failure.LOCAL_FAILURE if exc.result.get('local_resource_defense_failure') else Failure.INVALID_ADMISSION
            raise IntegrationError(classification, 'technical_media_rejected') from exc
        except (ValueError, TypeError, KeyError) as exc:
            raise IntegrationError(Failure.INVALID_ADMISSION, getattr(exc, 'code', 'invalid_application_admission')) from exc
        except Exception as exc:
            raise IntegrationError(Failure.LOCAL_FAILURE, 'admission_operation_unavailable') from exc
        try:
            produced = media.produce(original, mime, decoder=self.decoder)
        except V3Error as exc:
            raise IntegrationError(Failure.INVALID_CANONICAL, exc.code) from exc
        except Exception as exc:
            raise IntegrationError(Failure.LOCAL_FAILURE, 'codec_worker_unavailable') from exc
        if produced.outcome.status != Status.VALID:
            classification = Failure.LOCAL_FAILURE if produced.outcome.status == Status.INDETERMINATE_LOCAL_FAILURE else Failure.INVALID_CANONICAL
            raise IntegrationError(classification, produced.outcome.reason or produced.outcome.code,
                                   outcome=produced.outcome)
        descriptor_bytes = canonical(produced.descriptor)
        if len(descriptor_bytes) > reservation.descriptor_bound:
            raise IntegrationError(Failure.INVALID_CANONICAL, 'descriptor_reservation')
        prepared = PreparedAdmission(original, descriptor_bytes, frozen, reservation)
        self._prepared[original_hash] = prepared
        return prepared
