export const FEEDBACK_PANEL_OPEN_EVENT = 'zoidberg-feedback-open';

export function requestFeedbackPanelOpen(options = {}) {
  if (typeof window === 'undefined') {
    return;
  }
  window.dispatchEvent(new CustomEvent(FEEDBACK_PANEL_OPEN_EVENT, {
    detail: {
      panelId: String(options.panelId || 'feedback-panel'),
      scrollIntoView: Boolean(options.scrollIntoView),
    },
  }));
}
