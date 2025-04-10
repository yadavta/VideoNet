"""
Given a Sqlite3 database from the clip collection stage and a JSONL file containing GCS addresses of the YouTube videos present in that DB,
    (1) downloads videos from GCS
    (2) converts them to a browser-compatible format, if needed
    (3) trims them based on user-specified start and end times from DB
    (4) uploads clips to GCS
    (5) creates Sqlite3 database for clip verification stage
"""
import argparse, os, json, sqlite3, subprocess, uuid, re, shutil, subprocess, concurrent.futures
import multiprocessing as mp
from datetime import datetime
from tqdm import tqdm
from pathlib import Path
from google.cloud import storage

print()     # space out CLI output nicely

# Parse CLI input
parser = argparse.ArgumentParser(description='Prepare videos from clip collection stage for clip verification stage. See docstring at top of Python file for details.')
parser.add_argument('-d', '--database', required=True, type=str, help='Local path to Sqlite3 database from clip collection')
parser.add_argument('-i', '--jsonl', required=True, type=str, help='Local path to JSONL file')
parser.add_argument('-g', '--gcs', required=True, type=str, help='GCS folder where trimmed clips are uploaded. Should begin with "gs://" and end with "/".')
parser.add_argument('-t', '--tmpdir', required=False, type=str, help='Directory where videos are staged for download, trim, upload. Results are stored here.')
parser.add_argument('-y', '--overwrite', required=False, action='store_true', help='If trimmed clips already exists, chooses to overrwrite them instead of skipping them. Same goes for if converted videos already exist.')
args = parser.parse_args()
args.gcs = os.path.join(args.gcs, 'exact/')
if args.gcs[:5] != 'gs://':
    print("ERROR: GCS bucket given via -g flag must begin with 'gs://'")
    exit()

# Establish temporary directories
tmp_dir = args.tmpdir if args.tmpdir else f"tmp_{datetime.now().strftime('%Y%m%d_%H%M%S')}" 
os.makedirs(tmp_dir, exist_ok=True)
os.makedirs(os.path.join(tmp_dir, "videos"), exist_ok=True)
os.makedirs(os.path.join(tmp_dir, "clips"), exist_ok=True)

# Set up Sqlite connection
def make_dicts(cursor, row): return dict((cursor.description[idx][0], value) for idx, value in enumerate(row))
conn = sqlite3.connect(args.database)
conn.row_factory = make_dicts
cursor = conn.cursor()

# Populate `uuid` field and `yt_id` field of Sqlite database as needed
#   Add `uuid` col if needed
cursor.execute('PRAGMA table_info(Clips)')
columns = cursor.fetchall()
col_names = [col['name'] for col in columns]
if 'uuid' not in col_names:
    cursor.execute('ALTER TABLE Clips ADD COLUMN uuid TEXT')
#   Populate `uuid` col if needed
cursor.execute('SELECT id FROM Clips WHERE uuid IS NULL')
lack_uuid = cursor.fetchall()
for row in lack_uuid:
    cursor.execute('UPDATE Clips SET uuid = ? WHERE id = ?', (str(uuid.uuid4()), row['id']))
#   Populate `yt_id` col if needed
pattern = r'(?:youtube\.com/(?:watch\?(?:.*?&)?v=|shorts/)|youtu\.be/)([a-zA-Z0-9_-]{11})(?:(?:\?|&)si=|&|\?|\s|$)'
cursor.execute('SELECT id, url FROM Clips WHERE yt_id IS NULL')
lack_yt_id = cursor.fetchall()
for row in lack_yt_id:
    match = re.search(pattern, row['url'].strip())
    if match:
        yt_id = match.group(1)
        cursor.execute('UPDATE Clips SET yt_id = ? WHERE id = ?', (yt_id, row['id']))
    else:
        print(f"\tERROR: Unable to extract YouTube ID for URL {row['url']} from row ID {row['id']}")
conn.commit()

# Parse JSONL contents
with open(args.jsonl, 'r') as f:
    lines = [json.loads(l) for l in f]
videos = lines
num_vids = len(videos)
urls = [v['video_path'] for v in videos]   # these are GCS paths, not web URLs
tails = [v.split('/')[-1] for v in urls]
yt_ids = [v.split('/')[-2] for v in urls]    # these are youtube ids, not the sql row ids
exts = [t.split('.')[-1] for t in tails]
assert len(urls) == len(tails) == len(yt_ids) == len(exts), 'size mismatch'

# Check if any videos are included in our DB but missing from GCS (this indicates a failure by yt_crawl)
clips = conn.cursor().execute('select * from clips;').fetchall()
ids_hash = set(yt_ids)
missing = [c['url'] for c in clips if c['yt_id'] not in ids_hash]
if missing:
    print("\n\tERROR: the following YouTube URLs are missing from the GCS bucket [indicating a failure by yt_crawl]")
    print("\t", missing, '\n')
    if not args.tmpdir:
        shutil.rmtree(tmp_dir)
    exit()

# Download videos from GCS, skipping those that have already been downloaded
#   core download logic
def download_video(i):    
    vid_path = f'{tmp_dir}/videos/{tails[i]}'
    if Path(vid_path).is_file():
        return False
    subprocess.run(['curl', '-s', f'https://storage.googleapis.com/{urls[i][5:]}', '--output', vid_path])
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
        print(f"ERROR: unable to get encoding of {urls[i]}")
    video_coding, audio_coding = vres.stdout.strip(), ares.stdout.strip()
    cmd = ['ffmpeg', '-i', vid_path]
    cmd.extend(['-c:v', 'copy'] if exts[i] == 'mkv' and video_coding in acceptable_codecs else ['-c:v', 'libx264'])
    cmd.extend(['-c:a', 'copy'] if audio_coding == 'aac' or audio_coding == 'opus' else ['-c:a', 'aac'])
    out_path = f'{tmp_dir}/videos/{yt_ids[i]}.mp4'
    cmd.append(out_path)
    # check if video already exists
    if Path(out_path).is_file():
        if args.overwrite:
            cmd.append('-y')
        else:
            continue
    # convert video
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode:
        err = f"ERROR: unable to convert {urls[i]} with the following command: {' '.join(cmd)}"
        err_str.append(err)
        err_yts.append(yt_ids[i])
        print(err)

# Trim into clips and upload to GCS
#   core logic for trimming and uploading
def trim_and_upload(clip_data) -> tuple[str | None, str | None, str | None, str | None]:
    """
    Returns 4 tuple of,
        0. UUID of processed clip
        1. Trimmed Tail of processed clip (so uuid.ext where uuid is clip's UUID and ext is clip's file extension)
        2. Error message as a string
        3. ID of YouTube video for which error occured
    Note that [0] and [1] are set IFF operation is successful, meanwhile [2] and [3] are set IFF an error occurs.
    """
    clip, bucket_name, subbuckets, tmp_dir, args = clip_data
    start, end, unique, yt_id = clip['start'], clip['end'], clip['uuid'], clip['yt_id']
    
    # skip if already trimmed
    if not args.overwrite:
        if Path(f'{tmp_dir}/clips/{unique}.mp4').is_file():
            return unique, f"{unique}.mp4", None, None
        if Path(f'{tmp_dir}/clips/{unique}.webm').is_file():
            return unique, f"{unique}.webm", None, None
    
    # determine if we working with a mp4 or webm file
    if Path(f'{tmp_dir}/videos/{yt_id}.mp4').is_file():
        ext = 'mp4'
    elif Path(f'{tmp_dir}/videos/{yt_id}.webm').is_file():
        ext = 'webm'
    else:
        err = f"ERROR: unable to locate a video with MP4 or WEBM extension at {tmp_dir}/videos/{yt_id}"
        print(err)
        return None, None, err, yt_id
    og_path = f"{tmp_dir}/videos/{yt_id}.{ext}"
    
    # ensure start point of trim is during video
    length_cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', og_path]
    res = subprocess.run(length_cmd, capture_output=True, text=True)
    if res.returncode:
        print(res.returncode)
        err = f"ERROR: ffprobe could not determine duration of video with yt id {yt_id}"
        # print(err)
        return None, None, err, yt_id
    duration = float(res.stdout.strip())
    if start > duration:
        err = f"ERROR: clip with UUID {unique} and yt id {yt_id} had duration {duration} but clip start time {start}"
        print(err)
        return None, None, err, yt_id
    
    # trim
    trimmed_path = f"{tmp_dir}/clips/{unique}.{ext}"
    trimmed_tail = f"{unique}.{ext}"
    res = subprocess.run(['ffmpeg', '-loglevel', 'quiet', '-i', og_path, '-ss', str(start), '-to', str(end + 1), trimmed_path, '-y'])
    if res.returncode:
        # trimming failure
        err = f"ERROR: ffmpeg trimming from {start} to {end + 1} failed for uuid {unique} and yt id {yt_id}"
        print(err)
        return None, None, err, yt_id
    else:
        # upload
        storage_client = storage.Client()
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(os.path.join(subbuckets, trimmed_tail))
        blob.upload_from_filename(trimmed_path)
        blob.make_public()
        return unique, trimmed_tail, None, None

#   GCS logic
gcs_without_prefix = args.gcs[5:]           # ex: args.gcs is 'gs://action-atlas/public/skateboarding/', so this removes 'gs://'
gcs_parts = gcs_without_prefix.split('/')   # ex: ['action-atlas', 'public', 'skateboarding', '']
bucket_name, subbuckets = gcs_parts[0], "/".join(gcs_parts[1:]).strip() # ex: 'action-atlas', 'public/skateboarding/'

#   parallelization logic
pinputs = [(clip, bucket_name, subbuckets, tmp_dir, args) for clip in clips]
cores = int((os.cpu_count() - 2) * 0.8)
with mp.Pool(processes=cores) as pool:
    pres = list(tqdm(pool.imap(trim_and_upload, pinputs), total=len(clips), desc="    Trimming & Uploading clips"))
new_tails, uuids = {}, []
for r in pres:
    if r[0]:    # success
        new_tails[r[0]] = r[1]
        uuids.append(r[0])
    if r[2]:    # error
        err_str.append(r[2])
        err_yts.append([r[3]])

# Initialize verification database connection
base = args.database.split('/')[-1].split('.')[0]
vdb_name = f'verify_{base}.db'
vdb_path = f'{tmp_dir}/{vdb_name}'
already_added = set()
if not Path(vdb_path).is_file():
    # if DB doesn't exist, initialize its schema
    Path(vdb_path).touch()
    schema = """
    PRAGMA foreign_keys = ON;

    CREATE TABLE Actions(
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        domain_name TEXT NOT NULL,
        assigned INTEGER DEFAULT 0,
        finished INTEGER DEFAULT 0,
        subdomain TEXT,
        UNIQUE(name, domain_name)
    );

    CREATE TABLE Assignments(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        action_id INTEGER NOT NULL REFERENCES Actions(id),
        completed INTEGER DEFAULT 0,
        user_id TEXT NOT NULL,
        study_id TEXT NOT NULL,
        session_id TEXT NOT NULL,
        UNIQUE (action_id, user_id, study_id)
    );

    CREATE TABLE Clips(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        action_id INTEGER NOT NULL REFERENCES Actions(id),
        gcp_url TEXT NOT NULL UNIQUE,
        uuid TEXT NOT NULL UNIQUE,
        yt_id TEXT NOT NULL,
        start REAL NOT NULL,
        end REAL NOT NULL
    );

    CREATE TABLE Annotations(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        clip_id INTEGER REFERENCES Clips(id) NOT NULL,
        classification INTEGER DEFAULT 0,
        action_id INTEGER REFERENCES Actions(id) NOT NULL,
        user_id TEXT NOT NULL,
        study_id TEXT NOT NULL,
        session_id TEXT NOT NULL,
        UNIQUE (clip_id, user_id, study_id)
    );

    CREATE TABLE Feedback(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        thoughts TEXT NOT NULL,
        user_id TEXT,
        study_id TEXT,
        session_id TEXT
    );"""
    vconn = sqlite3.connect(vdb_path)
    vconn.row_factory = make_dicts
    vcursor = vconn.cursor()

    for statement in schema.split(';'):
        if statement.strip():
            vcursor.execute(statement)

    # and copy over the actions table from the provided clip collection DB    
    cursor.execute('SELECT id, name, domain_name, subdomain FROM Actions')
    res = cursor.fetchall()
    values_strs = []
    for r in res:
        subdomain = "\'{sub}\'".format(sub=r['subdomain']) if r['subdomain'] else 'NULL'
        values_strs.append(f"({r['id']}, '{r['name']}', '{r['domain_name']}', {subdomain})")
    if values_strs:
        insert_str = "INSERT INTO Actions(id, name, domain_name, subdomain) VALUES "
        values_str = ", ".join(values_strs)
        execute_str = insert_str + values_str
        vcursor.execute(execute_str)
        if vcursor.rowcount == 0:
            err = "ERROR: unable to update Actions table in verification table based on provided Actions table from collection table"
            err_str.append(err)
            err_yts.append('N/A; sqlite3 error')
        else:
            vconn.commit()
else:
    # if DB exists, get list of clips that have already been uploaded to GCS so we don't repeat them
    vconn = sqlite3.connect(vdb_path)
    vconn.row_factory = make_dicts
    vcursor = vconn.cursor()
    vcursor.execute('SELECT gcp_url FROM Clips WHERE gcp_url IS NOT NULL')
    res = vcursor.fetchall()
    for r in res:
        already_added.add(r['gcp_url'].split('/')[-1].split('.')[0])

# Add clips to database for verification stage
for unique in uuids:
    if unique in already_added:
        continue
    cursor.execute('SELECT action_id, yt_id, start, end FROM Clips WHERE uuid = ?', (unique,))
    res = cursor.fetchone()
    if res:
        action_id, yt_id, start, end = res['action_id'], res['yt_id'], res['start'], res['end']
        gcp_tail = new_tails[unique]
        gcp_url = 'https://storage.googleapis.com/' + os.path.join(gcs_without_prefix, gcp_tail)
        vcursor.execute('INSERT INTO Clips (action_id, gcp_url, uuid, yt_id, start, end) VALUES (?, ?, ?, ?, ?, ?)', 
                        (action_id, gcp_url, unique, yt_id, start, end))
    else:
        err = f"ERROR: no clip in {args.database} with UUID {unique}"
        err_str.append(err)
        err_yts.append(unique)

vconn.commit()
vconn.close()
conn.close()
print()
if err_str:
    err_str[0] = "\n        " + err_str[0]
    errs = "\n        ".join(err_str)
    error_summary = f"    #### ERROR SUMMARY ####    {errs}\n    #### ENDOF ERRORS ####"
    print(error_summary)
    with open(f'{tmp_dir}/error_summary', 'w') as f:
        f.write(error_summary)
else:
    print("    #### NO ERRORS RECORDED ####    ")
print()
print(f"    #### RESULTS IN {tmp_dir} ####    ")
print()
