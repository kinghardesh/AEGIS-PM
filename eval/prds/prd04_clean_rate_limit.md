# API Rate-Limiting Middleware

## Overview

Our public API has no protection against abusive or runaway clients, which risks degrading service for everyone. We will add rate-limiting middleware that caps how many requests each API key may make within a time window. Limits must be enforced consistently across all application instances, so counters live in a shared store rather than in per-process memory.

The middleware sits in front of the API routes and applies uniformly to authenticated API traffic keyed by API key.

## Requirements

1. **Token-bucket per API key** — Enforce rate limits using a token-bucket algorithm scoped to each API key, so each key gets an independent allowance.

2. **Configurable limits** — Make the bucket capacity and refill rate configurable via application configuration, without requiring code changes to adjust them.

3. **Redis-backed counters** — Store rate-limit counters/state in Redis so limits are enforced consistently across all server instances.

4. **429 response** — When a key exceeds its limit, reject the request with an HTTP 429 (Too Many Requests) status.

5. **Retry-After header** — Include a `Retry-After` header on 429 responses indicating how long the client should wait before retrying.

## Out of Scope

- Billing, paid quota tiers, or purchasing additional request allowances
- Per-endpoint custom limits (single global policy for this iteration)
