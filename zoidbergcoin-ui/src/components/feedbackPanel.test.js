import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import url from 'node:url';

const __dirname = path.dirname(url.fileURLToPath(import.meta.url));

function read(relativePath) {
  return fs.readFileSync(path.resolve(__dirname, relativePath), 'utf8');
}

test('feedback panel keeps beta safety copy and user-facing prompts visible', () => {
  const source = read('./FeedbackPanel.vue');

  assert.match(source, /Found a bug or something confusing\? Send feedback\./i);
  assert.match(source, /Do not include private keys, seed phrases, passwords, invite codes/i);
  assert.match(source, /Include wallet, page, device, and safe eligibility details automatically/i);
});

test('blocked access gate exposes the in-app feedback entry point', () => {
  const source = read('./ControlledAccessGate.vue');

  assert.match(source, /<FeedbackPanel/i);
  assert.match(source, /Blocked or stuck\? Send feedback\./i);
  assert.match(source, /entry-point="access_gate"/i);
  assert.match(source, /href="#feedback-panel"/i);
});

test('admin page includes feedback review controls for status, priority, and notes', () => {
  const source = read('../pages/AdminPage.vue');

  assert.match(source, /Review beta user feedback/i);
  assert.match(source, /Update Status \+ Priority/i);
  assert.match(source, /Add Note/i);
  assert.match(source, /feedback-admin-grid/i);
});

test('dashboard and wallet surfaces expose a visible send feedback shortcut', () => {
  const dashboardSource = read('../pages/Dashboard.vue');
  const walletSource = read('./WalletPanel.vue');

  assert.match(dashboardSource, /Send Feedback/i);
  assert.match(dashboardSource, /href="#feedback-panel"/i);
  assert.match(walletSource, /Send Feedback/i);
  assert.match(walletSource, /href="#feedback-panel"/i);
});
