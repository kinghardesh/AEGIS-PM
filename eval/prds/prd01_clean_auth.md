# Email/Password User Authentication

## Overview

Our web application currently has no way for users to create accounts or sign in. We need a self-contained email and password authentication system so that visitors can register, authenticate, and manage their own sessions securely. All credentials must be stored safely, and authenticated sessions must be represented by stateless tokens that the frontend can attach to API requests.

This work covers the full baseline flow: account creation, login, session issuance, and logout. It does not cover third-party identity providers.

## Requirements

1. **Registration** — Provide a registration endpoint that accepts an email address and a password. Reject registration when the email is already in use, and validate that the email is well-formed and the password meets a minimum length of 8 characters.

2. **Password hashing** — Store passwords using bcrypt hashing. Never store or log plaintext passwords.

3. **Login** — Provide a login endpoint that accepts an email and password, verifies the password against the stored bcrypt hash, and rejects invalid credentials with a generic error message.

4. **JWT session tokens** — On successful login, issue a signed JWT access token that encodes the user identity and an expiry. The frontend attaches this token to subsequent authenticated requests.

5. **Logout** — Provide a logout endpoint that ends the user's session so the token can no longer be used for authenticated requests.

## Out of Scope

- Social or OAuth login (Google, GitHub, etc.)
- Multi-factor authentication
- Password reset (tracked separately)
