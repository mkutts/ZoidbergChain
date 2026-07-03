<template>
  <div class="home-container">
    <h1>ZoidbergCoin</h1>
    <p class="subtitle">The Meme-Centric Blockchain</p>

    <!-- Quote Section -->
    <blockquote class="quote">
      "The remedy to be applied is more speech, not enforced silence."
      <span class="author"> - Louis Brandeis</span>
    </blockquote>

    <div class="form-container">
      <button @click="goToDashboard" class="btn secondary">Welcome</button>
      <button @click="generateWallet" class="btn primary">Register & Generate Wallet</button>
      
      <!-- Why ZoidbergCoin Button -->
      <button @click="goToWhyPage" class="btn secondary why-btn">Why ZoidbergCoin? ... Why not ZoidbergCoin</button>

      <!-- Download White Paper Button -->
      <a :href="whitePaperURL" download class="btn primary">Download White Paper</a>
    </div>

    <p v-if="successMessage" class="status-message success">{{ successMessage }}</p>
    <p v-if="errorMessage" class="status-message error">{{ errorMessage }}</p>

    <div v-if="walletDetails" class="wallet-details">
      <p v-if="walletDetails.privateKey" class="warning"><strong>Development only:</strong> Private key export is enabled for this local node.</p>
      <p v-else class="warning">{{ walletDetails.exportMessage }}</p>
      <p><strong>Public Key:</strong> {{ walletDetails.publicKey }}</p>
      <p v-if="walletDetails.privateKey"><strong>Private Key:</strong> {{ walletDetails.privateKey }}</p>
    </div>
  </div>
</template>

<script>
import { apiClient, getApiErrorMessage } from '../config/api';

export default {
  data() {
    return {
      walletDetails: null,
      successMessage: '',
      errorMessage: '',
      whitePaperURL: "/ZoidbergCoin_WhitePaper.pdf" // ✅ Path to the white paper in public folder
    };
  },
  methods: {
    async generateWallet() {
      this.successMessage = '';
      this.errorMessage = '';
      try {
        const response = await apiClient.post('/generate_wallet');

        const { public_key, private_key } = response.data.wallet;
        const keyExport = response.data.key_export || {};

        this.walletDetails = {
          publicKey: public_key,
          privateKey: private_key || null,
          exportMessage: keyExport.enabled
            ? 'Development-only private key export is available separately.'
            : keyExport.message || 'Private key export is disabled for this response.',
        };
        this.successMessage = response.data.message || 'Wallet generated successfully.';
      } catch (error) {
        console.error("Error generating wallet:", error);
        this.errorMessage = getApiErrorMessage(error, 'Failed to generate wallet.');
      }
    },
    goToDashboard() {
      this.$router.push('/dashboard');
    },
    goToWhyPage() {
      this.$router.push('/why-zoidbergcoin');
    }
  }
};
</script>

<style scoped>
/* General Layout */
.home-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100vh;
  text-align: center;
  background: radial-gradient(circle, #1a1a1a 0%, #000000 100%);
  color: #fff;
  font-family: 'Arial', sans-serif;
}

/* Title & Subtitle */
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

/* Quote */
.quote {
  font-size: 1rem;
  font-style: italic;
  color: #ddd;
  max-width: 500px;
  margin-top: 20px;
  margin-bottom: 30px;
}

/* Form Container */
.form-container {
  background: rgba(30, 30, 30, 0.9);
  padding: 25px;
  border-radius: 12px;
  box-shadow: 0px 4px 10px rgba(255, 0, 0, 0.5);
  width: 340px;
  display: flex;
  flex-direction: column;
  gap: 20px;
  margin-top: 20px;
}

/* Wallet Details */
.wallet-details {
  margin-top: 20px;
  padding: 20px;
  background: rgba(50, 50, 50, 0.9);
  border-radius: 12px;
  box-shadow: 0px 4px 10px rgba(255, 0, 0, 0.5);
  text-align: left;
  width: 360px;
}

.wallet-details p {
  margin: 5px 0;
  word-break: break-word;
}

.warning {
  color: #ff4747;
  margin-bottom: 10px;
  font-weight: bold;
}

.status-message {
  margin-top: 18px;
  max-width: 520px;
  line-height: 1.4;
}

.success {
  color: #8df5a6;
}

.error {
  color: #ff8c8c;
}

/* Buttons */
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

/* Primary Button */
.primary {
  background: linear-gradient(135deg, #ff4747 0%, #ff1616 100%);
  color: white;
  box-shadow: 0px 4px 10px rgba(255, 0, 0, 0.6);
}

.primary:hover {
  background: linear-gradient(135deg, #ff1616 0%, #cc0000 100%);
}

/* Secondary Button */
.secondary {
  background: linear-gradient(135deg, #4a90e2 0%, #2455a5 100%);
  color: white;
  box-shadow: 0px 4px 10px rgba(74, 144, 226, 0.5);
}

.secondary:hover {
  background: linear-gradient(135deg, #2455a5 0%, #123a70 100%);
}
</style>
