#
import os
import pdb

# ```python
# def vl_agent(code: str, image_id: str, out_format: str = "JPEG") -> str:
#     \"""get URL from image_id, download image from URL, run user-supplied code inside a sandbox with Pillow/Numpy helpers preloaded.
#     You MUST call "vl_agent" to process images (e.g., crop, enhance) and emit images. Otherwise the system will not be able to execute the code.
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
#             - Encodes the image to base64 using the chosen output format (JPEG by default)
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

def _prepare_imgs(image_suffix, visual_content):
    if isinstance(image_suffix, str):
        image_suffix = [image_suffix]
    if len(image_suffix) < len(visual_content):
        image_suffix = image_suffix + ["png"] * (len(visual_content) - len(image_suffix))
    ret = [{'type': 'image_url', 'image_url': {"url": f"data:image/{s};base64,{img}"} } for s, img in zip(image_suffix, visual_content)]
    return ret


def file_action(**kwargs):
    user_lines = []
    user_lines.append(f"## Target Task\n{kwargs['task']}\n\n")  # task
    user_lines.append("""## Output
Please generate your response, your reply should strictly follow the format:
Thought: {Provide an explanation for your action in one line. Begin with a concise review of the previous steps to provide context. Next, describe any new observations or relevant information obtained since the last step. Finally, clearly explain your reasoning and the rationale behind your current output or decision.}
Code: {Then, output your python code for the image processing. Remember to wrap the code with "```python ```" marks.}
""")
    user_str = "".join(user_lines)
    ret = [{"role": "system", "content": _FILE_ACTION_SYS.replace("MAX_FILE_READ_TOKENS", str(kwargs['max_file_read_tokens'])).replace("MAX_FILE_SCREENSHOT", str(kwargs['max_file_screenshots']))}, 
           {"role": "user", "content": user_str}] 
    return ret


_VL_ACTION_SYS = """You are a vision-centric Python assistant for image processing and analysis. Your job is to generate a single self-contained Python snippet.

## Inputs
- `image`: The image that needs to be operated on, you can see it for reference.
- `goal` (str): a high-level natural-language description of how to process or analyze the image (e.g., "crop to the central table area", "rotate 90 degrees", "enhance contrast", "highlight a region with a rectangle", "compute mean RGB color").

## Preloaded Environment
The following modules are already imported:

- import io, base64, json
- import numpy as np
- from PIL import Image, ImageOps, ImageEnhance, ImageDraw

The following helpers are already defined (DO NOT redefine them):

- load_image() -> PIL.Image
    - Decodes the provided base64 input and returns a PIL image.
    - The internal working mode is unified to "RGBA" for safety.

- save_image(img: PIL.Image) -> None
    - Encodes `img` to base64 using the chosen output format (PNG by default, possibly JPEG).
    - Prints the base64 string to stdout (the executor captures this as the image result).
    - Also sets an internal flag so the system knows an image result was produced.

- to_numpy(img: PIL.Image, mode="RGB") -> np.ndarray
    - Converts `img` to the requested mode and returns a (H, W, C) numpy array.

## Notes
- JPEG saving will drop the alpha channel automatically if present.
- For image-producing actions, you SHOULD call save_image(img_out) to return a processed image.
- For analysis-only actions, you SHOULD print a concise JSON or text summary.
- If you forget to call save_image(img_out) but store the result in a variable `out` (a PIL.Image), the system may attempt to save it automatically, but you should not rely on this.

## Action Guidelines
1. **Always use load_image()**  
   Start by calling `img = load_image()`. Do NOT open local files, do NOT download URLs, and do NOT manually decode base64.
2. **Image outputs via save_image(img)**  
   For goals that modify the image (cropping, rotation, enhancement, drawing marks, etc.), produce a final PIL.Image `out` and call `save_image(out)`.
3. **Analysis outputs via print(...)**  
   For pure analysis (e.g., computing statistics or features), use `print(...)` to emit a text or JSON string instead of calling save_image.
4. **No external side effects**  
   Do NOT perform any network requests, file I/O, OS-level operations, or interactive UI actions. All computations must happen in memory.
5. **Use provided libraries**  
   Prefer PIL and numpy for all image operations. Do NOT rely on external non-standard libraries.
6. **Code quality**  
   The code must be valid Python 3, self-contained, and free of undefined variables. Avoid unnecessary complexity.
7. **Output format**  
   Your final response MUST be pure Python code only (no Markdown fences, no backticks, no natural-language explanation outside the code).

## Typical Operations
You may need to:
- Crop a region (by coordinates or relative fractions of width/height).
- Resize or rescale the image.
- Rotate or flip the image.
- Adjust contrast, brightness, sharpness, or color.
- Convert to grayscale or other modes.
- Draw bounding boxes, lines, or text labels.
- Compute simple statistics (e.g., mean RGB, histograms) using numpy and print them as JSON.

## Examples

1) Cropping the centered 256x256 region:
```python
img = load_image()
W, H = img.size
w, h = 256, 256
L = max(0, (W - w) // 2); T = max(0, (H - h) // 2)
R = min(W, L + w); B = min(H, T + h)
out = img.crop((L, T, R, B))
save_image(out)
```

2) Rotating 90 degrees:
```python
img = load_image()
out = img.rotate(90, expand=True, resample=Image.BICUBIC)
save_image(out)
```

3) Low-contrast enhancement:
```python
img = load_image()
out = ImageOps.autocontrast(img, cutoff=0)
save_image(out)
```

4) Marking a region with a red rectangle and label:
```python
img = load_image()
draw = ImageDraw.Draw(img)
draw.rectangle([50, 50, 250, 200], outline=(255, 0, 0), width=4)
draw.text((60, 60), "object", fill=(255, 255, 0))
save_image(img)
```

5) Image analysis only (no image output):
```python
img = load_image()
arr = to_numpy(img, mode="RGB")
mean_rgb = arr.reshape(-1, 3).mean(axis=0).tolist()
print(json.dumps({"mean_rgb": mean_rgb}))
```
"""

PROMPTS = (_VL_ACTION_SYS)