#
import base64
from io import BytesIO
from typing import Dict, List, Any
import time
import os
import json
import io
import mimetypes
from PIL import Image   
import string as _string
import numpy as np
from ..agents.agent import register_template, MultiStepAgent
# from ..agents.utils import zwarn, CodeExecutor, Download_Upload
from ..agents.utils import zwarn, Download_Upload
from .utils import CodeExecutor
from ..agents.model import LLM

# from .utils import FileEnv
from .prompts import PROMPTS as VL_PROMPTS

class VLAgent(MultiStepAgent):
    """
    One-shot VL agent:
      - Input: image_url (or base64) + goal (how to process the image)
      - Step 1: Ask LLM to write Python code using helpers (load_image, save_image, to_numpy)
      - Step 2: Run the code in a sandbox
      - Step 3: Interpret stdout as base64 image, upload it, and return a multimodal JSON.
    """
    def __init__(self, **kwargs):
        # note: this is a little tricky since things will get re-init again in super().__init__
        feed_kwargs = dict(
            name="vl_agent",
            description="Given an image_url and a processing task (e.g., cropping, rotation, contrast enhancement, marking, analysis), generate Python code to modify the image in a sandbox, execute it, and return a URL of the processed output.",
            templates={"action": "vl_action"},  # template names
            max_steps=1,
        )
        feed_kwargs.update(kwargs)
        # self.file_env_kwargs = {}  # kwargs for file env
        # register_template(VL_PROMPTS)  # add web prompts
        super().__init__(**feed_kwargs)
        # self.file_envs = {}  # session_id -> ENV
        self.current_session = None
        # FTQ: here, add global functions
        self.ACTIVE_FUNCTIONS={
            "load_image": self.my_load_image,
            "save_image": self.my_save_image, 
            "to_numpy":  self.my_to_numpy,
        }
        self.executor = CodeExecutor()
        self.Download_Upload = Download_Upload()
        self.llm = LLM()
        self.default_format = "JPEG"

    #TODO: 这里的load_image和 sandbox 里的不一致，看后续要不要改
    def my_load_image(_INPUT_IMAGE_B64) -> Image.Image:
        raw = base64.b64decode(_INPUT_IMAGE_B64)
        img = Image.open(io.BytesIO(raw))
        return img.convert("RGBA")

    def my_save_image(img: Image.Image):
        global _DID_SAVE
        buf = io.BytesIO()
        _img = Image.new("RGB", img.size)
        _img.paste(img, mask=img.split()[-1])
        _img.save(buf, format="JPEG")
        _DID_SAVE = True
        print(base64.b64encode(buf.getvalue()).decode("utf-8"))
    
    def my_to_numpy(img: Image.Image, mode="RGB"):
        if mode:
            img = img.convert(mode)
        return np.array(img)

    def resolve_image_url(self, img_id: str) -> str:
        """
        img_id -> real url
        get_image_url(img_id) 应由执行器注入（从 session.registry 取）
        """
        if not isinstance(img_id, str) or not img_id.strip():
            raise ValueError("IMAGE_ID_INVALID: empty img_id")
        return self.get_image_url(img_id)  # <-- injected
    
    def get_function_definition(self, short: bool):
        # FTQ: your vl_agent definition
        if short:
            return "- def vl_agent(task: str, image_id: str, out_format: str = \"JPEG\") -> str:  # Processes or analyzes an image to accomplish a specified task."
        else:
            return """- vl_agent
```python
def vl_agent(code: str, image_id: str, out_format: str = "JPEG") -> str:
    \"""get URL from image_id, download image from URL, run user-supplied code inside a sandbox with Pillow/Numpy helpers preloaded.
    You MUST call "vl_agent" to process images (e.g., crop, enhance) and emit images. Otherwise the system will not be able to execute the code.
    Args:
        task (str): Description of the image processing or analysis task (e.g., cropping, rotation, enhancement, marking, analysis).
        image_id (str): Registry image ID or URL of the input image.
        out_format (str, optional): Output image format (e.g., "JPEG", "PNG"). Defaults to "JPEG".
    Returns:
        str: A JSON string containing the analysis results and the URL of the processed image.
    Examples:
        ```python
        img_id = "img:0"
        task = "Enhance the contrast of the image and rotate it by 90 degrees clockwise."
        print(vl_agent(task, img_id))
        ```
    \"""
```"""
    def _looks_like_url(self, s: str) -> bool:
        # 简单判断：以 http(s) 开头就认为是 URL
        return s.startswith("http://") or s.startswith("https://")

    def bind_registry(self, get_image_url_fn, register_image_fn):
        self.get_image_url = get_image_url_fn
        self.register_image = register_image_fn

    def _is_base64(self, s: str) -> bool:
        try:
            # 粗糙校验，避免把普通短文本误当 base64
            if len(s) < 50:
                return False
            base64.b64decode(s, validate=True)
            return True
        except Exception:
            return False
    
    def _is_local_image_path(self, s: str) -> bool:
        if not isinstance(s, str) or not s.strip():
            return False
        p = os.path.expanduser(s.strip())
        return os.path.isfile(p)
    

    def _path_to_data_url_b64(self, path: str) -> str:
        p = os.path.expanduser(path.strip())
        with open(p, "rb") as f:
            data = f.read()
        b64 = base64.b64encode(data).decode("utf-8")

        mime, _ = mimetypes.guess_type(p)
        if not mime or not mime.startswith("image/"):
            # fallback by extension
            ext = os.path.splitext(p)[1].lower().lstrip(".")
            if ext in ("jpg", "jpeg"):
                mime = "image/jpeg"
            elif ext == "png":
                mime = "image/png"
            elif ext == "webp":
                mime = "image/webp"
            else:
                mime = "image/png"  # safe default

        return f"data:{mime};base64,{b64}"

    def _maybe_decode_image_base64(self, s: str):
        try:
            data = base64.b64decode(s, validate=True)
            if len(data) < 50:
                return None
            return data
        except Exception:
            return None

    def normalize_b64(self, s: str) -> str:
        s = s.strip()
        # 1) 去掉 data url 头
        if s.startswith("data:"):
            s = s.split(",", 1)[1]
        # 2) 去掉换行/空格
        s = s.replace("\n", "").replace("\r", "").replace(" ", "")
        # 3) 兼容 urlsafe base64
        s = s.replace("-", "+").replace("_", "/")
        # 4) 补齐 padding 到 4 的倍数
        s += "=" * (-len(s) % 4)
        return s

    def __call__(self, task: str, image_id: str, out_format=None, **kwargs):  # allow *args styled calling
        # breakpoint()
        """
        :param image_input: image_url 或 base64
        :param task: 文本描述如何处理图像（cropping / rotation / enhancement / mark / analysis 等）
        :return: JSON 字符串，多模态格式：
                 [
                   {"type": "text", "text": "..."},
                   {"type": "image_url", "image_url": "..."}
                 ]
                 或只有 text 的错误信息。
        """
        # breakpoint()
        image_input = self.resolve_image_url(image_id)
        # 1. 先把 image_input 统一成 base64
        if self._looks_like_url(image_input):
            image_b64 = self.Download_Upload.try_download_tencent(image_input)
            if image_b64 is None:
                elements = [{"type": "text", "text": "[VL agent] Error: failed to download image from URL."}]
                return json.dumps(elements, ensure_ascii=False)
        elif self._is_local_image_path(image_input):
            image_b64 = self._path_to_data_url_b64(image_input)
            if image_b64 is None:
                elements = [{"type": "text", "text": "[VL agent] Error: failed to download image from URL."}]
                return json.dumps(elements, ensure_ascii=False)
        else:
            if not self._is_base64(image_input):
                elements = [{"type": "text", "text": "[VL agent] Error: input is neither a valid URL nor valid base64 image."}]
                return json.dumps(elements, ensure_ascii=False)
            image_b64 = image_input

        ofmt = (out_format or self.default_format).upper()

        # 2. 让 LLM 生成 Python 代码
        sys_prompt = VL_PROMPTS
        user_prompt = f"Goal: {task}\nPlease write Python code only, no explanations."

        messages = [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": [
                {"type": "text", "text": user_prompt},
                {"type": "image_url", "image_url": {"url": image_b64}},
            ]},
        ]

        raw_resp = self.llm(messages)
        code = CodeExecutor.extract_code(raw_resp) or raw_resp
        image_b64_n = self.normalize_b64(image_b64)

        # 3. 构造 sandbox 代码（类似你之前 SimpleImageExecTool 的 preamble）
        preamble = f"""
import io, base64, json
import numpy as np
from PIL import Image, ImageOps, ImageEnhance, ImageDraw

_INPUT_IMAGE_B64 = {json.dumps(image_b64_n)}
_OUT_FORMAT = {json.dumps(ofmt)}
_DID_SAVE = False

def _b64_to_image(b64_str: str) -> Image.Image:
    raw = base64.b64decode(b64_str)
    img = Image.open(io.BytesIO(raw))
    return img.convert("RGBA")  # unify internal mode
def _image_to_b64(img: Image.Image, fmt: str) -> str:
    buf = io.BytesIO()
    _img = img
    if fmt == "JPEG" and img.mode in ("RGBA", "LA"):
        # drop alpha for JPEG
        _img = Image.new("RGB", img.size)
        _img.paste(img, mask=img.split()[-1])
    _img.save(buf, format=fmt)
    return base64.b64encode(buf.getvalue()).decode("utf-8")
def load_image() -> Image.Image:
    return _b64_to_image(_INPUT_IMAGE_B64)
def save_image(img: Image.Image):
    global _DID_SAVE
    print(_image_to_b64(img, _OUT_FORMAT))  # executor collects via custom_print
    _DID_SAVE = True
def to_numpy(img: Image.Image, mode="RGB"):
    if mode:
        img = img.convert(mode)
    return np.array(img)
"""

#         epilogue = r"""
# # ===== AUTO EPILOGUE =====
# try:
#     from PIL import Image as __PILImage
#     if (not _DID_SAVE) and ('out' in globals()) and isinstance(out, __PILImage.Image):
#         save_image(out)
# except Exception:
#     pass
# """

        full_code = preamble + "\n# ===== USER CODE START =====\n" + code

        # 4. 在 sandbox 中执行
        self.executor.results.clear()
        self.executor.add_global_vars(**self.ACTIVE_FUNCTIONS)
        self.executor.run(full_code, catch_exception=True, null_stdin=True, timeout=30)
        out = self.executor.get_print_results(clear=True)
        if isinstance(out, list):
            out = "\n".join(str(x) for x in out)
        if not isinstance(out, str):
            out = "" if out is None else str(out)

        # 5. 如果输出是 base64 图像 → 上传 → 返回多模态 JSON；否则当作纯文本返回
        img_bytes = self._maybe_decode_image_base64(out)
        if img_bytes is None:
            # 纯文本分析结果
            elements = [
                {
                    "type": "text",
                    "text": f"[VL agent] Analysis result:\n{out}"
                }
            ]
            return json.dumps(elements, ensure_ascii=False)

        try:
            url = self.Download_Upload.upload(img_bytes, byte=True)
            if url is None:
                raise ValueError("upload returned None")

            img_id = ""
            try:
                img_id = self.register_image(
                    url,
                    desc="vl_tool_output",
                    meta={"source": "vl_tool", "snippet": task}
                )
            except Exception as e:
                # Do not fail the whole tool output if registry write fails
                img_id = ""
                zwarn(f"[VL agent] register_image failed: {e}")

            elements = [
                {
                    "type": "text",
                    "text": "[VL agent] The output image id: " + img_id
                }
            ]
            return json.dumps(elements, ensure_ascii=False)
        except Exception as e:
            zwarn("VL agent execution error!" + f"\nFailed to upload processed image: {e}")
            elements = [
                {
                    "type": "text",
                    "text": f"[VL agent] Error after execution: {e}"
                }
            ]
            return json.dumps(elements, ensure_ascii=False)

    # def init_run(self, session):
    #     super().init_run(session)
    #     _id = session.id
    #     assert _id not in self.file_envs
    #     _kwargs = self.file_env_kwargs.copy()

    #     self.file_envs[_id] = FileEnv(**_kwargs)
    #     self.current_session = session

    # def end_run(self, session):
    #     ret = super().end_run(session)
    #     _id = session.id
    #     self.file_envs[_id].stop()
    #     del self.file_envs[_id]  # remove web env
    #     return ret

    # def step_prepare(self, session, state):
    #     # FTQ: preparing observation. For you it's just image_url
    #     self.current_session = session
    #     _input_kwargs, _extra_kwargs = super().step_prepare(session, state)
    #     image_url = _input_kwargs.get("image_url", None)

    #     if self._looks_like_url(image_url):
    #         # URL：调用 download 逻辑，返回 base64
    #         image_b64 = self.Download_Upload.try_download_tencent(image_url)
    #         if image_b64 is None:
    #             return "[image_processor] Error: failed to download image from URL."
    #     else:
    #         # 非 URL：尝试当作 base64 使用
    #         if not self._is_base64(image_url):
    #             return "[image_processor] Error: input is neither a valid URL nor a valid base64 image."
    #         image_b64 = image_url

    #     _input_kwargs["image_b64"] = image_b64

    #     return _input_kwargs, _extra_kwargs

    # def step_action(self, action_res, action_input_kwargs, file_env=None, **kwargs):
    #     # action_res["file_state_before"] = file_env.get_state()  # inplace storage of the web-state before the action
    #     _rr = super().step_action(action_res, action_input_kwargs)  # get action from code execution
    #     # FTQ: call super().step_action to execute python code.
    #     action_str, action_result = _rr.action, _rr.result
    #     # --
    #     if isinstance(action_result, list):
    #         out = "\n".join(str(x) for x in action_result)
    #     if not isinstance(out, str):
    #         out = "" if action_result is None else str(action_result)
        
    #     img_bytes = self._maybe_decode_image_base64(out)
    #     if img_bytes is None:
    #         raise ValueError("[VL agent] Error: the code did not produce valid base64 image output. Please ensure to call save_image(img) or print base64 string.")

    #     try:
    #         url = self.Download_Upload.upload(img_bytes, byte=True)
    #         if url is None:
    #             raise ValueError("[VL agent] Failed to upload processed image: upload returned None")

    #         elements = [
    #         {
    #             "type": "text",
    #             "text": "[VL agent] The output image:"
    #         },
    #         {
    #             "type": "image_url",
    #             "image_url": url
    #         }
    #     ]
    #         return json.dumps(elements, ensure_ascii=False)
    #     except Exception as e:
    #         zwarn("vl agent execution error!" + f"\nFailed to upload processed image: {e}")
    #         elements = [
    #             {
    #                 "type": "text",
    #                 "text": f"[VL agent] Error: {e}"
    #             }
    #         ]
    #         return json.dumps(elements, ensure_ascii=False)

    # def step_call(self, messages, session, model=None):
    #     if model is None:
    #         model = self.model
    #     response = model(messages)
    #     return response

    # def _prep_page(self, file_state):
    #     # FTQ: prepare observation
    #     _ss = file_state

    #     _ret = {"image_url": _ss["image_url"],
    #             "task":_ss["task"],
    #             "image_suffix":None,
    #             "error_message":None}

    #     if _ss["error_message"]:
    #         _ret["error_message"] = _ss["error_message"]
    #     _ret["image_suffix"] = _ss["image_suffix"]
    #     return _ret
