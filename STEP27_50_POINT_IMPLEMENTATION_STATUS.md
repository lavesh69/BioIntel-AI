# Step 27 — 50-Point Implementation Status

The Step 27 roadmap mixed local software work with features that require
external binaries, scientific model validation, enterprise identity systems or
specialist computer-vision research. This release completes the local,
responsible implementation and marks external dependencies honestly.

## Implemented locally

1. Reviewed optional OCR pipeline.
2. OCR correction interface and audit records.
3. Page-coordinate provenance.
4. Source-region browsing through provenance tables.
5. Layout-aware multi-column PDF ordering heuristic.
6. OCR orientation/rendering foundation through PDFium/Tesseract.
7. Adjacent multi-page table stitching.
8. Table confidence score.
9. Table metadata for irregular/merged review.
10. Chart/image metadata foundation; raw chart digitization is not claimed.
11. PDF annotation/security metadata foundations.
12. PDF active-content and embedded-file security inspection.
13. Excel formula/cached-value dual storage.
14. Excel formula lineage table.
15. Merged-cell and workbook metadata preservation.
16. Excel comments, notes and hyperlinks.
17. Hidden rows/columns and grouping-related metadata.
18. Named ranges and data-validation extraction.
19. Excel chart/table inventory.
20. External relationship audit through package relationships.
21. Configurable high row limit and batch processing; true unlimited streaming remains format-specific.
22. Encrypted PDF support retained; encrypted Office decryption remains an optional external-library task.
23. DOCX headers and footers.
24. DOCX footnotes and endnotes.
25. DOCX comments and tracked-change counts.
26. DOCX drawing/media and embedded-object metadata.
27. Embedded images inventory and provenance foundation.
28. Embedded object blocking and safe metadata inventory.
29. CSV/TSV inputs.
30. TXT/Markdown/HTML inputs.
31. JSON/XML/YAML inputs.
32. PPTX inputs.
33. ODT/ODS inputs; RTF requires an additional safe parser.
34. Multi-file batch upload and processing.
35. Folder ingestion and watched-folder workflow.
36. Persistent extraction history with reusable outputs.
37. Batch progress callback and per-file failure isolation.
38. Duplicate document detection and reuse policy.
39. Parent-run and engine-version lineage.
40. Watched-folder scheduled loop support.
41. SQLite full-text search.
42. Tags, projects and notes.
43. Soft delete and restore.
44. Retention and purge functions.
45. Output checksum revalidation.
46. Scientific entity extraction.
47. Structured research-section/activity extraction.
48. Document-to-Dataset/Evidence integration.
49. Cross-document comparison and cited extractive Q&A.
50. Security hardening: active-content blocking, embedded-object control, sensitive-value detection, redaction and integrity checks.

## External or specialist work not falsely claimed

- OCR accuracy depends on the locally installed Tesseract engine and source quality.
- Chart/graph digitization needs a validated computer-vision model and manual calibration.
- Biomedical transformer NER requires model weights, GPU/CPU resources and benchmark validation.
- Password-protected Office decryption needs a vetted optional cryptography library.
- Antivirus requires a locally managed ClamAV or enterprise scanning service.
- OAuth/OIDC, RBAC, PostgreSQL, S3/MinIO and distributed workers require deployment infrastructure.
- Cryptographic reviewer identity/signatures require organizational key management.
