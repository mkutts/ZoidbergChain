const SIDE_LABELS = {
  original: 'ORIGINAL',
  not_original: 'NOT_ORIGINAL',
};

function sideLabel(side) {
  return SIDE_LABELS[String(side || '').trim().toLowerCase()] || 'No final side yet';
}

export function buildVoterRewardRulesCopy() {
  return [
    'Voter rewards are testnet ZOID only.',
    'Rewards go only to voters on the final majority side.',
    'UNSURE never receives voter rewards. This is anti-Sybil friction, not proof-of-personhood.',
  ];
}

export function describeSubmissionVoterReward(summary) {
  if (!summary) {
    return 'If approved, eligible ORIGINAL voters split testnet ZOID. If rejected as not original, eligible NOT_ORIGINAL voters split testnet ZOID. UNSURE receives no rewards.';
  }

  const status = String(summary.reward_status || '').trim().toLowerCase();
  const reason = String(summary.reason || '').trim().toLowerCase();
  const finalSide = sideLabel(summary.final_majority_side);
  const amount = summary.reward_amount_per_voter ?? '0';
  const rewardedCount = Number(summary.rewarded_voter_count || 0);

  if (!status || status === 'none') {
    if (summary.final_majority_side) {
      if (reason === 'voter_rewards_disabled') {
        return `Final majority side: ${finalSide}. Voter rewards are disabled on this node, so no payout was created.`;
      }
      return `Final majority side: ${finalSide}. No eligible majority-side voter rewards were paid. UNSURE receives no rewards.`;
    }
    return 'If approved, eligible ORIGINAL voters split testnet ZOID. If rejected as not original, eligible NOT_ORIGINAL voters split testnet ZOID. UNSURE receives no rewards.';
  }

  if (status === 'pending') {
    return `Final majority side: ${finalSide}. Eligible voters are set. Rewards settle in an accepted certified meme block. Estimated per voter: ${amount} testnet ZOID.`;
  }

  return `Final majority side: ${finalSide}. ${rewardedCount} majority-side voter${rewardedCount === 1 ? '' : 's'} received ${amount} testnet ZOID each.`;
}

export function describeBlockVoterRewardSettlements(block) {
  const rewards = Array.isArray(block?.voter_rewards) ? block.voter_rewards : [];
  if (!rewards.length) {
    return 'No voter reward settlements in this block.';
  }

  const firstReward = rewards[0] || {};
  const finalSide = sideLabel(firstReward.final_decision);
  const amount = firstReward.reward_amount ?? '0';
  return `${rewards.length} ${finalSide} voter reward settlement${rewards.length === 1 ? '' : 's'} at ${amount} testnet ZOID each.`;
}
