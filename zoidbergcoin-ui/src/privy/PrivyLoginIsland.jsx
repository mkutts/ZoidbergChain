import React, { useEffect, useMemo } from 'react';
import {
  PrivyProvider,
  useLogin,
  usePrivy,
  useSignMessage,
  useWallets,
} from '@privy-io/react-auth';

function buildSafeLoginMetadata(user) {
  if (!user || typeof user !== 'object') {
    return null;
  }
  const linkedAccounts = Array.isArray(user.linkedAccounts) ? user.linkedAccounts : [];
  return {
    userId: typeof user.id === 'string' ? user.id : '',
    linkedAccountTypes: linkedAccounts
      .map((account) => String(account?.type || '').trim())
      .filter(Boolean),
  };
}

function pickPrivyWallet(wallets = []) {
  return wallets.find((wallet) => wallet?.walletClientType === 'privy')
    || wallets.find((wallet) => wallet?.connectorType === 'embedded')
    || wallets[0]
    || null;
}

function extractSignatureValue(result) {
  if (result == null) {
    return '';
  }
  if (typeof result === 'string') {
    return result;
  }
  if (typeof result?.signature === 'string') {
    return result.signature;
  }
  if (typeof result?.rawSignature === 'string') {
    return result.rawSignature;
  }
  if (typeof result?.data?.signature === 'string') {
    return result.data.signature;
  }
  if (typeof result?.result?.signature === 'string') {
    return result.result.signature;
  }
  return '';
}

function PrivyLoginController({ onReady, onStateChange, onError }) {
  const { ready, authenticated, user, logout } = usePrivy();
  const { wallets, ready: walletsReady } = useWallets();
  const { signMessage: usePrivySignMessage } = useSignMessage();
  const { login } = useLogin({
    onError(error) {
      onError?.(error);
    },
  });

  const activeWallet = useMemo(() => pickPrivyWallet(wallets), [wallets]);

  useEffect(() => {
    onStateChange?.({
      ready: Boolean(ready && walletsReady),
      authenticated,
      walletAddress: activeWallet?.address || '',
      loginMetadata: buildSafeLoginMetadata(user),
    });
  }, [activeWallet?.address, authenticated, onStateChange, ready, user, walletsReady]);

  useEffect(() => {
    onReady?.({
      async connect(options = {}) {
        const loginOptions = {};
        if (options?.disableSignup === true) {
          loginOptions.disableSignup = true;
        }
        if (Array.isArray(options?.loginMethods) && options.loginMethods.length > 0) {
          loginOptions.loginMethods = options.loginMethods;
        }
        return login(loginOptions);
      },
      async disconnect() {
        return logout();
      },
      getState() {
        return {
          ready: Boolean(ready && walletsReady),
          authenticated,
          walletAddress: activeWallet?.address || '',
          loginMetadata: buildSafeLoginMetadata(user),
        };
      },
      async signMessage(message, walletAddress = '') {
        const targetAddress = String(walletAddress || activeWallet?.address || '').trim();
        if (!targetAddress) {
          throw new Error('Privy did not return an embedded wallet address.');
        }

        if (typeof activeWallet?.signMessage === 'function') {
          const result = await activeWallet.signMessage({ message, address: targetAddress });
          const signature = extractSignatureValue(result);
          if (signature) {
            return signature;
          }
          throw new Error('Privy embedded wallet did not return a signature value.');
        }

        if (typeof usePrivySignMessage === 'function') {
          const result = await usePrivySignMessage(
            { message },
            { address: targetAddress },
          );
          const signature = extractSignatureValue(result);
          if (signature) {
            return signature;
          }
          throw new Error('Privy signMessage hook did not return a signature value.');
        }

        throw new Error('Privy embedded wallet does not expose a signing method.');
      },
    });
  }, [activeWallet, authenticated, login, logout, onReady, ready, usePrivySignMessage, user, walletsReady]);

  return null;
}

export default function PrivyLoginIsland({
  appId,
  clientId,
  onReady,
  onStateChange,
  onError,
}) {
  return (
    <PrivyProvider
      appId={appId}
      clientId={clientId || undefined}
      config={{
        embeddedWallets: {
          ethereum: {
            createOnLogin: 'users-without-wallets',
          },
        },
      }}
    >
      <PrivyLoginController
        onReady={onReady}
        onStateChange={onStateChange}
        onError={onError}
      />
    </PrivyProvider>
  );
}
