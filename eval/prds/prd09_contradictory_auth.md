# Authentication Redesign

## Overview

We're redesigning how users authenticate with our platform. This document describes the target authentication experience for the next release. Security and usability are both top priorities.

## Section A — Authentication Model

Authentication must be passwordless. We will use magic email links only: the user enters their email address, we send them a one-time login link, and clicking it signs them in. There are no passwords anywhere in this system. We will never store passwords, never ask users to create one, and never maintain a password database. This eliminates an entire class of credential-theft risk and is central to our security posture.

## Section B — Login Flow Details

Users log in with their username and password. On the login screen, present a username field and a password field. Enforce a strong password policy: passwords must be at least 12 characters long, and we should encourage a mix of character types. Store credentials securely using industry-standard hashing.

Password reset should be available via a "Forgot password?" link.

## Non-Functional

The login flow should be accessible, mobile-friendly, and localized. Session tokens should expire after a period of inactivity.

## Rollout

Ship behind a feature flag, roll out to 10% of users first, then expand. Collect metrics on login success rate and time-to-login.
