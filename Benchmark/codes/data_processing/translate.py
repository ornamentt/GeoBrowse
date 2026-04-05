import json
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, Iterable
from tqdm import tqdm
from openai import OpenAI

MODEL_NAME = "Qwen/Qwen2.5-32B-Instruct"
DASHSCOPE_BASE_URL = os.getenv("DASHSCOPE_BASE_URL", "https://api-inference.modelscope.cn/v1/")
DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "")
if not DASHSCOPE_API_KEY:
    raise RuntimeError("Environment variable DASHSCOPE_API_KEY is not set.")

client = OpenAI(api_key=DASHSCOPE_API_KEY, base_url=DASHSCOPE_BASE_URL)

# ---------------------------
# 1) 简短翻译 prompt（你要的）
# ---------------------------
TRANSLATE_PROMPT = (
    "Translate the following Chinese text to natural, fluent English. "
    "Preserve names, numbers, units, and punctuation. Output ONLY the translation.\n\n"
    "Text:\n{src}"
)

# ---------------------------
# 2) 中文检测
# ---------------------------
_CHINESE_RE = re.compile(r"[\u4e00-\u9fff]")

def contains_chinese(s: str) -> bool:
    return bool(_CHINESE_RE.search(s))


# ---------------------------
# 3) DashScope 接口
# ---------------------------
def translate_zh_to_en(text: str, *, model: str = MODEL_NAME, max_retries: int = 3) -> str:
    if not isinstance(text, str) or not text.strip():
        return text

    for attempt in range(1, max_retries + 1):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": TRANSLATE_PROMPT},
                    {"role": "user", "content": text},
                ],
                temperature=0.0,
                extra_body={"enable_thinking": False},
            )
            out = resp.choices[0].message.content or ""
            return out.strip()
        except Exception as e:
            if attempt == max_retries:
                return text
            time.sleep(0.8 * attempt)


# ---------------------------
# 4) JSONL: 翻译指定 keys
# ---------------------------
def _translate_value_if_needed(
    key: str,
    value: Any,
    translator,
    skip_if_no_chinese: bool,
) -> Any:
    """
    value 支持 str / list[str] / 其他（原样返回）
    skip_if_no_chinese: True -> 若完全不含中文则跳过翻译
    """
    if isinstance(value, str):
        if skip_if_no_chinese and (not contains_chinese(value)):
            return value
        # 对于其它字段：只要含中文就整体翻译（满足“中文内容翻译成英文”）
        if contains_chinese(value):
            return translator(value)
        return value

    if isinstance(value, list):
        out = []
        for item in value:
            if isinstance(item, str):
                if skip_if_no_chinese and (not contains_chinese(item)):
                    out.append(item)
                else:
                    out.append(translator(item) if contains_chinese(item) else item)
            else:
                out.append(item)
        return out

    return value


def translate_keys_in_jsonl(
    input_jsonl: str,
    output_jsonl: str,
    keys_to_translate: Iterable[str] = ("prompt", "gold_image_answer", "gold_text_answer", "image_solution", "text_solution"),
):
    """
    - 翻译 keys_to_translate 中的中文到英文
    - gold_image_answer / gold_text_answer 若无中文则不翻译（按你的规则）
    """
    keys_to_translate = set(keys_to_translate)
    gold_skip_keys = {"gold_image_answer", "gold_text_answer"}

    def translator(text: str) -> str:
        return translate_zh_to_en(text)

    in_path = Path(input_jsonl)
    out_path = Path(output_jsonl)
    done = 0
    
    with in_path.open("r", encoding="utf-8") as f:
        total = sum(1 for _ in f)
    with out_path.open("r", encoding="utf-8") as f:
        done = sum(1 for _ in f)


    with open(input_jsonl, "r", encoding="utf-8") as fin, open(output_jsonl, "a", encoding="utf-8") as fout:


        for line_no, line in enumerate(tqdm(fin, total=total, desc="Translating JSONL")):
            if line_no < done:
                continue

            line = line.strip()
            if not line:
                continue
            obj: Dict[str, Any] = json.loads(line)

            for k in list(obj.keys()):
                if k in keys_to_translate:
                    obj[k] = _translate_value_if_needed(
                        key=k,
                        value=obj[k],
                        translator=translator,
                        skip_if_no_chinese=(k in gold_skip_keys),
                    )

            fout.write(json.dumps(obj, ensure_ascii=False) + "\n")


# ---------------------------
# 5) 你的路径直接跑
# ---------------------------
if __name__ == "__main__":
    translate_keys_in_jsonl(
        input_jsonl="/Users/gengxinyu/Documents/codes/GeoBrowse/Benchmark/data/level1/level1_zh_1.jsonl",
        output_jsonl="/Users/gengxinyu/Documents/codes/GeoBrowse/Benchmark/data/level1/level1_en_1.jsonl"
    )
