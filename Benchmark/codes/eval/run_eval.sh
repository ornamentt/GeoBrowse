export API_KEY=""
export BASE_URL="https://api-inference.modelscope.cn/v1/"
export JUDGE_MODEL="Qwen/Qwen2.5-72B-Instruct"
export MAX_WORKERS=8

input_file=""

python Benchmark/codes/eval/evaluate.py \
    --input_fp $input_file
