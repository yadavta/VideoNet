import os, argparse, logging
from pathlib import Path

from src.models import Qwen25VL, Gemini
from src.utils import cut_video, parse_segments, sanitize_segments
from src.globals import ORIGINALS_DIR, CLIPS_DIR
from src.prompts import GEMINI_TEMPORAL_LOCALIZATION, QWEN_FALSE_POSITIVE_VERIFICATION

logging.basicConfig(
    format="[%(asctime)s] %(levelname)s@%(name)s: %(message)s",
    datefmt="%H:%M:%S" # %Y-%m-%d
)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

def main(video_name: str, overwrite=False, gem: Gemini | None = None, qwen: Qwen25VL | None = None) -> list[Path]:
    """
    Given a video -- located in `data/originals/` with name `{video_name}.mp4` -- 
    finds all instances of an action occuring and saves clips of those instances in `data/clips/`.

    The clips are named `{video_name}_i.mp4`, where 'i' is the 1-indexed "index" of the action instance; 
    that is, the clip of the first instance of an action in the provided video has `i=1`; 
    the clip fo the second instance has `i=2`; and so forth.

    Returns a list of Path-like objects pointing to the saved clips.

    An error will be thrown if trying to save a clip that already exists with `overwrite` set to False;
    setting `overwrite` to True avoids this.

    For efficiency purposes, client can choose to pass in instances of Gemini and Qwen2.5-VL in `gem` and `qwen`.
    This allows this function be called multiple times in succession by client while only loading checkpoints onto GPU once.
    """
    video_path = ORIGINALS_DIR / f'{video_name}.mp4'
    logger.info(f"Kicking off pipeline to localize actions in {video_path}")

    # STEP 0: Verify that the provided video exists.
    if not video_path.exists() and not video_path.is_file():
        raise FileNotFoundError(f"Attempting to run pipeline on a video file that doesn't exist: {video_path}")

    # STEP 1: Query Gemini on when the action occurs in the video
    logger.info("Asking Gemini to identify segments where action occured")
    if not gem:
        gem = Gemini('thinking')
    output = gem.inference(GEMINI_TEMPORAL_LOCALIZATION, [video_path])

    # STEP 2: Parse Gemini's response into a list of start/stop times for segments where the action may have occured
    segments = parse_segments(output)
    segments = sanitize_segments(segments)
    logger.info("Segments identified by Gemini")

    # STEP 3: Extract clips corresponding to each segment found by Gemini; save them as '{video_name}_clip_i.mp4'
    cut_video(video_name, segments, overwrite=overwrite)
    logger.info("Clips of segments extracted")

    # STEP 4: Verify via Qwen if *an* action occured in each segment (i.e., filter out false positives)
    logger.info("Begginning second pass using Qwen to identify false positive clips")
    print()
    if not qwen:
        qwen = Qwen25VL()
    verified_segments = set()
    for i in range(1, len(segments) + 1):
        temp_clip_path = CLIPS_DIR / f"{video_name}_clip_{i}.mp4"
        retval = qwen.video_inference(QWEN_FALSE_POSITIVE_VERIFICATION, str(temp_clip_path), is_path=True, fps=16)[0]
        if retval == 'YES':
            verified_segments.add(i)
    print()

    # STEP 5: Filter clips so only those of verified segments remain.
    #         For each temp clip from step 3, save it as a real clip if it was verified by Qwen; otherwise, delete it.
    logger.info("Removing false positives")
    real_clip_paths, j = [], 1
    for i in range(1, len(segments) + 1):
        # false positive; remove it
        temp_clip_path = CLIPS_DIR / f'{video_name}_clip_{i}.mp4'
        if i not in verified_segments:
            os.remove(temp_clip_path)
            continue

        # true positive; save it
        real_clip_path = CLIPS_DIR / f'{video_name}_{j}.mp4'
        if real_clip_path.exists():
            if overwrite:
                os.replace(temp_clip_path, real_clip_path)
            else:
                raise FileExistsError(f'Attempted to save a clip that already exists: {real_clip_path}')
        else:
            os.rename(temp_clip_path, real_clip_path)
        
        real_clip_paths.append(real_clip_path)
        j += 1

    logger.info("Done :)")
    print()
    return real_clip_paths

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="A pipeline to localize action occurences in a video and extract clips of said occurences.")
    parser.add_argument('video', help="name of MP4 video in `data/originals/` to be localized")
    parser.add_argument('--overwrite', action='store_true', help="if clips of same name already exist, overwrite them")
    args = parser.parse_args()

    print()
    logger.info("Initializing Qwen on this device")
    qwen = Qwen25VL()
    gem = Gemini('thinking')
    clips: list[Path] = main(args.video, args.overwrite, gem, qwen)

    print("------------------------------------------------------------------------------------")
    print("\t RESULTING CLIPS:\n")
    for clip in clips:
        print("\t", str(clip))
    print("------------------------------------------------------------------------------------\n")
