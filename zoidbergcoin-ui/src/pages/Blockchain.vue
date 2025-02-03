<template>
  <div class="blockchain">
    <h1>Blockchain Data</h1>
    <p v-if="loading">Loading blockchain data...</p>
    <p v-if="error">{{ error }}</p>

    <div v-for="block in blockchain" :key="block.index" class="block">
      <h3>Block #{{ block.index }}</h3>
      <p>Miner: {{ block.miner }}</p>
      <img v-if="block.meme && block.meme.encoded_image" 
           :src="'data:image/png;base64,' + block.meme.encoded_image" 
           alt="Meme">
    </div>
  </div>
</template>

<script>
import axios from 'axios';

export default {
  data() {
    return {
      blockchain: [],
      loading: true,
      error: null
    };
  },
  async created() {
    const API_URL = 'http://127.0.0.1:8000';

    try {
      const response = await axios.get(`${API_URL}/chain`);
      this.blockchain = response.data.chain;
      this.loading = false;
    } catch (error) {
      console.error("Error fetching blockchain data:", error);
      this.error = "Failed to load blockchain data.";
      this.loading = false;
    }
  }
};
</script>

<style scoped>
.blockchain {
  text-align: center;
}
.block {
  border: 1px solid #ccc;
  padding: 10px;
  margin: 10px;
}
img {
  max-width: 100%;
  height: auto;
}
</style>
