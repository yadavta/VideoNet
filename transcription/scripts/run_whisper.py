""" Basic script to run whisper transcription jobs on local or videos in gcs"""
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

from transcription.verbalizer.whisper_verbalizer import WhisperTranscriber
from transcription.pipeline import transcribe_pipeline

# Configure loguru logger                                                 
warnings.filterwarnings('ignore', module='pydantic')
warnings.filterwarnings('ignore', module='google')
logger.remove()  # Remove default handler                                 
logger.add(sys.stdout, level="INFO")

if __name__ == '__main__':

    '''
    python -m transcription.scripts.run_whisper \
        zkNgfVCzhYk.webm \
        --mode whisperx \
        --whisper_model large-v3-turbo
    '''
    parser = argparse.ArgumentParser("Whisper API or GPU jobs for videos in gcs.")
    parser.add_argument('video', type=str, help='local or gcs uri of video to transcribe')
    parser.add_argument('--mode', choices=['whisper-api', 'whisper-gpu', 'whisperx'], required=True)
    parser.add_argument('--whisper_model', type=str, default='large-v3-turbo', help='size for gpu model')
    parser.add_argument('--api_model', type=str, default='whisper-1', help='model to use for API jobs')
    parser.add_argument('--segment_length', default=30*1000, type=int, help='length to segment audio input in miliseconds for API jobs')
    parser.add_argument('--output', default='transcription.json', help='output file to save transcriptions')

    args = parser.parse_args()

    whisper_kwargs = {}
    if os.environ.get("WHISPER_CACHE_DIR", None) is not None:
        whisper_kwargs = {'download_root': os.environ["WHISPER_CACHE_DIR"]}
 
    # Load the whisper model
    model_args = {
        'whisper_model': args.whisper_model,
        'api_model': args.api_model,
        'segment_length': args.segment_length,
        **whisper_kwargs
    }
    whisper_model = WhisperTranscriber.load_model(args.mode, **model_args)
    result = transcribe_pipeline(args.video, whisper_verbalizer=whisper_model, verbose=True)
    logger.info(f"Transcription result: {result}")
    if result is not None:
        # Save the result to the output file
        with open(args.output, 'w') as f:
            json.dump(result, f, ensure_ascii=False)
        logger.success(f"Transcription completed for {args.video} at {args.output}")
    else:
        logger.error(f"Transcription failed for {args.video}")