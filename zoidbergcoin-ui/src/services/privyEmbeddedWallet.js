import { EMBEDDED_WALLET_CONFIG } from '../utils/embeddedWalletConfig.js';

const PRIVY_COMING_SOON_MESSAGE = 'Email / Social Wallet is coming soon in this browser. MetaMask is still the only supported login method right now.';
const PRIVY_REACT_ISLAND_REQUIRED_MESSAGE = 'Email / Social Wallet is coming soon. Privy\'s supported web integration path for this Vue app is a small React island, so MetaMask remains the only live login until that path is implemented.';
const PRIVY_MISSING_APP_ID_MESSAGE = 'Embedded wallet setup is missing a public Privy app id.';
const PRIVY_PROVIDER_DISABLED_MESSAGE = 'Embedded wallet provider is disabled for this deployment.';

function buildDiagnostics(config = {}, lastErrorMessage = '') {
  const providerName = String(config?.provider || '').trim();
  const providerConfigured = Boolean(config?.isPrivySelected);
  const appIdPresent = Boolean(config?.privyAppId);
  const providerDisabled = !providerConfigured;
  const missingAppId = providerConfigured && !appIdPresent;
  const unavailableReason = providerDisabled
    ? 'provider_disabled'
    : (missingAppId ? 'missing_app_id' : 'react_sdk_required');

  return {
    providerConfigured,
    appIdPresent,
    providerName,
    sdkImportAttempted: false,
    sdkImportSucceeded: false,
    initAttempted: false,
    initSucceeded: false,
    unavailableReason,
    lastErrorMessage,
  };
}

function buildUnavailableMessage(config = {}) {
  const diagnostics = buildDiagnostics(config);
  switch (diagnostics.unavailableReason) {
    case 'provider_disabled':
      return PRIVY_PROVIDER_DISABLED_MESSAGE;
    case 'missing_app_id':
      return PRIVY_MISSING_APP_ID_MESSAGE;
    case 'react_sdk_required':
      return PRIVY_REACT_ISLAND_REQUIRED_MESSAGE;
    default:
      return PRIVY_COMING_SOON_MESSAGE;
  }
}

function buildUnavailableError(config = {}) {
  const error = new Error(buildUnavailableMessage(config));
  error.code = 'privy_integration_deferred';
  error.privyUnavailableReason = buildDiagnostics(config).unavailableReason;
  return error;
}

export async function loadPrivySdk() {
  return null;
}

export function createPrivyEmbeddedWalletService(options = {}) {
  const config = options.config || EMBEDDED_WALLET_CONFIG;

  function getDiagnostics() {
    return buildDiagnostics(config);
  }

  function getAvailability() {
    return 'coming_soon';
  }

  function getUnavailableMessage() {
    return buildUnavailableMessage(config);
  }

  function throwUnavailable() {
    throw buildUnavailableError(config);
  }

  return {
    async initialize() {
      return false;
    },
    getAvailability,
    getUnavailableMessage,
    getDiagnostics,
    getConnectionStatus() {
      return 'coming_soon';
    },
    isConfigured() {
      return Boolean(config?.isConfigured);
    },
    async restoreConnection() {
      return [];
    },
    async connect() {
      throwUnavailable();
    },
    async sendEmailCode() {
      throwUnavailable();
    },
    async startOAuthLogin() {
      throwUnavailable();
    },
    async getAccounts() {
      return [];
    },
    async getAddress() {
      return '';
    },
    async getChainId() {
      return '';
    },
    async requestSignature() {
      throwUnavailable();
    },
    async disconnect() {},
    getPortabilityInfo() {
      return {
        helpUrl: config?.portabilityHelpUrl || '',
        helpCopy: config?.portabilityHelpCopy || '',
      };
    },
    getAuthState() {
      return {
        isAuthenticated: false,
        method: 'none',
      };
    },
  };
}
