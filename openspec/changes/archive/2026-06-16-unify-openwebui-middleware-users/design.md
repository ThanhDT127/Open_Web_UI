## Context

Open WebUI owns interactive login identities, groups, SSO, and SCIM. The middleware owns subkeys, model access, quotas, and billing audit. These records currently use unrelated identifiers and counts, so the system cannot reliably attribute Open WebUI activity to middleware quota records.

Open WebUI currently calls the middleware through a service credential. Direct API clients may also call the middleware with individual subkeys.

## Goals / Non-Goals

**Goals:**

- Establish one canonical identity for interactive Open WebUI users.
- Preserve direct API subkeys while associating them with the canonical identity.
- Reduce middleware roles to `admin` and `user`.
- Reconcile existing records safely before future SSO or group quota work.

**Non-Goals:**

- Configure a specific SSO provider.
- Implement group quotas.
- Remove Open WebUI's native `pending` onboarding state.

## Decisions

### 1. Use Open WebUI user UUID as canonical interactive identity

Middleware user records will store a unique `openwebui_user_id`. Existing middleware `user_id` values remain as display/legacy identifiers during migration.

Open WebUI UUID is selected because it is stable across name and email changes and is already used by Open WebUI groups, analytics, SSO, and SCIM.

### 2. Trust forwarded user identity only on authenticated service requests

For Open WebUI-originated calls, the middleware will accept a forwarded Open WebUI user identifier only when the request is authenticated with the configured Open WebUI service credential. Direct API subkeys continue to resolve directly to their associated middleware user.

This avoids trusting arbitrary user identity headers from external clients.

### 3. Reconcile before auto-provisioning

An admin-only reconciliation report will classify exact matches, unmatched Open WebUI users, unmatched middleware users, duplicates, and conflicts. Migration actions must be explicit and auditable.

Automatic SSO provisioning is deferred until this mapping is stable.

### 4. Use only admin and user roles in middleware

The middleware dashboard, API validation, and database will support only `admin` and `user`. Existing `manager` values migrate to `user`. Open WebUI `pending` remains an Open WebUI account state and receives no middleware access until approved/provisioned.

### 5. Persist roles in the database

The middleware database schema and all user serialization paths will include role. The dashboard will display only persisted role values.

## Risks / Trade-offs

- [Existing names or emails do not uniquely match] -> Generate a reconciliation report and require explicit mapping.
- [Forwarded identity headers can be forged] -> Trust them only with the Open WebUI service credential and internal network path.
- [Removing manager changes behavior] -> Migrate manager to user and document the removal.
- [Open WebUI upgrade changes forwarded headers] -> Centralize header parsing and cover it with integration tests.

## Migration Plan

1. Add nullable canonical identity and persisted role fields.
2. Generate a reconciliation report without changing users.
3. Explicitly map confirmed users and migrate `manager` to `user`.
4. Enable trusted Open WebUI user forwarding and attribution.
5. Update dashboard/API role options and quota lookup authorization.
6. Verify existing direct subkeys and Open WebUI chat attribution.
7. Roll back by disabling forwarded identity use while preserving additive mapping fields.

## Open Questions

- Whether unmatched approved Open WebUI users should later receive a default quota automatically or require admin approval.
