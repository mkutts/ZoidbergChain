import assert from 'node:assert/strict';
import test from 'node:test';
import { buildActivationDisplay, buildIntegrityDisplay, buildMediaLifecycleDisplay, certificateScopeLabel } from './mediaLifecycle.js';

test('canonical lifecycle stages remain distinct and conservative', () => {
  assert.equal(buildMediaLifecycleDisplay({ stage: 'technical_rejected' }).label, 'Technical Rejection');
  assert.equal(buildMediaLifecycleDisplay({ stage: 'awaiting_attestation' }).label, 'Attestation Required');
  assert.equal(buildMediaLifecycleDisplay({ stage: 'review_rejected_originality' }).label, 'Not Original');
  assert.equal(buildMediaLifecycleDisplay({ stage: 'review_rejected_admissibility' }).label, 'Not Admissible');
  assert.equal(buildMediaLifecycleDisplay({ stage: 'quarantined' }).detail.includes('not been deleted'), true);
  assert.equal(buildMediaLifecycleDisplay({}).label, 'Loading lifecycle…');
});

test('admission, mint, finality, dispute, and legacy stages have distinct labels', () => {
  const expected = new Map([
    ['admission_qualified', 'Admission Qualified'],
    ['mintable', 'Mintable'],
    ['minted', 'Minted'],
    ['finalized', 'Finalized'],
    ['post_mint_disputed', 'Finalized · Disputed'],
    ['legacy_pre_activation', 'Legacy · Pre-Activation'],
  ]);
  for (const [stage, label] of expected) {
    assert.equal(buildMediaLifecycleDisplay({ stage }).label, label);
  }
});

test('integrity copy is limited to exact byte commitments', () => {
  const verified = buildIntegrityDisplay({ status: 'verified' });
  assert.match(verified.detail, /exactly match/i);
  assert.match(verified.detail, /does not mean lawful, safe, original, admissible, or undisputed/i);
  assert.equal(buildIntegrityDisplay({ status: 'failed' }).label, 'Media Integrity Failed');
  assert.equal(buildIntegrityDisplay({ status: 'unavailable' }).label, 'Media Integrity Unavailable');
});

test('activation and legacy certificate labels never imply current enforcement', () => {
  assert.match(buildActivationDisplay({ state: 'misconfigured' }).label, /misconfigured/i);
  assert.equal(certificateScopeLabel('legacy_originality_only'), 'Legacy originality-only');
  assert.equal(certificateScopeLabel('current_dual_admission'), 'Current admission-certified');
});

