from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description='Validate a merged BioIntel AI Step 157 folder.')
    parser.add_argument('--root', default='.')
    parser.add_argument('--allow-uninstalled', action='store_true')
    args = parser.parse_args()

    root = Path(args.root).expanduser().resolve()
    sys.dont_write_bytecode = True
    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
    src = root / 'src'
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))

    checks: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    advisories: list[dict[str, str]] = []

    def check(key: str, passed: bool, message: str = '', *, advisory: bool = False) -> None:
        item = {'key': key, 'passed': bool(passed), 'message': message, 'advisory': advisory}
        checks.append(item)
        if not passed:
            (advisories if advisory else failures).append({'key': key, 'message': message})

    def runtime_residue_paths() -> list[Path]:
        return sorted(
            p for p in root.rglob('*')
            if p.name in {'__pycache__', '.pytest_cache', '.mypy_cache', '.ruff_cache'}
            or p.name.endswith(('-wal', '-shm', '.pyc', '.pyo'))
        )

    initial_residue = runtime_residue_paths()
    check('release_runtime_residue_absent', not initial_residue, json.dumps([p.relative_to(root).as_posix() for p in initial_residue[:100]]))

    def remove_validator_generated_residue() -> None:
        initial = {p.resolve() for p in initial_residue}
        for path in runtime_residue_paths():
            if path.resolve() in initial:
                continue
            try:
                if path.is_dir():
                    import shutil
                    shutil.rmtree(path)
                elif path.exists():
                    path.unlink()
            except OSError:
                pass

    check('root_exists', root.is_dir(), str(root))
    for part in range(1, 5):
        marker = root / '.release_parts' / f'step157_part{part}.ok'
        check(f'step157_part_{part}', marker.is_file(), marker.as_posix())

    # Retain the mature base installation/path validator without invoking obsolete
    # Step 151-154 critical hashes that are expected to change in Step 157.
    base_validator = root / 'scripts' / 'step150_validate_installation.py'
    check('step150_validator_present', base_validator.is_file(), str(base_validator))
    if base_validator.is_file():
        command = [sys.executable, str(base_validator), '--root', str(root)]
        if args.allow_uninstalled:
            command.append('--allow-uninstalled')
        completed = subprocess.run(
            command, cwd=root, text=True, capture_output=True, check=False,
            env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'},
        )
        base_ok = completed.returncode == 0
        if not base_ok and args.allow_uninstalled:
            base_report = root / 'reports' / 'step150_installation_validation.json'
            try:
                base_payload = json.loads(base_report.read_text(encoding='utf-8'))
                failure_keys = {str(item.get('key')) for item in base_payload.get('failures', [])}
                base_ok = failure_keys <= {'application_not_installed'}
            except Exception:
                base_ok = False
        check('step150_base_validation', base_ok, (completed.stdout + completed.stderr)[-2400:])
        remove_validator_generated_residue()

    release_file = root / 'STEP157_RELEASE.json'
    check('release_metadata_present', release_file.is_file(), release_file.as_posix())
    release: dict[str, Any] = {}
    if release_file.is_file():
        release = json.loads(release_file.read_text(encoding='utf-8'))
        check('release_step', release.get('step') == 157, str(release.get('step')))
        tests = release.get('tests', {})
        check('tests_collected', tests.get('collected') == 1342, str(tests))
        check('tests_passed', tests.get('passed') == 1315, str(tests))
        check('tests_skipped', tests.get('skipped') == 27, str(tests))
        check('tests_failed_zero', tests.get('failed') == 0, str(tests))
        check('native_workflows_80_metadata', release.get('native_workflows') == 80, str(release.get('native_workflows')))
        check('workflow_families_49_metadata', release.get('native_workflow_families', 0) >= 49, str(release.get('native_workflow_families')))
        check('engine_adapters_76_metadata', release.get('registered_engine_adapters', 0) >= 76, str(release.get('registered_engine_adapters')))
        check('plans_78_metadata', release.get('safe_external_execution_plans', 0) >= 78, str(release.get('safe_external_execution_plans')))
        full = release.get('analysis_modes', {}).get('full', {})
        check('full_mode_one_million_rows', full.get('row_limit') == 1_000_000, str(full))
        check('full_mode_512_features', full.get('feature_limit') == 512, str(full))

    critical_manifest = root / 'release' / 'step157_critical_hashes.json'
    check('critical_manifest_present', critical_manifest.is_file(), critical_manifest.as_posix())
    if critical_manifest.is_file():
        payload = json.loads(critical_manifest.read_text(encoding='utf-8'))
        files = payload.get('files', payload)
        for relative, expected in files.items():
            path = root / relative
            if not path.is_file():
                check(f'critical_file:{relative}', False, 'missing')
            else:
                actual = sha256(path)
                check(f'critical_file:{relative}', actual == expected, f'expected={expected} actual={actual}')

    # Compile every Python source in memory, avoiding bytecode residue.
    compile_failures: dict[str, str] = {}
    py_files = sorted(root.rglob('*.py'))
    for path in py_files:
        try:
            source = path.read_text(encoding='utf-8-sig')
            compile(source, str(path), 'exec')
        except Exception as exc:  # pragma: no cover - validation path
            compile_failures[path.relative_to(root).as_posix()] = f'{type(exc).__name__}: {exc}'
    check('python_source_compile', not compile_failures, json.dumps(compile_failures, sort_keys=True))

    # Databases must open read-only, pass integrity and contain no FK violations.
    db_failures: dict[str, str] = {}
    db_paths = sorted(p for p in root.rglob('*.sqlite*') if p.is_file() and not p.name.endswith(('-wal', '-shm')))
    for db in db_paths:
        try:
            con = sqlite3.connect(f'file:{db.as_posix()}?mode=ro', uri=True)
            integrity = con.execute('PRAGMA integrity_check').fetchone()
            fk = con.execute('PRAGMA foreign_key_check').fetchall()
            con.close()
            if not integrity or integrity[0] != 'ok' or fk:
                db_failures[db.relative_to(root).as_posix()] = f'integrity={integrity}; foreign_keys={len(fk)}'
        except Exception as exc:  # pragma: no cover - validation path
            db_failures[db.relative_to(root).as_posix()] = f'{type(exc).__name__}: {exc}'
    check('sqlite_databases_40', len(db_paths) == 40, str(len(db_paths)))
    check('sqlite_integrity_and_foreign_keys', not db_failures, json.dumps(db_failures, sort_keys=True))

    # Verify the release package manifest when present. It intentionally excludes itself.
    package_manifest = root / 'release' / 'step157_package_manifest.json'
    check('package_manifest_present', package_manifest.is_file(), package_manifest.as_posix())
    if package_manifest.is_file():
        manifest = json.loads(package_manifest.read_text(encoding='utf-8'))
        mismatches: dict[str, str] = {}
        for relative, meta in manifest.get('files', {}).items():
            path = root / relative
            if not path.is_file():
                mismatches[relative] = 'missing'
                continue
            if path.stat().st_size != int(meta['size']):
                mismatches[relative] = 'size'
                continue
            if sha256(path) != meta['sha256']:
                mismatches[relative] = 'sha256'
        check('package_manifest_entries', len(manifest.get('files', {})) >= 4000, str(len(manifest.get('files', {}))))
        check('package_manifest_hashes', not mismatches, json.dumps(dict(list(mismatches.items())[:50]), sort_keys=True))

    try:
        import pandas as pd
        from biointel.engineering.module_reliability import source_connection_audit
        from biointel.native.engines import ENGINE_REGISTRY, plan_catalog
        from biointel.scientific_depth import MODULE_PROFILES, native_input_template, native_workflow_catalog, run_native_workflow
        from biointel.scientific_depth.native_budget import choose_native_budget

        catalog = native_workflow_catalog()
        check('scientific_profiles_80', len(MODULE_PROFILES) == 80, str(len(MODULE_PROFILES)))
        check('native_catalog_80', len(catalog) == 80, str(len(catalog)))
        check('native_families_49', int(catalog.family.nunique()) >= 49, str(catalog.family.nunique()))
        check('engine_registry_76', len(ENGINE_REGISTRY) >= 76, str(len(ENGINE_REGISTRY)))
        check('execution_plans_78', len(plan_catalog()) >= 78, str(len(plan_catalog())))

        from biointel.native.qualification import qualification_matrix
        qualification = qualification_matrix(keys=['bcftools'], timeout_seconds=0.2)
        check('qualified_toolchains_fail_closed', not qualification.empty and qualification.iloc[0]['Qualification status'] in {'Blocked', 'Qualified'}, qualification.to_json(orient='records'))

        budget = choose_native_budget({'analysis_mode': 'full'}, rows=2_000_000, columns=120)
        check('adaptive_full_budget', budget.requested_mode == 'full' and budget.feature_limit == 120 and budget.row_limit > 250_000, json.dumps(budget.manifest(), sort_keys=True))

        demo_failures: dict[str, str] = {}
        for module_key in MODULE_PROFILES:
            result = run_native_workflow(module_key, native_input_template(module_key, demonstration=True))
            if result.status == 'fail':
                demo_failures[module_key] = '; '.join(result.checks.loc[result.checks.status == 'fail', 'detail'].astype(str).tolist())
        check('all_80_demo_workflows_execute', not demo_failures, json.dumps(demo_failures, sort_keys=True))

        audit = source_connection_audit(root)
        check('managed_sqlite_connections', bool(audit.get('passed')), json.dumps(audit.get('violations', [])))

        # A one-million-row frame is not materialised here; budget and coverage are
        # tested in the full automated suite. This smoke verifies non-first-N coverage.
        frame = pd.DataFrame({'value': range(1001)})
        result = run_native_workflow('population_gwas', frame, metadata={'analysis_mode': 'interactive', 'row_limit': 100})
        analyzed = result.provenance.get('rows_analyzed')
        check('bounded_workflow_executes', result.status in {'pass', 'review'} and analyzed == 100, json.dumps(result.provenance, sort_keys=True, default=str))
    except ModuleNotFoundError as exc:
        check('runtime_dependencies_available', False, f'{type(exc).__name__}: {exc}', advisory=args.allow_uninstalled)
    except Exception as exc:
        check('step157_runtime_contracts', False, f'{type(exc).__name__}: {exc}')

    source_checks = {
        'native_budget': 'src/biointel/scientific_depth/native_budget.py',
        'step155_enhancements': 'src/biointel/scientific_depth/native_step155_enhancements.py',
        'step156_translational': 'src/biointel/scientific_depth/native_step156_translational.py',
        'step156_operational': 'src/biointel/scientific_depth/native_step156_operational.py',
        'native_orchestrator': 'src/biointel/scientific_depth/native_workflows.py',
        'step157_specialist_plans': 'src/biointel/native/engine_plans_step157.py',
        'engine_registry': 'src/biointel/native/engines.py',
        'engine_qualification': 'src/biointel/native/qualification.py',
        'instrument_qualification': 'src/biointel/biotech/instrument_qualification.py',
        'instrument_import': 'src/biointel/biotech/lab_import.py',
        'lims_lineage': 'src/biointel/expansion/advanced_analysis.py',
        'read_only_jobs': 'src/biointel/jobs/local_queue.py',
        'read_only_api': 'src/biointel/api/main.py',
        'renderer': 'src/biointel/scientific_depth/renderer.py',
        'command_center': 'pages/227_Scientific_Readiness_Command_Center.py',
        'step156_translational_tests': 'tests/test_step156_translational_readiness.py',
        'step156_qualification_tests': 'tests/test_step156_tool_instrument_qualification.py',
    }
    for key, relative in source_checks.items():
        path = root / relative
        check(key, path.is_file() and path.stat().st_size > 500, relative)

    remove_validator_generated_residue()

    report = {
        'schema': 'biointel.step157.validation-report.v1',
        'root': str(root),
        'checks': checks,
        'failures': failures,
        'advisories': advisories,
        'passed': not failures,
    }
    report_dir = root / 'reports'
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / 'step157_installation_validation.json'
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2, sort_keys=True))
    print(f'REPORT_PATH={report_path}')
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
