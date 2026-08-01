import test from 'node:test';
import assert from 'node:assert/strict';

import {
  getAppEnvironment,
  isPublicDemoMode,
  publicDemoBannerLines,
  showDevelopmentTools,
} from './runtimeConfig.js';

test('runtime config defaults to development tools in local development', () => {
  assert.equal(getAppEnvironment(), 'development');
  assert.equal(isPublicDemoMode(), false);
  assert.equal(showDevelopmentTools(), true);
});

test('public demo banner includes required controlled-testnet labels', () => {
  const lines = publicDemoBannerLines();
  assert.equal(lines[0], 'ZoidbergChain controlled testnet');
  assert.ok(lines.includes('Test ZOID has no real monetary value'));
  assert.ok(lines.includes('This network may reset'));
  assert.ok(lines.includes('Not mainnet'));
  assert.ok(lines.includes('Native ZOID lives on ZoidbergChain, not Ethereum'));
  assert.ok(lines.includes('MetaMask signs ZoidbergChain actions'));
});
