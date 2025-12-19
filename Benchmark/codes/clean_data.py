import csv
import json
from pathlib import Path

def csv_to_jsonl(csv_path, jsonl_path, encoding="utf-8"):
    with open(csv_path, "r", encoding=encoding, newline="") as f:
        reader = csv.DictReader(f)
        with open(jsonl_path, "w", encoding="utf-8") as out:
            for row in reader:
                out.write(json.dumps(row, ensure_ascii=False) + "\n")

def rewrite_image_field_jsonl(input_path, output_path):
    with open(input_path, "r", encoding="utf-8") as fin, \
         open(output_path, "w", encoding="utf-8") as fout:
        
        for idx, line in enumerate(fin, start=1):
            obj = json.loads(line.strip())

            image_field = obj.get("image", "")
            if isinstance(image_field, str):
                images = [s.strip() for s in image_field.split(",") if s.strip()]

                if len(images) == 1:
                    # 单张图片
                    obj["image"] = f"./Benchmark/data/level2/images/{idx}.png"
                elif len(images) > 1:
                    # 多张图片
                    new_images = [f"./Benchmark/data/level2/images/{idx}.png"]
                    for i in range(1, len(images)):
                        new_images.append(f"./Benchmark/data/level2/images/{idx}({i}).png")
                    obj["image"] = new_images

            fout.write(json.dumps(obj, ensure_ascii=False) + "\n")

def drop_keys_in_jsonl(input_path: str, output_path: str):
    keys_to_drop=["creator", "Finalize", "judge"]

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

if __name__ == "__main__":
    # input_csv = "/Users/gengxinyu/Documents/codes/GeoBrowse/Benchmark/data/level2/Geographic Benchmark_Bench-BrowseComp.csv"
    # output_jsonl = "/Users/gengxinyu/Documents/codes/GeoBrowse/Benchmark/data/level2/Geographic Benchmark_Bench-BrowseComp.jsonl"
    # csv_to_jsonl(input_csv, output_jsonl)

    # input_jsonl = "/Users/gengxinyu/Documents/codes/GeoBrowse/Benchmark/data/level2/Geographic Benchmark_Bench-BrowseComp.jsonl"
    # output_jsonl = "/Users/gengxinyu/Documents/codes/GeoBrowse/Benchmark/data/level2/Benchmark_Bench-BrowseComp.jsonl"
    # rewrite_image_field_jsonl(input_jsonl, output_jsonl)

    input_jsonl = "/Users/gengxinyu/Documents/codes/GeoBrowse/Benchmark/data/level2/Benchmark_Bench-BrowseComp.jsonl"
    output_jsonl = "/Users/gengxinyu/Documents/codes/GeoBrowse/Benchmark/data/level2/level2.jsonl"
    drop_keys_in_jsonl(input_jsonl, output_jsonl)
