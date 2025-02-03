<template>
  <div class="home-container">
    <h1>Welcome to ZoidbergCoin</h1>
    <p>Sign in with your wallet or create a new one.</p>
    
    <button @click="generateWallet">Register & Generate Wallet</button>
    <input type="text" v-model="wallet" placeholder="Enter your wallet ID">
    <button @click="signIn">Sign In</button>
  </div>
</template>

<script>
import axios from 'axios';

export default {
  data() {
    return {
      wallet: ''
    };
  },
  methods: {
    async generateWallet() {
  try {
    const response = await axios.post("http://127.0.0.1:8000/generate_wallet", {}, {
      headers: {
        "X-API-Key": "admin_key_123"  // Replace with your actual API key
      }
    });
    this.wallet = response.data.wallet.public_key;
    alert("Wallet Created! Your Wallet ID: " + this.wallet);
  } catch (error) {
    console.error("Error generating wallet:", error);
    alert("Failed to generate wallet. Check API key.");
  }
}
  }
};
</script>
