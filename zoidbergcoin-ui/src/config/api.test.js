import test from 'node:test';
import assert from 'node:assert/strict';

import { createDefaultApiBaseUrl, resolveApiBaseUrl } from './api.js';

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

test('production resolves API base URL from VITE_API_BASE_URL', () => {
  assert.equal(
    resolveApiBaseUrl(
      {
        PROD: true,
        VITE_API_BASE_URL: 'https://zoidbergcoin.com/api',
        VITE_API_BASE: 'https://example.com/ignored',
        VITE_BACKEND_URL: 'https://example.com/ignored-too',
      },
      { hostname: 'zoidbergcoin.com' },
    ),
    'https://zoidbergcoin.com/api',
  );
});

test('production does not fall back to 127.0.0.1 when VITE_API_BASE_URL is provided', () => {
  assert.notEqual(
    resolveApiBaseUrl(
      {
        PROD: true,
        VITE_API_BASE_URL: 'https://zoidbergcoin.com/api',
      },
      { hostname: 'zoidbergcoin.com' },
    ),
    'http://127.0.0.1:8000',
  );
});

test('API base URL falls back through public env names in order', () => {
  assert.equal(
    resolveApiBaseUrl(
      {
        PROD: true,
        VITE_API_BASE_URL: '   ',
        VITE_API_BASE: 'https://zoidbergcoin.com/api-from-base',
        VITE_BACKEND_URL: 'https://zoidbergcoin.com/api-from-backend',
      },
      { hostname: 'zoidbergcoin.com' },
    ),
    'https://zoidbergcoin.com/api-from-base',
  );

  assert.equal(
    resolveApiBaseUrl(
      {
        PROD: true,
        VITE_API_BASE_URL: '',
        VITE_API_BASE: '',
        VITE_BACKEND_URL: 'https://zoidbergcoin.com/api-from-backend',
      },
      { hostname: 'zoidbergcoin.com' },
    ),
    'https://zoidbergcoin.com/api-from-backend',
  );
});
