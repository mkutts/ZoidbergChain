export function shouldShowAdminDashboard(session) {
  return Boolean(session?.authenticated);
}

export function adminSafetyLines() {
  return [
    'Invite codes are shown once. Copy before leaving this screen.',
    'This gate reduces spam but is not proof-of-personhood.',
    'Test ZOID has no real monetary value.',
    'Do not approve users you do not recognize.',
  ];
}
