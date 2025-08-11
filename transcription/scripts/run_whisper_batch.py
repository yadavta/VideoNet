import os
import argparse
import time
from tqdm import tqdm
from functools import partial
from pathlib import Path
import tempfile
import json
import sys

from loguru import logger
import warnings

from src.utils.gcs import download_blob_as_bytes, parse_gcs_url
from src.utils.async_caller import FutureThreadCaller
from transcription.verbalizer.whisper_verbalizer import WhisperTranscriber
from transcription.pipeline import transcribe_pipeline

# Configure loguru logger                                                 
warnings.filterwarnings('ignore', module='pydantic')
warnings.filterwarnings('ignore', module='google')
logger.remove()  # Remove default handler                                 
logger.add(sys.stdout, level="INFO")

def transcribe_data(
    datum,
    whisper_verbalizer: WhisperTranscriber,
    verbose=False,
    check_if_en=True
) -> dict:
    """
    Loads a video from gcs, extracts key frames, and generates captions for key frames.
    This function processes a single video entry, handling both GCS and local files.
    It extracts audio from the video and transcribes it using the provided Whisper model.

    Args:
        datum (dict): A dictionary containing the video path and other metadata.
        whipser_verbalizer (object): An instance of the Whisper model to use for transcription.
        verbose (bool): If True, prints additional information during processing.
        check_if_en (bool): If True, checks if the video is in English before processing (expects GCS URIs).
                            Else, processes all languages.
    Returns:
        dict: A dictionary containing the following keys:
            - 'uri': The URI of the video.
            - 'id': The ID of the video.
            - 'text': The transcribed text.
            - 'duration': The duration of the video in seconds.
            - 'segments': A list of dictionaries containing the start time, end time, and text for each segment.
            - 'language': The language of the transcription.
            - (Optional) 'cost': The cost of the transcription (for api models).
        If error occurs, returns None.
    """

    uri = datum['video_path']
    if uri is None:
        logger.error(f"URI not found for {datum}. Skipping...")
        return None
    result = {
        "uri": uri, 
        "id": datum.get('id', Path(uri).stem),
    }

    if check_if_en:
        assert uri.startswith('gs://'), 'Language check is only supported for gcs uris'

        json_path = datum['json_path']
        if json_path is None:
            logger.error(f"Metadata not found for {uri}. Skipping...")
            return None
        bucket_json_name, blob_json_name = parse_gcs_url(json_path)
        content = download_blob_as_bytes(bucket_json_name, blob_json_name)
        if content is None:
            logger.error(f"Failed to download metadata for {uri} from {json_path}.")
            return None

        metadata = json.loads(content)
        if "language" in metadata and metadata["language"] != "en":
            if verbose:
                logger.info(f"Skipping {uri} as it is not English.")
            return None
    
    transcription = transcribe_pipeline(uri, whisper_verbalizer=whisper_verbalizer, verbose=verbose)
    if transcription is None:
        logger.error(f"Failed to transcribe {uri}.")
        return None
    
    result.update(transcription)
 
    return result

def load_jsonl(file_path):
    """Load a jsonl file and return a list of dictionaries."""
    with open(file_path, 'r') as f:
        data = [json.loads(line) for line in f]
    return data

def load_parquet(file_path):
    """Load a parquet file and return a list of dictionaries."""
    import pandas as pd
    df = pd.read_parquet(file_path)
    data = df.to_dict(orient='records')
    return data

def save_batch(results: list[dict], output_file: str):
    """Save a batch of results to a jsonl file."""
    with open(output_file, 'a') as f:
        for result in results:
            f.write(json.dumps(result, ensure_ascii=False)+'\n')

if __name__ == '__main__':

    '''
    python -m transcription.scripts.run_whisper_batch \
        --mode whisper-api \
        --input_file transcription/data/oe-training-yt-crawl-video-list-04-10-2025.jsonl \
        --shard_index 0 \
        --num_shards 256
    
    python -m transcription.scripts.run_whisper_batch \
        --mode whisper-gpu \
        --input_file transcription/data/oe-training-yt-crawl-video-list-04-10-2025.jsonl \
        --whisper_model large-v3-turbo \
        --shard_index 1 \
        --num_shards 256
    '''
    parser = argparse.ArgumentParser("Whisper API or GPU jobs for videos in gcs.")
    parser.add_argument('--mode', choices=['whisper-api', 'whisper-gpu', 'whisperx'], required=True)
    parser.add_argument('--input_file', required=True, type=str, help='input jsonl file with gcs uris')
    parser.add_argument('--whisper_model', type=str, default='large-v3-turbo', help='size for gpu model')
    parser.add_argument('--segment_length', default=30*1000, type=int, help='length to segment audio input in miliseconds for API jobs')
    parser.add_argument('--all_lang', action='store_true', help='transcribe all languages (default: skip non-english)')

    # Sharding arguments
    parser.add_argument('--shard_index', type=int, default=0)
    parser.add_argument('--num_shards', type=int, default=100)
    parser.add_argument('--batch_size', type=int, default=100, help='batch size to call API jobs and/or save results')

    # Output arguments
    parser.add_argument('--overwrite_output', action='store_true', help='overwrite output file if it exists')
    parser.add_argument('--output_file', default=None, help='name of output file to save transcriptions')
    parser.add_argument('--output_dir', default="transcription/output", help='output dir to write the transcriptions onto')

    # API specific arguments
    parser.add_argument('--api_model', type=str, default='whisper-1', help='model to use for API jobs')
    parser.add_argument('--num_workers', type=int, default=10, help='number of workers to use for api jobs')

    args = parser.parse_args()

    assert args.shard_index < args.num_shards

    if args.output_file is None:
        ext = Path(args.input_file).suffix

        # set output file name based on input file name.
        # output will always be in jsonl format
        args.output_file = args.input_file.replace(
            ext, 
            '_whisper_{}_{:04d}_{:04d}.jsonl'.format(args.mode, args.shard_index, args.num_shards)
        )
        assert args.output_file != args.input_file, "Output file name cannot be the same as input file name"
    os.makedirs(args.output_dir, exist_ok=True)
    args.output_file = os.path.join(args.output_dir, args.output_file)

    whisper_kwargs = {}
    if os.environ.get("WHISPER_CACHE_DIR", None) is not None:
        whisper_kwargs = {'download_root': os.environ["WHISPER_CACHE_DIR"]}

    model_args = {
        'whisper_model': args.whisper_model,
        'api_model': args.api_model,
        'segment_length': args.segment_length,
        **whisper_kwargs
    }
 
    # Load the whisper model
    whisper_model = WhisperTranscriber.load_model(args.mode, **model_args)
    transcribe = partial(transcribe_data, 
                         whisper_verbalizer=whisper_model,
                         check_if_en=not args.all_lang,
                         )
 
    # Shard data
    if args.input_file.endswith('.jsonl'):
        data = load_jsonl(args.input_file)
    elif args.input_file.endswith('.parquet'):
        data = load_parquet(args.input_file)
    else:
        raise ValueError(f"Unsupported file format: {args.input_file}")
    logger.info(f"Found {len(data)} total URIs in {args.input_file}")
    data = data[args.shard_index::args.num_shards]
    logger.info(f"Loaded {len(data)} URIs from shard {args.shard_index} of {args.num_shards} shards")

    if args.overwrite_output:
        logger.info(f"Overwriting {args.output_file}...")
        with open(args.output_file, 'w') as f:
            pass

    # Load and skip processed uris
    uris_to_skip = set()
    if os.path.isfile(args.output_file) and not args.overwrite_output:
        with open(args.output_file) as f:
            for line in f:
                line = json.loads(line)
                uris_to_skip.add(line['uri'])
    input_data = [datum for datum in data if datum['video_path'] not in uris_to_skip]
    logger.info(f"Skipping {len(uris_to_skip)} already processed URIs")
    logger.info(f"Processing {len(input_data)} new URIs")
    logger.info(f"Will save transcriptions to {args.output_file}...")

    res = transcribe(input_data[0], verbose=True)
    logger.info(f"Example Transcription result: {res}")

    # async callers automatically handles batching
    if args.mode == 'whisper-api':
        FutureThreadCaller.batch_process_save(
            data,
            transcribe,
            args.output_file,
            batch_size=args.batch_size,
            max_workers=args.num_workers
        )
 
    # Transcribe every batch of videos with the GPU model
    else:
        for idx in tqdm(range(0, len(input_data), args.batch_size)):
            batch = input_data[idx:idx+args.batch_size]
            results = []
            for datum in tqdm(batch):
                result = transcribe(datum)
                if result is not None:
                    results.append(result)
            save_batch(results, args.output_file)
            logger.info(f"Saved {len(results)} transcriptions to {args.output_file}")
    
    logger.success(f"Transcription completed for {len(input_data)} URIs")
