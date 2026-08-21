import test from 'node:test';
import assert from 'node:assert/strict';

import {
  FEEDBACK_TYPE_OPTIONS,
  buildSafeEligibilitySnapshot,
  createDefaultFeedbackForm,
  summarizeFeedbackContext,
  validateFeedbackForm,
} from './feedback.js';

test('feedback defaults start with a bug report and context enabled', () => {
  const form = createDefaultFeedbackForm();

  assert.equal(form.type, 'bug');
  assert.equal(form.includeContext, true);
});

test('feedback validation requires type, title, and description', () => {
  const errors = validateFeedbackForm({
    type: '',
    title: '',
    description: '',
  });

  assert.ok(errors.type);
  assert.ok(errors.title);
  assert.ok(errors.description);
});

test('safe eligibility snapshot keeps user-facing rule outcomes without secrets', () => {
  const snapshot = buildSafeEligibilitySnapshot({
    access_granted: false,
    can_access_app: false,
    wallet_bound: false,
    can_submit: false,
    can_vote: true,
    can_receive_rewards: false,
    blocked_reasons: [
      { scope: 'access', reason: 'wallet_not_bound', rule_id: 'wallet_binding_active' },
    ],
    submission: {
      can_submit: false,
      eligibility_source: 'blocked',
      blocked_reason: 'wallet_not_bound',
      session_token: 'should-not-pass-through',
    },
  });

  assert.equal(snapshot.can_submit, false);
  assert.equal(snapshot.blocked_reasons[0].reason, 'wallet_not_bound');
  assert.equal(snapshot.submission.blocked_reason, 'wallet_not_bound');
  assert.equal('session_token' in snapshot.submission, false);
});

test('feedback context summary stays human-readable', () => {
  const summary = summarizeFeedbackContext({
    currentPage: '/dashboard',
    currentFlow: 'dashboard',
    walletAddress: '0x1111111111111111111111111111111111111111',
    accessAccountId: 'acct-1',
    isMobile: true,
    eligibilityIncluded: true,
  });

  assert.ok(summary.includes('Page: /dashboard'));
  assert.ok(summary.includes('Flow: dashboard'));
  assert.ok(summary.includes('Mobile device details included'));
  assert.ok(summary.includes('Eligibility snapshot included'));
});

test('feedback type options cover wallet, mobile, and suggestion flows', () => {
  const values = FEEDBACK_TYPE_OPTIONS.map((item) => item.value);

  assert.ok(values.includes('wallet_connection_issue'));
  assert.ok(values.includes('mobile_issue'));
  assert.ok(values.includes('general_suggestion'));
});
