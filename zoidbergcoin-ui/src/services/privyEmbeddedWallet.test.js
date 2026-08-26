import test from 'node:test';
import assert from 'node:assert/strict';

import { createPrivyEmbeddedWalletService } from './privyEmbeddedWallet.js';

function createEnabledConfig() {
  return {
    provider: 'privy',
    isPrivySelected: true,
    isConfigured: true,
    privyAppId: 'app-id',
    privyClientId: '',
    socialProvider: 'google',
    portabilityHelpUrl: 'https://docs.privy.io/wallets/wallets/export',
    portabilityHelpCopy: 'Use this if you are new to wallets. This creates or connects a portable beta wallet.',
  };
}

function createBridgeMock(overrides = {}) {
  let state = {
    ready: true,
    authenticated: false,
    walletAddress: '',
    loginMetadata: null,
  };

  return {
    async probeAvailability() {
      return true;
    },
    async connect() {
      state = {
        ready: true,
        authenticated: true,
        walletAddress: '0x9999999999999999999999999999999999999999',
        loginMetadata: {
          userId: 'privy-user-1',
          linkedAccountTypes: ['email'],
        },
      };
      return {
        provider_id: 'privy',
        wallet_address: state.walletAddress,
        login_metadata: state.loginMetadata,
      };
    },
    async disconnect() {
      state = {
        ready: true,
        authenticated: false,
        walletAddress: '',
        loginMetadata: null,
      };
      return true;
    },
    getState() {
      return { ...state };
    },
    async requestSignature(message) {
      return `signed:${message}`;
    },
    ...overrides,
  };
}

test('Privy service stays disabled when embedded wallets are not selected', async () => {
  const service = createPrivyEmbeddedWalletService({
    config: { isConfigured: false },
  });

  assert.equal(await service.initialize(), false);
  assert.equal(service.getAvailability(), 'coming_soon');
  assert.equal(service.getUnavailableMessage(), 'Email / Social Wallet coming soon');
  assert.equal(service.getDiagnostics().unavailableReason, 'provider_disabled');
});

test('Privy service stays coming soon when required public ids are missing', async () => {
  const service = createPrivyEmbeddedWalletService({
    config: { provider: 'privy', isConfigured: false, isPrivySelected: true, privyAppId: '', privyClientId: '' },
  });

  assert.equal(await service.initialize(), false);
  assert.equal(service.getAvailability(), 'coming_soon');
  assert.equal(service.getDiagnostics().unavailableReason, 'missing_app_id');
});

test('Privy service reports available when the React island path is configured', async () => {
  const service = createPrivyEmbeddedWalletService({
    config: createEnabledConfig(),
  });

  assert.equal(await service.initialize(), true);
  assert.equal(service.getAvailability(), 'available');
  assert.equal(service.getConnectionStatus(), 'idle');
  assert.equal(service.getUnavailableMessage(), '');
  assert.equal(service.getDiagnostics().sdkImportAttempted, false);
  assert.equal(service.getDiagnostics().sdkImportSucceeded, false);
});

test('Privy service can connect and sign through the React island bridge', async () => {
  const calls = [];
  const service = createPrivyEmbeddedWalletService({
    config: createEnabledConfig(),
    createBridge() {
      return createBridgeMock({
        async probeAvailability() {
          calls.push('probeAvailability');
          return true;
        },
        async connect() {
          calls.push('connect');
          return {
            provider_id: 'privy',
            wallet_address: '0x9999999999999999999999999999999999999999',
            login_metadata: {
              userId: 'privy-user-1',
              linkedAccountTypes: ['email'],
            },
          };
        },
        getState() {
          return {
            ready: true,
            authenticated: true,
            walletAddress: '0x9999999999999999999999999999999999999999',
            loginMetadata: {
              userId: 'privy-user-1',
              linkedAccountTypes: ['email'],
            },
          };
        },
        async requestSignature(message) {
          calls.push(['sign', message]);
          return '0xprivy-signature';
        },
      });
    },
  });

  const accounts = await service.connect();
  const signature = await service.requestSignature('Exact challenge message');

  assert.deepEqual(accounts, ['0x9999999999999999999999999999999999999999']);
  assert.equal(signature, '0xprivy-signature');
  assert.equal(service.getAvailability(), 'available');
  assert.equal(service.getConnectionStatus(), 'connected');
  assert.equal(service.getDiagnostics().sdkImportAttempted, true);
  assert.equal(service.getDiagnostics().sdkImportSucceeded, true);
  assert.deepEqual(calls, [
    'probeAvailability',
    'connect',
    ['sign', 'Exact challenge message'],
  ]);
});

test('Privy service forwards the wallet address when signing a challenge', async () => {
  const calls = [];
  const service = createPrivyEmbeddedWalletService({
    config: createEnabledConfig(),
    createBridge() {
      return createBridgeMock({
        async requestSignature(message, walletAddress) {
          calls.push({ message, walletAddress });
          return `signed:${message}:${walletAddress}`;
        },
      });
    },
  });

  const signature = await service.requestSignature('Exact challenge message', '0xabcdefabcdefabcdefabcdefabcdefabcdef1234');

  assert.equal(signature, 'signed:Exact challenge message:0xabcdefabcdefabcdefabcdefabcdefabcdef1234');
  assert.deepEqual(calls, [{
    message: 'Exact challenge message',
    walletAddress: '0xabcdefabcdefabcdefabcdefabcdefabcdef1234',
  }]);
});

test('Privy service degrades cleanly when the React island import fails', async () => {
  const service = createPrivyEmbeddedWalletService({
    config: createEnabledConfig(),
    createBridge() {
      return createBridgeMock({
        async probeAvailability() {
          throw new Error('Failed to import Privy React island');
        },
      });
    },
  });

  await assert.rejects(
    () => service.connect(),
    /temporarily unavailable/i,
  );

  assert.equal(service.getAvailability(), 'error');
  assert.equal(service.getConnectionStatus(), 'error');
  assert.equal(service.getDiagnostics().sdkImportAttempted, true);
  assert.equal(service.getDiagnostics().sdkImportSucceeded, false);
  assert.equal(service.getDiagnostics().unavailableReason, 'sdk_import_failed');
});
