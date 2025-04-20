## Whisper Trasncription

This module provides tools for transcribing audio files using OpenAI's [Whisper API](https://platform.openai.com/docs/guides/speech-to-text) or a [local Whisper model](https://github.com/openai/whisper). It is designed to work with the `VideoNet` repository but separates the transcription functionality for easier use and testing.

### Installation

Install the required dependencies by running pip install in the **root** of the repository:
```
pip install -e .[transcription]
```

Alternatively, you can install the dependencies directly in the `transcription` directory:
```
cd transcription
pip install -r requirements.txt
```

For whisperx and cuda 11, you might need to reinstall `ctranslate2` with version 3.x.x. See this [issue](https://github.com/SYSTRAN/faster-whisper/issues/734)
```
pip install ctranslate2==3.24.0
```

### Usage
From root, run `transcription/scripts/run_whisper.py` script to transcribe audio files.
To support distributed processing, the script accepts `--shard_index` and `--num_shards` arguments. These arguments are used to split the input data into smaller chunks for parallel processing.

Example usage with local whisper model:
```bash
python -m transcription.scripts.run_whisper \
    --mode gpu \ 
    --input_file transcription/data/oe-training-yt-crawl-video-list-04-10-2025.jsonl \
    --shard_index 0 \
    --num_shards 256 \
    --output_dir /path/to/output \
```

To use **OpenAI Whisper API**, make sure to set the `OPENAI_API_KEY` environment variable.
By default, we use the `whisper-1` model (TODO: add model params for api calls).
Then, run the script with the `--mode api` argument:
```bash
python -m transcription.scripts.run_whisper \
    --mode api \
    --input_file transcription/data/oe-training-yt-crawl-video-list-04-10-2025.jsonl \
    --shard_index 0 \
    --num_shards 256 \
    --output_dir /path/to/output \
```

#### Input Format

The input file should be a JSONL file containing video metadata:
```json
{
  "folder": "gs://your-bucket/video_folder",
  "has_both": true,
  "has_video": true, 
  "has_json": true,
  "video_path": "gs://your-bucket/video_folder/video_id.mkv",
  "json_path": "gs://your-bucket/video_folder/video_id.json",
  "id": "video_id"
}
```

#### Output Format

The output is a JSONL file where each line contains a JSON object with the transcription results and metadata
```json
{
  "id": "video_id",
  "uri": "gs://your-bucket/video_folder/video_id.mkv",
  "duration": 120.0,
  "language": "en",
  "text": "Transcribed text for entire video goes here",
  "segments": [{
    "start": 0.0,
    "end": 5.0,
    "text": "Transcribed text for this segment goes here",
    "id": 0, # segment id
  }],
  "cost": 0.36, # cost of transcription in dollars (if using OpenAI API)
}
```

If the `output_file` argument is not provided, the script will generate a default output filename based on the input file name and add the postfix `_whisper_{mode}_{shard_index}_{num_shards}.jsonl`. For example, if the input file is `video_list.jsonl`, the output file will be `video_list_whisper_api_0_256.jsonl`. This output file will be saved in the specified `output_dir` directory.


#### Command Line Arguments

| Argument | Description | Default |
|----------|-------------|---------|
| `--mode` | Transcription mode: 'api' or 'gpu' | (Required) |
| `--input_file` | Path to the input JSONL file containing video metadata | (Required) |
| `--whisper_model` | Size of whisper model (for GPU mode) | 'large' |
| `--shard_index` | Index of the shard to process | 0 |
| `--num_shards` | Total number of shards to split the input data into | 1 |
| `--output_dir` | Directory to save the transcription results | 'transcriptions' |
| `--batch_size` | Batch size for processing | 100 |
| `--output_file` | Custom output filename | (Auto-generated) |
| `--output_dir` | Directory for output files | 'transcriptions' |
| `--overwrite_output` | Overwrite existing output files | False |
| `--num_workers` | Parallel workers for API mode | 10 | 
| `--all_lang` | Process all languages (don't limit to English) | False |


### Gantry Job Submission
You can also submit GPU-enabled array jobs using [beaker-gantry](https://github.com/allenai/beaker-gantry). To set up:

1. Configure beaker secrets in your workspace to access Google Storage. 
    - Set `SERVICE_ACCOUNT` and `GOOGLE_APPLICATION_CREDENTIALS` need to be set in your beaker workspace.
    - See [beaker docs for google-cloud-storage](https://beaker-docs.apps.allenai.org/compute/data-storage.html#from-google-cloud-storage) for more details.

2. Create a beaker experiment with the following command:
```
bash transcription/scripts/beaker/run_whisper_gantry.sh
```

3. Configuration options in the script:
   - NUM_SHARDS: Total number of data partitions
   - SHARD_START/SHARD_END: Range of shards to process
   - DATA_NAME: Name to identify input data
   - FNAME: Name of input file

4. (**Recommended**) After completion, you can use the [beaker-client](https://beaker-py.readthedocs.io/en/latest/installation.html) to retrieve results:
```
pip install beaker-py # if not already installed
```

Then run:
```
python transcription/scripts/beaker/get_results.py \
    $EXP_NAME \
    --output_dir /path/to/output
```
This will download results for the experiment from each **latest finished** (whether completed/preempted) job. This ensures that you get all the available results, even if some jobs were preempted. 

- Using the beaker CLI (not recommended):
This approach, while easy to use, downloads the result in the **latest** job,  and ignores the previous job with the sam job ID. So, it will download empty files for preempted jobs since the results are not available before the job has started. 
```
beaker experiment results $EXP_NAME -o /path/to/output
```

