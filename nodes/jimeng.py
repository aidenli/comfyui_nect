import os
import shutil
import json
import subprocess
from typing import List, Union
import torch 
from PIL import Image
import numpy as np
from dotenv import load_dotenv
import requests
from .server import start_node_server

load_dotenv()

size_preset = [
    "智能",
    "21:9 (3024x1296)",
    "16:9 (2560x1440)",
    "3:2 (2496x1664)",
    "4:3 (2304x1728)",
    "1:1 (2048x2048)",
    "3:4 (1728x2304)",
    "2:3 (1664x2496)",
    "9:16 (1440x2560)",
]

# 获取当前路径
current_path = os.path.dirname(os.path.abspath(__file__))
# 获取上级路径
parent_path = os.path.dirname(current_path)
downloads_path = os.path.join(parent_path, "downloads")
refs_path = os.path.join(parent_path, "refs")
logs_path = os.path.join(parent_path, "logs")
state_path = os.path.join(parent_path, "state")


def init_resources():
    # 创建downloads，refs，logs目录
    os.makedirs(downloads_path, exist_ok=True)
    os.makedirs(refs_path, exist_ok=True)
    os.makedirs(logs_path, exist_ok=True)
    os.makedirs(state_path, exist_ok=True)   

def reset_resources():
    # 清空downloads，refs，logs目录
    shutil.rmtree(downloads_path, ignore_errors=True)
    shutil.rmtree(refs_path, ignore_errors=True)
    # 重新创建目录
    init_resources()


def _save_tensor_to_png(t: "torch.Tensor", out_path: str):
    # Normalize and convert a torch tensor to PNG.
    # Supports HWC, CHW, or BHWC/BCHW (will use first image for batched tensors).
    tt = t.detach().cpu()
    if tt.ndim == 4:  # batched
        tt = tt[0]
    if tt.ndim == 3:
        if tt.shape[0] in (1, 3, 4):  # CHW
            tt = tt.permute(1, 2, 0)
        # tt now HWC
        arr = (tt.clamp(0, 1).numpy() * 255).astype("uint8")
        Image.fromarray(arr).save(out_path)
    elif tt.ndim == 2:  # HW (grayscale)
        arr = (tt.clamp(0, 1).numpy() * 255).astype("uint8")
        Image.fromarray(arr).save(out_path)
    else:
        raise ValueError("Unsupported tensor shape for image saving")


def _save_image_any(img: Union["torch.Tensor", "Image.Image"], out_path: str):
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    if isinstance(img, torch.Tensor):
        _save_tensor_to_png(img, out_path)
        return
    if isinstance(img, Image.Image):
        img.save(out_path)
        return
    # Fallback: try numpy array (HWC)
    if isinstance(img, np.ndarray):
        if img.ndim == 3:
            Image.fromarray(img.astype("uint8")).save(out_path)
            return
    raise ValueError("Unsupported image type for saving")


# --- 通过 Web 服务调用生成接口 ---
def request_generate_image_api(model, prompt, size: str = None, refs_json: str = None):
    """
    调用 Node.js 生成图片的 API
    - prompt: 文本提示词
    - size: 比值字符串，如 "9:16"
    - refs_json: JSON 序列化的本地图片路径数组字符串
    """
    try:
        PORT = os.getenv("PORT", "11880")
        url = f"http://localhost:{PORT}/api/generate-image"
        payload = {
            "model": model,
            "prompt": prompt,
            "size": size or "9:16",
            "refs": json.loads(refs_json) if refs_json else [],
        }
        resp = requests.post(url, json=payload, timeout=300)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"errcode": 1, "errmsg": f"请求异常: {e}"}


class JiMengNode:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "model": (["图片 4.0", "图片 3.1"], {"default": "图片 4.0"}),
                "prompt": ("STRING", {"multiline": True}),
                "size": (size_preset, {"default": "3:4 (1728x2304)"}),
            },
            "optional": {
                "images": ("IMAGE",),
                "seed": ("INT", {"default": 0, "min": 0, "max": 2147483647}),
            },
        }

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "run"
    OUTPUT_NODE = False
    CATEGORY = "image"

    def run(self, model, prompt, images=None, size=None, seed=None):
        reset_resources()
        start_node_server()

        saved_paths: List[str] = []
        start_idx = 1
        # 处理并保存传入的 images（如果有）
        if images is not None:
            imgs = images if isinstance(images, (list, tuple)) else [images]
            for i, img in enumerate(imgs):
                out_name = f"{start_idx + i}.png"
                out_path = os.path.join(refs_path, out_name)
                _save_image_any(img, out_path)
                saved_paths.append(out_path)

        # 将 ComfyUI 的 size 文本映射到 main.js 所需的比值
        size_arg = "9:16"
        if isinstance(size, str) and size:
            size_arg = size.split()[0]

        # 调用接口生成图片
        response = request_generate_image_api(model, prompt, size_arg, json.dumps(saved_paths))
        if response.get("errcode") != 0:
            print(f"接口调用失败，错误码：{response.get('errcode')}，错误信息：{response.get('errmsg')}")
            return (None,)

        image_list = response.get("data", {}).get("imageList")
        if not image_list:
            print("接口返回空图片列表")
            return (None,)

        result_imgs = []
        for img_path in image_list:
            try:
                img = Image.open(img_path)
                arr = np.array(img).astype(np.float32) / 255.0  # HWC, 0-1
                tensor = torch.from_numpy(arr).unsqueeze(0)  # (1,H,W,C)
                result_imgs.append(tensor)
            except Exception as e:
                print(f"读取图片失败: {img_path}, {e}")
        if len(result_imgs) == 0:
            return (None,)
        result_stack = torch.cat(result_imgs, dim=0)  # (N,H,W,C)
        return (result_stack,)
