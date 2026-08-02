import test from 'node:test';
import assert from 'node:assert/strict';

import {
  buildReviewerEligibilityMessage,
  buildReviewPolicySummary,
  buildReviewPolicyWarning,
  normalizeReviewPolicyResponse,
} from './reviewPolicy.js';

test('public policy display renders label and mode', () => {
  const summary = buildReviewPolicySummary({
    public_label: 'Controlled testnet reviewer eligibility',
    eligibility_mode: 'allowlist',
  });
  assert.equal(summary, 'Controlled testnet reviewer eligibility (allowlist mode)');
});

test('controlled testnet warning appears for restricted modes', () => {
  const warning = buildReviewPolicyWarning({
    eligibility_mode: 'hybrid',
  });
  assert.match(warning, /Controlled testnet voting may require allowlist or activity eligibility/i);
});

test('ineligible wallet message includes reason and action', () => {
  const message = buildReviewerEligibilityMessage({
    eligibility: {
      eligible: false,
      reason: 'wallet_not_allowlisted',
      recommended_action: 'Use an approved testnet wallet or ask the operator for access.',
    },
  });
  assert.match(message, /not currently eligible to review/i);
  assert.match(message, /wallet not allowlisted/i);
  assert.match(message, /approved testnet wallet/i);
});

test('normalizeReviewPolicyResponse tolerates missing fields', () => {
  const normalized = normalizeReviewPolicyResponse({});
  assert.equal(normalized.eligibilityMode, 'open');
  assert.equal(normalized.publicLabel, 'Open local review voting');
  assert.equal(normalized.allowlistModeEnabled, false);
});
