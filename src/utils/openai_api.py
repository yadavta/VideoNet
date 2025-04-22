import ast
import base64
import io
import json
import os
import sys
import time
from typing import Dict, List, Optional, Union
from pathlib import Path

import backoff
import requests
from loguru import logger
from openai import APIConnectionError, BadRequestError, OpenAI, RateLimitError
from openai.types.completion_usage import CompletionUsage
from PIL import Image
from pydantic import BaseModel
from tqdm import tqdm


class Message(BaseModel):
    role: str
    content: str


RETRY_ERRORS = (RateLimitError, APIConnectionError)
API_COST = {
    'gpt-4o': { # 'gpt-4o-2024-08-06'
        'input_tokens': 2.5 / 1e6,
        'cached_input_tokens': 1.25 / 1e6, 
        'output_tokens': 10.0 / 1e6,
    },
    'gpt-4o-2024-11-20': {
        'input_tokens': 2.5 / 1e6,
        'cached_input_tokens': 1.25 / 1e6, 
        'output_tokens': 10.0 / 1e6,
    },
    'gpt-4o-2024-08-06': {
        'input_tokens': 2.5 / 1e6,
        'cached_input_tokens': 1.25 / 1e6, 
        'output_tokens': 10.0 / 1e6,
    },
    'gpt-4o-2024-05-13': {
        'input_tokens': 5.0 / 1e6,
        'cached_input_tokens': 5.0 / 1e6, 
        'output_tokens': 15.0 / 1e6,
    },
    'o3-mini': { # 'o3-mini-2025-01-31'
        'input_tokens': 1.1 / 1e6,
        'cached_input_tokens': 0.55 / 1e6, 
        'output_tokens': 4.4 / 1e6,
    },
    'o3-mini-2025-01-31': {
        'input_tokens': 1.1 / 1e6,
        'cached_input_tokens': 0.55 / 1e6, 
        'output_tokens': 4.4 / 1e6,
    },
    'o1': { # 'o1-2024-12-17'
        'input_tokens': 15.0 / 1e6,
        'cached_input_tokens': 7.5 / 1e6, 
        'output_tokens': 60.0 / 1e6,
    },
    'o1-2024-12-17': {
        'input_tokens': 15.0 / 1e6,
        'cached_input_tokens': 7.5 / 1e6, 
        'output_tokens': 60.0 / 1e6,
    },
    
    'whisper-1': {
        'cost_per_minute': 0.006,
    }
}
BATCH_FILE_LIMIT = 200 # MB

### Helper functions
def read_image(filepath) -> Image.Image:
    if os.path.isfile(filepath):
        raw_image = Image.open(filepath)
    else:
        raw_image = Image.open(requests.get(filepath, stream=True).raw)
    raw_image = raw_image.convert("RGB")
    
    return raw_image

def encode_image(image_input: Union[str, Image.Image]):
    if isinstance(image_input, str):  # if it's a file path
        with open(image_input, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')
    elif isinstance(image_input, Image.Image):  # if it's a PIL Image object
        byte_arr = io.BytesIO()
        image_input.save(byte_arr, format='PNG')  # you can change the format if you like
        return base64.b64encode(byte_arr.getvalue()).decode('utf-8')
    else:
        raise ValueError(f"Invalid image input: {image_input}. Must be a file path or PIL Image object.")

def prepare_image_payload(image_input: str | Image.Image) -> str:
    """ Prepare image payload for API call """
    if isinstance(image_input, str):
        if ('https://' in image_input or 'http://' in image_input):
            image_content = image_input
        else: # local file
            assert os.path.isfile(image_input)
            image_content = f"data:image/jpeg;base64,{encode_image(image_input)}"
    else:
        image_content = f"data:image/jpeg;base64,{encode_image(image_input)}"
    return image_content

def is_json_schema(response_format) -> bool:
    if isinstance(response_format, dict):
        return response_format["type"] == "json_schema"
    try:
        return issubclass(response_format, BaseModel)
    except Exception:
        return False
### 
class OpenaiAPI:

    def __init__(self, api_key=None, backoff_seconds=3, max_tries=3):
        """ 
        Initializes the OpenAI API client with the provided API key and retry settings.
        Args:
            api_key (str, optional): The API key for authenticating with the OpenAI service. Defaults to None.
            backoff_time (int, optional): The time in seconds to wait between retry attempts when a request fails. Defaults to 3.
            max_tries (int, optional): The maximum number of retry attempts for a failed request. Defaults to 3.
        """
        self.client = OpenAI(api_key=api_key)
        self.backoff_seconds = backoff_seconds
        self.max_tries = max_tries
        self.logger = logger
    
    def retry_api_call(self, fn, *args, **kwargs):
        ''' Retry API call with exponential backoff '''
        @backoff.on_exception(backoff.expo, (RateLimitError, APIConnectionError), max_tries=self.max_tries, factor=2)
        def _call_api():
            return fn(*args, **kwargs)
        return _call_api()
    
    def run_asr(self, audio_input, model: str='whisper-1') -> dict:
        def _run_asr():
            response = self.client.audio.translations.create(
                model=model, file=audio_input, response_format='verbose_json')
            response = response.model_dump()
            response['cost'] = API_COST[model]['cost_per_minute'] * (response['duration'] / 60)
            return response

        return self.retry_api_call(_run_asr)
    
    @classmethod
    def get_response_format(cls, response_format: str | BaseModel, is_batch_api=False) -> dict | BaseModel:
        ''' Returns response format for API call. '''
        if response_format is None:
            return {"type": "text"}
        
        if isinstance(response_format, str):
            if response_format in ["json", "json_object"]:
                return {"type": "json_object"}
            
        if is_json_schema(response_format):
            if is_batch_api:
                try:
                    return {
                        "type": "json_schema",
                        "json_schema": {
                            "name": response_format.__name__,
                            "schema": response_format.schema(),
                        }
                    }
                except Exception:
                    pass
            else:
                return response_format
        
        raise ValueError(f"Invalid response format: {response_format}")
    
    def _extract_tokens(self, usage: dict) -> dict:
        """Extract token counts from API usage info."""
        prompt_tokens = usage.get('prompt_tokens', 0)
        cached_input_tokens = usage.get('prompt_tokens_details', {}).get('cached_tokens', 0)
        input_tokens = prompt_tokens - cached_input_tokens
        output_tokens = usage.get('completion_tokens', 0)
        total_tokens = usage.get('total_tokens', 0)
        return {
            'input_tokens': input_tokens,
            'cached_input_tokens': cached_input_tokens,
            'output_tokens': output_tokens,
            'total_tokens': total_tokens
        }

    def get_api_usage(self, model, usage):
        if isinstance(usage, BaseModel):
            usage = usage.model_dump()
        tokens = self._extract_tokens(usage)
        tokens['cost'] = self.get_api_cost(model, usage)
        return tokens

    def get_api_cost(self, model, usage):
        """Calculate API cost based on usage."""
        if isinstance(usage, BaseModel):
            usage = usage.model_dump()
        tokens = self._extract_tokens(usage)
        cost = (
            API_COST[model]['input_tokens'] * tokens['input_tokens'] +
            API_COST[model]['cached_input_tokens'] * tokens['cached_input_tokens'] +
            API_COST[model]['output_tokens'] * tokens['output_tokens']
        )
        return cost
    
    def generate_image(self, text, n, model="dall-e-3", size=256):
        images = []
        c = 0
        while c < self.max_tries:
            try :
                image_resp = self.client.images.generate(model=model, prompt=text, n=n, size=f"{size}x{size}", quality="standard")
                for d in image_resp['data']:
                    image_url = d['url']
                    images.append(read_image(image_url))
                break
            except Exception:
                error = sys.exc_info()[0]
                if error == BadRequestError:
                    self.logger.error(f"BadRequestError\nQuery:\n\n{text}\n\n")
                    self.logger.error(sys.exc_info())
                    break
                else:
                    self.logger.error('Error:', sys.exc_info())
                    if error in RETRY_ERRORS:
                        self.logger.error(f"Retrying after {self.backoff_seconds} seconds")
                        time.sleep(self.backoff_seconds)
                    else:
                        self.logger.error(f"Retrying... ({c+1}/{self.max_tries})")

                    c+=1

        return images

    def _complete_chat(self, messages, model='gpt-4o-2024-08-06', 
                       max_tokens=256, response_format=None, 
                       top_p = 1.0, temperature=1.0, n=1, stop = '\n\n\n', 
                       frequency_penalty=None, presence_penalty=None):
        """ 
        Helper function that calls the OpenAI chat completion API with exponential backoff support.
        Args:
            messages (list): A list of message dictionaries representing the conversation history.
            model (str, optional): The model to use for generating the completion. Defaults to 'gpt-3.5-turbo'.
            max_tokens (int, optional): Maximum number of tokens to generate. Defaults to 256.
            response_format (str, optional): Specifies the output format. If it matches a JSON schema, an alternative endpoint is used.
            top_p (float, optional): Nucleus sampling probability. Defaults to 1.0.
            temperature (float, optional): Controls randomness in generation. Defaults to 1.0.
            n (int, optional): Number of completion variants to generate. Defaults to 1.
            stop (str, optional): A string or list of strings that indicates where to stop generation. Defaults to '\\n\\n\\n'.
            frequency_penalty (float, optional): Penalty for token frequency to reduce repetition.
            presence_penalty (float, optional): Penalty for token presence to encourage topic diversity.
        Returns:
            dict: The response from the OpenAI chat completion API if successful; otherwise, returns None after exhausting retries.
        Behavior:
            The function attempts to call the OpenAI API using the provided parameters. It utilizes an exponential
            backoff strategy to handle transient errors such as RateLimitError and APIConnectionError. For each failure,
            it waits for a predefined backoff time before retrying, up to a maximum number of attempts specified by self.max_tries.
            If a BadRequestError occurs, the function prints error details along with the problematic message and ceases further retries.
        """
        response = None
        c = 0
        
        if is_json_schema(response_format):
            completions_fn = self.client.beta.chat.completions.parse
        else:
            completions_fn = self.client.chat.completions.create
                    
        while c < self.max_tries:
            try:
                response = completions_fn(
                    messages=messages, model=model, max_tokens=max_tokens, response_format=response_format,
                    temperature=temperature, top_p=float(top_p), n=n, stop=stop,
                    frequency_penalty=frequency_penalty, presence_penalty=presence_penalty
                )
                return response
            except Exception:
                error = sys.exc_info()[0]
                if error == BadRequestError: # should break if message was malformed.
                    self.logger.error(f"BadRequestError\nQuery:\n\n{messages}\n\n")
                    self.logger.error(sys.exc_info())
                    break
                elif error in (APIConnectionError, RateLimitError):
                    self.logger.error(f"Error: {error}")
                    self.logger.error(f"Retrying after {self.backoff_seconds} seconds ({c+1}/{self.max_tries})")
                    time.sleep(self.backoff_seconds)
                    c+=1

        return response
    
    def build_messages(
        self, 
        sys_prompt: str = None, 
        usr_prompt: str = None, 
        examples: Optional[List[Dict]] = None,
        image_input: Union[str, Image.Image, List[str | Image.Image]] = None,
        image_detail: str | List[str] = 'auto',
    ) -> List[Dict[str, str]]:
        ''' Prepare messages for chat_completions call '''
        messages = []
        if sys_prompt is not None:
            messages.append({"role": "system", "content": sys_prompt})
        user_message = self._build_user_message(usr_prompt, image_input, image_detail)
        example_messages = []
        if examples is not None:
            example_messages = self._build_example_messages(examples)
        messages = messages + example_messages + user_message
        return messages

    def _build_user_message(
        self, 
        usr_prompt: str, 
        image_input: Union[str, Image.Image, List[str | Image.Image]], 
        image_detail: str | List[str]
    ) -> List[Dict[str, str]]:
        messages = []
        if image_input is not None:
            if not isinstance(image_input, list):
                image_input = [image_input]

            if not isinstance(image_detail, list):
                image_detail = [image_detail] * len(image_input)
            
            assert len(image_input) == len(image_detail), "Length of image input and image detail should be the same."
            
            visual_content = []
            for idx,im in enumerate(image_input):
                visual_content.append({
                    "type": "image_url",
                    "image_url": {
                        "url": prepare_image_payload(im),
                        "detail": image_detail[idx],
                    }
                })
            if visual_content:
                messages += [{"role": "user", "content": visual_content}]
        if usr_prompt is None:
            usr_prompt = ""
        messages += [{"role": "user", "content": usr_prompt}]
        return messages
    
    def _build_example_messages(
        self, 
        examples: List[Dict]
    ) -> List[Dict[str, str]]:
        ''' Prepare example messages
        Args:
            examples (List[Dict]): List of examples with role and content.
                Should start with user example and end with system example.
        Returns:
            List[Dict]: List of messages with role and content.
        '''
        example_messages = []
        valid_example_roles = ['user', 'system']
        valid_user_keys = ['role', 'content', 'image', 'detail']

        assert len(examples) % 2 == 0, "Examples should be in pairs of user and system response"
        for idx, example in enumerate(examples):
            assert 'role' in example, f"Role should be provided in your example: {example}"
            assert 'content' in example, f"Content should be provided in your example: {example}"

            if idx % 2 == 0:
                expected_role = 'user'
                message = self._build_user_message(example['content'], example.get('image', None), example.get('detail', 'auto'))
                for k in example.keys():
                    assert k in valid_user_keys, f"Invalid key: {k} in example {example}"
            else:
                expected_role = 'system'
                assert 'image' not in example, "Image should not be provided in system response."
                message = [{"role": "system", "content": example['content']}]

            assert example['role'] == expected_role, f"Expected role: {expected_role} but found role: {example['role']} in example {example}"
            example_messages.append(message)
        return example_messages
    
    def call_chatgpt(
        self,
        model: str,
        sys_prompt: str = None,
        usr_prompt: str = None,
        image_input: Union[str, Image.Image, List[str | Image.Image]] = None,
        image_detail: str | List[str] = 'auto',
        examples: Optional[List[Dict[str, str]]] = None,
        response_format: str | BaseModel = None,
        max_tokens=256,
        top_p=1.0,
        temperature=1.0,
    ) -> tuple[str | BaseModel, CompletionUsage]:  
        """
        Generate a response from an OpenAI Chat model with optional image input.

        Parameters:
            model (str): Model version to be used.
            sys_prompt (str, optional): System-level prompt defining assistant behavior.
            usr_prompt (str, optional): User prompt that the assistant responds to.
            image_input (str, Image.Image, or list, optional): URL, local file path, or PIL image(s) for image input.
                                                               The image(s) can be a single image or a list of images.
            image_detail (str or list, optional): Details corresponding to each image; defaults to 'auto'.
                                                  Must be a string or list of strings with the same length as image_input.
            examples (List[Dict[str, str]], optional): In-context examples, may include images.
                - role (str): Role of the example (user or system).
                - content (str): Content of the example.
                - image (str or Image.Image, optional): URL, local file path, or PIL image for image input.
                - detail (str, optional): Details corresponding to the image; defaults to 'auto'.
            response_format (str or BaseModel, optional): Desired format of the response.
            max_tokens (int, optional): Maximum tokens for the response (default is 256).
            top_p (float, optional): Nucleus sampling probability (default is 1.0).
            temperature (float, optional): Sampling temperature for randomness (default is 1.0).

        Returns:
            tuple (str or BaseModel, dict): The response from the OpenAI Chat API and usage information.
        """
        # Prepare messages for API call
        messages = self.build_messages(sys_prompt, usr_prompt, examples, image_input, image_detail)

        response_format = self.get_response_format(response_format)
        response_is_json_schema = is_json_schema(response_format)

        def parse_response(response) -> Union[str, BaseModel]:
            if response_is_json_schema:
                result: BaseModel = response.choices[0].message.parsed
            else:
                result: str = response.choices[0].message.content
            return result

        # Call OpenAI Chat API
        try:
            response = self._complete_chat(
                messages=messages,
                model=model,
                max_tokens=max_tokens,
                response_format=response_format,
                top_p=top_p,
                temperature=temperature,
                n=1
            )
            if response is None:
                return None
            
            result = parse_response(response)
            return result, response.usage

        except AttributeError as e:
            self.logger.info(f"{e}" )
            return None
    
    def parse_json_from_text(self, raw_text: str) -> dict:
        """
        Extracts and parses the first JSON block found in the given raw text.
        The JSON block can be marked by ```json or ```.
        Returns the parsed JSON data as a dictionary, or None if no JSON block is found.
        """

        # See if you can directly parse the data
        try:
            data = ast.literal_eval(raw_text)
            return data
        except Exception:
            pass

        # Try to find the start of the JSON block, considering both ```json and ``` markers
        start_markers = ["```json", "```"]
        start = -1
        for marker in start_markers:
            start = raw_text.find(marker)
            if start != -1:
                start += len(marker)
                break
        
        # If we found a start marker, then find the end of the JSON block
        if start != -1:
            end = raw_text.find("```", start)

            # Extract and strip the JSON string
            raw_text = raw_text[start:end]
        
        # Parse the JSON string into a Python dictionary
        try:
            json_data = json.loads(raw_text)
            return json_data
        except json.JSONDecodeError as e:
            self.logger.warning("Failed to decode JSON:", e)
            return None
    
    def create_chat_completions_batch(
        self,
        custom_id: str,
        model: str,
        sys_prompt: str = None,
        usr_prompt: str = None,
        examples: Optional[List[Dict[str, str]]] = None,
        image_input: Union[str, List[str], Image.Image, List[Image.Image]] = None,
        image_detail: str | list[str] = 'auto',
        response_format: str | BaseModel = None,
        max_tokens=256,
        top_p=1.0,
        temperature=1.0,
    ) -> dict:  
        """
        Generate a batch API call for OpenAI Chat completions with optional image input.
        Returns a dictionary that can be used to make a batch API call to the OpenAI Chat API.
        """
        
        # Prepare messages for API call
        messages = self.build_messages(sys_prompt, usr_prompt, examples, image_input, image_detail)
        
        batch_api = {
            "custom_id": custom_id, 
            "method": "POST", 
            "url": "/v1/chat/completions", 
            "body": {"model": model, 
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "top_p": top_p,
                    "temperature": temperature,
                    "response_format": self.get_response_format(response_format, is_batch_api=True),
                },
        }

        return batch_api
    
    def submit_tasks_in_batches(
        self,
        tasks: List[dict],
        batch_file_template: str,
        batch_info_log: str,
        batch_size: int = 1000,
        overwrite_batch_info: bool = False,
        metadata: Optional[Dict] = None
    ) -> None:
        """
        Submits tasks in batches to GPT and logs the batch info.

        Args:
            tasks (List[dict]): The tasks to be processed in batches.
            batch_file_template (str): File path template for writing each batch to disk.
            batch_info_log (str): The file path to which batch metadata is appended.
            batch_size (int): Maximum number of tasks to include in a single batch.
            overwrite_batch_info (bool): Whether to overwrite the batch info log file.
            metadata (Optional[Dict]): Additional metadata to pass along with each batch request.
        """

        if metadata is None:
            metadata = {}
        
        write_mode = "w" if overwrite_batch_info else "a"

        # Ensure the parent directory for batch file outputs exists
        Path(batch_file_template).parent.mkdir(parents=True, exist_ok=True)

        total_tasks = len(tasks)
        if total_tasks == 0:
            self.logger.warning("No tasks provided. Exiting without submitting any batches.")
            return

        if total_tasks > batch_size:
            self.logger.info(f"Splitting {total_tasks} tasks into batches of size {batch_size}.")
        
        def build_batch_file_path(file_template: str, batch_index: int) -> str:
            """
            Given an output file path template, returns a unique filename for each batch.

            Args:
                file_template (str): The template path for the batch file.
                batch_index (int): The start index of the batch (used to form a unique suffix).

            Returns:
                str: A unique file path for the current batch.
            """
            file_path = Path(file_template)
            # e.g. "data/batch_tasks.jsonl" --> "data/batch_tasks_00000000.jsonl"
            # Insert an 8-digit zero-padded index in the file stem before ".jsonl"
            new_stem = f"{file_path.stem}_{batch_index:08}"
            return str(file_path.with_name(new_stem).with_suffix(file_path.suffix))
        
        # Iterate over tasks in steps of batch_size
        for batch_start_index in tqdm(range(0, total_tasks, batch_size), desc="Submitting batches"):
            current_batch_tasks = tasks[batch_start_index : batch_start_index + batch_size]

            # Build a unique batch file path per chunk
            current_batch_file_path = build_batch_file_path(
                file_template=batch_file_template,
                batch_index=batch_start_index
            )

            # Write current batch tasks to file
            if os.path.exists(current_batch_file_path):
                self.logger.warning(f"Overwriting existing batch file: {current_batch_file_path}")
            with open(current_batch_file_path, "w", encoding="utf-8") as f:
                for task in current_batch_tasks:
                    f.write(json.dumps(task) + "\n")
            self.logger.info(f"Saved batch tasks to: {current_batch_file_path}")

            # Upload file & create GPT batch
            # TODO: rename metadata to batch_metadata
            response = self.upload_and_submit_batch(
                local_file_path=current_batch_file_path,
                # metadata=metadata
            )

            # Collect metadata about this batch
            batch_info = {
                "batch_id": response.id,
                "batch_file": current_batch_file_path,
                "batch_index": batch_start_index,
                "num_samples": len(current_batch_tasks),
                **metadata
            }

            # Log to console and to batch info file
            self.logger.info(f"Sent Batch ID: {response.id} with {len(current_batch_tasks)} tasks.")
            with open(batch_info_log, write_mode, encoding="utf-8") as f:
                f.write(json.dumps(batch_info) + "\n")

    def upload_and_submit_batch(
        self,
        local_file_path: str,
        metadata: Optional[Dict] = None
    ):
        """
        Uploads a local file to GPT and submits a batch creation request.

        Args:
            local_file_path (str): Path to the local file containing tasks in JSONL format.
            metadata (Optional[Dict]): Additional metadata for the batch.

        Returns:
            response: The response object from the batch creation request.
        """
        if metadata is None:
            metadata = {}

        # Upload file to GPT
        with open(local_file_path, "rb") as f:
            uploaded_file = self.client.files.create(file=f, purpose="batch")

        # Create the batch job
        self.logger.info(f"Scheduling batch job for input file: {local_file_path}")
        response = self.client.batches.create(
            input_file_id=uploaded_file.id,
            endpoint="/v1/chat/completions",
            completion_window="24h",
            metadata=metadata
        )

        file_size = os.path.getsize(local_file_path) / (1024 * 1024)
        self.logger.info(f"Batch creation response: {response}")
        self.logger.info(f"Created GPT batch job ID: {response.id} for input file: {local_file_path} ({file_size:.2f} MB)")

        if file_size > BATCH_FILE_LIMIT:
            self.logger.warning(f"File size exceeds {BATCH_FILE_LIMIT} MB limit: {file_size:.2f} MB")

        return response
    
    def download_batch(self, batch_id: str, output_file):
        """ Download results from a GPT batch API call to a file. 
        If batch is not completed, print the status.
        """
        self.logger.info('Retrieving batch: {}'.format(batch_id))
        response = self.client.batches.retrieve(batch_id)
        if response.status == 'completed':
            file_id = response.output_file_id
            file_response = self.client.files.content(file_id)
            with open(output_file, 'wb') as f:
                f.write(file_response.content)
            self.logger.info('Downloaded batch {} to: {}'.format(batch_id, output_file))
        else:
            self.logger.info('Response Status:', response.status)
            self.logger.info('Response:', response)
            self.logger.info('Still processing: {}'.format(batch_id))