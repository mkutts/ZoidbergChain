import { reactive, readonly } from 'vue';
import { normalizeWalletAddress, shortenWalletAddress } from '../utils/walletAddress.js';

const LAST_CONNECTED_ADDRESS_KEY = 'zoidberg:last-wallet-address';

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
    isConnected: false,
    walletAddress: '',
    normalizedWalletAddress: '',
    chainId: '',
    connectionStatus: 'idle',
    errorMessage: '',
    isVerifiedSession: false,
    lastConnectedAddress: '',
  };
}

function mapWalletError(error) {
  const code = error?.code;
  if (code === 4001) {
    return 'Connection request was rejected in MetaMask.';
  }
  if (code === -32002) {
    return 'A MetaMask connection request is already pending.';
  }
  if (code === 4900 || code === 4901) {
    return 'MetaMask is connected to an unavailable network right now.';
  }
  if (error?.message) {
    return error.message;
  }
  return 'Unable to connect to MetaMask right now.';
}

export function createWalletManager(options = {}) {
  const state = reactive(createInitialState());
  const getProvider = options.getProvider || defaultProviderGetter;
  const storage = options.storage ?? defaultStorage();

  let provider = null;
  let listenersAttached = false;
  let onAccountsChanged = null;
  let onChainChanged = null;
  let onDisconnect = null;

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

  function restorePersistedAddress() {
    if (!storage) {
      return '';
    }
    const saved = storage.getItem(LAST_CONNECTED_ADDRESS_KEY) || '';
    const normalized = normalizeWalletAddress(saved);
    state.lastConnectedAddress = normalized || '';
    return state.lastConnectedAddress;
  }

  function applyDisconnectedState() {
    state.isConnected = false;
    state.walletAddress = '';
    state.normalizedWalletAddress = '';
    state.isVerifiedSession = false;
    state.connectionStatus = state.isMetaMaskAvailable ? 'disconnected' : 'unavailable';
    persistAddress('');
  }

  async function readChainId(activeProvider) {
    if (!activeProvider) {
      return '';
    }
    if (typeof activeProvider.chainId === 'string') {
      return activeProvider.chainId;
    }
    try {
      const chainId = await activeProvider.request({ method: 'eth_chainId' });
      return typeof chainId === 'string' ? chainId : '';
    } catch {
      return '';
    }
  }

  async function syncAccounts(accounts = null) {
    provider = getProvider();
    state.isMetaMaskAvailable = Boolean(provider);

    if (!provider) {
      state.connectionStatus = 'unavailable';
      state.errorMessage = 'MetaMask is not installed or the browser wallet provider is unavailable.';
      applyDisconnectedState();
      return null;
    }

    const nextAccounts = Array.isArray(accounts)
      ? accounts
      : await provider.request({ method: 'eth_accounts' });

    if (!Array.isArray(nextAccounts)) {
      state.connectionStatus = 'error';
      state.errorMessage = 'MetaMask returned an unsupported account response.';
      applyDisconnectedState();
      return null;
    }

    const selectedAddress = nextAccounts[0];
    const normalized = normalizeWalletAddress(selectedAddress);
    state.chainId = await readChainId(provider);

    if (!selectedAddress || !normalized) {
      state.errorMessage = nextAccounts.length > 0
        ? 'MetaMask returned an invalid wallet address.'
        : '';
      applyDisconnectedState();
      return null;
    }

    state.walletAddress = selectedAddress;
    state.normalizedWalletAddress = normalized;
    state.isConnected = true;
    state.connectionStatus = 'connected';
    state.errorMessage = '';
    state.isVerifiedSession = false;
    persistAddress(normalized);
    return normalized;
  }

  function attachProviderListeners() {
    provider = getProvider();
    if (!provider || listenersAttached || typeof provider.on !== 'function') {
      return;
    }

    onAccountsChanged = async (accounts) => {
      try {
        await syncAccounts(accounts);
      } catch (error) {
        state.connectionStatus = 'error';
        state.errorMessage = mapWalletError(error);
        applyDisconnectedState();
      }
    };

    onChainChanged = async (chainId) => {
      state.chainId = typeof chainId === 'string' ? chainId : '';
      state.errorMessage = '';
      state.isVerifiedSession = false;
      if (state.isConnected) {
        state.connectionStatus = 'connected';
      }
    };

    onDisconnect = () => {
      state.errorMessage = 'MetaMask disconnected from this app.';
      applyDisconnectedState();
    };

    provider.on('accountsChanged', onAccountsChanged);
    provider.on('chainChanged', onChainChanged);
    provider.on('disconnect', onDisconnect);
    listenersAttached = true;
  }

  async function detectMetaMask() {
    restorePersistedAddress();
    provider = getProvider();
    state.isMetaMaskAvailable = Boolean(provider);

    if (!provider) {
      state.connectionStatus = 'unavailable';
      state.errorMessage = 'MetaMask is not installed or the browser wallet provider is unavailable.';
      applyDisconnectedState();
      return false;
    }

    attachProviderListeners();
    state.connectionStatus = 'checking';
    await syncAccounts();
    if (!state.isConnected) {
      state.connectionStatus = 'disconnected';
    }
    return state.isMetaMaskAvailable;
  }

  async function connectWallet() {
    provider = getProvider();
    state.isMetaMaskAvailable = Boolean(provider);

    if (!provider) {
      state.connectionStatus = 'unavailable';
      state.errorMessage = 'MetaMask is not installed. Install MetaMask to connect a wallet.';
      return null;
    }

    attachProviderListeners();
    state.connectionStatus = 'connecting';
    state.errorMessage = '';

    try {
      const accounts = await provider.request({ method: 'eth_requestAccounts' });
      const normalized = await syncAccounts(accounts);
      if (!normalized) {
        state.connectionStatus = 'error';
        state.errorMessage = 'MetaMask did not return a usable wallet address.';
      }
      return normalized;
    } catch (error) {
      applyDisconnectedState();
      state.connectionStatus = 'error';
      state.errorMessage = mapWalletError(error);
      return null;
    }
  }

  function disconnectWallet() {
    state.errorMessage = '';
    state.chainId = '';
    applyDisconnectedState();
  }

  function handleAccountsChanged(accounts) {
    return onAccountsChanged ? onAccountsChanged(accounts) : syncAccounts(accounts);
  }

  function handleChainChanged(chainId) {
    if (onChainChanged) {
      return onChainChanged(chainId);
    }
    state.chainId = typeof chainId === 'string' ? chainId : '';
    state.isVerifiedSession = false;
    return state.chainId;
  }

  return {
    state: readonly(state),
    detectMetaMask,
    connectWallet,
    disconnectWallet,
    normalizeAddress: normalizeWalletAddress,
    shortenAddress: shortenWalletAddress,
    handleAccountsChanged,
    handleChainChanged,
  };
}

const walletManager = createWalletManager();

export function useWallet() {
  return walletManager;
}
