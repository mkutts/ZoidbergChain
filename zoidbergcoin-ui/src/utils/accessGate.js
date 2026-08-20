export function shouldDisplayAccessGate({
  requiresAppAccess = false,
  isAppUnlocked = false,
  skipAccessGate = false,
} = {}) {
  if (skipAccessGate) {
    return false;
  }
  return Boolean(requiresAppAccess && !isAppUnlocked);
}
