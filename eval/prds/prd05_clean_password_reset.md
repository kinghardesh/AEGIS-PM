# Password Reset Flow

## Overview

Users who forget their password currently have no way to regain access to their account without contacting support. We will add a self-service password reset flow driven by a token emailed to the account's registered address. The flow must be secure: reset tokens are single-use and time-limited, and completing a reset invalidates any existing sessions to protect against account takeover.

This builds on the existing email/password authentication system and covers only the email-based reset path.

## Requirements

1. **Forgot password entry point** — Add a "Forgot password?" link on the login page that opens a form where the user enters their account email to request a reset.

2. **Emailed reset token** — On request, generate a reset token and email a reset link containing it to the account's registered address. The token is single-use and expires after a limited time window.

3. **Reset form** — Provide a reset form, reachable from the emailed link, where the user enters and confirms a new password. Validate the token before accepting the new password and reject expired, already-used, or invalid tokens.

4. **Update password** — On successful reset, hash and store the new password using the existing password-hashing scheme.

5. **Invalidate old sessions** — After a successful reset, invalidate the user's existing sessions so previously issued tokens can no longer be used.

## Out of Scope

- SMS-based reset or two-factor authentication
- Security-question-based recovery
