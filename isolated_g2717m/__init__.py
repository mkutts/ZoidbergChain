"""Inactive Task 7.17M reference verifier. Never import into production admission."""
from .verifier import Outcome, Result, TrustedGenesisPin, verify_bytes, verify_file

__all__ = ['Outcome', 'Result', 'TrustedGenesisPin', 'verify_bytes', 'verify_file']
