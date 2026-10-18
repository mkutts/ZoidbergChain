import assert from 'node:assert/strict';
import test from 'node:test';
import { assertCommunityReviewChallenge, COMMUNITY_REVIEW_DOMAIN, COMMUNITY_REVIEW_NETWORK_ID } from './communityReview.js';

function challenge(overrides = {}) {
  const payload = {
    domain: COMMUNITY_REVIEW_DOMAIN,
    network_id: COMMUNITY_REVIEW_NETWORK_ID,
    vote_version: 2,
    policy_version: 1,
    policy_digest: 'a'.repeat(64),
    reviewer_policy_version: 1,
    reputation_rule_version: 1,
    wallet_address: `0x${'1'.repeat(40)}`,
    submission_id: 'submission',
    content_hash: 'b'.repeat(64),
    dimension: 'originality',
    choice: 'unsure',
    nonce: 'nonce',
    issued_at: '2099-10-14T00:00:00+00:00',
    expires_at: '2099-10-14T00:05:00+00:00',
    ...overrides,
  };
  return {
    ...payload,
    vote: payload.choice,
    message: JSON.stringify(Object.fromEntries(Object.entries(payload).sort(([a], [b]) => a.localeCompare(b)))),
  };
}

test('review challenge validates domain, policy, wallet, media, dimension and choice before signing', () => {
  const value = challenge();
  const expected = { walletAddress: value.wallet_address, submissionId: value.submission_id,
    contentHash: value.content_hash, dimension: value.dimension, choice: value.vote };
  assert.equal(assertCommunityReviewChallenge(value, expected), value.message);
  assert.throws(() => assertCommunityReviewChallenge(value, { ...expected, dimension: 'admissibility' }), /does not match/i);
  const wrongDomain = challenge({ domain: 'zoidbergchain/community-report/v1' });
  assert.throws(() => assertCommunityReviewChallenge(wrongDomain, expected), /policy/i);
  const wrongHash = challenge({ content_hash: 'c'.repeat(64) });
  assert.throws(() => assertCommunityReviewChallenge(wrongHash, expected), /does not match/i);
});

test('expired review challenge is rejected before wallet signing', () => {
  const value = challenge({ expires_at: '2020-01-01T00:00:00+00:00' });
  const expected = { walletAddress: value.wallet_address, submissionId: value.submission_id,
    contentHash: value.content_hash, dimension: value.dimension, choice: value.vote };
  assert.throws(() => assertCommunityReviewChallenge(value, expected), /expired/i);
});

