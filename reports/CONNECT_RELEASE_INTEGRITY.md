# BioIntel Connect Release Integrity

Release archives are assembled from a clean allowlist under a single `BioIntel-Step220` root. Runtime databases, logs, caches, `.env`, user uploads, generated recordings and secrets are excluded. `SHA256SUMS.txt` records archive hashes and the JSON manifest records composition and qualification status.
