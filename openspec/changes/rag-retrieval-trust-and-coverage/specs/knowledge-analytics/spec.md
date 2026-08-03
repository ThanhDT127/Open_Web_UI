## ADDED Requirements

### Requirement: A knowledge base is not judged on answers that were never recorded

Demand for a knowledge base is proven by its attachments; quality can only be judged from answers the system actually recorded. The classification SHALL gate the quality verdict on the count of recorded answers, separately from the count of attachments.

A knowledge base attached many times whose answers were never recorded SHALL be classified as unproven. It SHALL NOT be classified as needing tuning, because that verdict names the knowledge base as the thing at fault on the strength of missing logs — the same conflation the retrieval hit-rate carries, reached through the same join.

The reported hit-rate SHALL be absent rather than zero where no answer was read, and where a rate is reported alongside unread answers, the reader SHALL be able to tell how many were unread.

#### Scenario: Unmeasurable quality is unproven, not poor

- **WHEN** a knowledge base was attached well above the sample floor but no paired answer was recorded for any attachment
- **THEN** it is classified as unproven and its hit-rate is reported as absent

#### Scenario: The ordinary verdict resumes once answers are readable

- **WHEN** enough of a knowledge base's attachments have recorded answers
- **THEN** it is classified by the ordinary quality thresholds

#### Scenario: A dash states which absence it means

- **WHEN** a knowledge base shows no hit-rate
- **THEN** the reader can tell whether it was never attached or was attached without any answer being recorded

### Requirement: An unreadable corpus is reported, not rendered as an empty one

The knowledge endpoints answer with zeroed bodies and an error field when their queries fail. That body is indistinguishable from a healthy installation that simply holds no knowledge bases, so it SHALL NOT be rendered as figures.

Each section SHALL surface the failure and SHALL NOT paint zeros in its place. Because the sections read independent sources, one failing SHALL NOT suppress the sections that answered.

#### Scenario: A failed read is visible rather than silent

- **WHEN** a knowledge query fails
- **THEN** the section states that the data could not be read, and no counts, tables or totals are drawn from the failed response

#### Scenario: One failure does not blank the rest

- **WHEN** one of the three sections fails while the others succeed
- **THEN** the successful sections still render
