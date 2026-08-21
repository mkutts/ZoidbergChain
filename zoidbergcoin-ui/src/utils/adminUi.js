export function shouldShowAdminDashboard(session) {
  return Boolean(session?.authenticated);
}

export function shouldShowAdminOpsPanel(session) {
  return shouldShowAdminDashboard(session);
}

export function shouldUseStackedAdminCards(viewportWidth = 0) {
  const width = Number(viewportWidth) || 0;
  return width > 0 && width <= 900;
}

export function buildBoundWalletRows(walletAddresses = []) {
  return (Array.isArray(walletAddresses) ? walletAddresses : []).map((walletAddress) => {
    const value = String(walletAddress || '');
    return {
      walletAddress: value,
      shortLabel: value.length > 22 ? `${value.slice(0, 10)}...${value.slice(-8)}` : value,
    };
  });
}

export function adminSafetyLines() {
  return [
    'Invite codes are shown once. Copy before leaving this screen.',
    'This gate reduces spam but is not proof-of-personhood.',
    'Test ZOID has no real monetary value.',
    'Do not approve users you do not recognize.',
  ];
}

export function opsHealthTone(opsStatus) {
  if (!opsStatus) {
    return 'neutral';
  }

  const environmentValidation = opsStatus.environment_validation || {};
  const runtimeStorage = opsStatus.runtime_storage || {};
  const integrityStatus = opsStatus.integrity_status || {};
  const sqliteIntegrity = opsStatus.sqlite_integrity || {};

  if (
    opsStatus.health?.status !== 'ok'
    || runtimeStorage.healthy === false
    || integrityStatus.healthy === false
    || sqliteIntegrity.healthy === false
    || Number(environmentValidation.error_count || 0) > 0
  ) {
    return 'error';
  }

  if (
    Number(environmentValidation.warning_count || 0) > 0
    || Number(opsStatus.backup_status?.backup_count || 0) === 0
  ) {
    return 'warning';
  }

  return 'healthy';
}

export function buildAdminOpsMetricCards(opsStatus) {
  if (!opsStatus) {
    return [];
  }

  const metrics = opsStatus.metrics || {};
  const health = opsStatus.health || {};
  const latestBlock = opsStatus.latest_block || {};

  return [
    { label: 'Environment', value: opsStatus.environment || 'unknown' },
    { label: 'Storage backend', value: opsStatus.storage_backend || 'unknown' },
    { label: 'Chain height', value: metrics.chain_height ?? health.chain_height ?? 'n/a' },
    { label: 'Pending access', value: metrics.pending_access_requests ?? health.pending_access_requests_count ?? 0 },
    { label: 'Pending review', value: metrics.pending_review_submissions ?? 0 },
    { label: 'Mempool', value: metrics.mempool_size ?? health.mempool_transaction_count ?? 0 },
    { label: 'Peers', value: metrics.peer_count ?? health.peer_count ?? 0 },
    { label: 'Latest block', value: latestBlock.hash ? `#${latestBlock.index ?? '?'} ${latestBlock.hash.slice(0, 12)}...` : 'Not available' },
  ];
}

export function buildAdminOpsWarnings(opsStatus) {
  if (!opsStatus) {
    return [];
  }

  const warnings = [];
  const checks = Array.isArray(opsStatus.environment_validation?.checks)
    ? opsStatus.environment_validation.checks
    : [];

  for (const check of checks) {
    if (check && check.ok === false && check.message) {
      warnings.push(String(check.message));
    }
  }

  if (Number(opsStatus.backup_status?.backup_count || 0) === 0) {
    warnings.push('No backup snapshot has been detected yet.');
  }

  if (opsStatus.integrity_status?.healthy === false) {
    warnings.push('Storage integrity is reporting a problem.');
  }

  if (opsStatus.sqlite_integrity?.healthy === false) {
    warnings.push('SQLite integrity check is not healthy.');
  }

  return [...new Set(warnings)];
}
