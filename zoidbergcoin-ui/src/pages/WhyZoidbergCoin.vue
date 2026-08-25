<template>
  <div class="why-shell">
    <section class="why-card">
      <p class="eyebrow">Beta Tester Guide</p>
      <h1>How to use the ZoidbergChain beta</h1>
      <p class="lead">
        ZoidbergChain is a controlled beta where testers submit content, vote on originality, and track test ZOID
        rewards while we improve the product before wider access.
      </p>

      <div class="reason-grid">
        <article class="reason-card">
          <h2>What is ZoidbergChain?</h2>
          <p>
            ZoidbergChain is an experimental meme-focused blockchain where originality is reviewed by the community.
            Approved content can become a certified meme block.
          </p>
        </article>
        <article class="reason-card">
          <h2>What is this beta for?</h2>
          <p>
            This beta is for testing access, wallet setup, content submission, originality voting, rewards, transfers,
            and feedback before we invite more users.
          </p>
        </article>
        <article class="reason-card">
          <h2>Important disclaimers</h2>
          <p>
            Test ZOID has no real monetary value. Content, votes, accounts, and balances may reset during testing.
            Wallets are used for identity and signatures, and this is experimental software.
          </p>
        </article>
      </div>

      <div class="guide-grid">
        <section class="detail-panel">
          <p class="section-label">Before You Start</p>
          <ul>
            <li>You can use MetaMask, or Email / Social Wallet if that option is enabled on your deployment.</li>
            <li>Use a wallet you can reconnect with later.</li>
            <li>Do not share seed phrases, private keys, passwords, or invite codes.</li>
            <li>Do not upload illegal, abusive, private, or copyrighted content you do not have permission to use.</li>
          </ul>
        </section>

        <section class="detail-panel">
          <p class="section-label">Access And Invites</p>
          <ol>
            <li>Request access from the gate if you are new.</li>
            <li>Once approved, you receive a one-time invite code.</li>
            <li>Enter the invite code, connect your wallet path, verify the wallet, and bind it once.</li>
            <li>Later, return by connecting the same approved wallet and signing again.</li>
          </ol>
        </section>

        <section class="detail-panel">
          <p class="section-label">Why Access Is Controlled</p>
          <ul>
            <li>The beta is intentionally small while we test onboarding, moderation, originality review, and rewards.</li>
            <li>Allowlist rules help us slow spam, watch for abuse, and support invited testers directly.</li>
            <li>Some actions can stay approval-gated even after basic app access is granted.</li>
          </ul>
        </section>

        <section class="detail-panel">
          <p class="section-label">Connect And Reconnect</p>
          <ol>
            <li>Choose MetaMask if you already have a crypto wallet.</li>
            <li>Email / Social Wallet is planned as a simpler path, but it is still coming soon in this app.</li>
            <li>Sign the verification message so the app knows this wallet is really yours.</li>
            <li>Bind the verified wallet once during your first approved invite flow.</li>
            <li>When you return later, reconnect the same approved wallet and sign again.</li>
          </ol>
        </section>

        <section class="detail-panel">
          <p class="section-label">Submit And Vote</p>
          <ol>
            <li>Upload your image or text content.</li>
            <li>Submit it with your verified wallet.</li>
            <li>Vote <strong>ORIGINAL</strong> if it looks original.</li>
            <li>Vote <strong>NOT ORIGINAL</strong> if it looks copied or clearly derivative.</li>
            <li>Vote <strong>UNSURE</strong> if you cannot confidently decide.</li>
          </ol>
        </section>

        <section class="detail-panel">
          <p class="section-label">Rewards And Feedback</p>
          <ul>
            <li>Test ZOID rewards are only for this beta and have no real monetary value.</li>
            <li>Rewards can depend on final decisions and eligibility rules.</li>
            <li>Use the in-app Send Feedback button whenever something feels broken or confusing.</li>
            <li>If something breaks, reconnect the approved wallet first, then send feedback if the problem continues.</li>
          </ul>
        </section>

        <section class="detail-panel">
          <p class="section-label">If Something Breaks</p>
          <ul>
            <li>Refresh the page and reconnect the same approved wallet.</li>
            <li>If a signature popup was missed, try the wallet step again from the access gate.</li>
            <li>If you are using MetaMask on mobile, switch into the MetaMask Mobile browser before retrying.</li>
            <li>Use Send Feedback with the page, wallet, and device details so the team can reproduce it.</li>
          </ul>
        </section>

        <section class="detail-panel">
          <p class="section-label">What Can Block Access</p>
          <ul>
            <li>A wallet may be blocked if it was never approved, the invite was not completed, or the wallet binding was revoked.</li>
            <li>Voting and rewards can have their own approval rules even when app access works.</li>
            <li>If you think your wallet should already work, use the beta help or feedback option from the gate.</li>
          </ul>
        </section>

        <section class="detail-panel">
          <p class="section-label">Mobile Tips</p>
          <ul>
            <li>MetaMask users usually get the smoothest injected-wallet flow inside the MetaMask Mobile browser.</li>
            <li>If Safari or Chrome does not detect MetaMask, switch into MetaMask Mobile.</li>
            <li>Email / Social Wallet users should also test the normal mobile browser path.</li>
            <li>App switching and signing behavior can vary by device and browser.</li>
            <li>If mobile wallet connection fails, use the in-app feedback form from the gate.</li>
          </ul>
        </section>

        <section class="detail-panel">
          <p class="section-label">Known Beta Limitations</p>
          <ul>
            <li>This is a controlled beta, so some actions stay approval-gated.</li>
            <li>Explorer and advanced activity views can still feel more technical than the main app.</li>
            <li>Balances, rewards, and content can reset while we test the network.</li>
            <li>Some flows can still vary between desktop MetaMask and MetaMask Mobile.</li>
            <li>Wallet portability matters before any future mainnet-value launch.</li>
          </ul>
        </section>

        <section class="detail-panel">
          <p class="section-label">How Originality Review Works</p>
          <ul>
            <li>Testers review submitted content and vote based on whether it appears original.</li>
            <li>Use <strong>ORIGINAL</strong>, <strong>NOT ORIGINAL</strong>, or <strong>UNSURE</strong> based on your confidence.</li>
            <li>Final results can affect visibility, certification, and beta reward outcomes.</li>
          </ul>
        </section>
      </div>

      <div class="action-row">
        <button @click="goToDashboard" class="btn primary">Open Beta App</button>
        <button @click="goToAccessGate" class="btn secondary">Access Gate</button>
        <button @click="goToHome" class="btn secondary">Home</button>
      </div>
    </section>
  </div>
</template>

<script>
export default {
  methods: {
    goToAccessGate() {
      this.$router.push('/');
    },
    goToDashboard() {
      this.$router.push('/dashboard');
    },
    goToHome() {
      this.$router.push('/');
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

.guide-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
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

.detail-panel ol {
  margin: 0;
  padding-left: 18px;
  display: grid;
  gap: 8px;
  color: #ddd6c6;
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

  .guide-grid {
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
