#

import os
import time
import argparse
import json
from .agent import VLAgent
from ..agents.utils import rprint, my_open_with, zwarn, incr_update_dict, get_until_hit, my_json_dumps

def get_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("-c", "--config", type=str, default="")
    parser.add_argument("-i", "--input", type=str, default="")
    return parser.parse_args()

def yield_inputs(one_inst):
    task = get_until_hit(one_inst, ["task", "query", "goal", "instruction", "Task", "Query", "Instruction"])
    image_url = get_until_hit(one_inst, ["image_url", "img_url", "image"])
    if task and isinstance(image_url, str):
        yield {"task": task, "image_url": image_url, "_orig": one_inst}
    else:
        zwarn(f"Cannot find task/image_url from: {one_inst}")
    

def main():
    args = get_args()
    rprint(f"Run ck_vl.main with {args}")
    # init agent
    # configs = default_file_configs
    vl_agent = VLAgent()
    #TODO: 搞清楚输入形式
    input_ = json.loads(args.input)
    for inst in yield_inputs(input_):
        res_session = vl_agent(task=inst["task"], image_input=inst["image_url"])
        print(res_session)
        return res_session

    raise ValueError("No valid instruction found in input.")
    # --

if __name__ == '__main__':
    main()
