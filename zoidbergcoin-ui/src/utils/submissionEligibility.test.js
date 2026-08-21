import test from 'node:test';
import assert from 'node:assert/strict';

import { buildSubmissionEligibilityView } from './submissionEligibility.js';

test('normal approved submission state does not imply an override', () => {
  const view = buildSubmissionEligibilityView({
    submission: {
      can_submit: true,
      eligibility_source: 'normal_access_verified_wallet',
      message: 'Submission is allowed because this wallet has controlled beta access and the wallet session is verified.',
      policy_rule: 'Submissions currently require controlled beta access for submissions plus a verified wallet session.',
    },
  });

  assert.equal(view.tone, 'success');
  assert.match(view.headline, /can submit with this verified wallet/i);
  assert.match(view.detail, /controlled beta access/i);
  assert.doesNotMatch(`${view.headline} ${view.detail}`, /override/i);
});

test('blocked submission state shows a clear reason and next step', () => {
  const view = buildSubmissionEligibilityView({
    submission: {
      can_submit: false,
      eligibility_status: 'blocked',
      blocked_reason: 'wallet_not_bound',
      message: 'Submission is blocked because this wallet is not approved for the controlled beta yet.',
      recommended_action: 'Ask an admin to approve this wallet for controlled beta access before submitting.',
      policy_rule: 'Submissions currently require controlled beta access for submissions plus a verified wallet session.',
    },
  });

  assert.equal(view.tone, 'error');
  assert.match(view.headline, /not approved for the controlled beta/i);
  assert.match(view.detail, /approve this wallet/i);
});

test('submission override state renders clearly when present', () => {
  const view = buildSubmissionEligibilityView({
    submission: {
      can_submit: true,
      eligibility_source: 'admin_submission_override',
      policy_rule: 'Submissions currently require controlled beta access for submissions plus a verified wallet session.',
    },
  });

  assert.equal(view.tone, 'success');
  assert.match(view.headline, /admin approval is active/i);
  assert.match(view.detail, /direct beta approval/i);
});
