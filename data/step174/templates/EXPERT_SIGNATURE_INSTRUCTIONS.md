# Expert cryptographic sign-off

1. Create an expert review PDF or Markdown file.
2. Generate or use an approved signing key.
3. Sign with `openssl dgst -sha256 -sign private_key.pem -out review.sig review.pdf`.
4. Submit the review, detached signature, public key, credential and conflict disclosure with SHA-256 values.
5. Never include the private key in BioIntel AI.
