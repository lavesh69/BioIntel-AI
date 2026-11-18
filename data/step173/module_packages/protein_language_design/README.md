# Protein design depth

Internal software/native/framework rating: **10/10**.

Actual practical readiness: **3.5/10**.

Stage: `S0-internal-10of10-external-evidence-pending`.

Decision: `research-only-fail-closed`.

Remaining blockers: engine:proteinmpnn | engine:rfdiffusion | reference:bindingdb | reference:proteinmpnn-weights | reference:rfdiffusion-weights | reference:uniprot-swissprot | model:full task specific domain model | model:real public or official cohort present | model:checksum locked holdout complete | model:leakage audit pass | model:calibration audit pass | model:independent external site complete | model:expert review complete | confirmation:protocol complete | confirmation:independent site complete | confirmation:wet lab complete | confirmation:prospective complete | confirmation:orthogonal complete | governance:physical qualification complete | governance:operating history complete | governance:expert signoff complete | governance:formal release review complete | governance:upstream runtime reference model complete | step172:confirmation manifest missing.

Next actions: Run PROVISION_STEP170_SCIENTIFIC_RUNTIME_WINDOWS.bat --execute and qualify missing engines. | Run DOWNLOAD_STEP170_REFERENCE_DATABASES_WINDOWS.bat, then register checksums, licences and scientific review. | Prepare/import the authentic Step 171 package for protein_language_design and run independent holdout validation. | Prepare Step 172 evidence workspace for protein_language_design; attach prospective/wet-lab/orthogonal evidence as required. | Complete physical qualification, operating history, cryptographic expert sign-off and formal release review..
