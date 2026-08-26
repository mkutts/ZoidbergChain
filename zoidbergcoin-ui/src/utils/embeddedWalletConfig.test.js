import test from 'node:test';
import assert from 'node:assert/strict';

import { resolveEmbeddedWalletConfig } from './embeddedWalletConfig.js';

test('embedded wallet config records Privy selection for the React island path', () => {
  const config = resolveEmbeddedWalletConfig({
    VITE_EMBEDDED_WALLET_PROVIDER: 'privy',
    VITE_PRIVY_APP_ID: 'app-id-1',
    VITE_PRIVY_SOCIAL_PROVIDER: 'google',
  });

  assert.equal(config.isConfigured, true);
  assert.equal(config.isPrivySelected, true);
  assert.equal(config.isSupportedInVueApp, true);
  assert.equal(config.integrationStatus, 'react_island');
  assert.equal(config.supportsSocialLogin, true);
  assert.equal(config.socialProvider, 'google');
  assert.match(config.portabilityHelpCopy, /portable beta wallet/i);
});

test('embedded wallet config stays disabled without a public app id', () => {
  const config = resolveEmbeddedWalletConfig({
    VITE_EMBEDDED_WALLET_PROVIDER: 'privy',
    VITE_PRIVY_APP_ID: '',
    VITE_PRIVY_CLIENT_ID: '',
  });

  assert.equal(config.isConfigured, false);
  assert.equal(config.authOptionLabel, 'Email / Social Wallet');
});
