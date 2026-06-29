<template>
  <div class="blockchain-container">
    <h1>Blockchain Explorer</h1>
    <p class="subtitle">See the latest memes mined on the blockchain</p>

    <!-- Back to Dashboard Button -->
    <button @click="goToDashboard" class="btn secondary">Back to Dashboard</button>

    <div class="chain-container">
      <div v-if="chain.length === 0" class="loading-message">Loading blockchain data...</div>

      <div v-else class="blocks">
        <div v-for="(block, index) in chain" :key="index" class="block">
          <h3>Block #{{ block.index }}</h3>
          <p><strong>Mined by:</strong> {{ block.miner }}</p>

          <!-- Meme Image -->
          <div v-if="block.meme && block.meme.encoded_image" class="meme-container">
            <img :src="'data:image/png;base64,' + block.meme.encoded_image" alt="Meme Image" class="meme-image" />
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import axios from "axios";
import { API_BASE_URL } from "../config/api";

export default {
  data() {
    return {
      chain: [],
    };
  },
  async created() {
    try {
      const response = await axios.get(`${API_BASE_URL}/chain`);
      
      // Create a NEW array to prevent Vue reactivity issues
      this.chain = [...response.data.chain].reverse(); 
    } catch (error) {
      console.error("Error fetching blockchain data:", error);
    }
  },
  methods: {
    goToDashboard() {
      this.$router.push('/dashboard');
    }
  }
};
</script>

<style scoped>
/* General Layout */
.blockchain-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px;
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

/* Back to Dashboard Button */
.btn {
  width: 200px;
  padding: 12px;
  border: none;
  border-radius: 8px;
  font-size: 1rem;
  cursor: pointer;
  margin-bottom: 30px;
  transition: 0.3s ease-in-out;
  font-weight: bold;
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

/* Blockchain Blocks */
.chain-container {
  width: 80%;
  max-width: 800px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 20px;
}

/* Loading Message */
.loading-message {
  font-size: 1.2rem;
  color: #ff4747;
}

/* Blocks */
.block {
  background: rgba(30, 30, 30, 0.9);
  padding: 20px;
  border-radius: 12px;
  box-shadow: 0px 4px 10px rgba(255, 0, 0, 0.5);
  width: 100%;
  text-align: center;
}

.block h3 {
  color: #ff4747;
  margin-bottom: 10px;
}

.block p {
  margin: 5px 0;
  font-size: 1rem;
}

/* Meme Image */
.meme-container {
  text-align: center;
  margin-top: 10px;
}

.meme-image {
  max-width: 100%;
  height: auto;
  border-radius: 8px;
  box-shadow: 0px 4px 10px rgba(255, 0, 0, 0.5);
}
</style>
