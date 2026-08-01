import test from 'node:test';
import assert from 'node:assert/strict';

import {
  buildNativeBalanceSummary,
  buildRewardSummary,
  describeTransferIntentDirection,
  describeTransferIntentStatus,
  formatTransferIntentTimestamp,
  humanizeNativeTransferError,
} from './nativeWalletUi.js';

test('buildNativeBalanceSummary keeps final balance visible and does not require pending fields', () => {
  const rows = buildNativeBalanceSummary({
    final_balance: '15',
    native_balance: '15',
    symbol: 'ZOID',
  });

  assert.deepEqual(rows, [
    {
      label: 'Final balance',
      value: '15 ZOID',
    },
  ]);
});

test('buildNativeBalanceSummary includes pending and available values when present', () => {
  const rows = buildNativeBalanceSummary({
    final_balance: '15',
    native_balance: '15',
    pending_outgoing: '10',
    pending_incoming: '2',
    available_balance: '15',
    symbol: 'ZOID',
  });

  assert.equal(rows.length, 4);
  assert.equal(rows[1].label, 'Available to spend');
  assert.equal(rows[1].value, '15 ZOID');
  assert.equal(rows[2].label, 'Pending outgoing');
  assert.equal(rows[3].label, 'Pending incoming');
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
  assert.equal(
    describeTransferIntentStatus('signed_pending'),
    'Signed native ZOID transfer recorded. Not settled yet.',
  );
  assert.equal(
    describeTransferIntentStatus('mempool'),
    'In local mempool. Not settled yet.',
  );
  assert.equal(describeTransferIntentStatus('settled'), 'Settled on ZoidbergChain.');
  assert.doesNotMatch(describeTransferIntentStatus('signed_pending'), /settled on zoidbergchain/i);
  assert.doesNotMatch(describeTransferIntentStatus('mempool'), /confirmed/i);
});

test('formatTransferIntentTimestamp prefers later lifecycle timestamps', () => {
  assert.equal(
    formatTransferIntentTimestamp({
      settled_at: '2026-07-16T02:00:00+00:00',
      admitted_at: '2026-07-16T01:30:00+00:00',
      signed_at: '2026-07-16T01:00:00+00:00',
      created_at: '2026-07-16T00:00:00+00:00',
    }),
    '2026-07-16T02:00:00+00:00',
  );
});

test('humanizeNativeTransferError maps common backend reasons to account-friendly copy', () => {
  assert.equal(
    humanizeNativeTransferError('insufficient_available_balance'),
    'Available to spend is too low for that native ZOID transfer.',
  );
  assert.equal(
    humanizeNativeTransferError('network does not match the active ZoidbergChain network.'),
    'This transfer belongs to a different ZoidbergChain network.',
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

  assert.equal(summary[0].label, 'Native ZOID Reward Amount');
  assert.equal(summary[1].value, 'meme_mining_reward');
  assert.equal(summary[6].value, '2026-07-16T00:00:00+00:00');
});
