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


class JiMengNode:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {"multiline": True}),
                "image": ("IMAGE",),
                "size": (size_preset, {"default": "3:4 (1728x2304)"}),
            },
        }

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "run"
    OUTPUT_NODE = False
    CATEGORY = "image"

    def run(self, prompt, image, size):

        return (image,)
