import { normalizeWalletAddress } from '../utils/walletAddress.js';
import { createMetaMaskAdapter } from './walletProviderAdapter.js';

export const TRANSFER_PENDING_WARNING = 'This signs a native ZOID transfer on ZoidbergChain. Pending outgoing transfers reduce available balance. Final balance changes only when a transfer is settled in a meme-mined block.';

function parseDecimalToMicroUnits(value) {
  const candidate = String(value || '').trim();
  if (!/^\d+(\.\d{1,6})?$/.test(candidate)) {
    throw new Error('Amount must be a positive decimal with up to 6 decimal places.');
  }
  const [wholePart, fractionalPart = ''] = candidate.split('.');
  return BigInt(wholePart) * 1000000n + BigInt(fractionalPart.padEnd(6, '0'));
}

export function validateNativeTransferDraft({ fromAddress, toAddress, amount, memo = '', availableBalance = null }) {
  const normalizedFrom = normalizeWalletAddress(fromAddress);
  if (!normalizedFrom) {
    throw new Error('Verified from address is missing or invalid.');
  }

  const normalizedTo = normalizeWalletAddress(toAddress);
  if (!normalizedTo) {
    throw new Error('Recipient wallet must be a valid 0x address.');
  }
  if (normalizedTo === normalizedFrom) {
    throw new Error('Recipient wallet must be different from the verified wallet.');
  }

  const normalizedAmount = String(amount || '').trim();
  if (!/^\d+(\.\d{1,6})?$/.test(normalizedAmount)) {
    throw new Error('Amount must be a positive decimal with up to 6 decimal places.');
  }
  if (/^0+(\.0+)?$/.test(normalizedAmount)) {
    throw new Error('Amount must be greater than zero.');
  }
  if (availableBalance !== null && availableBalance !== undefined && String(availableBalance).trim() !== '') {
    const availableMicroUnits = parseDecimalToMicroUnits(String(availableBalance).trim());
    const amountMicroUnits = parseDecimalToMicroUnits(normalizedAmount);
    if (amountMicroUnits > availableMicroUnits) {
      throw new Error(`Amount exceeds available balance of ${String(availableBalance).trim()} ZOID.`);
    }
  }

  const normalizedMemo = String(memo || '').trim();
  if (normalizedMemo.length > 280) {
    throw new Error('Memo must be 280 characters or fewer.');
  }

  return {
    fromAddress: normalizedFrom,
    toAddress: normalizedTo,
    amount: normalizedAmount,
    fee: '0',
    memo: normalizedMemo,
  };
}

export function createNativeTransferService(options = {}) {
  const api = options.api;
  const walletAdapter = options.walletAdapter || createMetaMaskAdapter({
    getProvider: options.getProvider,
  });
  const getApiErrorMessage = options.getApiErrorMessage || ((error, fallback) => error?.message || fallback);

  return {
    async submitSignedTransferIntent({ fromAddress, walletAddressForSigning, toAddress, amount, memo = '', availableBalance = null }) {
      if (!walletAdapter.isAvailable()) {
        throw new Error(`${walletAdapter.providerLabel} is not available in this browser.`);
      }

      const draft = validateNativeTransferDraft({
        fromAddress,
        toAddress,
        amount,
        memo,
        availableBalance,
      });

      try {
        const challengeResponse = await api.post('/auth/wallet/transfer-challenge', {
          from_address: draft.fromAddress,
          to_address: draft.toAddress,
          amount: draft.amount,
          fee: draft.fee,
          memo: draft.memo || null,
        });
        const challenge = challengeResponse.data;
        const signature = await walletAdapter.requestSignature(challenge.message, walletAddressForSigning);
        const submitResponse = await api.post('/transfers/submit', {
          from_address: draft.fromAddress,
          to_address: draft.toAddress,
          amount: draft.amount,
          fee: draft.fee,
          memo: draft.memo || null,
          message: challenge.message,
          signature,
        });
        return submitResponse.data;
      } catch (error) {
        if (error?.code === 4001) {
          throw new Error(`Signature request was rejected in ${walletAdapter.providerLabel}.`);
        }
        throw new Error(getApiErrorMessage(error, 'Native transfer intent submission failed.'));
      }
    },
  };
}
