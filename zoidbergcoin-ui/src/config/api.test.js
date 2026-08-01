import test from 'node:test';
import assert from 'node:assert/strict';

import { createDefaultApiBaseUrl } from './api.js';

test('production default API base URL uses zoidbergcoin.com api path', () => {
  assert.equal(
    createDefaultApiBaseUrl({ PROD: true }, { hostname: 'zoidbergcoin.com' }),
    'https://zoidbergcoin.com/api',
  );
});

test('development default API base URL stays local', () => {
  assert.equal(
    createDefaultApiBaseUrl({ PROD: false }, { hostname: 'localhost' }),
    'http://localhost:8000',
  );
  assert.equal(
    createDefaultApiBaseUrl({ PROD: false }, { hostname: 'zoidbergcoin.com' }),
    'http://127.0.0.1:8000',
  );
});
