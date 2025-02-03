<template>
  <div class="why-container">
    <h1>Why ZoidbergCoin? ... Why not ZoidbergCoin</h1>

    <p>
      ZoidbergCoin is inspired by the “Why Not Zoidberg?” meme from the animated sci-fi series <strong>Futurama</strong>.
      The meme originates from the eccentric and often underappreciated character Dr. John Zoidberg, who frequently
      suggests himself for roles he is wildly unqualified for—often punctuated with the phrase “Why not Zoidberg?”
    </p>

    <p>
      This phrase became a widespread meme, symbolizing an enthusiastic yet misguided suggestion, often in response to
      situations where someone is struggling to find an answer. Over time, it evolved into a playful way of endorsing
      something unconventional or overlooked with a humorous, self-aware tone.
    </p>

    <h2>ZoidbergCoin: Embracing the Meme Economy</h2>

    <p>
      In the world of cryptocurrency, meme coins thrive on internet culture, humor, and community engagement.
      ZoidbergCoin embraces this fully, positioning itself as a fun-first, decentralized platform for meme creators
      and enthusiasts. Just as Zoidberg persistently asks, “Why not me?”, ZoidbergCoin asks:
    </p>

    <ul>
      <li>Why not a blockchain that celebrates and preserves meme culture?</li>
      <li>Why not reward creators for their contributions to internet culture?</li>
      <li>Why not build a blockchain where memes are the currency itself?</li>
    </ul>

    <p>
      By fusing decentralized technology with meme culture, ZoidbergCoin champions free expression and creativity while
      ensuring memes are immortalized on the blockchain—safe from censorship, takedowns, or disappearing internet
      archives.
    </p>

    <p><strong>Why ZoidbergCoin? The real question is: Why not ZoidbergCoin?</strong></p>

    <button @click="goBack" class="btn secondary">Back to Home</button>
  </div>
</template>

<script>
export default {
  methods: {
    goBack() {
      this.$router.push('/');
    }
  }
};
</script>

<style scoped>
/* General Layout */
.why-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px;
  text-align: center;
  background: radial-gradient(circle, #1a1a1a 0%, #000000 100%);
  color: #fff;
  font-family: 'Arial', sans-serif;
  min-height: 100vh;
}

/* Title */
h1 {
  font-size: 2.5rem;
  margin-bottom: 20px;
  text-shadow: 3px 3px 6px rgba(255, 0, 0, 0.5);
}

/* Subtitle */
h2 {
  font-size: 1.8rem;
  margin-top: 20px;
  color: #ff4747;
}

/* Paragraphs */
p {
  font-size: 1.2rem;
  margin-bottom: 15px;
  max-width: 800px;
  text-align: justify;
  line-height: 1.6;
}

/* Bullet Points */
ul {
  text-align: left;
  max-width: 800px;
  margin: 20px 0;
}

li {
  font-size: 1.2rem;
  margin-bottom: 10px;
  color: #bbb;
}

/* Back to Home Button */
.btn {
  width: 200px;
  padding: 12px;
  border: none;
  border-radius: 8px;
  font-size: 1rem;
  cursor: pointer;
  margin-top: 20px;
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
</style>
