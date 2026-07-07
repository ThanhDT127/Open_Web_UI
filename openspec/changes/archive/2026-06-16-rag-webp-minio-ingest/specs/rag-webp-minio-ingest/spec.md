## ADDED Requirements

### Requirement: ZIP Ingestion Proxy
The system MUST proxy Docling conversion requests by requesting the `image_export_mode=referenced` parameter, receiving a ZIP package containing raw markdown and separate PNG files.

#### Scenario: Successful PDF ingestion with ZIP format
- **WHEN** Open WebUI sends a document conversion request to `/docling-proxy`
- **THEN** the system SHALL download the ZIP package, extract it in-memory, process the text/images, and return the final Markdown JSON payload back to Open WebUI.

### Requirement: WebP Image Conversion
The system MUST convert all extracted PNG images to the WebP format using Pillow compression to minimize network payload and storage space.

#### Scenario: Image compression to WebP
- **WHEN** a PNG file is extracted from the ingestion ZIP file
- **THEN** the system SHALL convert it to WebP format using `quality=80` compression.

### Requirement: MinIO/S3 Storage Upload
The system MUST upload WebP images to a centralized MinIO/S3 bucket and generate public static URLs pointing to those objects.

#### Scenario: Image upload to MinIO/S3
- **WHEN** WebP image bytes are successfully generated
- **THEN** the system SHALL upload the WebP file to the configured MinIO bucket under the `rag-images/{doc_id}/` folder and return the public URL.

### Requirement: Database Base64 Migration
The system MUST support a one-time migration to clean up all old database chunks containing Base64 image tags.

#### Scenario: Database cleanup
- **WHEN** the database migration script is executed
- **THEN** the system SHALL scan all document chunks, replace Base64 strings with materialized MinIO WebP URLs, and update the database entries.

### Requirement: Chat Query Path Base64 Bypass
The system MUST bypass scanning and decoding Base64 strings in prompt messages on the Query Path.

#### Scenario: Low-latency chat completion processing
- **WHEN** a chat completion request is received at `/v1/chat/completions`
- **THEN** the system SHALL not scan message content for `data:image/` strings, and instead directly forward the request payload to LiteLLM.
