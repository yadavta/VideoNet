import os
import numpy as np
import tempfile
from typing import Any, Union, Dict
from pydub import AudioSegment
import whisper
import ffmpeg

from loguru import logger

from .base_verbalizer import Verbalizer


def parse_segments(segments: list[dict]):
    return [{k:v for k,v in seg.items() if k in ['id', 'start', 'end', 'text']} for seg in segments]

def get_duration(video_input: str) -> float:
    """
    Get the duration of the video in seconds.
    """
    probe = ffmpeg.probe(video_input)
    duration = float(probe['format']['duration'])
    return duration

class WhisperAPI(Verbalizer):

    def __init__(self, api_key=None, segment_length=30* 1000):
        from src.utils.openai_api import OpenaiAPI
        self.openai_api = OpenaiAPI(api_key)
        self.segment_length = segment_length

    def __call__(self, video_input: str) -> Dict:
        """
        Runs Whisper API to specified video path. 
        Split audio into `segment_length` segments (length 1000 = 1 sec) to deal with file limits.
        """

        audio = AudioSegment.from_file(video_input)
        duration = audio.duration_seconds
        transcriptions = []
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_file:
            for i in range(0,len(audio),self.segment_length):
                start = i
                end = i+self.segment_length 
                sound_export = audio[start:end]
                sound_export.export(temp_file.name, format="wav")
                
                with open(temp_file.name, "rb") as audio_input:
                    try:
                        transcription = self.openai_api.run_asr(audio_input)
                    except Exception as e:
                        logger.error(e)
                        continue
                transcription['segments'] = parse_segments(transcription['segments'])
                transcription['start'] = start
                transcriptions.append(transcription)
        
        # Gather segment results
        text = ' '.join([t['text'] for t in transcriptions])
        language = transcriptions[0]['language']
        segments = []
        cost = 0
        id = 0
        for t in transcriptions:
            start_time = t['start'] / 1000
            for segment in t['segments']:
                segment['id'] = id
                segment['start'] += start_time
                segment['end'] += start_time
                id+=1
            segments += t['segments']
            cost += t['cost']
        
        result = {
            'text': text,
            'duration': duration,
            'segments': segments,
            'language': language,
            'cost': cost
        }
        
        return result
 
class WhisperGPU(Verbalizer):

    def __init__(self, whisper_model, device='cuda', download_root="$HOME/.cache/whisper"):
        self.model = whisper.load_model(whisper_model, device=device, download_root=download_root)
        self.device = device
    
    def __call__(self, video_input: str) -> Dict:
        """
        Use the local whisper model to transcribe video.
        """

        audio_input: np.ndarray = self.load_audio(video_input)
        result = self.model.transcribe(audio_input)
        segments = parse_segments(result['segments'])

        # detect the spoken language
        language = self.detect_language(audio_input)

        duration = get_duration(video_input)

        return {
            'text': result['text'],
            'duration': duration,
            'segments': segments,
            'language': language
        }
    
    def load_audio(self, video_input: str):
        return whisper.load_audio(video_input)
    
    def detect_language(self, audio_input: np.ndarray):
        audio = whisper.pad_or_trim(audio_input)
        mel = whisper.log_mel_spectrogram(audio, self.model.dims.n_mels).to(self.device)
        _, probs = self.model.detect_language(mel)
        language = max(probs, key=probs.get)

        return language

    
    