## MODIFIED Requirements

### Requirement: Retrieval Citation Hit-Rate

The citation hit-rate SHALL be computed over the requests whose answer was actually recorded, not over every request that had a document attached. A request with no paired response SHALL be reported as a distinct `unpaired` figure and SHALL NOT be counted as a failure to cite: the absence of a recorded answer is evidence of nothing about the answer.

When no answer in the window could be read, the rate SHALL be absent rather than zero. Zero is a verdict — it states that the model answered and cited nothing — and that verdict cannot be supported by records that were never written.

The zero-citation list SHALL contain only requests whose answer was read and found to carry no citation marker. Listing an unpaired request there sends the reader to investigate a question that may well have been answered perfectly.

Every breakdown of the rate — by model, by source document, by user — SHALL carry the same split, so that a reader can verify that attachments equal evaluated plus unpaired at any level.

#### Scenario: An unrecorded answer is not counted as a missing citation

- **WHEN** a request carried an attached document but no paired response event was logged
- **THEN** it is counted as unpaired, is excluded from both sides of the rate, and does not appear in the zero-citation list

#### Scenario: A window with nothing readable has no rate

- **WHEN** every attached request in the window is unpaired
- **THEN** the rate is reported as absent rather than as zero, and the reader is told how many requests could not be read

#### Scenario: The reader can reconcile the three figures

- **WHEN** any window is aggregated, at the total level or within any breakdown
- **THEN** the attached count equals the evaluated count plus the unpaired count, and the cited count never exceeds the evaluated count

#### Scenario: A read answer with no citation is still listed

- **WHEN** a request's answer was recorded and contains no citation marker
- **THEN** it appears in the zero-citation list, and the count of that list equals evaluated minus cited

## ADDED Requirements

### Requirement: Source documents are named by their attachment tag

A source document SHALL be identified by the attachment tag that carries its name, not by the first tag bearing the same identifier. The system emits a citation *instruction template* — an unnamed tag — ahead of the real attachment tags in the same request, and the identifier is a per-request index rather than a document key, so first-match-wins collapses every document in the corpus into one synthetic entry.

Where no tag for an identifier carries a name, the entry SHALL be labelled as unnamed rather than attributed to an arbitrary document.

#### Scenario: A named tag outranks an unnamed one sharing its identifier

- **WHEN** a request body contains an unnamed source tag followed by a named tag carrying the same identifier
- **THEN** the breakdown attributes the request to the named document

#### Scenario: Renaming does not change how many attachments were counted

- **WHEN** the attribution rule changes
- **THEN** the total count of attached requests is unchanged; only the labels differ

### Requirement: Coverage of the shared knowledge base is reported

The system SHALL report what share of the questions asked in a window reached a shared knowledge base. Without it, every other retrieval figure measures the quality of a feature without ever stating whether the feature is used, and a perfect hit-rate over a handful of questions reads as success.

Numerator and denominator SHALL come from the same event type, the same window and the same filters, so that the ratio cannot exceed 100 percent by construction rather than by luck. The denominator SHALL NOT be taken from a source whose rows users can delete, and SHALL NOT be counted in a different unit from the numerator.

Coverage SHALL count only attachments to a shared knowledge base. A file a user attached to a single conversation is not the shared corpus, and folding the two together inflates the figure with something it does not measure; that count SHALL be reported separately rather than discarded.

The figure SHALL be named for the unit it counts. Where the records cannot attribute a request to a conversation, the metric SHALL be named per question asked rather than per conversation.

#### Scenario: The ratio cannot exceed one hundred percent

- **WHEN** coverage is computed for any window, with or without a model or user filter
- **THEN** the numerator is a subset of the denominator by construction, and the reported share lies between zero and one hundred

#### Scenario: A filter narrows both sides together

- **WHEN** the reader filters the tab by model
- **THEN** the denominator narrows to that model's questions, rather than a filtered numerator being divided by an unfiltered total

#### Scenario: Ad-hoc uploads are named, not folded in

- **WHEN** a window contains questions whose only attachment was a file uploaded to that one conversation
- **THEN** those questions are excluded from coverage and reported separately

#### Scenario: A window with no questions has no coverage

- **WHEN** no questions were asked in the window
- **THEN** coverage is reported as absent rather than as zero

### Requirement: A failed section says so instead of leaving figures on screen

Each section of the tab reads its own data source, so each SHALL carry its own failure notice and one failing section SHALL NOT blank the sections that answered.

When a section fails, its figures, tables, captions and period-comparison badges SHALL be cleared. A notice placed above the previously selected window's numbers still leaves those numbers reading as though they describe the window now on screen.

#### Scenario: A rejected time range is reported, not substituted

- **WHEN** the range parameters are malformed
- **THEN** the section reports the failure, rather than rendering a window the reader did not ask for

#### Scenario: Stale figures do not survive a failure

- **WHEN** a section fails after having rendered an earlier window
- **THEN** its values, tables, captions and comparison badges are cleared alongside the notice
