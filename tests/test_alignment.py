from biointel.sequence.alignment import align_sequences


def test_global_alignment():
    result = align_sequences("ATGC", "ATCC", "DNA")
    assert result["score"] > 0
    assert result["identities"] == 3
    assert result["identity_percent"] == 75.0


def test_protein_alignment():
    result = align_sequences("MKWV", "MKWV", "Protein")
    assert result["identities"] == 4
    assert result["identity_percent"] == 100.0
