<template>
  <div id="app">
    <div v-if="!isAccessReady" class="app-loading-shell">
      <div class="app-loading-card">
        <p class="loading-eyebrow">ZoidbergChain</p>
        <h1>Loading controlled testnet status...</h1>
        <p class="loading-copy">
          Checking the current environment, wallet session, and controlled access rules.
        </p>
      </div>
    </div>
    <ControlledAccessGate v-else-if="shouldShowAccessGate" />
    <router-view v-else />
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue';
import { useRoute } from 'vue-router';
import ControlledAccessGate from './components/ControlledAccessGate.vue';
import { useWallet } from './services/wallet';
import { useAccess } from './services/access';
import { shouldDisplayAccessGate } from './utils/accessGate.js';

const wallet = useWallet();
const access = useAccess();
const route = useRoute();
const isAccessReady = ref(false);

const shouldShowAccessGate = computed(
  () => shouldDisplayAccessGate({
    requiresAppAccess: access.requiresAppAccess(),
    isAppUnlocked: access.isAppUnlocked(),
    skipAccessGate: Boolean(route.meta?.skipAccessGate),
  }),
);

onMounted(async () => {
  await wallet.detectMetaMask();
  await access.initialize(wallet.getAuthorizationHeader());
  isAccessReady.value = true;
});
</script>

<style>
/* Reset default browser styles */
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

html, body {
  height: 100%;
  width: 100%;
  background: #000; /* Matches the HomePage theme */
  overflow-x: hidden; /* Prevent horizontal scrollbars */
}

/* Ensure the app container spans the full viewport */
#app {
  height: 100%;
  width: 100%;
}

.app-loading-shell {
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: 24px;
  background:
    radial-gradient(circle at top, rgba(255, 92, 51, 0.18), transparent 42%),
    linear-gradient(180deg, #0f1724 0%, #05070d 100%);
}

.app-loading-card {
  width: min(560px, 100%);
  padding: 28px;
  border-radius: 24px;
  border: 1px solid rgba(255, 205, 115, 0.2);
  background: rgba(8, 12, 20, 0.92);
  color: #f7f0de;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.35);
}

.loading-eyebrow {
  margin: 0 0 12px;
  color: #ffcd73;
  font-size: 0.82rem;
  letter-spacing: 0.18em;
  text-transform: uppercase;
}

.app-loading-card h1 {
  margin: 0 0 12px;
  font-size: 2rem;
  line-height: 1.1;
}

.loading-copy {
  margin: 0;
  color: #dfd7c6;
  line-height: 1.6;
}
</style>
