import test from 'node:test';
import assert from 'node:assert/strict';
import { normalizeWalletAddress, shortenWalletAddress } from './walletAddress.js';

test('valid 0x address normalizes to lowercase', () => {
  assert.equal(
    normalizeWalletAddress('0xAbCdEfabcdefABCDEFabcdefabcdefABCDEF1234'),
    '0xabcdefabcdefabcdefabcdefabcdefabcdef1234',
  );
});

test('invalid address returns null', () => {
  assert.equal(normalizeWalletAddress('not-an-address'), null);
  assert.equal(normalizeWalletAddress('0x1234'), null);
});

test('short address display works', () => {
  assert.equal(
    shortenWalletAddress('0xAbCdEfabcdefABCDEFabcdefabcdefABCDEF1234'),
    '0xabcd...1234',
  );
});
