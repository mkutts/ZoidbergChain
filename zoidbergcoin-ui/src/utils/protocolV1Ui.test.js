import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import url from 'node:url';

import {
  buildBlockContentAvailability,
  buildBlockDisplay,
  buildProtocolNetworkIdentity,
  buildSubmissionLifecycleDisplay,
  hasRenderableProtocolPreview,
  humanizeProtocolActionError,
  isProtocolGenesisBlock,
  shouldRetryProtocolAction,
} from './protocolV1Ui.js';

const __dirname = path.dirname(url.fileURLToPath(import.meta.url));

test('network identity prefers the frozen Public Testnet v1 label', () => {
  const identity = buildProtocolNetworkIdentity({
    protocol_version: 1,
    network_id: 'zoidberg-public-testnet-v1',
    network_name: 'zoidberg-testnet',
    canonical_genesis_hash: '585474a5',
  });

  assert.equal(identity.displayName, 'Public Testnet v1');
  assert.equal(identity.networkId, 'zoidberg-public-testnet-v1');
  assert.equal(identity.protocolLabel, 'Protocol v1');
  assert.equal(identity.genesisHash, '585474a5');
});

test('submission lifecycle distinguishes voting, canonical, and validator-quorum finality', () => {
  assert.equal(
    buildSubmissionLifecycleDisplay({
      protocol_v1_lifecycle: { phase: 'voting', voting: true },
    }).label,
    'Voting',
  );

  const canonical = buildSubmissionLifecycleDisplay({
    protocol_v1_lifecycle: {
      canonical: true,
      confirmations: 1,
      confirmation_depth: 2,
      finality_depth: 6,
    },
  });
  assert.equal(canonical.label, 'Canonical');
  assert.match(canonical.detail, /1 confirmation/i);

  const finalized = buildSubmissionLifecycleDisplay({
    protocol_v1_lifecycle: {
      finalized: true,
      confirmations: 6,
      confirmation_depth: 2,
      finality_depth: 6,
      valid_attestation_count: 2,
      quorum_required: 2,
    },
  });
  assert.equal(finalized.label, 'Validator-Quorum Finalized');
  assert.match(finalized.detail, /2\/2 valid validator attestations/i);
});

test('genesis detection and rendering stay separate from normal submission blocks', () => {
  const genesis = {
    index: 0,
    is_genesis: true,
    canonical: true,
    confirmations: 6,
    confirmed: true,
    finalized: true,
    confirmation_depth: 2,
    finality_depth: 6,
    media_embedded: true,
    download_url: '/blocks/2b99e87f80e0e855ab98b3269b635be5415273f41d7d4bf1a2aeb8b277b13061/media',
  };

  assert.equal(isProtocolGenesisBlock(genesis), true);

  const display = buildBlockDisplay(genesis);
  assert.equal(display.title, 'Public Testnet v1 Genesis');
  assert.equal(display.categoryLabel, 'Protocol v1 genesis object');
  assert.equal(display.statusLabel, 'Validator-Quorum Finalized');

  const availability = buildBlockContentAvailability(genesis);
  assert.equal(availability.chipLabel, 'Immutable Genesis Media');
  assert.match(availability.detail, /exact original Zoidberg meme bytes/i);
  assert.match(availability.detail, /non-certified genesis object/i);
});

test('MODEL A media helper keeps embedded block media authoritative without requiring list bytes', () => {
  const blockMedia = buildBlockContentAvailability({
    media_embedded: true,
    content_type: 'image',
    mime_type: 'image/png',
    storage_status: 'missing',
  });

  assert.equal(blockMedia.chipLabel, 'Immutable In Block');
  assert.match(blockMedia.detail, /immutable block record/i);
  assert.match(blockMedia.detail, /authoritative/i);
  assert.equal(
    hasRenderableProtocolPreview({
      media_embedded: true,
      content_type: 'image',
      mime_type: 'image/png',
    }),
    false,
  );
});

test('expired or reused signing failures are retryable and get concise copy', () => {
  assert.equal(shouldRetryProtocolAction('Challenge expired before verification.'), true);
  assert.equal(
    humanizeProtocolActionError('Challenge already been used.', { action: 'vote' }),
    'Vote signing window expired. Try again to request a fresh Protocol v1 message.',
  );
  assert.equal(
    humanizeProtocolActionError('wallet_address must match the verified wallet session.', { action: 'submission' }),
    'The signed wallet does not match your verified session. Reconnect the same wallet and try again.',
  );
});

test('maintained frontend source does not reference the legacy add_block route', () => {
  const srcRoot = path.resolve(__dirname, '..');
  const stack = [srcRoot];
  const contents = [];

  while (stack.length > 0) {
    const currentPath = stack.pop();
    for (const entry of fs.readdirSync(currentPath, { withFileTypes: true })) {
      const nextPath = path.join(currentPath, entry.name);
      if (entry.isDirectory()) {
        stack.push(nextPath);
        continue;
      }
      if (entry.name.includes('.test.')) {
        continue;
      }
      if (/\.(js|vue)$/.test(entry.name)) {
        contents.push(fs.readFileSync(nextPath, 'utf8'));
      }
    }
  }

  assert.equal(contents.some((source) => source.includes('/add_block')), false);
});
