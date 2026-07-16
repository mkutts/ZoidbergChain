import test from 'node:test';
import assert from 'node:assert/strict';

import {
  buildNativeBalanceSummary,
  buildRewardSummary,
  describeTransferIntentDirection,
  describeTransferIntentStatus,
  formatTransferIntentTimestamp,
} from './nativeWalletUi.js';

test('buildNativeBalanceSummary keeps final balance visible and does not require pending fields', () => {
  const rows = buildNativeBalanceSummary({
    native_balance: '15',
    symbol: 'ZOID',
  });

  assert.deepEqual(rows, [
    {
      label: 'Final Native ZOID Balance',
      value: '15 ZOID',
    },
  ]);
});

test('buildNativeBalanceSummary includes pending and available values when present', () => {
  const rows = buildNativeBalanceSummary({
    native_balance: '15',
    pending_outgoing: '10',
    available_balance: '15',
    symbol: 'ZOID',
  });

  assert.equal(rows.length, 3);
  assert.equal(rows[1].label, 'Pending Outgoing');
  assert.equal(rows[2].label, 'Available Balance');
});

test('describeTransferIntentDirection detects outgoing and incoming transfer history', () => {
  assert.equal(
    describeTransferIntentDirection(
      {
        from_address: '0x1111111111111111111111111111111111111111',
        to_address: '0x2222222222222222222222222222222222222222',
      },
      '0x1111111111111111111111111111111111111111',
    ),
    'Outgoing',
  );

  assert.equal(
    describeTransferIntentDirection(
      {
        from_address: '0x1111111111111111111111111111111111111111',
        to_address: '0x2222222222222222222222222222222222222222',
      },
      '0x2222222222222222222222222222222222222222',
    ),
    'Incoming',
  );
});

test('describeTransferIntentStatus keeps signed pending copy non-final', () => {
  assert.equal(describeTransferIntentStatus('signed_pending'), 'Signed transfer intent');
  assert.equal(describeTransferIntentStatus('mempool'), 'Pending transaction processing');
});

test('formatTransferIntentTimestamp prefers signed timestamp', () => {
  assert.equal(
    formatTransferIntentTimestamp({
      signed_at: '2026-07-16T01:00:00+00:00',
      created_at: '2026-07-16T00:00:00+00:00',
    }),
    '2026-07-16T01:00:00+00:00',
  );
});

test('buildRewardSummary exposes reward history fields cleanly', () => {
  const summary = buildRewardSummary({
    reward_amount: 5,
    reward_type: 'meme_mining_reward',
    submission_id: 'submission-1',
    certificate_id: 'certificate-1',
    block_height: 12,
    block_hash: 'hash-1',
    minted_at: '2026-07-16T00:00:00+00:00',
  });

  assert.equal(summary[0].label, 'Reward Amount');
  assert.equal(summary[1].value, 'meme_mining_reward');
  assert.equal(summary[6].value, '2026-07-16T00:00:00+00:00');
});
