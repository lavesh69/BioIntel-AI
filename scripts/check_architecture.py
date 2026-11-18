from pathlib import Path

from biointel.engineering.quality_gates import check_architecture

if __name__ == "__main__":
    result = check_architecture(Path("."))
    print(result.evidence)
    raise SystemExit(0 if result.passed else 1)
