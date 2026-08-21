import test from 'node:test';
import assert from 'node:assert/strict';

import {
  adminSafetyLines,
  buildAdminOpsMetricCards,
  buildAdminOpsWarnings,
  buildBoundWalletRows,
  opsHealthTone,
  shouldShowAdminDashboard,
  shouldShowAdminOpsPanel,
  shouldUseStackedAdminCards,
} from './adminUi.js';

test('unauthenticated admin state does not show the dashboard', () => {
  assert.equal(shouldShowAdminDashboard({ authenticated: false }), false);
  assert.equal(shouldShowAdminDashboard(null), false);
});

test('authenticated admin state shows the dashboard', () => {
  assert.equal(shouldShowAdminDashboard({ authenticated: true }), true);
});

test('admin ops panel only shows for authenticated operators', () => {
  assert.equal(shouldShowAdminOpsPanel({ authenticated: true }), true);
  assert.equal(shouldShowAdminOpsPanel({ authenticated: false }), false);
});

test('admin mobile layout switches to stacked cards on phone-width screens', () => {
  assert.equal(shouldUseStackedAdminCards(390), true);
  assert.equal(shouldUseStackedAdminCards(1024), false);
});

test('bound wallet helper preserves copyable full addresses and short labels', () => {
  const rows = buildBoundWalletRows([
    '0xabcdefabcdefabcdefabcdefabcdefabcdef1234',
  ]);

  assert.equal(rows[0].walletAddress, '0xabcdefabcdefabcdefabcdefabcdefabcdef1234');
  assert.match(rows[0].shortLabel, /^0xabcdefab\.\.\.cdef1234$/i);
});

test('admin safety copy keeps public testnet warnings visible', () => {
  const lines = adminSafetyLines();

  assert.ok(lines.includes('Invite codes are shown once. Copy before leaving this screen.'));
  assert.ok(lines.includes('This gate reduces spam but is not proof-of-personhood.'));
  assert.ok(lines.includes('Test ZOID has no real monetary value.'));
  assert.ok(lines.includes('Do not approve users you do not recognize.'));
});

test('ops metric cards summarize the most useful admin dashboard counts', () => {
  const cards = buildAdminOpsMetricCards({
    environment: 'testnet',
    storage_backend: 'sqlite',
    metrics: {
      chain_height: 42,
      pending_access_requests: 3,
      pending_review_submissions: 2,
      mempool_size: 4,
      peer_count: 1,
    },
    latest_block: {
      index: 42,
      hash: 'abc1234567890fedcba',
    },
  });

  assert.equal(cards[0].label, 'Environment');
  assert.equal(cards[0].value, 'testnet');
  assert.equal(cards[2].value, 42);
  assert.equal(cards[3].value, 3);
  assert.match(cards[7].value, /^#42 abc123456789/i);
});

test('ops health tone reports warning and error states clearly', () => {
  assert.equal(opsHealthTone(null), 'neutral');
  assert.equal(opsHealthTone({
    health: { status: 'ok' },
    runtime_storage: { healthy: true },
    integrity_status: { healthy: true },
    sqlite_integrity: { healthy: true },
    environment_validation: { error_count: 0, warning_count: 1 },
    backup_status: { backup_count: 2 },
  }), 'warning');
  assert.equal(opsHealthTone({
    health: { status: 'ok' },
    runtime_storage: { healthy: false },
    integrity_status: { healthy: true },
    sqlite_integrity: { healthy: true },
    environment_validation: { error_count: 0, warning_count: 0 },
    backup_status: { backup_count: 2 },
  }), 'error');
});

test('ops warnings include failed checks and missing backup coverage', () => {
  const warnings = buildAdminOpsWarnings({
    environment_validation: {
      checks: [
        { ok: false, message: 'ACCESS_DEV_BYPASS_ENABLED must be false outside development.' },
        { ok: true, message: 'ignored healthy check' },
      ],
    },
    backup_status: { backup_count: 0 },
    integrity_status: { healthy: false },
    sqlite_integrity: { healthy: true },
  });

  assert.ok(warnings.includes('ACCESS_DEV_BYPASS_ENABLED must be false outside development.'));
  assert.ok(warnings.includes('No backup snapshot has been detected yet.'));
  assert.ok(warnings.includes('Storage integrity is reporting a problem.'));
});
