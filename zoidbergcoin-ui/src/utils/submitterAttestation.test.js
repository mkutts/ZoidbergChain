import assert from 'node:assert/strict';
import test from 'node:test';

import {
  SUBMITTER_ATTESTATION_DOMAIN,
  SUBMITTER_ATTESTATION_STATEMENT,
  canonicalAttestationMessage,
  prepareSubmitterAttestationChallenge,
} from './submitterAttestation.js';

function challenge() {
  const canonical_payload = {
    wallet_address: '0x1111111111111111111111111111111111111111',
    technical_evidence_version: 1,
    technical_evidence_digest: 'e'.repeat(64),
    submission_id: 'a'.repeat(32),
    statement_version: 1,
    statement_id: 'zoidberg-public-testnet-v1/submitter-rights-permanence/1',
    statement: SUBMITTER_ATTESTATION_STATEMENT,
    raw_media_sha256: 'b'.repeat(64),
    policy_version: 1,
    policy_id: 'zoidberg-public-testnet-v1/media-admission/1',
    policy_digest: 'c'.repeat(64),
    nonce: 'fresh-nonce',
    network_id: 'zoidberg-public-testnet-v1',
    issued_at: '2026-09-18T20:00:00+00:00',
    expires_at: '2026-09-18T20:05:00+00:00',
    attestation_version: 1,
  };
  return {
    canonical_payload,
    message: canonicalAttestationMessage(canonical_payload),
    submission_id: canonical_payload.submission_id,
    network_id: canonical_payload.network_id,
    policy_digest: canonical_payload.policy_digest,
    technical_evidence_digest: canonical_payload.technical_evidence_digest,
  };
}

test('acknowledgment is required before a signature request', () => {
  assert.throws(
    () => prepareSubmitterAttestationChallenge(challenge()),
    /must acknowledge/i,
  );
});

test('canonical challenge payload is rebuilt before signing', () => {
  const prepared = prepareSubmitterAttestationChallenge(challenge(), { acknowledged: true });
  assert.equal(prepared.message, challenge().message);
  assert.match(prepared.message, new RegExp(SUBMITTER_ATTESTATION_DOMAIN));
});

test('altered canonical message and statement are rejected', () => {
  assert.throws(
    () => prepareSubmitterAttestationChallenge({ ...challenge(), message: `${challenge().message} ` }, { acknowledged: true }),
    /does not match/i,
  );
  const altered = challenge();
  altered.canonical_payload = { ...altered.canonical_payload, statement: 'Finalized media can be deleted.' };
  altered.message = canonicalAttestationMessage(altered.canonical_payload);
  assert.throws(
    () => prepareSubmitterAttestationChallenge(altered, { acknowledged: true }),
    /unsupported/i,
  );
});

test('wrong public-testnet policy, network, and binding summaries are rejected', () => {
  for (const [field, value] of [
    ['network_id', 'zoidberg-mainnet-v1'],
    ['policy_id', 'unknown-policy'],
    ['raw_media_sha256', 'not-a-hash'],
  ]) {
    const altered = challenge();
    altered.canonical_payload = { ...altered.canonical_payload, [field]: value };
    altered.message = canonicalAttestationMessage(altered.canonical_payload);
    assert.throws(
      () => prepareSubmitterAttestationChallenge(altered, { acknowledged: true }),
      /invalid|inconsistent/i,
    );
  }
  const inconsistent = challenge();
  inconsistent.policy_digest = 'f'.repeat(64);
  assert.throws(
    () => prepareSubmitterAttestationChallenge(inconsistent, { acknowledged: true }),
    /inconsistent/i,
  );
});

test('statement communicates permanence without claiming proof of ownership', () => {
  assert.match(SUBMITTER_ATTESTATION_STATEMENT, /permanently replicated/i);
  assert.match(SUBMITTER_ATTESTATION_STATEMENT, /cannot be removed/i);
  assert.match(SUBMITTER_ATTESTATION_STATEMENT, /not proof of ownership/i);
});
