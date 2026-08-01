<template>
  <section class="public-demo-banner">
    <p class="banner-label">Public Demo</p>
    <h2>ZoidbergChain controlled testnet</h2>
    <p class="banner-copy">
      Test ZOID has no real monetary value, this network may reset, and it is not mainnet.
    </p>
    <ul class="banner-points">
      <li>Native ZOID lives on ZoidbergChain, not Ethereum.</li>
      <li>MetaMask signs ZoidbergChain actions.</li>
    </ul>
  </section>
</template>

<style scoped>
.public-demo-banner {
  width: min(1080px, 100%);
  margin: 0 auto 24px;
  padding: 18px 20px;
  border: 1px solid rgba(255, 190, 92, 0.4);
  border-radius: 18px;
  background:
    linear-gradient(135deg, rgba(255, 190, 92, 0.16), rgba(255, 112, 67, 0.10)),
    rgba(15, 18, 28, 0.9);
  color: #f8f2df;
  box-shadow: 0 16px 40px rgba(0, 0, 0, 0.22);
}

.banner-label {
  margin: 0 0 6px;
  font-size: 0.8rem;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: #ffcd73;
}

h2 {
  margin: 0 0 10px;
  font-size: 1.35rem;
}

.banner-copy {
  margin: 0 0 10px;
  line-height: 1.5;
}

.banner-points {
  margin: 0;
  padding-left: 18px;
  line-height: 1.5;
}
</style>
