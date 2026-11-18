from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


def main() -> int:
    parser = argparse.ArgumentParser(description='Merge isolated Step 157 AppTest batch reports.')
    parser.add_argument('--root', default='.')
    parser.add_argument('--batch-dir', default='reports/app_batches')
    parser.add_argument('--output', default='reports/step157_all_pages_app_test.json')
    args = parser.parse_args()

    root = Path(args.root).expanduser().resolve()
    batch_dir = Path(args.batch_dir)
    if not batch_dir.is_absolute():
        batch_dir = root / batch_dir
    output = Path(args.output)
    if not output.is_absolute():
        output = root / output

    expected = ['app.py'] + [p.relative_to(root).as_posix() for p in sorted((root / 'pages').glob('*.py'), key=lambda p: p.name.casefold())]
    by_page: dict[str, dict[str, Any]] = {}
    source_reports: list[str] = []
    duplicates: list[str] = []
    for report in sorted(batch_dir.glob('batch_*.json')):
        payload = json.loads(report.read_text(encoding='utf-8'))
        source_reports.append(report.relative_to(root).as_posix())
        for result in payload.get('results', []):
            page = str(result.get('page', ''))
            if page in by_page:
                duplicates.append(page)
            by_page[page] = result

    missing = [page for page in expected if page not in by_page]
    unexpected = sorted(set(by_page) - set(expected))
    ordered_results = [by_page[page] for page in expected if page in by_page]
    failures = [item for item in ordered_results if not bool(item.get('passed'))]
    payload = {
        'schema': 'biointel.step157.all-pages-app-test-merged.v1',
        'generated_at_utc': datetime.now(timezone.utc).isoformat(),
        'pages_expected': len(expected),
        'pages_collected': len(ordered_results),
        'passed': sum(bool(item.get('passed')) for item in ordered_results),
        'failed': len(failures),
        'timeouts': sum(bool(item.get('timed_out')) for item in ordered_results),
        'missing': missing,
        'unexpected': unexpected,
        'duplicates': sorted(set(duplicates)),
        'source_reports': source_reports,
        'results': ordered_results,
        'complete': not missing and not unexpected and not duplicates and not failures,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print(json.dumps({k: payload[k] for k in ('pages_expected','pages_collected','passed','failed','timeouts','missing','unexpected','duplicates','complete')}, indent=2))
    print(f'REPORT_PATH={output}')
    return 0 if payload['complete'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
