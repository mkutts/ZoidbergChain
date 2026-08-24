import { build } from 'vite';
import { sharedViteConfig } from './vite.shared.mjs';

await build({
  ...sharedViteConfig,
  configFile: false,
});
