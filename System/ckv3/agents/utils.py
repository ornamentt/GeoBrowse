import os
import time
import logging
import requests
import random
import re
import sys
import json
import types
import base64
import contextlib
from typing import Union, Callable
from functools import partial
import signal
import numpy as np
from qcloud_cos import CosConfig, CosS3Client
from rich.console import Console as rich_console
from rich import print as rich_print
from rich.markup import escape as rich_escape
import string as _string
from io import BytesIO

# rprint
_console = rich_console(force_terminal=(False if os.getenv("NO_FORCE_TERMINAL", False) else True))
def rprint(inputs, style=None, timed=False):
    if isinstance(inputs, str):
        inputs = [inputs]  # with style as the default
    all_ss = []
    for one_item in inputs:
        if isinstance(one_item, str):
            one_item = (one_item, None)
        one_str, one_style = one_item  # pairs
        one_str = rich_escape(one_str)
        one_style = style if one_style is None else one_style
        if one_style:
            one_str = f"[{one_style}]{one_str}[/]"
        all_ss.append(one_str)
    _to_print = "".join(all_ss)
    if timed:
        _to_print = f"[{time.ctime()}] {_to_print}"
    # rich_print(_to_print)
    _console.print(_to_print)

# --
# simple adpators
zlog = rprint
zwarn = lambda x: rprint(x, style="white on red")
# --

class MyJsonEncoder(json.JSONEncoder):
    def default(self, one: object):
        if hasattr(one, "to_dict"):
            return one.to_dict()
        if isinstance(one, list):
            one = [item.to_dict() if hasattr(item, "to_dict") else item for item in one]
        else:
            try:
                return json.JSONEncoder.default(self, one)
            except:  # note: simply return a str for whatever the python code may return
                zwarn(f"WARNING: MyJsonEncoder cannot encode the object of {type(one)}, simply put its str: {str(one)}")
                return str(one)

def my_json_dumps(*args, **kwargs):
    return json.dumps(*args, **kwargs, cls=MyJsonEncoder)

def tuple_keys_to_str(d):
    if isinstance(d, dict):
        return {str(k): tuple_keys_to_str(v) for k, v in d.items()}
    elif isinstance(d, list):
        return [tuple_keys_to_str(i) for i in d]
    else:
        return d

# wrapping a function and try it multiple times
def wrapped_trying(func, default_return=None, max_times=10, wait_error_names=(), reraise=False):
    # --
    if max_times < 0:
        return func()  # directly no wrap (useful for debugging)!
    # --
    remaining_tryings = max_times
    ret = default_return
    while True:
        try:
            ret = func()
            break  # remember to jump out!!!
        except Exception as e:
            rprint(f"Retry with Error: {e}", style="white on red")
            rand = random.randint(1, 5)
            time.sleep(rand)
            if type(e).__name__ in wait_error_names:
                continue  # simply wait it
            else:
                remaining_tryings -= 1
                if remaining_tryings <= 0:
                    if reraise:
                        raise e
                    else:
                        break
    return ret

# get env variable until hitting a key or returning the default value
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

# easier init with kwargs
class KwargsInitializable:
    def __init__(self, _assert_existing=True, _default_init=False, **kwargs):
        updates = {}
        new_updates = {}
        for k, v in kwargs.items():
            if _assert_existing:
                if not hasattr(self, k):
                    zwarn(f"Unknown attr {k}, ignored")
                    continue
            v0 = getattr(self, k, None)
            if v0 is not None and isinstance(v0, KwargsInitializable):
                new_val = type(v0)(**v)  # further make a new one!
                updates[k] = f"__new__ {type(new_val)}"
            elif v0 is None:  # simply directly update
                new_val = v
                new_updates[k] = new_val
            else:
                new_val = type(v0)(v)  # conversion
                updates[k] = new_val
            setattr(self, k, new_val)
        if not _default_init:
            rprint(f"Finish init {self}, updates={updates}, new_updates={new_updates}")

# --
# templated string (also allowing conditional prompts)
class TemplatedString:
    def __init__(self, s: Union[str, Callable]):
        self.str = s

    def format(self, **kwargs):
        if isinstance(self.str, str):
            return TemplatedString.eval_fstring(self.str, **kwargs)
        else:  # direct call it!
            return self.str(**kwargs)

    @staticmethod
    def eval_fstring(s: str, _globals=None, _locals=None, **kwargs):
        if _locals is None:
            _inner_locals = {}
        else:
            _inner_locals = _locals.copy()
        _inner_locals.update(kwargs)
        assert '"""' not in s, "Special seq not allowed!"
        ret = eval('f"""'+s+'"""', _globals, _inner_locals)
        return ret

# a simple wrapper class for with expression
class WithWrapper:
    def __init__(self, f_start: Callable = None, f_end: Callable = None, item=None):
        self.f_start = f_start
        self.f_end = f_end
        self.item: object = item

    def __enter__(self):
        if self.f_start is not None:
            self.f_start()
        if self.item is not None and hasattr(self.item, "__enter__"):
            self.item.__enter__()
        # return self if self.item is None else self.item
        return self.item

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.item is not None and hasattr(self.item, "__exit__"):
            self.item.__exit__()
        if self.f_end is not None:
            self.f_end()

def my_open_with(fd_or_path, mode='r', empty_std=False, **kwargs):
    if empty_std and fd_or_path == '':
        fd_or_path = sys.stdout if ('w' in mode) else sys.stdin
    if isinstance(fd_or_path, str) and fd_or_path:
        directory = os.path.dirname(fd_or_path)
        if directory and not os.path.exists(directory):
            os.makedirs(directory)

        if mode in ('w', 'a') and not os.path.exists(fd_or_path):
            with open(fd_or_path, mode=mode, **kwargs):
                pass  
                
        return open(fd_or_path, mode=mode, **kwargs)
    else:
        # assert isinstance(fd_or_path, IO)
        return WithWrapper(None, None, fd_or_path)

# get unique ID
def get_unique_id(prefix=""):
    import datetime
    import threading
    dt = datetime.datetime.now().isoformat()
    ret = f"{prefix}{dt}_P{os.getpid()}_T{threading.get_native_id()}"  # PID+TID
    return ret

# update dict (in an incremental way)
def incr_update_dict(trg, src_dict):
    for name, value in src_dict.items():
        path = name.split(".")
        curr = trg
        for _piece in path[:-1]:
            if _piece not in curr:  # create one if not existing
                curr[_piece] = {}
            curr = curr[_piece]
        _piece = path[-1]
        if _piece in curr and curr[_piece] is not None:
            assigning_value = type(curr[_piece])(value)  # value to assign
            if isinstance(assigning_value, dict) and isinstance(curr[_piece], dict):
                incr_update_dict(curr[_piece], assigning_value)  # further do incr
            else:
                curr[_piece] = assigning_value  # with type conversion
        else:
            curr[_piece] = value  # directly assign!

# --
# common response format; note: let each agent specify their own ...
# RESPONSE_FORMAT_REQUIREMENT = """## Output
# Please generate your response, your reply should strictly follow the format:
# Thought: {First, explain your reasoning for your outputs in one line.}
# Code: {Then, output your python code blob.}
# """

# parse specific formats
def parse_response(s: str, seps: list, strip=True, return_dict=False):
    assert len(seps) == len(set(seps)), f"Repeated items in seps: {seps}"
    ret = []
    remaining_s = s
    # parse them one by one
    for one_sep_idx, one_sep in enumerate(seps):
        try:
            p1, p2 = remaining_s.split(one_sep, 1)
            if p1.strip():
                rprint(f"Get an unexpected piece: {p1}")
            sep_val = p2
            for one_sep2 in seps[one_sep_idx+1:]:
                if one_sep2 in p2:
                    sep_val = p2.split(one_sep2, 1)[0]
                    break  # finding one is enough!
            assert p2.startswith(sep_val), "Internal error for unmatched prefix??"
            remaining_s = p2[len(sep_val):]
            one_val = sep_val
        except:  # by default None
            one_val = None
        ret.append(one_val)
    # --
    if strip:
        if isinstance(strip, str):
            ret = [(z.strip(strip) if isinstance(z, str) else z) for z in ret]
        else:
            ret = [(z.strip() if isinstance(z, str) else z) for z in ret]
    if return_dict:
        ret = {k: v for k, v in zip(seps, ret)}
    return ret

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
            for one_line in code.split("\n"):
                if any(re.match(r"from\s*.*\s*import\s*"+function_name, one_line.strip()) for function_name in self.globals.keys()):  # no need of such imports
                    code_nopes.append(one_line)
                else:
                    code_lines.append(one_line)
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


class COSManager:
    def __init__(self, secret_id, secret_key, region, bucket):
        self.secret_id = secret_id
        self.secret_key = secret_key
        self.region = region
        self.bucket = bucket
        self.config = CosConfig(Region=self.region, SecretId=self.secret_id, SecretKey=self.secret_key)
        self.client = CosS3Client(self.config)


    def upload_file(self, local_path, cos_path_prefix, file_name):
        """
        Uploads a local file to Tencent Cloud COS.

        :param local_path: Path to the local file.
        :param cos_path_prefix: The prefix to use for the COS object key (e.g., "AgentFiles/session_123").
        :param file_name: The name of the file.
        :return: The public URL of the uploaded file, or None if upload fails.
        """
        cos_key = f"{cos_path_prefix}/{file_name}"
        try:
            response = self.client.upload_file(
                Bucket=self.bucket,
                LocalFilePath=local_path,
                Key=cos_key
            )
            cos_url = f"https://{self.bucket}.cos.{self.region}.myqcloud.com/{cos_key}"
            logging.info(f"Successfully uploaded {local_path} to {cos_url}")
            return cos_url
        except Exception as e:
            logging.error(f"\033[91mFailed to upload {local_path} to COS. Error: {e}")
            return None

    def upload_bytes(self, data: bytes, cos_path_prefix: str, file_name: str):
        """
        Uploads bytes data to Tencent Cloud COS.

        :param data: Binary content to upload (e.g., image bytes, decoded base64 等).
        :param cos_path_prefix: The prefix to use for the COS object key.
        :param file_name: The name of the file (used in COS key).
        :param content_type: Optional HTTP Content-Type, e.g. "image/jpeg".
        :return: The public URL of the uploaded file, or None if upload fails.
        """
        cos_key = f"{cos_path_prefix}/{file_name}"
        try:
            put_kwargs = {
                "Bucket": self.bucket,
                "Key": cos_key,
                "Body": data,
            }

            response = self.client.put_object(**put_kwargs)

            cos_url = f"https://{self.bucket}.cos.{self.region}.myqcloud.com/{cos_key}"
            logging.info(f"\033[92mSuccessfully uploaded bytes to {cos_url}\033[0m")
            return cos_url
        except Exception as e:
            logging.error(f"Failed to upload bytes to COS key={cos_key}. Error: {e}\033[0m")
            return None


    def download_file(self, cos_key, local_path):
        """
        Downloads a file from Tencent Cloud COS using presigned URL.

        :param cos_key: The key of the object in COS (e.g., "AgentFiles/session_123/test_file.txt").
        :param local_path: The local path to save the downloaded file.
        :return: True if download is successful, False otherwise.
        """
        try:
            presigned_url = self.client.get_presigned_url(
                Bucket=self.bucket,
                Key=cos_key,
                Method='GET',
                Expired=300
            )
            with requests.get(presigned_url, stream=True, timeout=30) as r:
                r.raise_for_status()
                with open(local_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
            logging.info(f"\033[92mSuccessfully downloaded via presigned URL {cos_key} to {local_path}\033[0m")
            return True
        except Exception as e:
            logging.error(f"\033[91mFailed to download {cos_key} from COS. Error: {e}\033[0m")
            return False

    def download_base64(self, cos_key):
        """
        Downloads an object from Tencent Cloud COS as base64-encoded data.

        :param cos_key: The key of the object in COS (e.g., "AgentFiles/session_123/test_file.jpg").
        :return: base64 string (with data: 前缀)，失败时返回 None。
        """
        try:
            presigned_url = self.client.get_presigned_url(
                Bucket=self.bucket,
                Key=cos_key,
                Method='GET',
                Expired=300
            )
            # 直接一次性拉取内容（图片通常不会很大）
            r = requests.get(presigned_url, timeout=30)
            r.raise_for_status()
            binary_data = r.content

            # 转为 base64 字符串
            b64_str = base64.b64encode(binary_data).decode("utf-8")
            base64_qwen = f"data:image;base64,{b64_str}"
            logging.info(f"\033[92mSuccessfully downloaded {cos_key} as base64\033[0m")
            return base64_qwen

        except Exception as e:
            logging.error(f"\033[91mFailed to download {cos_key} from COS as base64. Error: {e}\033[0m")
            return None

    def object_exists(self, cos_key, max_retries=3, sleep_sec=1.0):
        """
        Checks if an object exists in Tencent Cloud COS with retries and fallbacks.

        :param cos_key: The key of the object in COS.
        :param max_retries: Number of attempts.
        :param sleep_sec: Sleep seconds between attempts.
        :return: True if the object exists, False otherwise.
        """
        for attempt in range(max_retries):
            try:
                exists = self.client.object_exists(Bucket=self.bucket, Key=cos_key)
                if exists:
                    logging.info(f"HeadObject OK for {cos_key}")
                    return True
            except Exception as e:
                logging.warning(f"HeadObject failed for {cos_key} (attempt {attempt+1}/{max_retries}): {e}")

            # Fallback 1: explicit head_object
            try:
                self.client.head_object(Bucket=self.bucket, Key=cos_key)
                logging.info(f"head_object fallback OK for {cos_key}")
                return True
            except Exception as e2:
                logging.debug(f"head_object fallback failed for {cos_key}: {e2}")

            # Fallback 2: presigned HEAD
            try:
                presigned_head = self.client.get_presigned_url(
                    Bucket=self.bucket,
                    Key=cos_key,
                    Method='HEAD',
                    Expired=120
                )
                resp = requests.head(presigned_head, timeout=15)
                if resp.status_code == 200:
                    logging.info(f"Presigned HEAD OK for {cos_key}")
                    return True
                else:
                    logging.warning(f"Presigned HEAD status {resp.status_code} for {cos_key}")
            except Exception as e3:
                logging.debug(f"Presigned HEAD failed for {cos_key}: {e3}")

            # Fallback 3: presigned GET Range 0-0
            try:
                presigned_get = self.client.get_presigned_url(
                    Bucket=self.bucket,
                    Key=cos_key,
                    Method='GET',
                    Expired=120
                )
                resp = requests.get(presigned_get, headers={'Range': 'bytes=0-0'}, timeout=15)
                if resp.status_code in (200, 206):
                    logging.info(f"Presigned GET range OK for {cos_key}")
                    return True
                else:
                    logging.warning(f"Presigned GET status {resp.status_code} for {cos_key}")
            except Exception as e4:
                logging.debug(f"Presigned GET failed for {cos_key}: {e4}")

            if attempt < max_retries - 1:
                time.sleep(sleep_sec)

        return False



class Download_Upload:
    def __init__(self):
        self.timeout = 20
        self.max_retries = 10
        self.SECRET_ID = os.getenv("SECRET_ID")
        self.SECRET_KEY = os.getenv("SECRET_KEY")
        self.REGION = os.getenv("REGION", "ap-guangzhou")
        self.BUCKET = os.getenv("BUCKET", "ck-pro-research-1258344706")
        self.cos_manager = COSManager(
            secret_id=self.SECRET_ID,
            secret_key=self.SECRET_KEY,
            region=self.REGION,
            bucket=self.BUCKET,
        )
    
    def save_image_detail(self, data_dict, save_dir):
        with open(save_dir, 'a') as df:
            df.write(json.dumps(data_dict, ensure_ascii=False) + '\n')

    def try_download_tencent(self, url):
        cos_key = self.clean_image_url(url)
        
        for retry in range(self.max_retries):
            try:
                exists = self.cos_manager.object_exists(cos_key=cos_key)
                if not exists:
                    print("  [WARN] Existence check failed, retrying...")
                    time.sleep(2)
                    retry += 1
                    continue
                else:
                    print(f"  [SUCCESS] Object existence confirmed.")

                download_content = self.cos_manager.download_base64(cos_key=cos_key)
                if download_content is not None:
                    return download_content
                else:
                    logging.error(f"Download attempt {retry+1} failed for {url}: Content is None")
                    retry += 1
                    time.sleep(2)  
                    continue
            except Exception as e:
                logging.error(f"Download attempt {retry+1} failed for {url}: {str(e)}")
                download_content = None
                retry += 1
                time.sleep(2)  
                continue
        return None

    def try_download_google(self, url, method):

        if method == 'requests':
            fetch_function = lambda: requests.get(url, timeout=self.timeout)
        elif method == 'wget':
            fetch_function = lambda: subprocess.run(["wget", "-O-", url], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout).stdout
        elif method == 'curl':
            fetch_function = lambda: subprocess.run(
                ["curl", "--location", "--silent", "--fail", constructed_url],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout
            ).stdout
        else:
            raise ValueError("Invalid download method")
        
        for attempt in range(self.max_retries):
            response = fetch_function()
            content = response.content if method == 'requests' else response
            if content:
                return content     # 下载再上传应该上传bytes而不是base64
            else:
                logging.error(f"Download attempt {attempt+1} failed for {url}")
                time.sleep(2)  # wait before retrying
            # try:
            #     image_b64 = re.search(rb'data:image\/[a-zA-Z]+;base64,([^\"]+)', content)
            #     if image_b64:
            #         image_bytes = base64.b64decode(image_b64.group(1))
            #         return image_bytes  # 返回解码后的二进制图片
            # except (json.JSONDecodeError, KeyError, ValueError) as e:
            #     try:
            #         response_json = json.loads(content.decode('utf-8'))
            #         if isinstance(response_json, dict) and response_json.get('data').get('type') == 'b64':
            #             image_b64 = response_json['data']['file_b64']
            #             image_bytes = base64.b64decode(image_b64)
            #             return image_bytes  # 返回解码后的二进制图片
            #     except Exception as e2:
            #         return content
        return None


    def clean_image_url(self, url):
        prefix = "https://ck-pro-research-1258344706.cos.ap-guangzhou.myqcloud.com/"
        if url.startswith(prefix):
            return url[len(prefix):]
        else:
            logging.warning(f"[DOWNLOAD]: URL {url} does not start with expected prefix.")
            return url

    def generate_random_string(self, length=6):
        chars = _string.ascii_letters + _string.digits
        return ''.join(random.choice(chars) for _ in range(length))

    def upload(self, image, byte=True):
        """
        使用腾讯云 COS 上传逻辑。

        :param image: byte=False 时为本地文件路径；byte=True 时为二进制 bytes
        :return:      可访问的文件 URL，失败时返回 None
        """

        train = os.getenv("TRAINDATA", False)
        dataset = os.getenv("DATASET", "default_dataset")
        if train:
            datadir = 'traindata'
        else:
            datadir = 'cache_can_delete'   

        image_name = f'{self.generate_random_string()}.jpeg'
        cos_path_prefix = f"Research/cognitive_kernel/{datadir}/{dataset}"
        cos_key = f"{cos_path_prefix}/{dataset}_{image_name}"

        if byte:
            image_bytes = BytesIO(image)
            image_size = image_bytes.getbuffer().nbytes
        else:
            try:
                image_size = os.path.getsize(image)
            except OSError:
                return None

        if image_size <= 1024:
            return None
        
        if byte:
            cos_url = self.cos_manager.upload_bytes(
                data=image,
                cos_path_prefix=cos_path_prefix,
                file_name=image_name,
            )
        else:
            # 直接用原始文件路径上传
            cos_url = self.cos_manager.upload_file(
                local_path=image,
                cos_path_prefix=cos_path_prefix,
                file_name=image_name,
            )

        if not cos_url:
            return None
       
        return cos_url

    def download_upload(self, search_data, img_save_path, byte=True):
        upload_data = []
        for item in tqdm(search_data, desc="download"):
            image_path = item.get("search_image", '')
            # breakpoint()
            if image_path.startswith('x-raw-image:///'):
                continue

            image_data = self.try_download(image_path, 'curl')

            if image_data is None:
                logging.info(f"Using wget to download {image_path} (curl failed)")
                image_data = self.try_download(image_path, 'wget')

                if image_data is None:
                    logging.error(f"Using request to download {image_path} (curl and wget failed)")
                    image_data = self.try_download(image_path, 'request')


            if image_data is not None:

                #保存到本地
                if not byte:
                    # 生成唯一文件名（基于URL的MD5）
                    url_md5 = hashlib.md5(item['url'].encode()).hexdigest()
                    filename = f"{url_md5}.jpeg"
                    save_path = os.path.join(img_save_path, filename)
                    
                    try:
                        with open(save_path, 'wb') as f:
                            f.write(image_data)
                    
                        image_url = save_path
                    except Exception as e:
                        logging.error(f"Save image failed: {str(e)}")
                        
                else:
                    image_url_ = self.upload(image_data, byte=byte)
                        
            else:
                logging.error(f"All download attempts failed for {image_path}")
                return [{"snippet": item['snippet'], "link": item['link'], "image_url":None}]

            data_dict = {
                "search_image": image_url,
                "snippet": item['snippet'],
                "link": item['link']
            }
        
            upload_data.append(data_dict)

        return upload_data

    
