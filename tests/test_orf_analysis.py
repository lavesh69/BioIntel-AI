from biointel.sequence.orf_analysis import find_orfs


def test_orf_coordinates():
    rows = find_orfs("CCCATGAAATAAGGG", min_length_nt=9)
    assert rows[0]["start"] == 4
    assert rows[0]["end"] == 12
    assert rows[0]["protein_sequence"] == "MK"
