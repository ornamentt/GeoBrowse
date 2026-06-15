# GeoBrowse

GeoBrowse is a benchmark with open-source system for geography-oriented web browsing and multimodal task solving. Its core inference component is **GATE**, a reasoning framework that coordinates web browsing, visual reasoning, search, file/document utilities, and evaluation helpers.

<img width="1202" height="705" alt="image" src="https://github.com/user-attachments/assets/e1445987-42ec-46b4-9262-a783922eae83" />

## Links
📄 arXiv Paper: https://arxiv.org/abs/2604.04017
🤗 Hugging Face Paper: https://huggingface.co/papers/2604.04017

For more details about the benchmark, data construction pipeline, and evaluation protocol, please refer to the paper.

## What It Does

- Runs task-solving agents over JSONL datasets.
- Uses an LLM/VLM backend through `gpt:*` model names or OpenAI-compatible HTTP endpoints.
- Uses the GATE reasoning framework to coordinate planning, tool use, browser interactions, and answer generation.
- Starts a local Playwright browser service for web tasks.
- Supports DuckDuckGo or Google CSE style search backends.
- Saves per-task session traces and evaluation results as JSONL.
- Includes baseline evaluation scripts and a release-readiness verifier.

## Repository Layout

```text
.
├── run.sh                         # Main entry point for dataset runs
├── .env.example                   # Local configuration template
├── Dockerfile                     # Sandboxed runtime image
├── scripts/verify_open_source_ready.sh
├── System/
│   └── ckv3/
│       ├── agents/                # Core GATE agent abstractions, model wrapper, tools
│       ├── ck_main/               # GATE multi-agent runner
│       ├── ck_web/                # Playwright-backed web agent
│       ├── ck_web/_web/           # Node/Express browser service
│       ├── ck_web2/               # Alternate browser utilities
│       └── ck_vl/                 # Vision-language agent utilities
└── Evaluation/
    └── baseline/                  # Baseline inference/evaluation scripts
```

## Requirements

Recommended:

- Python 3.12
- Node.js 20 or newer
- npm
- Docker, if you want the safer container workflow

System packages commonly used by browser and document workflows:

```bash
sudo apt-get update
sudo apt-get install -y poppler-utils default-jre libreoffice ffmpeg
```

On macOS, install equivalents with Homebrew:

```bash
brew install --cask libreoffice
brew install poppler ffmpeg
```

## Quickstart

### 1. Clone And Enter The Repo

```bash
git clone https://github.com/ornamentt/GeoBrowse.git
cd GeoBrowse
```

### 2. Create Python Environment

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

`requirements.txt` is intentionally broad because the framework includes web, file, vision, model-serving, and evaluation utilities. For a smaller deployment, trim it to the workflows you use.

### 3. Install Browser Service Dependencies

```bash
cd System/ckv3/ck_web/_web
npm install
npx playwright install
cd ../../../..
```

### 4. Configure Secrets Locally

```bash
cp .env.example .env
```

Edit `.env`. Keep it private.

For a basic local run with DuckDuckGo search, you can leave search API keys empty:

```env
SEARCH_BACKEND=DuckDuckGo
```

For GPT/Azure-backed runs, fill the relevant model credentials:

```env
LLM_URL=gpt:gpt-4.1
VLM_URL=gpt:gpt-4.1
AZURE_OPENAI_API_KEY=...
AZURE_OPENAI_ENDPOINT=...
AZURE_OPENAI_API_VERSION=2025-01-01-preview
```

For an OpenAI-compatible vLLM server, point the model URL to your endpoint:

```env
LLM_URL=http://localhost:8080/v1/chat/completions
VLM_URL=http://localhost:8081/v1/chat/completions
```

### 5. Prepare A JSONL Dataset

By default, `run.sh` expects:

```text
data/<DATASET>/<DATASET>.jsonl
```

For the default dataset name:

```text
data/geobrowse_level2/geobrowse_level2.jsonl
```

Minimal example:

```bash
mkdir -p data/geobrowse_level2
cat > data/geobrowse_level2/geobrowse_level2.jsonl <<'JSONL'
{"question":"What is shown in the image?", "image_path":"example.png", "answer":"example answer"}
JSONL
```

Image workflows currently expect `image_path` or `image_url`. Put local image files next to the JSONL or use paths resolvable from the run directory.

### 6. Run

```bash
./run.sh
```

Outputs are written under:

```text
outputs/<DATASET>/<timestamp>.jsonl
```

Override paths without editing the script:

```bash
DATASET=gaia_10 \
DATA_DIR=/path/to/data \
OUTPUT_DIR=/path/to/outputs \
./run.sh
```

## Safer Docker Run

Containerized execution is recommended because model-generated code may run locally.

```bash
docker build -t geobrowse .
mkdir -p outputs
docker run --rm \
  --env-file .env \
  -v "$PWD/data:/app/data:ro" \
  -v "$PWD/outputs:/app/outputs" \
  geobrowse
```

The Docker image runs as a non-root user. You should still treat it as an untrusted-code runtime and avoid mounting sensitive host directories.

## Configuration Reference

`run.sh` loads `.env` if present and then applies defaults. Environment variables always let you override behavior without editing source.

| Variable | Required | Default | Description |
| --- | --- | --- | --- |
| `DATASET` | No | `geobrowse_level2` | Dataset name used to resolve input/output paths. |
| `DATA_DIR` | No | `./data` | Base directory containing dataset folders. |
| `OUTPUT_DIR` | No | `./outputs` | Base output directory. |
| `INPUT_FILE` | No | `$DATA_DIR/$DATASET/$DATASET.jsonl` | Exact JSONL input file path. |
| `OUTPUT_FILE` | No | timestamped JSONL under `$OUTPUT_DIR` | Exact output file path. |
| `LLM_URL` | Yes for model calls | `gpt:gpt-4.1` | Main LLM target. Use `gpt:<model>` or an HTTP endpoint. |
| `VLM_URL` | Yes for vision calls | `gpt:gpt-4.1` | Vision/multimodal model target. |
| `AZURE_OPENAI_API_KEY` | If using Azure | empty | Azure OpenAI key. |
| `AZURE_OPENAI_ENDPOINT` | If using Azure | empty | Azure OpenAI endpoint. |
| `AZURE_OPENAI_API_VERSION` | If using Azure | `2025-01-01-preview` | Azure OpenAI API version. |
| `OPENAI_API_KEY` | If using OpenAI directly | empty | OpenAI API key, depending on backend. |
| `SEARCH_BACKEND` | No | `DuckDuckGo` | Search backend. Use `Google` when using Google CSE. |
| `SEARCH_API_KEY` | If using Google search | empty | Google/SerpAPI style key, depending on tool configuration. |
| `SEARCH_CSE_ID` | If using Google CSE | empty | Google custom search engine ID. |
| `PLAYWRIGHT_BACKEND` | No | `local` | Browser backend, usually `local` or `browserless`. |
| `BROWSERLESS_TOKEN` | If using Browserless | empty | Browserless token. |
| `BROWSERLESS_TARGET_HOST` | If using Browserless | `production-sfo.browserless.io` | Browserless host. |
| `LISTEN_PORT` | No | `3000` | Local web browser service port. |
| `WEB_IP` | No | `localhost:$LISTEN_PORT` | Address used by Python agent to call the browser service. |
| `WEB_SERVICE_FOLDER` | No | `System/ckv3/ck_web/_web` | Node browser service directory. |
| `WEB_COMMAND` | No | `npm start` | Browser service command, executed without a shell. |
| `INFERENCE_TIME_EVALUATION_METHOD` | No | `gpt_judge` | Runtime evaluator mode passed to `ck_main`. |
| `MAX_RETRY_NUM` | No | `3` | Retry count for inference/evaluation modes. |
| `EVALUATION_METRIC` | No | `llm_score` | Evaluation metric, such as `em` or `llm_score`. |
| `SECRET_ID`, `SECRET_KEY`, `REGION`, `BUCKET` | Optional | empty except region | Tencent COS settings for image upload/download workflows. |

## Input Data Format

The runner reads JSON Lines. Each line is one task.

Accepted task fields include:

- `question`
- `Question`
- `task`
- `Task`
- `query`
- `Query`
- `instruction`
- `Instruction`

Optional fields:

- `file_name`: input file associated with the task.
- `image_url` or `image_path`: image input.
- `answer`, `Final answer`, or `true_answer`: gold answer for evaluation.
- `skip`: set to `1` to mark hard queries that can be skipped with `--skip-hard-query`.

Example:

```json
{"question":"Find the text in this image.", "image_path":"sample.png", "answer":"hello"}
```

Output records contain the original task, session trace, model/tool observations, and evaluation fields.

## Browser Service

The web agent talks to a local Node/Express service in:

```text
System/ckv3/ck_web/_web
```

`run.sh` passes this service to the Python agent through:

```text
web_env_kwargs.web_command = "npm start"
web_env_kwargs.web_cwd = "System/ckv3/ck_web/_web"
web_env_kwargs.web_env.LISTEN_PORT = "$LISTEN_PORT"
```

The Python side starts and stops this service as part of the web environment lifecycle. If port `3000` is busy, set:

```bash
LISTEN_PORT=3001 WEB_IP=localhost:3001 ./run.sh
```

## Model Backend Notes

The model wrapper supports several target styles:

- `gpt:<model-name>` for GPT-style configured backends.
- `http://.../v1/chat/completions` for OpenAI-compatible servers such as vLLM.
- Other providers may require additional environment variables supported by `System/ckv3/agents/model.py`.

For self-hosted vLLM, make sure your endpoint accepts OpenAI-compatible chat completion requests and that the served model name matches what your backend expects.

## Evaluation And Baselines

Baseline scripts live in:

```text
Evaluation/baseline
```

Run baseline inference:

```bash
DATASET=gaia_10 ./Evaluation/baseline/run_infer.sh
```

Run baseline evaluation:

```bash
API_KEY=... INPUT_FILE=/path/to/predictions.jsonl ./Evaluation/baseline/run_eval.sh
```

Do not commit evaluation provider keys. Store them in `.env` or pass them through the environment.

## Citation

If you find GeoBrowse useful in your research, please cite:

```bibtex
@misc{geng2026geobrowsegeolocationbenchmarkagentic,
  title={GeoBrowse: A Geolocation Benchmark for Agentic Tool Use with Expert-Annotated Reasoning Traces},
  author={Xinyu Geng and Yanjing Xiao and Yuyang Zhang and Hanwen Wang and Xinyan Liu and Rui Min and Tianqing Fang and Yi R. Fung},
  year={2026},
  eprint={2604.04017},
  archivePrefix={arXiv},
  primaryClass={cs.CL},
  url={https://arxiv.org/abs/2604.04017}
}
```
