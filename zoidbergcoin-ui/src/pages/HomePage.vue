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
export default {
  data() {
    return {
      wallet: ''
    };
  },
  methods: {
    generateWallet() {
      alert("Generating a new wallet... (Functionality Coming Soon)");
    },
    signIn() {
      if (this.wallet) {
        alert("Signing in... (Functionality Coming Soon)");
        this.$router.push('/dashboard');
      } else {
        alert('Please enter a wallet ID.');
      }
    }
  }
};
</script>

<style scoped>
.home-container {
  text-align: center;
  margin-top: 50px;
}
input {
  margin: 10px;
  padding: 8px;
}
</style>
