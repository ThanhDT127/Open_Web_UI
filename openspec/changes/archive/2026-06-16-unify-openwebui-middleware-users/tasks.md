## 1. Define and Migrate User Schema

- [x] 1.1 Add persisted middleware `role` with allowed values `admin` and `user`
- [x] 1.2 Add a unique nullable Open WebUI user UUID mapping field to middleware users
- [x] 1.3 Update all user row serializers, targeted updates, create operations, and admin responses for the new fields
- [x] 1.4 Create a migration that converts existing `manager` roles to `user` and records the migration

## 2. Build Reconciliation

- [x] 2.1 Add read-only access for retrieving required Open WebUI user identity fields
- [x] 2.2 Build an admin-only reconciliation report for matched, unmatched, duplicate, disabled, and conflicting users
- [x] 2.3 Add an explicit audited operation for confirming or changing a user mapping
- [x] 2.4 Verify reconciliation does not silently create, merge, disable, or delete users

## 3. Attribute Open WebUI Requests

- [x] 3.1 Configure Open WebUI to forward its user UUID to the middleware for authenticated upstream requests
- [x] 3.2 Add middleware validation that trusts forwarded identity only with the configured Open WebUI service credential
- [x] 3.3 Resolve forwarded Open WebUI identity to the mapped middleware quota record
- [x] 3.4 Preserve direct subkey authentication and attribute it to the same mapped quota record
- [x] 3.5 Add audit fields that distinguish Open WebUI service requests from direct subkey requests

## 4. Simplify Roles and Dashboard

- [x] 4.1 Remove `manager` from middleware API validation and dashboard role selectors
- [x] 4.2 Display only persisted `admin` and `user` role values in the dashboard
- [x] 4.3 Keep Open WebUI `pending` as an onboarding state without middleware quota access
- [x] 4.4 Add tests proving roles persist across middleware restart and user reload

## 5. Secure Quota Lookup

- [x] 5.1 Require a valid user credential for self quota lookup or an admin credential for arbitrary user lookup
- [x] 5.2 Reject non-admin requests that supply another user's identifier
- [x] 5.3 Update the Open WebUI quota filter integration to use authenticated self lookup

## 6. Migration Verification and Documentation

- [x] 6.1 Run reconciliation against current Open WebUI and middleware users and review all conflicts
- [x] 6.2 Verify mapped Open WebUI chat and direct API calls charge the same user quota record
- [x] 6.3 Verify existing subkeys remain valid after migration
- [x] 6.4 Document the canonical identity, role model, reconciliation process, and future SSO provisioning contract
