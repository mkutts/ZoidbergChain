export const SUBMITTER_ATTESTATION_VERSION = 1;
export const SUBMITTER_ATTESTATION_STATEMENT_VERSION = 1;
export const SUBMITTER_ATTESTATION_STATEMENT_ID = 'zoidberg-public-testnet-v1/submitter-rights-permanence/1';
export const SUBMITTER_ATTESTATION_DOMAIN = 'zoidbergchain/submitter-attestation/v1';
export const SUBMITTER_ATTESTATION_NETWORK_ID = 'zoidberg-public-testnet-v1';
export const SUBMITTER_ATTESTATION_POLICY_ID = 'zoidberg-public-testnet-v1/media-admission/1';
export const SUBMITTER_ATTESTATION_POLICY_VERSION = 1;
export const SUBMITTER_ATTESTATION_STATEMENT = 'I assert that I have the right or authorization to submit this exact content under the identified ZoidbergChain Public Testnet media-admission policy. I understand that, if accepted and finalized, the accepted media bytes become permanently replicated in immutable ZoidbergChain history and cannot be removed through ordinary moderation. This testnet attestation is my signed assertion; it is not proof of ownership, a legal determination, a waiver, or a license beyond this explicit assertion.';

function canonicalValue(value) {
  if (Array.isArray(value)) {
    return value.map(canonicalValue);
  }
  if (value && typeof value === 'object') {
    return Object.keys(value)
      .sort()
      .reduce((result, key) => {
        result[key] = canonicalValue(value[key]);
        return result;
      }, {});
  }
  return value;
}

export function canonicalAttestationMessage(payload) {
  return JSON.stringify(canonicalValue({
    domain: SUBMITTER_ATTESTATION_DOMAIN,
    network_id: payload.network_id,
    object_type: 'submitter-attestation',
    payload,
    protocol: 'zoidbergchain',
    protocol_version: 1,
  }));
}

export function prepareSubmitterAttestationChallenge(challenge, { acknowledged = false } = {}) {
  if (!acknowledged) {
    throw new Error('You must acknowledge the submitter attestation before signing.');
  }
  const payload = challenge?.canonical_payload;
  if (!payload || typeof payload !== 'object') {
    throw new Error('The server returned a malformed submitter attestation.');
  }
  if (
    payload.attestation_version !== SUBMITTER_ATTESTATION_VERSION
    || payload.statement_id !== SUBMITTER_ATTESTATION_STATEMENT_ID
    || payload.statement_version !== SUBMITTER_ATTESTATION_STATEMENT_VERSION
    || payload.statement !== SUBMITTER_ATTESTATION_STATEMENT
  ) {
    throw new Error('The server returned an unsupported submitter attestation statement.');
  }
  if (
    payload.network_id !== SUBMITTER_ATTESTATION_NETWORK_ID
    || payload.policy_id !== SUBMITTER_ATTESTATION_POLICY_ID
    || payload.policy_version !== SUBMITTER_ATTESTATION_POLICY_VERSION
    || !/^[0-9a-f]{32}$/.test(payload.submission_id || '')
    || !/^[0-9a-f]{64}$/.test(payload.raw_media_sha256 || '')
    || !/^[0-9a-f]{64}$/.test(payload.policy_digest || '')
    || !/^[0-9a-f]{64}$/.test(payload.technical_evidence_digest || '')
    || !/^0x[0-9a-f]{40}$/.test(payload.wallet_address || '')
    || !payload.nonce
  ) {
    throw new Error('The server returned invalid submitter attestation bindings.');
  }
  if (
    (challenge.submission_id && challenge.submission_id !== payload.submission_id)
    || (challenge.network_id && challenge.network_id !== payload.network_id)
    || (challenge.policy_digest && challenge.policy_digest !== payload.policy_digest)
    || (
      challenge.technical_evidence_digest
      && challenge.technical_evidence_digest !== payload.technical_evidence_digest
    )
  ) {
    throw new Error('The server returned inconsistent submitter attestation bindings.');
  }
  const message = canonicalAttestationMessage(payload);
  if (challenge.message !== message) {
    throw new Error('The server attestation message does not match its canonical payload.');
  }
  return { message, payload };
}
