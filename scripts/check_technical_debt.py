from pathlib import Path

from biointel.engineering.quality_gates import check_technical_debt

if __name__ == "__main__":
    result = check_technical_debt(Path("."))
    print(result.evidence)
    raise SystemExit(0 if result.passed else 1)
