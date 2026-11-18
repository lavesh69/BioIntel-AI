# Workflow Guide

Workflows are directed acyclic graphs with unique node keys, validated edges, topological order, parallel levels, retry/timeout/cache settings, and immutable version hashes. Runs reference an exact workflow version, input hashes, parameters, environment, tool versions, seed, warnings, errors, logs, and artifacts.

Clone a run to change parameters; freeze reviewed runs before reproducibility export. Missing external dependencies must be resolved or explicitly accepted as an unavailable optional path.
