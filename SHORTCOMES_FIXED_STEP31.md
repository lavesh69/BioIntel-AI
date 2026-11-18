# Shortcomings Fixed in Step 31

1. Dataset files were registered for only part of the catalogue. Step 31 registers a primary file or immutable manifest for every dataset.
2. Column dictionaries, QC and provenance coverage were incomplete. All 51 datasets now have these registry layers.
3. Historical experiment hashes did not match current canonical registry hashes. Task-aware aliases preserve original hashes and provide auditable resolution.
4. Experiment artifacts and dataset bindings were not visible as a unified readiness layer. They are now checksummed and queryable.
5. Source catalogues differed between Internet and Evidence databases. All 15 provider profiles are synchronized.
6. Provider profiles could be mistaken for downloaded data. UI/API labels now distinguish profile-only, connector-ready and genuinely imported records.
7. Project records lacked consistent scientific-resource links. All 30 projects now have dataset/model/document/evidence lineage.
8. Feature-cache schema versions and runtime parameters were implicit. They are explicit and searchable.
9. Document extraction engine history was stale. Original versions remain preserved and a separate current registry-verification version is recorded.
10. Research Assets missed one primary database and newer modules. All 11 databases and 71 modules are indexed.
11. The default Streamlit page list was overloaded. A searchable, category-filtered custom navigation shell now serves all screens.
12. Page identity and context were inconsistent. Automatic breadcrumbs, descriptions and screen position appear globally.
13. Dense tables and tabs were difficult on smaller displays. Sticky headers, horizontal tab scrolling and responsive layouts were added.
14. Navigation favourites/recent work were not prominent. They are available in the shared sidebar.
15. Scientific completeness and release eligibility were visually mixed. Readiness scores and scientific blockers are shown separately.
