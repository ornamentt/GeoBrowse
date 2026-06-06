import requests
from .utils import KwargsInitializable, rprint, GET_ENV_VAR, parse_response, CodeExecutor, zwarn, Download_Upload
import os
import json
import time
import base64
from typing import Dict, List, Any
import tempfile
from io import BytesIO
import mimetypes


class Tool(KwargsInitializable):
    def __init__(self, **kwargs):
        self.name = ""
        super().__init__(**kwargs)

    def get_function_definition(self, short: bool):
        raise NotImplementedError("To be implemented")

    def __call__(self, *args, **kwargs):
        raise NotImplementedError("To be implemented")

# --
# useful tools

class StopResult(dict):
    pass

class StopTool(Tool):
    def __init__(self, agent=None):
        super().__init__(name="stop")
        self.agent = agent

    def get_function_definition(self, short: bool):
        if short:
            return """- def stop(output: str, log: str) -> Dict:  # Finalize and formalize the answer when the task is complete."""
        else:
            return """- stop
```python
def stop(output: str, log: str) -> dict:
    \""" Finalize and formalize the answer when the task is complete.
    Args:
        output (str): The concise, well-formatted final answer to the task.
        log (str): Brief notes or reasoning about how the answer was determined.
    Returns:
        dict: A dictionary with the following structure:
            {
                'output': <str>  # The well-formatted answer, strictly following any specified output format.
                'log': <str>     # Additional notes, such as steps taken, issues encountered, or relevant context.
            }
    Examples:
        >>> answer = stop(output="Inter Miami", log="Task completed. The answer was found using official team sources.")
        >>> print(answer)
    \"""
```"""

    def __call__(self, output: str, log: str):
        ret = StopResult(output=output, log=log)
        if self.agent is not None:
            self.agent.put_final_result(ret)  # mark end and put final result
        return ret

class AskLLMTool(Tool):
    def __init__(self, llm=None):
        super().__init__(name="ask_llm")
        self.llm = llm

    def set_llm(self, llm):
        self.llm = llm

    def get_function_definition(self, short: bool):
        if short:
            return """- def ask_llm(query: str) -> str:  # Directly query the language model for tasks that do not require external tools."""
        else:
            return """- ask_llm
```python
def ask_llm(query: str) -> str:
    \""" Directly query the language model for tasks that do not require external tools.
    Args:
        query (str): The specific question or instruction for the LLM.
    Returns:
        str: The LLM's generated response.
    Notes:
        - Use this function for fact-based or reasoning tasks that can be answered without web search or external data.
        - Phrase the query clearly and specifically.
    Examples:
        >>> answer = ask_llm(query="What is the capital city of the USA?")
        >>> print(answer)
    \"""
```"""

    def __call__(self, query: str):
        messages = [{"role": "system", "content": "You are a helpful assistant. Answer the user's query with your internal knowledge. Ensure to follow the required output format if specified."}, {"role": "user", "content": query}]
        response = self.llm(messages)
        return response

class SimpleSearchTool(Tool):
    def __init__(self, target="", llm=None, max_results=7, list_enum=True, **kwargs):
        super().__init__(name="simple_web_search")
        self.llm = llm
        self.max_results = max_results
        self.list_enum = list_enum
        if not target:
            target = GET_ENV_VAR("SEARCH_BACKEND", df="DuckDuckGo")  # use which backend search engine
        rprint(f"Setup SimpleSearchTool with {target}")
        self.target = target
        if target == "DuckDuckGo":
            self.ddgs_params = kwargs.copy()
        elif target == "Google":
            self.google_params = {"key": GET_ENV_VAR("SEARCH_API_KEY"), "cx": GET_ENV_VAR("SEARCH_CSE_ID")}
        else:
            raise ValueError(f"UNK search target = {target}")
        # --

    def set_llm(self, llm):
        self.llm = llm  # might be useful for formatting?

    def get_function_definition(self, short: bool):
            if short:
                return """- def simple_web_search(query: str) -> str:  # Perform a quick web search using a search engine for straightforward information needs."""
            else:
                return """- simple_web_search
```python
def simple_web_search(query: str) -> str:
    \""" Perform a quick web search using a search engine for straightforward information needs.
    Args:
        query (str): A simple, well-phrased search term or question.
    Returns:
        str: A string containing search results, including titles, URLs, and snippets.
    Notes:
        - Use for quick lookups or when you need up-to-date information.
        - Avoid complex or multi-step queries; keep the query simple and direct.
        - Do not use for tasks requiring deep reasoning or multi-source synthesis.
    Examples:
        >>> answer = simple_web_search(query="latest iPhone")
        >>> print(answer)
    \"""
```"""

    def __call__(self, query: str):
        target = self.target
        if target == "DuckDuckGo":
            from duckduckgo_search import DDGS
            ddgs = DDGS(**self.ddgs_params)
            rprint(f"Query ddgs with: query={query}, max_results={self.max_results}")
            results = ddgs.text(query, max_results=self.max_results)
            search_results = [{"title": _item["title"], "link": _item["href"], "content": _item["body"]} for _item in results]
        elif target == "Google":
            url = "https://www.googleapis.com/customsearch/v1"
            params = self.google_params.copy()
            params.update({"q": query, "num": self.max_results})
            rprint(f"Query google-search with params={params}")
            response = requests.get(url, params=params)
            results = response.json()
            search_results = [{"title": _item["title"], "link": _item["link"], "content": _item.get("snippet", "")} for _item in results.get("items", [])]
        else:
            raise ValueError(f"UNK search target = {target}")
        
        if len(search_results) == 0:
            ret = "Search Results: No results found! Try a less restrictive/simpler query."
        elif self.list_enum:
            ret = "Search Results:\n" + "\n".join([f"({ii}) title={repr(vv['title'])}, link={repr(vv['link'])}, content={repr(vv['content'])}" for ii, vv in enumerate(search_results)])
        else:
            ret = "Search Results:\n" + "\n".join([f"- title={repr(vv['title'])}, link={repr(vv['link'])}, content={repr(vv['content'])}" for ii, vv in enumerate(search_results)])
        
        elements = [
            {
                "type": "text",
                "text": ret,
            }
        ]
        return json.dumps(elements, ensure_ascii=False)

class SimpleVLSearchTool(Tool):
    def __init__(self, llm=None, max_results=5, list_enum=True, byte=True, **kwargs):
        super().__init__(name="simple_image_search")
        self.llm = llm
        self.max_results = max_results
        self.list_enum = list_enum
        self.byte = byte
        self.key = GET_ENV_VAR("SEARCH_API_KEY")
        self.Download_Upload = Download_Upload()

    def set_llm(self, llm):
        self.llm = llm  # might be useful for formatting?

    def bind_registry(self, get_image_url_fn, register_image_fn):
        self.get_image_url = get_image_url_fn
        self.register_image = register_image_fn

    def _looks_like_url(self, s: str) -> bool:
        # 简单判断：以 http(s) 开头就认为是 URL
        return s.startswith("http://") or s.startswith("https://")

    def _is_base64(self, s: str) -> bool:
        try:
            # 粗糙校验，避免把普通短文本误当 base64
            if len(s) < 50:
                return False
            base64.b64decode(s, validate=True)
            return True
        except Exception:
            return False

    def resolve_image_url(self, img_id: str) -> str:
        """
        img_id -> real url
        get_image_url(img_id) 应由执行器注入（从 session.registry 取）
        """
        if not isinstance(img_id, str) or not img_id.strip():
            raise ValueError("IMAGE_ID_INVALID: empty img_id")
        return self.get_image_url(img_id)  # <-- injected

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

    def get_function_definition(self, short=False):
        if short:
            return """- def simple_image_search(image_id: str) -> str:  # Perform a quick web image search using a search engine for straightforward information needs, given an image id."""
        else:
            return """- simple_image_search
```python
def simple_image_search(image_id: str) -> str:
\""" Perform a quick web search using a search engine for straightforward information needs.
Args:
    image_id (str): id of the input image.
Returns:
    str: A string containing search results, including images, URLs, and snippets.
Notes:
    - Use for quick lookups or when you need up-to-date information of input image.
    - Avoid multiple images.
    - Do not use for images requiring deep reasoning or multi-source synthesis.
Examples:
    >>> answer = simple_image_search(image_id="img_id:<int>")
    >>> print(answer)
\"""
```"""

    def __call__(self, image_id: str, retry_attempt=1, results_int=5):
        # img_id -> url
        image_url = self.resolve_image_url(image_id)

        if self._looks_like_url(image_url):
            # URL：调用 download 逻辑，返回 base64
            image_b64 = self.Download_Upload.try_download_tencent(image_url)
            if image_b64 is None:
                return "[image_processor] Error: failed to download image from URL."
        elif self._is_local_image_path(image_input):
            image_b64 = self._path_to_data_url_b64(image_input)
            if image_b64 is None:
                elements = [{"type": "text", "text": "[VL agent] Error: failed to download image from URL."}]
                return json.dumps(elements, ensure_ascii=False)
        else:
            # 非 URL：尝试当作 base64 使用
            if not self._is_base64(image_url):
                return "[image_processor] Error: input is neither a valid URL nor a valid base64 image."
            image_b64 = image_url

        search_results = []
        url = "https://vision.googleapis.com/v1/images:annotate"
        headers = {"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"}
        payload = {
        "requests": [
            {
                "image": {
                    "content": image_b64  # "BASE64_ENCODED_IMAGE"
                },
                "features": [
                    {
                        "maxResults": results_int,  
                        "type": "WEB_DETECTION"
                    }
                ]
            }]}
        # breakpoint()
        for attempt in range(retry_attempt):
            try:
                response = requests.post(url, headers=headers, json=payload, timeout=1)
                rst = response.json()
                docs = rst.get('responses')[0].get('webDetection')
                web_entities = docs.get("webEntities")
                image_entities = docs.get("fullMatchingImages")
                search_entities = docs.get("pagesWithMatchingImages")

                descriptions = []
                for entity in web_entities:
                    desc = entity.get("description")
                    if desc:
                        descriptions.append(desc)

                description_str = "Here are description keywords of input image: " + ", ".join(descriptions)
                
                search_data = [
                    {
                        "search_image": img.get("url", ""),
                        "snippet": page.get("pageTitle", ""),
                        "link": page.get("url", "")
                    }
                    for page, img in zip(search_entities, image_entities)
                ]

                search_results = self.download_upload(search_data, None, byte)
                # search_results = search_data
            except requests.exceptions.Timeout:
                print(f"请求超时(尝试 {attempt + 1}/{retry_attempt}): {download_url}")
            except Exception as e:
                # breakpoint()
                print(f"Error searching image via base64: {str(e)}. Retrying...")

        elements = []
        if len(search_results) == 0:
            # 没有结果时，就只放一段 text
            elements.append({
                "type": "text",
                "text": "Image Search Results: No results found!"
            })
        else:
            elements.append({
                "type": "text",
                "text": f"{description_str}\nImage Search Results:"
            })

            for idx, item in enumerate(search_results):
                img_url = item.get("search_image", "") or ""
                snippet = item.get("snippet", "") or ""
                link = item.get("link", "") or ""

                try:
                    # register（写入 registry，LLM 后续可引用 img_id）
                    img_id = self.register_image(
                        img_url,
                        desc=f"image_search_result_{idx}",
                        meta={
                            "source": "image_search",
                            "snippet": snippet,
                            "link": link
                        }
                    )
                except Exception as e:
                    zwarn(f"[SimpleVLSearchTool]: failed to register image {img_url}: {e}")
                    img_id = "unregistered"

                # 先加 image
                if img_url:
                    elements.append({
                        "type": "image_url",
                        "image_url": img_url,
                    })
                # 再加对应的文字说明
                text_content = f"caption: {snippet}; link: {link}; image_id: {img_id}"
                elements.append({
                    "type": "text",
                    "text": text_content,
                })
        result = json.dumps(elements, ensure_ascii=False)
        return result


# class SimpleImageExecTool(Tool):
#     """
#     Execute *user-supplied* Python snippets inside CodeExecutor with a preloaded
#     Pillow/Numpy helper environment. The snippet should use the helpers documented
#     in get_function_definition(False), and must `print(...)` or call `save_image(img)`
#     to produce output captured by the executor.
#     """

#     def __init__(self, llm=None, default_format="PNG"):
#         super().__init__(name="image_processor")
#         # 原代码里引用了未定义的 executor 变量，这里直接内部创建一个
#         self.executor = CodeExecutor()
#         self.llm = llm
#         self.default_format = default_format
#         self.Download_Upload = Download_Upload()

#     def set_llm(self, llm):
#         self.llm = llm

#     def _maybe_decode_image_base64(self, s: str):
#         """
#         尝试把字符串当作 base64 图片解码。
#         成功返回 bytes，失败返回 None。
#         """
#         try:
#             data = base64.b64decode(s, validate=True)
#             # 粗略过滤一下极短内容，避免把普通短文本当成图片
#             if len(data) < 50:
#                 return None
#             return data
#         except Exception:
#             return None

#     def get_function_definition(self, short=False) -> str:
#         if short:
#             return (
#                 "- def image_processor(code: str, image_url: str, out_format: str='PNG') -> str:  "
#                 "Download image from URL, run Python snippet in a sandbox to edit it, "
#                 "and return a URL of the processed image. For analysis-only code, returns text."
#             )
#         return """- image_processor
# ```python
# def image_processor(code: str, image_url: str, out_format: str = "PNG") -> str:
#     \"""Download image from URL, run user-supplied code inside a sandbox with Pillow/Numpy helpers preloaded.
#     You MUST call "image_processor" to process images (e.g., crop, enhance) and emit images. Otherwise the system will not be able to execute the code.
#     =========================
#     Preloaded Environment
#     =========================
#     Imports:
#         import io, base64, json
#         import numpy as np
#         from PIL import Image, ImageOps, ImageEnhance, ImageDraw
#     Preloaded helpers (already defined; DO NOT redefine):
#         load_image() -> PIL.Image
#             - Decodes the provided base64 input and returns a PIL image.
#             - The internal working mode is unified to "RGBA" for safety.
#         save_image(img: PIL.Image) -> None
#             - Encodes the image to base64 using the chosen output format (PNG by default)
#               and prints the resulting base64 string (executor captures print output).
#             - Also sets an internal flag so the tool knows an output was produced.
#         to_numpy(img: PIL.Image, mode="RGB") -> np.ndarray
#             - Converts a PIL image to a numpy array (H, W, C) after optional mode conversion.
#     Notes:
#         - JPEG saving will drop alpha channel automatically.
#         - For image-producing actions, you SHOULD call save_image(img) to return base64.
#         - If you forget and store the result in variable `out`, the tool will attempt to print it automatically.
#         - For computational actions, print(...) the text/JSON you want to return.
#     =========================
#     Actions & Minimal Examples
#     =========================
#     1) Cropping (center 256x256):
#         img = load_image()
#         W, H = img.size
#         w, h = 256, 256
#         L = max(0, (W - w)//2); T = max(0, (H - h)//2)
#         R = min(W, L + w);      B = min(H, T + h)
#         out = img.crop((L, T, R, B))
#         save_image(out)
#     2) Rotation (rotate 90 deg):
#         img = load_image()
#         out = img.rotate(90, expand=True, resample=Image.BICUBIC)
#         save_image(out)
#     3) Low-Contrast Enhancement (autocontrast):
#         img = load_image()
#         out = ImageOps.autocontrast(img, cutoff=0)
#         save_image(out)
#        Or Contrast factor=1.5:
#         img = load_image()
#         out = ImageEnhance.Contrast(img).enhance(1.5)
#         save_image(out)
#     4) Mark (draw rectangle + text):
#         img = load_image()
#         draw = ImageDraw.Draw(img)
#         draw.rectangle([50, 50, 250, 200], outline=(255, 0, 0), width=4)
#         draw.text((60, 60), "object", fill=(255, 255, 0))
#         save_image(img)
#     5) Image Analysis (no image output):
#         img = load_image()
#         arr = to_numpy(img, mode="RGB")
#         mean_rgb = arr.reshape(-1, 3).mean(axis=0).tolist()
#         print(json.dumps({"mean_rgb": mean_rgb}))
#     \"""
# ```"""
#     def _looks_like_url(self, s: str) -> bool:
#         # 简单判断：以 http(s) 开头就认为是 URL
#         return s.startswith("http://") or s.startswith("https://")

#     def _is_base64(self, s: str) -> bool:
#         try:
#             # 粗糙校验，避免把普通短文本误当 base64
#             if len(s) < 50:
#                 return False
#             base64.b64decode(s, validate=True)
#             return True
#         except Exception:
#             return False

#     def __call__(self, code: str, image_url: str, out_format: str = None, timeout: int = 30) -> str:
#         """
#         Run user code inside CodeExecutor with a preloaded helper preamble.
#         Returns whatever the code prints (base64 for image ops).
#         Additionally, if user code set a variable `out` to a PIL.Image but did not call save_image(out),
#         the tool will automatically print that image as base64, turn it into bytes and upload.
#         """
#         if self._looks_like_url(image_url):
#             # URL：调用 download 逻辑，返回 base64
#             image_b64 = self.Download_Upload.try_download_tencent(image_url)
#             if image_b64 is None:
#                 return "[image_processor] Error: failed to download image from URL."
#         else:
#             # 非 URL：尝试当作 base64 使用
#             if not self._is_base64(image_url):
#                 return "[image_processor] Error: input is neither a valid URL nor a valid base64 image."
#             image_b64 = image_url
#         ofmt = (out_format or self.default_format).upper()
#         preamble = f"""
# import io, base64, json
# import numpy as np
# from PIL import Image, ImageOps, ImageEnhance, ImageDraw

# # ---------- Helpers preloaded into the snippet environment ----------
# _INPUT_IMAGE_B64 = {json.dumps(image_base64)}
# _OUT_FORMAT = {json.dumps(ofmt)}
# _DID_SAVE = False  # flag to detect whether user has produced output via save_image()

# def _b64_to_image(b64_str: str) -> Image.Image:
#     raw = base64.b64decode(b64_str)
#     img = Image.open(io.BytesIO(raw))
#     return img.convert("RGBA")  # unify internal mode

# def _image_to_b64(img: Image.Image, fmt: str) -> str:
#     buf = io.BytesIO()
#     _img = img
#     if fmt == "JPEG" and img.mode in ("RGBA", "LA"):
#         # drop alpha for JPEG
#         _img = Image.new("RGB", img.size)
#         _img.paste(img, mask=img.split()[-1])
#     _img.save(buf, format=fmt)
#     return base64.b64encode(buf.getvalue()).decode("utf-8")
 
# def load_image() -> Image.Image:
#     return _b64_to_image(_INPUT_IMAGE_B64)
# def save_image(img: Image.Image):
#     global _DID_SAVE
#     print(_image_to_b64(img, _OUT_FORMAT))  # executor collects via custom_print
#     _DID_SAVE = True
# def to_numpy(img: Image.Image, mode="RGB"):
#     if mode:
#         img = img.convert(mode)
#     return np.array(img)
# # -------------------------------------------------------------------
# """
#         # 自动尾声：如果用户没调用 save_image，但定义了变量 out 且为 PIL.Image，则自动 save_image(out)
#         epilogue = r"""
# # ===== AUTO EPILOGUE =====
# try:
#     from PIL import Image as __PILImage
#     if (not _DID_SAVE) and ('out' in globals()) and isinstance(out, __PILImage.Image):
#         save_image(out)
# except Exception:
#     pass
# """

#         full_code = preamble + "\n# ===== USER CODE START =====\n" + code + "\n# ===== USER CODE END =====\n" + epilogue
#         # breakpoint()

#         # Run in executor (必须执行 full_code，而不是原始 code)
#         self.executor.results.clear()
#         self.executor.run(full_code, catch_exception=True, null_stdin=True, timeout=timeout)

#         out = self.executor.get_print_results(clear=True)
#         if isinstance(out, list):
#             out = "\n".join(str(x) for x in out)
#         if not isinstance(out, str):
#             out = "" if out is None else str(out)
        
#         img_bytes = self._maybe_decode_image_base64(out)
#         if img_bytes is None:
#             raise ValueError("[image_processor] Error: the code did not produce valid base64 image output. Please ensure to call save_image(img) or print base64 string.")

#         try:
#             url = self.Download_Upload.upload(img_bytes, byte=True)
#             if url is None:
#                 raise ValueError("[SimpleImageExecTool] Failed to upload processed image: upload returned None")

#             elements = [
#             {
#                 "type": "text",
#                 "text": "[image_processor] The output image:"
#             },
#             {
#                 "type": "image_url",
#                 "image_url": url
#             }
#         ]
#             return json.dumps(elements, ensure_ascii=False)
#         except Exception as e:
#             raise ValueError(f"[SimpleImageExecTool] Failed to upload processed image: {e}")




if __name__ == "__main__":
    pass

# cd /path/to/cognitive_kernel_GAIA/System
# python -m ckv3.agents.tool
# 测不了，得先配梯子
