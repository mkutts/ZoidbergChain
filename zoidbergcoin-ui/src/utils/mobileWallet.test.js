import test from 'node:test';
import assert from 'node:assert/strict';

import {
  buildMetaMaskDeepLink,
  buildReturningWalletGuidance,
  describeWalletSupport,
  isMobileDevice,
} from './mobileWallet.js';

test('mobile device detection recognizes common phone user agents', () => {
  assert.equal(isMobileDevice('Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)'), true);
  assert.equal(isMobileDevice('Mozilla/5.0 (Linux; Android 14; Pixel 8)'), true);
  assert.equal(isMobileDevice('Mozilla/5.0 (Windows NT 10.0; Win64; x64)'), false);
});

test('deep link targets the current page without the protocol prefix', () => {
  assert.equal(
    buildMetaMaskDeepLink('https://zoidbergcoin.com/dashboard?view=wallet#transfers'),
    'https://metamask.app.link/dapp/zoidbergcoin.com/dashboard?view=wallet#transfers',
  );
});

test('mobile browsers without an injected provider show guidance and deeplink support', () => {
  const support = describeWalletSupport({
    userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)',
    ethereum: null,
    currentUrl: 'https://zoidbergcoin.com/',
  });

  assert.match(support.helperText, /MetaMask Mobile browser/i);
  assert.match(support.noProviderMessage, /MetaMask was not detected/i);
  assert.equal(support.shouldShowOpenInMetaMask, true);
  assert.equal(support.openInMetaMaskUrl, 'https://metamask.app.link/dapp/zoidbergcoin.com/');
});

test('MetaMask mobile browser keeps injected-provider flow without showing the deeplink button', () => {
  const support = describeWalletSupport({
    userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) MetaMaskMobile',
    ethereum: { isMetaMask: true },
    currentUrl: 'https://zoidbergcoin.com/access',
  });

  assert.equal(support.isMetaMaskMobileBrowser, true);
  assert.equal(support.shouldShowOpenInMetaMask, false);
  assert.equal(support.noProviderMessage, '');
});

test('returning approved wallets keep a reconnect-first call to action', () => {
  const guidance = buildReturningWalletGuidance({
    walletBound: true,
    isConnected: false,
  });

  assert.match(guidance.headline, /Returning user/i);
  assert.match(guidance.detail, /without reusing the invite code/i);
  assert.equal(guidance.actionLabel, 'Connect Approved Wallet');
});
