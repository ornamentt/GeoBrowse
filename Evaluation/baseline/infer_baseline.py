#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Run LLM inference over a JSONL file and write outputs to JSONL.
- Read each line as JSON object
- Build messages (prefer obj["messages"]; fallback to obj["prompt"]/["question"]/["text"])
- Call LLM(...)
- Save model output to obj["gen"]
"""
import base64
import argparse
import json
import os
import sys
import mimetypes
import time
from typing import Any, Dict, List, Optional
from model import LLM
from pathlib import Path

def _guess_mime(image_path: str) -> str:
    mime, _ = mimetypes.guess_type(image_path)
    # 兜底：常见图片类型
    return mime or "image/jpeg"

def _load_jsonl(path: str):
    with open(path, "r", encoding="utf-8") as f:
        for ln, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                yield ln, json.loads(line)
            except Exception as e:
                yield ln, {"__parse_error__": str(e), "__raw__": line}


def _dump_jsonl_line(f, obj: Dict[str, Any]):
    f.write(json.dumps(obj, ensure_ascii=False) + "\n")

def _encode_image_to_data_url(image_path: str) -> str:
    p = Path(image_path)
    if not p.exists() or not p.is_file():
        raise FileNotFoundError(f"image_path not found: {image_path}")

    mime = _guess_mime(str(p))
    b64 = base64.b64encode(p.read_bytes()).decode("utf-8")
    return f"data:{mime};base64,{b64}"

def _build_messages(
    obj: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    Priority:
      1) if obj["messages"] exists -> use it directly
      2) else use first existing key in user_key_priority: prompt/question/text/input/query
    """
    if isinstance(obj.get("messages"), list) and obj["messages"]:
        return obj["messages"]

    question = obj.get("Question") or obj.get("question")
    if question is None:
        # 给一个更稳的兜底优先级（可按你需要删改）
        for k in ("prompt", "input", "query", "text"):
            if obj.get(k):
                question = obj.get(k)
                break

    image_path = obj.get("image_path") or obj.get("image") or obj.get("img_path")

    if not question:
        raise ValueError("Missing question text in obj (Question/question/prompt/input/query/text).")
    if not image_path:
        raise ValueError("Missing image_path in obj (image_path/image/img_path).")
    
    image_data_url = _encode_image_to_data_url(image_path)
    system_prompt = "Give the answer based on the image and the prompt provided concisely. Your output can only consist of a short number or word!"
    user_content = [
        {"type": "text", "text": "Your output can only consist of a short number or word!\nQuestion: " + str(question)},
        {"type": "image_url", "image_url": {"url": image_data_url}},
    ]
    messages: List[Dict[str, Any]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": user_content})
    return messages

def _build_judge_messages(gen_text: str, ans_text: str) -> List[Dict[str, Any]]:
    """
    Force judge to output ONLY 1 or 0.
    """
    system_prompt = "You are a strict judge."
    prompt = ("You are a strict judge. Compare the model prediction and the ground-truth answer. "
        "If they are semantically equivalent for the task, output 1; otherwise output 0. "
        "Output must be exactly one character: 1 or 0. No other text.")
    user_prompt = prompt + f"Prediction: {gen_text}\nGroundTruth: {ans_text}\nOutput:"
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

def _parse_corr(resp: Any) -> Optional[int]:
    """
    Robustly parse judge output to 0/1.
    """
    if resp is None:
        return None
    s = str(resp).strip()
    # 兼容一些 LLM 可能输出 "1\n" 或 "Answer: 1"
    if "1" in s and "0" not in s:
        return 1
    if "0" in s and "1" not in s:
        return 0
    # 最严格：取首个 0/1
    for ch in s:
        if ch == "1":
            return 1
        if ch == "0":
            return 0
    return None
 


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", "-i", required=True, help="input jsonl path")
    ap.add_argument("--output", "-o", required=True, help="output jsonl path")
    ap.add_argument("--call_target", default=os.getenv("LLM_URL", "gpt:gpt-4o-mini"),
                    help='LLM call_target, e.g. "gpt:gpt-4o-mini" / "request:http://..." / "manual"')
    ap.add_argument("--max_tokens", type=int, default=4096, help="override max_tokens if supported")
    ap.add_argument("--temperature", type=float, default=None, help="override temperature if supported")
    ap.add_argument("--top_p", type=float, default=None, help="override top_p if supported")
    ap.add_argument("--start", type=int, default=0, help="skip first N valid lines")
    ap.add_argument("--limit", type=int, default=0, help="process at most N lines (0 = no limit)")
    ap.add_argument("--sleep", type=float, default=0.0, help="sleep seconds between calls")
    ap.add_argument("--overwrite", action="store_true", help='overwrite if "gen" already exists')
    ap.add_argument("--gen_key", default="gen", help='output field name (default: "gen")')
    args = ap.parse_args()


    llm = LLM(call_target=args.call_target)
    judge_llm = LLM(call_target=args.call_target)

    # Prepare per-call kwargs
    call_kwargs: Dict[str, Any] = {}
    if args.max_tokens is not None:
        call_kwargs["max_tokens"] = args.max_tokens
    if args.temperature is not None:
        call_kwargs["temperature"] = args.temperature
    if args.top_p is not None:
        call_kwargs["top_p"] = args.top_p

    processed = 0
    skipped = 0

    with open(args.output, "w", encoding="utf-8") as wf:
        for ln, obj in _load_jsonl(args.input):
            # pass through parse errors
            if "__parse_error__" in obj:
                obj[args.gen_key] = ""
                obj["gen_error"] = f"JSON parse error at line {ln}: {obj['__parse_error__']}"
                _dump_jsonl_line(wf, obj)
                continue

            # skip logic counts only valid json objects
            if skipped < args.start:
                skipped += 1
                _dump_jsonl_line(wf, obj)
                continue

            if args.limit > 0 and processed >= args.limit:
                _dump_jsonl_line(wf, obj)
                continue

            # if already has gen
            if (not args.overwrite) and (args.gen_key in obj) and obj[args.gen_key]:
                _dump_jsonl_line(wf, obj)
                continue

            messages = _build_messages(obj)

            try:
                resp = llm(messages, **call_kwargs)
                obj[args.gen_key] = resp
                obj.pop("gen_error", None)
            except Exception as e:
                obj[args.gen_key] = ""
                obj["gen_error"] = f"{type(e).__name__}: {e}"

    
            has_gen = bool(obj.get(args.gen_key))
            has_ans = bool(obj.get("answer") or obj.get("answers"))

            if has_gen and has_ans:
                # try:
                    jm = _build_judge_messages(str(obj[args.gen_key]), str(obj.get("answer") or obj.get("answers")))
                    jresp = judge_llm(jm, max_tokens=4096, temperature=0.0)
                    corr = _parse_corr(jresp)
                    if corr is None:
                        obj["corr"] = 0
                        obj["corr_error"] = f"Judge unparsable output: {str(jresp)[:200]}"
                    else:
                        obj["corr"] = int(corr)
                        obj.pop("corr_error", None)
                # except Exception as e:
                #     obj["corr"] = 0
                #     obj["corr_error"] = f"{type(e).__name__}: {e}"

            _dump_jsonl_line(wf, obj)
            processed += 1

            if args.sleep > 0:
                time.sleep(args.sleep)

    print(f"Done. processed={processed}, skipped_prefix={args.start}. output={args.output}")


if __name__ == "__main__":
    main()