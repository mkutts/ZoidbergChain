<template>
  <div class="home-container">
    <PublicDemoBanner v-if="showPublicDemoBanner" />
    <h1>ZoidbergCoin</h1>
    <p class="subtitle">A controlled beta for community-reviewed meme publishing</p>

    <WalletPanel />

    <blockquote class="quote">
      Submit memes, vote on originality, and follow test ZOID rewards while the beta stays invite-only.
    </blockquote>

    <div class="form-container">
      <button @click="goToDashboard" class="btn secondary">Open Beta App</button>
      <button @click="goToWhyPage" class="btn secondary why-btn">Open Beta Guide</button>

      <a :href="whitePaperURL" download class="btn primary">Download White Paper</a>
    </div>
  </div>
</template>

<script>
import PublicDemoBanner from '../components/PublicDemoBanner.vue';
import WalletPanel from '../components/WalletPanel.vue';
import { isPublicDemoMode } from '../utils/runtimeConfig';

export default {
  components: {
    PublicDemoBanner,
    WalletPanel,
  },
  data() {
    return {
      showPublicDemoBanner: isPublicDemoMode(),
      whitePaperURL: '/ZoidbergCoin_WhitePaper.pdf',
    };
  },
  methods: {
    goToDashboard() {
      this.$router.push('/dashboard');
    },
    goToWhyPage() {
      this.$router.push('/why-zoidbergcoin');
    },
  },
};
</script>

<style scoped>
.home-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  text-align: center;
  background: radial-gradient(circle, #1a1a1a 0%, #000000 100%);
  color: #fff;
  font-family: 'Arial', sans-serif;
  padding: 32px 16px 48px;
}

h1 {
  font-size: 3rem;
  margin-bottom: 10px;
  text-shadow: 3px 3px 6px rgba(255, 0, 0, 0.5);
}

.subtitle {
  font-size: 1.2rem;
  margin-bottom: 20px;
  font-weight: 300;
  color: #bbb;
}

.quote {
  font-size: 1rem;
  font-style: italic;
  color: #ddd;
  max-width: 500px;
  margin-top: 20px;
  margin-bottom: 30px;
}

.form-container {
  background: rgba(30, 30, 30, 0.9);
  padding: 25px;
  border-radius: 12px;
  box-shadow: 0 4px 10px rgba(255, 0, 0, 0.5);
  width: min(340px, 100%);
  display: flex;
  flex-direction: column;
  gap: 20px;
  margin-top: 20px;
}

.btn {
  width: 100%;
  padding: 12px;
  border: none;
  border-radius: 8px;
  font-size: 1rem;
  cursor: pointer;
  transition: 0.3s ease-in-out;
  font-weight: bold;
  text-align: center;
}

.primary {
  background: linear-gradient(135deg, #ff4747 0%, #ff1616 100%);
  color: white;
  box-shadow: 0 4px 10px rgba(255, 0, 0, 0.6);
}

.primary:hover {
  background: linear-gradient(135deg, #ff1616 0%, #cc0000 100%);
}

.secondary {
  background: linear-gradient(135deg, #4a90e2 0%, #2455a5 100%);
  color: white;
  box-shadow: 0 4px 10px rgba(74, 144, 226, 0.5);
}

.secondary:hover {
  background: linear-gradient(135deg, #2455a5 0%, #123a70 100%);
}

@media (max-width: 620px) {
  .home-container {
    padding: 24px 12px 36px;
  }

  h1 {
    font-size: 2.35rem;
  }

  .form-container,
  .wallet-details {
    padding: 18px;
  }
}
</style>
