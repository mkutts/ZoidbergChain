import test from 'node:test';
import assert from 'node:assert/strict';

import { createPrivyEmbeddedWalletService } from './privyEmbeddedWallet.js';

function createEnabledConfig() {
  return {
    provider: 'privy',
    isPrivySelected: true,
    isConfigured: true,
    privyAppId: 'app-id',
    privyClientId: 'client-id',
    socialProvider: 'google',
    portabilityHelpUrl: 'https://docs.privy.io/wallets/wallets/export',
    portabilityHelpCopy: 'Privy portability help.',
  };
}

test('Privy service does not import the SDK when embedded wallets are disabled', async () => {
  let loadCalls = 0;
  const service = createPrivyEmbeddedWalletService({
    config: { isConfigured: false },
    sdkLoader: async () => {
      loadCalls += 1;
      return {};
    },
  });

  assert.equal(await service.initialize(), false);
  assert.equal(service.getAvailability(), 'coming_soon');
  assert.equal(service.getUnavailableMessage(), 'Embedded wallet provider is disabled for this deployment.');
  assert.equal(service.getDiagnostics().unavailableReason, 'provider_disabled');
  assert.equal(loadCalls, 0);
});

test('Privy service does not import the SDK when required public ids are missing', async () => {
  let loadCalls = 0;
  const service = createPrivyEmbeddedWalletService({
    config: { provider: 'privy', isConfigured: false, isPrivySelected: true, privyAppId: '', privyClientId: '' },
    sdkLoader: async () => {
      loadCalls += 1;
      return {};
    },
  });

  assert.equal(await service.initialize(), false);
  assert.equal(service.getAvailability(), 'coming_soon');
  assert.equal(service.getDiagnostics().unavailableReason, 'missing_app_id');
  assert.equal(loadCalls, 0);
});

test('Privy service clearly defers the Vue path even when public Privy config is present', async () => {
  const service = createPrivyEmbeddedWalletService({
    config: createEnabledConfig(),
  });

  assert.equal(await service.initialize(), false);
  assert.equal(service.getAvailability(), 'coming_soon');
  assert.equal(service.getConnectionStatus(), 'coming_soon');
  assert.match(service.getUnavailableMessage(), /react island/i);
  assert.equal(service.getDiagnostics().sdkImportAttempted, false);
  assert.equal(service.getDiagnostics().sdkImportSucceeded, false);
  assert.equal(service.getDiagnostics().unavailableReason, 'react_sdk_required');
  assert.equal(service.getDiagnostics().lastErrorMessage, '');

  await assert.rejects(
    () => service.sendEmailCode('tester@example.com'),
    /react island/i,
  );
});
