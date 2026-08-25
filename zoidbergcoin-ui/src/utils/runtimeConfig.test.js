import test from 'node:test';
import assert from 'node:assert/strict';

import {
  getEmbeddedWalletConfig,
  getAppEnvironment,
  isPublicDemoMode,
  publicDemoBannerLines,
  showDevelopmentTools,
} from './runtimeConfig.js';

test('development fallback keeps public demo mode off and dev tools on', () => {
  const env = { MODE: 'development', PROD: false };
  assert.equal(getAppEnvironment(env), 'development');
  assert.equal(isPublicDemoMode(env), false);
  assert.equal(showDevelopmentTools(env), true);
});

test('testnet environment returns public demo mode true', () => {
  const env = { MODE: 'production', PROD: true, VITE_ENVIRONMENT: 'testnet' };
  assert.equal(getAppEnvironment(env), 'testnet');
  assert.equal(isPublicDemoMode(env), true);
  assert.equal(showDevelopmentTools(env), false);
});

test('production fallback returns public demo mode true', () => {
  const env = { MODE: 'production', PROD: true };
  assert.equal(getAppEnvironment(env), 'production');
  assert.equal(isPublicDemoMode(env), true);
  assert.equal(showDevelopmentTools(env), false);
});

test('explicit public demo flag true forces public demo mode on', () => {
  const env = { MODE: 'development', PROD: false, VITE_PUBLIC_DEMO_MODE: 'true' };
  assert.equal(isPublicDemoMode(env), true);
  assert.equal(showDevelopmentTools(env), false);
});

test('explicit public demo flag false forces public demo mode off', () => {
  const env = { MODE: 'production', PROD: true, VITE_PUBLIC_DEMO_MODE: 'false' };
  assert.equal(isPublicDemoMode(env), false);
});

test('development tools explicit flag is ignored when public demo mode is true', () => {
  const env = {
    MODE: 'development',
    PROD: false,
    VITE_PUBLIC_DEMO_MODE: 'true',
    VITE_ENABLE_DEV_TOOLS: 'true',
  };
  assert.equal(showDevelopmentTools(env), false);
});

test('explicit development tools false disables them', () => {
  const env = {
    MODE: 'development',
    PROD: false,
    VITE_ENABLE_DEV_TOOLS: 'false',
  };
  assert.equal(showDevelopmentTools(env), false);
});

test('public demo banner includes required controlled-testnet labels', () => {
  const lines = publicDemoBannerLines();
  assert.equal(lines[0], 'ZoidbergChain controlled testnet');
  assert.ok(lines.includes('Test ZOID has no real monetary value'));
  assert.ok(lines.includes('This network may reset'));
  assert.ok(lines.includes('Not mainnet'));
  assert.ok(lines.includes('Wallets are used for identity and signatures'));
  assert.ok(lines.includes('Native ZOID lives on ZoidbergChain, not Ethereum'));
  assert.ok(lines.includes('Never enter a seed phrase or private key in this app'));
});

test('embedded wallet config stays disabled by default', () => {
  const config = getEmbeddedWalletConfig({ MODE: 'development', PROD: false });

  assert.equal(config.enabled, false);
  assert.equal(config.configured, false);
});

test('embedded wallet config enables Privy when app id is present', () => {
  const config = getEmbeddedWalletConfig({
    MODE: 'development',
    PROD: false,
    VITE_EMBEDDED_WALLET_PROVIDER: 'privy',
    VITE_PRIVY_APP_ID: 'privy-app-id',
  });

  assert.equal(config.enabled, true);
  assert.equal(config.configured, true);
  assert.equal(config.privy.appId, 'privy-app-id');
});
