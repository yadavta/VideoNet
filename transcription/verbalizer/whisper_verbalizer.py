import os
import numpy as np
import tempfile
from typing import Any, Union, Dict
from pydub import AudioSegment
import whisper
import ffmpeg

from loguru import logger

from .base_verbalizer import Verbalizer

try:
    import whisperx
except ImportError:
    logger.warning("WhisperX not installed. Please run `pip install whisperx` if you want to use WhisperX transcriber.")

WHISPER_CACHE_DIR = os.path.join(os.path.expanduser("~"), ".cache", "whisper")

def parse_segments(segments: list[dict]):
    return [{k:v for k,v in seg.items() if k in ['id', 'start', 'end', 'text']} for seg in segments]

def get_duration(video_input: str) -> float:
    """
    Get the duration of the video in seconds.
    """
    probe = ffmpeg.probe(video_input)
    duration = float(probe['format']['duration'])
    return duration

class WhisperTranscriber(Verbalizer):
    """ Abstract class for Whisper transcribers. """
    # Registry to store available WhisperTranscriber classes
    _registry = {}
    
    @classmethod
    def _register_model(cls, name: str):
        """
        Decorator to register a WhisperTranscriber subclass in the registry.
        
        Args:
            name: String identifier for the transcriber
        """
        def decorator(subclass):
            cls._registry[name] = subclass
            return subclass
        return decorator
    
    @classmethod
    def load_model(cls, name: str, **kwargs):
        """
        Factory method to get a WhisperTranscriber instance by name.
        
        Args:
            name: String identifier for the transcriber ('whisper-api', 'whisper-gpu', 'whisperx')
            **kwargs: Arguments to pass to the transcriber constructor
            
        Returns:
            An instance of the requested WhisperTranscriber subclass
            
        Raises:
            ValueError: If the requested transcriber is not registered
        """
        if name not in cls._registry:
            raise ValueError(
                f"Transcriber '{name}' not found. Available transcribers: {list(cls._registry.keys())}"
            )
        
        return cls._registry[name](**kwargs)
    
    @classmethod
    def get_available_models(cls):
        """
        Get a list of available models.
        """
        return sorted(list(cls._registry.keys()))
    
    def __call__(self, video_path: str) -> Dict:
        pass

@WhisperTranscriber._register_model('whisper-api')
class WhisperAPI(WhisperTranscriber):

    def __init__(self, api_key=None, segment_length=30* 1000, api_model='whisper-1', **kwargs):
        from src.utils.openai_api import OpenaiAPI
        print(f"Using OpenAI Whisper API model {api_model} with segment length {segment_length}")
        self.openai_api = OpenaiAPI(api_key)
        self.segment_length = segment_length
        self.whisper_model = api_model

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
                        transcription = self.openai_api.run_asr(audio_input, model=self.whisper_model)
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
 
@WhisperTranscriber._register_model('whisper-gpu')
class WhisperGPU(WhisperTranscriber):

    def __init__(self, whisper_model, device='cuda', download_root=WHISPER_CACHE_DIR, **kwargs):
        self.model = whisper.load_model(whisper_model, device=device, download_root=download_root)
        print(f"Loaded Whisper model {whisper_model} from {download_root} on {device}")
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

@WhisperTranscriber._register_model('whisperx')
class WhisperX(WhisperTranscriber):
    def __init__(self, whisper_model, device='cuda', download_root=WHISPER_CACHE_DIR, **kwargs):
        import torch
        torch.backends.cuda.matmul.allow_tf32 = False
        torch.backends.cudnn.allow_tf32 = False
        self.model = whisperx.load_model(whisper_model, device=device, download_root=download_root)
        print(f"Loaded WhisperX model {whisper_model} from {download_root} on {device}")
        self.device = device
    
    def __call__(self, video_input: str, batch_size=128) -> Dict:
        """
        Use the local whisper model to transcribe video.
        """

        audio_input: np.ndarray = self.load_audio(video_input)
        result = self.model.transcribe(audio_input, batch_size=batch_size)
        segments = parse_segments(result['segments'])
        for idx, seg in enumerate(segments):
            seg['id'] = idx
        language = result['language']

        text = ' '.join([s['text'] for s in segments])

        duration = get_duration(video_input)

        return {
            'text': text,
            'duration': duration,
            'segments': segments,
            'language': language
        }
    
    def load_audio(self, video_input: str):
        return whisperx.load_audio(video_input)
    
    def detect_language(self, audio_input: np.ndarray):
        return self.model.model.detect_language(audio_input)[0]
    
    
    