import csv
import json
from pathlib import Path

def csv_to_jsonl(csv_path, jsonl_path, encoding="utf-8"):
    with open(csv_path, "r", encoding=encoding, newline="") as f:
        reader = csv.DictReader(f)
        with open(jsonl_path, "w", encoding="utf-8") as out:
            for row in reader:
                out.write(json.dumps(row, ensure_ascii=False) + "\n")

def _get_suffix(p: str) -> str:
    # 取出扩展名（包含点），如 ".jpg"
    suf = Path(p.strip()).suffix
    return suf if suf else ".png"  # 没有扩展名时的兜底策略

def rewrite_image_field_jsonl(input_path, output_path, level='level1'):
    base_dir = f"./Benchmark/data/{level}/images"
    with open(input_path, "r", encoding="utf-8") as fin, \
         open(output_path, "w", encoding="utf-8") as fout:
        
        for idx, line in enumerate(fin, start=1):
            obj = json.loads(line.strip())

            image_field = obj.get("image", "")
            if isinstance(image_field, str):
                images = [s.strip() for s in image_field.split(",") if s.strip()]

                # if len(images) == 1:
                #     # 单张图片
                #     obj["image"] = f"./Benchmark/data/level1/images/{idx}.png"
                # elif len(images) > 1:
                #     # 多张图片
                #     new_images = [f"./Benchmark/data/level1/images/{idx}.png"]
                #     for i in range(1, len(images)):
                #         new_images.append(f"./Benchmark/data/level1/images/{idx}({i}).png")
                #     obj["image"] = new_images

                if len(images) == 1:
                    ext0 = _get_suffix(images[0])
                    obj["image"] = f"{base_dir}/{idx+314}{ext0}"
                elif len(images) > 1:
                    new_images = []
                    for j, old in enumerate(images):
                        ext = _get_suffix(old)
                        if j == 0:
                            new_images.append(f"{base_dir}/{idx+314}{ext}")
                        else:
                            new_images.append(f"{base_dir}/{idx+314}({j}){ext}")
                    obj["image"] = new_images

            fout.write(json.dumps(obj, ensure_ascii=False) + "\n")

def drop_keys_in_jsonl(input_path: str, output_path: str):
    keys_to_drop=["creator", "Finalize", "judge", "date", "referee", "llm_answer"]

    in_path = Path(input_path)
    out_path = Path(output_path)

    with in_path.open("r", encoding="utf-8") as fin, out_path.open("w", encoding="utf-8") as fout:
        for line in fin:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            for k in keys_to_drop:
                obj.pop(k, None)
            fout.write(json.dumps(obj, ensure_ascii=False) + "\n")

def replace_image_field(jsonl1_path: str, jsonl2_path: str, output_jsonl1_path: str):
    """
    将 jsonl2 中每一行的 "image" 字段替换到 jsonl1 对应行的 "image" 字段，输出新的 jsonl1。
    默认按行号一一对应（第 i 行替换第 i 行）。
    """
    p1, p2, pout = Path(jsonl1_path), Path(jsonl2_path), Path(output_jsonl1_path)

    # 先读取 jsonl2 的 image 列表（按行号对齐）
    image_list: List[Any] = []
    with p2.open("r", encoding="utf-8") as f2:
        for line_no, line in enumerate(f2, start=1):
            line = line.strip()
            if not line:
                image_list.append(None)
                continue
            obj2 = json.loads(line)
            image_list.append(obj2.get("image", None))

    # 逐行读取 jsonl1 并替换
    with p1.open("r", encoding="utf-8") as f1, pout.open("w", encoding="utf-8") as fo:
        for i, line in enumerate(f1, start=1):
            line = line.strip()
            if not line:
                fo.write("\n")
                continue

            obj1: Dict[str, Any] = json.loads(line)

            if i <= len(image_list):
                obj1["image"] = image_list[i - 1]
            else:
                # jsonl2 行数不足时，不替换（也可以改为置 None 或报错）
                pass

            fo.write(json.dumps(obj1, ensure_ascii=False) + "\n")

def reorder_and_reset_question_id(in_path: str, out_path: str) -> None:
    with open(in_path, "r", encoding="utf-8") as f:
        items = [json.loads(line) for line in f if line.strip()]

    # reset question_id by line number after sorting (start from 1)
    for i, obj in enumerate(items, start=1):
        obj["question_id"] = int(i)

    with open(out_path, "w", encoding="utf-8") as f:
        for obj in items:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")

if __name__ == "__main__":

    # input_csv = "/Users/gengxinyu/Documents/codes/GeoBrowse/Benchmark/data/level1/Geographic.csv"
    # output_jsonl = "/Users/gengxinyu/Documents/codes/GeoBrowse/Benchmark/data/level1/Geographic Benchmark_Bench-image.jsonl"
    # csv_to_jsonl(input_csv, output_jsonl)

    # input_jsonl = "/Users/gengxinyu/Documents/codes/GeoBrowse/Benchmark/data/level1/Geographic Benchmark_Bench-image.jsonl"
    # output_jsonl = "/Users/gengxinyu/Documents/codes/GeoBrowse/Benchmark/data/level1/Benchmark_Bench-image.jsonl"
    # rewrite_image_field_jsonl(input_jsonl, output_jsonl)

    # input_jsonl = "/Users/gengxinyu/Documents/codes/GeoBrowse/Benchmark/data/level1/level1_en.jsonl"
    # output_jsonl = "/Users/gengxinyu/Documents/codes/GeoBrowse/Benchmark/data/level1/level1_en_1.jsonl"
    # drop_keys_in_jsonl(input_jsonl, output_jsonl)

    # jsonl_zh = "/Users/gengxinyu/Documents/codes/GeoBrowse/Benchmark/data/level1/level1_zh.jsonl"
    # jsonl_en = "/Users/gengxinyu/Documents/codes/GeoBrowse/Benchmark/data/level1/level1_en.jsonl"
    # output_jsonl = "/Users/gengxinyu/Documents/codes/GeoBrowse/Benchmark/data/level1/level1_en_new.jsonl"
    # replace_image_field(jsonl_en, jsonl_zh, output_jsonl)

    input_jsonl = "/Users/gengxinyu/Documents/codes/GeoBrowse/Benchmark/data/level2/level2_en_old.jsonl"
    output_jsonl = "/Users/gengxinyu/Documents/codes/GeoBrowse/Benchmark/data/level2/level2_en.jsonl"
    reorder_and_reset_question_id(input_jsonl, output_jsonl)

