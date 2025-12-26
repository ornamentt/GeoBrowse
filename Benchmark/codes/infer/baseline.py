import json
import openai 
import time
import openai
from openai import OpenAI
import base64
from pathlib import Path
# from key import xinyu_or_key, xinyu_ms_key
from tqdm import tqdm

data_file = "/Users/gengxinyu/Documents/codes/GeoBrowse/Benchmark/data/level1/level1_en.jsonl" #输入文件，用test.jsonl
output_file= "/Users/gengxinyu/Documents/codes/GeoBrowse/level1_en.jsonl" #输出文件

c_or = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key='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',
)

# c_ms = OpenAI(
#     api_key=xinyu_ms_key,
#     base_url="https://api-inference.modelscope.cn/v1/"
# )

or_models = [
            # "openai/gpt-5-image",
             "openai/gpt-4.1",
            #  "openai/gpt-4o", 
            #  "anthropic/claude-opus-4.5",
            #  "google/gemini-3-pro-preview",
            #  "google/gemini-2.5-flash-image",
            #  "meta-llama/llama-3.2-90b-vision-instruct"
             ]

# ms_models = [
#             "Qwen/Qwen3-VL-32B-Instruct", 
#             "Qwen/Qwen3-VL-32B-Thinking"
#             ]

models = or_models
#改这里的prompt
sys_p = "Give the answer based on the image and the prompt provided concisely. Your output can only consist of a short number or word!"

def encode_image_to_base64(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')


def generate_with_openai(prompt, image_paths=None,model="gpt-4o-mini", system_prompt=None, max_tokens=16384, temperature=0.1, top_p=1.0,
                         retry_attempt=5, verbose=False,type = None) : # T/F,response
    if model in or_models:
        client = c_or
    elif model in ms_models:
        client = c_ms
    else:
        raise ValueError("Choose a model provider")

    if isinstance(image_paths, (str, Path)):
        image_paths = [str(image_paths)]
    
    image_data = []
    for path in image_paths:
        base64_str = encode_image_to_base64(path)
        image_data.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:image/jpeg;base64,{base64_str}"
            }
        })

    if system_prompt:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content":[
                { 
                "type": "text", 
                "text": prompt
            },

        ]},
        ]
        if image_paths:
            for image in image_data:
                messages[1]["content"].append(image)
    else:
        messages = [
            {"role": "user", "content":[
                { 
                "type": "text", 
                "text": prompt
            },
            
        ]}
        ]
        if image_paths:
            for image in image_data:
                messages[1]["content"].append(image)
    retry_num = 0
    generation_success = False
    while retry_num < retry_attempt and not generation_success:
        try:
            if model not in ["openai/gpt-5-image","o1-mini","o3-mini"]:
                gen = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    top_p=top_p
                )
            else:
                gen = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    max_completion_tokens=max_tokens,
                    #temperature=temperature,
                    #top_p=top_p
                )

            generation_success = True
            input_tokens = gen.usage.prompt_tokens
            output_tokens = gen.usage.completion_tokens

            if verbose:
                print('\n\n----------------------\n')
                print(gen.choices[0].message.content.strip())
                print("Prompt tokens: {}; Completion tokens: {}".format(input_tokens, output_tokens))
                print('\n----------------------\n\n')
        except openai.APIError as e:  # TRIGGERED OpenAI API ERROR, Could be network issue
            if verbose:
                print(e)
            retry_num += 1
            generation_success = False
            time.sleep(5)
        except openai.RateLimitError as e:  # TRIGGERED OpenAI RATE LIMIT
            if verbose:
                print(e)
            retry_num += 1
            generation_success = False
            time.sleep(20)
        except openai.BadRequestError as e:  # TRIGGERED OpenAI CONTENT SAFETY FILTER
            if verbose:
                print(e)
            retry_num += 1
            generation_success = False
            # time.sleep(1)
        except:
            retry_num += 1
            generation_success = False
            time.sleep(2)
    if generation_success:
        return True, gen.choices[0].message.content


#data = json.load(open(data_file, "r", encoding='utf-8'))

with open(data_file, "r", encoding="utf-8") as f:
    data = []
    for line in f:
        line = line.strip()
        if not line:
            continue
        try:
            data.append(json.loads(line))
        except json.JSONDecodeError as e:
            print(f"Skipping invalid JSON line: {e}")

for model in models:

    with open(output_file, "w", encoding="utf-8") as f_out:
        for item in tqdm(data, desc=f"Model: {model}", total=len(data)):
            try:
                prompt = item["prompt"]
                image_paths = item.get("image", [])

                success, response = generate_with_openai(
                    prompt,
                    image_paths=image_paths,
                    model=model,
                    system_prompt=sys_p,
                    verbose=True
                )
            except Exception as e:
                print(e)
                # breakpoint()
                success = False

            result_item = item.copy()
            #现在存的key是"llm_answer"，改成"hops"
            result_item["llm_answer"] = response if success else "Generation failed after retries."

            # JSONL: 一行一个 JSON
            f_out.write(json.dumps(result_item, ensure_ascii=False) + "\n")