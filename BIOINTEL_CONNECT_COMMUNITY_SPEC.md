# BioIntel Connect community and collaboration specification

Communities support public, private, invite-only, institution-member and verified-member visibility. Join policy is open, approval or invite-only. Roles are owner, administrator, moderator, expert and member, with hierarchy checks for role assignment and channel posting.

Each community has a profile, rules, research fields, membership count and ordered channels. The initial General channel is created atomically with owner membership. Community posts use `community_members` visibility, which is enforced through active membership queries.

Scientific collaboration extends communities with:

- collaboration requests and reviewed applications;
- research projects and role-based members;
- publication records requiring explicit authorship confirmation;
- dataset listings and controlled access decisions;
- workflow definitions, immutable versions and safe forks that never execute code;
- events with capacity-aware registration;
- typed research opportunities.

Permission-aware discovery filters every result and recommendation before presentation. Private community and workflow no-auto-execution cases are automated tests.
