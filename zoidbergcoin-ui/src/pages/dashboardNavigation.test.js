import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import url from 'node:url';

const __dirname = path.dirname(url.fileURLToPath(import.meta.url));

function read(relativePath) {
  return fs.readFileSync(path.resolve(__dirname, relativePath), 'utf8');
}

test('logged-in dashboard navigation exposes the new user-facing page structure', () => {
  const dashboardSource = read('./Dashboard.vue');
  const routerSource = read('../router/index.js');

  assert.match(dashboardSource, /label:\s*'Home'/i);
  assert.match(dashboardSource, /label:\s*'Submit'/i);
  assert.match(dashboardSource, /label:\s*'Vote'/i);
  assert.match(dashboardSource, /label:\s*'Rewards'/i);
  assert.match(dashboardSource, /label:\s*'Activity'/i);
  assert.match(dashboardSource, /label:\s*'Help'/i);
  assert.match(dashboardSource, /label:\s*'Feedback'/i);
  assert.doesNotMatch(dashboardSource, /label:\s*'Admin'/i);

  assert.match(routerSource, /path:\s*'\/submit'[\s\S]*appSection:\s*'submit'/i);
  assert.match(routerSource, /path:\s*'\/vote'[\s\S]*appSection:\s*'vote'/i);
  assert.match(routerSource, /path:\s*'\/rewards'[\s\S]*appSection:\s*'rewards'/i);
  assert.match(routerSource, /path:\s*'\/activity'[\s\S]*appSection:\s*'activity'/i);
  assert.match(routerSource, /path:\s*'\/help'[\s\S]*appSection:\s*'help'/i);
  assert.match(routerSource, /path:\s*'\/feedback'[\s\S]*appSection:\s*'feedback'/i);
  assert.match(routerSource, /path:\s*'\/blockchain'[\s\S]*redirect:\s*'\/activity'/i);
});

test('dashboard home and detail pages keep simplified copy and empty states visible', () => {
  const dashboardSource = read('./Dashboard.vue');

  assert.match(dashboardSource, /What should you do next\?/i);
  assert.match(dashboardSource, /Submit your first meme to start testing originality review\./i);
  assert.match(dashboardSource, /Nothing to vote on right now\. Check back after someone submits content\./i);
  assert.match(dashboardSource, /Use this guide if you get stuck\./i);
  assert.match(dashboardSource, /Tell us what is broken, confusing, or missing\./i);
  assert.match(dashboardSource, /Test ZOID has no real monetary value/i);
});
