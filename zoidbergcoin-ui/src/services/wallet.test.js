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

function createAuthApi(overrides = {}) {
  return {
    async createChallenge(walletAddress) {
      return {
        wallet_address: walletAddress,
        normalized_wallet_address: walletAddress.toLowerCase(),
        nonce: 'nonce-1',
        message: 'Exact challenge message',
        expires_at: '2099-01-01T00:00:00+00:00',
      };
    },
    async verifyChallenge(payload) {
      return {
        verified: true,
        wallet_address: payload.wallet_address.toLowerCase(),
        normalized_wallet_address: payload.wallet_address.toLowerCase(),
        session_token: 'session-token-1',
        expires_at: '2099-01-01T00:00:00+00:00',
      };
    },
    async getSession() {
      return {
        valid: true,
        wallet_address: '0xabcdefabcdefabcdefabcdefabcdefabcdef1234',
        normalized_wallet_address: '0xabcdefabcdefabcdefabcdefabcdefabcdef1234',
        expires_at: '2099-01-01T00:00:00+00:00',
      };
    },
    async logout() {
      return {
        logged_out: true,
        revoked: true,
      };
    },
    ...overrides,
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
    authApi: createAuthApi({
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
          normalized_wallet_address: payload.wallet_address,
          session_token: 'session-token-1',
          expires_at: '2099-01-01T00:00:00+00:00',
        };
      },
    }),
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
  let logoutCalls = 0;
  const manager = createWalletManager({
    getProvider: () => provider,
    storage: createMemoryStorage(),
    authApi: createAuthApi({
      async logout() {
        logoutCalls += 1;
        return { logged_out: true, revoked: true };
      },
    }),
  });

  await manager.connectWallet();
  await manager.verifyWallet();
  await manager.handleAccountsChanged(['0x2222222222222222222222222222222222222222']);

  assert.equal(manager.state.isVerifiedSession, false);
  assert.equal(manager.state.sessionToken, '');
  assert.equal(logoutCalls, 1);
});

test('disconnect clears verified state', async () => {
  const provider = new MockProvider(['0xAbCdEfabcdefABCDEFabcdefabcdefABCDEF1234']);
  let logoutCalls = 0;
  const manager = createWalletManager({
    getProvider: () => provider,
    storage: createMemoryStorage(),
    authApi: createAuthApi({
      async logout() {
        logoutCalls += 1;
        return { logged_out: true, revoked: true };
      },
    }),
  });

  await manager.connectWallet();
  await manager.verifyWallet();
  await manager.disconnectWallet();

  assert.equal(manager.state.isVerifiedSession, false);
  assert.equal(manager.state.sessionToken, '');
  assert.equal(logoutCalls, 1);
});

test('user rejects signature and gets a clear error', async () => {
  const provider = new MockProvider(['0xAbCdEfabcdefABCDEFabcdefabcdefABCDEF1234']);
  const manager = createWalletManager({
    getProvider: () => provider,
    storage: createMemoryStorage(),
    authApi: createAuthApi({
      async verifyChallenge() {
        throw new Error('verify should not be called');
      },
    }),
  });

  await manager.connectWallet();
  provider.nextError = { code: 4001, message: 'Rejected' };
  const result = await manager.verifyWallet();

  assert.equal(result, null);
  assert.equal(manager.state.isVerifiedSession, false);
  assert.match(manager.state.errorMessage, /signature request was rejected/i);
});

test('persisted verified session is restored through backend session introspection', async () => {
  const storage = createMemoryStorage();
  storage.setItem('zoidberg:last-wallet-address', '0xabcdefabcdefabcdefabcdefabcdefabcdef1234');
  storage.setItem(
    'zoidberg:verified-wallet-session',
    JSON.stringify({
      walletAddress: '0xabcdefabcdefabcdefabcdefabcdefabcdef1234',
      sessionToken: 'session-token-1',
      expiresAt: '2099-01-01T00:00:00+00:00',
    }),
  );

  let sessionCalls = 0;
  const manager = createWalletManager({
    getProvider: () => new MockProvider(['0xAbCdEfabcdefABCDEFabcdefabcdefABCDEF1234']),
    storage,
    authApi: createAuthApi({
      async getSession() {
        sessionCalls += 1;
        return {
          valid: true,
          wallet_address: '0xabcdefabcdefabcdefabcdefabcdefabcdef1234',
          normalized_wallet_address: '0xabcdefabcdefabcdefabcdefabcdefabcdef1234',
          expires_at: '2099-01-02T00:00:00+00:00',
        };
      },
    }),
  });

  await manager.detectMetaMask();

  assert.equal(sessionCalls, 1);
  assert.equal(manager.state.isVerifiedSession, true);
  assert.equal(manager.state.verifiedWalletAddress, '0xabcdefabcdefabcdefabcdefabcdefabcdef1234');
  assert.equal(manager.state.identitySource, 'metamask_verified');
});

test('session refresh clears verified state when backend rejects the token', async () => {
  const provider = new MockProvider(['0xAbCdEfabcdefABCDEFabcdefabcdefABCDEF1234']);
  const manager = createWalletManager({
    getProvider: () => provider,
    storage: createMemoryStorage(),
    authApi: createAuthApi({
      async getSession() {
        const error = new Error('Session expired');
        error.response = {
          status: 401,
          data: { detail: 'Session token has expired.' },
        };
        throw error;
      },
    }),
  });

  await manager.connectWallet();
  await manager.verifyWallet();
  const session = await manager.refreshVerifiedSession();

  assert.equal(session, null);
  assert.equal(manager.state.isVerifiedSession, false);
  assert.equal(manager.state.sessionToken, '');
  assert.equal(manager.state.connectionStatus, 'expired');
  assert.match(manager.state.authError, /expired/i);
});

test('authorization header is only exposed for active verified sessions', async () => {
  const provider = new MockProvider(['0xAbCdEfabcdefABCDEFabcdefabcdefABCDEF1234']);
  const manager = createWalletManager({
    getProvider: () => provider,
    storage: createMemoryStorage(),
    authApi: createAuthApi(),
  });

  await manager.connectWallet();
  assert.deepEqual(manager.getAuthorizationHeader(), {});

  await manager.verifyWallet();
  assert.deepEqual(manager.getAuthorizationHeader(), {
    Authorization: 'Bearer session-token-1',
  });
});
