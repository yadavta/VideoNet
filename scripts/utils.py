from pathlib import Path
from subprocess import CompletedProcess, CalledProcessError
import subprocess

def cut_video(video_name: str, dir: str, cuts: list[tuple[float|int, float|int]], overwrite=False) -> None:
    """
    Given a video located at `dir/video_name.mp4`, creates clips of video as specified by `cuts` and
    saves them in `dir/video_name_i.mp4` where i is the index of the clip's start/stop time pair in `cuts` (1-indexed). 

    Start and stop times should be provided in seconds.
    
    Raises a `FileExistsError` if a file already exists where an output clip is to be saved and `overwrite` is set to False (default).
    """
    # Determine video path and its validity
    if verify_directory(dir):
        raise Exception('`dir` must be a directory, provided as a string or a Path object.')
    video_path: Path = Path(dir) / f'{video_name}.mp4'
    if not video_path.exists():
        raise FileNotFoundError(f'Instructed to create cuts of MP4 video at following location, but no such video exists: {str(video_path)}')
    
    # Get length of video
    # https://trac.ffmpeg.org/wiki/FFprobeTips#Formatcontainerduration
    ffmpeg_length_command = ['ffprobe', '-v', 'quiet', '-show_entries', 'format=duration', '-print_format', 'default=noprint_wrappers=1:nokey=1', str(video_path)]
    length_result: CompletedProcess = subprocess.run(ffmpeg_length_command, capture_output=True, text=True)
    if length_result.returncode:
        print(f"Encountered the following error while trying to get length of video at {video_path} using FFprobe: {length_result.stderr}")
        length_result.check_returncode()
    video_duration = float(length_result.stdout)

    # For each desired clip...
    for i in range(len(cuts)):
        # Find where to save the clip to
        clip_path = Path(dir) / f'{video_name}_{i+1}.mp4'
        if clip_path.exists() and not overwrite:
            raise FileExistsError(f'Attempted to save a clip at the following location, but a file already exists there: {str(clip_path)}')

        # Validate start and stop times
        start, stop = cuts[i]
        if stop <= start:
            raise ValueError('Stop time must come after the start time.')
        if stop > video_duration:
            raise ValueError('Stop time must come before the end of the video.')
        
        # Extract clip
        ffmpeg_clip_extraction_commad = ['ffmpeg',  '-i', str(video_path), '-ss', str(start), '-to', str(stop), str(clip_path)] # note: far more efficient ffmpeg commands for cutting videos exist, but they are far less accurate
        if overwrite: ffmpeg_clip_extraction_commad.insert(-1, '-y')
        clip_extraction_result: CompletedProcess = subprocess.run(ffmpeg_clip_extraction_commad, capture_output=True, text=True)
        if clip_extraction_result.returncode:
            print(f'Encountered an error while trying to clip segment from {start} seconds to {stop} seconds of video at {video_path}')
            clip_extraction_result.check_returncode()

def verify_directory(dir: str | Path) -> str | None:
    if not isinstance(dir, str) and not isinstance(dir, Path):
        return 'The specified directory `dir` must be a string or a Path object.'
    if not Path(dir).is_dir():
        return 'The provided `dir` is not a directory.'