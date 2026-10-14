import test from 'node:test';
import assert from 'node:assert/strict';
import { assertPostMintDisputeChallenge, DISPUTE_DOMAIN, DISPUTE_POLICY_ID,
  DISPUTE_NETWORK_ID } from './postMintDispute.js';

test('finalized dispute challenge binds the exact block, media and reason', () => {
  const payload = {
    domain: DISPUTE_DOMAIN, network_id: DISPUTE_NETWORK_ID,
    policy_id: DISPUTE_POLICY_ID, policy_version: 1,
    policy_digest: 'a'.repeat(64), reviewer_policy_version: 1,
    reputation_rule_version: 1, wallet_address: `0x${'1'.repeat(40)}`,
    submission_id: 'submission', block_height: 8, block_hash: 'b'.repeat(64),
    media_hash: 'c'.repeat(64), reason: 'other_policy_concern', nonce: 'nonce',
    issued_at: '2099-10-10T00:00:00+00:00', expires_at: '2099-10-10T00:05:00+00:00',
  };
  const message = JSON.stringify(Object.fromEntries(Object.entries(payload).sort(([a], [b]) => a.localeCompare(b))));
  const challenge = { payload, message };
  const expected = { walletAddress: payload.wallet_address, submissionId: payload.submission_id,
    blockHeight: payload.block_height, blockHash: payload.block_hash,
    mediaHash: payload.media_hash, reason: payload.reason };
  assert.equal(assertPostMintDisputeChallenge(challenge, expected), message);
  assert.throws(() => assertPostMintDisputeChallenge(challenge, { ...expected, blockHash: 'd'.repeat(64) }));
  assert.throws(() => assertPostMintDisputeChallenge(challenge, { ...expected, reason: 'potentially_illegal_content' }));
  assert.throws(() => assertPostMintDisputeChallenge({ ...challenge, payload: { ...payload, domain: 'zoidbergchain/community-report/v1' } }, expected));
  assert.throws(() => assertPostMintDisputeChallenge(challenge, expected, Date.parse('2100-01-01T00:00:00Z')), /expired/i);
});
