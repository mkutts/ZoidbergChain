function normalizeScopes(scopes = []) {
  return new Set(
    (Array.isArray(scopes) ? scopes : [scopes])
      .map((scope) => String(scope || '').trim().toLowerCase())
      .filter(Boolean),
  );
}

export function getEligibilityRuleChecks(eligibility, scopes = []) {
  const allowedScopes = normalizeScopes(scopes);
  const checks = Array.isArray(eligibility?.rule_checks) ? eligibility.rule_checks : [];
  return checks.filter((check) => {
    const scope = String(check?.scope || '').trim().toLowerCase();
    const applicable = check?.applicable !== false;
    return applicable && (!allowedScopes.size || allowedScopes.has(scope));
  });
}

export function getFailedRequiredRuleChecks(eligibility, scopes = []) {
  return getEligibilityRuleChecks(eligibility, scopes).filter(
    (check) => check?.required && check?.passed === false,
  );
}

export function getPassedAllowlistChecks(eligibility, scopes = []) {
  return getEligibilityRuleChecks(eligibility, scopes).filter((check) => (
    check?.passed === true
    && /(allowlist|override)/i.test(String(check?.rule_id || ''))
  ));
}
