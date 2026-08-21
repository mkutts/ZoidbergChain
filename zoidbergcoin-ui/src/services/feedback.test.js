import test from 'node:test';
import assert from 'node:assert/strict';

import { createFeedbackService } from './feedback.js';

function createMockClient() {
  return {
    postCalls: [],
    postHandlers: new Map(),
    async post(path, payload = null, options = {}) {
      this.postCalls.push({ path, payload, options });
      const handler = this.postHandlers.get(path);
      if (!handler) {
        throw new Error(`Unexpected POST ${path}`);
      }
      return handler(payload, options);
    },
  };
}

test('feedback service submits successfully and stores the last feedback id', async () => {
  const publicApi = createMockClient();
  publicApi.postHandlers.set('/feedback', async (_payload, options) => ({
    data: {
      message: 'Feedback submitted.',
      feedback: {
        feedback_id: 'fb-1',
        status: 'new',
      },
      headers_seen: options.headers,
    },
  }));

  const feedback = createFeedbackService({ publicApi });
  const result = await feedback.submitFeedback(
    { type: 'bug', title: 'Mobile issue', description: 'Button overlaps keyboard' },
    { Authorization: 'Bearer wallet-session', 'X-ZOID-Access-Session': 'access-session-1' },
  );

  assert.equal(result.feedback.feedback_id, 'fb-1');
  assert.equal(feedback.state.lastSubmittedFeedback.feedback_id, 'fb-1');
  assert.equal(feedback.state.successMessage, 'Feedback submitted.');
  assert.deepEqual(publicApi.postCalls[0].options.headers, {
    Authorization: 'Bearer wallet-session',
    'X-ZOID-Access-Session': 'access-session-1',
  });
});

test('feedback service surfaces backend errors cleanly', async () => {
  const publicApi = createMockClient();
  publicApi.postHandlers.set('/feedback', async () => {
    const error = new Error('Bad request');
    error.response = {
      status: 400,
      data: {
        detail: 'Feedback title is required.',
      },
    };
    throw error;
  });

  const feedback = createFeedbackService({ publicApi });
  const result = await feedback.submitFeedback({
    type: 'bug',
    title: '',
    description: 'missing title',
  });

  assert.equal(result, null);
  assert.match(feedback.state.errorMessage, /title is required/i);
});
