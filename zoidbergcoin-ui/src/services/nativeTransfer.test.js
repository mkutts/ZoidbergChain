import test from 'node:test';
import assert from 'node:assert/strict';

import {
  TRANSFER_PENDING_WARNING,
  createNativeTransferService,
  validateNativeTransferDraft,
} from './nativeTransfer.js';

class MockProvider {
  constructor() {
    this.lastPersonalSignParams = null;
    this.signatureResult = '0xsigned-transfer';
    this.nextError = null;
  }

  async request({ method, params }) {
    if (this.nextError) {
      const error = this.nextError;
      this.nextError = null;
      throw error;
    }
    if (method === 'personal_sign') {
      this.lastPersonalSignParams = params;
      return this.signatureResult;
    }
    return null;
  }
}

function createApi(overrides = {}) {
  const calls = [];
  return {
    calls,
    async post(path, payload) {
      calls.push({ path, payload });
      if (path === '/auth/wallet/transfer-challenge') {
        return {
          data: {
            message: 'Exact backend transfer message',
            nonce: 'random-nonce',
            expires_at: '2099-01-01T00:00:00+00:00',
            transfer_preview: {
              from_address: payload.from_address,
              to_address: payload.to_address,
              amount: payload.amount,
              fee: payload.fee,
              network: 'zoidberg-testnet',
            },
          },
        };
      }
      if (path === '/transfers/submit') {
        return {
          data: {
            transfer_id: 'transfer-1',
            status: 'signed_pending',
            from_address: payload.from_address,
            to_address: payload.to_address,
            amount: payload.amount,
          },
        };
      }
      throw new Error(`Unexpected path ${path}`);
    },
    ...overrides,
  };
}

test('validateNativeTransferDraft rejects invalid addresses and zero amount', () => {
  assert.throws(
    () => validateNativeTransferDraft({
      fromAddress: '0x1111111111111111111111111111111111111111',
      toAddress: 'bad-wallet',
      amount: '1',
    }),
    /valid 0x address/i,
  );
  assert.throws(
    () => validateNativeTransferDraft({
      fromAddress: '0x1111111111111111111111111111111111111111',
      toAddress: '0x2222222222222222222222222222222222222222',
      amount: '0',
    }),
    /greater than zero/i,
  );
});

test('submitSignedTransferIntent signs exact backend message and returns pending status', async () => {
  const provider = new MockProvider();
  const api = createApi();
  const service = createNativeTransferService({
    api,
    getProvider: () => provider,
    getApiErrorMessage: (error, fallback) => error?.message || fallback,
  });

  const result = await service.submitSignedTransferIntent({
    fromAddress: '0x1111111111111111111111111111111111111111',
    walletAddressForSigning: '0x1111111111111111111111111111111111111111',
    toAddress: '0x2222222222222222222222222222222222222222',
    amount: '1.25',
    memo: 'hello',
  });

  assert.equal(provider.lastPersonalSignParams[0], 'Exact backend transfer message');
  assert.equal(provider.lastPersonalSignParams[1], '0x1111111111111111111111111111111111111111');
  assert.equal(api.calls[0].path, '/auth/wallet/transfer-challenge');
  assert.equal(api.calls[1].path, '/transfers/submit');
  assert.equal(result.status, 'signed_pending');
});

test('submitSignedTransferIntent surfaces MetaMask rejection clearly', async () => {
  const provider = new MockProvider();
  provider.nextError = { code: 4001, message: 'Rejected' };
  const api = createApi();
  const service = createNativeTransferService({
    api,
    getProvider: () => provider,
    getApiErrorMessage: (error, fallback) => error?.message || fallback,
  });

  await assert.rejects(
    () => service.submitSignedTransferIntent({
      fromAddress: '0x1111111111111111111111111111111111111111',
      walletAddressForSigning: '0x1111111111111111111111111111111111111111',
      toAddress: '0x2222222222222222222222222222222222222222',
      amount: '1',
    }),
    /rejected in metamask/i,
  );
});

test('pending warning copy stays non-final', () => {
  assert.match(TRANSFER_PENDING_WARNING, /not settled/i);
});
