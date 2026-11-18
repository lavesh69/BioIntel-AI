from __future__ import annotations


class ShiroError(RuntimeError):
    code = "shiro_error"


class UnsupportedDocumentError(ShiroError):
    code = "unsupported_document"


class CorruptDocumentError(ShiroError):
    code = "corrupt_document"


class ProjectAccessError(ShiroError):
    code = "project_access_error"


class IndexUnavailableError(ShiroError):
    code = "index_unavailable"


class CitationValidationError(ShiroError):
    code = "citation_validation_failure"


class ProviderUnavailableError(ShiroError):
    code = "provider_unavailable"


class ExternalAccessDisabledError(ShiroError):
    code = "external_access_disabled"

class UserCancellationError(ShiroError):
    code = "user_cancellation"


class GenerationTimeoutError(ShiroError):
    code = "generation_timeout"


class EmbeddingModelUnavailableError(ShiroError):
    code = "embedding_model_unavailable"


class IndexMismatchError(ShiroError):
    code = "index_mismatch"


class RetrievalFailureError(ShiroError):
    code = "retrieval_failure"


class ExternalSearchFailureError(ShiroError):
    code = "external_search_failure"
