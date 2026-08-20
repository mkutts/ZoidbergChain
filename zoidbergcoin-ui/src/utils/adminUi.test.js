import test from 'node:test';
import assert from 'node:assert/strict';

import { adminSafetyLines, shouldShowAdminDashboard } from './adminUi.js';

test('unauthenticated admin state does not show the dashboard', () => {
  assert.equal(shouldShowAdminDashboard({ authenticated: false }), false);
  assert.equal(shouldShowAdminDashboard(null), false);
});

test('authenticated admin state shows the dashboard', () => {
  assert.equal(shouldShowAdminDashboard({ authenticated: true }), true);
});

test('admin safety copy keeps public testnet warnings visible', () => {
  const lines = adminSafetyLines();

  assert.ok(lines.includes('Invite codes are shown once. Copy before leaving this screen.'));
  assert.ok(lines.includes('This gate reduces spam but is not proof-of-personhood.'));
  assert.ok(lines.includes('Test ZOID has no real monetary value.'));
  assert.ok(lines.includes('Do not approve users you do not recognize.'));
});
