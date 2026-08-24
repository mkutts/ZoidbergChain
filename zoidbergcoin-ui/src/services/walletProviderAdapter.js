import { createPrivyEmbeddedWalletService } from './privyEmbeddedWallet.js';
import { EMBEDDED_WALLET_CONFIG } from '../utils/embeddedWalletConfig.js';

function defaultMetaMaskProviderGetter() {
  if (typeof window === 'undefined') {
    return null;
  }
  return window.ethereum || null;
}

function normalizeAccounts(accounts) {
  return Array.isArray(accounts) ? accounts.filter((value) => typeof value === 'string' && value) : [];
}

function buildProviderDescriptor(adapter) {
  const portability = typeof adapter.getPortabilityInfo === 'function'
    ? adapter.getPortabilityInfo()
    : {};
  const availability = typeof adapter.getAvailability === 'function'
    ? adapter.getAvailability()
    : (adapter.isAvailable() ? 'available' : 'unavailable');
  const availabilityMessage = typeof adapter.getAvailabilityMessage === 'function'
    ? adapter.getAvailabilityMessage()
    : '';
  const diagnostics = typeof adapter.getDiagnostics === 'function'
    ? adapter.getDiagnostics()
    : null;

  return {
    provider_id: adapter.providerId,
    provider_label: adapter.providerLabel,
    provider_type: adapter.providerType,
    availability,
    availability_message: availabilityMessage,
    supports_message_signing: Boolean(adapter.supportsMessageSigning),
    supports_native_transfer_signing: Boolean(adapter.supportsNativeTransferSigning),
    supports_export_info: Boolean(adapter.supportsExportInfo),
    supports_portable_wallet_promise: Boolean(adapter.supportsPortableWalletPromise),
    portability_help_url: portability.helpUrl || '',
    portability_help_copy: portability.helpCopy || '',
    diagnostics,
  };
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
    async initialize() {
      return true;
    },
    getAvailability() {
      return this.isAvailable() ? 'available' : 'unavailable';
    },
    getAvailabilityMessage() {
      return this.isAvailable() ? '' : 'MetaMask is not available in this browser.';
    },
    getProvider() {
      return getProvider();
    },
    isAvailable() {
      return Boolean(getProvider());
    },
    getConnectionStatus() {
      return this.isAvailable() ? 'available' : 'unavailable';
    },
    async restoreConnection() {
      return this.getAccounts();
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
    async getAddress() {
      const accounts = await this.getAccounts();
      return accounts[0] || '';
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
    removeListener(event, handler) {
      const provider = getProvider();
      if (!provider || typeof provider.removeListener !== 'function') {
        return;
      }
      provider.removeListener(event, handler);
    },
    disconnect() {
      return Promise.resolve();
    },
    getPortabilityInfo() {
      return {
        helpCopy: 'MetaMask wallets are already user-controlled external wallets.',
      };
    },
  };
}

export function createPrivyEmbeddedWalletAdapter(options = {}) {
  const service = options.service || createPrivyEmbeddedWalletService({
    config: options.config || EMBEDDED_WALLET_CONFIG,
  });

  return {
    providerId: 'privy_embedded',
    providerLabel: 'Email / Social Wallet',
    providerType: 'embedded_wallet',
    supportsExportInfo: true,
    supportsNativeTransferSigning: true,
    supportsMessageSigning: true,
    supportsPortableWalletPromise: true,
    async initialize() {
      return service.initialize();
    },
    getAvailability() {
      if (typeof service.getAvailability === 'function') {
        return service.getAvailability();
      }
      return service.isConfigured?.() ? 'available' : 'coming_soon';
    },
    getAvailabilityMessage() {
      return typeof service.getUnavailableMessage === 'function'
        ? service.getUnavailableMessage()
        : '';
    },
    isAvailable() {
      return this.getAvailability() === 'available';
    },
    getConnectionStatus() {
      return typeof service.getConnectionStatus === 'function'
        ? service.getConnectionStatus()
        : (this.isAvailable() ? 'ready' : 'unavailable');
    },
    async restoreConnection() {
      return service.restoreConnection({ silent: true });
    },
    async connect(options = {}) {
      return service.connect(options);
    },
    async sendEmailCode(email) {
      return service.sendEmailCode(email);
    },
    async startOAuthLogin(providerId) {
      return service.startOAuthLogin(providerId);
    },
    async getAccounts() {
      return service.getAccounts();
    },
    async getAddress() {
      return service.getAddress();
    },
    async getChainId() {
      return service.getChainId();
    },
    async requestSignature(message, walletAddress) {
      return service.requestSignature(message, walletAddress);
    },
    disconnect() {
      return service.disconnect();
    },
    on() {},
    removeListener() {},
    getPortabilityInfo() {
      return typeof service.getPortabilityInfo === 'function'
        ? service.getPortabilityInfo()
        : {};
    },
    getAuthState() {
      return typeof service.getAuthState === 'function'
        ? service.getAuthState()
        : {};
    },
    getDiagnostics() {
      return typeof service.getDiagnostics === 'function'
        ? service.getDiagnostics()
        : null;
    },
  };
}

export function createWalletProviderRegistry(options = {}) {
  const metaMask = createMetaMaskAdapter({
    getProvider: options.getMetaMaskProvider || options.getProvider,
  });
  const privy = createPrivyEmbeddedWalletAdapter({
    service: options.embeddedWalletService,
    config: options.embeddedWalletConfig || EMBEDDED_WALLET_CONFIG,
  });
  const adapters = [metaMask, privy];

  return {
    listAdapters() {
      return adapters.slice();
    },
    describeAdapters() {
      return adapters.map(buildProviderDescriptor);
    },
    getDefaultAdapter() {
      return metaMask;
    },
    getAdapterById(providerId) {
      return adapters.find((adapter) => adapter.providerId === providerId) || null;
    },
  };
}
