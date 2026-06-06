#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

if [[ -n "$(git status --short)" ]]; then
  echo "ERROR: working tree is not clean." >&2
  git status --short >&2
  exit 1
fi

echo "Checking shell syntax..."
bash -n run.sh Evaluation/baseline/run_eval.sh Evaluation/baseline/run_infer.sh

echo "Checking Python syntax..."
python3 -m py_compile \
  System/ckv3/ck_main/main.py \
  System/ckv3/ck_web/main.py \
  System/ckv3/ck_web/utils.py \
  System/ckv3/ck_web2/cookies.py

echo "Checking tracked generated artifacts..."
tracked_generated="$(git ls-files '*__pycache__*' '*node_modules*' '*screenshots*' '*quicksort_bin' '*.pyc')"
if [[ -n "${tracked_generated}" ]]; then
  echo "ERROR: generated artifacts are tracked:" >&2
  echo "${tracked_generated}" >&2
  exit 1
fi

generic_secret_pattern='(AKIA[0-9A-Z]{16}|AKID[0-9A-Za-z]{20,}|sk-[A-Za-z0-9_-]{20,}|AIza[0-9A-Za-z_-]{20,}|private:[^@]+@|BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY)'
p_apd="$(printf '%s' 'apd''cephfs')"
p_share="$(printf '%s' 'share_''1603164')"
p_data_datasets="/data/$(printf '%s' 'datasets')"
p_data_output="/data/$(printf '%s' 'output')"
p_mnt="/mnt/$(printf '%s' 'd')/"
p_ip_a="$(printf '%s' '29')\\.81"
p_ip_b="$(printf '%s' '9')\\.135"
p_conda="file:///home/$(printf '%s' 'con''da')"
p_users="/$(printf '%s' 'Users')/"
internal_path_pattern="(${p_apd}|${p_share}|${p_data_datasets}|${p_data_output}|${p_mnt}|${p_ip_a}|${p_ip_b}|${p_conda}|${p_users})"

echo "Scanning current tree for internal paths..."
if rg -n --glob '!**/.git/**' --glob '!**/node_modules/**' --glob '!**/__pycache__/**' --glob '!**/*.pyc' --glob '!scripts/verify_open_source_ready.sh' "${internal_path_pattern}" .; then
  echo "ERROR: internal path or private endpoint found in current tree." >&2
  exit 1
fi

echo "Scanning current tree for generic secret patterns..."
if rg -n --glob '!**/.git/**' --glob '!**/node_modules/**' --glob '!**/__pycache__/**' --glob '!**/*.pyc' --glob '!scripts/verify_open_source_ready.sh' "${generic_secret_pattern}" .; then
  echo "ERROR: generic secret pattern found in current tree." >&2
  exit 1
fi

echo "Scanning Git history for internal paths..."
if git grep -n -I -E "${internal_path_pattern}" "$(git rev-list --all)" -- . ':!scripts/verify_open_source_ready.sh'; then
  echo "ERROR: internal path or private endpoint found in Git history." >&2
  exit 1
fi

echo "Scanning Git history for generic secret patterns..."
if git grep -n -I -E "${generic_secret_pattern}" "$(git rev-list --all)" -- . ':!scripts/verify_open_source_ready.sh'; then
  echo "ERROR: generic secret pattern found in Git history." >&2
  exit 1
fi

if command -v gitleaks >/dev/null 2>&1; then
  echo "Running gitleaks..."
  gitleaks detect --source "${ROOT_DIR}" --no-banner --redact --verbose
elif [[ -x /root/go/bin/gitleaks ]]; then
  echo "Running gitleaks..."
  /root/go/bin/gitleaks detect --source "${ROOT_DIR}" --no-banner --redact --verbose
else
  echo "WARNING: gitleaks not found; install it and rerun before publishing." >&2
fi

echo "Open-source readiness checks passed."
