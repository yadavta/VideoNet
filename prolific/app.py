from flask import Flask, request, render_template, g, redirect, url_for
from prolific.utils import assign_videos, get_next_video_id, get_next_clip, update_uclip_as_processed, update_video_as_processed, remaining_videos, get_cushion_url, get_exact_url, get_clip_times
import prolific.utils as utils
from urllib.parse import urlparse
from markupsafe import escape
from sqlite3 import Connection

import sqlite3, json

app = Flask(__name__)
DATABASE = 'data.db'
ERROR_MSG = "<h1> This page is only accessible through Prolific. </h1> <p> If you reached this page through Prolific, please report our study as having an error in the setup. </p>"

# THE FOLLOWING **MUST** BE CHANGED FOR EACH PROLIFIC STUDY
PROLIFIC_COMPLETION_CODE = "CHHXQERF"

# **** BEGIN DATABASE ****

def get_db() -> Connection:
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
    
    def make_dicts(cursor, row):
        return dict((cursor.description[idx][0], value) for idx, value in enumerate(row))
    db.row_factory = make_dicts

    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

# **** ENDOF DATABASE ****

# **** BEGIN PAGE SERVING ****

@app.route('/')
def show_error():
    return ERROR_MSG

@app.route('/start')
def show_start():
    """
    Renders landing page for a Prolific user if given a URL with the required params (PROLIFIC_PID, STUDY_ID, SESSION_ID). Otherwise renders an error message.
    """
    # https://researcher-help.prolific.com/en/article/866615
    user_id: str | None = request.args.get('PROLIFIC_PID')
    study_id: str | None = request.args.get('STUDY_ID')
    session_id: str | None = request.args.get('SESSION_ID')
    kwargs = {'user_id': user_id, 'study_id': study_id, 'session_id': session_id}
    
    if not user_id or not study_id or not session_id:
        return ERROR_MSG
    else:
        return render_template('start.html', **kwargs)

@app.route('/dashboard', methods=['POST', 'GET'])
def show_dashboard():
    """
    Returns dashboard detailing videos that the Prolific user must work through.
    """
    # Get args
    args = request.form if request.method == 'POST' else request.args
    user_id, study_id, session_id = args.get('user_id'), args.get('study_id'), args.get('session_id')
    start = args.get('start', None)
    if not user_id or not study_id or not session_id:
        return 'An error occured.'

    if start:
        # user just began survey, so we must assign them videos
        assigned: list[int] | str
        total: int
        assigned, total = assign_videos(get_db(), user_id)
        if isinstance(assigned, str):
            # no videos available, render error message
            return assigned
        else:
            video_id: int | str = get_next_video_id(get_db(), user_id)
            if isinstance(video_id, str):
                # no videos left, user has finished study
                kwargs = {'completion_code': PROLIFIC_COMPLETION_CODE}
                return render_template('finish.html')
            kwargs = {'user_id': user_id, 'study_id': study_id, 'session_id': session_id,
                      'videos_left': len(assigned), 'clips_left': total, 'next_video_id': video_id}
            return render_template('dashboard.html', **kwargs)
    else:
        # user just finished a video (or got lost and returned to the dashboard)
        remaining = remaining_videos(get_db(), user_id)
        if isinstance(remaining, str):
            return 'An error occured.'
        elif remaining['nv'] == 0:
            # no videos left, user has finished study
            kwargs = {'completion_code': PROLIFIC_COMPLETION_CODE}
            return render_template('finish.html')
        else:
            # give user next video to work on
            video_id: int = get_next_video_id(get_db(), user_id)
            if isinstance(video_id, str): return video_id
            kwargs = {'user_id': user_id, 'study_id': study_id, 'session_id': session_id,
                      'videos_left': remaining['nv'], 'clips_left': remaining['nc'], 'next_video_id': video_id}
            return render_template('dashboard.html', **kwargs)

@app.route('/count', methods=['POST', 'GET'])
def show_count():
    args = request.form if request.method == 'POST' else request.args
    user_id, study_id, session_id, video_id, clip_type = args.get('user_id'), args.get('study_id'), args.get('session_id'), args.get('video_id'), args.get('clip_type')
    if clip_type == 'next':
        clip: dict | str = get_next_clip(get_db(), video_id)
        if isinstance(clip, str):
            # no more clips left to process
            update_video_as_processed(get_db(), video_id)
            kwargs = {'user_id': user_id, 'study_id': study_id, 'session_id': session_id}
            return redirect(url_for('show_dashboard', **kwargs))
        else:
            # serve next clip from this video
            kwargs = {'user_id': user_id, 'study_id': study_id, 'session_id': session_id, 
                  'clip_exact_url': clip['exact_url'], 'clip_id': clip['id'], 'clip_type': 'next', 'video_id': video_id}
            return render_template('count.html', **kwargs)
    if clip_type == 'remaining':
        clip_id, prev_end_abs, prev_end_rel = args.get('clip_id'), args.get('prev_end_abs'), args.get('prev_end_rel')
        url: str | None = utils.get_exact_url(get_db(), clip_id)
        if url is None:
            return "An error occured while retrieving the URL of the clip."
        kwargs = {'user_id': user_id, 'study_id': study_id, 'session_id': session_id, 'clip_exact_url': url,
                  'clip_type': 'remaining', 'clip_id': clip_id, 'new_start': prev_end_rel, 'prev_end_abs': prev_end_abs, 'video_id': video_id}
        return render_template('count.html', **kwargs)

    return 'An error occured.'

@app.route('/process-count', methods=['POST'])
def process_count():
    args = request.form
    user_id, study_id, session_id, video_id = args.get('user_id'), args.get('study_id'), args.get('session_id'), args.get('video_id')
    count, clip_id = args.get('counted', type=int), args.get('clip_id', type=int)
    kwargs = {'user_id': user_id, 'study_id': study_id, 'session_id': session_id, 'video_id': video_id}

    if count == 0:
        if update_uclip_as_processed(get_db(), clip_id):
            return 'An error occured while marking the clip as processed.'
        kwargs['clip_type'] = 'next'
        return redirect(url_for('show_count', **kwargs))
    else:
        kwargs['count'], kwargs['clip_id'], kwargs['clip_type'] = count, clip_id, args.get('clip_type')
        kwargs['prev_end_abs'], kwargs['prev_end_rel'] = args.get('prev_end_abs', None, type=float), args.get('prev_end_rel', None, type=float)
        return redirect(url_for('show_trim',  **kwargs))

@app.route('/trim', methods=['POST', 'GET'])
def show_trim():
    # ingest arguments
    args = request.form if request.method == 'POST' else request.args
    user_id, study_id, session_id, video_id, clip_id = args.get('user_id'), args.get('study_id'), args.get('session_id'), args.get('video_id'), args.get('clip_id')
    count, clip_type = args.get('count'), args.get('clip_type')
    kwargs = {'user_id': user_id, 'study_id': study_id, 'session_id': session_id, 'video_id': video_id, 'clip_id': clip_id, 'count': count, 'clip_type': clip_type}
    
    # fetch url from database
    url: str | None = get_cushion_url(get_db(), clip_id) if clip_type == 'next' else get_exact_url(get_db(), clip_id)
    if not url:
        return 'Error retrieving URL of clip.'
    kwargs.update({'clip_url': url, 'url_type': 'cushion' if clip_type == 'next' else 'exact'})
    
    # fetch start/end times from database
    clip_times: tuple[float] | None = get_clip_times(get_db(), clip_id)
    if not clip_times:
        return 'Error retrieving start and end times of clip.'
    start, end, cushion_start = clip_times

    # determine where trimmer should start/end
    trimmer_start: float
    trimmer_end: float
    duration = end - start
    if clip_type == 'next':
        trimmer_start = start - cushion_start
        trimmer_end = trimmer_start + duration
    else:
        prev_end_abs, prev_end_rel = args.get('prev_end_abs', type=float), args.get('prev_end_rel', type=float)
        kwargs.update({'prev_end_abs': prev_end_abs, 'prev_end_rel': prev_end_rel})
        trimmer_start = prev_end_rel
        trimmer_end = end
    print(type(trimmer_start), type(trimmer_end))
    kwargs.update({'trimmer_start': trimmer_start, 'trimmer_end': trimmer_end})
    
    # render trim page to user
    return render_template('trim.html', **kwargs)

@app.route('/process-trim', methods=['POST'])
def process_trim():
    args = request.form
    user_id, study_id, session_id, video_id = args.get('user_id'), args.get('study_id'), args.get('session_id'), args.get('video_id')
    clip_id, endpoint = args.get('clip_id', type=int), args.get('endpoint')
    kwargs = {'user_id': user_id, 'study_id': study_id, 'session_id': session_id, 'video_id': video_id}
    if endpoint == 'skip':
        if update_uclip_as_processed(get_db(), clip_id): return 'An error occured while marking the clip as processed.'
        kwargs['clip_type'] = 'next'
        return redirect(url_for('show_count', **kwargs))
    if endpoint == 'confirm':
        count, ui_start, ui_end = args.get('count', type=int), args.get('ui_start', type=float), args.get('ui_end', type=float)

        clip_times: tuple[float] | None = get_clip_times(get_db(), clip_id)
        if not clip_times:
            return 'Error retrieving start and end times of clip.'
        start, _, cushion_start = clip_times

        real_start: float
        real_end: float
        url_type, prev_end_rel = args.get('url_type'), args.get('prev_end_rel', type=float)
        if url_type == 'cushion':
            real_start = cushion_start + ui_start
            real_end = cushion_start + ui_end
        else:
            real_start = start + prev_end_rel + ui_start
            real_end = start + prev_end_rel + ui_end

        utils.add_verified_clip(get_db(), real_start, real_end, clip_id, video_id, user_id, study_id, session_id)
        if count == 1:
            if update_uclip_as_processed(get_db(), clip_id): return 'An error occured while marking the clip as processed.'
            kwargs['clip_type'] = 'next'
        else:
            kwargs.update({'clip_type': 'remaining', 'clip_id': clip_id, 'prev_end_abs': real_end, 'prev_end_rel': real_end - start})
        
        return redirect(url_for('show_count', **kwargs))
    
    # TODO: can likely get rid of `prev_end_abs` everywhere
    
    return 'Error processing user trim.'

# **** ENDOF PAGE SERVING ****