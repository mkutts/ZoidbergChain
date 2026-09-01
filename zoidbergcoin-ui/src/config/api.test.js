import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';

import {
  API_BASE_URL,
  adminApiClient,
  apiClient,
  buildApiUrl,
  createDefaultApiBaseUrl,
  publicApiClient,
  resolveApiBaseUrl,
} from './api.js';

test('production default API base URL uses same-origin api path', () => {
  assert.equal(
    createDefaultApiBaseUrl({ PROD: true }),
    '/api',
  );
});

test('development default API base URL uses the Vite local api proxy', () => {
  assert.equal(
    createDefaultApiBaseUrl({ PROD: false }),
    '/api',
  );
});

test('production can resolve API base URL from VITE_API_BASE_URL for split-origin hosting', () => {
  assert.equal(
    resolveApiBaseUrl(
      {
        PROD: true,
        VITE_API_BASE_URL: 'https://zoidbergcoin.com/api',
        VITE_API_BASE: 'https://example.com/ignored',
        VITE_BACKEND_URL: 'https://example.com/ignored-too',
      },
    ),
    'https://zoidbergcoin.com/api',
  );
});

test('production does not fall back to same-origin when VITE_API_BASE_URL is provided', () => {
  assert.notEqual(
    resolveApiBaseUrl(
      {
        PROD: true,
        VITE_API_BASE_URL: 'https://zoidbergcoin.com/api',
      },
    ),
    '/api',
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
    ),
    'https://zoidbergcoin.com/api-from-backend',
  );
});

test('development does not silently use the production API when local config is missing', () => {
  assert.equal(
    resolveApiBaseUrl({
      PROD: false,
      VITE_API_BASE_URL: '',
      VITE_API_BASE: '',
      VITE_BACKEND_URL: '',
    }),
    '/api',
  );
});

test('development ignores remote API configuration instead of hitting production', () => {
  assert.equal(
    resolveApiBaseUrl({
      PROD: false,
      VITE_API_BASE_URL: 'https://zoidbergcoin.com/api',
    }),
    '/api',
  );
});

test('development ignores explicit local backend API configuration in favor of the proxy', () => {
  assert.equal(
    resolveApiBaseUrl({
      PROD: false,
      VITE_API_BASE_URL: 'http://localhost:8000/api/',
    }),
    '/api',
  );
});

test('API URL builder normalizes duplicate slashes around paths', () => {
  assert.equal(buildApiUrl('/chain/summary'), '/api/chain/summary');
  assert.equal(buildApiUrl('chain/summary'), '/api/chain/summary');
});

test('shared API clients use the canonical API base URL', () => {
  assert.equal(API_BASE_URL, '/api');
  assert.equal(apiClient.defaults.baseURL, API_BASE_URL);
  assert.equal(publicApiClient.defaults.baseURL, API_BASE_URL);
  assert.equal(adminApiClient.defaults.baseURL, API_BASE_URL);
});

test('Vite development proxy routes api requests to the local backend', () => {
  const devScript = fs.readFileSync(new URL('../../scripts/dev.mjs', import.meta.url), 'utf8');
  assert.ok(devScript.includes("'/api'"));
  assert.ok(devScript.includes("target: 'http://localhost:8000'"));
  assert.ok(devScript.includes("path.replace(/^\\/api(?=\\/|$)/, '')"));
});
