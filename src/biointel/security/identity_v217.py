from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Mapping


@dataclass(frozen=True)
class OidcConfiguration:
    issuer: str
    audience: str
    allowed_algorithms: tuple[str, ...] = ("RS256", "ES256", "EdDSA")
    subject_claim: str = "sub"
    email_claim: str = "email"
    groups_claim: str = "groups"
    tenant_claim: str = "tenant_id"
    leeway_seconds: int = 60


@dataclass(frozen=True)
class FederatedIdentity:
    subject: str
    email: str
    tenant_id: str
    role: str
    groups: tuple[str, ...]
    issuer: str
    expires_at: int
    claims: dict[str, Any]


def _select_key(token: str, jwks: Mapping[str, Any]) -> dict[str, Any]:
    try:
        from jose import jwt
    except ImportError as exc:
        raise RuntimeError(
            "OIDC verification requires the production dependency python-jose[cryptography]."
        ) from exc
    header = jwt.get_unverified_header(token)
    kid = str(header.get("kid", ""))
    algorithm = str(header.get("alg", ""))
    keys = jwks.get("keys", [])
    if not isinstance(keys, list):
        raise ValueError("JWKS keys must be a list.")
    matches = [
        key
        for key in keys
        if isinstance(key, dict)
        and (not kid or str(key.get("kid", "")) == kid)
        and (not key.get("alg") or str(key.get("alg")) == algorithm)
    ]
    if len(matches) != 1:
        raise ValueError("OIDC signing key could not be selected unambiguously.")
    return matches[0]


def verify_oidc_token(
    token: str,
    *,
    jwks: Mapping[str, Any],
    configuration: OidcConfiguration,
    role_map: Mapping[str, str] | None = None,
    default_role: str = "viewer",
) -> FederatedIdentity:
    if not token.strip():
        raise ValueError("OIDC token is required.")
    if not configuration.issuer.startswith("https://"):
        raise ValueError("OIDC issuer must use HTTPS.")
    if not configuration.audience.strip():
        raise ValueError("OIDC audience is required.")
    try:
        from jose import jwt
    except ImportError as exc:
        raise RuntimeError(
            "OIDC verification requires the production dependency python-jose[cryptography]."
        ) from exc

    key = _select_key(token, jwks)
    claims = jwt.decode(
        token,
        key,
        algorithms=list(configuration.allowed_algorithms),
        audience=configuration.audience,
        issuer=configuration.issuer.rstrip("/"),
        options={
            "verify_signature": True,
            "verify_aud": True,
            "verify_iss": True,
            "verify_exp": True,
            "verify_nbf": True,
            "verify_iat": True,
            "require_sub": True,
            "require_exp": True,
            "require_iat": True,
        },
        leeway=max(0, min(int(configuration.leeway_seconds), 300)),
    )
    subject = str(claims.get(configuration.subject_claim, "")).strip()
    if not subject:
        raise ValueError("OIDC subject claim is missing.")
    raw_groups = claims.get(configuration.groups_claim, [])
    if isinstance(raw_groups, str):
        groups = tuple(value for value in raw_groups.replace(",", " ").split() if value)
    elif isinstance(raw_groups, list):
        groups = tuple(str(value) for value in raw_groups if str(value).strip())
    else:
        groups = ()
    mapping = {str(key): str(value) for key, value in (role_map or {}).items()}
    role = next((mapping[group] for group in groups if group in mapping), default_role)
    if role not in {"viewer", "reviewer", "operator", "admin"}:
        raise ValueError("Mapped OIDC role is unsupported.")
    expires_at = int(claims.get("exp", 0) or 0)
    if expires_at <= int(datetime.now(UTC).timestamp()):
        raise ValueError("OIDC token is expired.")
    return FederatedIdentity(
        subject=subject,
        email=str(claims.get(configuration.email_claim, "")),
        tenant_id=str(claims.get(configuration.tenant_claim, "default") or "default"),
        role=role,
        groups=groups,
        issuer=str(claims.get("iss", "")),
        expires_at=expires_at,
        claims=dict(claims),
    )


def validate_scim_user(payload: Mapping[str, Any]) -> dict[str, Any]:
    schemas = payload.get("schemas", [])
    if not isinstance(schemas, list) or not any("User" in str(value) for value in schemas):
        raise ValueError("SCIM User schema is required.")
    user_name = str(payload.get("userName", "")).strip()
    if not user_name:
        raise ValueError("SCIM userName is required.")
    groups = payload.get("groups", [])
    group_values = [
        str(item.get("value", ""))
        for item in groups
        if isinstance(item, dict) and str(item.get("value", "")).strip()
    ] if isinstance(groups, list) else []
    return {
        "external_id": str(payload.get("externalId", "")),
        "user_name": user_name,
        "active": bool(payload.get("active", True)),
        "groups": group_values,
    }
