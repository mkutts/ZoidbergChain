function defaultMetaMaskProviderGetter() {
  if (typeof window === 'undefined') {
    return null;
  }
  return window.ethereum || null;
}

function normalizeAccounts(accounts) {
  return Array.isArray(accounts) ? accounts.filter((value) => typeof value === 'string' && value) : [];
}

export function createMetaMaskAdapter(options = {}) {
  const getProvider = options.getProvider || defaultMetaMaskProviderGetter;

  return {
    providerId: 'metamask',
    providerLabel: 'MetaMask',
    providerType: 'injected_wallet',
    supportsExportInfo: true,
    supportsNativeTransferSigning: true,
    supportsMessageSigning: true,
    supportsPortableWalletPromise: true,
    getProvider() {
      return getProvider();
    },
    isAvailable() {
      return Boolean(getProvider());
    },
    getConnectionStatus() {
      return this.isAvailable() ? 'available' : 'unavailable';
    },
    async connect() {
      const provider = getProvider();
      if (!provider) {
        return [];
      }
      return normalizeAccounts(await provider.request({ method: 'eth_requestAccounts' }));
    },
    async getAccounts() {
      const provider = getProvider();
      if (!provider) {
        return [];
      }
      return normalizeAccounts(await provider.request({ method: 'eth_accounts' }));
    },
    async getChainId() {
      const provider = getProvider();
      if (!provider) {
        return '';
      }
      if (typeof provider.chainId === 'string') {
        return provider.chainId;
      }
      const chainId = await provider.request({ method: 'eth_chainId' });
      return typeof chainId === 'string' ? chainId : '';
    },
    async requestSignature(message, walletAddress) {
      const provider = getProvider();
      if (!provider) {
        throw new Error('MetaMask is not available in this browser.');
      }
      return provider.request({
        method: 'personal_sign',
        params: [message, walletAddress],
      });
    },
    on(event, handler) {
      const provider = getProvider();
      if (!provider || typeof provider.on !== 'function') {
        return;
      }
      provider.on(event, handler);
    },
    disconnect() {
      return Promise.resolve();
    },
  };
}

export function createWalletProviderRegistry(options = {}) {
  const metaMask = createMetaMaskAdapter({
    getProvider: options.getMetaMaskProvider || options.getProvider,
  });
  const adapters = [metaMask];

  return {
    listAdapters() {
      return adapters.slice();
    },
    getDefaultAdapter() {
      return metaMask;
    },
    getAdapterById(providerId) {
      return adapters.find((adapter) => adapter.providerId === providerId) || null;
    },
  };
}
