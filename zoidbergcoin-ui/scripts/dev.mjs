import { createServer } from 'vite';
import vue from '@vitejs/plugin-vue';

const args = process.argv.slice(2);
let host;
let port;
let strictPort = false;

for (let index = 0; index < args.length; index += 1) {
  const value = args[index];
  if (value === '--host') {
    const next = args[index + 1];
    host = next && !next.startsWith('--') ? next : true;
  }
  if (value === '--port') {
    const next = Number(args[index + 1]);
    if (!Number.isNaN(next)) {
      port = next;
    }
  }
  if (value === '--strictPort') {
    strictPort = true;
  }
}

const server = await createServer({
  configFile: false,
  plugins: [vue()],
  optimizeDeps: {
    noDiscovery: true,
  },
  server: {
    host,
    port,
    strictPort,
  },
});

await server.listen();
server.printUrls();
