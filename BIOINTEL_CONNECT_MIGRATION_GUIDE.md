# BioIntel Connect Migration Guide

Back up existing data, merge archives into one `BioIntel-Step220` directory in part order, retain deployment secrets separately, run installer/migrations and tests, then validate authentication and two-device calling. Legacy PBKDF2 hashes are accepted for migration; new hashes use Argon2id.
