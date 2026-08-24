import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import url from 'node:url';

const __dirname = path.dirname(url.fileURLToPath(import.meta.url));
const projectRoot = path.resolve(__dirname, '../..');

function readProjectFile(relativePath) {
  return fs.readFileSync(path.resolve(projectRoot, relativePath), 'utf8');
}

test('vite config keeps Privy SDK dependencies on the ESM-safe path', () => {
  const source = readProjectFile('scripts/vite.shared.mjs');

  assert.match(source, /plugins:\s*\[vue\(\)\]/i);
  assert.doesNotMatch(source, /eventemitter3/i);
  assert.doesNotMatch(source, /@privy-io\/js-sdk-core/i);
});

test('dev and build scripts both use the shared Privy interop config', () => {
  const source = readProjectFile('scripts/dev.mjs');
  const buildSource = readProjectFile('scripts/build.mjs');

  assert.match(source, /sharedViteConfig/i);
  assert.match(source, /configFile:\s*false/i);
  assert.doesNotMatch(source, /@vitejs\/plugin-vue/i);
  assert.match(source, /createServer\(\{/i);
  assert.match(buildSource, /sharedViteConfig/i);
  assert.match(buildSource, /configFile:\s*false/i);
  assert.doesNotMatch(buildSource, /@vitejs\/plugin-vue/i);
});
