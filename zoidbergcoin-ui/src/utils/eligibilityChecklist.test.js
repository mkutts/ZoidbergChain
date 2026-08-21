import test from 'node:test';
import assert from 'node:assert/strict';

import {
  getEligibilityRuleChecks,
  getFailedRequiredRuleChecks,
  getPassedAllowlistChecks,
} from './eligibilityChecklist.js';

test('blocked user checklist exposes failed required access rules', () => {
  const eligibility = {
    rule_checks: [
      {
        rule_id: 'wallet_verified',
        scope: 'access',
        required: true,
        passed: true,
        applicable: true,
      },
      {
        rule_id: 'access_allowlist_match',
        scope: 'access',
        required: false,
        passed: false,
        applicable: true,
      },
      {
        rule_id: 'access_approval_path',
        scope: 'access',
        required: true,
        passed: false,
        applicable: true,
      },
    ],
  };

  const failed = getFailedRequiredRuleChecks(eligibility, ['access']);
  assert.equal(failed.length, 1);
  assert.equal(failed[0].rule_id, 'access_approval_path');
});

test('failed allowlist rule stays visible without pretending access is blocked for another scope', () => {
  const eligibility = {
    rule_checks: [
      {
        rule_id: 'access_allowlist_match',
        scope: 'access',
        required: false,
        passed: true,
        applicable: true,
      },
      {
        rule_id: 'voting_config_review_allowlist',
        scope: 'voting',
        required: true,
        passed: false,
        applicable: true,
      },
    ],
  };

  const accessChecks = getEligibilityRuleChecks(eligibility, ['access']);
  const votingFailed = getFailedRequiredRuleChecks(eligibility, ['voting']);

  assert.equal(accessChecks[0].rule_id, 'access_allowlist_match');
  assert.equal(votingFailed[0].rule_id, 'voting_config_review_allowlist');
});

test('allowlisted wallets expose passed override state from backend rule checks', () => {
  const eligibility = {
    rule_checks: [
      {
        rule_id: 'access_allowlist_match',
        scope: 'access',
        required: false,
        passed: true,
        applicable: true,
      },
      {
        rule_id: 'voting_admin_allowlist_override',
        scope: 'voting',
        required: false,
        passed: true,
        applicable: true,
      },
    ],
  };

  const passed = getPassedAllowlistChecks(eligibility, ['access', 'voting']);
  assert.equal(passed.length, 2);
});
