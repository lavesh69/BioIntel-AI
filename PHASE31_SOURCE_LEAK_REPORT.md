# Phase 31 Source-Leak Report

## Result

`PASS` for the Phase 31–35 Windows production distribution.

- Protected proprietary Python modules: 1,505.
- Protected Streamlit pages: 357.
- Unexpected readable proprietary Python files: 0.
- Allowed readable files: generic `app.py` and page bytecode bootstraps plus
  `launcher/boot.py`. These contain no BioIntel algorithms or domain implementation.
- Third-party Python source under the bundled CPython runtime is intentionally retained
  for library compatibility and is not BioIntel proprietary source.
- The developer-source ZIP parts intentionally contain complete readable source and are
  a separate owner/developer distribution.

## Secret scan

The high-confidence credential scan covered `app.py`, `pages`, `src`, `scripts`,
`config`, `deploy`, and `.streamlit`.

One string matched: `-----BEGIN PRIVATE KEY-----` in
`src/biointel/major_module_standard_v188/engine.py`. Inspection confirmed that it is an
adversarial validation payload used to test rejection of secret material; it is not a
private key. No AWS, GitHub, OpenAI, Google, Slack, or private-key credential was found.

## Package enforcement

The release builder compiles BioIntel source to optimized CPython 3.11 bytecode, removes
the original proprietary `.py` implementations from the production stage, scans the
stage before archiving, and fails closed if an unexpected readable application source
is present. Archive verification repeats the prohibited-source check.

This control is source-obfuscation and distribution separation, not cryptographic DRM.
Bytecode can be reverse engineered by a determined party; legal and operational controls
remain necessary.
