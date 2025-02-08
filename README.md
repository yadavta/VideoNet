# VideoNet

The 'ImageNet moment' for action recognition in video.

## Installation

### Dependencies

This tutorial assumes that your GPU supports FlashAttention.

We also assume that your GPU can fit a 7B model with `bf16` parameters. If this is not the case, please modify the `Qwen25VL` initialization in `src/models.py` to use the 3B version.

Clone this repository and navigate to it.
```bash
git clone git@github.com:yadavta/VideoNet.git
cd VideoNet
```

Create a new Conda environment. Feel free to change its name to something other than `vidnet`.
```bash
conda create -n vidnet python=3.10
conda activate vidnet
```

Install Qwen2.5-VL.
```bash
pip install git+https://github.com/huggingface/transformers accelerate
pip install qwen-vl-utils[decord]
```

Install CUDA.
```bash
conda install cuda -c nvidia
```

Install FlashAttention-2.
```bash
pip install flash-attn --no-build-isolation
```

Install Google's (older) SDK for Gemini. Note that this is *not* the new `google-genai` package.
```bash
pip install google-generativeai
```

Fix a quick [bug](https://github.com/grpc/grpc/issues/38490#issuecomment-2604775087).
```bash
pip uninstall grpcio grpcio-status
pip install grpcio==1.67.1 grpcio-status==1.67.1
```

Churn through some miscellaneous installations.
```bash
pip install torchvision
conda install conda-forge::ffmpeg
```

Last but not least, configure this codebase as a Python package so the imports in our source code work properly.
```bash
pip install -e .
```

### Environment Variables

Please update the following variables in `src/globals.py` to better reflect your machine/environment:

- `MODELS_DIR`: this is where Qwen-2.5VL will be downloaded to
- `CREDENTIALS_DIR`: this is where you will store your Gemini API key

Additionally, this repository should have shipped with two empty directories: `data/originals/` and `data/clips/`. Please ensure that they exist; if they do not, please create them.

### Gemini API

[Get a key](https://aistudio.google.com/apikey) for the Gemini API and store it in `CREDENTIALS_DIR/google_genai.txt`. This file should contain exactly your API key and nothing else. 

Please be wary of Gemini's free usage limits. Also note their [terms of service](https://ai.google.dev/gemini-api/terms).

## Usage

All the code below assumes that it is being executed from this repository's root (i.e., where this README is located).

### Localization Pipeline (Two-Pass)

This pipeline will find all skateboard tricks performed in the provided `VIDEO` and extract short clips of them. Under the hood, it uses Gemini to get an initial list of segments where tricks occur, and then uses Qwen to filter out false positives (i.e., segments that Gemini identified as skateboard tricks but in reality include no such tricks).

To localize a video, run the following in your shell.
```bash
python src/pipeline.py VIDEO --overwrite
```

Ensure that `VIDEO` is the name of the MP4 file in your `ORIGINALS_DIR` (see `src/globals.py`) that you wish to localize. For example, if the repository's root directory is denoted by `.`, then I would localize the video located at `./data/originals/laser_flip.mp4` by replacing `VIDEO` with `laser_flip` in the command above.

### Localization with Qwen

Our experiments indicate that Gemini far surpasses Qwen at localizing segments within a video that contain actions (generic) from a specific domain (e.g., "skateboarding tricks"). However, we make it possible to give this task to Qwen using the code below.

```python
from src.models import Qwen25VL
qwen = Qwen25VL()

prompt = "You have been given a video that shows multiple skateboarding tricks. Your job is to help segment the different tricks. Provide a list of the start and end times of each trick that is performed. You do not need to name the trick, focus on providing the start and stop times."

vid_path = '' # replace this with an absolute path to the video you wish to localize
output = qwen.video_inference(prompt, vid_path, is_path=True)[0]
print(output)
```

It may be helpful to tinker with the `prompt` above. For instance, one could use the prompt we give to Gemini (`GEMINI_TEMPORAL_LOCALIZATION`) by importing it from `src.prompts`.