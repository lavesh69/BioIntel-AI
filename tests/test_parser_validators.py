import pytest

from biointel.sequence.parser import parse_sequence_text
from biointel.sequence.validators import SequenceType, detect_sequence_type, validate_for_type
from biointel.utils.exceptions import InvalidSequenceError


def test_parse_fasta():
    parsed = parse_sequence_text(">abc\nATG C\n")
    assert parsed.header == "abc"
    assert parsed.sequence == "ATGC"


def test_empty_rejected():
    with pytest.raises(InvalidSequenceError):
        parse_sequence_text("   ")


def test_ambiguous_detection():
    assert detect_sequence_type("ATGC").detected_type == SequenceType.AMBIGUOUS


def test_invalid_positions():
    assert validate_for_type("ATG#", SequenceType.DNA) == ((4, "#"),)
