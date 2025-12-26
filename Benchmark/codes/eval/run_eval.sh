export API_KEY="ms-4fcc0072-2e28-4428-9812-cbc7603ac9e9"
export BASE_URL="https://api-inference.modelscope.cn/v1/"
export JUDGE_MODEL="Qwen/Qwen2.5-72B-Instruct"
export MAX_WORKERS=8

input_file=/Users/gengxinyu/Documents/codes/GeoBrowse/level1_en.jsonl

python Benchmark/codes/eval/evaluate.py \
    --input_fp $input_file