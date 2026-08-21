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
  assert.match(source, /I&apos;m New/i);
  assert.match(source, /Returning With My Approved Wallet/i);
  assert.match(source, /Beta Guide/i);
  assert.match(source, /Approved testers receive a one-time invite code before binding their wallet\./i);
  assert.match(source, /Test ZOID stays testnet-only and has no real monetary value\./i);
  assert.match(source, /MetaMask Mobile browser/i);
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
  assert.match(dashboardSource, /Beta Guide/i);
  assert.match(walletSource, /requestFeedbackPanelOpen/i);
  assert.match(walletSource, /@click="openFeedbackPanel"/i);
  assert.match(walletSource, /Send Feedback/i);
});

test('beta guide page keeps onboarding, safety, and mobile guidance visible', () => {
  const guideSource = read('../pages/WhyZoidbergCoin.vue');
  const homeSource = read('../pages/HomePage.vue');
  const routerSource = read('../router/index.js');

  assert.match(guideSource, /Beta Tester Guide/i);
  assert.match(guideSource, /How to use the ZoidbergChain beta/i);
  assert.match(guideSource, /Connect And Reconnect/i);
  assert.match(guideSource, /If Something Breaks/i);
  assert.match(guideSource, /Use the in-app Send Feedback button/i);
  assert.match(guideSource, /MetaMask Mobile/i);
  assert.match(guideSource, /Test ZOID has no real monetary value/i);
  assert.match(homeSource, /Open Beta Guide/i);
  assert.match(routerSource, /path:\s*'\/why-zoidbergcoin'[\s\S]*meta:\s*\{\s*skipAccessGate:\s*true\s*\}/i);
});

test('dashboard keeps user-facing workflow copy and hides dev-only review controls by default', () => {
  const dashboardSource = read('../pages/Dashboard.vue');

  assert.match(dashboardSource, /Create, vote, and track test ZOID/i);
  assert.match(dashboardSource, /Prepare Your Content/i);
  assert.match(dashboardSource, /Vote On Originality/i);
  assert.match(dashboardSource, /Need the walkthrough again\? Open the Beta Guide/i);
  assert.match(dashboardSource, /v-if="showMintQueueTools"/i);
  assert.match(dashboardSource, /v-if="showMintQueueTools" @click="evaluateSubmission/i);
});

test('public beta banner keeps tester-facing warnings visible', () => {
  const bannerSource = read('./PublicDemoBanner.vue');

  assert.match(bannerSource, /Controlled Beta/i);
  assert.match(bannerSource, /Test ZOID has no real monetary value/i);
  assert.match(bannerSource, /Wallets are used for identity and signatures/i);
  assert.match(bannerSource, /Never enter a seed phrase or private key/i);
});
