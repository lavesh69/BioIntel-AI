# Step 197 Neuro/CNS Intelligence Studio

This feature release adds one unified Neuro/CNS workspace containing **23 independent local research engines** while preserving the verified Step 196/V16 Windows installer and two-step launch contract.

## Added

1. BBB Permeability Predictor
2. Neuro-Target Curation & Tagging
3. Neurotransmitter Pathway Mapper
4. Ion Channel Classifier
5. Neuro-Relevant GPCR Classifier
6. CNS Disease-Target Database
7. CNS Drug-Likeness Scorer
8. Off-Target Neurotoxicity Flagging
9. Neurodegeneration Protein Aggregation Risk
10. CNS Side-Effect Predictor
11. Neuroinflammation Target Set
12. Blood-CSF Barrier Module
13. Species/Model Organism Cross-Reference
14. CNS ADME & Transporter Interaction Studio
15. Brain Exposure & Neuro-PK Simulator
16. Receptor Occupancy & Target Engagement Lab
17. Neurogenetics & Variant Interpretation
18. Brain Cell-Type & Regional Expression Atlas
19. Neuro-Omics Biomarker Discovery Studio
20. EEG/MEG & Neural Signal Analytics
21. Neuroimaging & Connectomics Studio
22. CNS Clinical Evidence & Trial Intelligence
23. Precision Neurology & Patient Stratification

## Integration

- New curated page: `pages/263_Neuro_CNS_Intelligence_Studio.py`
- New backend package: `src/biointel/neuro_cns/`
- New versioned demo/reference snapshots: `data/neuro_cns/`
- Added to global module search, category navigation, role priorities and the Home workflow cards.
- Unified JSON and HTML report export across all Neuro/CNS results generated in the active session.
- The original SRS is preserved in `docs/specifications/Neuro_CNS_Module_SRS_Full.pdf`.

## Scientific boundaries

The implementation distinguishes software functionality from scientific validation. Descriptor, sequence, association, imaging and clustering outputs are labelled as screening or exploratory where appropriate. Bundled target/expression/side-effect records are demo/reference assets. The release does not claim clinical diagnosis, treatment recommendation, medical-device performance, licensed-database redistribution, independent-site validation or controlled scientific release.
