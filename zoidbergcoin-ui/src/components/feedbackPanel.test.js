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
  assert.match(source, /requestFeedbackPanelOpen/i);
  assert.match(source, /scrollIntoView:\s*true/i);
});

test('admin page includes feedback review controls for status, priority, and notes', () => {
  const source = read('../pages/AdminPage.vue');

  assert.match(source, /Review beta user feedback/i);
  assert.match(source, /Update Status \+ Priority/i);
  assert.match(source, /Mark Resolved/i);
  assert.match(source, /Dismiss/i);
  assert.match(source, /Active \/ Needs Review/i);
  assert.match(source, /Add Note/i);
  assert.match(source, /feedback-admin-grid/i);
});

test('unlocked app shell and wallet surface expose visible feedback entry points', () => {
  const appSource = read('../App.vue');
  const dashboardSource = read('../pages/Dashboard.vue');
  const walletSource = read('./WalletPanel.vue');

  assert.match(appSource, /<FeedbackPanel/i);
  assert.match(appSource, /showGlobalFeedback/i);
  assert.match(dashboardSource, /requestFeedbackPanelOpen/i);
  assert.match(dashboardSource, /@click="openFeedbackPanel"/i);
  assert.match(dashboardSource, /Send Feedback/i);
  assert.match(walletSource, /requestFeedbackPanelOpen/i);
  assert.match(walletSource, /@click="openFeedbackPanel"/i);
  assert.match(walletSource, /Send Feedback/i);
});
