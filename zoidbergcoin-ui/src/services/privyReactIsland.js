import { getEmbeddedWalletConfig } from '../utils/runtimeConfig.js';

let islandModuleLoader = () => import('../privy/PrivyLoginIsland.jsx');
let reactModuleLoader = () => import('react');

function createDeferred() {
  let resolve;
  let reject;
  const promise = new Promise((nextResolve, nextReject) => {
    resolve = nextResolve;
    reject = nextReject;
  });
  return { promise, resolve, reject };
}

export function setPrivyIslandModuleLoader(loader) {
  islandModuleLoader = typeof loader === 'function' ? loader : islandModuleLoader;
}

export function setPrivyReactModuleLoader(loader) {
  reactModuleLoader = typeof loader === 'function' ? loader : reactModuleLoader;
}

export async function canLoadPrivyReactIsland() {
  await Promise.all([
    reactModuleLoader(),
    islandModuleLoader(),
  ]);
  return true;
}

export function createPrivyReactBridge(options = {}) {
  const config = options.config || getEmbeddedWalletConfig(options.env);
  const documentRef = options.document || (typeof document === 'undefined' ? null : document);
  const bodyRef = documentRef?.body || null;
  let root = null;
  let container = null;
  let bridgeController = null;
  let bridgeState = {
    ready: false,
    authenticated: false,
    walletAddress: '',
    loginMetadata: null,
  };
  let mountPromise = null;

  function ensureDocument() {
    if (!documentRef || !bodyRef) {
      throw new Error('Privy React island can only run in a browser context.');
    }
  }

  function ensureConfigured() {
    if (!config.enabled || !config.configured || !config.privy.appId) {
      throw new Error('Email / Social Wallet is not configured.');
    }
  }

  function handleStateChange(nextState = {}) {
    bridgeState = {
      ready: Boolean(nextState.ready),
      authenticated: Boolean(nextState.authenticated),
      walletAddress: String(nextState.walletAddress || '').trim(),
      loginMetadata: nextState.loginMetadata || null,
    };
  }

  async function ensureMounted() {
    ensureConfigured();
    ensureDocument();
    if (mountPromise) {
      return mountPromise;
    }

    mountPromise = (async () => {
      const [reactModule, reactDomClient, islandModule] = await Promise.all([
        reactModuleLoader(),
        import('react-dom/client'),
        islandModuleLoader(),
      ]);

      const React = reactModule.default || reactModule;
      const PrivyLoginIsland = islandModule.default;

      container = documentRef.createElement('div');
      container.setAttribute('data-zoidberg-privy-island', 'true');
      container.style.display = 'contents';
      bodyRef.appendChild(container);

      const readyDeferred = createDeferred();
      root = reactDomClient.createRoot(container);
      root.render(
        React.createElement(PrivyLoginIsland, {
          appId: config.privy.appId,
          clientId: config.privy.clientId || undefined,
          onReady(controller) {
            bridgeController = controller;
            readyDeferred.resolve(controller);
          },
          onStateChange: handleStateChange,
          onError(error) {
            readyDeferred.reject(error);
          },
        }),
      );

      await readyDeferred.promise;
      return bridgeController;
    })();

    return mountPromise;
  }

  async function waitFor(predicate, timeoutMs = 45000) {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      if (predicate(bridgeState)) {
        return bridgeState;
      }
      await new Promise((resolve) => {
        window.setTimeout(resolve, 50);
      });
    }
    throw new Error('Email / Social Wallet did not finish loading in time.');
  }

  return {
    async connect() {
      const controller = await ensureMounted();
      const currentState = controller.getState?.() || bridgeState;
      handleStateChange(currentState);
      if (!bridgeState.authenticated || !bridgeState.walletAddress) {
        await controller.connect();
        await waitFor((state) => state.authenticated && state.walletAddress);
      }
      return {
        provider_id: 'privy',
        wallet_address: bridgeState.walletAddress,
        login_metadata: bridgeState.loginMetadata,
      };
    },
    async disconnect() {
      const controller = await ensureMounted();
      await controller.disconnect();
      await waitFor((state) => !state.authenticated, 10000).catch(() => null);
      bridgeState = {
        ready: bridgeState.ready,
        authenticated: false,
        walletAddress: '',
        loginMetadata: null,
      };
      return true;
    },
    async getAddress() {
      await ensureMounted();
      return bridgeState.walletAddress || '';
    },
    getConnectionStatus() {
      if (!config.enabled || !config.configured) {
        return 'coming_soon';
      }
      if (!bridgeState.ready) {
        return 'idle';
      }
      if (!bridgeState.authenticated || !bridgeState.walletAddress) {
        return 'disconnected';
      }
      return 'connected';
    },
    async requestSignature(message) {
      const controller = await ensureMounted();
      if (!bridgeState.walletAddress) {
        throw new Error('Email / Social Wallet is not connected.');
      }
      return controller.signMessage(message);
    },
    async probeAvailability() {
      ensureConfigured();
      await canLoadPrivyReactIsland();
      return true;
    },
  };
}
