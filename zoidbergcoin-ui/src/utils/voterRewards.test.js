import test from 'node:test';
import assert from 'node:assert/strict';

import {
  buildVoterRewardRulesCopy,
  describeBlockVoterRewardSettlements,
  describeSubmissionVoterReward,
} from './voterRewards.js';

test('buildVoterRewardRulesCopy includes public testnet and unsure warnings', () => {
  const lines = buildVoterRewardRulesCopy();

  assert.equal(lines[0], 'Voter rewards are testnet ZOID only.');
  assert.match(lines[2], /UNSURE never receives voter rewards/i);
  assert.match(lines[2], /anti-Sybil friction/i);
});

test('describeSubmissionVoterReward explains pending majority-side settlement', () => {
  const text = describeSubmissionVoterReward({
    reward_status: 'pending',
    final_majority_side: 'original',
    reward_amount_per_voter: '0.5',
  });

  assert.match(text, /Final majority side: ORIGINAL/i);
  assert.match(text, /settle in an accepted certified meme block/i);
  assert.match(text, /0\.5 testnet ZOID/i);
});

test('describeSubmissionVoterReward explains finalized rejection-side payouts', () => {
  const text = describeSubmissionVoterReward({
    reward_status: 'finalized',
    final_majority_side: 'not_original',
    reward_amount_per_voter: '1',
    rewarded_voter_count: 2,
  });

  assert.match(text, /NOT_ORIGINAL/i);
  assert.match(text, /2 majority-side voters received 1 testnet ZOID each/i);
});

test('describeSubmissionVoterReward explains final decisions with no payout', () => {
  const text = describeSubmissionVoterReward({
    reward_status: 'none',
    final_majority_side: 'original',
    reason: 'no_eligible_majority_voters',
  });

  assert.match(text, /Final majority side: ORIGINAL/i);
  assert.match(text, /No eligible majority-side voter rewards were paid/i);
});

test('describeBlockVoterRewardSettlements summarizes settled voter rewards', () => {
  const text = describeBlockVoterRewardSettlements({
    voter_rewards: [
      { final_decision: 'not_original', reward_amount: '0.25' },
      { final_decision: 'not_original', reward_amount: '0.25' },
    ],
  });

  assert.match(text, /2 NOT_ORIGINAL voter reward settlements/i);
  assert.match(text, /0\.25 testnet ZOID each/i);
});
