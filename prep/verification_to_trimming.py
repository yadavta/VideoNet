"""
Given a Sqlite3 database from the clip verification stage and a JSONL file containing GCS addresses of the YouTube videos present in that DB,
(1) Download videos from GCS
(2) Initialize the database schema for 

Since trimming is I/O bound, parallelizing across nodes is optimal for this task. 
Accordingly, this script is meant to be run via a Job Arary on Hyak (or any other server that uses the SLURM Workload Manager). 
"""
import sqlite3, json, os, subprocess, concurrent.futures, random, time
import multiprocess as mp
from tqdm import tqdm
from pathlib import Path
from google.cloud import storage

CUSHION = 2.0

# Force each node to wait some time before starting to make concurrency issues less likely
task_id = int(os.environ.get('SLURM_ARRAY_TASK_ID'))
time.sleep(7 * task_id + random.uniform(1, 5))

# Config
vdb, jsonl, gcs, tmp_dir, overwrite = os.environ.get('DATABASE'), os.environ.get('JSONL'), os.environ.get('GCS'), os.environ.get('TMPDIR'), int(os.environ.get('OVERWRITE'))
if gcs[:5] != 'gs://':
    print("ERROR: GCS bucket given via -g flag must begin with 'gs://'")
    exit()
gcs_exact = os.path.join(gcs, 'exact/')
gcs_cushion = os.path.join(gcs, 'cushion/')

# Establish temporary directories
os.makedirs(tmp_dir, exist_ok=True)
os.makedirs(os.path.join(tmp_dir, "videos"), exist_ok=True)
os.makedirs(os.path.join(tmp_dir, "clips"), exist_ok=True)

# Get clips from existing database (from verification stage)
def make_dicts(cursor, row): return dict((cursor.description[idx][0], value) for idx, value in enumerate(row))
vconn = sqlite3.connect(vdb)
vconn.row_factory = make_dicts
clips = vconn.execute('select * from clips').fetchall()
annotations = vconn.execute('select * from annotations').fetchall()
vconn.close()

# Only keep the rows corresponding to the clips we have to work on
num_clips, num_nodes, task_id = len(clips), int(os.environ.get('NUM_TASKS')), int(os.environ.get('SLURM_ARRAY_TASK_ID'))
slice_size = num_clips // num_nodes
remainder = num_clips % num_nodes
start_idx = task_id * slice_size + min(task_id, remainder)
end_idx = (task_id + 1) * slice_size + min(task_id + 1, remainder)
clips = clips[start_idx : end_idx]

# Skip clips that have already been processed
base = vdb.split('/')[-1].split('.')[0]
tdb_name = f'trimming_{base}.db'
tdb_path = f'{tmp_dir}/{tdb_name}'
i, proccessed_clips = 0, -1     # -1 is a placeholder, can put any non-list item here
while i < 10:
    try:
        with sqlite3.connect(tdb_path, timeout=20.0) as tconn:
            proccessed_clips = tconn.execute().fetchall()
            tconn.close()
            break
    except sqlite3.OperationalError as e:
        if "locked" in str(e):
            time.sleep(0.1 * (2 ** i) + random.uniform(0, 0.1))
            i += 1
        else:
            print("ERROR: unable to open trimming db")
            print("\t", str(e), "\n")
            i += 5
if proccessed_clips == -1:
    exit(1)
already_processed = set([c['uuid'] for c in proccessed_clips])
clips = [c for c in clips if c['uuid'] not in already_processed]

# Parse JSONL contents
with open(jsonl, 'r') as f:
    lines = [json.loads(l) for l in f]
id_to_gcs = {}
all_videos = lines
all_urls = [v['video_path'] for v in all_videos]   # these are GCS paths, not web URLs
all_yt_ids = [v.split('/')[-2] for v in all_urls]    # these are youtube ids, not the sql row ids
for i in range(len(all_videos)):
    id_to_gcs[all_yt_ids[i]] = all_urls[i]

# Only keep the GCS urls of the videos we have to work with
video_urls, missing = [], []
for clip in clips:
    if clip['yt_id'] in id_to_gcs:
        video_urls.append(id_to_gcs[clip['yt_id']])
    else:
        missing.append(clip['yt_id'])
if missing:
    print("\n\tERROR: the following YouTube URLs are missing from the GCS bucket [indicating a failure by yt_crawl]")
    print("\t", missing, '\n')
    exit()

# Extract info from all parts of the GCS URL
num_vids = len(video_urls)
tails = [v.split('/')[-1] for v in video_urls]
yt_ids = [v.split('/')[-2] for v in video_urls]    # these are youtube ids, not the sql row ids
exts = [t.split('.')[-1] for t in tails]
assert len(video_urls) == len(tails) == len(yt_ids) == len(exts), 'size mismatch'

# At this point, we have two lists of equal length, 
# with `clips` storing dicts of columns of that clip from previous stage's db
# and `video_urls` storing strings of where on GCS the entire YouTube video is stored.
# Both of these lists only store information on the clips **WE** are in charge of processing.

# Download videos from GCS, skipping those that have already been downloaded
#   core download logic
def download_video(i):    
    vid_path = f'{tmp_dir}/videos/{tails[i]}'
    if Path(vid_path).is_file():
        return False
    subprocess.run(['curl', '-s', f'https://storage.googleapis.com/{video_urls[i][5:]}', '--output', vid_path])
    return True
#   parallelization logic
threads = int(1.7 * os.cpu_count())
with concurrent.futures.ThreadPoolExecutor(max_workers=threads) as executor:
    futures = [executor.submit(download_video, i) for i in range(num_vids)]
    for _ in tqdm(concurrent.futures.as_completed(futures), total=num_vids, desc="    Downloading videos"):
        pass

# Ensure all videos are browser-compatible
err_str = []
err_yts = []
defacto_compatible = set(['mp4', 'webm'])
acceptable_codecs = set(['h264', 'vp9', 'av1'])
for i in tqdm(range(num_vids), desc="    Converting videos"):
    if exts[i] in defacto_compatible:
        continue
    
    vid_path = f'{tmp_dir}/videos/{tails[i]}'
    # check encoding
    vcmd = ['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=codec_name', '-of', 'default=nokey=1:noprint_wrappers=1', vid_path]
    acmd = ['ffprobe', '-v', 'error', '-select_streams', 'a:0', '-show_entries', 'stream=codec_name', '-of', 'default=noprint_wrappers=1:nokey=1', vid_path]
    vres = subprocess.run(vcmd, capture_output=True, text=True)
    ares = subprocess.run(acmd, capture_output=True, text=True)
    if vres.returncode or ares.returncode:
        print(f"ERROR: unable to get encoding of {video_urls[i]}")
    video_coding, audio_coding = vres.stdout.strip(), ares.stdout.strip()
    cmd = ['ffmpeg', '-i', vid_path]
    cmd.extend(['-c:v', 'copy'] if exts[i] == 'mkv' and video_coding in acceptable_codecs else ['-c:v', 'libx264'])
    cmd.extend(['-c:a', 'copy'] if audio_coding == 'aac' or audio_coding == 'opus' else ['-c:a', 'aac'])
    out_path = f'{tmp_dir}/videos/{yt_ids[i]}.mp4'
    cmd.append(out_path)
    # check if video already exists
    if Path(out_path).is_file():
        if overwrite:
            cmd.append('-y')
        else:
            continue
    # convert video
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode:
        err = f"ERROR: unable to convert {video_urls[i]} with the following command: {' '.join(cmd)}"
        err_str.append(err)
        err_yts.append(yt_ids[i])
        print(err)

# Trim into clips **WITH CUSHION** and upload to GCS
def trim_and_upload(clip_data) -> tuple[str | None, str | None, str | None, str | None]:
    """
    Returns 3 tuple of,
        0. UUID of processed clip
        1. Error message as a string
        2. ID of YouTube video for which error occured
    Note that [0] is set IFF operation is successful, meanwhile [1] and [2] are set IFF an error occurs.
    """
    clip, gcs_without_prefix, tmp_dir = clip_data
    start, end, unique, yt_id = clip['start'], clip['end'], clip['uuid'], clip['yt_id']

    # ex: gcs_without_prefix is 'action-atlas/public/skateboarding/cushion/'
    gcs_parts = gcs_without_prefix.split('/')   # ex: ['action-atlas', 'public', 'skateboarding', 'cushion', '']
    bucket_name, subbuckets = gcs_parts[0], "/".join(gcs_parts[1:]).strip() # ex: 'action-atlas', 'public/skateboarding/cushion/'
    
    # determine if we working with a mp4 or webm file
    if Path(f'{tmp_dir}/videos/{yt_id}.mp4').is_file():
        ext = 'mp4'
    elif Path(f'{tmp_dir}/videos/{yt_id}.webm').is_file():
        ext = 'webm'
    else:
        err = f"ERROR: unable to locate a video with MP4 or WEBM extension at {tmp_dir}/videos/{yt_id}"
        print(err)
        return None, err, yt_id
    og_path = f"{tmp_dir}/videos/{yt_id}.{ext}"
    
    # ensure start point of trim is during video
    length_cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', og_path]
    res = subprocess.run(length_cmd, capture_output=True, text=True)
    if res.returncode:
        print(res.returncode)
        err = f"ERROR: ffprobe could not determine duration of video with yt id {yt_id}"
        return None, err, yt_id
    duration = float(res.stdout.strip())
    if start > duration:
        err = f"ERROR: clip with UUID {unique} and yt id {yt_id} had duration {duration} but clip start time {start}"
        print(err)
        return None, err, yt_id
    
    # compute cushioned start and end times
    cushion_start = max(0, start - CUSHION)
    cushion_end = min(duration, end + CUSHION)
    
    # trim
    trimmed_path = f"{tmp_dir}/clips/{unique}.{ext}"
    trimmed_tail = f"{unique}.{ext}"
    res = subprocess.run(['ffmpeg', '-loglevel', 'quiet', '-i', og_path, '-ss', str(cushion_start), '-to', str(cushion_end + 1), trimmed_path, '-y'])
    if res.returncode:
        # trimming failure
        err = f"ERROR: ffmpeg trimming from {cushion_start} to {cushion_end + 1} failed for uuid {unique} and yt id {yt_id}"
        print(err)
        return None, err, yt_id
    else:
        # upload
        storage_client = storage.Client()
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(os.path.join(subbuckets, trimmed_tail))
        blob.upload_from_filename(trimmed_path)
        blob.make_public()
        public_url = 'https://storage.googleapis.com/' + os.path.join(gcs_without_prefix, trimmed_tail)
        clip['cushion_start'], clip['cushion_end'], clip['cushion_url'] = cushion_start, cushion_end, public_url
        return unique, None, None

#   parallelization logic
gcs_without_prefix = gcs_cushion[5:]        # ex: gcs_cushion is 'gs://action-atlas/public/skateboarding/cushion/', so this removes 'gs://'
pinputs = [(clip, gcs_without_prefix, tmp_dir) for clip in clips]
cores = int((os.cpu_count() - 2) * 0.8)
with mp.Pool(processes=cores) as pool:
    pres = list(tqdm(pool.imap(trim_and_upload, pinputs), total=len(clips), desc="    Trimming & Uploading clips"))
uuids = []  # list of UUIDs that were successfully trimmed and uploaded to GCS
for r in pres:
    if r[0]:    # success
        uuids.append(r[0])
    if r[2]:    # error
        err_str.append(r[2])
        err_yts.append([r[3]])
        
# Accumulate votes from annotations
clip_ids = set([c['id'] for c in clips])
for c in clips:
    c['votes'] = '000'
for a in annotations:
    if a['clip_id'] in clip_ids and a['uuid'] in uuids:
        idx = a['classification'] - 1
        if idx == -1:
            print(f"ERROR: no classification provided for annotation with ID {a['id']}")
            continue
        tmp = c['votes']
        tmp[idx] = str(int(tmp[idx]) + 1)
        c['votes'] = tmp

# TODO: compute rating from votes for each clip


# Prepare SQL statement to update trimming database
sql = "INSERT INTO Clips (id, action_id, exact_url, cushion_url, uuid, yt_id, og_start, og_end, cushion_start, cushion_end, votes, rating) VALUES"
for c in clips:
    if c['unique'] in uuids:
        sql += f" ({c['id']}, {c['action_id']}, {c['url']}, {c['cushion_url']}, {c['unique']}, {c['yt_id']}, {c['start']}, {c['end']}, {c['cushion_start']}, {c['cushion_end']}, {c['votes']}, {c['rating']}),"
if sql[-1] == ',':
    sql = sql[:-1]

# Connect to trimming database and commit updates
i = 0
while i < 10:
    try:
        with sqlite3.connect(tdb_path, timeout=20.0) as tconn:
            tconn.execute(sql)
            tconn.commit()
            break
    except sqlite3.OperationalError as e:
        if "locked" in str(e):
            time.sleep(0.1 * (2 ** i) + random.uniform(0, 0.1))
            i += 1
        else:
            print("ERROR: unable to save to trimming db")
            print("\t", str(e), "\n")
            i += 5