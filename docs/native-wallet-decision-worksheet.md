# Native Wallet Decision Worksheet

Task 7.0A creates a decision worksheet only.

This document is intended to help Matt choose the long-term wallet and token architecture for ZoidbergChain without locking any implementation direction yet.

Constraints for this worksheet:

- No final architecture decisions are made here.
- No MetaMask login implementation is proposed here.
- No wallet code is proposed here.
- No transfer system is proposed here.
- No consensus rules are changed here.
- No originality scoring is changed here.
- No storage defaults are changed here.
- No frontend redesign is proposed here.

Every section ends with a placeholder for an explicit owner decision.

## 1. Big Architecture Question

Core question:

Should ZOID be:

- A. native-only on ZoidbergChain
- B. ERC-20 first
- C. native ZOID with later wrapped ZOID
- D. EVM-compatible chain
- E. non-EVM native chain with MetaMask signature identity

### Option A. Native-only on ZoidbergChain

What it means:

- ZOID exists only in the ZoidbergChain ledger.
- Wallets, balances, rewards, and transfers are defined by ZoidbergChain rules.
- No ERC-20 representation exists at launch.

Pros:

- Maximizes protocol uniqueness and independence.
- Keeps ZOID aligned with the project goal of becoming its own Layer 1.
- Avoids early design pressure to fit Ethereum conventions.

Cons:

- Harder exchange and wallet integration early on.
- Requires custom tooling for balances, transfers, and explorer support.
- Liquidity may be delayed until wrappers or bridges exist.

Implementation difficulty:

- Medium to high.
- Identity-only MetaMask usage is still possible, but the asset layer remains fully custom.

Impact on exchange/liquidity:

- Weakest short-term liquidity path.
- Stronger long-term sovereignty if wrapped or bridged assets are added later.

Impact on uniqueness of Meme Proof of Originality:

- Strongly preserves a distinct ZoidbergChain identity.
- Keeps Meme Proof of Originality more clearly coupled to a native chain economy.

### Option B. ERC-20 first

What it means:

- ZOID begins as an Ethereum-compatible token first, rather than as a native chain asset.
- ZoidbergChain may still exist, but economic value initially lives in an ERC-20 contract.

Pros:

- Fastest path to familiar wallet and exchange compatibility.
- Lowest conceptual friction for users already familiar with MetaMask and ERC-20 tokens.
- Simplifies early liquidity planning.

Cons:

- Weakens the story that ZoidbergChain itself is the primary home of ZOID.
- Risks making the native chain feel secondary.
- Can create migration complexity later if the project wants native-first economics.

Implementation difficulty:

- Medium for token ecosystem alignment, but potentially high if later migration to native coin status is needed.

Impact on exchange/liquidity:

- Strongest near-term liquidity and exchange compatibility.
- Easier to explain to external partners at the beginning.

Impact on uniqueness of Meme Proof of Originality:

- Makes the originality system feel less unique at the token layer.
- The application logic may still be unique, but the asset model looks more conventional.

### Option C. Native ZOID with later wrapped ZOID

What it means:

- ZOID starts as a native ZoidbergChain asset.
- A wrapped version may be introduced later for exchange liquidity or external ecosystem access.

Pros:

- Best fit for a true Layer 1 roadmap while preserving a future liquidity path.
- Separates core chain identity from external market plumbing.
- Common long-term architecture for sovereign chains that still want exchange access.

Cons:

- Requires careful future accounting between native and wrapped representations.
- Adds eventual bridge or custodial wrapper design questions.
- More moving parts over time than a single-layer token model.

Implementation difficulty:

- Medium now, high later.
- Early architecture choices should avoid blocking future wrapped supply mapping.

Impact on exchange/liquidity:

- Slower initial liquidity than ERC-20 first.
- Better long-term balance between sovereignty and market access.

Impact on uniqueness of Meme Proof of Originality:

- Preserves uniqueness in the native chain while still leaving room for broader reach.
- Likely the cleanest separation between originality logic and exchange plumbing.

### Option D. EVM-compatible chain

What it means:

- ZoidbergChain itself becomes EVM-compatible or heavily EVM-shaped.
- Native ZOID and wallet behavior follow Ethereum-like conventions closely.

Pros:

- Broad compatibility with MetaMask tooling and developer expectations.
- Easier reuse of existing wallet and contract patterns.
- Simplifies third-party ecosystem integration.

Cons:

- Pulls the project closer to Ethereum architecture choices.
- Risks reducing the distinctiveness of the chain design.
- Could increase scope significantly if the current stack is not already EVM-oriented.

Implementation difficulty:

- High.
- This is an architecture-level direction, not just a wallet decision.

Impact on exchange/liquidity:

- Strong external compatibility story if executed well.
- Better partner familiarity than a fully custom chain model.

Impact on uniqueness of Meme Proof of Originality:

- Application-level originality can remain unique.
- Base-chain identity may feel less differentiated if too much is made EVM-like.

### Option E. Non-EVM native chain with MetaMask signature identity

What it means:

- ZoidbergChain remains a non-EVM native chain.
- MetaMask is used only as an identity and signing tool for selected user actions.
- Native asset logic remains defined by ZoidbergChain, not Ethereum token rules.

Pros:

- Preserves native-chain identity without giving up a familiar signature wallet.
- Lets the project use MetaMask for authentication and proof-of-control workflows.
- Avoids forcing native economics into ERC-20 assumptions too early.

Cons:

- Users may expect MetaMask to handle balances and transfers even if it does not.
- Requires clear product boundaries between identity signing and asset custody.
- Some exchange and liquidity paths still require later wrapping or bridging.

Implementation difficulty:

- Medium.
- Usually simpler than full EVM compatibility, but still requires careful identity and address mapping design.

Impact on exchange/liquidity:

- Better user onboarding than native-only without immediate exchange-native liquidity benefits.
- Still likely needs wrapped ZOID later for broader trading access.

Impact on uniqueness of Meme Proof of Originality:

- Strong preservation of project uniqueness.
- Keeps Meme Proof of Originality anchored to ZoidbergChain while borrowing only wallet signatures from Ethereum tooling.

Decision needed from Matt:


## 2. MetaMask Role

Possible roles for MetaMask:

### Option A. Login/identity only

- MetaMask proves wallet ownership during login.
- Native chain actions remain controlled by server-side or separate native wallet flows.
- Lowest scope for early adoption.

Tradeoffs:

- Simplest mental model for authentication.
- May disappoint users who expect signing at the action level.

### Option B. Login + submission/vote signing

- MetaMask handles identity plus direct signatures for submissions and votes.
- Native token transfers remain outside the early MetaMask scope.

Tradeoffs:

- Stronger action-level accountability.
- Adds more signature UX and message-format design.

### Option C. Login + native ZOID transfer signing

- MetaMask signs messages that authorize native ZOID movements in ZoidbergChain.
- The chain is still not necessarily EVM-compatible.

Tradeoffs:

- Strong wallet-centric user story.
- Considerably more architecture risk because transfer semantics must be carefully defined.

### Option D. Full custom MetaMask network

- ZoidbergChain is exposed to MetaMask like a full supported network.
- Users expect network switching, balances, and transaction handling through MetaMask.

Tradeoffs:

- Most familiar wallet UX if fully supported.
- Highest scope and strongest dependency on chain/network compatibility decisions.

### Option E. MetaMask Snap later

- Start without a Snap.
- Revisit a Snap later if native-chain UX needs deeper wallet integration.

Tradeoffs:

- Keeps the near-term scope smaller.
- Defers a specialized integration path until the core chain model is clearer.

Decision needed from Matt:


## 3. ZOID Reward Model

### Option A. Rewards exist only in ZoidbergChain native ledger

- Rewards are recorded only as native balances or credits inside ZoidbergChain.
- Clean native-first model.
- Delays external liquidity until later infrastructure exists.

### Option B. Rewards create claimable wrapped ZOID later

- Rewards first exist natively, but may later map to a claim process for wrapped assets.
- Preserves native-first design while planning for future exchange utility.
- Requires future issuance and claim policy decisions.

### Option C. Rewards immediately mint ERC-20/wrapped ZOID

- Reward outcomes directly create external token balances or mintable wrapped balances.
- Strong market-facing token story.
- Risks centering token plumbing over the native-chain economy too early.

### Option D. Hybrid native reward now, bridge later

- Rewards are native now.
- A later bridge or wrapper can convert part or all of that value into an external form.
- Flexible, but requires future supply-governance clarity.

Decision needed from Matt:


## 4. Wallet Address Model

### Option A. Use Ethereum-style 0x addresses from MetaMask as Zoidberg addresses

What it means:

- A MetaMask-controlled address becomes the visible user identity in ZoidbergChain.

Tradeoffs:

- Familiar to users and easy to display.
- Simplifies identity mapping if MetaMask is central.
- Ties user-facing identity closely to Ethereum-style address conventions.
- May constrain future native-wallet design flexibility.

### Option B. Keep current native Zoidberg wallet format

What it means:

- ZoidbergChain keeps its own address format independent of MetaMask addresses.

Tradeoffs:

- Best preserves native-chain identity.
- More flexible for long-term custom wallet design.
- Requires an extra mapping layer if MetaMask is used for authentication.

### Option C. Support both legacy native wallets and MetaMask addresses

What it means:

- The system recognizes both existing native wallet identities and MetaMask-linked identities.

Tradeoffs:

- Easiest migration path from current development state.
- May reduce disruption to existing data and workflows.
- Increases complexity in validation, display, and identity resolution.

### Option D. Create new Zoidberg address format derived from public keys

What it means:

- A new address format is introduced that may be derived from public-key material regardless of signing source.

Tradeoffs:

- Creates a clean future-facing identity layer.
- Could unify multiple signing systems under one visible address family.
- Adds design scope and migration work.

Decision needed from Matt:


## 5. Submission Identity

### Option A. Logged-in wallet session controls submissions

- After login, the active wallet session authorizes submissions.
- Lower friction for users.
- Weaker direct proof on each individual submission event.

### Option B. Each submission must include a direct MetaMask signature

- Every submission carries an explicit signed message.
- Stronger non-repudiation and clearer auditability.
- More user prompts and more message-format design work.

### Option C. Start with session-based, later require direct signatures

- Begin with a simpler user flow.
- Reserve stricter submission proof for a later phase.
- Helps phase rollout, but may create migration and consistency questions.

Decision needed from Matt:


## 6. Voting Identity

### Option A. One vote per verified wallet session

- Voting is authorized by an active verified session.
- Lowest friction.
- More dependent on session integrity and anti-abuse controls.

### Option B. One vote per direct signed vote message

- Each vote is individually signed.
- Stronger auditability and clearer proof of user intent.
- Higher UX friction and more signature handling complexity.

### Option C. One vote per wallet plus later anti-Sybil requirements

- Start with wallet-level identity.
- Add stronger anti-Sybil policy later if needed.
- Flexible, but defers some abuse-resistance decisions.

Decision needed from Matt:


## 7. Transfer Model

Future options only. Do not implement in this task.

### Option A. Internal native transfer ledger first

- Transfers are tracked only inside ZoidbergChain's own ledger model.
- Best fit for native-chain sovereignty.
- Requires custom transfer semantics and tooling.

### Option B. MetaMask-signed transfer messages

- Transfers are authorized by wallet signatures, but still processed by native chain logic.
- Good bridge between familiar identity and native ledger behavior.
- Requires careful message validation and replay protection design.

### Option C. Full transaction pool / mempool

- Transfers evolve into a more complete transaction system with pending transaction handling.
- Strong long-term blockchain architecture path.
- Highest scope and not appropriate for this worksheet task beyond noting the option.

### Option D. Bridge/wrapped transfer later

- Native value exists first.
- External transfer and market mobility come later through wrapped or bridged assets.
- Defers exchange-oriented plumbing until the native asset model is stable.

Decision needed from Matt:


## 8. Legacy Wallet Strategy

### Option A. Keep dev wallets for development only

- Preserve existing development wallets for local testing and internal workflows.
- Clean separation between development and public-facing identity.

### Option B. Hide dev wallets from normal UI

- Keep them technically present, but avoid exposing them in standard user flows.
- Reduces confusion without forcing immediate data removal.

### Option C. Migrate old submissions to legacy identity labels

- Existing records stay readable under a legacy identity classification.
- Makes the history understandable without pretending the old wallets match the new model.

### Option D. Leave old records readable but require MetaMask going forward

- Historical data remains accessible.
- New user-facing actions follow the new identity policy.
- Often the simplest transition model, but it creates a clear before/after split.

Decision needed from Matt:


## 9. Suggested Decision Checklist

Matt can fill this out after reviewing the options above.

- ZOID will be native / ERC-20 / hybrid:
- MetaMask will be used for:
- User wallet address format:
- Submissions require:
- Votes require:
- Rewards are recorded as:
- Transfers will be implemented as:
- Legacy wallets will be handled by:
- Wrapped ZOID will be considered when:

## 10. No Code Changes

This task is documentation-only.

- No code paths are changed.
- No tests are required unless code is touched.
- This worksheet is intentionally non-binding until explicit approval is given.
