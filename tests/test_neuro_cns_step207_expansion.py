from __future__ import annotations

import pandas as pd
import pytest

from biointel.neuro_cns.catalog import MODULES
from biointel.neuro_cns.translational_v207 import (
    FEATURES,
    brain_network_vulnerability_analysis,
    cognitive_trajectory_analysis,
    demo_frame,
    digital_neurology_sensor_analysis,
    fluid_biomarker_panel,
    neurodevelopmental_trajectory_analysis,
    neuroimmune_interaction_analysis,
    neurorehabilitation_response_analysis,
    neurovascular_research_profile,
    polypharmacy_cns_burden,
    sleep_circadian_profile,
)
from biointel.neuro_cns.visuals_v207 import figures_for


FUNCTIONS = {
    "neurovascular_research": neurovascular_research_profile,
    "sleep_circadian": sleep_circadian_profile,
    "fluid_biomarkers": fluid_biomarker_panel,
    "digital_neurology": digital_neurology_sensor_analysis,
    "neuroimmune_interactions": neuroimmune_interaction_analysis,
    "cognitive_trajectory": cognitive_trajectory_analysis,
    "neurorehabilitation": neurorehabilitation_response_analysis,
    "polypharmacy_cns": polypharmacy_cns_burden,
    "brain_network_vulnerability": brain_network_vulnerability_analysis,
    "neurodevelopmental_trajectory": neurodevelopmental_trajectory_analysis,
}


def test_catalog_has_all_41_unique_neuro_modules() -> None:
    assert len(MODULES) == 41
    keys = [module.key for module in MODULES]
    assert len(keys) == len(set(keys))
    assert {key for key, _, _ in FEATURES}.issubset(keys)


@pytest.mark.parametrize("feature_key", sorted(FUNCTIONS))
def test_all_step207_neuro_demos_execute_with_real_tables_and_visuals(feature_key: str) -> None:
    frame = demo_frame(feature_key)
    assert isinstance(frame, pd.DataFrame)
    assert not frame.empty
    result = FUNCTIONS[feature_key](frame)
    assert isinstance(result, dict)
    assert "scientific_boundary" in result
    assert "diagnos" in result["scientific_boundary"].lower() or "clinical" in result["scientific_boundary"].lower()
    tables = [value for value in result.values() if isinstance(value, pd.DataFrame)]
    assert tables
    assert all(not table.empty for table in tables)
    figures = figures_for(feature_key, result)
    assert figures
    for figure in figures.values():
        assert len(figure.data) >= 1


def test_sleep_requires_sufficient_time_points() -> None:
    with pytest.raises(ValueError, match="48"):
        sleep_circadian_profile(pd.DataFrame({"timestamp": pd.date_range("2025-01-01", periods=12, freq="h"), "activity": range(12)}))


def test_biomarker_requires_exactly_two_groups() -> None:
    with pytest.raises(ValueError, match="exactly two"):
        fluid_biomarker_panel(pd.DataFrame({"group": ["A", "B", "C"], "marker": [1.0, 2.0, 3.0]}))


def test_network_rejects_non_square_matrix() -> None:
    with pytest.raises(ValueError, match="square"):
        brain_network_vulnerability_analysis(pd.DataFrame([[1, 2, 3], [4, 5, 6]]))


def test_neurovascular_missing_required_columns_is_friendly() -> None:
    with pytest.raises(ValueError, match="Missing required column"):
        neurovascular_research_profile(pd.DataFrame({"age": [60]}))
