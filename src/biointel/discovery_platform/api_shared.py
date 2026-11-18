from __future__ import annotations

import sqlite3
from functools import lru_cache
from typing import Any, Callable, Mapping, Sequence, TypeVar

from fastapi import HTTPException, Request

from .models import (
    PlatformConflictError,
    PlatformPermissionError,
    PlatformValidationError,
)
from .service import DiscoveryPlatformService, default_platform_paths
from .storage import DiscoveryPlatformStore

T = TypeVar("T")


def api_error(
    status: int,
    code: str,
    message: str,
    *,
    how_to_fix: str,
    retryable: bool = False,
) -> HTTPException:
    return HTTPException(
        status_code=status,
        detail={
            "error": {
                "code": code,
                "message": message,
                "affected": "requested operation",
                "partial_results_usable": False,
                "how_to_fix": how_to_fix,
                "retryable": retryable,
            }
        },
    )


def invoke(function: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    try:
        return function(*args, **kwargs)
    except KeyError as exc:
        raise api_error(
            404,
            "not_found",
            str(exc).strip("'"),
            how_to_fix="Verify the entity identifier and project scope.",
        ) from exc
    except PlatformPermissionError as exc:
        raise api_error(
            403,
            "permission_denied",
            str(exc),
            how_to_fix="Use an account with the required project role.",
        ) from exc
    except PlatformConflictError as exc:
        raise api_error(
            409,
            "state_conflict",
            str(exc),
            how_to_fix="Resolve the reported lifecycle, origin, or validation conflict.",
        ) from exc
    except (PlatformValidationError, ValueError, TypeError) as exc:
        raise api_error(
            422,
            "validation_failed",
            str(exc),
            how_to_fix="Correct the input fields using the OpenAPI schema and retry.",
        ) from exc
    except FileNotFoundError as exc:
        raise api_error(
            404,
            "file_not_found",
            str(exc),
            how_to_fix="Provide an existing local file inside an approved workspace.",
        ) from exc
    except sqlite3.DatabaseError as exc:
        raise api_error(
            503,
            "database_unavailable",
            "The research platform database operation failed.",
            how_to_fix=(
                "Run the database integrity check and restore from a verified backup if needed."
            ),
            retryable=True,
        ) from exc
    except OSError as exc:
        raise api_error(
            507,
            "storage_failure",
            str(exc),
            how_to_fix="Check disk space, file permissions, and the configured UserData path.",
            retryable=True,
        ) from exc


@lru_cache(maxsize=1)
def shared_store() -> DiscoveryPlatformStore:
    database, artifacts = default_platform_paths()
    return DiscoveryPlatformStore(database, artifacts)


_API_ROLE_MAP = {
    "admin": "Administrator",
    "local_operator": "Administrator",
    "operator": "Bioinformatician",
    "reviewer": "Reviewer",
    "viewer": "Read-only Viewer",
}


def service_for(request: Request) -> DiscoveryPlatformService:
    identity = getattr(request.state, "api_identity", None)
    actor = str(getattr(identity, "client_id", "local-operator"))
    role = _API_ROLE_MAP.get(
        str(getattr(identity, "role", "local_operator")), "Read-only Viewer"
    )
    return DiscoveryPlatformService(store=shared_store(), actor=actor, role=role)


def page(
    items: Sequence[Mapping[str, Any]],
    limit: int,
    offset: int,
) -> dict[str, Any]:
    return {
        "items": list(items),
        "count": len(items),
        "limit": limit,
        "offset": offset,
    }


__all__ = ["api_error", "invoke", "page", "service_for", "shared_store"]
