<template>
  <div class="dashboard-container">
    <h1>Dashboard</h1>
    <p class="subtitle">Manage your wallet and submit memes to the blockchain</p>

    <div class="form-container">
      <!-- Wallet ID Input -->
      <div class="wallet-input">
        <label for="wallet" class="label">Enter Wallet ID:</label>
        <input type="text" v-model="wallet" placeholder="Enter your wallet ID" class="input-field">
      </div>

      <!-- Private Key Input -->
      <div class="private-key-input">
        <label for="private-key" class="label">Enter Private Key:</label>
        <input type="text" v-model="privateKey" placeholder="Enter your private key" class="input-field">
      </div>

      <!-- File Upload -->
      <div class="file-upload">
        <label for="meme-upload" class="label">Upload a Meme:</label>
        <input type="file" id="meme-upload" @change="uploadMeme" class="file-input">
      </div>

      <!-- Submit Meme Button -->
      <button @click="submitMeme" class="btn primary">Submit Meme</button>

      <!-- View Blockchain Button -->
      <router-link to="/blockchain">
        <button class="btn secondary">View Blockchain</button>
      </router-link>
    </div>
  </div>
</template>

<script>
import axios from 'axios';

export default {
  data() {
    return {
      memeFile: null,
      wallet: '', // User-entered wallet ID
      privateKey: '' // User-entered private key
    };
  },
  methods: {
    uploadMeme(event) {
      this.memeFile = event.target.files[0];
    },
    async submitMeme() {
      if (!this.wallet) {
        alert("Please enter your wallet ID.");
        return;
      }
      if (!this.privateKey) {
        alert("Please enter your private key.");
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
      formData.append("miner", this.wallet); // Wallet ID
      formData.append("private_key", this.privateKey); // Private Key

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
        alert("Failed to submit meme. Check your wallet ID, private key, or API key.");
      }
    }
  }
};
</script>

<style scoped>
/* General Layout */
.dashboard-container {
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

/* Form Container */
.form-container {
  background: rgba(30, 30, 30, 0.9);
  padding: 25px;
  border-radius: 12px;
  box-shadow: 0px 4px 10px rgba(255, 0, 0, 0.5);
  width: 360px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

/* Input Fields */
.input-field,
.file-input {
  padding: 12px;
  font-size: 1rem;
  border: none;
  border-radius: 8px;
  text-align: center;
  background: #222;
  color: #fff;
  border: 1px solid #ff4747;
}

.file-input {
  cursor: pointer;
}

/* Labels */
.label {
  font-size: 1rem;
  color: #ddd;
  text-align: left;
  margin-bottom: 5px;
}

/* Buttons */
.btn {
  width: 100%;
  padding: 12px;
  border: none;
  border-radius: 8px;
  font-size: 1rem;
  cursor: pointer;
  margin-top: 10px;
  transition: 0.3s ease-in-out;
  font-weight: bold;
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
