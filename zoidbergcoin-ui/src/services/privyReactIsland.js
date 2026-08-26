import { getEmbeddedWalletConfig } from '../utils/runtimeConfig.js';

let islandModuleLoader = () => import('../privy/PrivyLoginIsland.jsx');
let reactModuleLoader = () => import('react');
let reactDomClientModuleLoader = () => import('react-dom/client');

function createDeferred() {
  let resolve;
  let reject;
  const promise = new Promise((nextResolve, nextReject) => {
    resolve = nextResolve;
    reject = nextReject;
  });
  return { promise, resolve, reject };
}

function normalizeBridgeConfig(config = {}) {
  if (config?.privy?.appId || Object.prototype.hasOwnProperty.call(config, 'enabled')) {
    return {
      enabled: Boolean(config.enabled),
      configured: Boolean(config.configured && config?.privy?.appId),
      label: config.label || 'Email / Social Wallet',
      privy: {
        appId: String(config?.privy?.appId || '').trim(),
        clientId: String(config?.privy?.clientId || '').trim(),
      },
    };
  }

  return {
    enabled: Boolean(config?.isPrivySelected),
    configured: Boolean(config?.isConfigured && config?.privyAppId),
    label: config?.authOptionLabel || 'Email / Social Wallet',
    privy: {
      appId: String(config?.privyAppId || '').trim(),
      clientId: String(config?.privyClientId || '').trim(),
    },
  };
}

export function setPrivyIslandModuleLoader(loader) {
  islandModuleLoader = typeof loader === 'function' ? loader : islandModuleLoader;
}

export function setPrivyReactModuleLoader(loader) {
  reactModuleLoader = typeof loader === 'function' ? loader : reactModuleLoader;
}

export function setPrivyReactDomClientModuleLoader(loader) {
  reactDomClientModuleLoader = typeof loader === 'function' ? loader : reactDomClientModuleLoader;
}

export async function canLoadPrivyReactIsland() {
  await Promise.all([
    reactModuleLoader(),
    reactDomClientModuleLoader(),
    islandModuleLoader(),
  ]);
  return true;
}

export function createPrivyReactBridge(options = {}) {
  const config = normalizeBridgeConfig(options.config || getEmbeddedWalletConfig(options.env));
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
        reactDomClientModuleLoader(),
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
    async connect(options = {}) {
      const controller = await ensureMounted();
      const currentState = controller.getState?.() || bridgeState;
      handleStateChange(currentState);
      if (!bridgeState.authenticated || !bridgeState.walletAddress) {
        await controller.connect(options);
        await waitFor((state) => state.authenticated && state.walletAddress);
      }
      return {
        provider_id: 'privy',
        wallet_address: bridgeState.walletAddress,
        login_metadata: bridgeState.loginMetadata,
      };
    },
    async disconnect() {
      if (!bridgeController) {
        bridgeState = {
          ready: false,
          authenticated: false,
          walletAddress: '',
          loginMetadata: null,
        };
        return true;
      }
      await bridgeController.disconnect();
      await waitFor((state) => !state.authenticated, 10000).catch(() => null);
      bridgeState = {
        ready: bridgeState.ready,
        authenticated: false,
        walletAddress: '',
        loginMetadata: null,
      };
      return true;
    },
    getState() {
      return {
        ...bridgeState,
      };
    },
    async getAddress() {
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
    async requestSignature(message, walletAddress = '') {
      const controller = await ensureMounted();
      const targetAddress = String(walletAddress || bridgeState.walletAddress || '').trim();
      if (!targetAddress) {
        throw new Error('Email / Social Wallet is not connected.');
      }
      return controller.signMessage(message, targetAddress);
    },
    async probeAvailability() {
      ensureConfigured();
      await canLoadPrivyReactIsland();
      return true;
    },
  };
}
