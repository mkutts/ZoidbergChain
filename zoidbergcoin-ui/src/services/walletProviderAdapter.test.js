import test from 'node:test';
import assert from 'node:assert/strict';

import {
  createMetaMaskAdapter,
  createPrivyEmbeddedWalletAdapter,
  createWalletProviderRegistry,
} from './walletProviderAdapter.js';

class MockProvider {
  constructor(accounts = ['0x1111111111111111111111111111111111111111'], chainId = '0x1') {
    this.accounts = accounts;
    this.chainId = chainId;
    this.lastPersonalSignParams = null;
  }

  async request({ method, params }) {
    if (method === 'eth_requestAccounts' || method === 'eth_accounts') {
      return this.accounts;
    }
    if (method === 'eth_chainId') {
      return this.chainId;
    }
    if (method === 'personal_sign') {
      this.lastPersonalSignParams = params;
      return '0xsigned-message';
    }
    return null;
  }

  on() {}
}

test('MetaMask adapter detects availability and normalizes account access methods', async () => {
  const provider = new MockProvider();
  const adapter = createMetaMaskAdapter({
    getProvider: () => provider,
  });

  assert.equal(adapter.providerId, 'metamask');
  assert.equal(adapter.isAvailable(), true);
  assert.deepEqual(await adapter.connect(), ['0x1111111111111111111111111111111111111111']);
  assert.deepEqual(await adapter.getAccounts(), ['0x1111111111111111111111111111111111111111']);
  assert.equal(await adapter.getChainId(), '0x1');
});

test('MetaMask adapter requests personal_sign through the provider', async () => {
  const provider = new MockProvider();
  const adapter = createMetaMaskAdapter({
    getProvider: () => provider,
  });

  const signature = await adapter.requestSignature('Exact challenge message', '0x1111111111111111111111111111111111111111');

  assert.equal(signature, '0xsigned-message');
  assert.deepEqual(provider.lastPersonalSignParams, [
    'Exact challenge message',
    '0x1111111111111111111111111111111111111111',
  ]);
});

test('wallet provider registry exposes MetaMask as the default live adapter', () => {
  const registry = createWalletProviderRegistry({
    getProvider: () => null,
    embeddedWalletService: {
      getAvailability() {
        return 'coming_soon';
      },
      getUnavailableMessage() {
        return 'Embedded wallet setup is not configured on this deployment yet.';
      },
      isConfigured() {
        return false;
      },
      getConnectionStatus() {
        return 'unavailable';
      },
    },
  });

  const adapters = registry.listAdapters();
  assert.equal(adapters.length, 2);
  assert.equal(registry.getDefaultAdapter().providerId, 'metamask');
  assert.equal(registry.getAdapterById('metamask')?.providerLabel, 'MetaMask');
  assert.equal(registry.getAdapterById('privy_embedded')?.providerType, 'embedded_wallet');
  assert.equal(registry.describeAdapters()[1].availability, 'coming_soon');
});

test('wallet provider registry exposes deferred embedded wallets as a non-fatal coming-soon option', () => {
  const registry = createWalletProviderRegistry({
    getProvider: () => null,
    embeddedWalletService: {
      getAvailability() {
        return 'coming_soon';
      },
      getUnavailableMessage() {
        return 'Email / Social Wallet is coming soon. Privy\'s supported web integration path for this Vue app is a small React island, so MetaMask remains the only live login until that path is implemented.';
      },
      isConfigured() {
        return true;
      },
      getConnectionStatus() {
        return 'coming_soon';
      },
      getDiagnostics() {
        return {
          providerConfigured: true,
          appIdPresent: true,
          providerName: 'privy',
          sdkImportAttempted: false,
          sdkImportSucceeded: false,
          initAttempted: false,
          initSucceeded: false,
          unavailableReason: 'react_sdk_required',
          lastErrorMessage: '',
        };
      },
    },
  });

  const embedded = registry.describeAdapters().find((item) => item.provider_id === 'privy_embedded');
  assert.equal(embedded?.availability, 'coming_soon');
  assert.match(embedded?.availability_message || '', /coming soon/i);
  assert.equal(embedded?.diagnostics?.unavailableReason, 'react_sdk_required');
  assert.equal(embedded?.diagnostics?.providerConfigured, true);
});

test('embedded wallet adapter connects and signs through the injected service contract', async () => {
  const calls = [];
  const adapter = createPrivyEmbeddedWalletAdapter({
    service: {
      initialize() {
        calls.push('initialize');
        return Promise.resolve(true);
      },
      isConfigured() {
        return true;
      },
      getConnectionStatus() {
        return 'ready';
      },
      restoreConnection() {
        calls.push('restore');
        return Promise.resolve(['0x3333333333333333333333333333333333333333']);
      },
      connect(options) {
        calls.push(['connect', options]);
        return Promise.resolve(['0x3333333333333333333333333333333333333333']);
      },
      sendEmailCode(email) {
        calls.push(['sendEmailCode', email]);
        return Promise.resolve({ sent: true });
      },
      startOAuthLogin(providerId) {
        calls.push(['startOAuthLogin', providerId]);
        return Promise.resolve({ redirected: true });
      },
      getAccounts() {
        return Promise.resolve(['0x3333333333333333333333333333333333333333']);
      },
      getAddress() {
        return Promise.resolve('0x3333333333333333333333333333333333333333');
      },
      getChainId() {
        return Promise.resolve('0x1');
      },
      requestSignature(message, walletAddress) {
        calls.push(['requestSignature', message, walletAddress]);
        return Promise.resolve('0xembedded-signature');
      },
      disconnect() {
        calls.push('disconnect');
        return Promise.resolve();
      },
      getPortabilityInfo() {
        return {
          helpUrl: 'https://docs.privy.io/wallets/wallets/export',
          helpCopy: 'Privy portability help.',
        };
      },
      getAuthState() {
        return { isAuthenticated: true };
      },
      getDiagnostics() {
        return {
          providerConfigured: true,
          appIdPresent: true,
          providerName: 'privy',
          sdkImportAttempted: true,
          sdkImportSucceeded: true,
          initAttempted: true,
          initSucceeded: true,
          unavailableReason: 'none',
          lastErrorMessage: '',
        };
      },
    },
  });

  assert.equal(adapter.isAvailable(), true);
  assert.deepEqual(await adapter.connect({ authMethod: 'email' }), ['0x3333333333333333333333333333333333333333']);
  assert.equal(await adapter.requestSignature('hello', '0x3333333333333333333333333333333333333333'), '0xembedded-signature');
  assert.equal(await adapter.getChainId(), '0x1');
  assert.equal(adapter.getPortabilityInfo().helpUrl, 'https://docs.privy.io/wallets/wallets/export');
  assert.equal(adapter.getDiagnostics().initSucceeded, true);
  assert.deepEqual(calls[0], ['connect', { authMethod: 'email' }]);
  assert.deepEqual(calls[1], ['requestSignature', 'hello', '0x3333333333333333333333333333333333333333']);
});
