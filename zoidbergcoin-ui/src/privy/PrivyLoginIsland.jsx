import { useEffect, useMemo } from 'react';
import {
  PrivyProvider,
  useLogin,
  usePrivy,
  useSignMessage,
  useWallets,
} from '../../node_modules/@privy-io/react-auth/dist/esm/index.mjs';

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

function PrivyLoginController({ onReady, onStateChange, onError }) {
  const { ready, authenticated, user, logout } = usePrivy();
  const { wallets, ready: walletsReady } = useWallets();
  const { signMessage } = useSignMessage();
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
      async connect() {
        return login();
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
      async signMessage(message) {
        if (!activeWallet?.address) {
          throw new Error('Privy did not return an embedded wallet address.');
        }
        const result = await signMessage(
          { message },
          { address: activeWallet.address },
        );
        return result?.signature || result;
      },
    });
  }, [activeWallet?.address, authenticated, login, logout, onReady, ready, signMessage, user, walletsReady]);

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
      clientId={clientId}
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
