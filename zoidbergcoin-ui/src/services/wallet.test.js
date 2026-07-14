import test from 'node:test';
import assert from 'node:assert/strict';
import { createWalletManager } from './wallet.js';

class MockProvider {
  constructor(accounts = [], chainId = '0x1') {
    this.accounts = accounts;
    this.chainId = chainId;
    this.listeners = new Map();
    this.nextError = null;
    this.lastPersonalSignParams = null;
    this.signatureResult = '0xsigned-message';
  }

  on(event, handler) {
    this.listeners.set(event, handler);
  }

  async request({ method, params }) {
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
    if (method === 'personal_sign') {
      this.lastPersonalSignParams = params;
      return this.signatureResult;
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

test('verify wallet calls challenge and personal_sign and marks session verified', async () => {
  const provider = new MockProvider(['0xAbCdEfabcdefABCDEFabcdefabcdefABCDEF1234']);
  const authCalls = [];
  const manager = createWalletManager({
    getProvider: () => provider,
    storage: createMemoryStorage(),
    authApi: {
      async createChallenge(walletAddress) {
        authCalls.push(['challenge', walletAddress]);
        return {
          wallet_address: walletAddress,
          normalized_wallet_address: walletAddress,
          nonce: 'nonce-1',
          message: 'Exact challenge message',
          expires_at: '2099-01-01T00:00:00+00:00',
        };
      },
      async verifyChallenge(payload) {
        authCalls.push(['verify', payload]);
        return {
          verified: true,
          wallet_address: payload.wallet_address,
          session_token: 'session-token-1',
          expires_at: '2099-01-01T00:00:00+00:00',
        };
      },
    },
  });

  await manager.connectWallet();
  const verification = await manager.verifyWallet();

  assert.equal(provider.lastPersonalSignParams[0], 'Exact challenge message');
  assert.equal(provider.lastPersonalSignParams[1], '0xAbCdEfabcdefABCDEFabcdefabcdefABCDEF1234');
  assert.equal(authCalls[0][0], 'challenge');
  assert.equal(authCalls[1][0], 'verify');
  assert.equal(verification.verified, true);
  assert.equal(manager.state.isVerifiedSession, true);
});

test('account change clears verified state', async () => {
  const provider = new MockProvider(['0xAbCdEfabcdefABCDEFabcdefabcdefABCDEF1234']);
  const manager = createWalletManager({
    getProvider: () => provider,
    storage: createMemoryStorage(),
    authApi: {
      async createChallenge(walletAddress) {
        return {
          wallet_address: walletAddress,
          normalized_wallet_address: walletAddress,
          nonce: 'nonce-1',
          message: 'Exact challenge message',
          expires_at: '2099-01-01T00:00:00+00:00',
        };
      },
      async verifyChallenge(payload) {
        return {
          verified: true,
          wallet_address: payload.wallet_address,
          session_token: 'session-token-1',
          expires_at: '2099-01-01T00:00:00+00:00',
        };
      },
    },
  });

  await manager.connectWallet();
  await manager.verifyWallet();
  await manager.handleAccountsChanged(['0x2222222222222222222222222222222222222222']);

  assert.equal(manager.state.isVerifiedSession, false);
  assert.equal(manager.state.sessionToken, '');
});

test('disconnect clears verified state', async () => {
  const provider = new MockProvider(['0xAbCdEfabcdefABCDEFabcdefabcdefABCDEF1234']);
  const manager = createWalletManager({
    getProvider: () => provider,
    storage: createMemoryStorage(),
    authApi: {
      async createChallenge(walletAddress) {
        return {
          wallet_address: walletAddress,
          normalized_wallet_address: walletAddress,
          nonce: 'nonce-1',
          message: 'Exact challenge message',
          expires_at: '2099-01-01T00:00:00+00:00',
        };
      },
      async verifyChallenge(payload) {
        return {
          verified: true,
          wallet_address: payload.wallet_address,
          session_token: 'session-token-1',
          expires_at: '2099-01-01T00:00:00+00:00',
        };
      },
    },
  });

  await manager.connectWallet();
  await manager.verifyWallet();
  manager.disconnectWallet();

  assert.equal(manager.state.isVerifiedSession, false);
  assert.equal(manager.state.sessionToken, '');
});

test('user rejects signature and gets a clear error', async () => {
  const provider = new MockProvider(['0xAbCdEfabcdefABCDEFabcdefabcdefABCDEF1234']);
  const manager = createWalletManager({
    getProvider: () => provider,
    storage: createMemoryStorage(),
    authApi: {
      async createChallenge(walletAddress) {
        return {
          wallet_address: walletAddress,
          normalized_wallet_address: walletAddress,
          nonce: 'nonce-1',
          message: 'Exact challenge message',
          expires_at: '2099-01-01T00:00:00+00:00',
        };
      },
      async verifyChallenge() {
        throw new Error('verify should not be called');
      },
    },
  });

  await manager.connectWallet();
  provider.nextError = { code: 4001, message: 'Rejected' };
  const result = await manager.verifyWallet();

  assert.equal(result, null);
  assert.equal(manager.state.isVerifiedSession, false);
  assert.match(manager.state.errorMessage, /signature request was rejected/i);
});
