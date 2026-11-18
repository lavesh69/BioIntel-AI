# Phase 35 Claim-Evidence Graph Specification

Schema identifier: `biointel.phase35.claim-evidence-graph.v1`

## Node types

`claim`, `source`, `dataset`, `analysis`, `figure`, `hypothesis`, `experiment`,
`model`, `digital_twin_result`, `reviewer`, and `publication_asset`.

Each node has a workspace-scoped identity, label, metadata, confidence in `[0,1]`,
unsupported flag, provenance, creator, and timestamp. The unique key is
`(workspace, node type, external ID)`.

## Edge types

`direct_evidence`, `indirect_evidence`, `conflicting_evidence`, `derived_from`,
`generated_by`, `reviewed_by`, `supports`, `contradicts`, and `references`.

Each edge is workspace-scoped and records confidence, provenance, creator, and
timestamp. Duplicate source-target-relation edges are prevented.

## Generated claim requirements

Every scientific claim emitted by an agent records:

- direct evidence source IDs;
- indirect evidence source IDs;
- conflicting evidence source IDs;
- explicit unsupported status;
- bounded confidence;
- task, workspace, tenant, evidence-checksum, runtime, and provider provenance.

Evidence sources become graph nodes with content SHA-256, registered-existence
status, and stored retraction status. A missing source never becomes a supporting
edge. The graph does not convert confidence into truth or scientific proof.
