# Phase 23–30 Plugin Developer Guide

A plugin manifest must declare a stable key, name, version, compatibility and requested permissions. Registration does not enable the plugin.

An institution administrator reviews and grants each declared permission, then enables the plugin. Requests for unrestricted filesystem, network, SQL, shell, permission-management or credential access are rejected.

Plugins should generate drafts or call governed service operations. They must preserve institution context, use idempotency keys for retried writes, never log secrets and tolerate permission revocation. Arbitrary Python/plugin package execution is not part of this release.

