<template>
  <div class="dashboard">
    <h1>Dashboard</h1>
    <p>Select an action below:</p>
    
    <router-link to="/blockchain">
      <button>View Blockchain</button>
    </router-link>

    <input type="file" @change="uploadMeme">
    <button @click="submitMeme">Submit Meme</button>
  </div>
</template>

<script>
export default {
  data() {
    return {
      memeFile: null
    };
  },
  methods: {
    uploadMeme(event) {
      this.memeFile = event.target.files[0];
    },
    submitMeme() {
      if (!this.memeFile) {
        alert("Please upload a meme.");
        return;
      }
      alert("Meme submission functionality coming soon!");
    }
  }
};
</script>

<style scoped>
.dashboard {
  text-align: center;
  margin-top: 50px;
}
button {
  margin: 10px;
  padding: 10px;
}
</style>
