import test from 'node:test';
import assert from 'node:assert/strict';

import {
  createMetaMaskAdapter,
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
  });

  const adapters = registry.listAdapters();
  assert.equal(adapters.length, 1);
  assert.equal(registry.getDefaultAdapter().providerId, 'metamask');
  assert.equal(registry.getAdapterById('metamask')?.providerLabel, 'MetaMask');
  assert.equal(registry.getAdapterById('embedded-wallet'), null);
});
