import assert from 'node:assert/strict';
import test from 'node:test';
import { assertCommunityReportChallenge, REPORT_DOMAIN, REPORT_NETWORK_ID, REPORT_POLICY_ID } from './communityReport.js';

const payload = {
  domain: REPORT_DOMAIN, network_id: REPORT_NETWORK_ID,
  policy_id: REPORT_POLICY_ID, policy_version: 1,
  policy_digest: 'a'.repeat(64), wallet_address: `0x${'b'.repeat(40)}`,
  submission_id: 'submission', content_hash: 'c'.repeat(64), reason: 'other_policy_concern',
  nonce: 'nonce', issued_at: '2099-10-10T00:00:00+00:00', expires_at: '2099-10-10T00:05:00+00:00',
};
const message = JSON.stringify(Object.fromEntries(Object.keys(payload).sort().map((key) => [key, payload[key]])));
const expected = {
  walletAddress: payload.wallet_address, submissionId: payload.submission_id,
  contentHash: payload.content_hash, reason: payload.reason,
};

test('report challenge binds the selected action and canonical message', () => {
  assert.equal(assertCommunityReportChallenge({ payload, message }, expected), message);
  assert.throws(() => assertCommunityReportChallenge({ payload, message }, { ...expected, reason: 'potentially_illegal_content' }));
  assert.throws(() => assertCommunityReportChallenge({ payload: { ...payload, domain: 'zoidbergchain/community-review/v2' }, message }, expected));
  assert.throws(() => assertCommunityReportChallenge({ payload: { ...payload, network_id: 'another-network' }, message }, expected));
  assert.throws(() => assertCommunityReportChallenge({ payload, message: `${message} ` }, expected));
  assert.throws(() => assertCommunityReportChallenge({ payload, message }, expected, Date.parse('2100-01-01T00:00:00Z')), /expired/i);
});
