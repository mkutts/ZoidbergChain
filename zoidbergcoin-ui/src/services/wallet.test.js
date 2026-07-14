import test from 'node:test';
import assert from 'node:assert/strict';
import { createWalletManager } from './wallet.js';

class MockProvider {
  constructor(accounts = [], chainId = '0x1') {
    this.accounts = accounts;
    this.chainId = chainId;
    this.listeners = new Map();
    this.nextError = null;
  }

  on(event, handler) {
    this.listeners.set(event, handler);
  }

  async request({ method }) {
    if (this.nextError) {
      const error = this.nextError;
      this.nextError = null;
      throw error;
    }
    if (method === 'eth_accounts' || method === 'eth_requestAccounts') {
      return this.accounts;
    }
    if (method === 'eth_chainId') {
      return this.chainId;
    }
    return null;
  }
}

function createMemoryStorage() {
  const values = new Map();
  return {
    getItem(key) {
      return values.has(key) ? values.get(key) : null;
    },
    setItem(key, value) {
      values.set(key, value);
    },
    removeItem(key) {
      values.delete(key);
    },
  };
}

test('MetaMask unavailable state is exposed clearly', async () => {
  const manager = createWalletManager({
    getProvider: () => null,
    storage: createMemoryStorage(),
  });

  const available = await manager.detectMetaMask();

  assert.equal(available, false);
  assert.equal(manager.state.isMetaMaskAvailable, false);
  assert.equal(manager.state.isConnected, false);
});

test('connect success with mocked provider', async () => {
  const provider = new MockProvider(['0xAbCdEfabcdefABCDEFabcdefabcdefABCDEF1234'], '0xaa36a7');
  const manager = createWalletManager({
    getProvider: () => provider,
    storage: createMemoryStorage(),
  });

  await manager.connectWallet();

  assert.equal(manager.state.isConnected, true);
  assert.equal(manager.state.normalizedWalletAddress, '0xabcdefabcdefabcdefabcdefabcdefabcdef1234');
  assert.equal(manager.state.chainId, '0xaa36a7');
  assert.equal(manager.state.isVerifiedSession, false);
});

test('user rejection produces a friendly error', async () => {
  const provider = new MockProvider();
  provider.nextError = { code: 4001, message: 'Rejected' };
  const manager = createWalletManager({
    getProvider: () => provider,
    storage: createMemoryStorage(),
  });

  const result = await manager.connectWallet();

  assert.equal(result, null);
  assert.equal(manager.state.isConnected, false);
  assert.match(manager.state.errorMessage, /rejected/i);
});

test('accountsChanged updates address', async () => {
  const provider = new MockProvider(['0x1111111111111111111111111111111111111111']);
  const manager = createWalletManager({
    getProvider: () => provider,
    storage: createMemoryStorage(),
  });

  await manager.detectMetaMask();
  await manager.handleAccountsChanged(['0x2222222222222222222222222222222222222222']);

  assert.equal(manager.state.normalizedWalletAddress, '0x2222222222222222222222222222222222222222');
});

test('accountsChanged empty disconnects wallet', async () => {
  const provider = new MockProvider(['0x1111111111111111111111111111111111111111']);
  const manager = createWalletManager({
    getProvider: () => provider,
    storage: createMemoryStorage(),
  });

  await manager.detectMetaMask();
  await manager.handleAccountsChanged([]);

  assert.equal(manager.state.isConnected, false);
  assert.equal(manager.state.normalizedWalletAddress, '');
});

test('shortened address display is available from wallet manager', () => {
  const manager = createWalletManager({
    getProvider: () => null,
    storage: createMemoryStorage(),
  });

  assert.equal(
    manager.shortenAddress('0xAbCdEfabcdefABCDEFabcdefabcdefABCDEF1234'),
    '0xabcd...1234',
  );
});

test('connected wallet is never treated as verified yet and no private key is stored', async () => {
  const provider = new MockProvider(['0xAbCdEfabcdefABCDEFabcdefabcdefABCDEF1234']);
  const manager = createWalletManager({
    getProvider: () => provider,
    storage: createMemoryStorage(),
  });

  await manager.connectWallet();

  assert.equal(manager.state.isVerifiedSession, false);
  assert.equal('privateKey' in manager.state, false);
  assert.equal('private_key' in manager.state, false);
});
