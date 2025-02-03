<template>
  <div class="dashboard">
    <h1>Dashboard</h1>
    
    <label for="wallet">Enter Wallet ID:</label>
    <input type="text" v-model="wallet" placeholder="Enter your wallet ID">

    <router-link to="/blockchain">
      <button>View Blockchain</button>
    </router-link>

    <input type="file" @change="uploadMeme">
    <button @click="submitMeme">Submit Meme</button>
  </div>
</template>

<script>
import axios from 'axios';

export default {
  data() {
    return {
      memeFile: null,
      wallet: ''  // ✅ User will enter manually
    };
  },
  methods: {
    uploadMeme(event) {
      this.memeFile = event.target.files[0];
    },
    async submitMeme() {
      if (!this.wallet) {
        alert("Please enter a wallet ID.");
        return;
      }
      if (!this.memeFile) {
        alert("Please upload a meme.");
        return;
      }
      
      const API_URL = 'http://127.0.0.1:8000';
      const API_KEY = 'admin_key_123';

      let formData = new FormData();
      formData.append("image", this.memeFile);
      formData.append("miner", this.wallet);  // ✅ User-entered wallet ID

      try {
        const response = await axios.post(`${API_URL}/add_block`, formData, {
          headers: {
            "X-API-Key": API_KEY,
            "Content-Type": "multipart/form-data"
          }
        });
        alert("Meme Submitted Successfully!");
      } catch (error) {
        console.error("Error submitting meme:", error);
        alert("Failed to submit meme. Check API key and wallet.");
      }
    }
  }
};
</script>

<style scoped>
.dashboard {
  text-align: center;
  margin-top: 50px;
}
input {
  display: block;
  margin: 10px auto;
  padding: 8px;
}
button {
  margin: 10px;
  padding: 10px;
}
</style>
