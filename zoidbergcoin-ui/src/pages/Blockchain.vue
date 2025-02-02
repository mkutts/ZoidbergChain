<template>
  <div class="blockchain">
    <h1>Blockchain Data</h1>
    <p>View memes stored in the blockchain.</p>

    <div v-for="block in blockchain" :key="block.index" class="block">
      <h3>Block #{{ block.index }}</h3>
      <p>Miner: {{ block.miner }}</p>
      <img v-if="block.meme" :src="'data:image/png;base64,' + block.meme.encoded_image" alt="Meme">
    </div>
  </div>
</template>

<script>
export default {
  data() {
    return {
      blockchain: [
        { index: 1, miner: "Wallet123", meme: { encoded_image: "" } },
        { index: 2, miner: "Wallet456", meme: { encoded_image: "" } }
      ]
    };
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
