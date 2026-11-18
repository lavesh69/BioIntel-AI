from .profiles import MODULE_PROFILES, ModuleDepthProfile, profile_for
from .assessment import DepthAssessment, assess_dataframe, bh_fdr
from .evidence_readiness import (
    EvidenceReadiness,
    EvidenceRequirement,
    assess_evidence_readiness,
    build_evidence_manifest_template,
)
from .portfolio import scientific_portfolio_catalog, scientific_portfolio_manifest, scientific_portfolio_summary
from .native_workflows import (
    MAX_NATIVE_ROWS,
    NativeRunResult,
    NativeWorkflowSpec,
    is_native_engine,
    native_engine_status,
    native_input_template,
    native_template_manifest,
    native_portfolio_manifest,
    native_workflow_catalog,
    native_workflow_spec,
    run_native_workflow,
)
from .readiness_matrix import ModuleReadinessRecord, portfolio_readiness_matrix, readiness_summary
from .streaming_profile import OnlineNumericState, StreamingProfileResult, profile_tabular_file
from .toolchain_readiness import (
    detect_specialist_toolchains,
    reference_readiness,
    toolchain_summary,
)
from .capability import (
    CAPABILITY_SPECS,
    CapabilityAssessment,
    ModuleCapabilitySpec,
    PipelineStage,
    assess_capability,
    capability_spec_for,
)


def engine_status_frame(*args, **kwargs):
    """Lazy UI import keeps scientific assessment usable in CLI/API contexts."""
    from .renderer import engine_status_frame as implementation

    return implementation(*args, **kwargs)


def render_depth_upgrade_panel(*args, **kwargs):
    """Lazy Streamlit import prevents UI dependencies from blocking core science."""
    from .renderer import render_depth_upgrade_panel as implementation

    return implementation(*args, **kwargs)


__all__ = [
    "MODULE_PROFILES",
    "ModuleDepthProfile",
    "DepthAssessment",
    "assess_dataframe",
    "bh_fdr",
    "profile_for",
    "render_depth_upgrade_panel",
    "engine_status_frame",
    "CAPABILITY_SPECS",
    "CapabilityAssessment",
    "ModuleCapabilitySpec",
    "PipelineStage",
    "assess_capability",
    "capability_spec_for",
    "EvidenceReadiness",
    "EvidenceRequirement",
    "assess_evidence_readiness",
    "build_evidence_manifest_template",
    "scientific_portfolio_catalog",
    "scientific_portfolio_summary",
    "scientific_portfolio_manifest",
    "MAX_NATIVE_ROWS",
    "NativeRunResult",
    "NativeWorkflowSpec",
    "is_native_engine",
    "native_engine_status",
    "native_input_template",
    "native_template_manifest",
    "native_portfolio_manifest",
    "native_workflow_catalog",
    "native_workflow_spec",
    "run_native_workflow",
    "ModuleReadinessRecord",
    "portfolio_readiness_matrix",
    "readiness_summary",
    "OnlineNumericState",
    "StreamingProfileResult",
    "profile_tabular_file",
    "detect_specialist_toolchains",
    "reference_readiness",
    "toolchain_summary",
]
