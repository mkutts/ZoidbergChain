import test from 'node:test';
import assert from 'node:assert/strict';

import {
  canLoadPrivyReactIsland,
  createPrivyReactBridge,
  setPrivyIslandModuleLoader,
  setPrivyReactModuleLoader,
} from './privyReactIsland.js';

test('canLoadPrivyReactIsland resolves when the React island loaders succeed', async () => {
  setPrivyReactModuleLoader(async () => ({ default: {} }));
  setPrivyIslandModuleLoader(async () => ({ default: () => null }));

  const available = await canLoadPrivyReactIsland();

  assert.equal(available, true);
});

test('createPrivyReactBridge refuses to run when Privy is not configured', async () => {
  const bridge = createPrivyReactBridge({
    config: {
      provider: 'privy',
      enabled: true,
      configured: false,
      label: 'Email / Social Wallet',
      privy: { appId: '', clientId: '' },
    },
  });

  await assert.rejects(
    () => bridge.probeAvailability(),
    /not configured/i,
  );
});
