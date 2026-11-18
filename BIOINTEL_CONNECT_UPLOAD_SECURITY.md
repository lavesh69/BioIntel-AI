# BioIntel Connect upload security

Uploads are owner-bound, resumable and offset-checked. Initialization validates the declared filename, extension, MIME type and size. Chunks use durable upload state; completion verifies total size and optional SHA-256 before atomic storage.

The safety pipeline applies:

- allowlisted scientific/image/video/document/archive types and per-kind size limits;
- safe filenames and storage paths confined under the configured media root;
- content-signature/MIME inspection and archive-bomb traversal protections;
- malware-signature rejection and duplicate hash handling;
- warnings for participant, patient, genomic, consent, licence and institutional-risk text;
- explicit sensitive-content confirmation before flagged material becomes available;
- private-by-default media with object-level download authorization;
- audit state, scan JSON, checksum and ownership preservation.

Short videos additionally require transcript and alt text. Live/call recording is separate from upload and cannot begin without consent. Tests cover chunk resume, offset mismatch, deduplication, sensitive warnings, malware blocking and accessibility validation.
