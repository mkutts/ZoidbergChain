import { reactive, readonly } from 'vue';
import { publicApiClient, getApiErrorMessage } from '../config/api.js';

function createInitialState() {
  return {
    lastSubmittedFeedback: null,
    successMessage: '',
    errorMessage: '',
    isSubmitting: false,
  };
}

export function createFeedbackService(options = {}) {
  const publicApi = options.publicApi || publicApiClient;
  const state = reactive(createInitialState());

  function clearMessages() {
    state.successMessage = '';
    state.errorMessage = '';
  }

  async function submitFeedback(payload, headers = {}) {
    state.isSubmitting = true;
    clearMessages();
    try {
      const response = await publicApi.post('/feedback', payload, {
        headers: headers || {},
      });
      state.lastSubmittedFeedback = response.data?.feedback || null;
      state.successMessage = response.data?.message || 'Feedback submitted.';
      return response.data;
    } catch (error) {
      state.errorMessage = getApiErrorMessage(error, 'Feedback submission failed.');
      return null;
    } finally {
      state.isSubmitting = false;
    }
  }

  function reset() {
    state.lastSubmittedFeedback = null;
    clearMessages();
  }

  return {
    state: readonly(state),
    submitFeedback,
    reset,
  };
}

const feedbackService = createFeedbackService();

export function useFeedback() {
  return feedbackService;
}
