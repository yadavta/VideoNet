"""
Utilities for interacting with existing models: QWEN2.5-VL
"""
# General/shared imports
import torch

# Qwen2.5-VL-7B Instruct
from transformers import Qwen2_5_VLForConditionalGeneration, AutoTokenizer, AutoProcessor
from qwen_vl_utils import process_vision_info

MODELS_DIR = "/gscratch/raivn/tanush/models/"

class Qwen25VL:
    def __init__(self):
        """
        Initializes model and processor from Hugging Face transformers library.
        """
        self.model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
            "Qwen/Qwen2.5-VL-7B-Instruct", torch_dtype=torch.bfloat16, device_map="auto", 
            attn_implementation="flash_attention_2", cache_dir=MODELS_DIR
        )
        self.processor = AutoProcessor.from_pretrained("Qwen/Qwen2.5-VL-7B-Instruct")
        self.device = "cuda" if torch.cuda.is_available() else "cpu"

    def text_inference(self, text :str, max_tokens: int = 256):
        messages = [
            {
                "role": "user",
                "content": [
                    { "type": "text", "text": text }
                ]
            }
        ]
        text_inputs = self.processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = self.processor(text=[text_inputs], padding=True, return_tensors="pt")
        inputs = inputs.to(self.device)
        
        generated_ids = self.model.generate(**inputs, max_new_tokens=max_tokens)
        generated_ids_trimmed = [
            out_ids[len(in_ids) :] for in_ids, out_ids in zip(inputs.input_ids, generated_ids)
        ]
        output_text = self.processor.batch_decode(
            generated_ids_trimmed, skip_special_tokens=True, clean_up_tokenization_spaces=False
        )

        return output_text


    def video_inference(self, text: str, video: str, is_path: bool = False, max_pixels: int = 360 * 420, fps: float = 1.0, max_tokens: int = 4096):
        """
        Model generation with text and video input.

        By default, `video` is assumed to be a URL. If it is a local file, it should be an absolute path and the `is_path` flag should be turned on.
        """
        # Prepare message for model
        if is_path:
            video = f"file://{video}"
        messages = [
            {
                "role": "user",
                "content": [
                    { "type": "video", "video": video, "fps": fps }, 
                    { "type": "text",  "text": text }
                ]
            }
        ]

        # Prepare inputs

        text_inputs = self.processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        video_inputs: list[torch.Tensor]
        image_inputs, video_inputs = process_vision_info(messages)

        # inputs has the following keys: 'input_ids', 'attention_mask', 'pixel_values_videos', 'video_grid_thw', 'second_per_grid_ts'
        # all but the last key correspond to tensors; the last one corresponds to a list containing one float
        inputs: dict[str, torch.Tensor] = self.processor(
            text=[text_inputs],
            images=image_inputs,
            videos=video_inputs,
            fps=fps,
            padding=True,
            return_tensors="pt",
        )
        inputs: dict[str, torch.Tensor | list] = inputs.to(self.device)
        # print(f"FPS: {fps}    Input IDs: {inputs['input_ids'].size(1)}    Pixel Values: {inputs['pixel_values_videos'].size(0)}")

        # Inference
        generated_ids = self.model.generate(**inputs, max_new_tokens=max_tokens)

        # Prepare outputs
        generated_ids_trimmed = [
            out_ids[len(in_ids):] for in_ids, out_ids in zip(inputs.input_ids, generated_ids)
        ]
        output_text = self.processor.batch_decode(
            generated_ids_trimmed, skip_special_tokens=True, clean_up_tokenization_spaces=False
        )

        return output_text
    
    def test(self, name: str, num: int, fps: int):
        prompt = 'Your job is to determine if a skateboarding trick is performed in the video clip. If one is performed, return YES. If one is not performed, return NO.'
        results = []
        for i in range(1, num + 1):
            vid_path = f"/gscratch/raivn/tanush/VideoNet/data/{name}_{i}.mp4"
            res = self.video_inference(prompt, vid_path, is_path=True, fps=fps)
            results.append(res[0])
        return results
    
    def bin_search(self, name: str, num: int, gt: list[bool]):
        l, r, n = 2.0, 30.0, len(gt)
        best = float('inf')
        while l < r:
            m = l + (r - l) // 2
            res = self.test(name, num, m)
            res = [True if r == 'YES' else False for r in res]
            same = True
            for i in range(n):
                if gt[i] != res[i]:
                    same = False
                    break
            if same:
                r = m - 1
                best = min(best, m)
            else:
                l = m + 1
        return best