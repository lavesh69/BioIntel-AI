.PHONY: bootstrap test unit integration scientific quality final docs release
bootstrap:
	python scripts/bootstrap.py --dev
unit:
	pytest -q -m "not integration and not e2e and not visual"
integration:
	pytest -q tests/integration
scientific:
	pytest -q tests/scientific
test: unit integration scientific
quality:
	PYTHONPATH=src python scripts/engineering_quality_gate.py --json-output reports/engineering_quality.json
final:
	PYTHONPATH=src python scripts/qualify_step43_final.py
docs:
	mkdocs build --strict
release:
	SOURCE_DATE_EPOCH=1577836800 PYTHONPATH=src python scripts/build_reproducible_release.py --output dist/biointel-release.zip
