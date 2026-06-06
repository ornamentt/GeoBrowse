#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

if [[ -f "${ROOT_DIR}/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${ROOT_DIR}/.env"
  set +a
fi

export PYTHONPATH="${ROOT_DIR}/System:${PYTHONPATH:-}"
export DATASET="${DATASET:-gaia_10}"
DATE_STAMP="$(date +%Y%m%d_%H%M)"
DATA_DIR="${DATA_DIR:-${ROOT_DIR}/data}"
OUTPUT_DIR="${OUTPUT_DIR:-${ROOT_DIR}/outputs/baseline}"
INPUT_FILE="${INPUT_FILE:-${DATA_DIR}/${DATASET}/${DATASET}.jsonl}"
OUTPUT_FILE="${OUTPUT_FILE:-${OUTPUT_DIR}/${DATASET}/${DATE_STAMP}.jsonl}"

export LLM_URL="${LLM_URL:-gpt:gpt-4.1}"
export AZURE_OPENAI_API_VERSION="${AZURE_OPENAI_API_VERSION:-2025-01-01-preview}"

mkdir -p "$(dirname "${OUTPUT_FILE}")"

python "${ROOT_DIR}/Evaluation/baseline/infer_baseline.py" \
  -i "${INPUT_FILE}" \
  -o "${OUTPUT_FILE}"
