# BioIntel Education Suite

BioIntel Education Suite extends BioIntel Classroom and the Career, Internship & Scholarship Hub with local-first teaching, assessment, collaboration and application tools.

## Included local features

- Interactive lesson builder and learner attempts
- Versioned collaborative notes and comments
- Browser-local whiteboard with PNG export
- Question bank, assessments and automatic grading
- Local Python practice runner with restrictions and timeout
- Auto-graded coding tasks and notebook grading
- Code-similarity review indicators
- Classroom Q&A with accepted answers
- Offline learning-resource library with SHA-256 evidence
- Unified education search
- Learning-event analytics and portable JSON statements
- Résumé builder, application documents and interview practice
- Evidence-backed local credentials and badges

These capabilities run from the BioIntel desktop application and local SQLite databases. They do not require an online account.

## Optional institutional services

Large multi-user services remain separate deployments and connect through BioIntel-branded endpoints:

- BioIntel Live Classroom
- BioIntel Virtual Classroom Pro
- BioIntel Collaborative Board Service
- BioIntel Real-Time Notes Service
- BioIntel Multi-User Scientific Lab
- BioIntel Assessment Worker
- BioIntel Code Sandbox
- BioIntel Learning Record Store
- BioIntel Education Search Service
- BioIntel LMS Bridge
- BioIntel Offline Library Sync

Configure them from **Classroom → Education suite → Services** or run `SETUP_BIOINTEL_EDUCATION_SERVICES_WINDOWS.bat` after the core installation.

## Security boundaries

The built-in code runner is designed for trusted classroom practice. It blocks selected high-risk imports and functions and enforces a timeout, but it is not a hardened operating-system sandbox. Institutions must use the optional BioIntel Code Sandbox endpoint for untrusted submissions or high-stakes examinations.

Opportunity records, credentials, assessments and learning analytics must be reviewed under the institution's privacy, retention and academic-governance rules. Code similarity is only a review indicator and is never presented as a plagiarism verdict.

## Data locations

By default, Education Suite data is stored under the BioIntel user-data directory in `education_suite`. Set `BIOINTEL_USER_DATA_DIR` to move local data to an institution-approved location.
