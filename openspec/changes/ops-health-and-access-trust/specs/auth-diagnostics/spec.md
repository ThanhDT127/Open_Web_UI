## ADDED Requirements

### Requirement: A valid session cookie restores the dashboard on reload

The dashboard SHALL check for an existing session as part of its startup sequence, rather than by registering a listener for a document event that has already fired.

The startup path awaits several asynchronous imports before authentication is initialised, and the document-ready event fires at the first of those awaits. A listener registered afterwards never runs, so a session whose cookie is still valid is never restored and the sign-in screen is presented instead. By the time initialisation runs the document is necessarily ready, so the check can simply be performed.

This defect also inflates the refusal statistics the access summary reports: tabs issue their requests before authentication is restored, and every one of those requests is refused. Suppressing those refusals by filtering paths at the counting stage would leave the underlying fault in place while making its symptom unmeasurable.

#### Scenario: A returning admin with a live cookie is not asked to sign in

- **WHEN** the dashboard is reloaded while the session cookie is present and unexpired
- **THEN** the session is restored and the dashboard renders without presenting the sign-in screen

#### Scenario: An expired session still requires signing in

- **WHEN** the dashboard is loaded while the session cookie is absent or expired
- **THEN** the sign-in screen is presented

#### Scenario: Restored sessions stop generating refusals

- **WHEN** a dashboard session is restored from a valid cookie
- **THEN** the tabs' initial requests are authorised, and the refusal figure does not accrue from the dashboard's own startup
