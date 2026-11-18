from biointel.sequence.protein_analysis import hydropathy_profile, protein_statistics


def test_protein_properties():
    stats = protein_statistics("MKWVTFISLLFLFSSAYSR")
    assert stats["length"] == 19
    assert stats["molecular_weight"] > 0
    assert stats["warning"] is None


def test_ambiguous_disables_properties():
    stats = protein_statistics("MKX")
    assert stats["warning"] is not None
    assert "molecular_weight" not in stats


def test_hydropathy():
    rows = hydropathy_profile("MKWVTFISL", 3)
    assert len(rows) == 7
