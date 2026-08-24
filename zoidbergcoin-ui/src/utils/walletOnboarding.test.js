import test from 'node:test';
import assert from 'node:assert/strict';

import { getWalletOnboardingOptions } from './walletOnboarding.js';

test('wallet onboarding options separate live MetaMask access from future alternative login copy', () => {
  const options = getWalletOnboardingOptions();

  assert.equal(options[0].title, 'Continue with MetaMask');
  assert.equal(options[0].availability, 'available');
  assert.equal(options[1].title, 'Alternative login coming soon');
  assert.equal(options[1].availability, 'coming_soon');
  assert.match(options[1].warning, /MetaMask is currently required/i);
});
