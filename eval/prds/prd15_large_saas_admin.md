# Multi-Tenant SaaS Admin Dashboard

## Overview

This PRD describes the administrative control plane for our multi-tenant SaaS
product. The platform serves many independent customer organizations (tenants),
each with its own users, data, and configuration. The admin dashboard is the
surface through which tenant administrators onboard their organization, manage
who has access and what they can do, monitor usage, control billing, and
configure the integrations and settings that govern their tenant. Everything in
this document is scoped per tenant unless stated otherwise; strict data isolation
between tenants is assumed throughout.

## Tenant Onboarding

A new organization can self-onboard by creating a tenant. Onboarding collects the
organization name, a subdomain/slug, and the details of the first administrator
account. Completing onboarding provisions an empty, isolated tenant workspace and
signs the first admin into it. Onboarding is the entry point that all other
tenant-scoped features depend on.

## Roles and Permissions (RBAC)

Each tenant has a set of roles, and each role grants a set of permissions. The
system ships with default roles (at minimum Admin and Member) and allows tenant
admins to define custom roles by selecting from the available permissions. Users
within a tenant are assigned one or more roles, and their effective permissions
are the union of their roles' permissions. Every permission-gated action in the
dashboard is enforced against the acting user's effective permissions.

## User Invitations

Tenant admins invite new users by email and assign one or more roles to the
invitation. The invitee receives an email with a link to accept, sets up their
account, and joins the tenant with the assigned roles. Admins can view pending
invitations, resend an invitation, and revoke an invitation before it is
accepted. User invitations depend on RBAC (roles must exist to be assigned) and
on tenant onboarding.

## Audit Log

The platform records an immutable audit log of significant actions within a
tenant: user invited, user removed, role changed, permission changed, billing
plan changed, API key created or revoked, and settings changed. Each entry
captures who performed the action, what changed, and when. Tenant admins can view
and filter the audit log by actor, action type, and date range.

## Usage Metrics Dashboard

The dashboard presents per-tenant usage metrics such as active users, API request
volume, and storage consumed, displayed over a selectable time range. Metrics are
shown as time-series so admins can see trends. The usage metrics feed into the
billing and plan-limit logic described below.

## Billing and Plan Management

Each tenant is on a plan that defines its limits and price. Tenant admins can view
the current plan, see current usage against plan limits, and upgrade or downgrade
the plan. Billing depends on usage metrics (to show usage-against-limits) and on
tenant onboarding.

## SSO (SAML)

Tenants may configure SAML-based single sign-on so their users authenticate
through the tenant's own identity provider. Configuration captures the IdP
metadata (entity ID, SSO URL, certificate). Once enabled, users in that tenant
sign in via SAML. SSO configuration is a tenant-level setting available to admins.

## API Key Management

Tenant admins can create named API keys scoped to their tenant, view the list of
active keys (showing name, created date, and last-used date), and revoke a key.
The secret value of a key is shown only once at creation time. API keys inherit
tenant-scoped access and are subject to the tenant's permissions.

## Feature Flags

Tenant admins can toggle tenant-level feature flags to enable or disable optional
product capabilities for their organization. The dashboard lists available flags
with their current on/off state and lets admins change them.

## Data Export

Tenant admins can request an export of their tenant's data. The export is
generated asynchronously and, when ready, made available for download. Admins are
notified when an export is ready.

## Tenant-Level Settings

Each tenant has a settings area where admins configure tenant-wide options: the
organization display name, the tenant subdomain/slug, the default role assigned to
new members, and the default timezone. Changes to settings are recorded in the
audit log.

## Cross-Cutting Constraints

- Strict tenant data isolation: no tenant can read or write another tenant's data.
- All admin actions are permission-gated via RBAC.
- All significant mutations are recorded in the audit log.

## Out of Scope

Reseller/partner hierarchies, per-user (seat-level) billing, and OIDC/OAuth SSO
are out of scope for this release.
