#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

if [[ -f "${ROOT_DIR}/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${ROOT_DIR}/.env"
  set +a
fi

: "${API_KEY:?Set API_KEY in the environment or .env before running evaluation.}"

export BASE_URL="${BASE_URL:-https://api-inference.modelscope.cn/v1/}"
export JUDGE_MODEL="${JUDGE_MODEL:-Qwen/Qwen2.5-32B-Instruct}"
export MAX_WORKERS="${MAX_WORKERS:-8}"

INPUT_FILE="${INPUT_FILE:-${ROOT_DIR}/data/eval/input.jsonl}"

python "${ROOT_DIR}/Evaluation/baseline/evaluate.py" \
  --input_fp "${INPUT_FILE}"
