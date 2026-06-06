import os
import json
import requests
from urllib.parse import urlparse
from PIL import Image, ImageDraw
from io import BytesIO
import base64
import math
 
dataset_name = os.getenv("DATASET", "ck_image_test")
 
class ImageProcessor:
    def __init__(self, max_pixels=1024*1024, min_pixels=256*256):
        self.max_pixels = max_pixels
        self.min_pixels = min_pixels
        self.output_dir = os.path.join("../data/vl/images", dataset_name)
    
    def download_image(self, image_url):
        os.makedirs(self.output_dir, exist_ok=True)

        image_name = os.path.basename(urlparse(image_url).path)
        image_path = os.path.join(self.output_dir, image_name)
        try:
            response = requests.get(image_url)
            if response.status_code == 200:
                with open(image_path, 'wb') as img_file:
                    for chunk in response.iter_content(1024):
                        img_file.write(chunk)
                print(f"成功下载图片: {image_name}")
            else:
                print(f"下载失败: {image_url} (状态码: {response.status_code})")
            return image_path
        except Exception as e:
            zwarn(f"Failed to download image from {image_url}: {e}")
            return None
 
    def process_image(self, image):
        if isinstance(image, dict):
            image = Image.open(BytesIO(image['bytes']))
        elif isinstance(image, str):
            image = Image.open(image)

        if (image.width * image.height) > self.max_pixels:
            resize_factor = math.sqrt(self.max_pixels / (image.width * image.height))
            width, height = int(image.width * resize_factor), int(image.height * resize_factor)
            image = image.resize((width, height))

        if (image.width * image.height) < self.min_pixels:
            resize_factor = math.sqrt(self.min_pixels / (image.width * image.height))
            width, height = int(image.width * resize_factor), int(image.height * resize_factor)
            image = image.resize((width, height))

        if image.mode != 'RGB':
            image = image.convert('RGB')
        
        byte_stream = BytesIO()
        image.save(byte_stream, format="JPEG")
        byte_array = byte_stream.getvalue()
        base64_encoded_image = base64.b64encode(byte_array)
        base64_string = base64_encoded_image.decode("utf-8")
        base64_qwen = f"data:image;base64,{base64_string}"

        return image, base64_qwen

    def call(self, image):

        if image.startswith("http://") or image.startswith("https://"):
            image_path = self.download_image(image)
        else:
            image_path = image
        
        if image_path is None:
            raise RuntimeError(f"Failed to download image from {image} or cannot find local image from {image}.")

        image_raw = Image.open(image_path)
        _, test_img_base64 = self.process_image(image_raw)

        return test_img_base64
