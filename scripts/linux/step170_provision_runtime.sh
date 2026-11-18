#!/usr/bin/env bash
set -uo pipefail
ROOT="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
ENV_NAME="${BIOINTEL_STEP170_ENV:-biointel-step170}"
export MAMBA_ROOT_PREFIX="${MAMBA_ROOT_PREFIX:-$HOME/.local/share/biointel-micromamba}"
export PATH="$HOME/.local/bin:$PATH"
PLAN="$ROOT/data/step170/environment/step170-install-plan.tsv"
REPORT="$ROOT/reports/step170_wsl_install_results.jsonl"
mkdir -p "$ROOT/reports"
: > "$REPORT"

if ! command -v micromamba >/dev/null 2>&1; then
  echo "micromamba not found" >&2
  exit 2
fi
if [[ ! -f "$PLAN" ]]; then
  echo "Install plan missing: $PLAN" >&2
  exit 2
fi

micromamba create -y -n "$ENV_NAME" -c conda-forge -c bioconda --strict-channel-priority python=3.11 >/dev/null || exit 3

total=0
passed=0
failed=0
manual=0
while IFS=$'\t' read -r engine conda_packages pip_packages manual_distribution; do
  [[ "$engine" == "engine" ]] && continue
  total=$((total+1))
  if [[ "$manual_distribution" == "1" ]]; then
    manual=$((manual+1))
    printf '{"engine":"%s","status":"manual-provider-action-required"}\n' "$engine" >> "$REPORT"
    continue
  fi
  rc=0
  if [[ -n "$conda_packages" ]]; then
    IFS=',' read -ra pkgs <<< "$conda_packages"
    args=()
    for pkg in "${pkgs[@]}"; do
      pkg="${pkg#${pkg%%[![:space:]]*}}"; pkg="${pkg%${pkg##*[![:space:]]}}"
      [[ -n "$pkg" ]] && args+=("$pkg")
    done
    if ((${#args[@]})); then
      micromamba install -y -n "$ENV_NAME" -c conda-forge -c bioconda --strict-channel-priority "${args[@]}" || rc=$?
    fi
  elif [[ -n "$pip_packages" ]]; then
    IFS=',' read -ra pkgs <<< "$pip_packages"
    args=()
    for pkg in "${pkgs[@]}"; do
      pkg="${pkg#${pkg%%[![:space:]]*}}"; pkg="${pkg%${pkg##*[![:space:]]}}"
      [[ -n "$pkg" ]] && args+=("$pkg")
    done
    if ((${#args[@]})); then
      micromamba run -n "$ENV_NAME" python -m pip install --upgrade "${args[@]}" || rc=$?
    fi
  fi
  if [[ $rc -eq 0 ]]; then
    passed=$((passed+1))
    printf '{"engine":"%s","status":"package-install-completed"}\n' "$engine" >> "$REPORT"
  else
    failed=$((failed+1))
    printf '{"engine":"%s","status":"package-install-failed","return_code":%d}\n' "$engine" "$rc" >> "$REPORT"
  fi
done < "$PLAN"

micromamba run -n "$ENV_NAME" python "$ROOT/scripts/step170_runtime_manager.py" --root "$ROOT" --environment "$ENV_NAME" || true
printf '{"summary":true,"total":%d,"automatic_passed":%d,"automatic_failed":%d,"manual":%d}\n' "$total" "$passed" "$failed" "$manual" >> "$REPORT"
[[ $failed -eq 0 ]]
