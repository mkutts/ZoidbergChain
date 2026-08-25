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
  assert.match(source, /class="access-hero-grid"/i);
  assert.match(source, /class="access-intro-panel"/i);
  assert.match(source, /class="active-flow-shell"/i);
  assert.match(source, /class="journey-grid access-paths responsive-access-grid"/i);
  assert.match(source, /class="journey-grid onboarding-grid compact-options responsive-wallet-grid"/i);
  assert.match(source, /class="helper-links-inline"/i);
  assert.match(source, /class="panel-stack flow-panel"/i);
  assert.match(source, /class="panel-stack flow-panel request-panel"/i);
  assert.match(source, /I&apos;m New/i);
  assert.match(source, /Returning With My Approved Wallet/i);
  assert.match(source, /Beta Guide/i);
  assert.match(source, /Controlled Beta/i);
  assert.match(source, /Request beta access/i);
  assert.match(source, /Choose a wallet method/i);
  assert.match(source, /Continue with MetaMask/i);
  assert.match(source, /Email \/ Social Wallet/i);
  assert.match(source, /Email \/ Social Wallet is coming soon\./i);
  assert.match(source, /Wallet verified\. Bind this wallet to your approved beta access\./i);
  assert.match(source, /Change Wallet Method/i);
  assert.match(source, /Why am I blocked\?/i);
  assert.match(source, /Request Beta Help/i);
  assert.match(source, /Open Beta Help Form|Hide Beta Help Form/i);
  assert.match(source, /Email \/ Social Wallet Coming Soon/i);
  assert.match(source, /Email \/ Social Wallet diagnostics \(development only\)/i);
  assert.match(source, /embeddedWalletDiagnosticReasonLabel/i);
  assert.match(source, /providerConfigured:/i);
  assert.match(source, /sdkImportAttempted:/i);
  assert.match(source, /More details are available in the Beta Guide\./i);
  assert.match(source, /Test ZOID has no real monetary value\./i);
  assert.match(source, /MetaMask Mobile browser/i);
  assert.match(source, /Never share seed phrases or private keys\./i);
  assert.match(source, /Blocked or stuck\? Send feedback\./i);
  assert.match(source, /entry-point="access_gate"/i);
  assert.match(source, /requestFeedbackPanelOpen/i);
  assert.match(source, /scrollIntoView:\s*true/i);
  assert.match(source, /width:\s*min\(1160px,\s*100%\)/i);
  assert.match(source, /grid-template-columns:\s*minmax\(0,\s*1\.45fr\)\s*minmax\(320px,\s*0\.95fr\)/i);
  assert.match(source, /responsive-access-grid[\s\S]*repeat\(2,\s*minmax\(0,\s*1fr\)\)/i);
  assert.match(source, /responsive-wallet-grid[\s\S]*repeat\(auto-fit,\s*minmax\(220px,\s*1fr\)\)/i);
  assert.match(source, /active-flow-shell[\s\S]*margin-top:\s*16px/i);
  assert.match(source, /access-paths[\s\S]*margin-bottom:\s*10px/i);
  assert.match(source, /entry-switch[\s\S]*margin-top:\s*10px/i);
  assert.match(source, /feedback-shortcut[\s\S]*display:\s*inline-flex[\s\S]*justify-content:\s*center[\s\S]*min-height:\s*52px/i);
  assert.match(source, /onboarding-grid[\s\S]*margin:\s*4px 0 0/i);
  assert.match(source, /mini-help[\s\S]*padding:\s*0/i);
  assert.match(source, /mini-help[\s\S]*overflow:\s*hidden/i);
  assert.match(source, /mini-help summary[\s\S]*display:\s*flex[\s\S]*width:\s*100%[\s\S]*min-height:\s*40px[\s\S]*padding:\s*10px 14px/i);
  assert.match(source, /mini-help summary:focus-visible/i);
  assert.doesNotMatch(source, /<section v-if="shouldShowEligibilityStatus" class="rules-panel blocked-panel">/i);
  assert.doesNotMatch(source, /<section v-if="canRequestOverride" class="rules-panel">/i);
  assert.match(source, /@media \(max-width:\s*720px\)[\s\S]*responsive-access-grid[\s\S]*grid-template-columns:\s*minmax\(0,\s*1fr\)/i);
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
  assert.match(guideSource, /Why Access Is Controlled/i);
  assert.match(guideSource, /What Can Block Access/i);
  assert.match(guideSource, /How Originality Review Works/i);
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
  assert.match(bannerSource, /width:\s*min\(1160px,\s*100%\)/i);
});
