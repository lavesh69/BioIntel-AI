from biointel.sequence.dna_analysis import (
    dna_transformations,
    nucleotide_statistics,
    six_frame_translation,
)


def test_gc_content():
    stats = nucleotide_statistics("GGCCATAT")
    assert stats["gc_percent"] == 50.0
    assert stats["at_percent"] == 50.0


def test_reverse_complement():
    assert dna_transformations("ATGC")["reverse_complement"] == "GCAT"


def test_six_frames():
    rows = six_frame_translation("ATGAAATAA")
    assert len(rows) == 6
    assert rows[0]["protein"].startswith("MK")
