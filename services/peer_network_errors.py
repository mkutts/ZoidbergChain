"""Shared peer-networking errors without framework or facade dependencies."""


class PeerSyncError(ValueError):
    pass


class MissingSignedPeerHeadersError(PeerSyncError):
    pass


class InvalidPeerTimestampError(PeerSyncError):
    pass


class ExpiredPeerSignatureError(PeerSyncError):
    pass


class InvalidPeerSignatureError(PeerSyncError):
    pass


class ReplayedPeerNonceError(PeerSyncError):
    pass


class ContentSyncError(PeerSyncError):
    pass


class MalformedTransactionError(PeerSyncError):
    pass


class ConflictingTransactionError(PeerSyncError):
    pass


class UnauthorizedPeerError(PeerSyncError):
    pass


class WrongNetworkError(PeerSyncError):
    pass


class MalformedSubmissionError(PeerSyncError):
    pass


class DuplicateSubmissionError(PeerSyncError):
    pass


class MalformedVoteError(PeerSyncError):
    pass


class MalformedCertificateError(PeerSyncError):
    pass


class ConflictingCertificateError(PeerSyncError):
    pass


class UnknownSubmissionError(PeerSyncError):
    pass


class ConflictingVoteError(PeerSyncError):
    pass


class MalformedBlockError(PeerSyncError):
    def __init__(self, message, *, code=None, details=None):
        super().__init__(message)
        self.code = code
        self.details = dict(details or {})

    def to_detail(self):
        if self.code or self.details:
            payload = {"code": self.code or "invalid_block", "message": str(self)}
            payload.update(self.details)
            return payload
        return str(self)


class DuplicateBlockError(PeerSyncError):
    pass


class ChainExtensionError(PeerSyncError):
    pass


class ChainSyncError(PeerSyncError):
    pass
