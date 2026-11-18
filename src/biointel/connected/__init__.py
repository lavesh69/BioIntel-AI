from biointel.connected.config import public_connection_status, settings_from_environment
from biointel.connected.diagnostics import test_openai_connection, test_provider_connections
from biointel.connected.free_web_ai import (
    FreeWebCopilot,
    OllamaClient,
    SearxNGClient,
    free_web_stack_diagnostic,
)
from biointel.connected.models import (
    ConnectedRecord,
    ConnectionDiagnostic,
    ProviderSpec,
    QueryResult,
)
from biointel.connected.providers import (
    ENTITY_PROVIDER_DEFAULTS,
    PROVIDERS,
    ConnectedProviderService,
    provider_rows,
    provider_supports_entity,
)
from biointel.connected.registry import (
    initialize_registry,
    latest_health_by_provider,
    recent_copilot_runs,
    recent_health_checks,
    recent_queries,
    registry_summary,
)

__all__ = [
    "ConnectedProviderService",
    "ConnectedRecord",
    "ProviderSpec",
    "QueryResult",
    "ConnectionDiagnostic",
    "PROVIDERS",
    "ENTITY_PROVIDER_DEFAULTS",
    "provider_rows",
    "provider_supports_entity",
    "public_connection_status",
    "settings_from_environment",
    "test_openai_connection",
    "test_provider_connections",
    "FreeWebCopilot",
    "OllamaClient",
    "SearxNGClient",
    "free_web_stack_diagnostic",
    "initialize_registry",
    "recent_queries",
    "recent_copilot_runs",
    "recent_health_checks",
    "latest_health_by_provider",
    "registry_summary",
]
