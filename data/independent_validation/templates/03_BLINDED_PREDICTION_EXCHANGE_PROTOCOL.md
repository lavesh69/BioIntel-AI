# Blinded prediction exchange protocol

1. Freeze model, feature specification, code version, environment and dataset schema using SHA-256 hashes.
2. Record sample identifiers without outcome labels in the prediction-input manifest.
3. Generate predictions and lock the signed prediction batch before outcomes are released.
4. The independent site releases adjudicated outcomes through a separate controlled channel.
5. Reconcile one-to-one sample identifiers and document all exclusions or deviations.
6. Execute only the preregistered primary analysis before exploratory analyses.
7. Preserve input, prediction, outcome, analysis and audit artifacts in the validation dossier.
