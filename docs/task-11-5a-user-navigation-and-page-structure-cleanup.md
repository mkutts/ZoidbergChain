# Task 11.5a: User Navigation And Page Structure Cleanup

Date: August 21, 2026

## Summary

This task reorganizes the normal beta user app into a clearer page structure so approved testers are not dropped into every tool at once after unlock.

Admin remains separate at `/admin` and is not included in the normal user navigation.

## User-Facing Page Structure

- `Home`
  - Access and wallet status summary
  - Recommended next action
  - Simple action cards for submit, vote, rewards, help, and feedback
- `Submit`
  - Content upload and preview
  - Submission form
  - Submission eligibility messaging
  - Recent submissions for the connected approved wallet
- `Vote`
  - Review queue
  - Original / not original / unsure actions
  - Voting eligibility and override request flow
- `Rewards`
  - Wallet verification state
  - Test ZOID balance
  - Reward history
  - Transfer tools and transfer history
- `Activity`
  - Chain summary
  - Certified submissions
  - Rejected outcomes
  - Recent meme-mined blocks
  - Development-only mint queue tools remain hidden outside development mode
- `Help`
  - Beta guide summary
  - MetaMask reminders
  - Feedback reminder
  - Safety warnings
- `Feedback`
  - Dedicated entry point that opens the in-app feedback form

## Manual QA Checklist

1. Open the app as a new or private-session visitor.
2. Confirm the access gate still appears before unlock.
3. Confirm access request, invite, approved returning-wallet, override request, and gate feedback flows still work.
4. Unlock the app with an approved wallet and confirm the new user navigation appears.
5. Confirm `Home` stays simple and focuses on status plus next steps.
6. Confirm `Submit` contains upload, submission, and recent submission details.
7. Confirm `Vote` contains the review queue and voting actions.
8. Confirm `Rewards` contains wallet, balance, rewards, and transfer history.
9. Confirm `Activity` contains certified submission and recent block details.
10. Confirm `Help` exposes the beta guide copy and safety reminders.
11. Confirm `Feedback` opens the post-login feedback form.
12. Confirm phone-width layouts remain usable at 360px, 390px, 414px, and 430px.
13. Confirm `/admin` is still separate and not exposed in the normal user nav.
