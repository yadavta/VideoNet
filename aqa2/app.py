from flask import Flask, request, render_template, g, make_response
from sqlite3 import Connection
import sqlite3, os, subprocess
import a2utils

app = Flask(__name__)
DATABASE = os.environ.get('DATABASE', '/persistent/data.db')
PROLIFIC_COMPLETION_CODE = os.environ.get('PROLIFIC_COMPLETION_CODE')
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

ERROR_MSG = "<h1> This page is only accessible through Prolific. </h1> <p> If you reached this page through Prolific, please report our study as having an error in the setup. </p>"

@app.route('/')
def show_error():
    return ERROR_MSG

@app.route('/return-tasks-ostrich')
def return_tasks():
    if request.args.get('animal') == 'beaver':
        subprocess.run(['python', '/opt/render/project/src/aqa2/return_tasks.py'])
        return 'Returned (if applicable)', 200
    else:
        return 'Wrong Password', 401

@app.route('/task')
def show_task():
    """
    Renders landing page for a Prolific user if given a URL with the required params (PROLIFIC_PID, STUDY_ID, SESSION_ID).
    
    Otherwise renders an error message.
    
    Note that the "landing page" contains the entirety of the task; the only other page the user will interact with is the "finish page".
    """
# Extract identifiers provided by Prolific; see https://researcher-help.prolific.com/en/article/866615
    user_id: str | None = request.args.get('PROLIFIC_PID')
    study_id: str | None = request.args.get('STUDY_ID')
    session_id: str | None = request.args.get('SESSION_ID')
    if not user_id or not study_id or not session_id:
        return ERROR_MSG
     
    # get asignment
    assignment_info = a2utils.get_assignment(get_db(), user_id, study_id, session_id)
    if isinstance(assignment_info, str): return assignment_info
    batch_uuid, domain = assignment_info
    
    # get videos
    videos: list[tuple[str, str, int, int, str, str, str]] | str = a2utils.get_videos(get_db(), batch_uuid)
    if isinstance(videos, str): return videos
    
    start_times: list[str] = [a2utils.convert_time_to_str(v[2]) for v in videos]
    end_times: list[str] = [a2utils.convert_time_to_str(v[3], end=True) for v in videos]
    kwargs = {'videos': videos, 'domain': domain, 'starts': start_times, 'ends': end_times,
              'user_id': user_id, 'study_id': study_id, 'session_id': session_id, 'batch_uuid': batch_uuid}
    
    response = make_response(render_template('start.html', **kwargs))
    return response

@app.route('/submit', methods=['POST'])
def submit_annotations():
    """
    Adds the user annotations for the videos to the Videos database.

    Upon success, returns HTML for survey finish page. Upon failure, returns helpful error message in string form.
    """
    args = request.form
    if 'user_id' not in args or 'study_id' not in args or 'session_id' not in args:
        return "We had trouble verifying if your submission originated from Prolific. Please message us."
    user_id, study_id, session_id = args['user_id'], args['study_id'], args['session_id']
    if 'batch_uuid' not in args or 'feedback' not in args:
        return "Your submission was corrupted. Please try again. If the issue persists, please message us."
    batch_uuid, feedback = args['batch_uuid'], args['feedback']
    
    annotations: list[tuple[int, int, str, str, str]] = []
    for i in range(1, int(args['video_count']) + 1):
        if f'v{i}-uuid' not in args or f'action-{i}' not in args or f'v{i}-uuid' not in args:
            return "Your submission was corrupted. Please try again. If the issue persists, please message us."
        unique, action = args.get(f'v{i}-uuid'), args.get(f'action-{i}')
        if action == "": return "It appears that one of your action names is missing. Please fix that and re-submit."

        required_keys = set([f'c-s-min-{i}', f'c-s-sec-{i}', f'c-e-min-{i}', f'c-e-sec-{i}', f'w-s-min-{i}', f'w-s-sec-{i}', f'w-e-min-{i}', f'w-e-sec-{i}'])
        print(required_keys.difference(set(args.keys())))
        if required_keys.difference(set(args.keys())):
            return "Your annotations were corrupted. Please try again. If the issue persists, please message us."
        raw_timestamps = {k: args[k] for k in required_keys}
        timestamps = a2utils.process_timestamps(raw_timestamps, i)
        if (timestamp_error := a2utils.verify_timestamps(timestamps, i)):
            return '<p style="font-size: xx-large">' + timestamp_error + '</p>'
        annotations.append((*timestamps, action, unique, batch_uuid))
    
    if a2utils.update_videos(get_db(), annotations):
        return "We were unable to process your annotations. Please go back and hit 'submit' again. If the issue persists, please message us."
    if a2utils.mark_finished(get_db(), batch_uuid, user_id, study_id, session_id):
        return "We have processed your annotations but were unable to mark your study as complete in our server. Please message us on Prolific and submit a NOCODE; we will make sure to approve your submission so you get paid."
    
    if feedback and feedback != '':
        a2utils.add_feedback(get_db(), feedback, user_id, study_id, session_id)
    
    kwargs = {'completion_code': PROLIFIC_COMPLETION_CODE}
    response = make_response(render_template('finish.html', **kwargs))
    return response