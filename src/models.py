"""
Utilities for interacting with existing models: QWEN2.5-VL
"""
# General/shared imports
from pathlib import Path
import torch

# Global variables (**YOU** will likely need to change these for your setup)
from globals import MODELS_DIR, CREDENTIALS_DIR, GCLOUD_API_KEY_FILENAME

# Qwen2.5-VL-7B Instruct
from transformers import Qwen2_5_VLForConditionalGeneration, AutoProcessor
from qwen_vl_utils import process_vision_info

# Gemini
import google.generativeai as genai     # note that we use the older google-generativeai SDK, not the newer google-genai one; see https://ai.google.dev/gemini-api/docs/migrate
import mimetypes, time

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


    def video_inference(self, text: str, video: str, is_path: bool = False, max_pixels: int = 360 * 420, fps: float = 1.0, max_tokens: int = 4096) -> list[str]:
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
    
    def second_pass(self, name: str, num: int, fps: int):
        prompt = 'Your job is to determine if a skateboarding trick is performed in the video clip. If one is performed, return YES. If one is not performed, return NO.'
        results = []
        for i in range(1, num + 1):
            vid_path = f"/gscratch/raivn/tanush/VideoNet/data/{name}_{i}.mp4"
            res = self.video_inference(prompt, vid_path, is_path=True, fps=fps)
            results.append(res[0])
        return results
    
    def bin_search(self, name: str, gt: list[bool]):
        l, r, num = 2.0, 30.0, len(gt)
        best_fps = float('inf')
        best_acc = float('-inf')
        while l < r:
            m = l + (r - l) // 2
            res = self.second_pass(name, num, m)
            res = [True if r == 'YES' else False for r in res]
            curr_acc = 0
            for i in range(num):
                curr_acc += int(gt[i] == res[i])
            if curr_acc >= best_acc:
                best_acc = curr_acc
                best_fps = min(best_fps, m)
                r = m - 1
            else:
                l = m + 1
        return best_fps, best_acc
    
class Gemini:
    # variables that *YOU* might need to change
    _MODEL_INFO = {
        "thinking": {"name": "gemini-2.0-flash-thinking-exp-01-21", "rpm": 10, "rpd": 1500},
        "flash": {"name": "gemini-2.0-flash-exp", "rpm": 10, "rpd": 1500},
        "flash-pro": {"name": "gemini-2.0-pro-exp-02-05", "rpm": 2, "rpd": 50},
        "flash-lite": {"name": "gemini-2.0-flash-lite-preview-02-05", "rpm": 30, "rpd": 1500}
    }

    def __init__(self, model_id: str, sys_instr: str | None = None):
        # get model info
        if model_id not in Gemini._MODEL_INFO:
            raise ValueError(f"`model_id` must be a key in the `{Gemini.__name__}._MODEL_INFO` map.")
        name, rpm, rpd = [*Gemini._MODEL_INFO[model_id].values()]

        # get api key
        api_file = CREDENTIALS_DIR + GCLOUD_API_KEY_FILENAME
        try:
            with open(api_file, 'r') as f:
                api_key = f.read().strip()
        except Exception as e:
            print("ERROR: unable to read Google GenAI API Key at ", api_file)
            raise e

        # set up a Gemini instance
        genai.configure(api_key=api_key)
        config = {
            "temperature": 0,
            "top_p": 0.95,
            "top_k": 64,
            "max_output_tokens": 65536,
            "response_mime_type": "text/plain"
        }
        self.model = genai.GenerativeModel(
            model_name = name,
            generation_config = config,
            system_instruction = sys_instr if sys_instr else "Be concise."
        )

    def upload_media(self, media: list[tuple[str | Path, str | None]]) -> list:
        if not media:
            return None

        if not isinstance(media, list):
            raise TypeError("`media` must be a list.")

        media_sanitized: list[tuple[str, str | None]] = []
        for m in media:
            if isinstance(m, tuple):
                if len(m) != 2:
                    raise ValueError("All tuples in `media` must have 2 elements.")
                local_path, mime_type = m
                if not isinstance(mime_type, str) and isinstance(mime_type, None):
                    raise TypeError("`media` must be a list of tuples where the second element is always a string (or None).")
                if mime_type and mime_type not in mimetypes.types_map.values():
                    raise ValueError("The second element of every tuple in `media` -- which itself is a list -- must be a valid MIME type (or None).")
            elif isinstance(m, str):
                local_path, mime_type = m, None
            elif isinstance(m, Path):
                local_path, mime_type = str(m), None
            else:
                raise TypeError("Elements of `media` must be tuples or strings.")
        
            if not isinstance(local_path, Path) and not isinstance(local_path, str):
                raise TypeError("`media` must be a list of tuples where the first element is always a Path-like object OR a string.")
            if not Path(local_path).exists():
                raise FileNotFoundError(f"`media` included a path to the following file, but no such file exists: {local_path}")

            media_sanitized.append((str(local_path), mime_type))

        files = [genai.upload_file(local_path, mime_type=mime_type) for local_path, mime_type in media_sanitized]

        print("\n\tMedia files have been uploaded to Gemini. \n\tCurrently waiting for them to be processed...", end="")
        # code from Google AI Studio demo
        for name in (file.name for file in files):
            file = genai.get_file(name)
            i = 0
            while file.state.name == 'PROCESSING' and i < 4:
                print(".", end="", flush=True)
                time.sleep(5)
                file = genai.get_file(name)
                i += 1
            if file.state.name != 'ACTIVE':
                raise Exception(f"File {file.name} failed to process")
        print("\n\tAll files are now ready!")
        print()

        return files

    def inference(self, prompt, media: list[tuple[Path | str, str | None] | Path | str]):
        # to avoid annoying warning message: https://github.com/grpc/grpc/issues/38490#issuecomment-2604775087
        # prompt = "You have been given a video that shows multiple skateboarding tricks. Your job is to help segment the different tricks. Provide a list of the start and end times of each trick that is performed. You do not need to name the trick, focus on providing the start and stop times.\n\nFormat your response as a list of segments. Each segment should be denoted MM:SS-MM:SS."
        try:
            files = self.upload_media(media)
        except Exception as e:
            print("ERROR: unable to upload the provided media files to Gemini.")
            raise e
        
        chat_session = self.model.start_chat(
            history = [ {'role': "user", 'parts': files} ]
        )
        response = chat_session.send_message(prompt)
        
        return response.text