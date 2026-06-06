#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SYSTEM_DIR="${ROOT_DIR}/System"

if [[ -f "${ROOT_DIR}/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${ROOT_DIR}/.env"
  set +a
fi

export PYTHONPATH="${SYSTEM_DIR}:${PYTHONPATH:-}"

### Input/output
export DATASET="${DATASET:-geobrowse_level2}"
DATE_STAMP="$(date +%Y%m%d_%H%M)"
DATA_DIR="${DATA_DIR:-${ROOT_DIR}/data}"
OUTPUT_DIR="${OUTPUT_DIR:-${ROOT_DIR}/outputs}"
INPUT_FILE="${INPUT_FILE:-${DATA_DIR}/${DATASET}/${DATASET}.jsonl}"
OUTPUT_FILE="${OUTPUT_FILE:-${OUTPUT_DIR}/${DATASET}/${DATE_STAMP}.jsonl}"
mkdir -p "$(dirname "${OUTPUT_FILE}")"

cd "${SYSTEM_DIR}"

### Browserless/web service
export TAIJI="${TAIJI:-False}"
export PLAYWRIGHT_BACKEND="${PLAYWRIGHT_BACKEND:-local}"
export BROWSERLESS_TARGET_HOST="${BROWSERLESS_TARGET_HOST:-production-sfo.browserless.io}"
export LISTEN_PORT="${LISTEN_PORT:-3000}"
export WEB_IP="${WEB_IP:-localhost:${LISTEN_PORT}}"

### Model
export VLM_URL="${VLM_URL:-gpt:gpt-4.1}"
export LLM_URL="${LLM_URL:-gpt:gpt-4.1}"
export AZURE_OPENAI_API_VERSION="${AZURE_OPENAI_API_VERSION:-2025-01-01-preview}"

### Search/langchain
export SEARCH_BACKEND="${SEARCH_BACKEND:-DuckDuckGo}"
export EVALUATOR_LLM="${EVALUATOR_LLM:-${LLM_URL}}"
export LANGCHAIN_LLM="${LANGCHAIN_LLM:-gpt-4.1}"
export OPENAI_API_TYPE="${OPENAI_API_TYPE:-azure_ai}"
export AZURE_INFERENCE_ENDPOINT="${AZURE_INFERENCE_ENDPOINT:-${AZURE_OPENAI_ENDPOINT:-}}"
export AZURE_INFERENCE_CREDENTIAL="${AZURE_INFERENCE_CREDENTIAL:-${AZURE_OPENAI_API_KEY:-}}"
export TOKENIZERS_PARALLELISM="${TOKENIZERS_PARALLELISM:-false}"

WEB_SERVICE_FOLDER="${WEB_SERVICE_FOLDER:-${SYSTEM_DIR}/ckv3/ck_web/_web}"
WEB_COMMAND="${WEB_COMMAND:-npm start}"

MAIN_ARGS="${MAIN_ARGS:-{'web_agent': {'max_steps': 20, 'model': {'call_target': '${LLM_URL}'}, 'model_multimodal': {'call_target': '${VLM_URL}'}, 'web_env_kwargs': {'web_ip': '${WEB_IP}', 'web_command': '${WEB_COMMAND}', 'web_cwd': '${WEB_SERVICE_FOLDER}', 'web_env': {'LISTEN_PORT': '${LISTEN_PORT}'}}}, 'vl_agent': {'max_steps': 20, 'model': {'call_target': '${LLM_URL}'}, 'model_multimodal': {'call_target': '${VLM_URL}'}}, 'model': {'call_target': '${LLM_URL}'}, 'max_steps': 12}}"

NO_NULL_STDIN="${NO_NULL_STDIN:-1}" python -u -m ckv3.ck_main.main \
  --updates "${MAIN_ARGS}" \
  --inference-time-evaluation-method "${INFERENCE_TIME_EVALUATION_METHOD:-gpt_judge}" \
  --max_retry_num "${MAX_RETRY_NUM:-3}" \
  --evaluation-metric "${EVALUATION_METRIC:-llm_score}" \
  --input "${INPUT_FILE}" \
  --output "${OUTPUT_FILE}"
