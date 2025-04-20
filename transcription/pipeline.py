"""Unified transcription pipeline for processing video files (local or GCS)"""
import time
import tempfile
import json

from loguru import logger

from src.utils.gcs import download_blob_as_bytes, parse_gcs_url, get_file_extension
from transcription.verbalizer.whisper_verbalizer import WhisperTranscriber

def transcribe_pipeline(
    video_path,
    whisper_verbalizer: WhisperTranscriber,
    verbose=False,
):
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

    load_time = time.time()

    if video_path.startswith('gs://'):
        
        # Download the video file from GCS
        try:
            bucket_name, blob_name = parse_gcs_url(video_path)
            content = download_blob_as_bytes(bucket_name, blob_name)
        except Exception as e:
            logger.error(f"Failed to download video {video_path}: {e}")
            return None
        if verbose:
            logger.info('Time took to load video: {} seconds'.format(time.time() - load_time))

        # Store the downloaded audio file in a temporary local file
        # as input to the Whisper model
        suffix = get_file_extension(video_path)
        with tempfile.NamedTemporaryFile(delete=True, suffix=suffix) as temp:
            temp.write(content)
            temp.flush()
            try:
                transcription = whisper_verbalizer(temp.name)
            except Exception as e:
                logger.error(f'Error in verbalizing {video_path}: {e}')
                return None
    else:
        try:
            transcription = whisper_verbalizer(video_path)
        except Exception as e:
            logger.error(f'Error in verbalizing {video_path}: {e}')
            return None
      
    if verbose:
        logger.info('Verbalization took: {} seconds'.format(time.time() - load_time))
    
    return transcription