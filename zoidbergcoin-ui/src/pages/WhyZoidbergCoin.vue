<template>
  <div class="why-shell">
    <section class="why-card">
      <p class="eyebrow">Why ZoidbergChain?</p>
      <h1>Memes, originality, and community review</h1>
      <p class="lead">
        ZoidbergChain is a playful blockchain experiment where memes are submitted, reviewed by the community,
        and preserved with originality certificates when they pass.
      </p>

      <div class="reason-grid">
        <article class="reason-card">
          <h2>Why the name?</h2>
          <p>
            The project borrows the spirit of the “Why not Zoidberg?” joke: a little chaotic, a little self-aware,
            and willing to try something unconventional if it makes people smile.
          </p>
        </article>
        <article class="reason-card">
          <h2>What happens here?</h2>
          <p>
            Testers submit content, other testers vote on originality, and approved items can become certified meme
            blocks on the chain.
          </p>
        </article>
        <article class="reason-card">
          <h2>What is test ZOID?</h2>
          <p>
            Test ZOID is only for the controlled beta. It has no real monetary value, may reset, and is used to help
            us test rewards, balances, and transfers safely.
          </p>
        </article>
      </div>

      <div class="detail-panel">
        <p class="section-label">Beta Principles</p>
        <ul>
          <li>Wallets are used for identity and signatures.</li>
          <li>Some actions require approval while we reduce spam during testing.</li>
          <li>MetaMask never gives this app your seed phrase or private key.</li>
          <li>The goal is to make the tester journey understandable before the wider launch.</li>
        </ul>
      </div>

      <div class="action-row">
        <button @click="goToDashboard" class="btn primary">Open Beta App</button>
        <button @click="goBack" class="btn secondary">Back</button>
      </div>
    </section>
  </div>
</template>

<script>
export default {
  methods: {
    goBack() {
      this.$router.push('/');
    },
    goToDashboard() {
      this.$router.push('/dashboard');
    },
  },
};
</script>

<style scoped>
.why-shell {
  min-height: 100vh;
  padding: 36px 16px 48px;
  background:
    radial-gradient(circle at top left, rgba(255, 122, 69, 0.18), transparent 28%),
    linear-gradient(180deg, #0d1320 0%, #05070d 100%);
  color: #f7f0de;
}

.why-card {
  width: min(980px, 100%);
  margin: 0 auto;
  padding: 28px;
  border-radius: 24px;
  border: 1px solid rgba(255, 205, 115, 0.18);
  background: rgba(8, 12, 20, 0.92);
  box-shadow: 0 20px 56px rgba(0, 0, 0, 0.28);
  display: grid;
  gap: 18px;
}

.eyebrow,
.section-label {
  margin: 0;
  color: #ffcd73;
  font-size: 0.82rem;
  letter-spacing: 0.18em;
  text-transform: uppercase;
}

h1,
h2,
p {
  margin: 0;
}

h1 {
  font-size: clamp(2rem, 4vw, 3.4rem);
  line-height: 1.02;
}

h2 {
  font-size: 1.2rem;
}

.lead,
.reason-card p,
.detail-panel li {
  color: #ddd6c6;
  line-height: 1.6;
}

.reason-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
}

.reason-card,
.detail-panel {
  border-radius: 18px;
  border: 1px solid rgba(255, 205, 115, 0.14);
  background: rgba(255, 255, 255, 0.04);
  padding: 18px;
  display: grid;
  gap: 10px;
}

.detail-panel ul {
  margin: 0;
  padding-left: 18px;
  display: grid;
  gap: 8px;
}

.action-row {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.btn {
  border: none;
  border-radius: 14px;
  padding: 12px 16px;
  font: inherit;
  font-weight: 700;
  cursor: pointer;
}

.primary {
  background: linear-gradient(135deg, #ffcd73 0%, #ff945f 100%);
  color: #20150a;
}

.secondary {
  background: rgba(255, 255, 255, 0.08);
  color: #f7f0de;
}

@media (max-width: 900px) {
  .reason-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 620px) {
  .why-shell {
    padding: 24px 12px 36px;
  }

  .why-card {
    padding: 18px 16px;
    border-radius: 20px;
  }

  .action-row {
    display: grid;
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
