# Task 11.1 Admin Allowlist Management and User Override Requests

As of Friday, August 21, 2026, Task 11.1 adds persistent operator-managed allowlists and user-facing override requests for the controlled ZoidbergChain beta.

## Summary

Task 11.1 keeps the testnet closed by default while giving operators a safer manual override path for early testers who are blocked by invite, wallet binding, review eligibility, voting, or rewards rules.

This task adds:

- persistent allowlist entries stored with existing node-local backend state
- separate access and review-related override scopes
- user-facing eligibility status and plain-English blocked explanations
- public override-request submission for blocked testers
- admin processing for allowlist entries and override requests
- audit logging for allowlist and override actions

## Allowlist Scopes

Supported scopes:

- `access`
- `review`
- `submission`
- `voting`
- `rewards`
- `all_beta`

Scope intent:

- `access`: unlocks entry to the gated beta when the backend can safely identify the subject
- `review`: broad review-related override for submission, voting, and rewards eligibility
- `submission`: targeted submission override
- `voting`: targeted voting override
- `rewards`: targeted rewards override
- `all_beta`: broad beta override that can satisfy both access and review-related checks

## Access Allowlist vs Review Eligibility Allowlist

These are related but separate:

- Access allowlist controls who can enter and use the gated beta app.
- Review eligibility allowlist controls who can submit, vote, or receive review-related beta permissions when normal review policy would block them.

Important guardrails:

- admin authentication is still separate and is never bypassed by allowlist entries
- suspended or revoked access accounts remain blocked until an admin reactivates them
- revoked wallet bindings remain blocked until they are rebound or explicitly reapproved
- wallet signature verification is still required for wallet-authenticated actions

## Override Request Flow

Blocked users can submit `POST /eligibility/override-requests` without admin auth.

The request can include:

- requested scope
- optional name, email, and handle
- wallet address or access account id when known
- reason
- current page or flow
- detected blocked reason

Submitting an override request does not unlock access by itself.

Admin review flow:

- operators view pending requests in `/admin`
- approval creates the matching allowlist entry
- rejection stores an operator note
- both actions write audit records

## User-Facing Explanation

The UI now explains:

- the beta is controlled and invite-only
- approval or allowlist entry may be required
- a verified wallet may still be required
- some actions can have separate reviewer eligibility
- Test ZOID has no real monetary value
- admin overrides exist for early testers during controlled beta

Safe user-facing status now includes:

- access granted or blocked
- whether a wallet is connected and bound
- whether submissions, votes, or rewards are allowed
- blocked reasons
- active allowlist overrides
- suggested next steps

## Admin Instructions

Operators can now:

- create allowlist entries by wallet, access account, email, or handle
- filter allowlist entries by scope or status
- revoke or reactivate allowlist entries
- review override requests
- approve requests into allowlist entries
- reject requests with notes
- review audit log coverage for sensitive actions

## Security and Beta Limitations

This remains a controlled-beta operator tool, not a production identity system.

Known limits:

- allowlist decisions are still operator trust decisions, not proof-of-personhood
- persistence may remain node-local depending on deployment backend layout
- there is still no email notification, CRM integration, or external helpdesk integration
- review eligibility remains anti-Sybil friction only, not KYC or staking-based security
