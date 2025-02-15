from pathlib import Path
from subprocess import CompletedProcess, CalledProcessError
import subprocess, re, json, cv2, numpy as np

from src.globals import ORIGINALS_DIR, CLIPS_DIR

def cut_video(video_name: str, cuts: list[tuple[float|int, float|int]], overwrite=False) -> None:
    """
    Given a video located at `data/originals/{video_name}.mp4`, creates clips of video as specified by `cuts` and
    saves them in `data/clips/{video_name}_clip_i.mp4` where i is the index of the clip's start/stop time pair in `cuts` (1-indexed).

    Start and stop times should be provided in seconds.
    
    Raises a `FileExistsError` if a file already exists where an output clip is to be saved and `overwrite` is set to False (default).
    """
    # Determine video path and its validity
    video_path: Path = ORIGINALS_DIR / f'{video_name}.mp4'
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
        clip_path = CLIPS_DIR / f'{video_name}_clip_{i+1}.mp4'
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

def parse_segments(text: str) -> list[tuple[int, int]]:
    """
    Given a string in a specific format that contains a list of video segments, 
    returns a list of those segments' start and end times in seconds. 
    The start/end times must be denoted as MM:SS in the provided string.

    See SAMPLE INPUTS section of source code to see the expected format of `text`.
    """
    """
    SAMPLE INPUTS: (each sample is enclosed within single quotes and appears on its own line)

    '00:00-00:02\n00:06-00:08\n00:14-00:17\n00:21-00:24\n00:24-00:27'

    '00:00-00:07\n00:08-00:10'

    '00:00-00:02\n00:03-00:05\n00:06-00:08\n00:10-00:12\n00:13-00:15\n00:16-00:18\n00:20-00:22\n00:23-00:25'

    '- 00:03-00:05\n- 00:06-00:07\n- 00:08-00:10\n- 00:11-00:12\n- 00:13-00:15\n- 00:16-00:17'

    '- 00:00-00:00\n- 00:09-00:10\n- 00:12-00:13\n- 00:16-00:18\n- 00:21-00:24\n- 00:29-00:32\n- 00:32-00:33\n- 00:34-00:35\n- 00:36-00:37\n- 00:56-00:57'
    """
    pattern = r'(?:- )?(\d\d):(\d\d)-(\d\d):(\d\d)'
    matches = re.finditer(pattern, text)

    segments = []
    for m in matches:
        smin, ssec, emin, esec = map(int, m.groups())
        start, end = 60 * smin + ssec, 60 * emin + esec
        segments.append((start, end))

    return segments

def sanitize_segments(segments: list[tuple[int, int]]) -> None:
    """
    Ensures that segments are sensible by enforcing following constraints:
    (1) segment end time must come after segment start time (cannot be equal)
    (2) segments do not overlap (this is checked pair-wise; if overlap, former segment is kept and latter is discarded)
    """
    sanitized = []
    i, n = 0, len(segments)
    while i < n:
        if segments[i][0] >= segments[i][1]:
            i += 1
        if i + 1 < n and segments[i][1] > segments[i + 1][0]:
            sanitized.append(segments[i])
            i += 2
        else:
            sanitized.append(segments[i])
            i += 1

    return sanitized

def verify_directory(dir: str | Path) -> str | None:
    """
    Checks whether `dir` is a string or Path pointing to a directory.

    If it is, returns nothing (None). If it isn't, returns a string explaining what's wrong.
    """
    if not isinstance(dir, str) and not isinstance(dir, Path):
        return f'The provided directory {dir} must be a string or a Path object.'
    if not Path(dir).is_dir():
        return f'The provided directory {dir} is not a directory.'

def extract_bboxs_qwen(s: str) -> list[tuple[str, list[int]]] | None:
    """
    Given a Python string containing a list of bounding boxes in JSON format as returned by Qwen2.5-VL, 
    returns a list of the bounding boxes with their labels. If Qwen found no bounding boxes, returns None.

    Assumes prompt given to Qwen ended with 'Report the bbox coordinates in JSON format.' or a similar instruction.
    It is critical that Qwen is instructed to return 'bbox coordinates in JSON format' -- the rest of the prompt can be tinkered with.

    EXAMPLE INPUTS:

    '```json\n[\n\t{"bbox_2d": [1356, 714, 1559, 1198], "label": "children skipping rope"},\n\t{"bbox_2d": [1059, 726, 1191, 966], "label": "children skipping rope"}\n]\n```'
    """
    if len(s) < 7 or s[:7] != '```json' or s[-3:] != '```':
        return None
    s = s[7:-3]
    s.replace('\n', '').replace('\t', '').strip()
    data = json.loads(s)
    bboxs: list[tuple[str, list[int]]] = [(item['label'], item['bbox_2d']) for item in data]
    return bboxs

def draw_bboxs(image: str, out: str, bboxs: list[tuple[str, list[int] | tuple[int]]],
               color: cv2.typing.Scalar = (0, 255, 0), thickness: int = 5, font: int = cv2.FONT_HERSHEY_COMPLEX) -> None:
    """
    Given an `image` and a list of bounding boxes with labels, saves a copy of the image with the bounding boxes drawn on it
    at `out`. Both `image` and `out` should be strings representing local file paths.
    """
    image, out = Path(image), Path(out)
    if not image.exists() or not image.is_file():
        raise Exception(f'Could not find a file at specified `image` location: {image}')
    
    image = cv2.imread(image)
    for label, bbox in bboxs:
        x1, y1, x2, y2 = bbox
        cv2.rectangle(image, (x1,y1), (x2,y2), color, thickness)
        font = cv2.FONT_HERSHEY_DUPLEX
        cv2.putText(image, label, (x1, y1-10), font, 0.5, color, 2)
    
    cv2.imwrite(out, image)
    print(f"Saved image with bounding box overlay to {out}")