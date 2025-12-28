import json
import base64
import os
from pathlib import Path
from tqdm import tqdm
from openai import OpenAI
from collections import defaultdict

data_file = "/Users/aurosky/Desktop/25UROP/GeoBrowse-yanjing/Benchmark/codes/infer/level1_en.jsonl"
output_file = "level1_en_output.jsonl"

MAX_ITEMS = 199  # run 199

c_or = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key='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',
)

model = "openai/gpt-4.1"

system_prompt = (
"Your ONLY task: Analyze the provided `image_solution` text, count the number of distinct VISUAL CLUES that are explicitly described as being DIRECTLY observed from the image (ignore all reasoning/logic steps, combine image content for comprehensive evaluation).\n"
    "Strict counting rules (MUST follow for the given Chinese/English mixed scenario):\n"
    "1. Valid clue definition: Elements explicitly stated as 'observed/noticed from the image' (e.g., 'black hair and yellow skin of pedestrians' = 1 clue, as hair/skin color are features of the same subject; billboard text, traffic lane direction, license plate, etc.).\n"
    "2. Special rules: License plate + driving/traffic lane direction = 2 separate clues; 2 different license plates = 2 individual clues (even if used to infer the same location).\n"
    "3. Core principle: Be comprehensive, ERR ON THE SIDE OF COUNTING MORE (never miss any potential visual clues from the image), take the image as the ultimate basis and the `image_solution`'s description of the image as the key reference.\n"
    "4. Invalid content (DO NOT count): Web search results, logical elimination/inference, geographic knowledge, conclusions, or elements not stated as 'observed from the image'.\n"
    "5. Output requirement: Return ONLY a single integer (no other text, no lists, no explanations) – this number is the 'hops'."
)

def encode_image_to_base64(image_path):
    abs_path = os.path.abspath(image_path)
    if not os.path.exists(abs_path):
        print(f"warning：image not found - {abs_path}")
        return None
    
    try:
        with open(abs_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')
    except Exception as e:
        print(f"fail to get image {abs_path}: {e}")
        return None

def generate_hops(prompt, image_paths, model="openai/gpt-4.1"):
    if isinstance(image_paths, (str, Path)):
        image_paths = [str(image_paths)]

    image_data = []
    for path in image_paths:
        base64_str = encode_image_to_base64(path)
        if base64_str:
            image_data.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{base64_str}"
                }
            })

    user_prompt = (
        f"Based on the provided images and the following reasoning text, extract ALL visual clues directly from the images, then count them:\n"
        f"Reasoning text: {prompt}\n"
        f"Strictly follow the rules in the system prompt: list all clues first, then output the total count as a single number."
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": [{"type": "text", "text": user_prompt}] + image_data}
    ]

    try:
        response = c_or.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=16, 
            temperature=0.0,  
            top_p=1.0
        )
        answer = response.choices[0].message.content.strip()
    
        lines = answer.split('\n')
        hops = -1
        for line in reversed(lines):
            line = line.strip()
            if line.isdigit():
                hops = int(line)
                break
        if hops == -1:
            digits = [int(c) for c in answer if c.isdigit()]
            hops = digits[-1] if digits else -1
        return hops, answer  
    except Exception as e:
        print(f"fail to use llm: {e}")
        return -1, f"Error: {str(e)}"

def count_hop_ids(input_file):
    hop_dict = defaultdict(list)
    
    with open(input_file, "r", encoding="utf-8") as f:
        for line in f:
            try:
                item = json.loads(line.strip())
                hop = item.get("hops")
                qid = item.get("question_id")
                if hop != -1 and qid != -1:
                    hop_dict[hop].append(qid)
            except json.JSONDecodeError as e:
                print(f"fail to get jsonl: {e}")
                continue
    
    for hop in sorted(hop_dict.keys()):
        hop_dict[hop].sort()
        print(f"Hop {hop} IDs: {hop_dict[hop]}")
    
    return hop_dict


if __name__ == "__main__":
    
    data = []
    try:
        with open(data_file, "r", encoding="utf-8") as f:
            line_count = 0
            for line in f:
                if line_count >= MAX_ITEMS:
                    break
                try:
                    item = json.loads(line.strip())
                    data.append(item)
                    line_count += 1
                except json.JSONDecodeError as e:
                    print(f"解析第{line_count+1}行JSON失败: {e}")
                    continue
        print(f"complete loading {len(data)} data（aim {MAX_ITEMS} ）")
    except FileNotFoundError:
        print(f"fail：can't find file {data_file}，please check the path")
        exit(1)

    current_dir = os.path.dirname(os.path.abspath(__file__))
    image_root = os.path.abspath(os.path.join(current_dir, '../../data/level1/images'))
    print(f"from image root：{image_root}")

    with open(output_file, "w", encoding="utf-8") as fout:
        desc = f"Processing first {MAX_ITEMS} examples"
        for item in tqdm(data, desc=desc):
            qid = item.get("question_id", -1)
            solution = item.get("image_solution", "")
            
            original_image_paths = item.get("image", [])
            if isinstance(original_image_paths, str):
                original_image_paths = [original_image_paths]
            correct_image_paths = []
            for path in original_image_paths:
                path_str = str(path) if path else ""
                image_filename = os.path.basename(path_str)
                correct_path = os.path.join(image_root, image_filename)
                correct_image_paths.append(correct_path)

            hops, answer = generate_hops(solution, correct_image_paths)
            
            output_item = {
                "question_id": qid,
                "hops": hops
            }

            fout.write(json.dumps(output_item, ensure_ascii=False) + "\n")

    print(f"\n✅ finish！out put file：{os.path.abspath(output_file)}")

    print("\n========== hop dataset ==========")
    count_hop_ids(output_file)
