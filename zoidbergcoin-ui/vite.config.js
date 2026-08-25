import { fileURLToPath, URL } from 'node:url';
import { defineConfig } from 'vite';
import { sharedViteConfig } from './scripts/vite.shared.mjs';

export default defineConfig(sharedViteConfig);
