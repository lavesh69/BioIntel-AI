class BioIntelError(Exception):
    """Base exception for this project."""


class InvalidSequenceError(BioIntelError):
    """Raised when a sequence cannot be parsed or validated."""


class UnsupportedSequenceTypeError(BioIntelError):
    """Raised for unsupported or incompatible sequence types."""


class InvalidSmilesError(BioIntelError):
    """Raised when a molecular SMILES string cannot be parsed or sanitized."""


class FeatureSchemaMismatchError(BioIntelError):
    """Raised when a model and feature extractor use incompatible schemas."""


class DatasetValidationError(BioIntelError):
    """Raised when a DTI dataset does not meet required structure or quality rules."""


class ModelNotFoundError(BioIntelError):
    """Raised when a requested trained model artifact is unavailable."""


class TrainingError(BioIntelError):
    """Raised when DTI model training cannot be completed safely."""
