# Task 11.2 In-App User Feedback System

As of Friday, August 21, 2026, Task 11.2 adds a lightweight in-app feedback system for the controlled ZoidbergChain beta.

## Summary

Task 11.2 gives testers a direct way to report bugs, confusing flows, mobile issues, wallet trouble, access problems, submission trouble, voting issues, rewards issues, and general suggestions without leaving the app.

This task adds:

- persistent feedback records stored in the existing node-local backend state
- a public `POST /feedback` endpoint for beta feedback intake
- optional safe wallet, page, device, and eligibility context on feedback submissions
- protected admin feedback APIs for list, detail, status, priority, and notes
- `/admin` feedback review UI with queue filters and note-taking
- audit logging for admin feedback actions
- feedback summary counts in the admin ops payload

## User Feedback Flow

User-facing entry points now exist in:

- the main dashboard
- the blocked controlled-access gate

Users can submit:

- feedback type
- short title
- description
- optional name, email, and handle
- optional safe automatic context such as wallet, page, device, and eligibility status

The UI reminds users:

- this is a controlled beta
- rough edges are expected
- they should not include private keys, seed phrases, passwords, invite codes, or sensitive personal information

Submitting feedback does not unlock access, bind wallets, approve accounts, or change eligibility.

## Admin Processing Flow

Operators can:

- list feedback by status, type, or priority
- view full feedback detail
- mark feedback `reviewed`
- move feedback to `in_progress`
- mark feedback `resolved`
- mark feedback `dismissed`
- change priority to `low`, `normal`, `high`, or `urgent`
- add admin notes

Protected admin endpoints:

- `GET /admin/feedback`
- `GET /admin/feedback/{feedback_id}`
- `PATCH /admin/feedback/{feedback_id}`
- `POST /admin/feedback/{feedback_id}/status`
- `POST /admin/feedback/{feedback_id}/note`

## Feedback Statuses

- `new`
- `reviewed`
- `in_progress`
- `resolved`
- `dismissed`

## Feedback Safety Rules

Safe metadata may include:

- wallet address when connected or verified
- access account id when known
- current page or flow
- browser or viewport hints
- safe eligibility status summary

This task does not collect:

- private keys
- seed phrases
- wallet signatures
- admin credentials
- invite codes
- backend secrets

## Ops and Audit Notes

Admin ops status can now expose:

- new feedback count
- open feedback count
- high or urgent feedback count
- latest feedback timestamp

Admin audit events now cover feedback status changes, priority changes, note creation, and detail views without copying user-submitted descriptions into the audit log.

## Known Limitations

- this is not a full helpdesk or CRM
- no email notification is included yet
- no external helpdesk integration is included yet
- screenshot or file attachment support is still deferred
- feedback storage may remain node-local depending on the selected backend and deployment shape
