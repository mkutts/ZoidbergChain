import test from 'node:test';
import assert from 'node:assert/strict';

import { shouldDisplayAccessGate } from './accessGate.js';

test('normal visitors still see the access gate when app access is required', () => {
  assert.equal(
    shouldDisplayAccessGate({
      requiresAppAccess: true,
      isAppUnlocked: false,
      skipAccessGate: false,
    }),
    true,
  );
});

test('admin route bypasses the normal access gate without unlocking the app globally', () => {
  assert.equal(
    shouldDisplayAccessGate({
      requiresAppAccess: true,
      isAppUnlocked: false,
      skipAccessGate: true,
    }),
    false,
  );
});
