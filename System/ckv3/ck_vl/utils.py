#

# utils for our web-agent

import re
import io
import os
import copy
import time
import requests
import base64
import pdf2image
import types
import json
import math
import ast
import sys
import logging
import random
import signal
import numpy as np
from rich.console import Console as rich_console
from rich import print as rich_print
from rich.markup import escape as rich_escape
import string as _string
from typing import Union, Callable
from functools import partial
import contextlib

from ..agents.utils import KwargsInitializable, rprint, zwarn, zlog
from .mdconvert import MarkdownConverter
import markdownify

def timeout_handler(signum, frame):
    raise TimeoutError("Code execution exceeded timeout")

def get_np_generator(seed):
    return np.random.RandomState(seed)

# there are images in the messages
def have_images_in_messages(messages):
    for message in messages:
        contents = message.get("content", "")
        if not isinstance(contents, list):
            contents = [contents]
        for one_content in contents:
            if isinstance(one_content, dict):
                if one_content.get("type") == "image_url":
                    return True
    return False

def check_file_size(file_path, max_size=100):
    """
    Checks if a file's size is greater than max_size Megabytes.
    
    Args:
        file_path (str): The path to the file.
        
    Returns:
        None. Prints the result to the console.
    """
    # Define the size threshold in bytes (512 MB)
    # 1 MB = 1024 * 1024 bytes
    threshold_bytes = max_size * 1024 * 1024

    try:
        # Get the file size in bytes
        file_size_bytes = os.path.getsize(file_path)
        
        rprint(f"Size: {file_size_bytes / (1024*1024):.2f} MB")

        # Compare the file size to the threshold
        if file_size_bytes > threshold_bytes:
            return True
        else:
            return False

    except FileNotFoundError:
        rprint(f"Error: The file '{file_path}' was not found.", stype="white on red")
        return False
    except Exception as e:
        rprint(f"An error occurred: {e}", stype="white on red")
        return False

class MyMarkdownify(markdownify.MarkdownConverter):
    def convert_img(self, el, text, parent_tags):
        return ""  # simply ignore image

    def convert_a(self, el, text, parent_tags):
        if (not text) or (not text.strip()):
            return ""  # empty
        text = text.strip()  # simply strip!
        href = el.get("href")
        if not href:
            href = ""
        if not any(href.startswith(z) for z in ["http", "https"]):
            ret = text  # simply no links
            # ret = ""  # more aggressively remove things! (nope, removing too much...)
        else:
            ret = f"[{text}]({href})"
        return ret

    @staticmethod
    def md_convert(html: str):
        html_md = MyMarkdownify().convert(html)
        valid_lines = []
        for line in html_md.split("\n"):
            line = line.rstrip()
            if not line: continue
            valid_lines.append(line)
        ret = "\n".join(valid_lines)
        return ret

def GET_ENV_VAR(*keys: str, df=None):
    for k in keys:
        if k in os.environ:
            return os.getenv(k)
    return df

# get until hit
def get_until_hit(d, keys, df=None):
    for k in keys:
        if k in d:
            return d[k]
    return df
# --
# web state
class FileState:
    def __init__(self, **kwargs):
        # current file
        self.current_file_name = None
        self.multimodal = False # whether to get the multimodal content of this state.
        

        # 

        self.loaded_files = {} # keys: file names, values: True/False, whether the file is loaded.
        self.file_meta_data = {} # A string indicating number of pages, tokens each page.
        self.current_page_id_list = []
        
        # 
        
        self.textual_content = ""
        self.visual_content = []
        self.image_suffix = []
        
        # step info
        self.curr_step = 0  # step to the root
        self.total_actual_step = 0  # [no-rev] total actual steps including reverting (can serve as ID)
        self.num_revert_state = 0  # [no-rev] number of state reversion
        # (last) action information
        self.action_string = ""
        self.action = None
        self.error_message = ""
        self.observation = ""
        # --
        self.update(**kwargs)

    def update(self, **kwargs):
        for k, v in kwargs.items():
            assert (k in self.__dict__), f"Attribute not found for {k} <- {v}"
        self.__dict__.update(**kwargs)

    def to_dict(self):
        return self.__dict__.copy()

    def copy(self):
        return FileState(**self.to_dict())

    def __repr__(self):
        return f"FileState({self.__dict__})"

class CodeExecutor:
    def __init__(self, global_dict=None):
        # self.code = code
        self.results = []
        self.globals = global_dict if global_dict else {}
        # self.additional_imports = None
        self.internal_functions = {"print": self.custom_print, "input": CodeExecutor.custom_input, "exit": CodeExecutor.custom_exit}  # customized ones
        self.null_stdin = not bool(int(GET_ENV_VAR("NO_NULL_STDIN", df="0")))  # for easier debugging and program interacting

    def add_global_vars(self, **kwargs):
        self.globals.update(kwargs)

    @staticmethod
    def extract_code(s: str):
        # CODE_PATTERN = r"```(?:py[^t]|python)(.*?)```"
        CODE_PATTERN = r"```(?:py[^t]|python)(.*)```"  # get more codes
        orig_s, hit_code = s, False
        # strip _CODE_PREFIX
        _CODE_PREFIX = "<|python_tag|>"
        if _CODE_PREFIX in s:  # strip _CODE_PREFIX
            hit_code = True
            _idx = s.index(_CODE_PREFIX)
            s = s[_idx+len(_CODE_PREFIX):].lstrip()  # strip tag
        # strip all ```python ... ``` pieces
        # m = re.search(r"```python(.*)```", s, flags=re.DOTALL)
        if "```" in s:
            hit_code = True
            all_pieces = []
            for piece in re.findall(CODE_PATTERN, s, flags=re.DOTALL):
                all_pieces.append(piece.strip())
            s = "\n".join(all_pieces)
        # --
        # cleaning
        while s.endswith("```"):  # a simple fix
            s = s[:-3].strip()
        ret = (s if hit_code else "")
        return ret

    def custom_print(self, *args):
        # output = " ".join(str(arg) for arg in args)
        # results.append(output)
        self.results.extend(args)  # note: simply adding!

    @staticmethod
    def custom_input(*args):
        return "No input available."

    @staticmethod
    def custom_exit(*args):
        return "Cannot exit."

    def get_print_results(self, return_str=False, clear=True):
        ret = self.results.copy()  # a list of results
        if clear:
            self.results.clear()
        if len(ret) == 1:
            ret = ret[0]  # if there is only one output
        if return_str:
            ret = "\n".join(ret)
        return ret

    def _exec(self, code, null_stdin, timeout):
        original_stdin = sys.stdin  # original stdin
        if timeout > 0:
            signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(timeout)
        try:
            with open(os.devnull, 'r') as fd:
                if null_stdin:  # change stdin
                    sys.stdin = fd
                exec(code, self.globals)  # note: no locals since things can be strange!
        finally:
            if null_stdin:  # change stdin
                sys.stdin = original_stdin
            if timeout > 0:
                signal.alarm(0)  # Disable the alarm
            # simply remove global vars to avoid pickle errors for multiprocessing running!
            # self.globals.clear()  # note: simply create a new executor for each run!

    def run(self, code, catch_exception=True, null_stdin=None, timeout=0):
        if null_stdin is None:
            null_stdin = self.null_stdin  # use the default one
        # --
        if code:  # some simple modifications
            code_nopes = []
            code_lines = [f"import {lib}\n" for lib in ["os", "sys"]] + ["", ""]
            # for one_line in code.split("\n"):
            #     if any(re.match(r"from\s*.*\s*import\s*"+function_name, one_line.strip()) for function_name in self.globals.keys()):  # no need of such imports
            #         code_nopes.append(one_line)
            #     else:
            #         code_lines.append(one_line)
            code = "\n".join(code_lines)
            if code_nopes:
                zwarn(f"Remove unneeded lines of {code_nopes}")
        self.globals.update(self.internal_functions)  # add internal functions
        # --
        if catch_exception:
            try:
                self._exec(code, null_stdin, timeout)
            except Exception as e:
                err = self.format_error(code)
                # self.results.append(err)
                if self.results:
                    err = f"{err.strip()}\n(* Partial Results={self.get_print_results()})"
                if isinstance(e, TimeoutError):
                    err = f"{err}\n-> Please revise your code and simplify the next step to control the runtime."
                self.custom_print(err)  # put err
                zwarn(f"Error executing code: {e}")
        else:
            self._exec(code, null_stdin, timeout)
        # --

    @staticmethod
    def format_error(code: str):
        import traceback
        err = traceback.format_exc()
        _err_line = None
        _line_num = None
        for _line in reversed(err.split("\n")):
            ps = re.findall(r"line (\d+),", _line)
            if ps:
                _err_line, _line_num = _line, ps[0]
                break
        # print(_line_num, code.split('\n'))
        try:
            _line_str = code.split('\n')[int(_line_num)-1]
            err = err.replace(_err_line, f"{_err_line}\n    {_line_str.strip()}")
        except:  # if we cannot get the line
            pass
        return f"Code Execution Error:\n{err}"

def timeout_handler(signum, frame):
    raise TimeoutError("Code execution exceeded timeout")

def get_np_generator(seed):
    return np.random.RandomState(seed)

# there are images in the messages
def have_images_in_messages(messages):
    for message in messages:
        contents = message.get("content", "")
        if not isinstance(contents, list):
            contents = [contents]
        for one_content in contents:
            if isinstance(one_content, dict):
                if one_content.get("type") == "image_url":
                    return True
    return False