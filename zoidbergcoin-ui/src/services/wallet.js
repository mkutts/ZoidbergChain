import { reactive, readonly } from 'vue';
import { normalizeWalletAddress, shortenWalletAddress } from '../utils/walletAddress.js';
import { apiClient, configureWalletApiAuth, getApiErrorMessage } from '../config/api.js';
import { createWalletProviderRegistry } from './walletProviderAdapter.js';

const LAST_CONNECTED_ADDRESS_KEY = 'zoidberg:last-wallet-address';
const LAST_CONNECTED_PROVIDER_KEY = 'zoidberg:last-wallet-provider';
const VERIFIED_SESSION_KEY = 'zoidberg:verified-wallet-session';

function defaultProviderGetter() {
  if (typeof window === 'undefined') {
    return null;
  }
  return window.ethereum || null;
}

function defaultStorage() {
  if (typeof window === 'undefined') {
    return null;
  }
  try {
    return window.localStorage || null;
  } catch {
    return null;
  }
}

function createInitialState() {
  return {
    isMetaMaskAvailable: false,
    isWalletProviderAvailable: false,
    isConnected: false,
    walletAddress: '',
    connectedWalletAddress: '',
    normalizedWalletAddress: '',
    chainId: '',
    connectionStatus: 'idle',
    errorMessage: '',
    isVerifiedSession: false,
    lastConnectedAddress: '',
    lastConnectedProviderId: 'metamask',
    sessionToken: '',
    sessionExpiresAt: '',
    verifiedWalletAddress: '',
    identitySource: 'none',
    providerId: 'metamask',
    providerLabel: 'MetaMask',
    providerType: 'injected_wallet',
    availableWalletProviders: [],
    portabilityHelpUrl: '',
    portabilityHelpCopy: '',
    supportsNativeTransferSigning: true,
    supportsMessageSigning: true,
    supportsExportInfo: true,
    authError: '',
    connected_wallet_address: '',
    normalized_wallet_address: '',
    is_connected: false,
    is_verified_session: false,
    session_token: '',
    session_expires_at: '',
    verified_wallet_address: '',
    identity_source: 'none',
    provider_id: 'metamask',
    auth_error: '',
  };
}

function mapWalletError(error, providerLabel = 'wallet provider') {
  const code = error?.code;
  if (code === 4001) {
    return `Connection request was rejected in ${providerLabel}.`;
  }
  if (code === -32002) {
    return `A ${providerLabel} connection request is already pending.`;
  }
  if (code === 4900 || code === 4901) {
    return `${providerLabel} is connected to an unavailable network right now.`;
  }
  if (error?.message) {
    return error.message;
  }
  return `Unable to connect to ${providerLabel} right now.`;
}

export function createWalletManager(options = {}) {
  const state = reactive(createInitialState());
  const storage = options.storage ?? defaultStorage();
  const walletProviderRegistry = options.walletProviderRegistry || createWalletProviderRegistry({
    getProvider: options.getProvider || defaultProviderGetter,
    embeddedWalletService: options.embeddedWalletService,
    embeddedWalletConfig: options.embeddedWalletConfig,
  });
  const authApi = options.authApi || {
    async createChallenge(walletAddress) {
      const response = await apiClient.post('/auth/wallet/challenge', { wallet_address: walletAddress });
      return response.data;
    },
    async verifyChallenge(payload) {
      const response = await apiClient.post('/auth/wallet/verify', payload);
      return response.data;
    },
    async getSession() {
      const response = await apiClient.get('/auth/wallet/session');
      return response.data;
    },
    async logout() {
      const response = await apiClient.post('/auth/wallet/logout');
      return response.data;
    },
  };

  let activeAdapter = walletProviderRegistry.getDefaultAdapter();
  let listenersAttached = false;
  let onAccountsChanged = null;
  let onChainChanged = null;
  let onDisconnect = null;

  function syncAvailableProviders() {
    state.availableWalletProviders = walletProviderRegistry.describeAdapters();
    const activeProviderRecord = state.availableWalletProviders.find((item) => item.provider_id === activeAdapter.providerId) || null;
    state.portabilityHelpUrl = activeProviderRecord?.portability_help_url || '';
    state.portabilityHelpCopy = activeProviderRecord?.portability_help_copy || '';
    state.supportsNativeTransferSigning = activeProviderRecord?.supports_native_transfer_signing !== false;
    state.supportsMessageSigning = activeProviderRecord?.supports_message_signing !== false;
    state.supportsExportInfo = Boolean(activeProviderRecord?.supports_export_info);
  }

  function syncProviderFields() {
    state.providerId = activeAdapter.providerId;
    state.providerLabel = activeAdapter.providerLabel;
    state.providerType = activeAdapter.providerType;
    state.provider_id = activeAdapter.providerId;
    state.isMetaMaskAvailable = Boolean(walletProviderRegistry.getAdapterById('metamask')?.isAvailable());
    state.isWalletProviderAvailable = activeAdapter.isAvailable();
    syncAvailableProviders();
  }

  function syncIdentityFields() {
    state.connectedWalletAddress = state.walletAddress;
    state.connected_wallet_address = state.walletAddress;
    state.normalized_wallet_address = state.normalizedWalletAddress;
    state.is_connected = state.isConnected;
    state.is_verified_session = state.isVerifiedSession;
    state.session_token = state.sessionToken;
    state.session_expires_at = state.sessionExpiresAt;
    state.verified_wallet_address = state.verifiedWalletAddress;
    state.identity_source = state.identitySource;
    state.provider_id = state.providerId;
    state.auth_error = state.authError;
  }

  function setIdentitySource() {
    if (state.isVerifiedSession && state.verifiedWalletAddress && state.providerId) {
      state.identitySource = `${state.providerId}_verified`;
    } else if (state.isConnected && state.normalizedWalletAddress && state.providerId) {
      state.identitySource = `${state.providerId}_unverified`;
    } else {
      state.identitySource = 'none';
    }
  }

  function persistAddress(address) {
    state.lastConnectedAddress = address || '';
    if (!storage) {
      return;
    }
    if (!address) {
      storage.removeItem(LAST_CONNECTED_ADDRESS_KEY);
      return;
    }
    storage.setItem(LAST_CONNECTED_ADDRESS_KEY, address);
  }

  function persistProviderId(providerId) {
    state.lastConnectedProviderId = providerId || 'metamask';
    if (!storage) {
      return;
    }
    if (!providerId) {
      storage.removeItem(LAST_CONNECTED_PROVIDER_KEY);
      return;
    }
    storage.setItem(LAST_CONNECTED_PROVIDER_KEY, providerId);
  }

  function restorePersistedAddress() {
    if (!storage) {
      return '';
    }
    const saved = storage.getItem(LAST_CONNECTED_ADDRESS_KEY) || '';
    const normalized = normalizeWalletAddress(saved);
    state.lastConnectedAddress = normalized || '';
    return state.lastConnectedAddress;
  }

  function restorePersistedProviderId() {
    const fallback = 'metamask';
    if (!storage) {
      state.lastConnectedProviderId = fallback;
      return fallback;
    }
    const saved = String(storage.getItem(LAST_CONNECTED_PROVIDER_KEY) || '').trim();
    const adapter = walletProviderRegistry.getAdapterById(saved);
    state.lastConnectedProviderId = adapter?.providerId || fallback;
    return state.lastConnectedProviderId;
  }

  function sessionIsExpired(expiresAt) {
    if (!expiresAt) {
      return true;
    }
    const parsed = Date.parse(expiresAt);
    if (Number.isNaN(parsed)) {
      return true;
    }
    return parsed <= Date.now();
  }

  function persistVerifiedSession(session) {
    state.sessionToken = session?.sessionToken || '';
    state.sessionExpiresAt = session?.expiresAt || '';
    state.isVerifiedSession = Boolean(session?.sessionToken && !sessionIsExpired(session?.expiresAt));
    state.verifiedWalletAddress = state.isVerifiedSession ? state.normalizedWalletAddress : '';
    setIdentitySource();
    syncIdentityFields();

    if (!storage) {
      return;
    }
    if (!state.isVerifiedSession || !state.normalizedWalletAddress || !state.providerId) {
      storage.removeItem(VERIFIED_SESSION_KEY);
      return;
    }
    storage.setItem(
      VERIFIED_SESSION_KEY,
      JSON.stringify({
        walletAddress: state.normalizedWalletAddress,
        providerId: state.providerId,
        sessionToken: state.sessionToken,
        expiresAt: state.sessionExpiresAt,
      }),
    );
  }

  function clearVerifiedSession(reason = '') {
    persistVerifiedSession(null);
    state.authError = reason || '';
    if (reason) {
      state.connectionStatus = 'expired';
    }
    syncIdentityFields();
  }

  async function restoreVerifiedSession() {
    if (!storage || !state.providerId || !state.normalizedWalletAddress) {
      return;
    }
    const raw = storage.getItem(VERIFIED_SESSION_KEY);
    if (!raw) {
      return;
    }
    try {
      const parsed = JSON.parse(raw);
      const normalized = normalizeWalletAddress(parsed.walletAddress);
      if (
        !normalized
        || sessionIsExpired(parsed.expiresAt)
        || normalized !== state.normalizedWalletAddress
        || String(parsed.providerId || '') !== state.providerId
      ) {
        state.connectionStatus = 'expired';
        clearVerifiedSession('Session expired - verify again.');
        return;
      }
      persistVerifiedSession({ sessionToken: parsed.sessionToken, expiresAt: parsed.expiresAt });
      try {
        const session = await authApi.getSession();
        state.isVerifiedSession = Boolean(session.valid);
        state.verifiedWalletAddress = session.normalized_wallet_address || normalized;
        state.sessionExpiresAt = session.expires_at || parsed.expiresAt;
        state.authError = '';
        setIdentitySource();
        syncIdentityFields();
      } catch (error) {
        state.connectionStatus = 'expired';
        clearVerifiedSession(getApiErrorMessage(error, 'Session expired - verify again.'));
      }
    } catch {
      clearVerifiedSession();
    }
  }

  async function readChainId(adapter) {
    try {
      return await adapter.getChainId();
    } catch {
      return '';
    }
  }

  function detachProviderListeners() {
    if (!listenersAttached) {
      return;
    }
    activeAdapter.removeListener?.('accountsChanged', onAccountsChanged);
    activeAdapter.removeListener?.('chainChanged', onChainChanged);
    activeAdapter.removeListener?.('disconnect', onDisconnect);
    listenersAttached = false;
    onAccountsChanged = null;
    onChainChanged = null;
    onDisconnect = null;
  }

  function attachProviderListeners() {
    if (listenersAttached) {
      return;
    }
    onAccountsChanged = async (accounts) => {
      try {
        if (state.sessionToken) {
          await authApi.logout();
        }
        await syncAccountsForAdapter(activeAdapter, accounts);
      } catch (error) {
        state.connectionStatus = 'error';
        state.errorMessage = mapWalletError(error, activeAdapter.providerLabel);
        await applyDisconnectedState();
      }
    };

    onChainChanged = async (chainId) => {
      state.chainId = typeof chainId === 'string' ? chainId : '';
      state.errorMessage = '';
      if (state.sessionToken) {
        await authApi.logout();
      }
      clearVerifiedSession('Network changed - verify again.');
      if (state.isConnected) {
        state.connectionStatus = 'connected';
      }
    };

    onDisconnect = async () => {
      state.errorMessage = `${activeAdapter.providerLabel} disconnected from this app.`;
      await applyDisconnectedState();
    };

    activeAdapter.on?.('accountsChanged', onAccountsChanged);
    activeAdapter.on?.('chainChanged', onChainChanged);
    activeAdapter.on?.('disconnect', onDisconnect);
    listenersAttached = true;
  }

  async function setActiveProvider(providerId) {
    const nextAdapter = walletProviderRegistry.getAdapterById(providerId) || walletProviderRegistry.getDefaultAdapter();
    if (nextAdapter.providerId === activeAdapter.providerId) {
      syncProviderFields();
      return activeAdapter;
    }
    detachProviderListeners();
    activeAdapter = nextAdapter;
    persistProviderId(activeAdapter.providerId);
    syncProviderFields();
    return activeAdapter;
  }

  async function applyDisconnectedState() {
    state.isConnected = false;
    state.walletAddress = '';
    state.connectedWalletAddress = '';
    state.normalizedWalletAddress = '';
    state.chainId = '';
    clearVerifiedSession();
    state.authError = '';
    state.connectionStatus = activeAdapter.isAvailable() ? 'disconnected' : 'idle';
    persistAddress('');
    persistProviderId(activeAdapter.providerId);
    syncProviderFields();
    setIdentitySource();
    syncIdentityFields();
  }

  async function syncAccountsForAdapter(adapter, accounts = null) {
    activeAdapter = adapter;
    syncProviderFields();
    const nextAccounts = Array.isArray(accounts)
      ? accounts
      : await adapter.getAccounts();

    if (!Array.isArray(nextAccounts)) {
      state.connectionStatus = 'error';
      state.errorMessage = `${adapter.providerLabel} returned an unsupported account response.`;
      await applyDisconnectedState();
      return null;
    }

    const selectedAddress = nextAccounts[0];
    const normalized = normalizeWalletAddress(selectedAddress);
    state.chainId = await readChainId(adapter);

    if (!selectedAddress || !normalized) {
      state.errorMessage = '';
      await applyDisconnectedState();
      return null;
    }

    state.walletAddress = selectedAddress;
    state.connectedWalletAddress = selectedAddress;
    state.normalizedWalletAddress = normalized;
    state.isConnected = true;
    state.connectionStatus = 'connected';
    state.errorMessage = '';
    state.authError = '';
    state.verifiedWalletAddress = '';
    persistAddress(normalized);
    persistProviderId(adapter.providerId);
    await restoreVerifiedSession();
    setIdentitySource();
    syncIdentityFields();
    attachProviderListeners();
    return normalized;
  }

  async function detectWallets() {
    restorePersistedAddress();
    const restoredProviderId = restorePersistedProviderId();
    const preferred = walletProviderRegistry.getAdapterById(restoredProviderId) || walletProviderRegistry.getDefaultAdapter();
    const defaultAdapter = walletProviderRegistry.getDefaultAdapter();
    const adapters = [
      preferred,
      ...walletProviderRegistry.listAdapters().filter(
        (adapter) => adapter.providerId !== preferred.providerId
          && adapter.providerId === defaultAdapter.providerId,
      ),
    ];

    for (const adapter of adapters) {
      try {
        const restoredAccounts = await adapter.restoreConnection?.();
        if (Array.isArray(restoredAccounts) && restoredAccounts.length > 0) {
          await setActiveProvider(adapter.providerId);
          await syncAccountsForAdapter(adapter, restoredAccounts);
          return true;
        }
      } catch {
        // Ignore restore failures while scanning providers.
      }
    }

    await setActiveProvider(restoredProviderId);
    syncProviderFields();
    state.connectionStatus = activeAdapter.isAvailable() ? 'disconnected' : 'idle';
    state.errorMessage = '';
    state.authError = '';
    syncIdentityFields();
    return false;
  }

  async function connectWallet(options = {}) {
    const providerId = options.providerId || state.providerId || 'metamask';
    const adapter = await setActiveProvider(providerId);
    syncProviderFields();
    state.connectionStatus = 'connecting';
    state.errorMessage = '';
    state.authError = '';

    try {
      const accounts = await adapter.connect(options);
      if (!Array.isArray(accounts) || accounts.length === 0) {
        state.connectionStatus = adapter.getConnectionStatus();
        return null;
      }
      return syncAccountsForAdapter(adapter, accounts);
    } catch (error) {
      await applyDisconnectedState();
      state.connectionStatus = 'error';
      state.errorMessage = mapWalletError(error, adapter.providerLabel);
      return null;
    }
  }

  async function sendEmbeddedWalletEmailCode(email) {
    const adapter = await setActiveProvider('privy_embedded');
    if (typeof adapter.sendEmailCode !== 'function') {
      throw new Error('Embedded wallet email login is not available.');
    }
    return adapter.sendEmailCode(email);
  }

  async function startEmbeddedWalletOAuthLogin(providerId = '') {
    const adapter = await setActiveProvider('privy_embedded');
    if (typeof adapter.startOAuthLogin !== 'function') {
      throw new Error('Embedded wallet social login is not available.');
    }
    return adapter.startOAuthLogin(providerId);
  }

  async function disconnectWallet() {
    state.errorMessage = '';
    state.chainId = '';
    if (state.sessionToken) {
      try {
        await authApi.logout();
      } catch {
        // Ignore logout errors during local state cleanup.
      }
    }
    try {
      await activeAdapter.disconnect?.();
    } catch {
      // Ignore provider logout failures during app disconnect.
    }
    await applyDisconnectedState();
  }

  async function verifyWallet() {
    if (!state.isConnected || !state.normalizedWalletAddress) {
      state.errorMessage = `Connect ${activeAdapter.providerLabel} before verifying this wallet.`;
      return null;
    }

    state.connectionStatus = 'verifying';
    state.errorMessage = '';
    state.authError = '';
    clearVerifiedSession();

    try {
      const challenge = await authApi.createChallenge(state.normalizedWalletAddress);
      const signature = await activeAdapter.requestSignature(challenge.message, state.walletAddress);
      const verification = await authApi.verifyChallenge({
        wallet_address: state.normalizedWalletAddress,
        message: challenge.message,
        signature,
        provider_id: state.providerId,
      });

      persistVerifiedSession({
        sessionToken: verification.session_token,
        expiresAt: verification.expires_at,
      });
      state.connectionStatus = 'verified';
      state.errorMessage = '';
      state.authError = '';
      state.verifiedWalletAddress = verification.normalized_wallet_address || state.normalizedWalletAddress;
      setIdentitySource();
      syncIdentityFields();
      return verification;
    } catch (error) {
      state.connectionStatus = 'error';
      clearVerifiedSession();
      if (error?.code === 4001) {
        state.errorMessage = `Signature request was rejected in ${activeAdapter.providerLabel}.`;
      } else {
        state.errorMessage = getApiErrorMessage(error, 'Wallet verification failed.');
      }
      state.authError = state.errorMessage;
      syncIdentityFields();
      return null;
    }
  }

  async function requestSignature(message, walletAddress = '') {
    if (!state.isConnected || !state.walletAddress) {
      throw new Error(`Connect ${activeAdapter.providerLabel} before requesting a signature.`);
    }
    return activeAdapter.requestSignature(message, walletAddress || state.walletAddress);
  }

  function handleAccountsChanged(accounts) {
    return onAccountsChanged ? onAccountsChanged(accounts) : syncAccountsForAdapter(activeAdapter, accounts);
  }

  function handleChainChanged(chainId) {
    if (onChainChanged) {
      return onChainChanged(chainId);
    }
    state.chainId = typeof chainId === 'string' ? chainId : '';
    clearVerifiedSession('Network changed - verify again.');
    return state.chainId;
  }

  function clearSessionFromUnauthorized(error) {
    state.connectionStatus = 'expired';
    state.errorMessage = '';
    clearVerifiedSession(getApiErrorMessage(error, 'Session expired - verify again.'));
  }

  configureWalletApiAuth({
    getAuthHeaders() {
      if (!state.isVerifiedSession || !state.sessionToken || sessionIsExpired(state.sessionExpiresAt)) {
        return {};
      }
      return { Authorization: `Bearer ${state.sessionToken}` };
    },
    onSessionUnauthorized(error) {
      clearSessionFromUnauthorized(error);
    },
  });

  syncProviderFields();

  return {
    state: readonly(state),
    detectMetaMask: detectWallets,
    detectWallets,
    connectWallet,
    disconnectWallet,
    verifyWallet,
    requestSignature,
    sendEmbeddedWalletEmailCode,
    startEmbeddedWalletOAuthLogin,
    setActiveProvider,
    handleAccountsChanged,
    handleChainChanged,
    normalizeAddress: normalizeWalletAddress,
    shortenAddress: shortenWalletAddress,
    getAuthorizationHeader() {
      if (!state.isVerifiedSession || !state.sessionToken || sessionIsExpired(state.sessionExpiresAt)) {
        return {};
      }
      return { Authorization: `Bearer ${state.sessionToken}` };
    },
    async refreshVerifiedSession() {
      if (!state.sessionToken || !state.normalizedWalletAddress) {
        clearVerifiedSession();
        return null;
      }
      try {
        const session = await authApi.getSession();
        state.isVerifiedSession = Boolean(session.valid);
        state.verifiedWalletAddress = session.normalized_wallet_address || state.normalizedWalletAddress;
        state.sessionExpiresAt = session.expires_at || state.sessionExpiresAt;
        state.connectionStatus = state.isVerifiedSession ? 'verified' : 'expired';
        state.authError = '';
        setIdentitySource();
        syncIdentityFields();
        return session;
      } catch (error) {
        clearSessionFromUnauthorized(error);
        return null;
      }
    },
    async refreshEmbeddedWalletStatus() {
      syncAvailableProviders();
      const adapter = walletProviderRegistry.getAdapterById('privy_embedded');
      return Boolean(adapter?.isAvailable());
    },
    getConnectedProvider() {
      return {
        provider_id: state.providerId,
        provider_label: state.providerLabel,
        provider_type: state.providerType,
      };
    },
  };
}

const walletManager = createWalletManager();

export function useWallet() {
  return walletManager;
}
